import json
import subprocess
import sys

import pytest

from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.roadmap import build_roadmap


def material(name, *, concepts=None, prerequisites=None, hours='2h', target=False):
    return Resource(title=name, url=f'https://example.org/{name}', source='course',
                    type='paper' if target else 'course', difficulty='advanced',
                    concepts=concepts or [name], prerequisites=prerequisites or [],
                    estimated_time=hours, metadata={'target_paper': target})


def test_phases_and_schedule_share_dependency_order_even_for_target_paper():
    resources = [material(f'step-{i}', prerequisites=[f'step-{i-1}'] if i else [])
                 for i in range(8)]
    target = material('target', prerequisites=['step-7'], target=True)
    plan = build_roadmap(LearnerProfile(goal='custom', weekly_hours=2), [target, *reversed(resources)])
    expected = [f'https://example.org/step-{i}' for i in range(8)] + ['https://example.org/target']
    assert [r['url'] for phase in plan['phases'] for r in phase['resources']] == expected
    assert [item['id'] for item in plan['schedule']['items']] == expected
    assert [item['start_week'] for item in plan['schedule']['items']] == [1, 2, 3, 4, 5, 6, 7, 8, 9]


@pytest.mark.parametrize('resources,reason', [
    ([material('a', prerequisites=['b']), material('b', prerequisites=['a'])], 'cycle'),
    ([material('a', prerequisites=['a'])], 'cycle'),
    ([material('a', prerequisites=['unmapped prerequisite'])], 'unknown prerequisite'),
])
def test_unresolvable_dependencies_are_reported(resources, reason):
    with pytest.raises(ValueError, match=reason) as error:
        build_roadmap(LearnerProfile(goal='custom'), resources)
    assert 'a' in str(error.value)


def test_dependency_matching_uses_bilingual_concept_identity():
    target = material('target', prerequisites=['线性代数'], target=True)
    foundation = material('foundation', concepts=['linear algebra'])
    plan = build_roadmap(LearnerProfile(goal='custom'), [target, foundation])
    assert [r['title'] for phase in plan['phases'] for r in phase['resources']] == ['foundation', 'target']


def test_explicitly_known_prerequisite_needs_no_resource():
    target = material('target', prerequisites=['线性代数'], target=True)
    plan = build_roadmap(LearnerProfile(goal='custom', known_topics=['linear algebra']), [target])
    assert [r['title'] for phase in plan['phases'] for r in phase['resources']] == ['target']


def test_target_resource_concepts_seed_prerequisites_without_goal_keyword():
    target = material('target', concepts=['变换器'], target=True)
    plan = build_roadmap(LearnerProfile(goal='Read this paper', known_topics=['机器学习']), [target])
    assert [node['id'] for node in plan['prerequisites']] == ['math', 'python', 'machine learning', 'deep learning', 'transformer']
    assert next(node for node in plan['prerequisites'] if node['id'] == 'machine learning')['status'] == 'skipped'


def test_readme_paper_command_includes_transformer_prerequisites(tmp_path):
    result = subprocess.run([
        sys.executable, '-m', 'fields_study_flow.cli', 'paper', '--url',
        'https://arxiv.org/abs/1706.03762', '--with-videos', '--output-language',
        'bilingual', '--resource-language', 'en-first', '--output-dir', str(tmp_path),
    ], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    plan = json.loads((tmp_path / 'roadmap.json').read_text(encoding='utf-8'))
    assert [node['id'] for node in plan['prerequisites']] == ['math', 'python', 'machine learning', 'deep learning', 'transformer']
    assert all(not r['metadata'].get('target_paper') for r in plan['phases'][0]['resources'])


def test_unknown_duration_propagates_without_erasing_known_hours():
    resources = [material('foundation', hours='unknown'),
                 material('core', prerequisites=['foundation'], hours='4h'),
                 material('practice', prerequisites=['core'], hours='2h')]
    plan = build_roadmap(LearnerProfile(goal='custom', weekly_hours=2, target_date='2099-01-01'), resources)
    schedule = plan['schedule']
    assert [item['hours'] for item in schedule['items']] == [None, 4, 2]
    assert all(item['start_week'] is None and item['end_week'] is None for item in schedule['items'])
    assert schedule['estimated_hours'] is None
    assert schedule['known_estimated_hours'] == 6
    assert schedule['total_weeks'] is None
    assert schedule['deadline_feasible'] is None
    assert schedule['unknown_estimates'] == ['https://example.org/foundation']


def test_known_prefix_keeps_its_weeks_before_unknown_duration():
    plan = build_roadmap(LearnerProfile(goal='custom', weekly_hours=2), [
        material('intro'), material('foundation', prerequisites=['intro'], hours='unknown'),
        material('core', prerequisites=['foundation']),
    ])
    items = plan['schedule']['items']
    assert (items[0]['start_week'], items[0]['end_week']) == (1, 1)
    assert items[2]['start_week'] is None
    assert items[2]['hours'] == 2
