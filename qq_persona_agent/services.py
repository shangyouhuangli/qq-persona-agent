import asyncio
import json
from pathlib import Path
from .agent_runtime import AgentRuntime
from .chat_exporter import ChatExporter
from .config import SettingsStore, Settings, Tuning
from .db import Database, now
from .llm_client import LLMClient
from .logging_utils import log
from .napcat_client import NapCatClient
from .persona_analyzer import PersonaAnalyzer
from .conversations import valid_key


class Services:
    def __init__(self, db=None, notify=None):
        self.db = db or Database()
        self.store = SettingsStore(self.db)
        self.settings, self.tuning = self.store.load(), self.store.load(Tuning)
        self.notify = notify
        self.wire()

    def wire(self):
        log.register(self.settings.api_key, self.settings.napcat_token)
        self.napcat = NapCatClient(self.settings)
        self.napcat.read_retries = min(self.tuning.failure_retries, 3)
        self.llm = LLMClient(self.settings, self.db)
        self.exporter = ChatExporter(self.db, self.napcat)
        self.analyzer = PersonaAnalyzer(self.db, self.llm, self.tuning)
        self.runtime = AgentRuntime(self.db, self.napcat, self.llm, self.tuning, self.notify)

    async def configure(self, settings, tuning=None):
        settings.validate()
        if tuning:
            tuning.validate()
        await self.runtime.stop()
        await self.napcat.close()
        await self.llm.close()
        self.settings = settings
        self.tuning = tuning or self.tuning
        self.store.save(settings)
        self.store.save(self.tuning)
        self.wire()
        log.emit('settings', '设置已加密保存；智能体保持停止')
        return {'summary': '设置已保存'}

    async def close(self):
        await self.runtime.stop()
        await self.napcat.close()
        await self.llm.close()
        self.db.close()

    async def clear(self):
        await self.runtime.stop()
        await self.configure(Settings(), Tuning())
        self.db.clear()
        log.records.clear()
        for path in self.db.path.parent.glob('history-*.jsonl.enc'):
            path.unlink(missing_ok=True)
        return {'summary': '本应用默认目录数据库与加密历史导出已清除；自行导出的外部文件请自行删除'}

    def save_edited_persona(self, persona_id, prompt):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('人格提示词不能为空')
        self.db.execute('UPDATE personas SET persona_prompt=?,updated_at=? WHERE id=?', (self.db.pack(prompt), now(), persona_id))
        return self.db.persona(persona_id)

    def export_persona(self, persona_id, path):
        path.write_text(json.dumps(self.db.persona(persona_id), ensure_ascii=False, indent=2), encoding='utf-8')

    def import_persona(self, path):
        if path.stat().st_size > 2**20:
            raise ValueError('人格文件超过 1MB')
        p = json.loads(path.read_text(encoding='utf-8-sig'))
        for key in ('group_id', 'member_id', 'member_nickname', 'persona_prompt'):
            if not isinstance(p.get(key), str):
                raise ValueError('人格文件字段类型错误')
        if not valid_key(p['group_id']) or not p['member_id'].isdigit() or not p['persona_prompt'].strip():
            raise ValueError('人格文件标识或提示词无效')
        PersonaAnalyzer.validate(p.get('structured_analysis_json', {}))
        p['sample_count'] = int(p['sample_count'])
        if p.get('confidence') not in ('low', 'medium', 'high'):
            raise ValueError('人格 confidence 无效')
        p['id'] = self.db.save_persona(p)
        return p
