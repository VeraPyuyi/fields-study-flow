from fields_study_flow.language import ResourceLanguagePreference
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.roadmap import build_roadmap


def test_build_roadmap_contains_required_files_and_resource_fields():
    profile = LearnerProfile(
        goal="从线代概率到理解 diffusion models",
        output_language="zh-CN",
        resource_language_preference=ResourceLanguagePreference.BALANCED,
        weekly_hours=8,
        levels={"math": "beginner", "ml_dl": "familiar"},
    )
    resources = [
        Resource(
            title="Diffusion Models Course",
            url="https://example.com/diffusion",
            source="youtube",
            type="video",
            language="en",
            difficulty="intermediate",
            concepts=["diffusion models", "score matching"],
            estimated_time="3h",
            trust_score=0.9,
            why_recommended="Strong visual intuition.",
            license_or_access_note="Public video page.",
            translation_note="Use Chinese notes in the roadmap.",
        )
    ]

    roadmap = build_roadmap(profile, resources)

    assert roadmap["profile"]["goal"] == profile.goal
    assert roadmap["outputs"] == [
        "learner_profile.json",
        "resource_index.json",
        "source_registry_snapshot.json",
        "roadmap.md",
        "roadmap.json",
    ]
    resource = roadmap["phases"][0]["resources"][0]
    for field in (
        "title",
        "url",
        "source",
        "type",
        "language",
        "difficulty",
        "prerequisites",
        "concepts",
        "estimated_time",
        "trust_score",
        "why_recommended",
        "license_or_access_note",
        "translation_note",
    ):
        assert field in resource


def test_bilingual_roadmap_keeps_both_language_labels():
    profile = LearnerProfile(
        goal="Understand and reproduce PPO/TRPO",
        output_language="bilingual",
        resource_language_preference=ResourceLanguagePreference.EN_FIRST,
    )

    roadmap = build_roadmap(profile, [])

    assert "Learning Roadmap" in roadmap["title"]
    assert "学习路线" in roadmap["title"]
