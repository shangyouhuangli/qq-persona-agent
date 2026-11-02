import os
import pytest


def test_five_pages_stop_settings_and_log(tmp_path):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtWidgets import QApplication
    from qq_persona_agent.app_gui import MainWindow
    from qq_persona_agent.logging_utils import log
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path / 'gui.db')
    window.show()
    app.processEvents()
    assert window.tabs.count() == 5 and window.stop_button.isVisible()
    assert not window.deploy_page.autonomous.isChecked()
    window.logs.add({'time': 'now', 'level': 'ERROR', 'category': 'send', 'message': '失败'})
    assert '失败' in window.logs.text.toPlainText()
    window.stop_button.click()
    for _ in range(10):
        app.processEvents()
    assert window.services.runtime.stop_flag.is_set()
    window.close()


def test_recent_chat_auto_load_and_event_display(tmp_path):
    import time
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtWidgets import QApplication
    from qq_persona_agent.app_gui import MainWindow
    from conftest import message
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path / 'gui.db')
    calls = []
    async def history(group_id, message_seq=None, count=100):
        calls.append(group_id)
        return [message('h1', 20, '最近群聊样本')]
    window.services.napcat.get_group_msg_history = history
    page = window.deploy_page
    page.group.addItem('测试群', '234567890')
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not calls:
        app.processEvents()
        time.sleep(.01)
    for _ in range(30):
        app.processEvents()
        time.sleep(.005)
    assert calls == ['234567890']
    assert '最近群聊样本' in page.messages.toPlainText()
    page.handle_event({'kind': 'message', 'group_id': '234567890', 'message_id': 'live', 'timestamp': 21, 'nickname': '群友', 'text': '实时消息'})
    page.handle_event({'kind': 'message', 'group_id': '234567890', 'message_id': 'live', 'timestamp': 21, 'nickname': '群友', 'text': '实时消息'})
    assert page.messages.toPlainText().count('实时消息') == 1
    assert window.services.runtime.status == 'stopped'  # Reading history never enables sending/listening.
    window.close()
