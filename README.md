# QQ 群成员人格智能体

Windows 10/11 + Python 3.11+，PySide6 QtWidgets 工作台。NapCat OneBot v11 HTTP/正向 WebSocket、DeepSeek、SQLite、人工审批、自主发送、MCP 与 Agent Skill。

GitHub仓库包含完整源码、测试、Skill/MCP和打包配置；Windows单文件exe与SHA256校验文件放在Releases。仓库不包含凭据、聊天数据、个人画像、NapCat登录数据或本地Python环境。下载源码后按下方步骤安装依赖；MCP通用示例见examples目录，运行生成脚本可获得本机路径配置。

历史分页兼容修复已合并到唯一正式程序 `dist/QQPersonaAgent.exe`。旧版程序和临时补丁已移出项目备份；历史原因见 [分页问题记录](docs/HISTORY_FIX.md)。

## 文件位置

- `dist/QQPersonaAgent.exe`：唯一正式程序；根目录快捷方式可直接启动。
- `exports/`：你手动保存的人格 JSON，已从程序目录分开保留。
- `qq_persona_agent/`、`tests/`：源码和测试。
- `docs/`：设计、验收和维护记录。
- `scripts/`、`build.spec`：构建及 MCP 配置示例生成脚本。
- `skills/`、`examples/`：Agent Skill 和 MCP 配置示例。
- `.venv/`、`tools/`：源码/MCP 运行环境和 UPX；不影响双击 exe 使用。
- 配置和聊天数据仍在 `%LOCALAPPDATA%/QQPersonaAgent/`。
- 旧版本、维护备份放在项目外 `%LOCALAPPDATA%/QQPersonaAgentMaintenance/20261102-upgrade/`。

先阅读 [设计与接口](docs/DESIGN.md) 和 [验收记录](docs/ACCEPTANCE.md)。本项目只参考 LangBot 的适配器/共用服务分层，未复制第三方源码。

## 双击运行

构建完成后双击 `dist/QQPersonaAgent.exe`。无需安装 Python；单文件首次启动需要解压到 Windows 临时目录。配置及数据位于 `%LOCALAPPDATA%/QQPersonaAgent/`，不写在 exe 旁。

默认不监听、不发送；生成人格后必须到部署页显式启用预览监听。程序退出/重启不会恢复运行。GUI 与 MCP 只能启动一个实例，避免重复发送。

