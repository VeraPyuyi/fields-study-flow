"""Run with an installed wheel's interpreter, from a directory outside the source root."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
import fields_study_flow


def main():
    assert 'site-packages' in str(fields_study_flow.__file__), fields_study_flow.__file__
    root = Path(__file__).resolve().parents[1]
    cli = Path(sys.executable).with_name('fields-study-flow.exe')
    commands = [
        [str(cli), 'explain-paper', '--url', str(root / 'examples/paper-explainer/abstract.json'), '--json'],
        [str(cli), 'explain-paper', '--url', 'https://arxiv.org/abs/1706.03762', '--text-file', str(root / 'examples/paper-explainer/body.txt'), '--language', 'zh'],
    ]
    for index, command in enumerate(commands):
        completed = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', env={**__import__('os').environ, 'PYTHONUTF8': '1'})
        if index == 0:
            assert json.loads(completed.stdout)['mode'] == 'offline_evidence_outline'
        else:
            assert '85%' in completed.stdout and '用户提供的正文' in completed.stdout
        print(f'CLI example {index + 1}: PASS')
        Path(f'cli-example-{index + 1}.txt').write_text(completed.stdout, encoding='utf-8')
    asyncio.run(check_stdio())
    for module, flag in [('fields_study_flow.mcp_server', '--legacy-jsonl'), ('fields_study_flow.mcp_server', None), ('git4study.mcp_server', None)]:
        command = [sys.executable, '-m', module] + ([flag] if flag else [])
        completed = subprocess.run(command, input=json.dumps({'tool': 'assessKnowledge', 'arguments': {'goal': 'python'}}) + '\n', capture_output=True, text=True, check=True, timeout=20)
        assert json.loads(completed.stdout)['result']['goal'] == 'python'
    print('Legacy JSONL: 3/3 PASS')
    print('Installed package:', fields_study_flow.__file__)


async def check_stdio():
    params = StdioServerParameters(command=sys.executable, args=['-m', 'fields_study_flow.mcp_server', '--mcp'])
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 9
            calls = [
                ('assessKnowledge', {'goal': 'python'}),
                ('discoverSources', {'goal': 'python'}),
                ('searchResources', {'query': 'python', 'filters': {'offline': True}}),
                ('ingestUrl', {'url': 'https://arxiv.org/abs/1706.03762'}),
                ('rankResources', {'resources': [], 'learnerProfile': {}}),
                ('buildRoadmap', {'goal': 'python', 'profile': {}, 'rankedResources': []}),
                ('validateSources', {'plan': {}}),
                ('exportPlan', {'plan': {}, 'outputDir': str(Path('export').resolve())}),
                ('explainPaper', {'metadata': {'title': 'Demo', 'abstract': 'Our method uses attention.'}, 'language': 'en'}),
            ]
            for name, arguments in calls:
                result = await session.call_tool(name, arguments)
                assert not result.is_error, (name, result)
                payload = json.loads(result.content[0].text)
                if name == 'explainPaper':
                    assert payload['paragraphs'][1]['basis'] == ['abstract']
            print('Installed MCP stdio: 9 tools listed, 9/9 calls PASS')


if __name__ == '__main__':
    main()
