from fields_study_flow.paper_explainer import explain_paper


def test_sdk_url_and_cli_expose_same_long_abstract(tmp_path, capsys):
    import asyncio
    import json
    import sys
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from fields_study_flow.cli import main

    abstract = 'Our method uses ' + 'context ' * 30 + 'a gated recurrent memory.'
    xml = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/1706.03762</id><title>Demo</title><summary>' + abstract + '</summary></entry></feed>'
    # Real SDK stdio call; only the public API transport is replaced, no network.
    script = (
        'import runpy; from fields_study_flow import sources_adapters as a; '
        f'xml={xml.encode()!r}; '
        f'service=a.SearchService(cache_dir={str(tmp_path / "cache")!r}, transport=lambda url, timeout: a.Response(200, xml, url), min_interval=0); '
        'a.SearchService=lambda: service; import sys; sys.argv=["server", "--mcp"]; '
        'runpy.run_module("fields_study_flow.mcp_server", run_name="__main__")'
    )
    async def run():
        async with stdio_client(StdioServerParameters(command=sys.executable, args=['-c', script])) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                result = await session.call_tool('explainPaper', {'url': 'https://arxiv.org/abs/1706.03762'})
                assert not result.is_error
                return json.loads(result.content[0].text)
    payload = asyncio.run(run())
    item = payload['source_material']['items'][0]
    assert item['text'] == abstract
    assert item['source_url'] == 'https://arxiv.org/abs/1706.03762'
    assert 'gated recurrent memory' in item['text']
    paper = tmp_path / 'paper.json'
    paper.write_text(json.dumps({'abstract': abstract}), encoding='utf-8')
    assert main(['explain-paper', '--url', str(paper), '--json']) == 0
    cli = json.loads(capsys.readouterr().out)
    assert cli['source_material']['items'][0]['text'] == item['text']
    assert cli['paragraphs'] == payload['paragraphs']


def test_source_material_preserves_context_and_bounds():
    abstract = 'Our method uses ' + 'context ' * 30 + 'a gated recurrent memory.'
    body = '\r\n# Model\n- classifier\n' + 'x' * 20000
    result = explain_paper({'abstract': abstract, 'url': 'https://arxiv.org/abs/1706.03762'}, [body])
    material = result['source_material']
    assert material['untrusted'] is True
    assert material['max_chars'] == 16384
    assert material['items'][0]['text'] == abstract
    assert material['items'][0]['source_url'] == 'https://arxiv.org/abs/1706.03762'
    item = material['items'][1]
    assert item['basis'] == 'user_text[段落1]'
    assert item['text'] == body[:16384-len(abstract)]
    assert item['omitted_range'] == [len(item['text']), len(body)]
    assert item['next_action']
    assert sum(len(i['text']) for i in material['items']) <= material['max_chars']


def test_source_material_empty_paragraph_indices_and_utf8():
    raw = '方法\r\n# Model\n- classifier'
    material = explain_paper(user_text=['', raw])['source_material']
    item = material['items'][0]
    assert item['text'].encode('utf-8') == raw.encode('utf-8')
    assert item['basis'] == 'user_text[段落2]'
    assert item['returned_range'] == [0, len(raw)]
    assert item['omitted_range'] is None



def test_markdown_excerpt_is_single_line_plain_text():
    raw = 'Our method uses\n# Model\n- classifier'
    result = explain_paper(user_text=[raw])
    excerpt = result['paragraphs'][1]['excerpt']
    assert '\n' not in excerpt and '#' not in excerpt
    assert '- classifier' not in excerpt
    assert result['source_material']['items'][0]['text'] == raw
    assert len(result['text'].splitlines()) == 11


def test_later_metric_candidate_is_not_lost():
    result = explain_paper({'abstract': 'Improving accuracy is a major challenge. Our model achieves 95% accuracy.'})
    results = result['paragraphs'][3]
    assert len(results['candidates']) == 2
    assert results['candidates'][1]['numbers'] == ['95%']
    assert results['candidates'][1]['source_sentence'] == 'Our model achieves 95% accuracy.'
    assert '摘要未给出具体指标' not in result['text']
    assert not any(g['role'] == 'results' for g in result['missing_information'])
    assert results['candidates'][1]['status'] == 'candidate_evidence'


def test_candidate_limit_does_not_claim_material_absence():
    result = explain_paper({'abstract': 'Accuracy is a challenge. ' * 10 + 'Our model achieves 95% accuracy.'})
    results = result['paragraphs'][3]
    assert len(results['candidates']) == 4
    assert results['candidate_coverage']['omitted'] == 7
    assert '摘要未给出具体指标' not in result['text']
    assert any(g['reason'] == 'candidate_coverage_incomplete' for g in result['missing_information'] if g['role'] == 'results')


def test_unmatched_numbers_are_not_proof_of_absence_or_validation():
    result = explain_paper({'abstract': 'We measured 95% on held-out samples.'})
    assert '摘要未给出具体指标' not in result['text']
    assert result['paragraphs'][3]['status'] == 'insufficient_material'
