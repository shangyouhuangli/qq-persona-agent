# 微信记录 → 人格 JSON（WeFlow）

只增加微信聊天记录读取、预览、加密导出和人格生成。没有微信发送接口、实时监听或微信部署流程；现有 QQ 功能继续独立使用。

## 使用

1. 安装并打开 [WeFlow](https://github.com/hicccc77/WeFlow)，按其向导加载自己的微信数据库。先在 WeFlow 中确认能看到目标会话的历史记录。本程序不会安装 WeFlow、获取微信密钥或替它解密数据库。
2. 在 WeFlow 设置中开启 **API 服务**，查看其地址、端口和 API Token。默认地址 `http://127.0.0.1:5031`。本功能只查询历史，无需开启主动推送。
3. 在本程序设置页填写 **WeFlow HTTP** 和 **WeFlow API Token**，保存设置，再点击 **测试 WeFlow**。测试查询鉴权会话接口，不能仅凭健康检查判定 Token 正确。Token 与其他凭据一起用 Windows DPAPI 加密。
4. 数据导出页选择 **微信记录（WeFlow）**，输入会话名称或 `wxid`，点击 **检索会话**。选择结果并点击 **确认会话 / 读取成员**。检索最多显示1000项，过多时缩小检索范围。这里用微信会话 ID，不是 QQ 号，也不保证用对方可见微信号能匹配。
5. 选择 **对方 / 指定群成员** 或 **自己（WeFlow 当前数据库账号）**。微信群先读取成员并选定具体成员；选择自己会按 WeFlow 的 `ownerId` 和 `isSend` 识别当前数据库账号，不要求手填自己的 wxid。
6. 设置起止时间和最大匹配条数，点击 **预览样本**，核对发送者与文本，再点击 **开始导出**。最大条数包含所选发送者的非文本消息；有效文本条数单独显示。
7. 到人格生成页点击 **生成 / 重新生成**，检查结构化分析和人格提示词，按需编辑，点击 **保存人格 JSON**。生成会调用 DeepSeek 并发送所选有效文本样本；读取/导出不会调用 DeepSeek。人格 JSON 按用户选择以明文保存。

导出中断后点击 **恢复上次中断**，沿用原会话、发送者、时间和数据库账号。改换发送者后应点击“开始导出”新建批次。切换 WeFlow 数据库账号后拒绝续传旧账号批次。

## 实现与限制

- 只使用官方 HTTP 读取接口：sessions、group-members、messages。Token 仅放请求头，不放 URL；设置超时，不记录原始响应或原文。
- 用 ChatLab 元数据读取 `ownerId`；用原始消息字段区分发送者。群成员 ID 同时兼容文档的 `wxid` 与当前源码的 `accountId`。
- 同一固定时间范围内使用 offset 分页，按消息 ID 去重；检测重复页/空页却有更多标记则显示 partial，不声称完整。恢复按已完成页续传。WeFlow 数据库重同步、删除或账号切换时，建议新建批次，避免 offset 因数据变化漂移。
- 会话键为 `weflow:<ownerId编码>:<talker编码>`，隔离微信账号、会话和 QQ 消息。不改旧表结构，不清空旧数据。
- 仅原生文本 `localType=1` 用于人格分析；图片、语音、表情等仅记标记，引用/转发/系统内容不纳入文本样本，避免第三方原文污染画像。
- 微信画像使用现有人格 JSON schema，`group_id` 为上述会话键、`member_id` 为微信发送者 ID，可保存/加载；微信会话键不能作为 QQ 部署目标。
- 聊天内容、原始消息段、昵称与批次请求在 SQLite 中加密，默认历史文件 `.jsonl.enc`。微信内部 ID 与现有 QQ 索引字段相同，以索引形式存储，不承诺全库每个字段均加密。
- 样本不足100条有效文本会提示 low confidence。WeFlow 只提供它已加载的数据库记录，不保证手机全部历史都在本机。

## 验证

`python -m pytest -q tests/test_weflow.py`：鉴权、错误信息脱敏、发送者过滤、分页、续传/换号拒绝、取消、重复页、账号隔离、设置兼容、人格分析/JSON导入导出、GUI路径。测试使用模拟接口，不读取真实微信或调用真实 DeepSeek。

接口依据：

- [WeFlow HTTP API 文档](https://github.com/hicccc77/WeFlow/blob/main/docs/HTTP-API.md)
- [WeFlow HTTP 实现](https://github.com/hicccc77/WeFlow/blob/main/electron/services/httpService.ts)

真实 WeFlow 数据库读取需在用户配置本机服务后联调。

构建验证：全量93项测试通过，WeFlow专项12项通过，正式单文件的离屏及原生Windows窗口启动自检通过（exit0）。界面布局已渲染检查。
