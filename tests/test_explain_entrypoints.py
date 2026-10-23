import json
from pathlib import Path

import pytest

from fields_study_flow import mcp_tools
from fields_study_flow.cli import main
from fields_study_flow.mcp_server import TOOLS
from fields_study_flow.sources_adapters import Response, SearchService


def call(**kwargs):
    assert hasattr(mcp_tools, 'explainPaper'), 'explainPaper missing'
    return mcp_tools.explainPaper(**kwargs)


def test_mcp_explain_metadata_and_nine_tools():
    assert len(TOOLS) == 9
    result = call(metadata={'title': 'Demo', 'abstract': 'Our method uses attention.'})
    assert result['paragraphs'][1]['basis'] == ['abstract']
    assert set(TOOLS) >= {'assessKnowledge', 'discoverSources', 'searchResources', 'ingestUrl', 'rankResources', 'buildRoadmap', 'validateSources', 'exportPlan'}


def test_cli_offline_abstract_json(tmp_path, capsys):
    paper = tmp_path / 'paper.json'
    paper.write_text(json.dumps({'title': 'Demo', 'abstract': 'Our method uses attention.'}), encoding='utf-8')
    assert main(['explain-paper', '--url', str(paper), '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['paragraphs'][1]['basis'] == ['abstract']


def test_cli_body_file_avoids_network(tmp_path, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('offline text must not fetch')
    monkeypatch.setattr(SearchService, 'ingest', forbidden)
    body = tmp_path / 'body.txt'
    body.write_text('Our method uses attention.\n\nThe model achieves 85% accuracy.', encoding='utf-8')
    assert main(['explain-paper', '--url', 'https://arxiv.org/pdf/1706.03762', '--text-file', str(body)]) == 0
    text = capsys.readouterr().out
    assert '85%' in text and '用户提供的正文' in text


def test_mcp_arxiv_uses_injected_existing_adapter(tmp_path, monkeypatch):
    from fields_study_flow import sources_adapters
    xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/1706.03762</id><title>Attention Is All You Need</title><summary>Our method uses attention.</summary></entry></feed>'
    def transport(url, timeout):
        assert url == 'https://export.arxiv.org/api/query?id_list=1706.03762'
        return Response(200, xml, url)
    service = SearchService(cache_dir=tmp_path, transport=transport, min_interval=0)
    monkeypatch.setattr(sources_adapters, 'SearchService', lambda: service)
    result = call(url='https://arxiv.org/pdf/1706.03762.pdf')
    assert result['paragraphs'][1]['basis'] == ['abstract']


@pytest.mark.parametrize('url', ['https://sci-hub.se/paper', 'http://arxiv.org/abs/1706.03762', 'https://example.com/a.pdf', 'https://user:pass@arxiv.org/abs/1706.03762'])
def test_unsupported_remote_urls_rejected_before_transport(url, monkeypatch):
    monkeypatch.setattr(SearchService, 'ingest', lambda *a: pytest.fail('unsafe fetch'))
    with pytest.raises(ValueError):
        call(url=url)


def test_mcp_never_reads_server_local_path(tmp_path):
    paper = tmp_path / 'secret.txt'
    paper.write_text('Our method uses attention.')
    with pytest.raises(ValueError):
        call(url=str(paper))


def test_cli_local_plain_text_is_user_material(tmp_path, capsys):
    paper = tmp_path / 'paper.txt'
    paper.write_text('Our method uses attention.', encoding='utf-8')
    assert main(['explain-paper', '--url', str(paper), '--language', 'en', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['paragraphs'][1]['basis'] == ['user_text[段落1]']


def test_missing_source_is_explicit_error():
    with pytest.raises(ValueError):
        call()
