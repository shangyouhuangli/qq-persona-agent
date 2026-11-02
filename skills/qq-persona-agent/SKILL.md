---
name: qq-persona-agent
description: 通过本项目 MCP 导出已授权的 QQ 群成员历史，分析聊天风格并预览、部署或停止人格智能体。适用于已配置 NapCat 与 DeepSeek 的本机 Windows 工作流。
---

使用已配置的 QQPersonaAgent MCP，不复制导出、分析和运行时代码。配置示例见项目 `examples/`，入口为 `python -m qq_persona_agent.skill_export`。先在 GUI 保存加密凭据，然后关闭 GUI 以释放本地实例锁，再启动 MCP。

先核对群号、成员号、时间范围和成员授权/群内风格模拟披露。模糊昵称必须让用户确认实际成员，不能自动选择同名第一人。时间转换为 Unix 秒并说明使用的时区。

1. `export_group_member_history` 默认 `preview_only=true`，检查样本并让用户修改目标或范围；确认后使用 `preview_only=false`，中断用同一参数及 `batch_id` 续传。partial 代表历史不完整，不能描述为完整导出。
2. `analyze_member_persona` 使用批次 ID，返回分析和人格。呈现 low confidence 与不可靠维度；生成会消耗 DeepSeek 额度，不会监听群。
3. `preview_persona_reply` 使用用户提供的场景生成候选，不发送；允许用户修改画像后在 GUI 保存再继续。
4. `deploy_persona_agent` 首次保持 `dry_run=true`。只有用户已经预览画像、候选并明确授权自主发送，才传 `dry_run=false`。不要从“分析”“生成”“看看效果”推断发送授权。保持 mention 默认；扩大自主触发范围需符合用户要求。
5. `stop_agent` 可随时调用；群内任意成员 `/stop` 同样停止。MCP 退出也停止，不把部署说成独立后台服务。

不把凭据、聊天内容或原始工具响应写到 Agent 日志或额外文件。聊天导出为当前 Windows 用户可解密的 `.jsonl.enc`；用户允许的明文人格 JSON 由 GUI 显式保存。不要向其他群转发原文证据。

GUI 和 MCP 不可同时占用数据，遇到实例锁错误应说明当前状态，不删除活跃锁。发送失败自动停止，不自动重试发送；排查权限/禁言/风控后由用户决定是否重新启用。
