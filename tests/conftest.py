import pytest
from qq_persona_agent.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / 'test.db')
    yield database
    database.close()


def message(mid, timestamp, text='unique secret chat 正文', sender='123456789', seq=None):
    return {'message_id': mid, 'message_seq': seq or mid, 'time': timestamp, 'user_id': sender,
            'sender': {'nickname': '昵称'}, 'message': [{'type': 'text', 'data': {'text': text}}]}


@pytest.fixture
def persona(db):
    from qq_persona_agent.persona_analyzer import DIMENSIONS
    return db.save_persona({'group_id': '234567890', 'member_id': '123456789', 'member_nickname': '某某',
        'sample_count': 10, 'confidence': 'low', 'persona_prompt': '【身份层】授权风格模拟\n【语言层】简短\n【反应层】自然\n【边界层】不编经历',
        'structured_analysis_json': {**{k: {'value': {}, 'confidence': 'low', 'evidence': []} for k in DIMENSIONS}, 'unreliable_dimensions': list(DIMENSIONS), 'summary': '短句'}})
