import pytest

from fields_study_flow.mcp_tools import validateSources


def validate(note, policy=None, url='https://example.org/course'):
    resource = {'title': 'public course', 'url': url, 'license_or_access_note': note}
    if policy is not None:
        resource['metadata'] = {'access_policy': policy}
    return validateSources({'phases': [{'resources': [resource]}]})


@pytest.mark.parametrize('note', [
    'Videos need to be downloaded',
    'The video needs to be downloaded',
    'Video content needs to be downloaded',
    'These videos have to be downloaded',
    'The video has to be downloaded',
    'Videos are required to be downloaded',
    'You need to download videos',
    'Please download the videos',
    'Login needs to be bypassed',
    'Full text has to be copied',
    'Restricted pages need to be scraped',
    'Do not copy full text and videos need to be downloaded',
    'Do not download videos or login has to be bypassed',
])
def test_active_and_passive_obligations_are_rejected(note):
    result = validate(note)
    assert not result['valid'], note
    assert any('Disallowed access instruction' in issue for issue in result['issues'])


@pytest.mark.parametrize('note', [
    'Downloading videos is never permitted',
    'Downloading the video is never allowed',
    'Downloading video content is not permitted',
    'Bypassing login is never permitted',
    'Copying full text is never allowed',
    'Scraping restricted pages is never permitted',
    'Downloading videos and bypassing login are never permitted',
    'Downloading videos, copying full text, and bypassing login are never allowed',
    'yt-dlp and youtube-dl are never permitted',
    'You are never permitted to download videos',
])
def test_negated_permission_prohibits_only_its_action_list(note):
    assert validate(note) == {'valid': True, 'issues': []}


@pytest.mark.parametrize('note', [
    'Do not copy full text and instead watch and download video content',
    'Never copy full text; instead watch and download videos',
    'Do not bypass login and instead read and copy full text',
    'Do not copy full text and instead inspect and scrape restricted pages',
    'Do not copy full text and instead watch and use yt-dlp',
    'Do not download videos but read and bypass login',
    'Do not copy full text and then watch and download videos',
    'Do not copy full text and please watch and download videos',
    'Do not copy full text and students must watch and download videos',
    'Do not copy full text and students need to watch and download videos',
    'Do not copy full text and do watch and download videos',
    'Do not copy full text and viewers have to watch and download videos',
])
def test_new_instruction_does_not_inherit_an_earlier_prohibition(note):
    result = validate(note)
    assert not result['valid'], note
    assert any('Disallowed access instruction' in issue for issue in result['issues'])


@pytest.mark.parametrize('note', [
    'Do not copy full text and instead never download video content',
    'Do not bypass login; instead do not download videos',
    'Never copy full text; instead downloading videos is never permitted',
    'Do not bypass login; videos must never be downloaded',
])
def test_new_clause_can_introduce_its_own_prohibition(note):
    assert validate(note) == {'valid': True, 'issues': []}


@pytest.mark.parametrize('note', [
    'Downloading videos is never prohibited',
    'Downloading videos is not forbidden',
    'Downloading videos is permitted',
    'Downloading videos is not never permitted',
    'Downloading videos is not allowed; login needs to be bypassed',
    'Downloading videos is never permitted; download videos',
    'Download videos and bypassing login is never permitted',
    'Downloading videos is required and bypassing login is never permitted',
])
def test_negated_bans_and_unrelated_prohibitions_do_not_allow_actions(note):
    assert not validate(note)['valid'], note


@pytest.mark.parametrize('policy,note,valid', [
    ({'action': 'metadata'}, 'Videos need to be downloaded', True),
    ({'action': 'link'}, 'Download videos', True),
    ({'action': 'summarize'}, 'Do not copy full text and instead watch and download video content', True),
    ({'action': 'download_video'}, 'Downloading videos is never permitted', False),
    ({'action': 'metadata', 'bypass_login': True}, 'Never bypass login', False),
    ({'action': 'link', 'mirror': True}, 'Link only', False),
    ({'action': 'summarize', 'authorized': False}, 'Link only', False),
])
def test_structured_policy_is_authoritative_over_legacy_prose(policy, note, valid):
    result = validate(note, policy)
    assert result['valid'] is valid
    if not valid:
        assert any('Disallowed access policy' in issue for issue in result['issues'])
    assert not any('Disallowed access instruction' in issue for issue in result['issues'])


@pytest.mark.parametrize('url,note,issue', [
    ('https://sci-hub.example/paper', 'Link only', 'Disallowed source'),
    ('ftp://example.org/course', 'Link only', 'unsafe URL'),
    ('https://example.org/course', '', 'Missing access note'),
])
def test_structured_policy_preserves_independent_url_and_note_checks(url, note, issue):
    result = validate(note, {'action': 'link'}, url)
    assert not result['valid']
    assert any(issue in message for message in result['issues'])
