import pytest

from fields_study_flow.mcp_tools import buildRoadmap, validateSources


def validate(note):
    resource = {'title': 'public course', 'url': 'https://example.org/course',
                'license_or_access_note': note}
    return validateSources({'phases': [{'resources': [resource]}]})


@pytest.mark.parametrize('note', [
    'Download videos',
    'Download the video now',
    'DOWNLOAD VIDEOS',
    'Please download these videos',
    'Bypass login to fetch the paper',
    'Download video content and bypass login',
    'Do not copy full text; download videos',
    'Do not download video content or you may bypass login',
    'Do not download video content but bypass login',
    'Never copy full text and then download videos',
    'Do not copy full text and do download videos',
    'Do not copy full text and please download videos',
    'Do not copy full text and must download videos',
    'Do not download videos; bypass login',
    'Videos must be downloaded',
    'The video is to be downloaded now',
    'Videos must not be downloaded, but bypass login',
    'Download videos and bypassing login is prohibited',
    'Do not download videos; login must be bypassed',
    'Downloading videos is not prohibited',
    'Downloading videos is required and bypassing login is prohibited',
    'Do not refuse to download videos',
    'Do not download videos and we will bypass login',
    'No login is required to download the videos',
    'Do not copy full text, download videos',
    'Videos must not be downloaded and login must be bypassed',
    'Do not download videos or full text must be copied',
    'Do not download videos and bypassing login is required',
    'Do not download videos and students must bypass login',
    'Do not download videos and login is to be bypassed',
    'Do not copy full text, download videos and you must bypass login',
    'Downloading videos is required, copying full text and bypassing login are prohibited',
    'Do not copy full text, read the abstract and download videos',
    'Do not download video content, read the abstract and bypass login',
    'Do not download videos, use yt-dlp',
    'You are not prohibited from downloading videos',
    'Do not refuse to bypass login',
    'Do not avoid downloading videos',
    'You are not forbidden to download videos',
])
def test_affirmative_video_and_bypass_clauses_are_rejected(note):
    result = validate(note)
    assert not result['valid'], note
    assert any('Disallowed access instruction' in issue for issue in result['issues'])


@pytest.mark.parametrize('note', [
    'Do not download video content or bypass login',
    'You must not download videos',
    'Never bypass login or download videos',
    'DO NOT DOWNLOAD VIDEOS',
    'Do not download the video now',
    "Don't download videos or bypass login",
    'You should not download video content or bypass login',
    'Do not download video content and copy full text',
    'Do not bypass login to fetch the paper',
    'Videos must not be downloaded',
    'The video is not to be downloaded',
    'Downloading videos is prohibited',
    'Downloading videos or bypassing login is prohibited',
    'Download videos is prohibited',
    'Video content must never be downloaded',
    'Login must not be bypassed',
    "Don't use yt-dlp to download videos",
    'Never download videos, and never bypass login.',
    'Do not download videos. Use public paper links.',
    'We do not download video content or bypass login',
    'Downloading videos and copying full text are not allowed',
    'Do not download videos or use yt-dlp',
    'Do not copy full text from the paper or download videos',
    'You must not bypass login or download the video',
    'Do not download video content, or bypass login',
    'Never bypass login, and download videos',
    'Do not bypass login to download videos',
    'No downloading videos or bypassing login',
    'Do not bypass login, scrape restricted pages, or download videos.',
    'Never download videos, copy full text and bypass login.',
    'Downloading videos, copying full text, and bypassing login are prohibited.',
    'You are not allowed to download videos',
    'You are forbidden to download the video',
    'You are prohibited from downloading videos',
    'Avoid downloading videos or bypassing login',
    'Do not attempt to download video content or bypass login',
])
def test_prohibitions_keep_action_and_clause_scope(note):
    result = validate(note)
    assert result['valid'], result['issues']


def test_generated_plan_accepts_coordinated_safety_note():
    resource = {'title': 'public course', 'url': 'https://example.org/course',
                'source': 'course', 'type': 'course', 'estimated_time': '2h',
                'license_or_access_note': 'Do not download video content or bypass login'}
    plan = buildRoadmap('study', {}, [resource])
    assert validateSources(plan) == {'valid': True, 'issues': []}
