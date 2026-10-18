"""Shared bilingual concept identities for ranking and prerequisite matching."""
import re


ALIASES = {
    'transformer': ('变换器', 'transformer'),
    'diffusion': ('扩散', 'diffusion'),
    'linear algebra': ('线性代数', '线代', 'linear algebra'),
    'probability': ('概率', 'probability'),
    'machine learning': ('机器学习', 'machine learning'),
    'deep learning': ('深度学习', 'deep learning'),
    'python': ('编程', 'python'),
    'database': ('数据库', 'database'),
    'transaction': ('事务', 'transaction'),
    'attention': ('注意力', 'attention'),
}
DOMAINS = {
    'programming': {'python'},
    'math': {'linear algebra', 'probability', 'math'},
    'ml_dl': {'transformer', 'diffusion', 'machine learning', 'deep learning', 'llm', 'yolo', 'cnn', 'ppo', 'trpo', 'attention'},
}

_ALIAS_TO_CONCEPT = {alias: canonical for canonical, aliases in ALIASES.items() for alias in aliases}
_PATTERN = re.compile('|'.join(
    r'(?<![a-z0-9])' + re.escape(alias) + r'(?![a-z0-9])' if alias.isascii() else re.escape(alias)
    for alias in sorted(_ALIAS_TO_CONCEPT, key=len, reverse=True)
))


def tokenize(value: str) -> set[str]:
    normalized = value.lower().replace('/', ' ').replace('-', ' ')
    concepts = set()

    def consume(match):
        concepts.add(_ALIAS_TO_CONCEPT[match.group()])
        return ' '

    remaining = _PATTERN.sub(consume, normalized)
    concepts.update(re.findall(r'[\w]+', remaining))
    return concepts


def concept_id(value: str) -> str:
    normalized = ' '.join(value.lower().replace('-', ' ').split())
    return _ALIAS_TO_CONCEPT.get(normalized, normalized)


def dominant_domain(value: str) -> str | None:
    terms = tokenize(value)
    counts = {domain: len(terms & concepts) for domain, concepts in DOMAINS.items()}
    maximum = max(counts.values())
    matches = [domain for domain, count in counts.items() if count == maximum]
    return matches[0] if maximum and len(matches) == 1 else None
