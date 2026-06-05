from __future__ import annotations

from enum import StrEnum


class ResourceLanguagePreference(StrEnum):
    ZH_FIRST = "zh-first"
    EN_FIRST = "en-first"
    BALANCED = "balanced"
    ZH_ONLY = "zh-only"
    EN_ONLY = "en-only"


OUTPUT_LANGUAGE_ALIASES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "chinese": "zh-CN",
    "中文": "zh-CN",
    "cn": "zh-CN",
    "en": "en",
    "english": "en",
    "英文": "en",
    "bilingual": "bilingual",
    "双语": "bilingual",
    "中英双语": "bilingual",
}

RESOURCE_LANGUAGE_ALIASES = {
    "zh-first": ResourceLanguagePreference.ZH_FIRST,
    "中文优先": ResourceLanguagePreference.ZH_FIRST,
    "优先中文": ResourceLanguagePreference.ZH_FIRST,
    "chinese-first": ResourceLanguagePreference.ZH_FIRST,
    "en-first": ResourceLanguagePreference.EN_FIRST,
    "english-first": ResourceLanguagePreference.EN_FIRST,
    "英文优先": ResourceLanguagePreference.EN_FIRST,
    "优先英文": ResourceLanguagePreference.EN_FIRST,
    "balanced": ResourceLanguagePreference.BALANCED,
    "中英均衡": ResourceLanguagePreference.BALANCED,
    "均衡": ResourceLanguagePreference.BALANCED,
    "zh-only": ResourceLanguagePreference.ZH_ONLY,
    "只要中文": ResourceLanguagePreference.ZH_ONLY,
    "仅中文": ResourceLanguagePreference.ZH_ONLY,
    "en-only": ResourceLanguagePreference.EN_ONLY,
    "只要英文": ResourceLanguagePreference.EN_ONLY,
    "仅英文": ResourceLanguagePreference.EN_ONLY,
}

TRANSLATION_HINTS = {
    "transformer": ("Transformer 推导", "Transformer derivation tutorial"),
    "diffusion": ("扩散模型 推导", "diffusion models derivation course"),
    "yolo": ("YOLO 目标检测 复现", "YOLO object detection tutorial"),
    "ppo": ("PPO TRPO 推导", "PPO TRPO derivation reinforcement learning"),
    "trpo": ("PPO TRPO 推导", "PPO TRPO derivation reinforcement learning"),
    "cnn": ("CNN 卷积神经网络 教程", "CNN convolutional neural network course"),
}


def normalize_output_language(value: str | None) -> str:
    if not value:
        return "zh-CN"
    normalized = OUTPUT_LANGUAGE_ALIASES.get(value.strip().lower())
    if normalized:
        return normalized
    if value in {"zh-CN", "en", "bilingual"}:
        return value
    raise ValueError(f"Unsupported output language: {value}")


def normalize_resource_language_preference(value: str | ResourceLanguagePreference | None) -> ResourceLanguagePreference:
    if isinstance(value, ResourceLanguagePreference):
        return value
    if not value:
        return ResourceLanguagePreference.BALANCED
    normalized = RESOURCE_LANGUAGE_ALIASES.get(value.strip().lower())
    if normalized:
        return normalized
    raise ValueError(f"Unsupported resource language preference: {value}")


def is_chinese_language(language: str | None) -> bool:
    return bool(language and language.lower().startswith("zh"))


def language_weight(language: str | None, preference: ResourceLanguagePreference | str) -> float:
    preference = normalize_resource_language_preference(preference)
    is_zh = is_chinese_language(language)
    is_en = bool(language and language.lower().startswith("en"))

    if preference == ResourceLanguagePreference.ZH_ONLY:
        return 1.15 if is_zh else 0.0
    if preference == ResourceLanguagePreference.EN_ONLY:
        return 1.15 if is_en else 0.0
    if preference == ResourceLanguagePreference.ZH_FIRST:
        return 1.2 if is_zh else 0.85
    if preference == ResourceLanguagePreference.EN_FIRST:
        return 1.2 if is_en else 0.85
    return 1.0


def build_language_queries(goal: str, preference: ResourceLanguagePreference | str) -> list[str]:
    preference = normalize_resource_language_preference(preference)
    base_queries: list[str] = [goal]
    lowered = goal.lower()

    for keyword, (zh_query, en_query) in TRANSLATION_HINTS.items():
        if keyword in lowered:
            if preference in {ResourceLanguagePreference.ZH_FIRST, ResourceLanguagePreference.ZH_ONLY}:
                base_queries.extend([zh_query, en_query])
            elif preference in {ResourceLanguagePreference.EN_FIRST, ResourceLanguagePreference.EN_ONLY}:
                base_queries.extend([en_query, zh_query])
            else:
                base_queries.extend([zh_query, en_query])

    if preference == ResourceLanguagePreference.ZH_ONLY:
        base_queries = [query for query in base_queries if _looks_chinese(query) or query == goal]
    elif preference == ResourceLanguagePreference.EN_ONLY:
        base_queries = [query for query in base_queries if not _looks_chinese(query)]
        if not base_queries:
            base_queries = [goal]

    return _dedupe_preserving_order(base_queries)


def _looks_chinese(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
