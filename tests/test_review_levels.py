import subprocess
import sys

import pytest

from fields_study_flow.mcp_tools import assessKnowledge
from fields_study_flow.models import LearnerProfile


@pytest.mark.parametrize('level', ['begginer', 'expert', '', None, 2, ['beginner']])
def test_invalid_domain_grade_is_rejected_with_allowed_values(level):
    with pytest.raises(ValueError) as error:
        LearnerProfile(goal='python', levels={'programming': level})
    assert 'programming' in str(error.value)
    assert 'beginner' in str(error.value)
    assert 'familiar' in str(error.value)
    assert 'advanced' in str(error.value)


@pytest.mark.parametrize('level', ['beginner', 'familiar', 'advanced', '初学', '熟悉', '老手'])
def test_documented_domain_grades_and_existing_aliases_are_accepted(level):
    assert LearnerProfile(goal='python', levels={'programming': level}).levels['programming'] == level


def test_mcp_assessment_rejects_grade_typo():
    with pytest.raises(ValueError, match='begginer'):
        assessKnowledge('python', confidenceLevels={'programming': 'begginer'})


@pytest.mark.parametrize('value', ['math=begginer', 'math'])
def test_cli_invalid_level_is_a_readable_usage_error(tmp_path, value):
    result = subprocess.run([
        sys.executable, '-m', 'fields_study_flow.cli', 'roadmap', '--goal',
        'linear algebra', '--level', value, '--output-dir', str(tmp_path / 'out'),
    ], capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert 'error:' in result.stderr
    assert 'beginner' in result.stderr
    assert 'Traceback' not in result.stderr
    assert not (tmp_path / 'out').exists()
