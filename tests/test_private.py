import asyncio
import json
import pytest
import httpx
from qq_persona_agent.config import Settings
from qq_persona_agent.napcat_client import NapCatClient
from qq_persona_agent.chat_exporter import ChatExporter
from qq_persona_agent.models import ExportRequest
from qq_persona_agent.agent_runtime import AgentRuntime
from qq_persona_agent.conversations import private_key
from test_runtime import Nap, LLM, tuning
from conftest import message


async def test_exact_contact_history_and_text_only_send():
    calls=[]
    def handler(r):
        action=r.url.path.rsplit('/',1)[-1];data=json.loads(r.content);calls.append((action,data))
        response={'get_friend_list':[{'user_id':123456789,'nickname':'matched'},{'user_id':123456,'nickname':'other'}], 'get_friend_msg_history':{'messages':[]},'send_private_msg':{'message_id':9},'get_stranger_info':{'user_id':99999,'nickname':'stranger'}}[action]
        return httpx.Response(200,json={'status':'ok','retcode':0,'data':response})
    n=NapCatClient(Settings(),httpx.MockTransport(handler))
    assert (await n.find_contact('123456789'))['nickname']=='matched'
    assert not (await n.find_contact('99999'))['is_friend']
    await n.get_friend_msg_history('123456789','-55')
    await n.send_private_msg('123456789','[CQ:at,qq=all]')
    assert calls[-2][1]['reverseOrder'] is True and calls[-2][1]['message_seq']=='-55'
    assert calls[-1]==('send_private_msg',{'user_id':'123456789','message':[{'type':'text','data':{'text':'[CQ:at,qq=all]'}}]})
    await n.close()


class PrivateNap(Nap):
    def __init__(self,pages=None):super().__init__();self.pages=iter(pages or [[]]);self.private_sent=[]
    async def get_friend_msg_history(self,uid,cursor=None,count=100):return next(self.pages,[])
    async def send_private_msg(self,uid,text):self.private_sent.append((uid,text))


class OwnHistoryNap(PrivateNap):
    own_id = '999999999'

    async def action(self, action):
        assert action == 'get_login_info'
        return {'user_id': self.own_id}


async def test_private_own_preview_export_and_persona(db):
    from qq_persona_agent.persona_analyzer import PersonaAnalyzer
    from qq_persona_agent.config import Tuning
    from test_persona import FakeLLM
    rows = [message(5, 90, '对方的话'), message(4, 80, '自己的话', sender='999999999')]
    req = ExportRequest('private:123456789', '123456789', 10, 100, sender_scope='self')
    exporter = ChatExporter(db, OwnHistoryNap([rows, []]))
    preview = await exporter.preview(req)
    assert [r['text'] for r in preview] == ['自己的话']
    exporter.napcat = OwnHistoryNap([rows, []])
    result = await exporter.export(req)
    stored = db.messages(result['batch_id'])
    assert len(stored) == 1 and stored[0]['sender_id'] == '999999999'
    assert stored[0]['group_id'] == 'private:123456789'
    llm = FakeLLM()
    persona = await PersonaAnalyzer(db, llm, Tuning()).analyze(result['batch_id'])
    assert persona['member_id'] == '999999999'
    assert '对方的话' not in json.dumps(llm.calls, ensure_ascii=False)


async def test_private_own_resume_rejects_changed_login(db):
    req = ExportRequest('private:123456789', '123456789', 10, 100, sender_scope='self')
    nap = OwnHistoryNap([[message(4, 80, sender='999999999')], []])
    exporter = ChatExporter(db, nap)
    result = await exporter.export(req)
    nap.own_id = '888888888'
    with pytest.raises(ValueError, match='参数不匹配'):
        await exporter.export(req, result['batch_id'])


async def test_private_own_login_required(db):
    nap = OwnHistoryNap(); nap.own_id = ''
    with pytest.raises(ValueError, match='当前登录 QQ'):
        await ChatExporter(db, nap).preview(ExportRequest('private:123456789', '123456789', 0, 100, sender_scope='self'))


async def test_legacy_export_batch_request_still_resumes(db):
    from dataclasses import asdict
    from test_export import Pages, REQUEST
    exporter = ChatExporter(db, Pages([[message(5, 90)], []]))
    result = await exporter.export(REQUEST)
    legacy = asdict(REQUEST); legacy.pop('sender_scope')
    db.execute('UPDATE export_batches SET request_json=? WHERE id=?', (db.pack(json.dumps(legacy)), result['batch_id']))
    assert (await exporter.export(REQUEST, result['batch_id']))['count'] == 1


def private_event(mid='p1',sender='123456789',text='你好',target=None):
    e=message(mid,20,text,sender=sender);e['message_type']='private'
    if target:e['target_id']=target
    return e


async def test_private_export_excludes_own_messages_and_group_namespace(db):
    rows=[message(5,90),message(4,80,sender='999999999')]
    n=PrivateNap([rows,[message(3,20),message(2,5)]])
    result=await ChatExporter(db,n).export(ExportRequest(private_key('123456789'),'123456789',10,100))
    stored=db.messages(result['batch_id'])
    assert len(stored)==2 and all(r['group_id']=='private:123456789' for r in stored)
    assert all(r['sender_id']=='123456789' for r in stored)


