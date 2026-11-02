# 验收记录

环境：Windows，本机 Python 3.12；2026-11-02。此表区分自动验证与真实服务验收。

| 阶段 | 最小验证方式 | 状态 |
|---|---|---|
| 1 设计 | 阅读 DESIGN.md / schema.sql；Database 初始化 | 已通过 |
| 2 加密/存储/日志 | `python -m pytest tests/test_storage.py -q` | 已通过 |
| 3 NapCat | `python -m pytest tests/test_napcat.py -q` | Mock通过；升级4.18.42后真实HTTP连接/登录通过 |
| 4 导出预览 | `python -m pytest tests/test_export.py -q` | 重叠/续传/停滞/上限/加密通过；真实分页第二页新增96条 |
| 5 人格 | `python -m pytest tests/test_persona.py -q` | 两次调用及低置信度通过；真实模型待配置 |
| 6 人工/记忆/风控 | `python -m pytest tests/test_runtime.py tests/test_storage.py -q` | 已通过 |
| 7 GUI | `python -m qq_persona_agent.app --smoke-test` / tests/test_gui.py | 五页/日志/停止通过 |
| 8 自主/停止/暂停 | tests/test_runtime.py | 默认预览/一次性审批/发送失败/LLM中停止/随机延迟中停止通过 |
| 9 MCP/Skill | tests/test_llm_mcp.py；skill-creator quick_validate.py | stdio 初始化/list/call、dry-run不启动通过 |
| 10 打包 | scripts/build.ps1；exe --smoke-test / --native-smoke-test | UPX onefile/windowed 构建及隔离 PATH 自检通过，见 BUILD_RESULT.md |

## 需要用户配置后完成的真实联调
- 设置页保存真实凭据并重启读取（自动测试目前使用虚构 Key/Token）。
- NapCat HTTP 登录信息成功、WS 真事件连通、群与成员列表真实拉取。
- 时间范围历史导出及分页方向与当前 NapCat 版本一致；用已知消息交叉核对。
- DeepSeek 默认模型在当前账号可调用，两次分析实际返回 schema 完整。
- 目标测试群人工批准后发送一条，确认编辑生效；再测试自主发送明确确认。
- 目标群 /stop 与按钮停止，QQ 禁言/风控失败后停止且没有重试。
- 在未安装 Python 的清洁 Windows 10/11 验证 exe，检查平台插件和本地数据目录。

未经真实配置，不宣称以上联网验收通过。本程序没有自带 NapCat 或 QQ 客户端。

## 2026-11-02 实时群聊修复
- `python -m pytest -q`：44 passed。新增覆盖历史只读载入、HTTP轮询/WebSocket重复事件去重、无 @ 时仍显示并提示触发条件、自主判断只生成候选、QQ自身消息可见但不自回复，以及选群自动刷新 UI。
- 本机 NapCat 真实只读预览：HTTP加载最近30条，进入preview并产生transport状态事件；模拟LLM零调用、send_group_msg零调用。
- 新单文件通过隔离PATH的离屏和原生Windows窗口smoke，自主发送未启用。
