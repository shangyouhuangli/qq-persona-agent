import hashlib
import time


class RiskControl:
    def __init__(self, tuning):
        self.tuning, self.recent = tuning, {}
        self.last_send = float('-inf')
        self.cool_until = 0

    def check(self, text):
        now = time.monotonic()
        if not text.strip() or len(text) > 2000:
            return '回复为空或超出 2000 字符'
        if now < self.cool_until or now - self.last_send < self.tuning.min_interval:
            return '频率限制，请等待冷却'
        digest = hashlib.sha256(text.strip().encode()).hexdigest()
        self.recent = {k: v for k, v in self.recent.items() if now - v < self.tuning.dedup_seconds}
        if digest in self.recent:
            return '短时间重复内容被拦截'
        if any(w.strip() and w.strip() in text for w in self.tuning.sensitive_words.split(',')):
            return '命中敏感词兜底'
        return None

    def sent(self, text):
        self.last_send = time.monotonic()
        self.recent[hashlib.sha256(text.strip().encode()).hexdigest()] = self.last_send

    def cooldown(self):
        self.cool_until = time.monotonic() + self.tuning.cooldown
