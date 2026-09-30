"""Application entry point: python -m auto_censor_studio."""

import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from . import APP_NAME
from .ui.window import MainWindow
from .ui.theme import STYLE
from .ui.branding import application_icon, configure_taskbar
from .ui.model_setup import ensure_models


def main():
    configure_taskbar()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(application_icon())
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    # Without models the editor still opens; detection reports the missing files.
    ensure_models()
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        QTimer.singleShot(0, lambda: window.open_paths(sys.argv[1:]))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
