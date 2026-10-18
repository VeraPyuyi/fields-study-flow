import asyncio
import json
import sys

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def test_sdk_stdio_policy_obligations_prohibitions_and_boundaries():
    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'fields_study_flow.mcp_server', '--mcp'])
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                for note, policy, valid in [
                    ('Videos need to be downloaded', None, False),
                    ('Downloading videos is never permitted', None, True),
                    ('Do not copy full text and instead watch and download video content', None, False),
                    ('The video has to be downloaded', None, False),
                    ('Downloading videos and bypassing login are never allowed', None, True),
                    ('Do not copy full text and viewers have to watch and download videos', None, False),
                    ('Do not copy full text and instead never download video content', None, True),
                    ('Download videos and bypassing login is never permitted', None, False),
                    ('Videos need to be downloaded', {'action': 'metadata'}, True),
                    ('Downloading videos is never permitted', {'action': 'download_video'}, False),
                ]:
                    resource = {'title': 'public course', 'url': 'https://example.org/course',
                                'license_or_access_note': note}
                    if policy is not None:
                        resource['metadata'] = {'access_policy': policy}
                    result = await session.call_tool('validateSources', {'plan': {'phases': [{'resources': [resource]}]}})
                    assert not result.is_error, result
                    checked = json.loads(result.content[0].text)
                    assert checked['valid'] is valid, (note, policy, checked)
                    assert bool(checked['issues']) is not valid
    asyncio.run(asyncio.wait_for(run(), timeout=20))
