from __future__ import annotations
import asyncio
from dataclasses import asdict, replace
import html
import json
import re
import uuid
from .db import now
from .models import ExportRequest
from .logging_utils import log
from .conversations import history


def segments_of(message):
    if isinstance(message, list):
        return [s for s in message if isinstance(s, dict)]
    text = str(message or '')
    result, offset = [], 0
    for match in re.finditer(r'\[CQ:([^,\]]+)((?:,[^\]]*)?)\]', text):
        if match.start() > offset:
            result.append({'type': 'text', 'data': {'text': html.unescape(text[offset:match.start()])}})
        data = dict(part.split('=', 1) for part in match[2].lstrip(',').split(',') if '=' in part)
        result.append({'type': match[1], 'data': data})
        offset = match.end()
    if offset < len(text):
        result.append({'type': 'text', 'data': {'text': html.unescape(text[offset:])}})
    return result


def clean_message(m):
    segments = segments_of(m.get('message', m.get('raw_message', '')))
    kinds = {s.get('type') for s in segments}
    sender = m.get('sender') or {}
    return {'timestamp': int(m.get('time', 0)), 'message_id': str(m.get('message_id', '')),
            'sender_id': str(m.get('user_id', sender.get('user_id', ''))),
            'sender_nickname': str(sender.get('card') or sender.get('nickname') or ''),
            'text': ''.join(str(s.get('data', {}).get('text', '')) for s in segments if s.get('type') == 'text').strip(),
            'raw_segments': segments, 'has_image': int('image' in kinds), 'has_voice': int('record' in kinds),
            'has_face': int('face' in kinds or 'mface' in kinds), 'has_at': int('at' in kinds)}


