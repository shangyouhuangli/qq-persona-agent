# PyInstaller onefile + windowed. Run with --upx-dir tools/upx.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.hooks.qt import pyside6_library_info

datas = [('qq_persona_agent/schema.sql', 'qq_persona_agent')]
# Qt hook collects Widgets/Gui/Core dependencies. Explicit platform collection.
platforms = pyside6_library_info.collect_plugins('platforms')
a = Analysis(['run_app.py'], pathex=['.'], binaries=platforms, datas=datas,
             hiddenimports=['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets'],
             excludes=['PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtWebEngineCore', 'tkinter', 'pytest'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='QQPersonaAgent', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=True,
          upx_exclude=['Qt6*.dll', 'qwindows.dll', 'qoffscreen.dll', 'vcruntime*.dll', 'python3*.dll'],
          console=False, disable_windowed_traceback=True)
