import pytest

from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.ranking import rank_resources


def difficulty(goal, concepts, levels):
    resource = Resource(title='Study material', url='https://example.org/study',
                        source='course', type='course', difficulty='advanced', concepts=concepts)
    return rank_resources([resource], LearnerProfile(goal=goal, levels=levels))[0].score_components['difficulty']


@pytest.mark.parametrize('concept,domain', [
    ('linear algebra', 'math'), ('线性代数', 'math'),
    ('machine learning', 'ml_dl'), ('深度学习', 'ml_dl'),
])
def test_multiword_concepts_use_their_domain_grade(concept, domain):
    assert difficulty(concept, [concept], {domain: 'advanced', 'programming': 'beginner'}) == 1.0


@pytest.mark.parametrize('concept', ['linear algebra', 'machine learning', 'unmapped topic'])
def test_unrelated_beginner_level_does_not_reduce_fit(concept):
    assert difficulty(concept, [concept], {}) == pytest.approx(0.65)
    assert difficulty(concept, [concept], {'programming': 'beginner'}) == pytest.approx(0.65)


def test_resource_domain_takes_precedence_over_overall_goal():
    assert difficulty('transformer', ['linear algebra'], {'math': 'advanced', 'ml_dl': 'beginner'}) == 1.0


def test_multiword_concept_is_not_matched_by_a_single_word():
    resource = Resource(title='Linear regression', concepts=['linear regression'],
                        url='https://example.org/linear', source='course', type='course')
    ranked = rank_resources([resource], LearnerProfile(goal='linear algebra'))[0]
    assert ranked.score_components['relevance'] == 0
    assert ranked.missing_concepts == ['linear algebra']
