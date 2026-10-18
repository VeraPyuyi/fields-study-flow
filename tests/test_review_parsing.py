from functools import partial
import json

import pytest

from fields_study_flow import sources_adapters as adapters
from fields_study_flow.mcp_tools import ingestUrl, searchResources
from fields_study_flow.sources_adapters import Response, SearchService


@pytest.mark.parametrize('source,body,reason', [
    ('arxiv', b'<feed', 'XML'),
    ('arxiv', b'<html/>', 'Atom feed'),
    ('arxiv', b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2501.12345</id></entry></feed>', 'title'),
    ('github', b'[]', 'object'),
    ('github', b'{"items": {}}', 'items'),
    ('github', b'{"items": [[]]}', 'object'),
    ('github', b'{"id":42,"full_name":null}', 'full_name'),
    ('github', b'{"id":42,"full_name":"a/b","topics":"graph"}', 'topics'),
    ('github', b'{"id":42,"full_name":"a/b","stargazers_count":{}}', 'stargazers_count'),
    ('github', b'{"full_name":"a/b"}', 'id'),
])
@pytest.mark.parametrize('operation', ['search', 'ingest'])
def test_invalid_metadata_degrades_at_both_tool_boundaries(tmp_path, monkeypatch, source, body, reason, operation):
    def transport(url, timeout):
        return Response(200, body, url)

    monkeypatch.setattr(adapters, 'SearchService', partial(
        SearchService, cache_dir=tmp_path, transport=transport, min_interval=0))
    if operation == 'search':
        result = searchResources('graph', [source], {'offline': False})
        assert result['mode'] == 'degraded'
        assert result['resources'] == []
        explanation = str(result['degraded'])
    else:
        url = 'https://github.com/a/b' if source == 'github' else 'https://arxiv.org/abs/2501.12345'
        result = ingestUrl(url, fetchMetadata=True)
        assert result['metadata']['retrieval_mode'] == 'degraded'
        assert result['type'] == 'link'
        explanation = result['metadata']['degraded']
    assert reason.lower() in explanation.lower()
    assert not list(tmp_path.glob('*.json'))


@pytest.mark.parametrize('payload', [[], {'timestamp': 99999999999, 'resources': [None]}])
def test_malformed_cache_is_refetched(tmp_path, payload):
    def transport(url, timeout):
        return Response(200, b'{"id":42,"full_name":"a/b"}', url)

    service = SearchService(cache_dir=tmp_path, transport=transport, min_interval=0)
    service.search('graph', ['github'])
    next(tmp_path.glob('*.json')).write_text(json.dumps(payload))
    result = service.search('graph', ['github'])
    assert result['mode'] == 'live'
    assert result['resources'][0]['title'] == 'a/b'
