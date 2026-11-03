"""Offline checks for the packaged dependency graph; no real credentials or network."""
import httpx
from openai import AsyncOpenAI
from .config import Settings


async def check_services(services):
    settings = Settings(api_key='smoke-secret-not-real', napcat_token='test-token-not-real', weflow_token='weflow-test-not-real')
    await services.configure(settings)
    assert services.store.load().api_key == settings.api_key
    assert services.store.load().weflow_token == settings.weflow_token
    def weflow_handler(request):
        assert request.headers['Authorization'] == 'Bearer weflow-test-not-real'
        return httpx.Response(200, json={'success': True, 'sessions': []})
    await services.weflow.http.aclose()
    services.weflow.http = httpx.AsyncClient(base_url=settings.weflow_http, transport=httpx.MockTransport(weflow_handler),
                                            headers={'Authorization': 'Bearer weflow-test-not-real'})
    assert (await services.weflow.test_connection())['success']
    def napcat_handler(request):
        assert request.headers['Authorization'] == 'Bearer test-token-not-real'
        payload = {'get_login_info': {'user_id': 123456789}, 'get_group_list': [{'group_id': 234567890}], 'get_group_member_list': [{'user_id': 345678901}]}
        return httpx.Response(200, json={'status': 'ok', 'retcode': 0, 'data': payload[request.url.path.rsplit('/', 1)[-1]]})
    await services.napcat.http.aclose()
    services.napcat.http = httpx.AsyncClient(base_url=settings.napcat_http, headers=services.napcat.headers,
                                           transport=httpx.MockTransport(napcat_handler))
    assert (await services.napcat.test_connection())['success']
    assert len(await services.napcat.get_group_list()) == 1
    assert len(await services.napcat.get_group_member_list('234567890')) == 1
    def llm_handler(request):
        return httpx.Response(200, json={'id': 'selftest', 'object': 'chat.completion', 'created': 0, 'model': 'deepseek-chat',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '{"ok":true}'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})
    await services.llm.client.close()
    services.llm.client = AsyncOpenAI(api_key=settings.api_key, http_client=httpx.AsyncClient(transport=httpx.MockTransport(llm_handler)))
    assert (await services.llm.test_connection())['success']
    assert services.db.one('SELECT json_parse_ok FROM llm_logs')['json_parse_ok']
    return {'summary': '离线 NapCat/DeepSeek/WeFlow 连接路径自检通过（Mock，不代表真实服务联调）'}
