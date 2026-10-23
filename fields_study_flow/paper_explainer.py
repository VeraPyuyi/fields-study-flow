"""Deterministic evidence organization, not scientific understanding or translation.

Patterns identify candidate passages only. The host agent must check context before
turning these candidates into a natural explanation. No model or network calls.
"""
from __future__ import annotations

import re

ROLES = ('motivation', 'method', 'experiments', 'results', 'limitations', 'outlook')
LABELS = ('研究动机', '方法', '实验设置', '结果', '作者讨论的不足', '作者提出的展望')
PATTERNS = (
    r'\b(problem|dominant|challenge|limited|motivat\w*)\b|问题|动机|挑战',
    r'\b(method|propose|architecture|uses?)\b|方法|提出|采用',
    r'\b(experiments?|evaluate[ds]?|dataset|tasks?)\b|实验|数据集|评估',
    r'\b(achieves?|results?|outperforms?|accuracy|BLEU)\b|结果|准确率|提升',
    r'\b(limitations?|sensitivity|fails?|drawbacks?)\b|不足|局限|失败',
    r'\bfuture\b|未来|展望',
)
GLOSSARY = (
    (r'attention|注意力', 'attention', '注意力机制按相关性汇总信息；这是通用术语解释，具体计算以材料为准。', 'Attention combines information according to relevance; this is general background, not a paper-specific claim.'),
    (r'gradient descent|梯度下降', 'gradient descent', '梯度下降沿损失减小的方向调整模型参数；这是通用术语解释。', 'Gradient descent adjusts model parameters in a direction that reduces loss; this is general background.'),
    (r'\bBLEU\b', 'BLEU', 'BLEU是比较机器翻译与参考译文重合程度的指标，不能单凭它判断所有翻译质量。', 'BLEU measures overlap with reference translations, not every aspect of translation quality.'),
    (r'accuracy|准确率', 'accuracy', '准确率表示预测正确的样本所占比例，需结合测试数据理解。', 'Accuracy is the proportion of correct predictions and depends on the evaluation data.'),
)


def explain_paper(metadata=None, user_text=None, level='beginner', language='zh'):
    if language not in {'zh', 'zh-CN', 'zh-cn', 'en', 'en-US', 'en-GB'}:
        raise ValueError('language must be zh or en')
    if level not in {'beginner', 'familiar', 'advanced'}:
        raise ValueError('level must be beginner, familiar, or advanced')
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError('metadata must be an object')
    if user_text is not None and (not isinstance(user_text, list) or not all(isinstance(p, str) for p in user_text)):
        raise ValueError('user_text must be a list of paragraphs')
    metadata = metadata or {}
    abstract = metadata.get('abstract') or metadata.get('summary') or ''
    if not isinstance(abstract, str):
        raise ValueError('abstract must be text')
    zh = language.startswith('zh')
    sources = [('abstract', abstract)] if abstract.strip() else []
    sources += [(f'user_text[段落{i}]', text) for i, text in enumerate(user_text or [], 1) if text.strip()]
    sentences = [(basis, n, s.strip()) for basis, text in sources
                 for n, s in enumerate(re.split(r'(?<=[.!?。！？])\s+(?!\d)|(?<=[。！？])', text), 1) if s.strip()]
    origin = ('摘要' if abstract else '元数据') + ('及用户提供的正文' if user_text else '')
    prefix = (f'这是基于{origin}的离线材料梳理，并非全文精讲。' if zh else
              'Based on the supplied abstract, metadata or user text, this is an offline evidence outline, not a full-paper explanation. ')
    paragraphs, missing, seen_terms = [], [], set()
    for index, (role, pattern) in enumerate(zip(ROLES, PATTERNS)):
        candidates = [(b, n, s) for b, n, s in sentences if re.search(pattern, s, re.I)]
        if candidates:
            basis, sentence, source = candidates[0]
            # A bounded excerpt is a locator aid, never presented as a translation.
            excerpt = source[:96] + ('…' if len(source) > 96 else '')
            text = (f'关于{LABELS[index]}，材料中检索到候选证据，需结合所在句子的上下文核实。' if zh else
                    f'A candidate passage for {role} is available; check its context before interpreting it. ')
            terms = []
            for regex, name, chinese, english in GLOSSARY:
                if re.search(regex, source, re.I):
                    terms.append(name)
                    if name not in seen_terms:
                        text += chinese if zh else english + ' '
                        seen_terms.add(name)
            numbers = re.findall(r'\d+(?:\.\d+)?%?', source) if role == 'results' else []
            if numbers:
                text += ('该候选句包含数值' + '、'.join(numbers) + '；它们的指标、比较对象与适用条件必须回查原句，不能据此推算提升幅度。' if zh else
                         'The candidate contains ' + ', '.join(numbers) + '; verify metrics, comparisons and conditions in the source. ')
            if role == 'results' and not numbers:
                text += ('摘要未给出具体指标，需查看实验结果表。' if zh else 'No concrete metrics were identified; consult the results table. ')
                missing.append({'role': role, 'request': '请补充结果表及指标定义' if zh else 'Supply results tables and metric definitions.'})
            if not terms and not numbers:
                text += ('原句短摘录为“' + excerpt + '”；这是证据定位，不是中文翻译或科学结论。' if zh else 'Short source excerpt: “' + excerpt + '”. ')
            item = {'role': role, 'text': text, 'basis': [basis], 'excerpt': excerpt,
                    'sentence': sentence, 'status': 'candidate_evidence'}
        else:
            text = (f'材料不足，摘要未说明或当前材料未检索到{LABELS[index]}的可靠证据，请补充对应正文段落。' if zh else
                    f'Insufficient material: {role} is not specified in the abstract or not identified in the supplied text. Supply the relevant paper section. ')
            if role == 'results':
                text += '摘要未给出具体指标，需查看实验结果表。' if zh else 'Consult the experimental results table for concrete metrics. '
            if role in {'limitations', 'outlook'}:
                text += '不能将一般学习建议当作作者的结论。' if zh else 'General reading advice must not be attributed to the authors. '
            item = {'role': role, 'text': text, 'basis': ['inferred'], 'status': 'insufficient_material'}
            missing.append({'role': role, 'request': '实验结果表及评估条件' if zh and role == 'results' else '请提供对应正文段落' if zh else 'Supply the relevant section and evaluation tables.'})
        if index == 0:
            item['text'] = prefix + item['text']
        paragraphs.append(item)
    return {'mode': 'offline_evidence_outline', 'language': 'zh' if zh else 'en', 'level': level,
            'paragraphs': paragraphs, 'text': '\n\n'.join(p['text'] for p in paragraphs),
            'missing_information': missing,
            'source_coverage': [b for b, _ in sources] or ['metadata'],
            'explanation_contract': {'stages': list(ROLES), 'headings': False, 'lists': False,
                                     'length': 'follow evidence and learner needs',
                                     'host_action': 'Verify candidate passages against supplied materials; explain naturally in the requested language. Distinguish author claims, general background and missing evidence. Never infer absent results, limitations or future work.'}}
