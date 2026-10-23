"""Offline paper-path contracts; transport fixtures never contact public APIs."""
import json
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import pytest
from fields_study_flow.sources_adapters import SearchService, Response
from fields_study_flow import mcp_tools
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.roadmap import build_roadmap, render_markdown

ATOM = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>http://arxiv.org/abs/1706.03762v2</id><title> A Transformer\n study </title>
<author><name> Ada  Researcher </name></author><published>2017-06-12T00:00:00Z</published>
<summary> Transformer models\n for learning. </summary><category term="cs.CL"/>
</entry></feed>'''

@pytest.mark.parametrize('url', ['https://arxiv.org/abs/1706.03762', 'https://arxiv.org/pdf/1706.03762.pdf'])
def test_metadata_to_prerequisites_and_export(tmp_path, url):
    service = SearchService(tmp_path / 'cache', transport=lambda u, t: Response(200, ATOM, u), min_interval=0)
    paper = service.ingest(url)
    assert paper['metadata']['authors'] == ['Ada Researcher']
    assert paper['metadata']['year'] == 2017
    assert paper['metadata']['categories'] == ['cs.CL']
    assert paper['metadata']['summary'] == 'Transformer models for learning.'
    assert paper['metadata']['id'] == 'arxiv:1706.03762'
    assert paper['metadata']['target_paper'] is True
    plan = mcp_tools.buildRoadmap(url, {}, [paper], 'en')
    assert [n['id'] for n in plan['prerequisites']] == ['math', 'python', 'machine learning', 'deep learning', 'transformer']
    assert all(p['checkpoints'] for p in plan['phases'])
    result = mcp_tools.exportPlan(plan, str(tmp_path / 'export'))
    assert json.loads(__import__('pathlib').Path(result['roadmap_json']).read_text()) == plan

@pytest.mark.parametrize('failure', [404, 429, 'timeout', 'no abstract'])
def test_paper_failure_has_actionable_minimal_route(tmp_path, monkeypatch, failure):
    def transport(url, timeout):
        if failure == 'timeout':
            raise TimeoutError('fixture timeout')
        return Response(200 if failure == 'no abstract' else failure, ATOM.replace(b' Transformer models\n for learning. ', b'') if failure == 'no abstract' else b'', url)
    service = SearchService(tmp_path, transport=transport, min_interval=0)
    monkeypatch.setattr('fields_study_flow.sources_adapters.SearchService', lambda: service)
    paper = mcp_tools.ingestUrl('https://arxiv.org/abs/1706.03762', fetchMetadata=True)
    assert paper['metadata']['degraded']
    assert paper['metadata']['next_action']
    plan = mcp_tools.buildRoadmap('paper', {}, [paper])
    assert plan['phases'][0]['checkpoints']

@pytest.mark.parametrize('url', ['https://doi.org/10.1234/example', 'https://example.org/paper.pdf'])
def test_unsupported_paper_url_explains_next_step(url):
    paper = mcp_tools.ingestUrl(url, fetchMetadata=True)
    assert 'arXiv' in paper['metadata']['next_action']
    assert mcp_tools.buildRoadmap(url, {}, [paper])['phases']

def test_pagination_and_stable_identity(tmp_path):
    seen = []
    def transport(url, timeout):
        q = parse_qs(urlsplit(url).query)
        seen.append(q)
        return Response(200, ATOM if q.get('start') == ['0'] else ATOM.replace(b'v2', b'v3'), url)
    service = SearchService(tmp_path, transport=transport, min_interval=0)
    result = service.search('transformer', ['arxiv'], {'pages': 2, 'page_size': 1})
    assert len(seen) == 2
    assert [q['start'] for q in seen] == [['0'], ['1']]
    assert len(result['resources']) == 1
    assert result['resources'][0]['metadata']['id'] == 'arxiv:1706.03762'
    assert service.search('transformer', ['arxiv'], {'pages': 2, 'page_size': 1})['mode'] == 'cache'

def test_github_pages_deduplicate_repository_ids(tmp_path):
    seen = []
    def transport(url, timeout):
        seen.append(parse_qs(urlsplit(url).query))
        return Response(200, json.dumps({'items': [{'id': 123, 'full_name': 'org/repo'}]}).encode(), url)
    result = SearchService(tmp_path, transport=transport, min_interval=0).search('repo', ['github'], {'pages': 2, 'page_size': 1})
    assert [q['page'] for q in seen] == [['1'], ['2']]
    assert len(result['resources']) == 1
    assert result['resources'][0]['metadata']['id'] == 'github:123'


def test_concurrent_cache_rebuild_preserves_provenance(tmp_path):
    def run(i):
        service = SearchService(tmp_path, transport=lambda u, t: Response(200, ATOM, u), min_interval=0)
        return service.search('transformer', ['arxiv'])
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, range(24)))
    assert all(not r['degraded'] for r in results)
    for path in tmp_path.glob('*.json'):
        data = json.loads(path.read_text())
        assert data['resources'][0]['metadata']['source'] == 'arxiv'
        assert data['resources'][0]['metadata']['retrieved_at']
        path.write_text('{broken')
    assert run(0)['mode'] == 'live'
    assert run(1)['mode'] == 'cache'

def test_phase_checkpoints_and_budget_gap():
    target = (date.today() + timedelta(days=7)).isoformat()
    resource = Resource(title='Paper', url='https://example.org/p', source='user', type='paper', estimated_time='20h')
    low = build_roadmap(LearnerProfile(goal='paper', weekly_hours=5, target_date=target, output_language='en'), [resource])
    high = build_roadmap(LearnerProfile(goal='paper', weekly_hours=25, target_date=target), [resource])
    assert low['schedule']['shortfall_hours'] == 15
    assert high['schedule']['shortfall_hours'] == 0
    assert low['schedule']['deadline_feasible'] is False
    assert high['schedule']['deadline_feasible'] is True
    assert (low['schedule']['total_weeks'], high['schedule']['total_weeks']) == (4, 1)
    assert all(p['checkpoints'] for p in low['phases'])
    assert low['phases'][0]['checkpoints'][0] in render_markdown(low)
    assert 'Shortfall: 15' in render_markdown(low)
    resource.estimated_time = 'unknown'
    unknown = build_roadmap(LearnerProfile(goal='paper', weekly_hours=5, target_date=target), [resource])
    assert unknown['schedule']['estimated_hours'] is None
    assert unknown['schedule']['deadline_feasible'] is None
