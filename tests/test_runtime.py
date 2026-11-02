import asyncio
import time
import pytest
from qq_persona_agent.agent_runtime import AgentRuntime
from qq_persona_agent.config import Tuning
from qq_persona_agent.risk_control import RiskControl
from conftest import message


class Nap:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail
        self.events_queue = asyncio.Queue()

    async def test_connection(self):
        return {'success': True, 'self_id': '999999999'}

    async def events(self):
        while True:
            yield await self.events_queue.get()

    async def send_group_msg(self, gid, text):
        if self.fail:
            raise RuntimeError('risk')
        self.sent.append((gid, text))


class LLM:
    def __init__(self, block=False):
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self.block = block

    async def complete(self, *args, **kwargs):
        self.started.set()
        if self.block:
            await self.release.wait()
        return {'should_reply': True, 'replies': ['你好']}


def event(text='你好', mid='1234'):
    e = message(mid, 20, text)
    e['group_id'] = '234567890'
    e['message'].append({'type': 'at', 'data': {'qq': '999999999'}})
    return e


def tuning(**kwargs):
    return Tuning(delay_min=0, delay_max=0, min_interval=0, cooldown=0, **kwargs)


async def candidate(runtime):
    await runtime.ingest(event())
    for _ in range(50):
        if runtime.pending:
            return next(iter(runtime.pending))
        await asyncio.sleep(.005)
    raise AssertionError('No candidate')


async def test_preview_approval_is_one_shot(db, persona):
    nap = Nap()
    runtime = AgentRuntime(db, nap, LLM(), tuning())
    await runtime.start(persona, '234567890')
    cid = await candidate(runtime)
    assert not nap.sent
    await runtime.approve(cid, ['人工编辑'])
    assert nap.sent == [('234567890', '人工编辑')]
    with pytest.raises(ValueError):
        await runtime.approve(cid)
    await runtime.stop()


async def test_stop_during_llm_and_group_stop(db, persona):
    llm, nap = LLM(True), Nap()
    runtime = AgentRuntime(db, nap, llm, tuning())
    await runtime.start(persona, '234567890', autonomous=True)
    await runtime.ingest(event())
    await llm.started.wait()
    await runtime.ingest(event('/stop', '4321'))
    llm.release.set()
    await asyncio.sleep(.01)
    assert runtime.stop_flag.is_set() and runtime.status == 'stopped' and not nap.sent and not runtime.pending


async def test_emergency_stop_during_random_delay(db, persona):
    nap = Nap()
    t = tuning()
    t.delay_min = t.delay_max = .1
    runtime = AgentRuntime(db, nap, LLM(), t)
    await runtime.start(persona, '234567890')
    cid = await candidate(runtime)
    task = asyncio.create_task(runtime.approve(cid))
    await asyncio.sleep(.01)
    runtime.emergency_stop()
    await task
    assert not nap.sent
    await runtime.stop()


async def test_send_failure_pauses(db, persona):
    nap = Nap(fail=True)
    runtime = AgentRuntime(db, nap, LLM(), tuning())
    await runtime.start(persona, '234567890')
    await runtime.approve(await candidate(runtime))
    assert runtime.status == 'stopped' and runtime.stop_flag.is_set()
    assert db.one('SELECT success FROM send_logs')['success'] == 0


async def test_self_dedup_and_unrelated_group(db, persona):
    runtime = AgentRuntime(db, Nap(), LLM(), tuning())
    await runtime.start(persona, '234567890')
    e = event()
    e['user_id'] = runtime.self_id
    await runtime.ingest(e)
    assert len(runtime.seen) == 1  # Own-account messages are displayed, never replied to.
    assert runtime.queue.empty()
    runtime.seen.clear()
    e['user_id'] = '123456789'
    e['group_id'] = '888888'
    await runtime.ingest(e)
    assert not runtime.seen
    e['group_id'] = runtime.group_id
    await runtime.ingest(e)
    await runtime.ingest(e)
    assert len(runtime.seen) == 1
    await runtime.stop()


