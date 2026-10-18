import asyncio
import json
import sys

from jsonschema import Draft202012Validator
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


TOOL_NAMES = {'assessKnowledge', 'discoverSources', 'searchResources', 'ingestUrl',
              'rankResources', 'buildRoadmap', 'validateSources', 'exportPlan'}


def test_sdk_all_eight_tools_schema_calls_and_errors(tmp_path):
    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'fields_study_flow.mcp_server', '--mcp'])
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                initialized = await session.initialize()
                assert initialized.server_info.name == 'fields-study-flow'
                listing = await session.list_tools()
                assert {tool.name for tool in listing.tools} == TOOL_NAMES
                schemas = {tool.name: tool.input_schema for tool in listing.tools}
                for schema in schemas.values():
                    assert schema['type'] == 'object'
                    Draft202012Validator.check_schema(schema)

                async def call(name, arguments):
                    Draft202012Validator(schemas[name]).validate(arguments)
                    result = await session.call_tool(name, arguments)
                    assert not result.is_error, result
                    return json.loads(result.content[0].text)

                profile = await call('assessKnowledge', {'goal': 'transformer', 'confidenceLevels': {'ml_dl': 'familiar'}})
                assert profile['levels']['ml_dl'] == 'familiar'
                sources = await call('discoverSources', {'goal': 'transformer'})
                assert {'arxiv', 'github'} <= {source['id'] for source in sources['sources']}
                search = await call('searchResources', {'query': 'transformer', 'filters': {'offline': True}})
                assert search['mode'] == 'offline' and search['resources']
                imported = await call('ingestUrl', {'url': 'https://arxiv.org/abs/1706.03762'})
                assert imported['metadata']['retrieval_mode'] == 'offline'
                ranked = await call('rankResources', {'resources': search['resources'], 'learnerProfile': profile})
                assert ranked['resources'][0]['score_components']
                plan = await call('buildRoadmap', {'goal': 'transformer', 'profile': profile, 'rankedResources': ranked['resources']})
                assert plan['prerequisites']
                checked = await call('validateSources', {'plan': plan})
                assert checked['valid']
                exported = await call('exportPlan', {'plan': plan, 'outputDir': str(tmp_path)})
                assert exported['roadmap_json']
                assert json.loads((tmp_path / 'roadmap.json').read_text(encoding='utf-8')) == plan

                cycle = dict(imported, title='cycle', concepts=['self'], prerequisites=['self'])
                for name, arguments, message in [
                    ('unknown', {}, 'unknown'),
                    ('assessKnowledge', {}, 'goal'),
                    ('assessKnowledge', {'goal': 'python', 'confidenceLevels': {'programming': 'begginer'}}, 'begginer'),
                    ('buildRoadmap', {'goal': 'custom', 'profile': {}, 'rankedResources': [cycle]}, 'cycle'),
                ]:
                    result = await session.call_tool(name, arguments)
                    assert result.is_error
                    assert message in result.content[0].text.lower()

    asyncio.run(asyncio.wait_for(run(), timeout=30))
