from pathlib import Path
import json
import pytest
from qq_persona_agent.config import Settings, SettingsStore, Crypto
from qq_persona_agent.logging_utils import EventLog
from qq_persona_agent.memory_store import MemoryStore, bounded
from qq_persona_agent.config import Tuning


def test_dpapi_and_no_plaintext_fallback():
    crypto = Crypto()
    encrypted = crypto.encrypt('secret-凭据')
    assert crypto.decrypt(encrypted) == 'secret-凭据'
    assert 'secret' not in encrypted
    with pytest.raises(ValueError):
        crypto.decrypt('plaintext')


def test_settings_encrypted_on_disk(db):
    store = SettingsStore(db)
    store.save(Settings(api_key='sk-this-is-sensitive-1234', napcat_token='sensitive-token-abcd'))
    assert store.load().napcat_token == 'sensitive-token-abcd'
    for p in db.path.parent.glob('test.db*'):
        assert b'sk-this-is-sensitive' not in p.read_bytes()
        assert b'sensitive-token' not in p.read_bytes()


def test_log_redaction_and_allowlist(tmp_path):
    log = EventLog()
    log.register('arbitrary-secret-abc123', 'short')
    log.emit('llm', 'fixed', api_key='arbitrary-secret-abc123', content='private chat', group_id='123456789')
    value = log.redact('arbitrary-secret-abc123 / 123456789 / Bearer abcXYZ / short')
    assert 'arbitrary-secret' not in value and '123456789' not in value and 'abcXYZ' not in value
    path = tmp_path / 'test.log'
    log.export(path)
    assert 'private chat' not in path.read_text() and 'api_key' not in path.read_text()


def test_memory_encryption_and_budget(db, persona):
    aid = db.execute("INSERT INTO agents(persona_id,status) VALUES(?,'preview')", (persona,))
    memory = MemoryStore(db, Tuning(recognition_tokens=18, short_turns=2))
    for _ in range(5):
        memory.append(aid, '234567890', 'user', '秘密中文' * 20)
    context, facts = memory.context(aid, '你好')
    assert sum(len(m['content'].encode()) for m in context) <= 18
    assert '秘密中文' not in str(db.all('SELECT content FROM memory_short'))
    assert len(bounded('中文内容', 5).encode()) <= 5


def test_clear(db, persona):
    SettingsStore(db).save(Settings(api_key='abc'))
    db.clear()
    assert not db.all('SELECT * FROM personas') and not db.all('SELECT * FROM settings')
