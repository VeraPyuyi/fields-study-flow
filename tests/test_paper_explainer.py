"""Offline contracts: evidence, gaps, language and entry points."""
import importlib.util
import json
import re

import pytest

ATTENTION = {
    'title': 'Attention Is All You Need',
    'abstract': 'The dominant sequence transduction models are based on complex recurrent or convolutional neural networks. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms. Experiments on two machine translation tasks show these models to be superior in quality while being more parallelizable. Our model achieves 28.4 BLEU on the WMT 2014 English-to-German translation task.',
}
RESULTS = {
    'title': 'Small classifier',
    'abstract': 'The problem is image classification with limited data. Our method uses a classifier with gradient descent. We evaluate on the CIFAR dataset. The model achieves 91.2% accuracy. A limitation is sensitivity to noisy labels. Future work will evaluate robustness.',
}
TITLE_ONLY = {'title': 'A study of learning'}


def explain(*args, **kwargs):
    assert importlib.util.find_spec('fields_study_flow.paper_explainer'), 'missing deterministic explainer'
    from fields_study_flow.paper_explainer import explain_paper
    return explain_paper(*args, **kwargs)


@pytest.mark.parametrize('paper', [ATTENTION, RESULTS, TITLE_ONLY])
def test_six_ordered_prose_paragraphs_without_invented_numbers(paper):
    result = explain(paper)
    assert [p['role'] for p in result['paragraphs']] == ['motivation', 'method', 'experiments', 'results', 'limitations', 'outlook']
    assert result['text'].split('\n\n') == [p['text'] for p in result['paragraphs']]
    assert not re.search(r'(?m)^\s*(#|[-*+] |\d+[.)] )', result['text'])
    assert set(re.findall(r'\d+(?:\.\d+)?%?', result['text'])) <= set(re.findall(r'\d+(?:\.\d+)?%?', json.dumps(paper)))
    for p in result['paragraphs']:
        assert p['basis']
        if 'inferred' in p['basis']:
            assert '材料不足' in p['text'] and '未说明' in p['text']
            assert p['role'] in [gap['role'] for gap in result['missing_information']]


def test_title_only_does_not_infer_scientific_claims():
    result = explain(TITLE_ONLY)
    assert len(result['missing_information']) == 6
    assert '摘要未给出具体指标，需查看实验结果表' in result['text']
    assert '元数据' in result['text']
    assert all(p['basis'] == ['inferred'] for p in result['paragraphs'])


def test_sufficient_material_has_beginner_explanations_and_detail():
    result = explain(RESULTS)
    assert result['mode'] == 'offline_evidence_outline'
    assert '离线材料梳理' in result['text']
    assert result['explanation_contract']['headings'] is False
    assert result['explanation_contract']['lists'] is False
    assert result['explanation_contract']['length'] == 'follow evidence and learner needs'
    assert '梯度下降' in result['text'] and '参数' in result['text']
    assert '91.2%' in result['paragraphs'][3]['text']
    assert not result['missing_information']
    assert all(p['basis'] == ['abstract'] for p in result['paragraphs'])


def test_english_request_and_short_evidence():
    result = explain(ATTENTION, language='en')
    assert 'Based on' in result['text'] and 'attention' in result['text'].lower()
    assert not re.search('[\u4e00-\u9fff]', result['text'])
    assert 'not specified' in result['paragraphs'][4]['text']
    assert all(len(p.get('excerpt', '')) <= 100 for p in result['paragraphs'])


def test_user_text_anchors_preserve_original_paragraph_indices():
    result = explain(TITLE_ONLY, user_text=['', 'Our method uses gradient descent.', 'The model achieves 85% accuracy.'])
    assert result['paragraphs'][1]['basis'] == ['user_text[段落2]']
    assert result['paragraphs'][3]['basis'] == ['user_text[段落3]']
    assert '85%' in result['paragraphs'][3]['text']
    assert '用户提供的正文' in result['text']


def test_qualitative_results_do_not_invent_metrics():
    result = explain({'abstract': 'Results show better translation quality.'})
    assert '摘要未给出具体指标，需查看实验结果表' in result['paragraphs'][3]['text']
    assert any(gap['role'] == 'results' for gap in result['missing_information'])
    assert result['paragraphs'][3]['basis'] == ['abstract']


def test_long_chinese_material_is_not_reproduced_in_prose():
    result = explain({'abstract': '我们提出方法。' + '这是一段说明文字。' * 100})
    assert len(result['paragraphs'][1]['excerpt']) <= 100
    assert '这是一段说明文字。' * 10 not in result['text']


@pytest.mark.parametrize('kwargs', [{'language': 'fr'}, {'level': 'expert'}, {'user_text': 'not a list'}, {'user_text': [4]}])
def test_invalid_explanation_options_are_rejected(kwargs):
    with pytest.raises(ValueError):
        explain(ATTENTION, **kwargs)
