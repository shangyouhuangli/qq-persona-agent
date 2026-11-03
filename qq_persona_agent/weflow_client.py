"""Read-only WeFlow HTTP API adapter. No push subscription or send API."""
from urllib.parse import quote
import httpx


class WeFlowError(ValueError):
    pass


def valid_wx_id(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and not any(c.isspace() or ord(c) < 32 for c in value)


def weflow_key(owner, talker):
    if not valid_wx_id(owner) or not valid_wx_id(talker):
        raise WeFlowError('微信账号或会话 ID 无效')
    return 'weflow:' + quote(owner, safe='') + ':' + quote(talker, safe='')


def valid_weflow_key(value):
    from urllib.parse import unquote
    parts = str(value).split(':')
    return len(parts) == 3 and parts[0] == 'weflow' and all(valid_wx_id(unquote(p)) for p in parts[1:])


class WeFlowClient:
    def __init__(self, settings, transport=None):
        headers = {'Authorization': 'Bearer ' + settings.weflow_token} if settings.weflow_token else {}
        self.http = httpx.AsyncClient(base_url=settings.weflow_http.rstrip('/') + '/', headers=headers,
                                      timeout=settings.timeout, transport=transport, trust_env=False,
                                      proxy=settings.proxy or None, follow_redirects=False)

    async def get(self, path, **params):
        try:
            response = await self.http.get(path, params=params)
            if response.status_code in (401, 403):
                raise WeFlowError('WeFlow Token 无效或权限不足，请检查 API Token')
            if response.status_code == 404:
                raise WeFlowError('WeFlow 接口不存在，请检查地址并升级支持 HTTP API 的版本')
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException:
            raise WeFlowError('WeFlow 请求超时，请确认记录已加载或增大超时') from None
        except httpx.ConnectError:
            raise WeFlowError('无法连接 WeFlow，请启动 WeFlow 并在设置中启用 API 服务（默认端口5031）') from None
        except (httpx.HTTPError, ValueError) as e:
            if isinstance(e, WeFlowError):
                raise
            raise WeFlowError('WeFlow 返回无效响应，请检查服务、数据库加载状态和版本') from None
        if not isinstance(body, dict) or body.get('success') is False:
            raise WeFlowError('WeFlow 读取失败，请在 WeFlow 中确认数据库和账号正常；未记录响应正文')
        return body

    async def sessions(self, keyword=''):
        data = await self.get('api/v1/sessions', keyword=keyword, limit=1000)
        rows = data.get('sessions')
        if not isinstance(rows, list) or any(not isinstance(r, dict) or not valid_wx_id(r.get('username')) for r in rows):
            raise WeFlowError('WeFlow 会话列表格式错误')
        return rows

    async def members(self, talker):
        data = await self.get('api/v1/group-members', chatroomId=talker)
        rows = data.get('members')
        if not isinstance(rows, list):
            raise WeFlowError('WeFlow 群成员列表格式错误')
        return rows

    async def metadata(self, talker):
        data = await self.get('api/v1/messages', talker=talker, limit=1, format='chatlab', media=0)
        meta = data.get('meta', {})
        owner = meta.get('ownerId') if isinstance(meta, dict) else None
        if not valid_wx_id(owner):
            raise WeFlowError('WeFlow 未返回当前账号 ownerId，请确认已加载微信数据库并升级 WeFlow')
        return data

    async def page(self, talker, start, end, offset, limit=200):
        data = await self.get('api/v1/messages', talker=talker, start=str(start), end=str(end),
                              offset=offset, limit=limit, media=0)
        if data.get('talker') != talker or not isinstance(data.get('messages'), list) or type(data.get('hasMore')) is not bool:
            raise WeFlowError('WeFlow 消息/分页字段不完整，无法保证正确导出')
        return data

    async def test_connection(self):
        try:
            # An authenticated endpoint, not just the unauthenticated health check.
            await self.sessions()
            return {'success': True, 'reason': 'WeFlow API 已连接，Token 校验通过；可检索微信会话'}
        except WeFlowError as e:
            return {'success': False, 'reason': str(e)}

    async def close(self):
        await self.http.aclose()