async def test_expired_candidate(db, persona):
    runtime = AgentRuntime(db, Nap(), LLM(), tuning())
    await runtime.start(persona, '234567890')
    cid = await candidate(runtime)
    runtime.pending[cid]['created'] -= 601
    with pytest.raises(ValueError, match='十分钟'):
        await runtime.approve(cid)
    await runtime.stop()


def test_risk_dedup_words_rate_and_cooldown():
    t = tuning(sensitive_words='拦截词')
    risk = RiskControl(t)
    assert risk.check('包含拦截词')
    assert risk.check('hello') is None
    risk.sent('hello')
    assert risk.check('hello')
    t.min_interval = 30
    assert risk.check('different')
    t.min_interval = 0
    t.cooldown = 30
    risk.cooldown()
    assert risk.check('another')


async def test_stop_during_startup_cannot_reenable(db, persona):
    class SlowNap(Nap):
        def __init__(self):
            super().__init__()
            self.started, self.release = asyncio.Event(), asyncio.Event()

        async def test_connection(self):
            self.started.set()
            await self.release.wait()
            return {'success': True, 'self_id': '999999999'}
    nap = SlowNap()
    runtime = AgentRuntime(db, nap, LLM(), tuning())
    starting = asyncio.create_task(runtime.start(persona, '234567890'))
    await nap.started.wait()
    runtime.emergency_stop()
    await runtime.stop()
    nap.release.set()
    with pytest.raises(ValueError, match='取消'):
        await starting
    assert runtime.status == 'stopped' and runtime.stop_flag.is_set()


async def test_autonomous_mode_explicit_and_stop(db, persona):
    nap = Nap()
    runtime = AgentRuntime(db, nap, LLM(), tuning())
    await runtime.start(persona, '234567890', autonomous=True)
    await runtime.ingest(event())
    for _ in range(50):
        if nap.sent:
            break
        await asyncio.sleep(.005)
    assert nap.sent == [('234567890', '你好')]
    await runtime.stop()


async def test_multi_reply_capped_and_sensitive_blocked(db, persona):
    runtime = AgentRuntime(db, Nap(), LLM(), tuning(sensitive_words='禁止'))
    await runtime.start(persona, '234567890')
    cid = await candidate(runtime)
    with pytest.raises(ValueError):
        await runtime.approve(cid, ['一', '二', '三'])
    await runtime.ingest(event(mid='5678'))
    for _ in range(50):
        if runtime.pending: break
        await asyncio.sleep(.005)
    await runtime.approve(next(iter(runtime.pending)), ['禁止'])
    assert not runtime.napcat.sent
    await runtime.stop()


class HistoryNap(Nap):
    def __init__(self, history=None, ws_fail=False):
        super().__init__()
        self.history = history or []
        self.ws_fail = ws_fail

    async def get_group_msg_history(self, group_id, message_seq=None, count=100):
        return list(self.history)

    async def events(self):
        if self.ws_fail:
            raise ConnectionRefusedError()
        async for e in super().events():
            yield e


async def test_history_loaded_but_never_replied_to(db, persona):
    old = event('/stop')
    nap, llm, events = HistoryNap([old]), LLM(), []
    runtime = AgentRuntime(db, nap, llm, tuning(), events.append)
    await runtime.start(persona, '234567890', trigger_mode='autonomous', autonomous=True)
    await asyncio.sleep(.02)
    assert runtime.status == 'autonomous'
    assert not llm.started.is_set() and not runtime.pending and not nap.sent
    assert any(e['kind'] == 'message' and e['historical'] for e in events)
    await runtime.stop()


async def test_http_polling_works_without_websocket_and_dedups(db, persona):
    nap, llm, events = HistoryNap([event(mid='old')], ws_fail=True), LLM(), []
    runtime = AgentRuntime(db, nap, llm, tuning(), events.append)
    runtime.poll_interval = .01
    await runtime.start(persona, '234567890')
    new = event(mid='new')
    new['time'] = int(time.time()) + 1
    nap.history.append(new)
    await asyncio.wait_for(llm.started.wait(), 1)
    await asyncio.sleep(.05)
    assert runtime.status == 'preview' and len(runtime.pending) == 1 and not nap.sent
    assert len([e for e in events if e['kind'] == 'message' and e['message_id'] == 'new']) == 1
    await runtime.ingest(new)  # Same event can arrive through WS after HTTP.
    assert len(runtime.pending) == 1
    await runtime.stop()
    nap.history.append(event(mid='after-stop'))
    await asyncio.sleep(.03)
    assert not runtime.pending and not nap.sent


