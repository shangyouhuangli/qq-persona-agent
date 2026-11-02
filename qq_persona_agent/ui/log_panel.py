import json
from pathlib import Path
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QTextEdit, QFileDialog
from ..logging_utils import log
from .common import button, row


class LogPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.filter = QComboBox()
        self.filter.addItems(['全部', '只看错误', '只看 LLM', '只看消息发送'])
        self.filter.currentIndexChanged.connect(self.reload)
        layout.addWidget(row(self.filter, button('导出脱敏日志', self.export)))
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.document().setMaximumBlockCount(2000)
        layout.addWidget(self.text)

    def add(self, record):
        i = self.filter.currentIndex()
        if (i == 1 and record['level'] != 'ERROR') or (i == 2 and record['category'] != 'llm') or (i == 3 and record['category'] != 'send'):
            return
        self.text.setTextColor(QColor({'ERROR': '#ff7070', 'WARNING': '#e8ad52'}.get(record['level'], '#b3d7ef')))
        self.text.moveCursor(QTextCursor.MoveOperation.End)
        self.text.insertPlainText(log.redact(json.dumps(record, ensure_ascii=False)) + '\n')

    def reload(self, *_):
        self.text.clear()
        for record in list(log.records):
            self.add(record)

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, '导出脱敏日志', 'qq-persona.log', '日志 (*.log)')
        if path:
            try:
                log.export(Path(path))
            except OSError:
                pass
