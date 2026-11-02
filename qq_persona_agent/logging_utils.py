"""Only allowlisted metadata enters persistent/UI logs; never raw exceptions or chat."""
from datetime import datetime
import json
import re
import threading


class EventLog:
    def __init__(self):
        self.secrets = set()
        self.records = []
        self.listeners = []
        self.lock = threading.RLock()

    def register(self, *values):
        with self.lock:
            self.secrets.update(str(v) for v in values if v)

    def redact(self, value):
        result = str(value)
        with self.lock:
            for secret in sorted(self.secrets, key=len, reverse=True):
                result = result.replace(secret, '****' + (secret[-4:] if len(secret) > 4 else ''))
        result = re.sub(r'(?i)(?:Bearer\s+|sk-)[A-Za-z0-9_\-\.]+', '****', result)
        return re.sub(r'(?<!\d)\d{5,}(?!\d)', lambda m: '****' + m[0][-4:], result)

    def emit(self, category, message, level='INFO', **metadata):
        # Call sites supply fixed messages. Content/output are deliberately not accepted.
        allowed = {'model', 'input_tokens', 'output_tokens', 'latency_ms', 'json_parse_ok', 'group_id', 'count', 'status', 'error_type', 'chars', 'agent_id', 'finish_reason', 'response_chars', 'retry_attempt'}
        record = {'time': datetime.now().astimezone().isoformat(timespec='seconds'), 'level': level,
                  'category': category, 'message': self.redact(message),
                  **{k: self.redact(v) for k, v in metadata.items() if k in allowed}}
        with self.lock:
            self.records.append(record)
            self.records[:] = self.records[-2000:]
            listeners = list(self.listeners)
        for fn in listeners:
            try:
                fn(record)
            except Exception:
                pass

    def export(self, path):
        with self.lock:
            content = '\n'.join(json.dumps(r, ensure_ascii=False) for r in self.records)
        path.write_text(self.redact(content), encoding='utf-8')


log = EventLog()
