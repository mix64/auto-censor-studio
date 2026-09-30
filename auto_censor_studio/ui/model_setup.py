"""First-run model download, shown before the main window opens."""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QMessageBox, QProgressDialog
from .. import APP_NAME
from ..models import download_models, missing_models


class ModelDownload(QThread):
    failed = Signal(str)

    def run(self):
        try:
            download_models(should_stop=self.isInterruptionRequested)
        except InterruptedError:
            pass
        except Exception as exc:
            self.failed.emit(str(exc))


def ensure_models():
    missing = missing_models()
    if not missing:
        return True
    megabytes = sum(spec.megabytes for spec in missing)
    dialog = QProgressDialog(f"初回のみ、検出モデルをダウンロードしています（約{megabytes}MB）…", "中止", 0, 0)
    dialog.setWindowTitle(APP_NAME)
    dialog.setMinimumDuration(0)
    errors = []
    worker = ModelDownload()
    worker.failed.connect(errors.append)
    worker.finished.connect(dialog.accept)
    worker.start()
    if dialog.exec() != QProgressDialog.DialogCode.Accepted:
        worker.requestInterruption()
    worker.wait()
    if errors:
        QMessageBox.critical(
            None,
            APP_NAME,
            "モデルをダウンロードできませんでした。\nネット接続を確認して起動し直してください。\n\n" + errors[0],
        )
    return not missing_models()
