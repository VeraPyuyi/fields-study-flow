import asyncio
import json
import subprocess
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


import pytest


@pytest.mark.parametrize('config_path', ['.cursor/mcp.json', '.vscode/mcp.json'])
def test_sdk_stdio_round_trip(config_path):
    async def run():
        config = json.loads(Path(config_path).read_text())
        server = config.get('mcpServers', config.get('servers'))['fields-study-flow']
        params = StdioServerParameters(command=sys.executable, args=server['args'])
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                initialized = await session.initialize()
                assert initialized.server_info.name == 'fields-study-flow'
                tools = await session.list_tools()
                assert len(tools.tools) == 9
                explained = await session.call_tool('explainPaper', {'metadata': {'title': 'Offline paper', 'abstract': 'Our method uses attention.'}, 'language': 'en'})
                assert not explained.is_error
                assert 'offline_evidence_outline' in explained.content[0].text
                assert all(t.input_schema.get('type') == 'object' for t in tools.tools)
                result = await session.call_tool('buildRoadmap', {'goal': 'transformer', 'profile': {}, 'rankedResources': []})
                assert not result.is_error
                assert 'phases' in result.content[0].text
                for name, args in [('unknown', {}), ('assessKnowledge', {})]:
                    bad = await session.call_tool(name, args)
                    assert bad.is_error
    asyncio.run(asyncio.wait_for(run(), timeout=20))


def test_legacy_jsonl_is_explicit_and_compatible():
    for module, flag in [('fields_study_flow.mcp_server', '--legacy-jsonl'), ('fields_study_flow.mcp_server', None), ('git4study.mcp_server', None)]:
        args = [sys.executable, '-m', module] + ([flag] if flag else [])
        result = subprocess.run(args, input=json.dumps({'tool': 'assessKnowledge', 'arguments': {'goal': 'python'}})+'\n', text=True, capture_output=True, timeout=15)
        assert result.returncode == 0
        assert json.loads(result.stdout)['result']['goal'] == 'python'


def test_editor_configs_select_mcp():
    for directory in ('.cursor', '.vscode'):
        config = json.loads((Path(directory) / 'mcp.json').read_text())
        servers = config.get('mcpServers', config.get('servers'))
        server = servers['fields-study-flow']
        assert server['args'] == ['-m', 'fields_study_flow.mcp_server', '--mcp']
