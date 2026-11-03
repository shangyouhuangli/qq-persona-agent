"""WeFlow offset pagination with fixed time bounds, account guard and encrypted batches."""
import asyncio
from dataclasses import asdict, dataclass
import hashlib
import json
import uuid
from .chat_exporter import ChatExporter
from .db import now
from .logging_utils import log
from .weflow_client import WeFlowError, valid_wx_id, weflow_key


@dataclass(frozen=True)
class WeFlowExportRequest:
    talker: str
    user_id: str  # '__self__' resolves against meta.ownerId, never guessed from messages.
    start_time: int
    end_time: int
    max_messages: int = 1000
    source: str = 'weflow'

    def validate(self):
        if self.source != 'weflow' or not valid_wx_id(self.talker) or not valid_wx_id(self.user_id):
            raise WeFlowError('请选择微信会话和发送者')
        if self.talker.endswith('@chatroom') and self.user_id == self.talker:
            raise WeFlowError('微信群需要选择具体成员')
        if self.start_time < 0 or self.end_time < self.start_time or not 1 <= self.max_messages <= 100000:
            raise WeFlowError('微信导出时间或条数范围无效')


class WeFlowExporter(ChatExporter):
    async def identity(self, request):
        request.validate()
        data = await self.napcat.metadata(request.talker)
        owner = data['meta']['ownerId']
        return owner, owner if request.user_id == '__self__' else request.user_id, data

    async def names(self, request, data):
        names = {r['platformId']: r.get('accountName') or r['platformId'] for r in data.get('members', [])}
        if request.talker.endswith('@chatroom'):
            for member in await self.napcat.members(request.talker):
                uid = member.get('accountId') or member.get('wxid')
                if uid:
                    names[uid] = member.get('groupNickname') or member.get('displayName') or member.get('nickname') or uid
        return names

    @staticmethod
    def clean(raw, owner, talker, names):
        sender = raw.get('senderUsername')
        flag = raw.get('isSend')
        if flag in (1, True, '1'):
            sender = owner
        elif flag in (0, False, '0') and not sender and not talker.endswith('@chatroom'):
            sender = talker
        if not valid_wx_id(sender):
            # System rows in group history may have no sender; never attribute them.
            sender = ''
        mid = raw.get('serverId')
        if mid in (None, '', 0, '0'):
            mid = raw.get('localId')
            mid = 'local:' + str(mid) if mid is not None else ''
        kind = raw.get('localType')
        # Only native text is used. Quotes, forwards and media can contain others' words.
        text = raw.get('content', '') if str(kind) == '1' else ''
        return {'message_id': str(mid), 'sender_id': sender, 'sender_nickname': names.get(sender, sender),
                'timestamp': int(raw.get('createTime', 0)), 'text': text if isinstance(text, str) else '',
                'raw_segments': [raw], 'has_image': int(str(kind) == '3'), 'has_voice': int(str(kind) == '34'),
                'has_face': int(str(kind) == '47'), 'has_at': 0}

    async def preview(self, request):
        owner, sender, data = await self.identity(request)
        names = await self.names(request, data)
        return (await self.collect(request, owner, sender, names, preview=True))[:20]

    async def export(self, request, batch_id=None, progress=None, cancel=None):
        owner, sender, data = await self.identity(request)
        names = await self.names(request, data)
        return await self.collect(request, owner, sender, names, batch_id=batch_id, progress=progress, cancel=cancel)

    async def collect(self, request, owner, sender, names, preview=False, batch_id=None, progress=None, cancel=None):
        spec = {**asdict(request), 'owner_id': owner}
        offset, scanned, previous = 0, 0, None
        key = weflow_key(owner, request.talker)
        if not preview:
            if batch_id:
                batch = self.db.one('SELECT * FROM export_batches WHERE id=?', (batch_id,))
                if not batch or json.loads(self.db.unpack(batch['request_json'])) != spec:
                    raise WeFlowError('微信断点参数或当前账号已改变，请创建新导出批次')
                if batch['status'] == 'complete':
                    return self.result(batch_id)
                cursor = json.loads(batch['cursor']) if batch['cursor'] else {}
                offset, scanned, previous = cursor.get('offset', 0), batch['scanned'], cursor.get('fingerprint')
            else:
                batch_id = uuid.uuid4().hex
                self.db.execute('INSERT INTO export_batches(id,request_json,updated_at) VALUES(?,?,?)',
                                (batch_id, self.db.pack(json.dumps(spec, sort_keys=True)), now()))
        rows_out, seen = [], set()
        seen_pages = {previous} if previous else set()
        count = len(self.db.messages(batch_id)) if not preview else 0
        maximum = min(20, request.max_messages) if preview else request.max_messages
        status, reason = 'complete', 'history_exhausted'
        try:
            while count < maximum:
                if cancel and cancel.is_set():
                    status, reason = 'interrupted', 'cancelled'
                    break
                page = await self.napcat.page(request.talker, request.start_time, request.end_time, offset)
                current = await self.napcat.metadata(request.talker)
                if current['meta']['ownerId'] != owner:
                    raise WeFlowError('WeFlow 数据库账号在读取期间改变，已中止；请重新检索并创建批次')
                raw_rows = page['messages']
                if not raw_rows:
                    if page['hasMore']:
                        status, reason = 'partial', 'weflow_pagination_stalled'
                    break
                rows = [self.clean(r, owner, request.talker, names) for r in raw_rows]
                fingerprint = hashlib.sha256(json.dumps([r['message_id'] for r in rows]).encode()).hexdigest()
                if fingerprint in seen_pages:
                    status, reason = 'partial', 'weflow_pagination_stalled'
                    break
                scanned += len(rows)
                seen_pages.add(fingerprint)
                matches = [r for r in rows if r['sender_id'] == sender and request.start_time <= r['timestamp'] <= request.end_time]
                if any(not r['message_id'] for r in matches):
                    raise WeFlowError('所选发送者的微信消息缺少消息 ID，无法安全去重/续传')
                if preview:
                    for r in matches:
                        if r['message_id'] not in seen and count < maximum:
                            seen.add(r['message_id']); rows_out.append(r); count += 1
                else:
                    with self.db.transaction() as conn:
                        for r in matches:
                            if count >= maximum:
                                break
                            conn.execute('INSERT OR IGNORE INTO exported_messages(group_id,message_id,sender_id,sender_nickname,timestamp,text,raw_segments_json,has_image,has_voice,has_face,has_at,export_batch_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                                         (key, r['message_id'], sender, self.db.pack(r['sender_nickname']), r['timestamp'], self.db.pack(r['text']), self.db.pack(r['raw_segments']), r['has_image'], r['has_voice'], r['has_face'], 0, batch_id))
                            pk = conn.execute('SELECT id FROM exported_messages WHERE group_id=? AND message_id=?', (key, r['message_id'])).fetchone()[0]
                            count += conn.execute('INSERT OR IGNORE INTO batch_messages VALUES(?,?)', (batch_id, pk)).rowcount
                        conn.execute('UPDATE export_batches SET cursor=?,scanned=?,updated_at=? WHERE id=?',
                                     (json.dumps({'offset': offset + len(rows), 'fingerprint': fingerprint}), scanned, now(), batch_id))
                if progress:
                    progress({'batch_id': batch_id, 'count': count, 'scanned': scanned, 'maximum': maximum})
                if count >= maximum:
                    reason = 'limit_reached'
                    break
                if not page['hasMore']:
                    break
                offset += len(rows)
                previous = fingerprint
                await asyncio.sleep(0)
        except BaseException:
            if not preview:
                self.db.execute("UPDATE export_batches SET status='interrupted',reason='network_or_cancel',updated_at=? WHERE id=?", (now(), batch_id))
            raise
        if preview:
            if status == 'partial':
                raise WeFlowError('WeFlow 分页重复或为空，预览不完整，请检查版本和数据库')
            return rows_out
        self.db.execute('UPDATE export_batches SET status=?,reason=?,updated_at=? WHERE id=?', (status, reason, now(), batch_id))
        log.emit('export', '微信记录导出结束', count=count, status=status)
        result = self.result(batch_id)
        if reason == 'weflow_pagination_stalled':
            result['reason_detail'] = 'WeFlow 分页未推进，历史读取不完整；请检查版本与数据库'
        return result
