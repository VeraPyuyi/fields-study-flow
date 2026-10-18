import json
import pytest
from fields_study_flow.sources_adapters import SearchService, Response

ATOM = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2501.12345v1</id><title>Graph learning</title><summary>graph networks</summary></entry></feed>'''
GITHUB = json.dumps({'items': [{'id': 42, 'full_name': 'example/graph', 'html_url': 'https://github.com/example/graph', 'description': 'Graph learning', 'language': 'Python', 'topics': ['graph'], 'stargazers_count': 3}]}).encode()


def test_adapters_normalize_cache_and_filters(tmp_path):
    calls = []
    def transport(url, timeout):
        calls.append(url)
        return Response(200, GITHUB if 'api.github.com' in url else ATOM, url)
    service = SearchService(cache_dir=tmp_path, transport=transport, min_interval=0)
    live = service.search('graph', sources=['arxiv', 'github'], filters={'language': 'en'})
    assert live['mode'] == 'live' and len(live['resources']) == 2
    for r in live['resources']:
        assert r['metadata']['id'] and r['metadata']['retrieved_at']
        assert r['source'] in ['arxiv', 'github'] and r['url'].startswith('https://')
        assert r['language'] == 'en' and r['title']
    cached = service.search('graph', sources=['arxiv', 'github'], filters={'language': 'en'})
    assert cached['mode'] == 'cache' and len(calls) == 2
    papers = service.search('graph', sources=['arxiv', 'github'], filters={'type': 'paper'})
    assert len(papers['resources']) == 1
    assert not service.search('graph', sources=['youtube'])['resources']


@pytest.mark.parametrize('response,reason', [(Response(429,b'', 'https://api.github.com/search/repositories'),'429'), (Response(200,b'not json','https://api.github.com/search/repositories'),'JSON'), (Response(200,GITHUB,'https://evil.example/redirect'),'redirect')])
def test_failures_are_explicit(tmp_path, response, reason):
    def transport(url, timeout):
        return Response(response.status, response.body, url if 'evil' not in response.url else response.url)
    service = SearchService(cache_dir=tmp_path, transport=transport, min_interval=0)
    result = service.search('graph', sources=['github'])
    assert result['mode'] == 'degraded' and not result['resources']
    assert reason.lower() in str(result['degraded']).lower()


def test_timeout_offline_and_credentials(tmp_path):
    def timeout(*args):
        raise TimeoutError('fixture timeout')
    service = SearchService(cache_dir=tmp_path, transport=timeout, min_interval=0)
    result = service.search('unseen-topic', sources=['arxiv'])
    assert result['mode'] == 'degraded' and 'timeout' in str(result['degraded'])
    assert service.search('unseen-topic', offline=True)['mode'] == 'offline'
    for url in ['https://user:secret@github.com/a/b', 'http://127.0.0.1/admin', 'https://github.com.evil.example/a/b']:
        with pytest.raises(ValueError):
            service.ingest(url)


def test_ingest_public_api_metadata(tmp_path):
    def transport(url, timeout):
        return Response(200, json.dumps({'id':42,'full_name':'example/graph','html_url':'https://github.com/example/graph','description':'Graph learning'}).encode(), url)
    service = SearchService(cache_dir=tmp_path, transport=transport, min_interval=0)
    resource = service.ingest('https://github.com/example/graph')
    assert resource['metadata']['id'] == 'github:42'
    assert resource['metadata']['retrieved_at']


def test_ingest_tool_can_request_public_metadata(monkeypatch):
    from fields_study_flow.mcp_tools import ingestUrl
    def fake(self, url):
        if 'example.org' in url:
            raise ValueError('unsupported host')
        return {'title': 'Public fixture', 'url': url}
    monkeypatch.setattr(SearchService, 'ingest', fake)
    assert ingestUrl('https://github.com/example/graph', fetchMetadata=True)['title'] == 'Public fixture'
    assert ingestUrl('https://example.org', fetchMetadata=True)['metadata']['retrieval_mode'] == 'degraded'


def test_cli_ingest_public_metadata_flag(monkeypatch, capsys):
    from fields_study_flow.cli import main
    monkeypatch.setattr(SearchService, 'ingest', lambda self, url: {'title': 'fixture', 'url': url})
    assert main(['ingest-url', 'https://github.com/example/graph', '--fetch-metadata']) == 0
    assert json.loads(capsys.readouterr().out)['title'] == 'fixture'


def test_cli_uses_shared_service(tmp_path, monkeypatch):
    from fields_study_flow.cli import main
    calls = []
    def fake(self, query, sources=None, filters=None, offline=False):
        calls.append((query, sources, offline))
        return {'resources': [], 'mode': 'degraded', 'degraded': ['fixture timeout']}
    monkeypatch.setattr(SearchService, 'search', fake)
    assert main(['roadmap', '--goal', 'graph', '--sources', 'arxiv', '--live', '--output-dir', str(tmp_path)]) == 0
    plan = json.loads((tmp_path / 'roadmap.json').read_text(encoding='utf-8'))
    assert calls == [('graph', ['arxiv'], False)]
    assert plan['retrieval']['degraded'] == ['fixture timeout']


def test_mcp_search_filters_and_degraded_metadata():
    from fields_study_flow.mcp_tools import searchResources, discoverSources
    result = searchResources('diffusion', filters={'offline': True, 'type': 'paper'})
    assert result['mode'] == 'offline'
    assert all(r['type'] == 'paper' for r in result['resources'])
    sources = discoverSources('graph')['sources']
    assert all(s['adapter_status'] == ('implemented' if s['id'] in {'github', 'arxiv'} else 'link-only') for s in sources)