async def test_same_numeric_group_and_private_message_id_do_not_collide(db):
    from test_export import Pages
    exporter=ChatExporter(db,Pages([[message(7,20)],[]]))
    group=await exporter.export(ExportRequest('123456789','123456789',10,100))
    exporter.napcat=PrivateNap([[message(7,20)],[]])
    private=await exporter.export(ExportRequest('private:123456789','123456789',10,100))
    assert len(db.messages(group['batch_id']))==len(db.messages(private['batch_id']))==1
    assert db.one('SELECT COUNT(*) AS n FROM exported_messages')['n']==2


async def test_private_preview_approval_targets_only_selected_user(db,persona):
    nap,llm=PrivateNap(),LLM()
    r=AgentRuntime(db,nap,llm,tuning())
    await r.start(persona,'private:123456789')
    await r.ingest(private_event(sender='888888'))
    await r.ingest({**private_event(), 'message_type':'group','group_id':'123456789'})
    assert not r.seen
    await r.ingest(private_event())
    await asyncio.wait_for(llm.started.wait(),1)
    for _ in range(50):
        if r.pending:break
        await asyncio.sleep(.005)
    assert not nap.private_sent and not nap.sent
    await r.approve(next(iter(r.pending)),['私聊回复'])
    assert nap.private_sent==[('123456789','私聊回复')] and not nap.sent
    await r.ingest(private_event(mid='stop',text='/stop'))
    assert r.status=='stopped'


async def test_group_runtime_rejects_private_events(db,persona):
    r=AgentRuntime(db,Nap(),LLM(),tuning());await r.start(persona,'234567890')
    await r.ingest({**private_event(),'group_id':'234567890'})
    assert not r.seen
    await r.stop()


async def test_private_manual_message_requires_separate_approval(db,persona):
    nap,llm=PrivateNap(),LLM();r=AgentRuntime(db,nap,llm,tuning())
    await r.start(persona,'private:123456789',autonomous=True)
    cid=r.manual_candidate('主动打招呼')
    assert not llm.started.is_set() and not nap.private_sent
    await r.approve(cid)
    assert nap.private_sent==[('123456789','主动打招呼')]
    await r.stop()
    with pytest.raises(ValueError):r.manual_candidate('停止后禁止')


async def test_private_recent_history_does_not_trigger_api(db,persona):
    nap,llm,events=PrivateNap([[private_event(text='/stop')]]),LLM(),[]
    r=AgentRuntime(db,nap,llm,tuning(),events.append)
    await r.start(persona,'private:123456789')
    assert any(e['kind']=='message' and e['historical'] for e in events)
    assert r.status=='preview' and not llm.started.is_set()
    await r.stop()


async def test_private_polling_generates_once_and_never_sends_without_approval(db,persona):
    import time
    class PollNap(PrivateNap):
        def __init__(self):super().__init__();self.rows=[]
        async def get_friend_msg_history(self,uid,cursor=None,count=100):return list(self.rows)
    nap,llm=PollNap(),LLM();r=AgentRuntime(db,nap,llm,tuning());r.poll_interval=.01
    await r.start(persona,'private:123456789')
    new=private_event(mid='polled');new['time']=int(time.time())+1;nap.rows.append(new)
    await asyncio.wait_for(llm.started.wait(),1)
    await asyncio.sleep(.04)
    assert len(r.pending)==1 and not nap.private_sent and not nap.sent
    await r.ingest(new)
    assert len(r.pending)==1
    await r.stop()


async def test_private_send_failure_stops_without_group_fallback(db,persona):
    class FailPrivate(PrivateNap):
        async def send_private_msg(self,*args):raise RuntimeError('failed')
    nap=FailPrivate();r=AgentRuntime(db,nap,LLM(),tuning())
    await r.start(persona,'private:123456789')
    cid=r.manual_candidate('测试')
    await r.approve(cid)
    assert r.status=='stopped' and not nap.sent and not nap.private_sent


async def test_private_mcp_dryrun_no_connection(db,persona):
    from types import SimpleNamespace
    from qq_persona_agent.skill_export import deploy_private_persona_agent
    ctx=SimpleNamespace(request_context=SimpleNamespace(lifespan_context=SimpleNamespace(db=db)))
    result=await deploy_private_persona_agent(persona,'123456789',ctx)
    assert result['dry_run'] and result['group_id']=='private:123456789'


def test_contact_change_invalidates_target(tmp_path):
    import os
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from qq_persona_agent.app_gui import MainWindow
    app=QApplication.instance() or QApplication([]);w=MainWindow(tmp_path/'private-gui.db')
    w.confirm=lambda _:True
    p=w.deploy_page;p.chat_type.setCurrentIndex(1)
    p.contact.number.setText('123456789');p.contact.set_contact({'user_id':'123456789','nickname':'测试','is_friend':True},'123456789')
    assert p.target()=='private:123456789'
    p.contact.number.setText('999999')
    assert p.target() is None
    e=w.export_page;e.chat_type.setCurrentIndex(1)
    with pytest.raises(ValueError):e.request()
    w.close()
