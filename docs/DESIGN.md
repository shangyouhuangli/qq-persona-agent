# 设计及实施记录

## 假设和约定
- Windows 10/11、Python 3.11+；本机当前 Windows 用户通过 DPAPI 解密。其他用户/机器无法直接读取加密导出。
- 用户已确认有成员授权且向群友说明风格模拟。身份锁定只约束角色口吻，不应捏造真实经历。
- 用户允许明文人格 JSON；聊天正文、昵称、原始段、记忆及设置默认加密。日志仅元数据，QQ/凭据保留后四位。
- NapCat 为正向 HTTP 和正向 WebSocket；不安装或操作 QQ/NapCat，不自动配置外部服务。
- 默认 mention + preview；部署、生成和启动监听分离。MCP dry_run 不监听，false 是显式发送授权。进程退出即停止，不后台隐身运行。
- /stop 由目标群任意成员触发，避免误操作无法及时制止；重启不恢复自主发送。
- JSONL 默认加密为 .jsonl.enc；人格 JSON 明文导出前界面告知含画像内容。
- 真实 API 验收需要用户配置，mock 测试不等于真实 QQ/DeepSeek 通过。

## 架构与接口
`app.py → app_gui.MainWindow → services.Services`；MCP 同样调用 Services。

| 模块 | 接口/职责 |
|---|---|
| config | Settings / Tuning；DPAPI Crypto；SettingsStore.load/save |
| db | Database；DAO；敏感列加密，事务提交批次及游标 |
| logging_utils | 安全事件总线；仅固定模板+元数据，不保存聊天/异常响应体 |
| napcat_client | test_connection/get_group_list/get_group_member_list/get_group_msg_history/send_group_msg/events |
| chat_exporter | preview/export；清洗 CQ/段、时间过滤、去重、持久游标 |
| llm_client | complete/test_connection；JSON 校验、计费元数据 |
| persona_analyzer | analyze(batch_id) 两次调用；结构特征+四层 prompt |
| memory_store | short/context/facts/reflect，严格字符上界估算 token |
| risk_control | 频率、冷却、去重、敏感词、连发上限 |
| agent_runtime | start/handle/approve/discard/pause/stop；generation 防止停止后的旧结果发送 |
| services | 生命周期、配置重建、业务编排，GUI/MCP 共用 |
| skill_export | FastMCP stdio，结构化输出，无 stdout 日志 |

## 目录
```
qq_persona_agent/
  app.py app_gui.py config.py db.py models.py services.py
  napcat_client.py chat_exporter.py persona_analyzer.py llm_client.py
  agent_runtime.py memory_store.py risk_control.py logging_utils.py skill_export.py
  ui/{settings_page,export_page,persona_page,deploy_chat_page,tuning_page,log_panel}.py
tests/ docs/ skills/qq-persona-agent/ scripts/ build.spec README.md
```

## SQLite
详见 `qq_persona_agent/schema.sql`（可执行的唯一 DDL 来源）。要求的八表保留；另增 export_batches 和 batch_messages，支持多批次同一消息复用、进度事务提交。敏感文本列存储带版本前缀的加密字符串，settings 为 BLOB。索引按群/成员/时间及 agent 建立。启用外键、WAL、busy_timeout。只存 encrypted 内容，不生成明文临时文件。

## GUI 页面与控件
| 页面 | 控件 |
|---|---|
| 设置 | Key/Token 密码框、Base URL、模型、HTTP/WS、代理、超时、两连接测试、保存、清除确认 |
| 导出 | 实时群/成员下拉、昵称过滤、时间起止、上限、预览20条、导出/取消、进度、统计 |
| 人格 | 历史选择、生成/重生成、JSON/摘要、可编辑 prompt、保存到库/JSON、加载 JSON、低样本提示 |
| 部署聊天 | 目标群、触发方式/关键词、启用预览、显式自主发送确认、暂停、候选编辑批准/丢弃、消息流 |
| 参数 | 群消息/token、短期轮数、中期 top-k、长期预算、反思间隔、连发/间隔/随机延迟/冷却/重试、分析预算、默认恢复 |
| 日志 dock | 级别颜色、全部/错误/LLM/发送过滤、脱敏日志导出；全局停止常驻顶栏 |

## 验证计划（每步先设计再实现）
1. 设计：本文件 + schema.sql；验证 DDL 初始化。
2. 基础：DPAPI 往返、DB 文件无明文、日志脱敏测试。
3. 网络：MockTransport 验证鉴权/401/404/超时/风控；真实连接手工测。
4. 导出：重叠分页/游标停滞/断点恢复/时间与上限/CQ 测试。
5. 分析：两次独立调用、JSON 验证/空白错误/低样本强制 low。
6. 人工运行：审批一次性、停止后拒绝、记忆预算、风控测试。
7. GUI：offscreen 页面启动、设置、日志和停止 smoke。
8. 自主：取消随机等待、停止竞态、失败暂停、self/事件去重。
9. MCP：SDK stdio 初始化、list_tools/call_tool、dry-run 不监听。
10. 打包：PyInstaller windowed onefile，UPX 可用则启用；产物启动 smoke。外部连接项目注明待联调。

## 参考（不直接复制源码）
- https://github.com/langbot-app/LangBot/blob/master/src/langbot/pkg/platform/sources/aiocqhttp.py ：协议转换与平台隔离。
- https://github.com/langbot-app/LangBot/blob/master/ARCHITECTURE.md ：平台/管线/共用服务/MCP 分层。
- https://github.com/NapNeko/NapCatQQ ：动作参数与历史分页，NapCat 历史可用性取决于 QQ 本地与服务端。
- https://napneko.github.io/develop/api/doc ：接口。
- https://api-docs.deepseek.com/guides/json_mode/ ：json_object 需提示词 JSON、处理空白和截断。
- https://github.com/modelcontextprotocol/python-sdk ：本项目固定 SDK 1.x FastMCP 接口，避免 2.x 破坏变更。
