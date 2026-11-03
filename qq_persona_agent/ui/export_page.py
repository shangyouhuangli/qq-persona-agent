from datetime import datetime
from pathlib import Path
import json
import threading
from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QDateTimeEdit, QPlainTextEdit, QProgressBar, QLabel
from ..models import ExportRequest
from .common import button, row, spin
from .contact_search import ContactSearch
from .weflow_source import WeFlowSource
from ..weflow_exporter import WeFlowExportRequest


class ExportPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main, self.batch_id, self.cancel = main, None, threading.Event()
        layout = QVBoxLayout(self)
        form = self.form = QFormLayout()
        self.chat_type = QComboBox()
        self.chat_type.addItems(['QQ 群成员记录', 'QQ 个人私聊记录', '微信记录（WeFlow）'])
        self.contact = ContactSearch(main)
        self.contact.hide()
        form.addRow('记录类型', self.chat_type)
        form.addRow('私聊 QQ 检索', self.contact)
        self.sender_scope = QComboBox()
        self.sender_scope.addItem('对方发送的消息', 'other')
        self.sender_scope.addItem('自己发送的消息（NapCat 当前登录账号）', 'self')
        self.sender_scope.hide()
        form.addRow('提取谁的消息', self.sender_scope)
        self.weflow_source = WeFlowSource(main)
        self.weflow_source.hide()
        form.addRow(self.weflow_source)
        self.chat_type.currentIndexChanged.connect(self.type_changed)
        self.group, self.member = QComboBox(), QComboBox()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText('昵称模糊过滤，仍需在下拉框人工选中成员')
        self.members = []
        self.filter.textChanged.connect(self.filter_members)
        self.start, self.end = QDateTimeEdit(), QDateTimeEdit()
        for c in (self.start, self.end):
            c.setCalendarPopup(True)
            c.setDisplayFormat('yyyy-MM-dd HH:mm:ss')
        self.start.setDateTime(QDateTime.currentDateTime().addDays(-30))
        self.end.setDateTime(QDateTime.currentDateTime())
        self.maximum = spin(1000, minimum=1)
        self.qq_rows = []
        for label, w in [('群', row(self.group, button('刷新群', self.groups))), ('成员', row(self.member, button('刷新成员', self.load_members))), ('昵称过滤', self.filter), ('开始（本机时间）', self.start), ('结束（本机时间）', self.end), ('最大成员消息条数', self.maximum)]:
            form.addRow(label, w)
            if label in ('群', '成员', '昵称过滤'):
                self.qq_rows.append(w)
        layout.addLayout(form)
        self.group.currentIndexChanged.connect(self.load_members)
        layout.addWidget(row(button('预览样本（最多20条）', self.preview), button('开始导出', self.export), button('恢复上次中断', lambda: self.export(True)), button('取消导出', self.cancel.set)))
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.summary = QLabel('请先预览，确认选中的成员与时间范围。')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.samples = QPlainTextEdit()
        self.samples.setReadOnly(True)
        layout.addWidget(self.samples)
        last = main.services.db.one('SELECT id FROM export_batches ORDER BY updated_at DESC LIMIT 1')
        if last:
            self.batch_id = last['id']
        self.type_changed(0)

    def groups(self):
        self.main.run(self.main.services.napcat.get_group_list(), self.show_groups)

    def type_changed(self, index):
        self.form.setRowVisible(self.contact, index == 1)
        self.form.setRowVisible(self.sender_scope, index == 1)
        self.form.setRowVisible(self.weflow_source, index == 2)
        for widget in self.qq_rows:
            self.form.setRowVisible(widget, index == 0)
        for widget in (self.group, self.member, self.filter):
            widget.setEnabled(index == 0)

    def show_groups(self, groups):
        self.group.blockSignals(True)
        self.group.clear()
        self.main.deploy_page.group.clear()
        for g in groups:
            label = f"{g.get('group_name', '')} ({g['group_id']})"
            self.group.addItem(label, str(g['group_id']))
            self.main.deploy_page.group.addItem(label, str(g['group_id']))
        self.group.blockSignals(False)
        self.load_members()

    def load_members(self, *_):
        if self.chat_type.currentIndex() != 0:
            return
        gid = self.group.currentData()
        if gid:
            self.main.run(self.main.services.napcat.get_group_member_list(gid), self.show_members)

    def show_members(self, members):
        self.members = members
        self.filter_members()

    def filter_members(self, *_):
        self.member.clear()
        query = self.filter.text().casefold()
        for m in self.members:
            name = m.get('card') or m.get('nickname') or ''
            if query in name.casefold():
                self.member.addItem(f"{name} ({m['user_id']})", str(m['user_id']))

    def request(self):
        if self.chat_type.currentIndex() == 2:
            return self.weflow_source.request(self.start.dateTime().toSecsSinceEpoch(), self.end.dateTime().toSecsSinceEpoch(), self.maximum.value())
        private = self.chat_type.currentIndex() == 1
        key = self.contact.key() if private else str(self.group.currentData() or '')
        user = self.contact.contact['user_id'] if private else str(self.member.currentData() or '')
        req = ExportRequest(key, user, self.start.dateTime().toSecsSinceEpoch(), self.end.dateTime().toSecsSinceEpoch(), self.maximum.value(),
                            self.sender_scope.currentData() if private else 'other')
        req.validate()
        return req

    def preview(self):
        try:
            req = self.request()
            exporter = self.main.services.weflow_exporter if isinstance(req, WeFlowExportRequest) else self.main.services.exporter
            self.main.run(exporter.preview(req), lambda rows: self.samples.setPlainText('\n'.join(f"{datetime.fromtimestamp(r['timestamp'])} {r['sender_nickname']}: {r['text']}" for r in rows)))
        except ValueError as e:
            self.main.error(str(e))

    def export(self, resume=False):
        try:
            if resume and self.batch_id:
                batch = self.main.services.db.one('SELECT request_json FROM export_batches WHERE id=?', (self.batch_id,))
                spec = json.loads(self.main.services.db.unpack(batch['request_json']))
                spec.pop('owner_id', None)
                req = WeFlowExportRequest(**spec) if spec.get('source') == 'weflow' else ExportRequest(**spec)
            else:
                req = self.request()
            self.cancel.clear()
            self.progress.setRange(0, 0)
            exporter = self.main.services.weflow_exporter if isinstance(req, WeFlowExportRequest) else self.main.services.exporter
            self.main.run(exporter.export(req, self.batch_id if resume else None,
                progress=lambda p: self.main.bridge.event.emit({'kind': 'export_progress', **p}), cancel=self.cancel), self.exported)
        except ValueError as e:
            self.main.error(str(e))

    def exported(self, result):
        self.batch_id = result['batch_id']
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if result['status'] == 'complete' else 0)
        self.progress.setFormat('已结束' if result['status'] == 'complete' else '未完整获取历史')
        self.summary.setText(f"{result['summary']}；累计扫描 {result['scanned']} 条会话消息；状态 {result['status']}；{result['reason_detail']}；low_sample={result['low_sample']}")
        self.main.persona_page.warning.setText('样本不足，建议增加导出条数或时间范围' if result['low_sample'] else '')
        self.main.persona_page.batch.setText(self.batch_id)
        path = self.main.services.db.path.parent / f'history-{self.batch_id}.jsonl.enc'
        async def save():
            self.main.services.exporter.save_encrypted_jsonl(self.batch_id, path)
        self.main.run(save())
