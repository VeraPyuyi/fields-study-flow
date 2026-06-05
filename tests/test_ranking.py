from fields_study_flow.language import ResourceLanguagePreference
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.ranking import rank_resources


def test_rank_resources_values_teaching_structure_over_stars_only():
    profile = LearnerProfile(
        goal="从 CNN 到复现 YOLO",
        output_language="zh-CN",
        resource_language_preference=ResourceLanguagePreference.BALANCED,
        known_topics=["python", "cnn"],
        levels={"programming": "familiar", "ml_dl": "beginner"},
    )
    flashy_repo = Resource(
        title="Popular unrelated repo",
        url="https://github.com/example/popular",
        source="github",
        type="repository",
        language="en",
        difficulty="intermediate",
        concepts=["web"],
        trust_score=0.8,
        metadata={"stars": 50000, "forks": 2000, "has_curriculum": False, "has_notebooks": False},
    )
    teaching_repo = Resource(
        title="YOLO tutorial with notebooks",
        url="https://github.com/example/yolo-course",
        source="github",
        type="repository",
        language="en",
        difficulty="beginner",
        concepts=["cnn", "yolo", "object detection"],
        trust_score=0.7,
        metadata={"stars": 1000, "forks": 100, "has_curriculum": True, "has_notebooks": True, "recently_updated": True},
    )

    ranked = rank_resources([flashy_repo, teaching_repo], profile)

    assert ranked[0].title == "YOLO tutorial with notebooks"
    assert ranked[0].score > ranked[1].score
    assert "matches your goal" in ranked[0].why_recommended


def test_rank_resources_applies_hard_language_filter():
    profile = LearnerProfile(
        goal="理解 Transformer",
        output_language="zh-CN",
        resource_language_preference=ResourceLanguagePreference.ZH_ONLY,
    )
    resources = [
        Resource(title="English Transformer Course", url="https://example.com/en", source="youtube", type="video", language="en"),
        Resource(title="中文 Transformer 课程", url="https://example.com/zh", source="bilibili", type="video", language="zh-CN"),
    ]

    ranked = rank_resources(resources, profile)

    assert [resource.language for resource in ranked] == ["zh-CN"]


def test_rank_resources_deduplicates_by_url_and_keeps_best_candidate():
    profile = LearnerProfile(
        goal="理解 Transformer",
        output_language="zh-CN",
        resource_language_preference=ResourceLanguagePreference.BALANCED,
    )
    weak = Resource(
        title="Transformer duplicate weak",
        url="https://example.com/transformer",
        source="youtube",
        type="video",
        language="en",
        concepts=["transformer"],
        trust_score=0.4,
    )
    strong = Resource(
        title="Transformer duplicate strong",
        url="https://example.com/transformer",
        source="course",
        type="article",
        language="en",
        concepts=["transformer", "attention"],
        trust_score=0.9,
        metadata={"has_curriculum": True},
    )

    ranked = rank_resources([weak, strong], profile)

    assert len(ranked) == 1
    assert ranked[0].title == "Transformer duplicate strong"


def test_rank_resources_prioritizes_explicit_target_paper():
    profile = LearnerProfile(
        goal="fully understand, derive, and reproduce the paper: https://arxiv.org/abs/1706.03762",
        output_language="zh-CN",
        resource_language_preference=ResourceLanguagePreference.EN_FIRST,
        levels={"paper_reading": "beginner"},
    )
    target = Resource(
        title="Attention Is All You Need",
        url="https://arxiv.org/abs/1706.03762",
        source="arxiv",
        type="paper",
        language="en",
        difficulty="advanced",
        concepts=["transformer"],
        trust_score=0.95,
        metadata={"target_paper": True},
    )
    support = Resource(
        title="Transformers from Scratch",
        url="https://github.com/karpathy/nanoGPT",
        source="github",
        type="repository",
        language="en",
        difficulty="intermediate",
        concepts=["transformer", "python"],
        trust_score=0.9,
        metadata={"has_curriculum": True, "stars": 40000, "recently_updated": True},
    )

    ranked = rank_resources([support, target], profile)

    assert ranked[0].url == "https://arxiv.org/abs/1706.03762"


def test_rank_resources_deduplicates_common_url_variants():
    profile = LearnerProfile(
        goal="读懂 Attention Is All You Need",
        output_language="zh-CN",
        resource_language_preference=ResourceLanguagePreference.EN_FIRST,
    )
    abs_page = Resource(
        title="Attention Is All You Need",
        url="https://arxiv.org/abs/1706.03762?utm_source=test",
        source="arxiv",
        type="paper",
        language="en",
        concepts=["transformer"],
        trust_score=0.95,
    )
    pdf_page = Resource(
        title="Attention Is All You Need PDF",
        url="http://arxiv.org/pdf/1706.03762.pdf#page=1",
        source="arxiv",
        type="paper",
        language="en",
        concepts=["transformer"],
        trust_score=0.9,
    )

    ranked = rank_resources([pdf_page, abs_page], profile)

    assert len(ranked) == 1
    assert ranked[0].url.startswith("https://arxiv.org/abs/")
