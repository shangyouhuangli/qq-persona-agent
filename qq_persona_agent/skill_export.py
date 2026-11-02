"""MCP stdio facade; all business logic lives in Services."""
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP, Context
from mcp.types import ToolAnnotations
from .config import data_dir
from .models import ExportRequest
from .services import Services
from .logging_utils import log


@asynccontextmanager
async def lifespan(server):
    from PySide6.QtCore import QLockFile
    lock = QLockFile(str(data_dir() / 'app.lock'))
    if not lock.tryLock(0):
        raise RuntimeError('GUI 或其他 MCP 实例已运行，请先关闭另一实例')
    services = Services()
    try:
        yield services
    finally:
        await services.close()
        lock.unlock()


mcp = FastMCP('QQPersonaAgent', lifespan=lifespan, log_level='ERROR',
              instructions='已获授权的 QQ 风格模拟工具。先预览导出和人格，再部署。部署默认 dry_run；只有用户明确授权发送才能传 false。进程退出会停止智能体。GUI 和 MCP 同时只能运行一个。')
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)


def service(ctx):
    return ctx.request_context.lifespan_context


@mcp.tool(annotations=WRITE)
async def export_group_member_history(group_id: str, user_id: str, start_time: int, end_time: int,
                                      ctx: Context, max_messages: int = 1000, preview_only: bool = True,
                                      batch_id: str | None = None) -> dict:
    """默认预览20条；确认后 preview_only=false 执行加密导出；batch_id 恢复中断。时间为 Unix 秒。"""
    request = ExportRequest(group_id, user_id, start_time, end_time, max_messages)
    request.validate()
    svc = service(ctx)
    if preview_only:
        rows = await svc.exporter.preview(request)
        return {'preview': rows, 'count': len(rows), 'summary': '请人工检查样本质量；确认后以 preview_only=false 导出'}
    result = await svc.exporter.export(request, batch_id)
    path = svc.db.path.parent / f"history-{result['batch_id']}.jsonl.enc"
    svc.exporter.save_encrypted_jsonl(result['batch_id'], path)
    return {**result, 'encrypted_path': str(path)}


@mcp.tool(annotations=WRITE)
async def analyze_member_persona(batch_id: str, ctx: Context) -> dict:
    """两次 DeepSeek 调用生成画像并保存，返回人格供预览；不会部署。调用消耗 API 额度。"""
    p = await service(ctx).analyzer.analyze(batch_id)
    return {**p, 'summary': '人格已生成并保存，请预览编辑；尚未监听或发送'}


@mcp.tool(annotations=WRITE)
async def deploy_persona_agent(persona_id: int, group_id: str, ctx: Context, dry_run: bool = True,
                               trigger_mode: str = 'mention', keywords: str = '') -> dict:
    """默认 dry_run=true 仅返回部署预览。用户明确授权后 false 才监听并自主发送。"""
    svc = service(ctx)
    p = svc.db.persona(persona_id)
    if not group_id.isdigit() or trigger_mode not in ('mention', 'keyword', 'autonomous'):
        raise ValueError('群号或触发方式无效')
    if trigger_mode == 'keyword' and not keywords.strip():
        raise ValueError('关键词不能为空')
    if dry_run:
        return {'dry_run': True, 'persona_id': persona_id, 'group_id': group_id, 'trigger_mode': trigger_mode,
                'persona_prompt': p['persona_prompt'], 'summary': '仅部署预览，未监听、未发送。请确认画像与候选回复，并授权后传 dry_run=false'}
    return {'dry_run': False, **await svc.runtime.start(persona_id, group_id, trigger_mode, keywords, autonomous=True)}


@mcp.tool(annotations=WRITE)
async def stop_agent(ctx: Context, agent_id: int | None = None) -> dict:
    """停止本 MCP 进程的智能体，取消未完成回复并丢弃候选。不向 QQ 发送消息。"""
    svc = service(ctx)
    if agent_id is not None and agent_id != svc.runtime.agent_id:
        raise ValueError('该 agent 不属于当前 MCP 运行实例')
    svc.runtime.emergency_stop()
    await svc.runtime.stop()
    return {'status': 'stopped', 'summary': '已停止，候选全部失效'}


@mcp.tool(annotations=READ)
async def list_local_personas(ctx: Context) -> dict:
    """列出本地画像 ID 和置信度，不返回聊天记录。"""
    return {'personas': service(ctx).db.all('SELECT id,sample_count,confidence,created_at FROM personas ORDER BY id DESC'), 'summary': '本地人格列表'}


@mcp.tool(annotations=WRITE)
async def preview_persona_reply(persona_id: int, message: str, ctx: Context) -> dict:
    """离线生成候选供预览，调用 DeepSeek，但不连接 QQ、不发送。"""
    svc = service(ctx)
    p = svc.db.persona(persona_id)
    if not message.strip() or len(message) > 4000:
        raise ValueError('预览输入必须为1~4000字符')
    result = await svc.llm.complete([{'role': 'system', 'content': p['persona_prompt'] + '\n仅 JSON {"replies":["回复"]}，不超过3条。'}, {'role': 'user', 'content': message}], json_mode=True)
    return {'candidate': result, 'summary': '候选预览，不会向 QQ 发送'}


def main():
    mcp.run(transport='stdio')


if __name__ == '__main__':
    main()
