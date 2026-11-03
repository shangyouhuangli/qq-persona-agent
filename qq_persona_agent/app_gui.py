from __future__ import annotations
import asyncio
import concurrent.futures
import threading
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QMainWindow, QTabWidget, QDockWidget, QToolBar, QLabel, QMessageBox, QPushButton
from .db import Database
from .services import Services
from .logging_utils import log
from .ui.settings_page import SettingsPage
from .ui.export_page import ExportPage
from .ui.persona_page import PersonaPage
from .ui.deploy_chat_page import DeployChatPage
from .ui.tuning_page import TuningPage
from .ui.log_panel import LogPanel


class Bridge(QObject):
    event = Signal(object)
    result = Signal(object, object, object)
    record = Signal(object)


class AsyncWorker:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name='QQPersona-network', daemon=True)
        self.thread.start()

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def close(self):
        async def cancel():
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        self.submit(cancel()).result(timeout=5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        self.loop.close()


class MainWindow(QMainWindow):
    def __init__(self, db_path=None):
        super().__init__()
        self.setWindowTitle('QQ 人格智能体 · 预览与审批工作台')
        self.resize(1180, 850)
        self.worker, self.bridge = AsyncWorker(), Bridge()
        self.bridge.event.connect(self.handle_event)
        self.bridge.result.connect(self.completed)
        self.bridge.record.connect(lambda r: self.logs.add(r))
        self.busy = False
        self.closing = False
        async def create():
            return Services(Database(db_path), self.bridge.event.emit)
        self.services = self.worker.submit(create()).result(timeout=15)
        self.toolbar = QToolBar('运行控制')
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        self.stop_button = QPushButton('■ 停止智能体')
        self.stop_button.setStyleSheet('background:#a52c37;color:white;font-weight:bold;padding:10px 18px')
        self.stop_button.clicked.connect(self.stop)
        self.toolbar.addWidget(self.stop_button)
        self.global_status = QLabel('  已停止 · 自主发送关闭')
        self.toolbar.addWidget(self.global_status)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tuning_page = TuningPage(self)
        self.persona_page = PersonaPage(self)
        self.deploy_page = DeployChatPage(self)
        self.export_page = ExportPage(self)
        self.settings_page = SettingsPage(self)
        for name, page in [('设置', self.settings_page), ('数据导出', self.export_page), ('人格生成', self.persona_page), ('部署与聊天', self.deploy_page), ('参数', self.tuning_page)]:
            self.tabs.addTab(page, name)
        self.logs = LogPanel()
        dock = QDockWidget('实时日志', self)
        dock.setWidget(self.logs)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.menuBar().addMenu('视图').addAction(dock.toggleViewAction())
        self._log_listener = self.bridge.record.emit
        log.listeners.append(self._log_listener)
        log.emit('app', '程序已启动；默认停止，自主发送关闭')
        self.statusBar().showMessage('就绪')

    def error(self, message):
        QMessageBox.warning(self, '操作未完成', log.redact(message))

    def confirm(self, message):
        return QMessageBox.question(self, '确认操作', message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def run(self, coro, callback=None, on_error=None, urgent=False):
        if self.busy and not urgent:
            coro.close()
            self.statusBar().showMessage('当前操作进行中，请等待完成；停止按钮始终可用')
            return
        if not urgent:
            self.busy = True
            self.statusBar().showMessage('后台处理中…')
        future = self.worker.submit(coro)
        future.add_done_callback(lambda f: self.bridge.result.emit(f, callback, (on_error, urgent)))

    def completed(self, future, callback, options):
        if self.closing:
            return
        on_error, urgent = options
        if not urgent:
            self.busy = False
        try:
            result = future.result()
            self.statusBar().showMessage('完成')
            if callback:
                callback(result)
        except concurrent.futures.CancelledError:
            self.statusBar().showMessage('操作已取消')
        except Exception as e:
            from .llm_client import LLMError
            from .napcat_client import NapCatError
            log.emit('app', '后台操作失败', level='ERROR', error_type=type(e).__name__)
            self.error(str(e) if isinstance(e, (ValueError, LLMError, NapCatError)) else '操作失败，请检查配置、网络和目录权限。日志中未记录原始响应。')
            if on_error:
                on_error()

    def handle_event(self, event):
        if self.closing:
            return
        if event['kind'] == 'export_progress':
            self.export_page.batch_id = event['batch_id']
            self.export_page.progress.setRange(0, 0)
            self.export_page.summary.setText(f"已扫描 {event['scanned']} 条会话消息；匹配 {event['count']} 条（条数上限 {event['maximum']}，不代表完成百分比）")
        elif event['kind'] == 'failure':
            self.error(event['message'])
        else:
            self.deploy_page.handle_event(event)
            if event['kind'] == 'status':
                self.global_status.setText('  状态：' + event['status'])

    def stop(self):
        self.services.runtime.emergency_stop()
        self.global_status.setText('  正在停止…（停止标记已设置）')
        self.run(self.services.runtime.stop(), urgent=True)

    def clear_data(self):
        if self.confirm('确认停止智能体并清除本应用数据库、密钥、记忆和默认加密导出？无法恢复。自行导出的外部人格文件请自行删除。'):
            self.services.runtime.emergency_stop()
            self.export_page.cancel.set()
            self.run(self.services.clear(), lambda _: self.reset_ui())

    def reset_ui(self):
        self.settings_page.load(self.services.settings)
        self.persona_page.persona_id = None
        self.persona_page.refresh()
        self.persona_page.prompt.clear()
        self.persona_page.analysis.clear()
        self.export_page.batch_id = None
        self.export_page.samples.clear()
        self.deploy_page.messages.clear()
        self.deploy_page.sent.clear()
        self.logs.reload()

    def closeEvent(self, event):
        self.closing = True
        self.services.runtime.emergency_stop()
        self.export_page.cancel.set()
        try:
            async def shutdown():
                tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await self.services.close()
            self.worker.submit(shutdown()).result(timeout=10)
            self.worker.close()
        except Exception:
            pass
        if self._log_listener in log.listeners:
            log.listeners.remove(self._log_listener)
        event.accept()
