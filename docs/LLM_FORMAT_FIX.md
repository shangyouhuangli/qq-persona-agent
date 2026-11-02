# JSON响应异常导致停机的修复

日志中 input_tokens/output_tokens 非零且延迟正常，说明请求曾取得模型响应，但 json_parse_ok=false。旧日志把空白、截断、JSON顶层不是对象等合并为LLMError，仅凭旧记录不能进一步确定具体是哪一种。连接测试原本只要求普通文本OK，也无法保证聊天所需JSON对象有效。

DeepSeek官方说明JSON模式可能返回空白，即使finish_reason=stop：https://api-docs.deepseek.com/guides/json_mode/

修改：
- 细分 empty_content / output_truncated / invalid_json / json_not_object / missing_choice；记录finish_reason、response_chars、retry_attempt，原文和凭据不落日志。
- 格式异常最多重新调用一次；不将任意普通文本转换为可发送回复，只容忍包住整个合法JSON对象的Markdown围栏。
- 聊天响应结构仍要求boolean should_reply和字符串数组replies，错误结构不发送。
- 重试后仍错误，本轮跳过，队列继续处理后续消息；自主模式连续3轮格式异常回到人工审批，保留群聊读取。
- 认证和其他请求故障仍暂停；发送失败仍暂停且绝不自动重发。
- 提示词明确人格风格仅作用于replies字符串，JSON为内部协议；给出“回复”和“不回复”两个完整示例。
- 连接测试改为同时验证JSON输出，避免普通文本OK造成误判。

验证：53项测试通过，包含空白后重试成功、格式异常的准确分类及调用次数上限、字段错误不发送、恢复后继续处理下一条、连续异常降级和认证错误仍停止。

额外使用本机保存的API配置发送一次纯合成测试场景，JSON协议校验通过（68 input / 15 output tokens）；没有上传群聊或向QQ发送消息。新版exe离屏与原生Windows启动测试均通过，正式文件名保持QQPersonaAgent.exe，旧版本仅保存在项目外维护目录。
