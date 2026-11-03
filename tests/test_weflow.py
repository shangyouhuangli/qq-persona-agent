import asyncio
import json
import os
import threading
from dataclasses import asdict
from types import SimpleNamespace
import httpx
import pytest
from qq_persona_agent.config import Settings, Tuning
from qq_persona_agent.weflow_client import WeFlowClient, WeFlowError
from qq_persona_agent.weflow_exporter import WeFlowExporter, WeFlowExportRequest
from qq_persona_agent.persona_analyzer import PersonaAnalyzer
from test_persona import FakeLLM


def wx(mid, sender='wxid_peer', own=0, text='微信秘密原文', kind=1, time=20):
    return {'serverId': str(mid), 'localId': mid, 'senderUsername': sender, 'isSend': own,
            'localType': kind, 'createTime': time, 'content': text}


class API:
    def __init__(self, pages):
        self.pages, self.offsets, self.owner = iter(pages), [], 'wxid_me'

    async def metadata(self, talker):
        return {'meta': {'ownerId': self.owner}, 'members': [
            {'platformId': 'wxid_me', 'accountName': '我'}, {'platformId': 'wxid_peer', 'accountName': '朋友'}]}

    async def page(self, talker, start, end, offset):
        self.offsets.append(offset)
        item = next(self.pages, {'messages': [], 'hasMore': False})
        if isinstance(item, Exception):
            raise item
        return item

    async def members(self, talker):
        return [{'accountId': 'wxid_peer', 'displayName': '朋友'}]


REQ = WeFlowExportRequest('wxid_peer', 'wxid_peer', 10, 100)


async def test_authenticated_http_and_errors_never_expose_body():
    calls = []
    def handler(r):
        calls.append(r)
        if r.url.path == '/api/v1/sessions':
            return httpx.Response(200, json={'success': True, 'sessions': [{'username': 'wxid_peer'}]})
        if r.url.path == '/api/v1/messages':
            return httpx.Response(200, json={'success': True, 'talker': 'wxid_peer', 'messages': [], 'hasMore': False})
        return httpx.Response(401, text='server secret')
    c = WeFlowClient(Settings(weflow_token='test-weflow-secret'), httpx.MockTransport(handler))
    assert (await c.test_connection())['success']
    await c.page('wxid_peer', 10, 100, 200)
    assert calls[-1].url.params['offset'] == '200'
    assert calls[-1].url.params['media'] == '0'
    assert calls[-1].headers['Authorization'] == 'Bearer test-weflow-secret'
    assert 'test-weflow-secret' not in str(calls[-1].url)
    with pytest.raises(WeFlowError, match='Token') as e:
        await c.get('bad')
    assert 'server secret' not in str(e.value)
    assert all(r.method == 'GET' for r in calls)
    await c.close()


async def test_preview_pagination_export_persona_roundtrip(db, tmp_path):
    pages = [{'messages': [wx(1), wx(2, own=1), wx(3, text='[图片]', kind=3)], 'hasMore': True},
             {'messages': [wx(4, text='另一个文本'), wx(5, time=101)], 'hasMore': False}]
    exporter = WeFlowExporter(db, API(pages))
    preview = await exporter.preview(REQ)
    assert [r['message_id'] for r in preview] == ['1', '3', '4']
    assert not preview[1]['text'] and preview[1]['has_image']
    assert not db.all('SELECT * FROM export_batches')
    exporter.napcat = API(pages)
    result = await exporter.export(REQ)
    assert result['count'] == 3 and result['valid_text_count'] == 2 and result['low_sample']
    assert exporter.napcat.offsets == [0, 3]
    llm = FakeLLM()
    persona = await PersonaAnalyzer(db, llm, Tuning()).analyze(result['batch_id'])
    assert persona['member_id'] == 'wxid_peer' and persona['member_nickname'] == '朋友'
    assert '[图片]' not in json.dumps(llm.calls, ensure_ascii=False)
    from qq_persona_agent.services import Services
    svc = Services(db)
    out = tmp_path / 'persona.json'
    svc.export_persona(persona['id'], out)
    assert svc.import_persona(out)['member_id'] == 'wxid_peer'
    await svc.runtime.stop(); await svc.napcat.close(); await svc.weflow.close(); await svc.llm.close()
    for p in tmp_path.glob('test.db*'):
        assert '微信秘密原文'.encode() not in p.read_bytes()


async def test_own_messages_and_groups_no_cross_sender(db):
    req = WeFlowExportRequest('room@chatroom', '__self__', 10, 100)
    rows = [wx(1), wx(2, sender='', own=1), wx(3, sender='third'), wx(4, sender='', kind=10000)]
    r = await WeFlowExporter(db, API([{'messages': rows, 'hasMore': False}])).export(req)
    stored = db.messages(r['batch_id'])
    assert len(stored) == 1 and stored[0]['sender_id'] == 'wxid_me'
    assert stored[0]['group_id'] == 'weflow:wxid_me:room%40chatroom'


