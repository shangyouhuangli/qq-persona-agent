from dataclasses import dataclass


@dataclass(frozen=True)
class ExportRequest:
    group_id: str
    user_id: str
    start_time: int
    end_time: int
    max_messages: int = 1000

    def validate(self):
        if not self.group_id.isdigit() or not self.user_id.isdigit():
            raise ValueError('群号/成员号必须是数字')
        if self.start_time > self.end_time or self.start_time < 0:
            raise ValueError('时间范围无效')
        if not 1 <= self.max_messages <= 100000:
            raise ValueError('最大条数必须为 1~100000')
