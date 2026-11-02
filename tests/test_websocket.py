import asyncio
import json
from dataclasses import replace
from websockets.asyncio.server import serve
from qq_persona_agent.config import Settings
from qq_persona_agent.napcat_client import NapCatClient


async def test_real_local_websocket_auth_and_event_filter():
    seen = []
    async def handler(ws):
        seen.append(ws.request.headers.get('Authorization'))
        await ws.send(json.dumps({'post_type': 'meta_event'}))
        await ws.send(json.dumps({'post_type': 'message', 'message_type': 'group', 'group_id': 12345, 'user_id': 67890, 'message': 'hello'}))
        await ws.wait_closed()
    async with serve(handler, '127.0.0.1', 0) as server:
        port = server.sockets[0].getsockname()[1]
        napcat = NapCatClient(Settings(napcat_ws=f'ws://127.0.0.1:{port}', napcat_token='ws-test-token'))
        events = napcat.events()
        event = await asyncio.wait_for(anext(events), timeout=3)
        assert event['group_id'] == 12345 and seen == ['Bearer ws-test-token']
        await events.aclose()
        await napcat.close()
