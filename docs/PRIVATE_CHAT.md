# 个人私聊接入

数据导出页：切换“个人私聊记录” → 输入完整QQ号 → 按QQ号检索 → 核对昵称/QQ号/好友状态并确认 → 选择“提取谁的消息”：对方或自己 → 选择范围 → 预览/导出。选择自己时通过get_login_info读取NapCat当前登录QQ，私聊对象仍是检索的QQ号。人格样本只使用所选发送者，默认加密保存；不会混合双方风格。

部署页：加载人格 → 切换“个人私聊” → 同样检索并确认QQ号 → 读取最近私聊 → 启用预览。默认触发在私聊中表示收到对方新消息即可分析，无需@。关键词/自主判断也可用，发送仍遵循人工审批或显式自主发送授权。

主动私信：先启用预览确认目标，点击“新建手动消息”，输入内容创建候选，再批准发送。该操作不调用模型；即使开启自主发送，手动消息仍需单独批准。

好友查询使用get_friend_list精确比对QQ号，未匹配时调用get_stranger_info。查到资料不代表能访问记录或发送；不自动添加好友或绕过QQ权限。历史通过get_friend_msg_history，发送通过send_private_msg，生成文本用text段防CQ注入。

群与私聊共用导出、分析、记忆、风控、冷却/长度权重以及停止逻辑。为兼容旧SQLite，已有group_id列在私聊记录中保存private:QQ号会话键；群仍保存纯数字。联合唯一键可隔离同号群、同号QQ以及相同message_id；历史导出JSONL也含conversation_key。无需清空/重建数据库。导入私聊画像允许该会话键。

同一实例只运行一个会话。修改私聊QQ号、切换目标或模式会停止旧会话，使原候选失效。WS仅按private事件和目标QQ匹配；群消息不会进入私聊。HTTP补读私聊历史并与WS去重，旧消息不触发回复或/stop。对方新发/stop与顶栏停止有效。

新增MCP工具：find_private_contact、export_private_history（preview_only=true）、deploy_private_persona_agent（dry_run=true）；分析与停止复用原工具。Skill中记录了私聊检索和授权步骤。

验收：接口Mock验证精确QQ匹配、私聊参数、文本段发送、私聊导出过滤机器人自身消息、群私隔离、人工候选/批准、主动消息不调用模型、目标更改失效及dry-run不连接。真实私聊读取/发送尚未验证：本次联调时NapCat HTTP未运行，没有真实发送或调用DeepSeek。

参考：
- https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-onebot/action/go-cqhttp/GetFriendMsgHistory.ts
- https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-onebot/action/msg/SendPrivateMsg.ts

最终结果：77项自动测试通过，包含私聊HTTP轮询、WS事件接收与去重、同号群/个人消息ID隔离、私聊发送失败停止且不回退到群发送。新版单文件通过隔离PATH的离屏和原生Windows窗口启动自检。项目仅保留dist/QQPersonaAgent.exe，旧文件及构建缓存位于项目外QQPersonaAgentMaintenance/20261103-private-chat目录。

自己记录更新：81项测试通过，覆盖自己的预览/导出/人格归属、登录账号获取失败、切换账号拒绝恢复错误批次、旧批次兼容。MCP export_private_history增加sender_scope（other默认，self为自己）。已有批次恢复沿用原发送者选择；切换选择后请点击开始导出创建新批次。