class ChatExporter:
    def __init__(self, db, napcat):
        self.db, self.napcat = db, napcat

    async def resolve_request(self, request):
        request.validate()
        if request.sender_scope == 'self':
            info = await self.napcat.action('get_login_info')
            own_id = str(info.get('user_id', '')) if isinstance(info, dict) else ''
            if not own_id.isdigit() or int(own_id) <= 0:
                raise ValueError('无法获取 NapCat 当前登录 QQ，不能确定自己的消息')
            request = replace(request, user_id=own_id)
        return request

    async def preview(self, request):
        request = await self.resolve_request(request)
        result, cursor, seen = [], None, set()
        for _ in range(200):
            page = await history(self.napcat, request.group_id, cursor)
            if not page:
                break
            rows = [clean_message(m) for m in page]
            for r in sorted(rows, key=lambda r: r['timestamp'], reverse=True):
                if r['message_id'] not in seen and r['sender_id'] == request.user_id and request.start_time <= r['timestamp'] <= request.end_time:
                    result.append(r)
                    seen.add(r['message_id'])
            if len(result) >= 20 or min(r['timestamp'] for r in rows) < request.start_time:
                break
            new_cursor = self.cursor(page)
            if new_cursor is None or new_cursor == cursor:
                break
            cursor = new_cursor
            await asyncio.sleep(0)
        return result[:20]

    @staticmethod
    def cursor(page):
        def seq(m):
            try:
                return int(m.get('message_seq') or 0)
            except (ValueError, TypeError):
                return 0
        earliest = min(page, key=lambda m: (int(m.get('time', 0)), seq(m)))
        # message_seq in an OB11 response may be the group sequence, whereas
        # NapCat's history action resolves the short message_id to a native ID.
        # Never subtract from either ID: they are not interchangeable counters.
        for key in ('message_id', 'message_seq'):
            value = earliest.get(key)
            if value is not None and str(value).strip() not in ('', '0'):
                return str(value)
        return None

    async def export(self, request: ExportRequest, batch_id=None, progress=None, cancel=None):
        request = await self.resolve_request(request)
        request_json = json.dumps(asdict(request), sort_keys=True)
        if batch_id:
            batch = self.db.one('SELECT * FROM export_batches WHERE id=?', (batch_id,))
            if not batch or ExportRequest(**json.loads(self.db.unpack(batch['request_json']))) != request:
                raise ValueError('断点批次不存在或请求参数不匹配')
            if batch['status'] == 'complete':
                return self.result(batch_id)
            cursor, scanned = batch['cursor'], batch['scanned']
            if batch['reason'] in ('cursor_stalled_check_napcat_version', 'napcat_4_7_5_history_direction_bug'):
                # Old versions persisted an ambiguous group sequence. Restart
                # traversal with the fixed protocol; the batch relation dedups.
                cursor = None
        else:
            batch_id, cursor, scanned = uuid.uuid4().hex, None, 0
            self.db.execute('INSERT INTO export_batches(id,request_json,updated_at) VALUES(?,?,?)', (batch_id, self.db.pack(request_json), now()))
        count = len(self.db.messages(batch_id))
        status, reason = 'complete', 'history_exhausted'
        seen_cursors = {cursor}
        try:
            while count < request.max_messages:
                if cancel and cancel.is_set():
                    status, reason = 'interrupted', 'cancelled'
                    break
                page = await history(self.napcat, request.group_id, cursor)
                if not page:
                    break
                rows = [clean_message(m) for m in page]
                scanned += len(page)
                next_cursor = self.cursor(page)
                with self.db.transaction() as conn:
                    for r in sorted(rows, key=lambda r: r['timestamp'], reverse=True):
                        if count >= request.max_messages:
                            break
                        if not r['message_id'] or r['sender_id'] != request.user_id or not request.start_time <= r['timestamp'] <= request.end_time:
                            continue
                        conn.execute('INSERT OR IGNORE INTO exported_messages(group_id,message_id,sender_id,sender_nickname,timestamp,text,raw_segments_json,has_image,has_voice,has_face,has_at,export_batch_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                                     (request.group_id, r['message_id'], r['sender_id'], self.db.pack(r['sender_nickname']), r['timestamp'], self.db.pack(r['text']), self.db.pack(r['raw_segments']), r['has_image'], r['has_voice'], r['has_face'], r['has_at'], batch_id))
                        pk = conn.execute('SELECT id FROM exported_messages WHERE group_id=? AND message_id=?', (request.group_id, r['message_id'])).fetchone()[0]
                        inserted = conn.execute('INSERT OR IGNORE INTO batch_messages VALUES(?,?)', (batch_id, pk)).rowcount
                        count += inserted
                    conn.execute('UPDATE export_batches SET cursor=?,scanned=?,updated_at=? WHERE id=?', (next_cursor, scanned, now(), batch_id))
                if progress:
                    progress({'batch_id': batch_id, 'count': count, 'scanned': scanned, 'maximum': request.max_messages})
                if min(r['timestamp'] for r in rows) < request.start_time:
                    reason = 'time_range_covered'
                    break
                if count >= request.max_messages:
                    reason = 'limit_reached'
                    break
                if next_cursor is None or next_cursor in seen_cursors:
                    status, reason = 'partial', 'cursor_stalled_check_napcat_version'
                    if hasattr(self.napcat, 'action'):
                        try:
                            version = await self.napcat.action('get_version_info')
                            if isinstance(version, dict) and version.get('app_version') == '4.7.5':
                                reason = 'napcat_4_7_5_history_direction_bug'
                        except Exception:
                            pass
                    break
                seen_cursors.add(next_cursor)
                cursor = next_cursor
                await asyncio.sleep(0.05)
        except BaseException:
            self.db.execute("UPDATE export_batches SET status='interrupted',reason='network_or_cancel',updated_at=? WHERE id=?", (now(), batch_id))
            raise
        self.db.execute('UPDATE export_batches SET status=?,reason=?,updated_at=? WHERE id=?', (status, reason, now(), batch_id))
        log.emit('export', '历史记录导出结束', count=count, status=status)
        return self.result(batch_id)

    def result(self, batch_id):
        batch = self.db.one('SELECT * FROM export_batches WHERE id=?', (batch_id,))
        rows = self.db.messages(batch_id)
        valid = sum(bool(r['text']) for r in rows)
        return {'batch_id': batch_id, 'count': len(rows), 'valid_text_count': valid, 'low_sample': valid < 100,
                'status': batch['status'], 'reason': batch['reason'],
                'reason_detail': {'cursor_stalled_check_napcat_version': 'NapCat 未返回更早的消息，历史读取不完整；请确认 NapCat 版本及该账号是否能查看更早记录',
                                  'napcat_4_7_5_history_direction_bug': '检测到 NapCat 4.7.5 历史分页方向缺陷；请升级 NapCat 或使用修复脚本，重启 NapCat 后恢复导出（已有数据保留）',
                                  'history_exhausted': 'NapCat 本次未返回更多历史', 'time_range_covered': '已覆盖起始时间',
                                  'limit_reached': '已达到设置的成员消息条数上限', 'cancelled': '已取消，可恢复'}.get(batch['reason'], batch['reason']),
                'scanned': batch['scanned'], 'summary': f'导出 {len(rows)} 条，有效文本 {valid} 条'}

    def save_encrypted_jsonl(self, batch_id, path):
        rows = self.db.messages(batch_id)
        text = '\n'.join(json.dumps({'conversation_key': r['group_id'], 'timestamp': r['timestamp'], 'message_id': r['message_id'], 'sender_id': r['sender_id'], 'sender_nickname': r['sender_nickname'], 'text': r['text'], 'raw_segments': r['raw_segments_json']}, ensure_ascii=False) for r in rows)
        path.write_text(self.db.crypto.encrypt(text), encoding='ascii')
