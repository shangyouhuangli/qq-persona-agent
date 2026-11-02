import asyncio
import json
import re
import time
import httpx
from openai import AsyncOpenAI, AuthenticationError, RateLimitError, APIConnectionError
from .db import now
from .logging_utils import log


class LLMError(RuntimeError):
    pass


class LLMResponseError(LLMError):
    """A successful provider request whose content cannot be safely consumed."""
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


class LLMClient:
    def __init__(self, settings, db):
        self.settings, self.db = settings, db
        self.client = AsyncOpenAI(api_key=settings.api_key or 'not-configured', base_url=settings.base_url,
                                 max_retries=0, timeout=settings.timeout,
                                 http_client=httpx.AsyncClient(proxy=settings.proxy or None, timeout=settings.timeout, trust_env=False))

    async def complete(self, messages, json_mode=False, agent_id=None, max_tokens=4096):
        for attempt in range(2 if json_mode else 1):
            current = messages if attempt == 0 else [*messages, {'role': 'user', 'content': '上次响应未通过内部 JSON 格式校验。请重新回答，仅输出一个符合上述字段要求的 JSON 对象，不要输出 Markdown、解释、裸文本或空白。'}]
            try:
                return await self._complete_once(current, json_mode, agent_id, max_tokens, attempt)
            except LLMResponseError:
                if not json_mode or attempt == 1:
                    raise

    async def _complete_once(self, messages, json_mode, agent_id, max_tokens, attempt):
        if not self.settings.api_key:
            raise LLMError('请先在设置页配置 DeepSeek API Key')
        started = time.monotonic()
        inp = out = 0
        parsed = False
        error = None
        finish_reason, response_chars = '', 0
        try:
            args = {'model': self.settings.model, 'messages': messages, 'max_tokens': max_tokens}
            if json_mode:
                args['response_format'] = {'type': 'json_object'}
            response = await self.client.chat.completions.create(**args)
            if response.usage:
                inp, out = response.usage.prompt_tokens, response.usage.completion_tokens
            if not response.choices:
                raise LLMResponseError('模型未返回候选响应', 'missing_choice')
            choice = response.choices[0]
            finish_reason = str(choice.finish_reason or '')
            text = choice.message.content or ''
            response_chars = len(text)
            if choice.finish_reason == 'length':
                raise LLMResponseError('模型输出被截断，本轮结果已忽略', 'output_truncated')
            if not text.strip():
                raise LLMResponseError('模型返回空白内容，本轮没有可用回复', 'empty_content')
            if json_mode:
                # Tolerate a complete fenced object, but never extract a random
                # object from prose or coerce arbitrary text into a sendable reply.
                match = re.fullmatch(r'\s*```(?:json)?\s*\n?(.*?)\n?```\s*', text, flags=re.S | re.I)
                payload = match[1] if match else text
                try:
                    result = json.loads(payload)
                except json.JSONDecodeError:
                    raise LLMResponseError('模型返回无效 JSON，本轮结果已忽略', 'invalid_json') from None
            else:
                result = text
            if json_mode and not isinstance(result, dict):
                raise LLMResponseError('模型返回的 JSON 顶层不是对象', 'json_not_object')
            parsed = True
            return result
        except asyncio.CancelledError:
            error = 'cancelled'
            raise
        except Exception as e:
            error = e.code if isinstance(e, LLMResponseError) else type(e).__name__
            if isinstance(e, LLMError):
                raise
            if isinstance(e, AuthenticationError):
                hint = 'DeepSeek 认证失败，请检查 API Key'
            elif isinstance(e, RateLimitError):
                hint = 'DeepSeek 限流或余额不足，请检查账户'
            elif isinstance(e, APIConnectionError):
                hint = 'DeepSeek 连接失败，请检查 URL、网络和代理'
            elif isinstance(e, (ValueError, IndexError)):
                hint = 'DeepSeek JSON/响应格式无效，请重试'
            else:
                hint = 'DeepSeek 调用失败，请检查模型、账户和服务状态'
            raise LLMError(hint) from None
        finally:
            elapsed = int((time.monotonic() - started) * 1000)
            self.db.execute('INSERT INTO llm_logs(agent_id,model,input_tokens,output_tokens,latency_ms,json_parse_ok,error,created_at) VALUES(?,?,?,?,?,?,?,?)',
                            (agent_id, log.redact(self.settings.model), inp, out, elapsed, int(parsed), error, now()))
            format_error = error in ('missing_choice', 'output_truncated', 'empty_content', 'invalid_json', 'json_not_object')
            log.emit('llm', 'LLM 返回格式异常' if format_error else 'LLM 调用完成', level='WARNING' if format_error else 'ERROR' if error else 'INFO', model=self.settings.model,
                     input_tokens=inp, output_tokens=out, latency_ms=elapsed, json_parse_ok=parsed, error_type=error or '',
                     finish_reason=finish_reason, response_chars=response_chars, retry_attempt=attempt)

    async def test_connection(self):
        try:
            result = await self.complete([{'role': 'system', 'content': '仅输出 JSON 对象 {"ok":true}。'}, {'role': 'user', 'content': '测试 JSON 输出。'}], json_mode=True, max_tokens=128)
            if result.get('ok') is not True:
                raise LLMResponseError('模型可连接，但 JSON 输出未通过测试', 'test_schema_invalid')
            return {'success': True, 'reason': 'DeepSeek 已连接，模型及 JSON 输出测试通过'}
        except LLMError as e:
            return {'success': False, 'reason': str(e)}

    async def close(self):
        await self.client.close()
