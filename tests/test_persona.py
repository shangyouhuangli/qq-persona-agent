from copy import deepcopy
import pytest
from qq_persona_agent.config import Tuning
from qq_persona_agent.chat_exporter import ChatExporter
from qq_persona_agent.persona_analyzer import PersonaAnalyzer, DIMENSIONS
from test_export import Pages, REQUEST
from conftest import message


class FakeLLM:
    def __init__(self):
        self.calls = []

    async def complete(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if len(self.calls) == 1:
            return {**{k: {'value': {'style': '短句'}, 'confidence': 'high', 'evidence': ['你好']} for k in DIMENSIONS}, 'unreliable_dimensions': [], 'summary': '偏短句'}
        return {'identity': '某某', 'language': '短句', 'reactions': '自然', 'boundaries': '不编造'}


async def test_two_calls_low_confidence_and_no_deployment(db):
    batch = await ChatExporter(db, Pages([[message(1, 20, '你好')], []])).export(REQUEST)
    llm = FakeLLM()
    p = await PersonaAnalyzer(db, llm, Tuning()).analyze(batch['batch_id'])
    assert len(llm.calls) == 2 and all(call[1]['json_mode'] for call in llm.calls)
    assert p['confidence'] == 'low' and all(p['structured_analysis_json'][k]['confidence'] == 'low' for k in DIMENSIONS)
    assert '人格锁定块' in p['persona_prompt'] and '不要编造经历' in p['persona_prompt']
    assert not db.all('SELECT * FROM agents')
    assert db.persona(p['id'])['persona_prompt'] == p['persona_prompt']


def test_schema_rejects_bad_output():
    with pytest.raises(ValueError):
        PersonaAnalyzer.validate({'language': 'made up'})
