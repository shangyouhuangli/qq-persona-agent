from __future__ import annotations
import asyncio
import json
import httpx
from websockets.asyncio.client import connect
from .logging_utils import log


class NapCatError(RuntimeError):
    pass


class RiskError(NapCatError):
    pass


class NapCatClient:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.read_retries = 0
        self.headers = {'Authorization': f'Bearer {settings.napcat_token}'} if settings.napcat_token else {}
        self.http = httpx.AsyncClient(base_url=settings.napcat_http.rstrip('/') + '/', headers=self.headers,
                                      timeout=settings.timeout, proxy=settings.proxy or None,
                                      transport=transport, trust_env=False)

    async def action(self, name, **params):
        for attempt in range(self.read_retries + 1 if name.startswith('get_') else 1):
            try:
                return await self._action(name, **params)
            except RiskError:
                raise
            except NapCatError as e:
                if attempt >= self.read_retries or not name.startswith('get_') or not any(w in str(e) for w in ('超时', '无法连接')):
                    raise
                await asyncio.sleep(min(2 ** attempt, 5))

    async def _action(self, name, **params):
        try:
            response = await self.http.post(name, json=params)
            if response.status_code == 401:
                raise NapCatError('NapCat Token 错误（401），请检查访问令牌')
            if response.status_code == 404:
                raise NapCatError('NapCat 路径或端口错误（404），确认已启用 HTTP 服务')
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException:
            raise NapCatError('NapCat 请求超时，请检查连接或增大超时') from None
        except httpx.ConnectError:
            raise NapCatError('无法连接 NapCat，请启动 HTTP 服务并检查端口/代理') from None
        except (httpx.HTTPError, ValueError):
            raise NapCatError('NapCat 返回无效响应，请检查服务地址与日志') from None
        if not isinstance(body, dict):
            raise NapCatError('NapCat 响应格式错误')
        if body.get('status') != 'ok' or body.get('retcode', 0) != 0:
            hint = str(body.get('message', '')) + str(body.get('wording', ''))
            if any(w in hint.lower() for w in ('风控', 'risk', '禁言', '频繁', '限制')):
                raise RiskError('NapCat 返回风控/禁言/频率限制，请人工检查 QQ 状态')
            raise NapCatError('NapCat 操作失败，请检查机器人权限和服务端日志（未记录响应正文）')
        return body.get('data')

    async def test_connection(self):
        try:
            info = await self.action('get_login_info')
            return {'success': True, 'reason': 'NapCat HTTP 已连接', 'self_id': str(info['user_id'])}
        except NapCatError as e:
            return {'success': False, 'reason': str(e)}

    async def get_group_list(self):
        return await self.action('get_group_list')

    async def get_group_member_list(self, group_id):
        return await self.action('get_group_member_list', group_id=int(group_id))

    async def get_group_msg_history(self, group_id, message_seq=None, count=100):
        # NapCat resolves message_seq through its short message-ID map. Despite
        # the parameter name, callers should prefer the returned message_id.
        # Both spellings are supported by current NapCat; true requests history.
        params = {'group_id': int(group_id), 'count': min(200, max(1, count)),
                  'reverseOrder': True, 'reverse_order': True}
        if message_seq is not None:
            params['message_seq'] = str(message_seq)
        data = await self.action('get_group_msg_history', **params)
        return data.get('messages', []) if isinstance(data, dict) else []

    async def send_group_msg(self, group_id, text):
        # Text segment prevents CQ injection through generated/edited text.
        return await self.action('send_group_msg', group_id=int(group_id), message=[{'type': 'text', 'data': {'text': text}}])

    async def events(self):
        # No automatic reconnect after an uncertain send/session failure.
        try:
            async with connect(self.settings.napcat_ws, additional_headers=self.headers,
                               open_timeout=self.settings.timeout, ping_timeout=self.settings.timeout,
                               max_size=2**20, proxy=self.settings.proxy or None) as ws:
                async for data in ws:
                    try:
                        event = json.loads(data)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(event, dict) and event.get('post_type') == 'message' and event.get('message_type') == 'group':
                        yield event
        except asyncio.CancelledError:
            raise
        except Exception:
            raise NapCatError('WebSocket 连接中断，请检查地址、Token、代理并重新启用') from None

    async def close(self):
        await self.http.aclose()
