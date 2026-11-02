import httpx
import pytest
from qq_persona_agent.config import Settings
from qq_persona_agent.napcat_client import NapCatClient, NapCatError, RiskError


@pytest.mark.parametrize('status,hint', [(401, 'Token'), (404, '端口')])
async def test_http_errors(status, hint):
    client = NapCatClient(Settings(), httpx.MockTransport(lambda r: httpx.Response(status)))
    with pytest.raises(NapCatError, match=hint):
        await client.get_group_list()
    await client.close()


async def test_auth_cursor_and_text_segment():
    requests = []
    def handler(request):
        import json
        requests.append(json.loads(request.content))
        assert request.headers['Authorization'] == 'Bearer token'
        return httpx.Response(200, json={'status': 'ok', 'retcode': 0, 'data': {'messages': []}})
    client = NapCatClient(Settings(napcat_token='token'), httpx.MockTransport(handler))
    await client.get_group_msg_history('123456', '900', 500)
    await client.send_group_msg('123456', '[CQ:at,qq=all]')
    assert requests[0]['count'] == 200 and requests[0]['message_seq'] == '900'
    assert requests[0]['reverseOrder'] is True and requests[0]['reverse_order'] is True
    assert requests[1]['message'][0]['type'] == 'text'
    await client.close()


async def test_risk_and_no_send_retry():
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json={'status': 'failed', 'retcode': 1200, 'message': '风控'})
    client = NapCatClient(Settings(), httpx.MockTransport(handler))
    client.read_retries = 3
    with pytest.raises(RiskError):
        await client.send_group_msg('12345', 'text')
    assert count == 1
    await client.close()


async def test_connection_refused_safe_message():
    def handler(request):
        raise httpx.ConnectError('secret token here')
    client = NapCatClient(Settings(), httpx.MockTransport(handler))
    result = await client.test_connection()
    assert not result['success'] and 'secret' not in result['reason']
    await client.close()
