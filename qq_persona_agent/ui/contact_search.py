from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QLabel
from ..conversations import private_key
from .common import row, button


class ContactSearch(QWidget):
    selected = Signal(object)

    def __init__(self, main):
        super().__init__()
        self.main, self.contact = main, None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.number = QLineEdit()
        self.number.setPlaceholderText('输入完整 QQ 号精确检索，不自动发送消息')
        self.number.textChanged.connect(self.invalidate)
        self.number.returnPressed.connect(self.search)
        layout.addWidget(row(self.number, button('按 QQ 号检索', self.search)))
        self.result = QLabel('请先检索并确认昵称及 QQ 号。')
        self.result.setWordWrap(True)
        layout.addWidget(self.result)

    def invalidate(self, *_):
        self.contact = None
        self.result.setText('QQ 号已更改，请重新检索。')
        self.selected.emit(None)

    def search(self):
        try:
            uid = private_key(self.number.text().strip())[8:]
        except ValueError as e:
            self.main.error(str(e))
            return
        self.main.run(self.main.services.napcat.find_contact(uid), lambda c: self.set_contact(c, uid))

    def set_contact(self, contact, requested):
        if self.number.text().strip() != requested:
            return
        label = f"{contact['nickname']} · QQ {contact['user_id']} · " + ('好友' if contact['is_friend'] else '非好友：历史和发送可能不可用')
        if not self.main.confirm('确认选择此私聊对象？\n' + label):
            return
        self.contact = contact
        self.result.setText(label)
        self.selected.emit(contact)

    def key(self):
        if not self.contact or self.contact['user_id'] != self.number.text().strip():
            raise ValueError('请先输入 QQ 号，检索并确认私聊对象')
        return private_key(self.contact['user_id'])
