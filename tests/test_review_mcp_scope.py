import asyncio
import json
import sys

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def test_sdk_stdio_access_action_scope():
    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'fields_study_flow.mcp_server', '--mcp'])
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                for note, valid in [
                    ('Download videos', False),
                    ('Download the video now', False),
                    ('Do not download video content or bypass login', True),
                    ('You must not download videos', True),
                    ('Bypass login to fetch the paper', False),
                    ('Never bypass login or download videos', True),
                    ('Videos must not be downloaded and login must be bypassed', False),
                    ('Do not bypass login, scrape restricted pages, or download videos.', True),
                ]:
                    resource = {'title': 'course', 'url': 'https://example.org/course',
                                'license_or_access_note': note}
                    result = await session.call_tool('validateSources', {'plan': {'phases': [{'resources': [resource]}]}})
                    assert not result.is_error, result
                    assert json.loads(result.content[0].text)['valid'] is valid, note
    asyncio.run(asyncio.wait_for(run(), timeout=20))


def test_sdk_stdio_planned_prerequisite_coverage():
    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'fields_study_flow.mcp_server', '--mcp'])
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                resource = {'title': 'advanced-python', 'url': 'https://example.org/python',
                            'source': 'course', 'type': 'course', 'difficulty': 'advanced',
                            'concepts': ['python'], 'prerequisites': ['python'], 'estimated_time': '2h',
                            'license_or_access_note': 'Do not download video content or bypass login'}
                arguments = {'goal': 'Python', 'profile': {'weekly_hours': 2}, 'rankedResources': [resource]}
                result = await session.call_tool('buildRoadmap', arguments)
                assert not result.is_error, result
                plan = json.loads(result.content[0].text)
                assert [(item['id'], item['hours'], item['start_week']) for item in plan['schedule']['items']] == [
                    ('python', 6, 1), ('https://example.org/python', 2, 4),
                ]
                checked = await session.call_tool('validateSources', {'plan': plan})
                assert not checked.is_error
                assert json.loads(checked.content[0].text) == {'valid': True, 'issues': []}

                for concepts, dependencies, error in [
                    (['uncovered'], ['uncovered'], 'cycle'),
                    (['python'], ['missing-basics'], 'unknown prerequisite'),
                ]:
                    invalid = dict(resource, concepts=concepts, prerequisites=dependencies)
                    result = await session.call_tool('buildRoadmap', dict(arguments, rankedResources=[invalid]))
                    assert result.is_error
                    assert error in result.content[0].text.lower()
                    assert 'advanced-python' in result.content[0].text
    asyncio.run(asyncio.wait_for(run(), timeout=20))
