# 历史分页问题记录（已通过升级解决）

NapCat 4.7.5 的历史接口没有将方向参数传到底层，只反转返回顺序。本机连续两页都是97条，第二页新增0条，导致35条成员消息后标记partial。原界面用“匹配条数/上限”显示3%，也容易误解为历史读取百分比。

程序侧已合并修复：请求明确向更早方向查询、优先使用短消息ID作分页锚点、旧partial批次重新遍历去重、改用扫描状态代替虚假的完成百分比。

2026-11-02 已将本机NapCat从4.7.5升级到官方4.18.42。真实HTTP返回4.18.42、账号在线；历史第一页97条，第二页97条，其中96条为新增记录，最早时间向前推进。分页问题已复验通过。

现在直接运行 dist/QQPersonaAgent.exe 或根目录启动快捷方式，点击“恢复上次中断”。已有记录和配置保留。无需再运行旧补丁脚本；脚本及旧exe已移到项目外备份，详见MAINTENANCE.md。

参考：https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-onebot/action/go-cqhttp/GetGroupMsgHistory.ts
