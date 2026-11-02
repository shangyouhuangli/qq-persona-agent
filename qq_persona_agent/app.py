import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description='QQ Persona Agent')
    parser.add_argument('--smoke-test', action='store_true', help='离线 GUI 自检，使用临时数据库并自动退出')
    parser.add_argument('--native-smoke-test', action='store_true', help='原生 Windows 窗口离线自检并自动退出')
    parser.add_argument('--mcp', action='store_true')
    args = parser.parse_args()
    smoke_mode = args.smoke_test or args.native_smoke_test
    if args.mcp:
        from qq_persona_agent.skill_export import main as mcp_main
        return mcp_main()
    if args.smoke_test:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtCore import QTimer, QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox
    from qq_persona_agent.config import data_dir
    from qq_persona_agent.app_gui import MainWindow
    import tempfile
    app = QApplication(sys.argv[:1])
    app.setStyle('Fusion')
    app.setStyleSheet('QWidget {font-family:"Microsoft YaHei UI";font-size:10pt;} QMainWindow,QDialog {background:#18232e;color:#dce6ef;} QPlainTextEdit,QTextEdit,QListWidget {background:#101923;color:#dce6ef;} QLabel {color:#748da5;} QPushButton {padding:6px 12px;} QTabBar::tab {padding:9px 20px;}')
    lock = QLockFile(str(data_dir() / 'app.lock'))
    if not smoke_mode and not lock.tryLock(0):
        QMessageBox.warning(None, '程序已运行', 'GUI 或 MCP 已占用本地数据，请先关闭另一实例。')
        return 1
    temp = tempfile.TemporaryDirectory() if smoke_mode else None
    window = MainWindow(Path(temp.name) / 'smoke.db' if temp else None)
    window.show()
    if smoke_mode:
        def smoke():
            try:
                from qq_persona_agent.selftest import check_services
                window.worker.submit(check_services(window.services)).result(timeout=10)
                assert window.tabs.count() == 5
                assert window.stop_button.isVisible()
                window.stop()
                QTimer.singleShot(300, window.close)
            except Exception:
                window.close()
                app.exit(1)
        QTimer.singleShot(500, smoke)
    result = app.exec()
    if temp:
        temp.cleanup()
    lock.unlock()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
