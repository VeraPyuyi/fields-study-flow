from fields_study_flow.language import ResourceLanguagePreference
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.roadmap import build_roadmap


def test_invalid_profile_time_rejected():
    import pytest
    for hours in [-1, 0, True, '8', float('nan'), 169]:
        with pytest.raises(ValueError):
            LearnerProfile(goal='x', weekly_hours=hours)
    for date in ['tomorrow', '2026-02-30', '2026-1-1']:
        with pytest.raises(ValueError):
            LearnerProfile(goal='x', target_date=date)


def test_prerequisites_schedule_known_and_anchor():
    from fields_study_flow.roadmap import render_markdown
    target = Resource(title='Target Transformer', url='https://arxiv.org/abs/1706.03762', source='arxiv', type='paper', concepts=['transformer'], estimated_time='6h', metadata={'target_paper': True})
    slow = build_roadmap(LearnerProfile(goal='transformer', weekly_hours=1, known_topics=['python']), [target])
    fast = build_roadmap(LearnerProfile(goal='transformer', weekly_hours=20, known_topics=['python']), [target])
    nodes = slow['prerequisites']
    ids = [n['id'] for n in nodes]
    for node in nodes:
        assert all(ids.index(dep) < ids.index(node['id']) for dep in node['depends_on'])
    assert next(n for n in nodes if n['id'] == 'python')['status'] == 'skipped'
    assert next(n for n in nodes if n['id'] == 'python')['reason']
    assert slow['schedule']['total_weeks'] > fast['schedule']['total_weeks']
    assert [s['id'] for s in slow['schedule']['items']] == [s['id'] for s in fast['schedule']['items']]
    assert slow['schedule']['target_date'] is None
    assert all(not r['metadata'].get('target_paper') for r in slow['phases'][0]['resources'])
    assert 'Checkpoints' in render_markdown(slow)
    assert 'Schedule' in render_markdown(slow)
    unknown = build_roadmap(LearnerProfile(goal='x', weekly_hours=2), [Resource(title='x',url='https://example.org',source='course',type='article')])
    assert unknown['schedule']['unknown_estimates']


def test_deadline_shortfall_is_explicit():
    from datetime import date
    plan = build_roadmap(LearnerProfile(goal='transformer', weekly_hours=1, target_date=date.today().isoformat()), [])
    assert plan['schedule']['deadline_feasible'] is False


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
