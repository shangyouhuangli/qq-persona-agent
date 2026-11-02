# 2026-11-02 升级及整理

## NapCat

- 安装方式：现有QQ 9.9.18-32869 + LiteLoader Framework；保留现有QQ、账号和加载入口。
- 版本：4.7.5 → 官方4.18.42（2026-10-30发布）。
- 来源：https://github.com/NapNeko/NapCatQQ/releases/tag/v4.18.42 ，资产NapCat.Framework.zip。
- 通过镜像传输后，与GitHub官方API提供的SHA256严格校验一致：`118d66bb4849b7fcec05a4cafc9e33ed44f9236d56661f7097aba2ab3081df2e`。
- 路径：`D:/NapCat.32869.Framework/versions/9.9.18-32869/resources/app/LiteLoader/plugins/NapCat/`。
- 更新678个运行时文件；保留LiteLoader集成入口，manifest版本同步；官方napcat.mjs保持原样，没有再打历史补丁。
- 6个配置文件与升级前SHA256逐一一致；HTTP/WS、Token和账号配置保留。
- 正向WebSocket服务器在原配置中未设置，升级后仍未设置；程序默认WS地址3001的连接被拒绝。这不影响HTTP导出；实时聊天部署前需要按README新增正向WS服务器。此次未擅自修改原网络配置。
- 已重启该安装目录的NapCat/QQ；未操作另一套`D:/QQ.exe`个人QQ实例。
- 真实HTTP报告4.18.42、账号在线。历史第一页97条、第二页97条，其中96条为新增记录，最早时间向前推进。未向QQ发送消息或启用智能体。
- 最终程序38项测试、隔离PATH的离屏/原生Windows窗口自检通过；正式exe校验和、根目录快捷方式和MCP入口路径已核对。

## 项目整理

- `dist/`仅保留`QQPersonaAgent.exe`和`SHA256SUMS.txt`；最新版修复已合并到正式文件名。
- 根目录`启动QQ人格智能体.lnk`指向唯一exe。
- 用户保存的`dist/persona.json`移至`exports/persona.json`，内容保留。
- 旧exe、旧校验文件、临时修复脚本和旧维护材料已归档到项目外。
- 可重建的build、测试缓存、截图/临时日志移至项目外维护目录的generated子目录；保留源码、测试、文档、Skill/MCP、Python环境和UPX。删除命令被自动审批拦截后采用归档，不强制删除。
- build.spec统一输出正式名称，后续构建不会产生fixed并列版本。

## 备份

目录：`%LOCALAPPDATA%/QQPersonaAgentMaintenance/20261102-upgrade/`。

- `NapCat-4.7.5-before-upgrade.zip.dpapi`：原插件完整备份，包含原配置，已用当前Windows用户DPAPI加密并验证解密一致性。还原需要原用户/机器；退出NapCat后可解密恢复。
- `project-before-cleanup.zip`：原程序、临时脚本及维护材料。
- `NapCat.Framework-4.18.42-verified.zip`：校验通过的官方包。

业务数据库和聊天记录仍在`%LOCALAPPDATA%/QQPersonaAgent/`，没有清除或重建。此次没有消耗DeepSeek调用额度，也没有执行真实消息发送测试。
