import pytest

from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.roadmap import build_roadmap


def course(title, concepts, prerequisites=(), difficulty='advanced'):
    return Resource(title=title, url=f'https://example.org/{title}', source='course',
                    type='course', concepts=list(concepts), prerequisites=list(prerequisites),
                    estimated_time='2h', difficulty=difficulty)


@pytest.mark.parametrize('concept,dependency', [('python', 'python'), ('编程', 'Python')])
def test_planned_python_foundation_satisfies_advanced_self_dependency(concept, dependency):
    advanced = course('advanced-python', [concept], [dependency])
    plan = build_roadmap(LearnerProfile(goal='advanced Python', weekly_hours=2), [advanced])
    assert plan['prerequisites'] == [{
        'id': 'python', 'depends_on': [], 'estimated_hours': 6, 'status': 'required',
        'reason': 'Prerequisite for target concepts',
    }]
    assert plan['schedule']['items'] == [
        {'id': 'python', 'hours': 6, 'kind': 'prerequisite', 'start_week': 1, 'end_week': 3},
        {'id': advanced.url, 'hours': 2, 'kind': 'resource', 'start_week': 4, 'end_week': 4},
    ]
    assert [r['title'] for phase in plan['phases'] for r in phase['resources']] == ['advanced-python']
    assert plan['schedule']['total_weeks'] == 4


def test_concrete_foundation_precedes_advanced_course_with_shared_concept():
    # Equal difficulty and advanced-first input ensure ordering follows coverage.
    advanced = course('advanced-python', ['python'], ['python'])
    foundation = course('python-intro', ['python'])
    plan = build_roadmap(LearnerProfile(goal='Python'), [advanced, foundation])
    assert [r['title'] for phase in plan['phases'] for r in phase['resources']] == ['python-intro', 'advanced-python']
    assert [item['id'] for item in plan['schedule']['items']] == ['python', foundation.url, advanced.url]


def test_custom_foundation_covers_advanced_course_with_shared_concept():
    advanced = course('advanced-custom', ['custom'], ['custom'])
    foundation = course('custom-intro', ['custom'])
    plan = build_roadmap(LearnerProfile(goal='study'), [advanced, foundation])
    assert not plan['prerequisites']
    assert [item['id'] for item in plan['schedule']['items']] == [foundation.url, advanced.url]


def test_known_python_satisfies_self_dependency_without_replanning():
    advanced = course('advanced-python', ['python'], ['编程'])
    plan = build_roadmap(LearnerProfile(goal='Python', known_topics=['Python']), [advanced])
    assert plan['prerequisites'][0]['status'] == 'skipped'
    assert [item['id'] for item in plan['schedule']['items']] == [advanced.url]


def test_planned_coverage_unblocks_resource_chain_before_cycle_detection():
    # The Python estimate is an independent provider, so this apparent resource
    # cycle is resolvable: Python foundation -> practice -> advanced Python.
    advanced = course('advanced-python', ['python'], ['practice'])
    practice = course('practice', ['practice'], ['python'])
    plan = build_roadmap(LearnerProfile(goal='Python'), [advanced, practice])
    assert [item['id'] for item in plan['schedule']['items']] == ['python', practice.url, advanced.url]
    assert [r['title'] for phase in plan['phases'] for r in phase['resources']] == ['practice', 'advanced-python']


@pytest.mark.parametrize('resources,expected', [
    ([course('advanced-custom', ['custom'], ['custom'])], ['cycle', 'advanced-custom', 'custom']),
    ([course('course-a', ['a'], ['b']), course('course-b', ['b'], ['a'])], ['cycle', 'course-a', 'course-b', 'a', 'b']),
    ([course('advanced-python', ['python', 'a'], ['python', 'b']), course('course-b', ['b'], ['a'])],
     ['cycle', 'advanced-python', 'course-b', 'a', 'b']),
    ([course('advanced-python', ['python'], ['python', 'missing-basics'])], ['unknown prerequisite', 'advanced-python', 'missing-basics']),
])
def test_uncovered_dependencies_still_report_readable_errors(resources, expected):
    with pytest.raises(ValueError) as error:
        build_roadmap(LearnerProfile(goal='study'), resources)
    for term in expected:
        assert term in str(error.value)