async def test_resume_and_account_guard(db):
    api = API([{'messages': [wx(1)], 'hasMore': True}, RuntimeError('network')])
    e = WeFlowExporter(db, api)
    with pytest.raises(RuntimeError):
        await e.export(REQ)
    batch = db.one('SELECT * FROM export_batches')
    api.owner = 'other-account'
    with pytest.raises(WeFlowError, match='账号已改变'):
        await e.export(REQ, batch['id'])
    api.owner = 'wxid_me'; api.pages = iter([{'messages': [wx(1), wx(2)], 'hasMore': False}])
    r = await e.export(REQ, batch['id'])
    assert r['count'] == 2 and api.offsets[-1] == 1


async def test_repeated_page_marked_partial(db):
    p = {'messages': [wx(1)], 'hasMore': True}
    r = await WeFlowExporter(db, API([p, p])).export(REQ)
    assert r['status'] == 'partial' and r['count'] == 1


async def test_account_switch_during_page_stops_before_persist(db):
    class Changed(API):
        async def page(self, *args):
            self.owner = 'different_owner'
            return {'messages': [wx(1, own=1)], 'hasMore': False}
    exporter = WeFlowExporter(db, Changed([]))
    with pytest.raises(WeFlowError, match='读取期间改变'):
        await exporter.export(REQ)
    assert not db.all('SELECT * FROM exported_messages')
    assert db.one('SELECT status FROM export_batches')['status'] == 'interrupted'


async def test_nonadjacent_page_cycle_stops_and_local_ids_remain_distinct(db):
    a, b = wx(0), wx(0)
    a['localId'], b['localId'] = 41, 42
    api = API([{'messages': [a], 'hasMore': True}, {'messages': [b], 'hasMore': True},
               {'messages': [a], 'hasMore': True}])
    result = await WeFlowExporter(db, api).export(REQ)
    assert result['status'] == 'partial' and result['count'] == 2


async def test_invalid_metadata_and_timeout_are_actionable():
    c = WeFlowClient(Settings(), httpx.MockTransport(lambda _: httpx.Response(200, json={'meta': {}})))
    with pytest.raises(WeFlowError, match='ownerId'):
        await c.metadata('wxid_peer')
    await c.close()
    def timeout(r):
        raise httpx.ReadTimeout('sensitive raw detail', request=r)
    c = WeFlowClient(Settings(), httpx.MockTransport(timeout))
    result = await c.test_connection()
    assert not result['success'] and '超时' in result['reason'] and 'sensitive' not in result['reason']
    await c.close()


async def test_cancel_before_fetch_and_resume(db):
    cancel = threading.Event(); cancel.set()
    e = WeFlowExporter(db, API([{'messages': [wx(1)], 'hasMore': False}]))
    r = await e.export(REQ, cancel=cancel)
    assert r['status'] == 'interrupted' and not e.napcat.offsets
    assert (await e.export(REQ, r['batch_id']))['count'] == 1


async def test_owner_namespace_isolates_same_message_ids(db):
    e = WeFlowExporter(db, API([{'messages': [wx(1)], 'hasMore': False}]))
    first = await e.export(REQ)
    e.napcat = API([{'messages': [wx(1)], 'hasMore': False}]); e.napcat.owner = 'another'
    second = await e.export(REQ)
    assert db.messages(first['batch_id'])[0]['group_id'] != db.messages(second['batch_id'])[0]['group_id']
    assert db.one('SELECT count(*) AS n FROM exported_messages')['n'] == 2


def test_weflow_settings_encrypted_defaults(db):
    from qq_persona_agent.config import SettingsStore
    from qq_persona_agent.logging_utils import log
    store = SettingsStore(db)
    legacy = asdict(Settings()); legacy.pop('weflow_token'); legacy.pop('weflow_http')
    db.execute('INSERT INTO settings VALUES(?,?,?)', ('Settings', db.crypto.encrypt(json.dumps(legacy)), 'now'))
    assert store.load().weflow_http == 'http://127.0.0.1:5031'
    s = Settings(weflow_token='my-weflow-secret'); store.save(s)
    assert store.load().weflow_token == s.weflow_token
    log.register(s.weflow_token)
    assert s.weflow_token not in log.redact(s.weflow_token)


def test_weflow_gui_source_and_settings(tmp_path):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtWidgets import QApplication, QLineEdit
    from qq_persona_agent.app_gui import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(tmp_path / 'wxgui.db'); w.confirm = lambda _: True
    page = w.export_page; page.chat_type.setCurrentIndex(2)
    source = page.weflow_source
    source.sessions.addItem('朋友', 'wxid_peer'); source.confirm_session()
    source.scope.setCurrentIndex(1)
    req = page.request()
    assert req.user_id == '__self__' and req.talker == 'wxid_peer'
    source.query.setText('different')
    with pytest.raises(ValueError): page.request()
    assert w.settings_page.controls['weflow_token'].echoMode() == QLineEdit.EchoMode.Password
    assert w.services.runtime.status == 'stopped'
    w.close()
