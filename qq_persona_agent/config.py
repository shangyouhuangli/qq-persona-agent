from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse


def data_dir() -> Path:
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'QQPersonaAgent'
    root.mkdir(parents=True, exist_ok=True)
    return root


def resource_path(name: str) -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / name


class Crypto:
    """Windows CurrentUser DPAPI; no plaintext fallback."""
    def __init__(self):
        if sys.platform != 'win32':
            raise RuntimeError('仅支持 Windows DPAPI；不允许明文回退')

    @staticmethod
    def _transform(data: bytes, decrypt: bool) -> bytes:
        class Blob(ctypes.Structure):
            _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        source, target = Blob(len(data), buffer), Blob()
        crypt = ctypes.WinDLL('crypt32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        fn.restype = wintypes.BOOL
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
            raise RuntimeError('DPAPI 操作失败，确认使用原 Windows 用户和机器')
        try:
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            kernel.LocalFree(target.pbData)

    def encrypt(self, text: str) -> str:
        return 'dpapi1:' + base64.b64encode(self._transform(text.encode('utf-8'), False)).decode('ascii')

    def decrypt(self, value: str | bytes) -> str:
        if isinstance(value, bytes):
            value = value.decode('ascii')
        if not value.startswith('dpapi1:'):
            raise ValueError('无效加密格式，拒绝明文读取')
        return self._transform(base64.b64decode(value[7:]), True).decode('utf-8')


@dataclass
class Settings:
    api_key: str = ''
    base_url: str = 'https://api.deepseek.com'
    model: str = 'deepseek-chat'
    napcat_http: str = 'http://127.0.0.1:3000'
    napcat_token: str = ''
    napcat_ws: str = 'ws://127.0.0.1:3001'
    proxy: str = ''
    timeout: int = 30
    weflow_http: str = 'http://127.0.0.1:5031'
    weflow_token: str = ''

    def validate(self):
        for key in ('base_url', 'napcat_http', 'napcat_ws', 'weflow_http'):
            url = urlparse(getattr(self, key))
            valid = ('ws', 'wss') if key.endswith('_ws') else ('http', 'https')
            if url.scheme not in valid or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError(f'{key}: 需要有效 URL，不能包含凭据、查询参数或片段')
        if not 1 <= self.timeout <= 300:
            raise ValueError('超时必须为 1~300 秒')
        if self.proxy and urlparse(self.proxy).scheme not in ('http', 'https', 'socks5'):
            raise ValueError('代理地址无效')


@dataclass
class Tuning:
    recognition_messages: int = 30
    recognition_tokens: int = 4000
    short_turns: int = 10
    medium_top_k: int = 4
    long_tokens: int = 6000
    reflection_minutes: int = 15
    reflection_messages: int = 50
    max_replies: int = 2
    min_interval: float = 3
    delay_min: float = 3
    delay_max: float = 12
    cooldown: float = 30
    dedup_seconds: int = 300
    failure_retries: int = 1
    message_max_chars: int = 500
    analysis_tokens: int = 12000
    allow_initiate: bool = False
    sensitive_words: str = ''
    include_faces: bool = False
    max_reply_chars: int = 10
    short_reply_weight: int = 65
    medium_reply_weight: int = 25
    long_reply_weight: int = 10

    def reply_length_limits(self):
        return (max(1, self.max_reply_chars // 3), max(1, self.max_reply_chars * 2 // 3), self.max_reply_chars)

    def reply_length_weights(self):
        return (self.short_reply_weight, self.medium_reply_weight, self.long_reply_weight)

    def validate(self):
        if type(self.max_reply_chars) is not int or not 1 <= self.max_reply_chars <= 2000:
            raise ValueError('每条回复最大字符数必须为1~2000')
        weights = self.reply_length_weights()
        if any(type(w) is not int or not 0 <= w <= 1000 for w in weights) or sum(weights) == 0:
            raise ValueError('短/中/长回复权重必须为0~1000，且至少一个大于0')
        if not 1 <= self.max_replies <= 3:
            raise ValueError('连发上限必须为 1~3')
        if not 0 <= self.delay_min <= self.delay_max <= 300 or self.min_interval < 0 or self.cooldown < 0:
            raise ValueError('延迟/冷却参数无效')
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0:
                raise ValueError(f'{field.name} 不能为负数')
        if min(self.recognition_messages, self.recognition_tokens, self.short_turns,
               self.long_tokens, self.reflection_minutes, self.reflection_messages,
               self.message_max_chars, self.analysis_tokens) < 1:
            raise ValueError('上下文、反思和分析预算必须为正数')


class SettingsStore:
    def __init__(self, db):
        self.db = db

    def load(self, cls=Settings):
        value = self.db.one('SELECT value_encrypted FROM settings WHERE key=?', (cls.__name__,))
        return cls(**json.loads(self.db.crypto.decrypt(value['value_encrypted']))) if value else cls()

    def save(self, obj):
        obj.validate()
        self.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?,datetime(\'now\'))',
                        (type(obj).__name__, self.db.crypto.encrypt(json.dumps(asdict(obj))).encode('ascii')))
