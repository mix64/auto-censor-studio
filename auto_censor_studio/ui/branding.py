"""Application icon and Windows taskbar identity."""

import os
from pathlib import Path
from PySide6.QtGui import QIcon


def application_icon():
    return QIcon(str(Path(__file__).resolve().parents[1] / "assets" / "app-icon.ico"))


def configure_taskbar():
    if os.name == "nt":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AutoCensorStudio.Desktop")
