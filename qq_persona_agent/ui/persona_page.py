import json
from pathlib import Path
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QComboBox, QPlainTextEdit, QLabel, QSplitter, QFileDialog
from ..persona_analyzer import lock_block, token_estimate
from .common import button, row


class PersonaPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main, self.persona_id = main, None
        layout = QVBoxLayout(self)
        self.batch = QLineEdit()
        self.batch.setPlaceholderText('导出批次 ID，导出完成后自动填入')
        layout.addWidget(row(self.batch, button('生成 / 重新生成', self.generate)))
        self.history = QComboBox()
        layout.addWidget(row(self.history, button('刷新历史', self.refresh), button('加载历史人格', self.load_history), button('加载人格 JSON', self.import_file)))
        self.warning = QLabel()
        self.warning.setStyleSheet('color:#ffb454;font-weight:bold')
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)
        self.summary = QLabel('生成后预览并编辑，再保存。不会自动监听群消息。')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        layout.addWidget(button('折叠 / 展开结构化 JSON', lambda: self.analysis.setVisible(not self.analysis.isVisible())))
        self.analysis, self.prompt = QPlainTextEdit(), QPlainTextEdit()
        self.analysis.setReadOnly(True)
        self.prompt.setPlaceholderText('可编辑的四层人格提示词')
        splitter = QSplitter()
        splitter.addWidget(self.analysis)
        splitter.addWidget(self.prompt)
        layout.addWidget(splitter)
        layout.addWidget(row(button('保存编辑到数据库', self.save), button('保存人格 JSON', self.export_file)))
        self.refresh()

    def refresh(self):
        self.history.clear()
        for p in self.main.services.db.all('SELECT id,sample_count,confidence FROM personas ORDER BY id DESC'):
            self.history.addItem(f"#{p['id']} 样本 {p['sample_count']} / {p['confidence']}", p['id'])

    def generate(self):
        if not self.batch.text().strip():
            return self.main.error('请先导出聊天记录')
        self.main.run(self.main.services.analyzer.analyze(self.batch.text().strip()), self.show_persona)

    def show_persona(self, p):
        self.persona_id = p['id']
        self.analysis.setPlainText(json.dumps(p['structured_analysis_json'], ensure_ascii=False, indent=2))
        self.prompt.setPlainText(p['persona_prompt'])
        self.summary.setText(f"人格 #{p['id']}；confidence={p['confidence']}\n" + p['structured_analysis_json'].get('summary', ''))
        self.warning.setText('样本不足或实际分析样本不足，建议增加导出条数或时间范围' if p['confidence'] == 'low' else '')
        self.main.tuning_page.lock_info.setText(f"人格锁定块预算上界：{token_estimate(lock_block(p['member_nickname']))} token；整个人格：{token_estimate(p['persona_prompt'])} token（UTF-8 字节保守估算）")
        self.refresh()

    def load_history(self):
        if self.history.currentData():
            self.show_persona(self.main.services.db.persona(self.history.currentData()))

    def save(self):
        if not self.persona_id:
            return self.main.error('请先生成人格或加载历史')
        try:
            self.show_persona(self.main.services.save_edited_persona(self.persona_id, self.prompt.toPlainText()))
        except ValueError as e:
            self.main.error(str(e))

    def export_file(self):
        if not self.persona_id:
            return self.main.error('请先选择人格')
        if not self.main.confirm('人格 JSON 含画像和提示词，将以明文保存。确认导出？'):
            return
        path, _ = QFileDialog.getSaveFileName(self, '保存人格', 'persona.json', 'JSON (*.json)')
        if path:
            self.save()
            try:
                self.main.services.export_persona(self.persona_id, Path(path))
            except OSError:
                self.main.error('无法写入人格文件，请检查目录权限')

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, '加载人格', '', 'JSON (*.json)')
        if path:
            try:
                self.show_persona(self.main.services.import_persona(Path(path)))
            except Exception:
                self.main.error('人格文件格式错误或不可读')
