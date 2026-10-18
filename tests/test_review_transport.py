from concurrent.futures import ThreadPoolExecutor
from functools import partial
import json
from pathlib import Path
from threading import Barrier, Event, Lock
import time

from fields_study_flow import sources_adapters as adapters
from fields_study_flow.mcp_tools import ingestUrl, searchResources
from fields_study_flow.sources_adapters import Response, SearchService


REPO = {'id': 42, 'full_name': 'example/graph', 'topics': ['graph']}


def test_mcp_calls_share_source_rate_limit_across_instances(tmp_path, monkeypatch):
    timestamps = []

    def transport(url, timeout):
        timestamps.append(time.monotonic())
        return Response(200, json.dumps(REPO).encode(), url)

    monkeypatch.setattr(adapters, 'SearchService', partial(
        SearchService, cache_dir=tmp_path, transport=transport, min_interval=0.04))
    assert searchResources('one', ['github'], {'offline': False})['mode'] == 'live'
    assert searchResources('two', ['github'], {'offline': False})['mode'] == 'live'
    assert ingestUrl('https://github.com/example/graph', fetchMetadata=True)['metadata']['retrieval_mode'] == 'live'
    assert len(timestamps) == 3
    assert all(b - a >= 0.035 for a, b in zip(timestamps, timestamps[1:]))


def test_concurrent_instances_share_source_rate_limit(tmp_path):
    timestamps, lock, start = [], Lock(), Barrier(4)

    def transport(url, timeout):
        with lock:
            timestamps.append(time.monotonic())
        return Response(200, json.dumps(REPO).encode(), url)

    def search(index):
        service = SearchService(cache_dir=tmp_path / str(index), transport=transport, min_interval=0.04)
        start.wait(timeout=5)
        return service.search(str(index), ['github'])

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(search, range(4)))
    assert all(result['mode'] == 'live' for result in results)
    assert len(timestamps) == 4
    assert all(b - a >= 0.035 for a, b in zip(timestamps, timestamps[1:]))


def test_cache_replacement_keeps_complete_json_during_concurrent_writes(tmp_path, monkeypatch):
    def transport(url, timeout):
        return Response(200, json.dumps(REPO).encode(), url)

    initial = SearchService(cache_dir=tmp_path, transport=transport, min_interval=0)
    initial.search('graph', ['github'])
    cache_path = next(tmp_path.glob('*.json'))
    assert json.loads(cache_path.read_text())['resources'][0]['title'] == 'example/graph'
    started, resume = Event(), Event()
    original_open = Path.open

    def paused_open(path, mode='r', *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        if path == cache_path and 'w' in mode:
            started.set()
            assert resume.wait(timeout=5)
        return handle

    monkeypatch.setattr(Path, 'open', paused_open)

    def refresh():
        return SearchService(cache_dir=tmp_path, transport=transport, min_interval=0, ttl=0).search('graph', ['github'])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(refresh) for _ in range(2)]
        # With atomic writes there is no direct truncation; writers finish.
        # A direct write is paused after truncation to make the race deterministic.
        try:
            started.wait(timeout=0.15)
            visible = cache_path.read_text()
        finally:
            resume.set()
        results = [future.result(timeout=5) for future in futures]
    assert json.loads(visible)['resources'][0]['title'] == 'example/graph'
    assert all(result['mode'] == 'live' for result in results)
    assert json.loads(cache_path.read_text())['resources'][0]['title'] == 'example/graph'
    assert sorted(p.name for p in tmp_path.iterdir()) == [cache_path.name]
