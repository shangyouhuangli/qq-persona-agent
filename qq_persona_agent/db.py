from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from .config import Crypto, data_dir


def now():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else data_dir() / 'persona.db'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.crypto = Crypto()
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA busy_timeout=10000')
        self.conn.executescript(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
        self.execute("UPDATE agents SET status='stopped'")

    @contextmanager
    def transaction(self):
        with self.lock, self.conn:
            yield self.conn

    def execute(self, sql, args=()):
        with self.transaction() as conn:
            return conn.execute(sql, args).lastrowid

    def all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def pack(self, value):
        return self.crypto.encrypt(json.dumps(value, ensure_ascii=False))

    def unpack(self, value):
        return json.loads(self.crypto.decrypt(value))

    def messages(self, batch_id):
        rows = self.all('SELECT m.* FROM exported_messages m JOIN batch_messages b ON b.message_pk=m.id WHERE b.batch_id=? ORDER BY timestamp,message_id', (batch_id,))
        for r in rows:
            for key in ('sender_nickname', 'text', 'raw_segments_json'):
                r[key] = self.unpack(r[key])
        return rows

    def persona(self, persona_id):
        r = self.one('SELECT * FROM personas WHERE id=?', (persona_id,))
        if not r:
            raise ValueError('人格不存在')
        for key in ('member_nickname', 'structured_analysis_json', 'persona_prompt'):
            r[key] = self.unpack(r[key])
        return r

    def save_persona(self, p):
        return self.execute('INSERT INTO personas(group_id,member_id,member_nickname,sample_count,confidence,structured_analysis_json,persona_prompt,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                            (p['group_id'], p['member_id'], self.pack(p['member_nickname']), p['sample_count'], p['confidence'], self.pack(p['structured_analysis_json']), self.pack(p['persona_prompt']), now(), now()))

    def clear(self):
        with self.transaction() as conn:
            for table in ('memory_short', 'memory_facts', 'agents', 'personas', 'batch_messages', 'exported_messages', 'export_batches', 'settings', 'llm_logs', 'send_logs'):
                conn.execute(f'DELETE FROM {table}')
        with self.lock:
            self.conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            self.conn.execute('VACUUM')

    def close(self):
        with self.lock:
            self.conn.close()
