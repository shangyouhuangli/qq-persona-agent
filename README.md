# QQ / 微信聊天记录人格生成与 QQ 智能体

Windows 10/11 + Python 3.11+，PySide6 QtWidgets 工作台。支持 QQ 群聊/私聊与微信聊天记录提取、自己或对方的聊天风格分析、人格画像 JSON 生成；QQ 还支持人工审批回复和显式开启自主发送。微信通过 WeFlow 只读接入。集成 NapCat OneBot v11、DeepSeek、加密 SQLite、MCP 与 Agent Skill。

GitHub仓库包含完整源码、测试、Skill/MCP和打包配置；Windows单文件exe与SHA256校验文件放在Releases。仓库不包含凭据、聊天数据、个人画像、NapCat登录数据或本地Python环境。下载源码后按下方步骤安装依赖；MCP通用示例见examples目录，运行生成脚本可获得本机路径配置。

历史分页兼容修复已合并到唯一正式程序 `dist/QQPersonaAgent.exe`。旧版程序和临时补丁已移出项目备份；历史原因见 [分页问题记录](docs/HISTORY_FIX.md)。

## 下载与快速开始

1. 从 [本项目 Releases](https://github.com/shangyouhuangli/qq-persona-agent/releases/latest) 下载 `QQPersonaAgent.exe` 和 `SHA256SUMS.txt`。
2. 按下一节安装并登录 NapCat，配置 HTTP 与正向 WebSocket。
3. 双击本程序，在设置页保存 DeepSeek 和 NapCat 配置，再执行两项连接测试。
4. 按“导出预览 → 导出 → 人格预览 → 候选预览 → 人工批准”完成第一次测试。

只使用微信记录生成人格：先按 [WeFlow 配置教程](docs/WEFLOW.md) 加载数据库并开启 API 服务，在本程序保存 WeFlow 地址/Token 与 DeepSeek 配置，然后选择“微信记录（WeFlow）”导出并生成人格 JSON；此流程不需要 NapCat。

exe 无需安装 Python。源码下载包不含 exe、本地虚拟环境、UPX、账号配置和群记录；exe 从 Releases 单独下载。项目源码放在同一目录时，正式程序位于 `dist/QQPersonaAgent.exe`；本机已有的启动快捷方式只是便利入口，GitHub 下载包不包含快捷方式。

## 安装 NapCat（Windows）

本程序是应用端，NapCat 是连接 QQ 的协议端，两者需分别运行。机器人 QQ 必须加入源群和目标群，实际消息由机器人 QQ 发出。以下按 NapCat 与本程序在同一台 Windows 电脑说明。

### 方式一：官方 Windows 一键安装（推荐新用户）

1. 打开 [NapCat 官方 Releases](https://github.com/NapNeko/NapCatQQ/releases/latest)，展开 **Assets**。
2. 下载 `NapCat.Shell.Windows.OneKey.zip`，完整解压到固定目录，例如 `D:\NapCat`，不要直接在压缩包里运行。
3. 运行解压后的 `NapCatInstaller.exe`，按安装器提示完成 QQ 和 NapCat 部署；这种方式无需事先安装 QQ。
4. 安装完成后进入生成的 `NapCat.XXXX.Shell` 目录，双击 `napcat.bat`。
5. 按控制台提示扫码登录机器人 QQ，保持 NapCat 启动。
6. 打开控制台输出的 WebUI 地址。通常为 `http://127.0.0.1:6099/webui/`，实际地址、端口和登录密钥以启动日志为准。首次登录若要求修改 WebUI 密码，先完成修改。

官方安装器和启动入口可能随版本变化，以下载包说明为准。[官方 Shell 安装教程](https://napneko.github.io/guide/boot/Shell)

### 方式二：已有 QQ，手动安装 Shell

从官方 Releases 下载 `NapCat.Shell.zip`，安装官方文档支持的 QQ 版本并完整解压 NapCat。Windows 11 运行 `launcher.bat`；Windows 10 按官方教程运行 `launcher-win10.bat`，按控制台提示登录并打开 WebUI。

`NapCat.Framework.zip` 是 LiteLoaderQQNT 插件包，适用于已部署 LiteLoader 的环境，不等同于一键安装器。已有 Framework 安装可继续使用，不必再安装第二套；升级前退出对应 QQ/NapCat，备份原配置，按官方方式升级。Shell、Framework 及 Node 包的用途见 [官方安装包说明](https://napneko.github.io/guide/boot/release)。

### 配置 HTTP 和正向 WebSocket

在 NapCat WebUI 的 **网络配置 → 新建** 中分别创建以下两个服务：

| 配置 | HTTP 服务器 | WebSocket 服务器（正向 WS） |
|---|---|---|
| 启用 | 开启 | 开启 |
| Host / 监听地址 | `127.0.0.1` | `127.0.0.1` |
| 端口 | `3000` | `3001` |
| Token | 自设较长随机字符串 | 与 HTTP 填相同 Token |
| 消息上报格式（若有） | `array` | `array` |
| 上报自身消息（若有） | 关闭 | 关闭 |
| Debug（若有） | 关闭 | 关闭 |

保存并应用；如页面要求重启，重启 NapCat。选择 **WebSocket 服务器**，不要误建成 WebSocket 客户端（反向 WS）。WebUI 登录密码和这里的 OneBot 服务 Token 是两套凭据，本程序填写的是服务 Token。[官方网络配置指南](https://napneko.github.io/config/basic)

本机运行无需公网映射。端口已占用时可换其他空闲端口，同时修改本程序对应地址。若 NapCat 在另一台电脑或 Docker 中，`127.0.0.1` 不再指向它；需要额外配置实际主机地址、端口映射和访问权限，本教程的本机地址不能直接照搬。

### 在本程序中连接

| 本程序设置项 | 填写内容 |
|---|---|
| NapCat HTTP | `http://127.0.0.1:3000` |
| NapCat WebSocket | `ws://127.0.0.1:3001` |
| NapCat Token | 上面两个服务的相同 Token，不带 `Bearer ` 前缀 |
| DeepSeek API Key | 自己账户的 Key |
| DeepSeek Base URL | 默认 `https://api.deepseek.com` |
| 模型 | 默认 `deepseek-chat`，以账户实际可用模型为准 |
| 全局代理 | 本机直连时先留空 |
| 请求超时 | 默认 30 秒，可按网络情况调整 |

点击 **保存设置**，再点击 **测试 NapCat** 和 **测试 DeepSeek**。NapCat 测试验证 HTTP 登录接口；WebSocket 由部署监听时连接。DeepSeek 测试会调用一次 JSON 输出请求，产生少量 API 费用。WS 不可用时程序可通过 HTTP 每 3 秒补读，但建议仍配置正向 WS 以降低实时延迟。

本项目已在 NapCat 4.18.42 上验证 HTTP 登录和历史翻页。旧版 4.7.5 存在已确认的历史分页方向问题；遇到反复读到同一页请升级，而非清空聊天数据库。参见 [分页问题记录](docs/HISTORY_FIX.md)。

## 文件位置

| 位置 | 内容 |
|---|---|
| `dist/` | 本机构建/下载的唯一正式 exe 和校验和，不提交源码仓库 |
| `exports/` | 用户自行导出的画像，可能包含个人内容，不提交仓库 |
| `qq_persona_agent/`、`tests/` | 程序源码、数据库 DDL 和测试 |
| `docs/` | 设计、验收与维护记录 |
| `scripts/`、`build.spec` | 构建、MCP 配置生成脚本 |
| `skills/`、`examples/` | Agent Skill 与通用 MCP 配置示例 |
| `%LOCALAPPDATA%/QQPersonaAgent/` | 加密设置、聊天数据库、默认历史导出 |

本地 `.venv/` 为源码和 MCP 的 Python 环境；`tools/upx/` 由构建者准备。它们不在 GitHub 源码包中。

先阅读 [设计与接口](docs/DESIGN.md) 和 [验收记录](docs/ACCEPTANCE.md)。本项目只参考 LangBot 的适配器/共用服务分层，未复制第三方源码。

## 双击运行

构建完成后双击 `dist/QQPersonaAgent.exe`。无需安装 Python；单文件首次启动需要解压到 Windows 临时目录。配置及数据位于 `%LOCALAPPDATA%/QQPersonaAgent/`，不写在 exe 旁。

默认不监听、不发送；生成人格后必须到部署页显式启用预览监听。程序退出/重启不会恢复运行。GUI 与 MCP 只能启动一个实例，避免重复发送。

## 源码运行与最小验证

```powershell
git clone https://github.com/shangyouhuangli/qq-persona-agent.git
cd qq-persona-agent
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

QQ每条回复最大字符数（含标点）与短/中/长回复权重可在参数页调整，默认10字符、65/25/10权重。三档预算分别为最大字符数的三分之一、三分之二和全长（向下取整，至少1字符）。例如最大30字符、权重1/2/7，代表以10%/20%/70%的概率选用最多10/20/30字符预算，实际回复可以更短。权重无需合计100，可将某档设0，不能全部为0。保存参数并重新启用智能体生效；模型超预算结果会本地截短，人工编辑及发送兜底按全局最大字符数校验。

“发送后禁止调用回复 API（秒）”沿用原冷却参数，默认30秒，从本次最后一条成功发送后计时。连发期间和冷却期间仅读取、显示、记忆新消息，不生成候选、不进行格式重试；旧触发队列丢弃，时间到了只响应后续新消息，不补答冷却期间内容。记忆反思也延后到冷却结束。冷却开始前已经发出的请求不能撤销已产生的计费，返回时会再次检查，避免变成新的发送候选。

模型连接正常仍可能返回空白、截断或错误 JSON。JSON调用遇到内容格式异常最多额外重试一次（这会消耗一次API额度）；仍失败则跳过本轮并继续读取群聊。自主模式连续3轮格式异常会切回人工审批。日志只记录 `empty_content`、`output_truncated`、`invalid_json`、`json_not_object` 等分类、返回字符数和结束原因，不记录返回正文。认证/账户/连接故障与发送失败仍会停止；发送不自动重试。“测试 DeepSeek”同时验证JSON输出，不再只检查普通文本响应。

## 常见问题

### 微信记录与人格 JSON（WeFlow）

现支持通过 WeFlow 读取微信私聊或群聊记录，选择自己、对方或指定群成员，预览导出后复用人格分析并保存 JSON。

1. 在 [WeFlow](https://github.com/hicccc77/WeFlow) 中先加载微信数据库并确认历史可读，在设置中开启 **API 服务**，取得地址与 Token（默认端口5031）。
2. 本程序设置页填写 **WeFlow HTTP / WeFlow API Token**，保存并测试连接。
3. 数据导出选择 **微信记录（WeFlow）**，按名称或 wxid 检索并确认会话，选择发送者与时间范围，先预览再导出。
4. 在人格生成页生成、编辑并保存人格 JSON。微信记录仅用于读取和画像生成，不提供微信对话、部署或自动发送。

记录默认加密；Token 用 DPAPI 加密。详见 [WeFlow 使用与接口说明](docs/WEFLOW.md)。真实读取取决于 WeFlow 已加载的数据库和版本。

### 个人私聊：按 QQ 号检索

1. 在**数据导出**页将记录类型切为“个人私聊记录”，输入完整QQ号，点击“按QQ号检索”，核对返回的昵称、QQ号及好友状态并确认。
2. 在“提取谁的消息”中选择“对方”或“自己（NapCat 当前登录账号）”，选择时间范围和上限，预览后导出。QQ号始终用于定位与该联系人的私聊；选“自己”只提取自己在此会话发出的内容，并用于生成自己的画像，双方内容不混合。加密存储、断点恢复和低样本提示与群记录相同。
3. 在人格页生成或加载人格后，到**部署与聊天**页切换“个人私聊”，同样输入QQ号检索并确认目标；自动读取最近私聊，启用预览后持续读取新消息。
4. 私聊默认“被@”模式视为收到对方消息即可触发，不需要在私聊中@机器人；关键词模式只在命中时触发。生成候选默认仍需人工批准。切换联系人或修改QQ输入会使旧目标失效，并停止旧会话，防止误发。
5. 如需主动发送，启用预览后点击“新建手动消息”，输入后生成候选，再点击“批准发送”。这不调用模型，也不会因为已开启自主模式就跳过人工批准。字数上限、去重和冷却仍生效。
6. 对方发`/stop`或点击顶栏停止均可终止。启用自主发送仍要单独确认，默认关闭。

NapCat仅能读取机器人账号自身可访问的好友/会话记录，不是查询任意QQ的全部聊天记录。资料检索成功不保证有历史或发送权限；非好友可能无法读取或发消息，工具不会自动加好友、创建临时会话或绕过权限。群和个人部署共用一个运行实例，同一时间只监听一个目标。

MCP同时提供 `find_private_contact`、`export_private_history`、`deploy_private_persona_agent`；人格分析及停止继续共用原工具。兼容数据库中的`group_id`列存储会话键，私聊键为`private:QQ号`，与同号群彻底隔离；不需要删除旧库。新私聊画像JSON可保存和重新加载。

| 现象 | 原因与处理 |
|---|---|
| NapCat 401 / Token 错误 | HTTP/WS 服务 Token 必须与本程序一致；不要填 WebUI 密码 |
| 连接被拒绝 / WS 中断 | 检查对应服务已启用、端口正确；HTTP 是3000，正向WS是3001；先在WebUI保存应用 |
| 能导出，但没有实时候选 | 先加载人格并启用；默认仅被 @ 触发。普通群聊需选“自主判断”并应用到当前智能体 |
| 机器人自己发消息不生成候选 | 为防止自回复循环，自身消息只展示；用另一个群成员发送测试消息 |
| 历史消息显示但不回复 | 设计如此：最近历史仅展示和提供上下文，不追溯发送；启用后等待新消息 |
| `partial` / 游标停滞 | 历史并未全部获取；升级旧NapCat并检查账号能访问的记录，使用“恢复上次中断”去重续传 |
| `low_sample=True` | 有效文本或实际分析样本不足100条，扩大时间范围/上限；画像低置信度并非连接失败 |
| 生成候选但不发送 | 默认人工模式；选择候选、编辑后批准。自主发送需单独勾选并确认 |
| 冷却时不调用模型 | 参数页“发送后禁止调用回复 API”正在生效；消息仍显示记忆，期满不补答旧触发 |
| `empty_content` / `invalid_json` | 模型返回格式异常，最多重试一次，失败跳过本轮；连续异常会切回人工审批 |
| 人格超过记忆预算 | 缩短人格提示词或增加参数页的长期记忆预算，含锁定块成本 |
| GUI/MCP 提示实例已运行 | 关闭另一实例后重试；两者共用本地数据且只允许运行一个 |
| exe 第一次启动慢 | PyInstaller单文件需先解压临时资源；程序未签名，下载后可核对SHA256 |

验证下载文件：

```powershell
Get-FileHash .\QQPersonaAgent.exe -Algorithm SHA256
# 将 Hash 与同一 Release 的 SHA256SUMS.txt 比较
```

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

## 验证范围与参考

当前源码通过93项测试，涵盖分页恢复、加密、JSON异常处理、实时读取、审批/停止、回复长度权重及调用前冷却；单文件在本机通过离屏和原生Windows启动自检。这不代表每个QQ/NapCat版本、模型服务或清洁Windows机器均已验证。

- [本项目发布与下载](https://github.com/shangyouhuangli/qq-persona-agent/releases)
- [NapCat 官方项目](https://github.com/NapNeko/NapCatQQ)
- [NapCat Windows 安装](https://napneko.github.io/guide/boot/Shell)
- [NapCat 网络配置](https://napneko.github.io/config/basic)
- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)
- [LangBot 平台适配器参考](https://github.com/langbot-app/LangBot/blob/master/src/langbot/pkg/platform/sources/aiocqhttp.py)

NapCat/QQ作为外部依赖单独安装和升级，不随本程序Release重新分发。请只处理有权使用的聊天记录，并向群友说明风格模拟身份。
