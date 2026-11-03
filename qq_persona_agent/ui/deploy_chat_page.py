from datetime import datetime
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QCheckBox, QPlainTextEdit, QListWidget, QListWidgetItem, QLabel, QSplitter, QInputDialog
from ..chat_exporter import clean_message
from .common import button, row
from .contact_search import ContactSearch
from ..conversations import history


class DeployChatPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main, self.candidates = main, {}
        self.displayed_ids = set()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.chat_type = QComboBox()
        self.chat_type.addItems(['群聊', '个人私聊'])
        self.contact = ContactSearch(main)
        self.contact.hide()
        form.addRow('会话类型', self.chat_type)
        form.addRow('个人 QQ 检索', self.contact)
        self.group = QComboBox()
        self.trigger = QComboBox()
        for label, key in [('被 @（默认）', 'mention'), ('关键词', 'keyword'), ('自主判断（分析新群消息）', 'autonomous')]:
            self.trigger.addItem(label, key)
        self.keywords = QLineEdit()
        self.keywords.setPlaceholderText('关键词以英文逗号分隔')
        form.addRow('群聊目标', row(self.group, button('刷新群列表', lambda: main.export_page.groups()), button('读取最近消息', lambda: self.load_recent())))
        form.addRow('触发方式', row(self.trigger, button('应用到当前智能体', self.apply_trigger)))
        form.addRow('关键词', self.keywords)
        layout.addLayout(form)
        self.connection = QLabel('选择目标群后自动显示最近消息；启用后持续读取新消息。')
        self.activity = QLabel('默认仅被 @ 时生成候选；自主判断模式会分析新群消息。实际发送需批准或开启自主发送。')
        self.connection.setWordWrap(True)
        self.activity.setWordWrap(True)
        layout.addWidget(self.connection)
        layout.addWidget(self.activity)
        self.autonomous = QCheckBox('自主发送（默认关闭）')
        self.autonomous.clicked.connect(self.toggle_auto)
        self.status = QLabel('已停止')
        layout.addWidget(row(button('启用智能体（仅预览）', self.start), self.autonomous, button('暂停自主回复', self.pause_auto), self.status))
        self.messages, self.list = QPlainTextEdit(), QListWidget()
        self.messages.setReadOnly(True)
        self.messages.document().setMaximumBlockCount(2000)
        self.list.currentItemChanged.connect(self.select)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText('编辑选中候选，每行一条；批准后才发送。候选十分钟后失效。')
        self.sent = QPlainTextEdit()
        self.sent.setReadOnly(True)
        right = QWidget()
        r = QVBoxLayout(right)
        r.addWidget(self.list)
        r.addWidget(self.editor)
        r.addWidget(row(button('新建手动消息', self.manual), button('批准发送', self.approve), button('丢弃', self.discard)))
        r.addWidget(self.sent)
        splitter = QSplitter()
        splitter.addWidget(self.messages)
        splitter.addWidget(right)
        layout.addWidget(splitter)
        self.group.currentIndexChanged.connect(self.group_changed)
        self.chat_type.currentIndexChanged.connect(self.type_changed)
        self.contact.selected.connect(lambda _: self.group_changed())

    def target(self):
        if self.chat_type.currentIndex() == 1:
            try:
                return self.contact.key()
            except ValueError:
                return None
        return self.group.currentData()

    def type_changed(self, index):
        self.contact.setVisible(index == 1)
        self.group.setEnabled(index == 0)
        self.trigger.setItemText(0, '收到对方消息（默认）' if index == 1 else '被 @（默认）')
        self.connection.setText('请检索并确认私聊QQ号；启用后持续读取该会话。' if index == 1 else '选择目标群后读取最近消息；启用后持续接收。')
        self.activity.setText('私聊默认收到对方新消息就生成候选；实际发送需批准或开启自主发送。' if index == 1 else '群聊默认被 @ 时生成候选；实际发送需批准或开启自主发送。')
        self.group_changed()

    def group_changed(self, *_):
        self.messages.clear()
        self.displayed_ids.clear()
        runtime = self.main.services.runtime
        if runtime.status != 'stopped' and self.target() != runtime.group_id:
            runtime.emergency_stop()
            self.main.run(runtime.stop(), urgent=True)
        gid = self.target()
        QTimer.singleShot(200, lambda: self.load_recent(gid))

    def load_recent(self, expected_group=None):
        gid = self.target()
        if self.main.closing or not gid or (expected_group is not None and expected_group != gid):
            return
        if self.main.busy:
            QTimer.singleShot(200, lambda: self.load_recent(gid))
            return
        self.connection.setText('正在读取最近会话消息…')
        def show(rows):
            if self.target() != gid:
                return
            for event in sorted(rows, key=lambda m: int(m.get('time', 0))):
                r = clean_message(event)
                self.show_message({'message_id': r['message_id'], 'timestamp': r['timestamp'], 'nickname': r['sender_nickname'],
                                   'text': r['text'] or '[非文本消息]', 'historical': True})
            self.connection.setText(f'已读取最近 {len(rows)} 条；启用智能体后持续接收新消息。历史消息不会触发回复。')
        self.main.run(history(self.main.services.napcat, gid, count=30), show,
                      on_error=lambda: self.connection.setText('最近消息读取失败，请检查HTTP连接及该会话的历史访问权限'))

    def show_message(self, e):
        key = str(e.get('message_id', ''))
        if key and key in self.displayed_ids:
            return
        if key:
            self.displayed_ids.add(key)
        stamp = datetime.fromtimestamp(e['timestamp']).strftime('%H:%M:%S') if e.get('timestamp') else ''
        marker = '历史' if e.get('historical') else '实时'
        self.messages.appendPlainText(f"[{marker} {stamp}] {e['nickname']}: {e['text']}")

    def start(self):
        pid, gid = self.main.persona_page.persona_id, self.target()
        if not pid or not gid:
            return self.main.error('请先加载人格并选择目标群，或检索确认私聊 QQ 号')
        if not self.main.confirm('确认已预览人格、获得授权，并向会话参与者说明这是风格模拟？将监听当前选定会话，候选仍需人工批准。'):
            return
        self.main.persona_page.save()
        self.autonomous.setChecked(False)
        self.main.run(self.main.services.runtime.start(pid, gid, self.trigger.currentData(), self.keywords.text()))

    def apply_trigger(self):
        mode, keywords = self.trigger.currentData(), self.keywords.text()
        async def apply():
            self.main.services.runtime.set_trigger(mode, keywords)
        self.main.run(apply())

    def toggle_auto(self, checked):
        if checked and not self.main.confirm('启用后会向当前选定会话（群或个人）实际发送消息，无需逐条批准。确认已完成候选预览，并授权自主发送？'):
            self.autonomous.setChecked(False)
            return
        async def change():
            self.main.services.runtime.set_autonomous(checked)
        self.main.run(change(), on_error=lambda: self.autonomous.setChecked(False))

    def pause_auto(self):
        self.autonomous.setChecked(False)
        self.toggle_auto(False)

    def select(self, current, previous):
        if previous and previous.data(256) in self.candidates:
            self.candidates[previous.data(256)] = self.editor.toPlainText().splitlines()
        self.editor.setPlainText('\n'.join(self.candidates.get(current.data(256), [])) if current else '')

    def approve(self):
        item = self.list.currentItem()
        if item:
            texts = [t for t in self.editor.toPlainText().splitlines() if t.strip()]
            cid = item.data(256)
            self.main.run(self.main.services.runtime.approve(cid, texts), lambda _: self.remove(cid))

    def manual(self):
        text, ok = QInputDialog.getText(self, '新建手动消息（不调用模型）', '输入内容，建立候选后仍需批准发送：')
        if ok:
            async def create():
                self.main.services.runtime.manual_candidate(text)
            self.main.run(create())

    def discard(self):
        item = self.list.currentItem()
        if item:
            cid = item.data(256)
            async def discard():
                self.main.services.runtime.discard(cid)
            self.main.run(discard(), lambda _: self.remove(cid))

    def remove(self, cid):
        self.candidates.pop(cid, None)
        for i in range(self.list.count() - 1, -1, -1):
            if self.list.item(i).data(256) == cid:
                self.list.takeItem(i)

    def handle_event(self, e):
        kind = e['kind']
        if kind == 'status':
            self.status.setText({'stopped': '已停止', 'preview': '实时读取 · 人工审批', 'autonomous': '实时读取 · 自主发送'}.get(e['status'], e['status']))
            self.autonomous.setChecked(e['status'] == 'autonomous')
            if e['status'] == 'stopped':
                self.candidates.clear()
                self.list.clear()
                self.editor.clear()
                self.activity.setText('已停止监听和回复；仍可手动读取最近群聊。')
        elif kind == 'message':
            if not e.get('group_id') or e['group_id'] == self.target():
                self.show_message(e)
        elif kind == 'transport':
            self.connection.setText(e['message'])
        elif kind == 'activity':
            self.activity.setText(e['message'])
        elif kind == 'candidate':
            cid = e['candidate_id']
            self.candidates[cid] = e['replies']
            item = QListWidgetItem('待批准：' + ' / '.join(e['replies'])[:80])
            item.setData(256, cid)
            self.list.addItem(item)
        elif kind == 'sent':
            self.sent.appendPlainText('已发送：' + e['text'])
            self.remove(e['candidate_id'])
        elif kind in ('blocked', 'discarded'):
            self.remove(e['candidate_id'])
            if kind == 'blocked':
                self.sent.appendPlainText('已拦截：' + e['message'])
