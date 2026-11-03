from dataclasses import fields
from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit, QSpinBox, QLabel
from ..config import Settings
from .common import button, row


class SettingsPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main, self.controls = main, {}
        layout = QFormLayout(self)
        labels = ['DeepSeek API Key', 'DeepSeek Base URL', '模型', 'NapCat HTTP', 'NapCat Token', 'NapCat WebSocket', '全局代理', '请求超时（秒）', 'WeFlow HTTP', 'WeFlow API Token']
        for f, label in zip(fields(Settings), labels):
            if f.name == 'timeout':
                w = QSpinBox()
                w.setRange(1, 300)
            else:
                w = QLineEdit()
                if f.name in ('api_key', 'napcat_token', 'weflow_token'):
                    w.setEchoMode(QLineEdit.EchoMode.Password)
            self.controls[f.name] = w
            layout.addRow(label, w)
        self.load(main.services.settings)
        layout.addRow(row(button('保存设置', self.save), button('测试 DeepSeek', lambda: self.test('llm')), button('测试 NapCat', lambda: self.test('napcat'))))
        layout.addRow(button('测试 WeFlow（微信记录读取）', lambda: self.test('weflow')))
        layout.addRow(button('一键清除本地数据', main.clear_data))
        layout.addRow(QLabel('配置由当前 Windows 用户 DPAPI 加密。测试前请保存设置。\n保存设置会停止智能体；不会自动启用发送。'))
        self.result = QLabel()
        self.result.setWordWrap(True)
        layout.addRow(self.result)

    def load(self, settings):
        for key, control in self.controls.items():
            control.setValue(settings.timeout) if key == 'timeout' else control.setText(getattr(settings, key))

    def value(self):
        return Settings(**{k: w.value() if k == 'timeout' else w.text().strip() for k, w in self.controls.items()})

    def save(self):
        try:
            s = self.value()
            s.validate()
            self.main.run(self.main.services.configure(s), lambda r: self.result.setText(r['summary']))
        except ValueError as e:
            self.main.error(str(e))

    def test(self, target):
        self.main.run(getattr(self.main.services, target).test_connection(), lambda r: self.result.setText(r['reason']))
