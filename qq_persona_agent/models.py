from dataclasses import dataclass
from .conversations import valid_key, is_private


@dataclass(frozen=True)
class ExportRequest:
    group_id: str
    user_id: str
    start_time: int
    end_time: int
    max_messages: int = 1000
    sender_scope: str = 'other'

    def validate(self):
        if not valid_key(self.group_id) or not self.user_id.isdigit():
            raise ValueError('群号/成员号必须是数字')
        if self.sender_scope not in ('other', 'self'):
            raise ValueError('发送者必须选择对方或自己')
        if not is_private(self.group_id) and self.sender_scope != 'other':
            raise ValueError('自己发送的记录选项仅适用于私聊')
        if is_private(self.group_id) and self.sender_scope == 'other' and self.group_id[8:] != self.user_id:
            raise ValueError('私聊导出对象必须与检索的 QQ 号一致')
        if self.start_time > self.end_time or self.start_time < 0:
            raise ValueError('时间范围无效')
        if not 1 <= self.max_messages <= 100000:
            raise ValueError('最大条数必须为 1~100000')
