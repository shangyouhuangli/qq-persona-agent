from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit, QComboBox, QLabel
from .common import row, button
from ..weflow_exporter import WeFlowExportRequest


class WeFlowSource(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main, self.confirmed = main, None
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        self.query = QLineEdit()
        self.query.setPlaceholderText('微信会话名称或 wxid；检索后人工选择')
        self.sessions, self.sender, self.scope = QComboBox(), QComboBox(), QComboBox()
        self.scope.addItem('对方 / 指定群成员', 'other')
        self.scope.addItem('自己（WeFlow 当前数据库账号）', 'self')
        self.info = QLabel('先在设置页保存 WeFlow 地址与 Token；这里只读取记录并生成人格。')
        self.info.setWordWrap(True)
        form.addRow('微信会话检索', row(self.query, button('检索会话', self.search)))
        form.addRow('会话', row(self.sessions, button('确认会话 / 读取成员', self.confirm_session)))
        form.addRow('提取谁的消息', row(self.scope, self.sender))
        form.addRow(self.info)
        self.sessions.currentIndexChanged.connect(self.invalidate)
        self.query.textChanged.connect(self.invalidate)
        self.scope.currentIndexChanged.connect(lambda: self.sender.setEnabled(self.scope.currentData() == 'other'))

    def invalidate(self, *_):
        self.confirmed = None
        self.sender.clear()
        self.info.setText('会话已变更，请确认会话；最多显示1000个匹配项，可缩小检索范围。')

    def search(self):
        query = self.query.text().strip()
        def show(rows):
            if self.query.text().strip() != query:
                return
            self.sessions.clear()
            for r in rows:
                uid = r['username']
                self.sessions.addItem(f"{r.get('displayName') or uid} ({uid})", uid)
            self.info.setText(f'匹配 {len(rows)} 个会话，请选择并确认。最多显示1000项。')
        self.main.run(self.main.services.weflow.sessions(query), show)

    def confirm_session(self):
        talker = self.sessions.currentData()
        if not talker:
            return self.main.error('请先检索并选择微信会话')
        if not self.main.confirm('确认读取此微信会话？\n' + self.sessions.currentText()):
            return
        self.confirmed = talker
        self.sender.clear()
        if talker.endswith('@chatroom'):
            def loaded(rows):
                if self.confirmed != talker:
                    return
                for r in rows:
                    # Official implementation uses accountId; some versions return wxid.
                    uid = r.get('accountId') or r.get('wxid')
                    if uid:
                        name = r.get('groupNickname') or r.get('displayName') or r.get('nickname') or uid
                        self.sender.addItem(f'{name} ({uid})', uid)
                self.info.setText('已确认微信群；选择成员或自己，设置范围后预览。')
            self.main.run(self.main.services.weflow.members(talker), loaded)
        else:
            self.sender.addItem(self.sessions.currentText(), talker)
            self.info.setText('已确认微信私聊；选择对方或自己，设置范围后预览。')

    def request(self, start, end, maximum):
        if not self.confirmed or self.confirmed != self.sessions.currentData():
            raise ValueError('请先检索并确认微信会话')
        sender = '__self__' if self.scope.currentData() == 'self' else self.sender.currentData()
        req = WeFlowExportRequest(self.confirmed, sender or '', start, end, maximum)
        req.validate()
        return req
