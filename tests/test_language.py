from git4study.language import (
    ResourceLanguagePreference,
    build_language_queries,
    language_weight,
    normalize_output_language,
    normalize_resource_language_preference,
)


def test_language_preferences_normalize_aliases():
    assert normalize_output_language("zh") == "zh-CN"
    assert normalize_output_language("bilingual") == "bilingual"
    assert normalize_resource_language_preference("中文优先") == ResourceLanguagePreference.ZH_FIRST
    assert normalize_resource_language_preference("en-only") == ResourceLanguagePreference.EN_ONLY


def test_build_language_queries_balances_chinese_and_english_terms():
    queries = build_language_queries(
        "从 Python 到掌握 Transformer",
        ResourceLanguagePreference.BALANCED,
    )

    assert "从 Python 到掌握 Transformer" in queries
    assert any("Transformer" in query and "derivation" in query for query in queries)
    assert any("Transformer" in query and "推导" in query for query in queries)


def test_language_weight_respects_hard_language_filters():
    assert language_weight("zh-CN", ResourceLanguagePreference.ZH_ONLY) > 0
    assert language_weight("en", ResourceLanguagePreference.ZH_ONLY) == 0
    assert language_weight("zh-CN", ResourceLanguagePreference.EN_ONLY) == 0
    assert language_weight("en", ResourceLanguagePreference.EN_ONLY) > 0


def test_language_weight_soft_preferences_keep_high_quality_cross_language_resources():
    assert language_weight("zh-CN", ResourceLanguagePreference.ZH_FIRST) > language_weight(
        "en", ResourceLanguagePreference.ZH_FIRST
    )
    assert language_weight("en", ResourceLanguagePreference.EN_FIRST) > language_weight(
        "zh-CN", ResourceLanguagePreference.EN_FIRST
    )
    assert language_weight("en", ResourceLanguagePreference.BALANCED) == language_weight(
        "zh-CN", ResourceLanguagePreference.BALANCED
    )