## 源码运行与最小验证

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m qq_persona_agent.app --smoke-test
.\.venv\Scripts\python -m qq_persona_agent.app
```

GUI 使用 `PySide6-Essentials` 发行包，包含 QtCore/Gui/Widgets，不安装 QML/WebEngine。代理支持 HTTP/HTTPS；如需 SOCKS，请额外安装 `httpx[socks]` 和 `python-socks[asyncio]`。代理中有凭据时也加密存储，不在日志记录 URL。

## 首次操作

1. 在 NapCat 开启 HTTP 服务与正向 WS 事件服务，设置访问 Token；机器人账号需已加入源群和目标群。WS 地址可含路径，不能含访问令牌查询串。
2. 设置页填写 DeepSeek Key（默认 `deepseek-chat`）、NapCat HTTP/WS/Token、代理和超时，保存后分别测试连接。测试 DeepSeek 会实际调用模型并消耗少量额度。
3. 导出页刷新群与成员，确认成员号/昵称，设置本机时区的时间起止和最大成员消息条数。先预览20条，必要时修改范围；再导出。默认保存 `.jsonl.enc`，部分历史或游标异常会明确标记 `partial`。
4. 中断时点“恢复上次中断”，使用原批次参数/游标，事务去重。恢复不会修改既有请求上限；要增加范围或上限请新开批次。NapCat 只能提供其可访问的历史，本工具不保证取到全部历史。
5. 人格页生成两次调用的画像，查看 JSON/摘要/低置信度，编辑提示词后保存。可加载历史或导入/导出明文人格 JSON。JSON 包含画像和提示词，请自行保管。
6. 部署页选择目标群后会自动加载最近30条供查看；启用后通过 HTTP 每3秒补读新消息，并同时监听已配置的 WebSocket 事件。读取和回复状态会显示在聊天区。历史消息仅供查看和上下文，不触发追溯回复。默认 mention 只对被 @ 消息生成候选；要分析每条新群消息，请选择“自主判断（分析新群消息）”并点击“应用到当前智能体”。这只切换候选生成方式，不等于自主发送授权。
7. 你已确认有成员授权且向群友说明是风格模拟。完成画像和候选预览后，可显式勾选“自主发送”并确认；开启触发范围不等于授权发送。
8. 顶栏“停止智能体”始终可用；目标群任意成员发送纯文本 `/stop` 可停止。发送、认证或其他API请求故障会停止；WS不可用时由HTTP继续读取，模型格式异常跳过本轮。无发送重试；超时可能发生在服务端已接受消息之后，应先检查群消息再重新操作。

参数保存会停止当前运行。token 预算以 UTF-8 字节数作保守上界，模型实际计费 token 在日志中显示。人格/锁定块与长期记忆共享预算，超限部署会拒绝，不静默截断人格。短期上下文另设预算；中期检索为本地关键词相关性，不依赖向量服务。记忆反思在空闲或消息累计阈值触发，主动发起默认关闭。

模型连接正常仍可能返回空白、截断或错误 JSON。JSON调用遇到内容格式异常最多额外重试一次（这会消耗一次API额度）；仍失败则跳过本轮并继续读取群聊。自主模式连续3轮格式异常会切回人工审批。日志只记录 `empty_content`、`output_truncated`、`invalid_json`、`json_not_object` 等分类、返回字符数和结束原因，不记录返回正文。认证/账户/连接故障与发送失败仍会停止；发送不自动重试。“测试 DeepSeek”同时验证JSON输出，不再只检查普通文本响应。

## 数据与日志

- API Key、NapCat Token、完整设置、聊天正文/昵称/原始段、人格库及记忆由当前 Windows 用户 DPAPI 加密，没有明文回退。群号/成员号作为本机 SQLite 索引保留；日志掩码保留后四位。
- `.jsonl.enc` 是整份 JSON Lines 经 DPAPI 加密，当前用户可用 `Crypto().decrypt(path.read_text())` 在内存中查看，不是可跨机器直接读取的明文 JSONL。
- 人格 JSON 按你的选择允许明文，界面显式确认后保存；数据库中的人格仍加密。
- “不得将聊天写入日志”优先于“记录每轮完整输入输出”：日志仅记录模型、token、延迟、JSON 成功、发送字符数和结果。聊天正文仅在 GUI 和加密业务存储可见，不复制到日志。
- 日志仅保留当前进程最近2000条，可导出已脱敏 `.log`。QQ号与已登记凭据保留末四位；原始网络响应/异常正文不写日志。
- 一键清除会停止、清空数据库和默认目录 `history-*.jsonl.enc`；自行选择其他目录导出的人格和日志不自动搜索删除。DPAPI 文件只适用于原 Windows 用户/机器；常规删除不等于磁盘取证级擦除。

## MCP / Skill

先在 GUI 配好加密凭据，关闭 GUI，再执行：

```powershell
.\.venv\Scripts\python scripts/generate_mcp_configs.py
.\.venv\Scripts\python -m qq_persona_agent.skill_export
```

最后一条是 stdio 服务，等待宿主 JSON-RPC 输入，不是交互式控制台。不要把无控制台 GUI exe 用作 stdio MCP；使用 `.venv/Scripts/python.exe` 入口。

生成的 `examples/codex-config.toml` 内容可合并到 Codex 的 `~/.codex/config.toml`；`examples/.mcp.json` 适用于 Claude Code 项目配置。示例已填本机绝对路径；移动目录后重新生成。不会自动修改你的 Agent 配置。[OpenAI MCP 配置文档](https://learn.chatgpt.com/docs/extend/mcp)

工具返回结构化对象和 `summary`：

| 工具 | 默认行为 |
|---|---|
| export_group_member_history | preview_only=true 仅20条预览；false 加密导出；支持 batch_id |
| analyze_member_persona | 两次调用，保存并返回画像，不监听 |
| deploy_persona_agent | dry_run=true 只给部署计划；false 是明确授权监听及自主发送 |
| stop_agent | 停止当前 MCP 运行实例，无外发消息 |
| preview_persona_reply | DeepSeek 候选预览，无 QQ 连接/发送 |
| list_local_personas | ID/置信度/样本数列表 |

Agent Skill 位于 `skills/qq-persona-agent/SKILL.md`。可将整个目录复制到编码 Agent 的个人 skills 目录；它调用 MCP 共用业务层，不另实现协议。MCP 进程退出时部署结束；没有 Windows 服务常驻模式。Skill 产物已生成，未自动安装到全局目录。

## 打包

```powershell
# 从 https://github.com/upx/upx/releases 下载官方 Windows UPX，将 upx.exe 放入 tools/upx/
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
# 无 UPX 的备选构建（不满足压缩要求，只用于排障）
powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -NoUPX
```

`build.spec` 实现 onefile/windowed，`upx=True`；显式收集 PySide6 platforms 插件。Qt DLL、平台插件和 Python DLL 排除 UPX，以保留正常加载；其余符合条件的二进制由 PyInstaller 使用 UPX。构建脚本先跑测试，再打包，最后对 exe 运行临时数据库离线 GUI 自检并输出 SHA256。

资源相对包 `__file__` 定位，PyInstaller 会指向 `_MEIPASS` 中的包；`resource_path()` 为额外资源提供 `_MEIPASS` 兼容入口。不要在 `_MEIPASS` 中保存可变配置。

当前 exe 未做代码签名。清洁 Windows 10/11 机器、真实 NapCat 与 DeepSeek 的联网验收需按验收表完成；mock 与离线自检不代表这些项目已经通过。
