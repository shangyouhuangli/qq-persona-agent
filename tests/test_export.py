import threading
import pytest
from qq_persona_agent.chat_exporter import ChatExporter, clean_message
from qq_persona_agent.models import ExportRequest
from conftest import message


REQUEST = ExportRequest('234567890', '123456789', 10, 100, 10)


class Pages:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.cursors = []

    async def get_group_msg_history(self, gid, cursor=None, count=100):
        self.cursors.append(cursor)
        item = next(self.pages, [])
        if isinstance(item, Exception):
            raise item
        return item


def test_cq_and_array_cleaning():
    m = message(1, 20)
    m['message'] = '你好[CQ:at,qq=123456789][CQ:image,file=x][CQ:record,file=y][CQ:face,id=1]&amp;'
    clean = clean_message(m)
    assert clean['text'] == '你好&'
    assert all(clean[k] == 1 for k in ('has_at', 'has_face', 'has_image', 'has_voice'))


async def test_overlap_filter_and_encrypted_jsonl(db, tmp_path):
    pages = Pages([[message(5, 90), message(4, 80), message(3, 70, sender='888888')], [message(4, 80), message(2, 20), message(1, 5)]])
    exporter = ChatExporter(db, pages)
    result = await exporter.export(REQUEST)
    assert result['count'] == 3 and result['low_sample']
    assert pages.cursors == [None, '3']
    path = tmp_path / 'output.enc'
    exporter.save_encrypted_jsonl(result['batch_id'], path)
    assert 'unique secret chat' not in path.read_text()
    assert 'unique secret chat' in db.crypto.decrypt(path.read_text())
    for p in db.path.parent.glob('test.db*'):
        assert b'unique secret chat' not in p.read_bytes()


async def test_resume_after_failure_and_request_match(db):
    exporter = ChatExporter(db, Pages([[message(5, 90), message(4, 80)], RuntimeError('network')]))
    with pytest.raises(RuntimeError):
        await exporter.export(REQUEST)
    batch = db.one('SELECT * FROM export_batches')
    assert batch['status'] == 'interrupted' and batch['cursor'] == '4'
    exporter.napcat = Pages([[message(4, 80), message(2, 20)], []])
    result = await exporter.export(REQUEST, batch['id'])
    assert result['count'] == 3 and exporter.napcat.cursors[0] == '4'
    with pytest.raises(ValueError):
        await exporter.export(ExportRequest('11111', '123456789', 10, 100), batch['id'])


async def test_stalled_cursor_and_limit(db):
    page = [message(5, 90), message(4, 80)]
    exporter = ChatExporter(db, Pages([page, page]))
    result = await exporter.export(REQUEST)
    assert result['status'] == 'partial' and result['count'] == 2
    exporter.napcat = Pages([page])
    result = await exporter.export(ExportRequest('234567890', '123456789', 10, 100, 1))
    assert result['count'] == 1


async def test_preview_does_not_persist(db):
    exporter = ChatExporter(db, Pages([[message(5, 90)], []]))
    assert len(await exporter.preview(REQUEST)) == 1
    assert not db.all('SELECT * FROM exported_messages')


class NapCatHistory:
    """Protocol model: native short IDs differ from group message sequences."""
    def __init__(self):
        self.rows = [message(-1000 - i, 20 + i, seq=500 + i) for i in range(12)]
        self.cursors = []

    async def get_group_msg_history(self, gid, cursor=None, count=100):
        self.cursors.append(cursor)
        if cursor is None:
            return self.rows[-4:]
        ids = [str(r['message_id']) for r in self.rows]
        if cursor not in ids:
            return self.rows[-4:]  # Wrong anchor reproduces the reported failure.
        index = ids.index(cursor)
        return self.rows[max(0, index - 3):index + 1] if index else []


async def test_distinct_short_id_and_group_sequence_paginate(db):
    nap = NapCatHistory()
    exporter = ChatExporter(db, nap)
    request = ExportRequest('234567890', '123456789', 10, 100, 100)
    result = await exporter.export(request)
    assert result['count'] == 12 and result['status'] == 'complete'
    assert nap.cursors[1] == '-1008'
    assert len(db.messages(result['batch_id'])) == 12


async def test_preview_crosses_pages_with_distinct_ids(db):
    nap = NapCatHistory()
    rows = await ChatExporter(db, nap).preview(ExportRequest('234567890', '123456789', 10, 100, 100))
    assert len(rows) == 12
    assert nap.cursors[1] == '-1008'


async def test_resume_legacy_stalled_batch_restarts_and_deduplicates(db):
    exporter = ChatExporter(db, Pages([[message(5, 90), message(4, 80)]] * 2))
    result = await exporter.export(REQUEST)
    assert result['status'] == 'partial'
    exporter.napcat = Pages([[message(5, 90), message(4, 80)], [message(4, 80), message(2, 20)], []])
    resumed = await exporter.export(REQUEST, result['batch_id'])
    assert exporter.napcat.cursors[0] is None
    assert resumed['count'] == 3 and resumed['status'] == 'complete'
