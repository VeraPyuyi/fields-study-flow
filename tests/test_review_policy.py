import pytest

from fields_study_flow.mcp_tools import validateSources


def validate(note, host='example.org'):
    resource = {'title': 'fixture', 'url': f'https://{host}/paper',
                'license_or_access_note': note}
    return validateSources({'phases': [{'resources': [resource]}]})


@pytest.mark.parametrize('note', [
    'yt-dlp is prohibited',
    'youtube-dl is not allowed',
    'Do not copy full text or download video',
    'Never bypass login and copy full text',
    'Do not download video; yt-dlp is forbidden',
    'Do not use yt-dlp or youtube-dl',
    'Do not copy full text and use yt-dlp',
    'No download video',
])
def test_prohibition_notes_are_allowed(note):
    assert validate(note)['valid']


@pytest.mark.parametrize('note', [
    'Do not copy full text, download video',
    'Do not copy full text but download video',
    'yt-dlp is prohibited; download video',
    'Do not bypass login. Use youtube-dl',
    'download video is not prohibited',
    'No login is required to download video',
    'No restrictions: use yt-dlp',
    'Do not copy full text and you may download video',
    'Do not copy full text! Download video',
])
def test_affirmative_action_outside_negation_is_rejected(note):
    assert not validate(note)['valid']


@pytest.mark.parametrize('host,valid', [
    ('libgenerator.example', True),
    ('notlibgen.example', True),
    ('sci-hub.example', False),
    ('www.libgen.example', False),
    ('LIBGEN.example.', False),
])
def test_prohibited_hosts_match_domain_boundaries(host, valid):
    assert validate('Link only', host)['valid'] is valid