async def test_new_message_displayed_when_trigger_not_matched(db, persona):
    llm, events = LLM(), []
    runtime = AgentRuntime(db, Nap(), llm, tuning(), events.append)
    await runtime.start(persona, '234567890')
    e = event()
    e['message'] = e['message'][:1]  # No mention.
    await runtime.ingest(e)
    await asyncio.sleep(.01)
    assert any(e['kind'] == 'message' for e in events)
    assert any(e['kind'] == 'activity' and '等待被 @' in e['message'] for e in events)
    assert not llm.started.is_set()
    await runtime.stop()


async def test_own_account_message_visible_without_self_reply(db, persona):
    llm, events = LLM(), []
    runtime = AgentRuntime(db, Nap(), llm, tuning(), events.append)
    await runtime.start(persona, '234567890', trigger_mode='autonomous')
    e = event()
    e['user_id'] = runtime.self_id
    await runtime.ingest(e)
    assert any(e['kind'] == 'message' and e['self_message'] for e in events)
    assert not llm.started.is_set() and runtime.queue.empty()
    await runtime.stop()


async def test_trigger_changes_apply_without_enabling_auto_send(db, persona):
    llm = LLM()
    runtime = AgentRuntime(db, Nap(), llm, tuning())
    await runtime.start(persona, '234567890')
    runtime.set_trigger('autonomous')
    e = event()
    e['message'] = e['message'][:1]
    await runtime.ingest(e)
    await asyncio.wait_for(llm.started.wait(), 1)
    assert runtime.status == 'preview' and not runtime.napcat.sent
    await runtime.stop()


async def test_bad_model_format_skips_turn_and_worker_processes_next_message(db, persona):
    from qq_persona_agent.llm_client import LLMResponseError
    class BrokenThenGood:
        def __init__(self):self.calls = 0
        async def complete(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:raise LLMResponseError('blank', 'empty_content')
            return {'should_reply': True, 'replies': ['恢复正常']}
    llm, events = BrokenThenGood(), []
    runtime = AgentRuntime(db, Nap(), llm, tuning(), events.append)
    await runtime.start(persona, '234567890')
    await runtime.ingest(event(mid='bad'))
    await asyncio.sleep(.02)
    assert runtime.status == 'preview' and not runtime.stop_flag.is_set()
    assert any(e['kind'] == 'activity' and 'empty_content' in e['message'] for e in events)
    await runtime.ingest(event(mid='next'))
    for _ in range(50):
        if runtime.pending:break
        await asyncio.sleep(.005)
    assert len(runtime.pending) == 1 and not runtime.napcat.sent
    await runtime.stop()


async def test_repeated_schema_failures_disable_auto_send_but_keep_listening(db, persona):
    class WrongSchema:
        async def complete(self,*args,**kwargs):return {'should_reply':'yes','replies':'unsafe plain text'}
    runtime = AgentRuntime(db, Nap(), WrongSchema(), tuning())
    await runtime.start(persona, '234567890', autonomous=True)
    for i in range(3):await runtime.ingest(event(mid=f'wrong-{i}'))
    for _ in range(50):
        if runtime.status == 'preview':break
        await asyncio.sleep(.005)
    assert runtime.status == 'preview' and not runtime.stop_flag.is_set()
    assert not runtime.pending and not runtime.napcat.sent
    await runtime.stop()


async def test_authentication_failure_still_stops_runtime(db, persona):
    from qq_persona_agent.llm_client import LLMError
    class AuthFailure:
        async def complete(self,*args,**kwargs):raise LLMError('DeepSeek 认证失败，请检查 API Key')
    runtime = AgentRuntime(db, Nap(), AuthFailure(), tuning())
    await runtime.start(persona, '234567890')
    await runtime.ingest(event())
    for _ in range(50):
        if runtime.status == 'stopped':break
        await asyncio.sleep(.005)
    assert runtime.stop_flag.is_set() and runtime.status == 'stopped' and not runtime.napcat.sent
