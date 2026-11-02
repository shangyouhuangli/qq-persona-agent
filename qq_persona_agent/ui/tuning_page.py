from dataclasses import fields
from PySide6.QtWidgets import QWidget, QFormLayout, QVBoxLayout, QLabel, QLineEdit, QCheckBox, QScrollArea
from ..config import Tuning
from .common import button, row, spin

LABELS = ['识别：最近群消息条数', '识别：token 预算', '短期：保留轮数', '中期：检索 top-k', '记忆：人格+锁定块+长期 token 预算', '空闲反思间隔（分钟）', '批量反思消息数', '最大连续回复（1~3）', '最小回复间隔（秒）', '随机延迟下限（秒）', '随机延迟上限（秒）', '连发后冷却（秒）', '相同内容去重窗口（秒）', '读取失败重试次数（发送不重试）', '分析单条最大字符数', '分析总 token 预算', '允许主动发起话题', '敏感词（英文逗号分隔）', '分析表情使用习惯']


class TuningPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main, self.controls = main, {}
        layout = QVBoxLayout(self)
        self.lock_info = QLabel('人格锁定块成本：加载或生成人格后显示。Token 使用 UTF-8 字节保守上界估算。')
        self.lock_info.setWordWrap(True)
        layout.addWidget(self.lock_info)
        content, form = QWidget(), QFormLayout()
        content.setLayout(form)
        for f, label in zip(fields(Tuning), LABELS):
            val = getattr(main.services.tuning, f.name)
            if isinstance(val, bool):
                control = QCheckBox()
                control.setChecked(val)
            elif isinstance(val, str):
                control = QLineEdit(val)
            else:
                control = spin(val, floating=isinstance(val, float))
            self.controls[f.name] = control
            form.addRow(label, control)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        layout.addWidget(QLabel('主动发起仅允许空闲时生成候选；是否发送仍由自主发送授权控制。参数保存会停止当前智能体。'))
        layout.addWidget(row(button('保存参数', self.save), button('恢复默认', self.defaults)))

    def value(self):
        return Tuning(**{k: w.isChecked() if isinstance(w, QCheckBox) else w.text() if isinstance(w, QLineEdit) else w.value() for k, w in self.controls.items()})

    def save(self):
        try:
            tuning = self.value()
            tuning.validate()
            self.main.run(self.main.services.configure(self.main.services.settings, tuning))
        except ValueError as e:
            self.main.error(str(e))

    def defaults(self):
        for k, w in self.controls.items():
            v = getattr(Tuning(), k)
            if isinstance(w, QCheckBox):
                w.setChecked(v)
            elif isinstance(w, QLineEdit):
                w.setText(v)
            else:
                w.setValue(v)
