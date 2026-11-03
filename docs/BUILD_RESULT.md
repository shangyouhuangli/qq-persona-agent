# 最终构建结果

日期：2026-11-03；构建主机 Windows 11 x64，Python 3.12.4。

- 产物：`dist/QQPersonaAgent.exe`
- 大小：46,460,822 bytes（约44.31 MiB）
- SHA256：`f469a9bb066af4b1a1a80de40b9c872b041c7bfb9d4256ad200296f5ff7fd015`
- PyInstaller 6.22.3，onefile / windowed，PE Subsystem=2（WINDOWS_GUI）。
- UPX 4.2.4 官方 Windows 版本；`upx=True`。Qt/Python DLL 和 CFG 保护二进制排除压缩，保留正常加载。
- PySide6 Essentials 6.8.3（QtWidgets）。platforms 插件显式收集。
- 自动测试：81 passed，新增短句长度、连发及冷却期间零回复调用、旧队列不补答、格式重试门禁测试。
- Skill：通过官方 skill-creator `quick_validate.py`，使用 `python -X utf8` 运行。
- Codex TOML 与 Claude Code JSON 示例已解析验证，入口路径存在。
- 源码 GUI 离线/原生启动通过；五页布局已渲染并检查，中文显示正常。
- 最终 exe：从独立临时工作目录启动，删除 PYTHONPATH/PYTHONHOME/VIRTUAL_ENV/Qt 插件变量，PATH 仅 System32，`--smoke-test` 和 `--native-smoke-test` 均 exit 0。
- exe 自检覆盖 DPAPI 设置读写、五页创建、日志、停止按钮，以及 NapCat/DeepSeek 的 MockTransport 连接路径；无真实 API 调用或 QQ 发送。

这验证了本机隔离环境可启动，不等于清洁 Windows 10/11 系统实机验收。NapCat已升级至4.18.42，并通过真实HTTP登录和向前历史分页验证；DeepSeek及真实发送仍需按ACCEPTANCE.md验收。

默认不启用监听或发送；没有自动替用户配置 NapCat、保存真实凭据、修改 Agent 全局配置或安装全局 Skill。

后续维护：用户已授权升级现有NapCat；升级、备份及整理见MAINTENANCE.md。正式程序统一为QQPersonaAgent.exe，不再保留fixed等并列版本。

JSON可靠性更新见LLM_FORMAT_FIX.md；已对最终exe再次完成隔离PATH的离屏及原生Windows窗口启动自检。旧exe和构建缓存放在项目外QQPersonaAgentMaintenance/20261102-llm-format目录。

2026-11-03短句与调用前冷却更新见SHORT_REPLIES.md；新版exe通过离屏和原生Windows启动自检，备份与构建缓存在QQPersonaAgentMaintenance/20261103-short-replies目录。

2026-11-03：参数页新增最大回复字符数及短/中/长权重、归一化概率提示。旧配置兼容、参数持久化及大于10字生成发送验证通过；新版单文件离屏/原生Windows启动自检通过。

个人私聊版：77项测试通过，exe离屏及原生Windows启动通过。按QQ号检索、私聊历史导出和个人消息审批已接入，说明见PRIVATE_CHAT.md；真实私聊联调待NapCat运行后执行。

自己私聊记录更新：可选自己或对方发送的记录，81项测试通过。新版exe已通过隔离环境离屏和原生窗口自检，两个exit均0；已替换正式exe并更新SHA256SUMS。旧exe及构建缓存位于QQPersonaAgentMaintenance/20261103-private-own。未执行真实QQ历史读取或发送。
