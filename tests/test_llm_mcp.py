import asyncio
import os
from pathlib import Path
import sys
import httpx
from openai import AsyncOpenAI
import pytest
from qq_persona_agent.config import Settings
from qq_persona_agent.llm_client import LLMClient, LLMError, LLMResponseError


@pytest.mark.parametrize('content,finish', [(' ', 'stop'), ('{"x":', 'length'), ('not json', 'stop'), ('[]', 'stop')])
async def test_llm_invalid_json_safe_logs(db, content, finish):
    def handler(request):
        return httpx.Response(200, json={'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'deepseek-chat',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': finish}],
            'usage': {'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30}})
    llm = LLMClient(Settings(api_key='not-a-real-key'), db)
    await llm.client.close()
    llm.client = AsyncOpenAI(api_key='not-a-real-key', http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(LLMError):
        await llm.complete([{'role': 'user', 'content': 'secret input'}], json_mode=True)
    record = db.one('SELECT * FROM llm_logs')
    assert not record['json_parse_ok'] and 'secret input' not in str(record)
    await llm.close()


async def test_mcp_stdio_handshake_and_call(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=['-m', 'qq_persona_agent.skill_export'],
                                   env={**os.environ, 'LOCALAPPDATA': str(tmp_path)})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            tools = (await client.list_tools()).tools
            names = {t.name for t in tools}
            assert {'export_group_member_history', 'analyze_member_persona', 'deploy_persona_agent', 'stop_agent'} <= names
            deploy = next(t for t in tools if t.name == 'deploy_persona_agent')
            assert deploy.inputSchema['properties']['dry_run']['default'] is True
            result = await client.call_tool('stop_agent', {})
            assert not result.isError
            listing = await client.call_tool('list_local_personas', {})
            assert not listing.isError


async def test_mcp_dryrun_does_not_start_runtime(db, persona):
    from types import SimpleNamespace
    from qq_persona_agent.skill_export import deploy_persona_agent
    class NeverRuntime:
        async def start(self, *args, **kwargs):
            raise AssertionError('Dry run must not start')
    svc = SimpleNamespace(db=db, runtime=NeverRuntime())
    ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=svc))
    result = await deploy_persona_agent(persona, '234567890', ctx)
    assert result['dry_run'] is True and not db.all('SELECT * FROM agents')


async def test_blank_json_retried_once_and_second_result_used(db):
    calls = []
    def handler(request):
        import json
        calls.append(json.loads(request.content))
        content = '   ' if len(calls) == 1 else '{"should_reply":false,"replies":[]}'
        return httpx.Response(200, json={'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'deepseek-chat',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 20, 'completion_tokens': 8, 'total_tokens': 28}})
    llm = LLMClient(Settings(api_key='fake'), db)
    await llm.client.close()
    llm.client = AsyncOpenAI(api_key='fake', http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await llm.complete([{'role': 'user', 'content': 'private secret json sample'}], json_mode=True)
    assert result == {'should_reply': False, 'replies': []} and len(calls) == 2
    rows = db.all('SELECT * FROM llm_logs ORDER BY id')
    assert rows[0]['error'] == 'empty_content' and rows[1]['json_parse_ok']
    assert 'private secret' not in str(rows)
    await llm.close()


@pytest.mark.parametrize('content,finish,code', [(' ', 'stop', 'empty_content'), ('{"x":', 'length', 'output_truncated'), ('plain answer', 'stop', 'invalid_json'), ('[]', 'stop', 'json_not_object')])
async def test_repeated_format_errors_have_specific_code_and_bounded_requests(db, content, finish, code):
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json={'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'deepseek-chat',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': finish}]})
    llm = LLMClient(Settings(api_key='fake'), db)
    await llm.client.close()
    llm.client = AsyncOpenAI(api_key='fake', http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(LLMResponseError) as caught:
        await llm.complete([{'role': 'user', 'content': 'json'}], json_mode=True)
    assert caught.value.code == code and count == 2
    assert all(r['error'] == code for r in db.all('SELECT error FROM llm_logs'))
    await llm.close()


async def test_complete_fenced_object_accepted(db):
    def handler(request):
        return httpx.Response(200, json={'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'deepseek-chat',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '```json\n{"ok":true}\n```'}, 'finish_reason': 'stop'}]})
    llm = LLMClient(Settings(api_key='fake'), db)
    await llm.client.close()
    llm.client = AsyncOpenAI(api_key='fake', http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await llm.complete([{'role': 'user', 'content': 'json'}], json_mode=True) == {'ok': True}
    await llm.close()


async def test_closed_generation_gate_prevents_format_retry(db):
    from qq_persona_agent.llm_client import LLMRequestSkipped
    calls=0
    def handler(request):
        nonlocal calls
        calls+=1
        return httpx.Response(200,json={'id':'test','object':'chat.completion','created':0,'model':'deepseek-chat','choices':[{'index':0,'message':{'role':'assistant','content':' '},'finish_reason':'stop'}]})
    llm=LLMClient(Settings(api_key='fake'),db)
    await llm.client.close()
    llm.client=AsyncOpenAI(api_key='fake',http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(LLMRequestSkipped):
        await llm.complete([{'role':'user','content':'json'}],json_mode=True,can_request=lambda:calls==0)
    assert calls==1
    await llm.close()
