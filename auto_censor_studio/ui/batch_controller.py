"""Coordinates image selection, background processing, review and export."""

from pathlib import Path
from .. import APP_NAME
from dataclasses import replace
import copy
from PySide6.QtWidgets import QFileDialog
from ..core.images import load_image, fingerprint, minimum_block
from ..core.regions import region_covers
from ..core.documents import Document, save_session
from ..services.workers import BatchWorker, ExportWorker


class BatchMixin:
    def init_batch(self):
        self.documents = []
        self.document_index = -1
        self.batch_worker = None
        self.batch_pending = set()
        self.batch_active = ""
        self.batch_running = False
        self.export_running = False
        self.export_worker = None
        self.batch_errors = []
        self._switching = False

    def current_document(self):
        return self.documents[self.document_index] if 0 <= self.document_index < len(self.documents) else None

    def edit_locked(self):
        document = self.current_document()
        return self.busy or self.export_running or bool(document and document.uid in self.batch_pending)

    def sync_document(self):
        document = self.current_document()
        if document and self.image is not None and not self._switching:
            document.regions = copy.deepcopy(self.regions)
            document.undo, document.redo = copy.deepcopy(self.undo_stack), copy.deepcopy(self.redo_stack)
            document.block, document.margin = self.block.value(), self.margin.value()
            document.threshold, document.tiled = self.threshold.value(), self.tiled.isChecked()
            document.dirty = self.dirty

    def update_batch_ui(self):
        if not hasattr(self, "batch_bar"):
            return
        self.batch_bar.setVisible(len(self.documents) > 1)
        self.image_picker.blockSignals(True)
        self.image_picker.clear()
        for index, document in enumerate(self.documents):
            state = (
                "処理中"
                if document.uid == self.batch_active
                else "待機中"
                if document.uid in self.batch_pending
                else document.title()
            )
            self.image_picker.addItem(f"{index + 1}/{len(self.documents)}  {document.source.name} · {state}")
            self.image_picker.setItemData(
                index, str(document.source) + ("\n" + document.error if document.error else ""), 3
            )
        self.image_picker.setCurrentIndex(self.document_index)
        self.image_picker.blockSignals(False)
        can_switch = not self.busy and not self.export_running
        self.image_picker.setEnabled(can_switch)
        self.previous_btn.setEnabled(can_switch and self.document_index > 0)
        self.next_btn.setEnabled(can_switch and self.document_index + 1 < len(self.documents))
        self.batch_detect_btn.setText("停止" if self.batch_running else "一括処理")
        self.batch_detect_btn.setEnabled(not self.busy and not self.export_running and bool(self.documents))
        self.review_btn.setEnabled(self.image is not None and not self.edit_locked())
        document = self.current_document()
        self.review_btn.setText("確認済み" if document and document.reviewed else "確認して次へ")
        self.batch_export_btn.setEnabled(
            not self.busy
            and not self.batch_running
            and not self.export_running
            and any(d.reviewed for d in self.documents)
        )
        self.remove_image_action.setEnabled(can_switch and not self.batch_running and bool(self.documents))

    def open_paths(self, paths):
        if self.busy or self.export_running:
            return
        self.sync_document()
        first = None
        errors = []
        for path in paths:
            source = Path(path).resolve()
            existing = next((i for i, d in enumerate(self.documents) if d.source == source), None)
            if existing is not None:
                if first is None:
                    first = existing
                continue
            try:
                if len(self.documents) >= 1000:
                    raise ValueError("画像は1,000枚まで追加できます。")
                image = load_image(source)
                document = Document(
                    source,
                    fingerprint(source),
                    minimum_block(image.size),
                    threshold=self.preferences.value("detection/threshold", 0.30, type=float),
                    tiled=self.preferences.value("detection/tiled", True, type=bool),
                )
                self.documents.append(document)
                if first is None:
                    first = len(self.documents) - 1
                del image
            except Exception as exc:
                errors.append(f"{source.name}: {exc}")
        if first is not None:
            self.switch_document(first)
        self.update_enabled()
        if errors:
            self.error("\n".join(errors))

    def switch_document(self, index):
        if self.busy or self.export_running or not 0 <= index < len(self.documents):
            self.update_batch_ui()
            return
        document = self.documents[index]
        self.cancel_drawing()
        self.sync_document()
        try:
            if fingerprint(document.source) != document.digest:
                raise ValueError("元画像が変更されています。一覧から外して読み込み直してください。")
            image = load_image(document.source)
        except Exception as exc:
            document.error = str(exc)
            document.reviewed = False
            self.document_index = index
            self.timer.stop()
            self.source = document.source
            self.image = self.rendered = None
            self.regions = copy.deepcopy(document.regions)
            self.dirty = document.dirty
            self.canvas.regions = []
            self.canvas.selected = ""
            self.canvas.size_ = (0, 0)
            self.canvas.picture.setPixmap(type(self.canvas.picture.pixmap())())
            self.canvas.draw_regions()
            self.canvas.placeholder.setText("画像を読み込めません。\n「…」から一覧を整理できます。")
            self.canvas.placeholder.show()
            self.status.setText(str(exc))
            self.setWindowTitle(f"{document.source.name} — 読み込み失敗")
            self.update_enabled()
            return
        self._switching = True
        try:
            self.document_index = index
            self.install_document(
                document.source, image, copy.deepcopy(document.regions), document.block, document.margin
            )
            self.undo_stack, self.redo_stack = copy.deepcopy(document.undo), copy.deepcopy(document.redo)
            self.dirty = document.dirty
            self.threshold.setValue(document.threshold)
            self.tiled.setChecked(document.tiled)
            self.setWindowTitle(("* " if self.dirty else "") + f"{document.source.name} — {APP_NAME}")
            self.status.setText(
                document.error
                or document.notice
                or (
                    "候補0件です。見落としがないか確認してください。"
                    if document.detected and not document.regions
                    else document.title()
                )
            )
        finally:
            self._switching = False
        self.update_enabled()

    def step_document(self, step):
        self.switch_document(self.document_index + step)

    def mark_reviewed(self):
        if self.edit_locked() or self.image is None:
            return
        self.timer.stop()
        self.refresh_image()
        self.sync_document()
        document = self.current_document()
        document.reviewed, document.dirty = True, True
        document.error = ""
        self.dirty = True
        next_index = next(
            (
                i
                for i in list(range(self.document_index + 1, len(self.documents))) + list(range(self.document_index))
                if not self.documents[i].reviewed and self.documents[i].uid not in self.batch_pending
            ),
            None,
        )
        if next_index is not None:
            self.switch_document(next_index)
        else:
            self.status.setText("確認済みにしました。確認済みの画像をまとめて保存できます。")
        self.update_enabled()

    def start_batch(self):
        if self.batch_running:
            self.batch_worker.requestInterruption()
            self.status.setText("停止しています。完了した画像は保持します。")
            return
        if self.busy or self.export_running:
            return
        self.cancel_drawing()
        self.sync_document()
        # Completed/reviewed work is not silently reprocessed by pressing the batch button again.
        jobs = [replace(d, regions=[], undo=[], redo=[]) for d in self.documents if not d.detected and not d.reviewed]
        if not jobs:
            self.status.setText("未処理の画像はありません。現在の画像だけ再処理するには「自動検出」を使ってください。")
            return
        self.batch_pending = {d.uid for d in jobs}
        self.batch_running = True
        self.batch_errors = []
        self.batch_worker = BatchWorker(jobs, self)
        self.batch_worker.progress.connect(self.batch_progress)
        self.batch_worker.result.connect(self.batch_result)
        self.batch_worker.finished.connect(self.batch_finished)
        self.progress.show()
        self.update_enabled()
        self.batch_worker.start()

    def batch_progress(self, uid, text):
        self.batch_active = uid
        self.status.setText("一括処理中 " + text + " · 完了した画像から確認できます")
        self.update_batch_ui()

    def batch_result(self, uid, found, error):
        document = next((d for d in self.documents if d.uid == uid), None)
        if document is None:
            return
        self.batch_pending.discard(uid)
        self.batch_active = ""
        document.error = error
        if error:
            self.batch_errors.append(f"{document.source.name}: {error}")
        else:
            added = [r for r in found if not any(region_covers(old, r) for old in document.regions)]
            if added:
                document.undo.append(copy.deepcopy(document.regions))
                document.undo = document.undo[-50:]
                document.redo.clear()
                document.regions.extend(added)
            document.detected, document.reviewed, document.dirty = True, False, True
            document.exported = ""
            fallback = sum(not r.contours for r in found)
            document.notice = (
                f"{len(found)}件を検出。輪郭と見落としを確認してください。"
                if found
                else "候補0件です。見落としがないか確認してください。"
            )
            if fallback:
                document.notice += f" {fallback}件は輪郭を抽出できず四角い範囲を保持。"
        if document is self.current_document():
            # Install the result directly; syncing stale on-screen state would discard it.
            self.regions = copy.deepcopy(document.regions)
            self.undo_stack, self.redo_stack = copy.deepcopy(document.undo), copy.deepcopy(document.redo)
            self.dirty = document.dirty
            self.refresh_regions()
            self.refresh_image()
            self.status.setText(error or document.notice)
        self.update_enabled()

    def batch_finished(self):
        self.batch_running = False
        self.batch_pending.clear()
        self.batch_active = ""
        self.progress.hide()
        message = (
            "一括処理を停止しました。" if self.batch_worker.isInterruptionRequested() else "一括処理が完了しました。"
        )
        self.status.setText(
            message
            + f" 確認済み {sum(d.reviewed for d in self.documents)} / {len(self.documents)}枚。"
            + (f" 失敗 {len(self.batch_errors)}枚（一覧から選択して詳細を確認）。" if self.batch_errors else "")
        )
        self.update_enabled()
        self.batch_worker.deleteLater()
        self.batch_worker = None

    def export_reviewed(self, folder=None):
        if self.busy or self.batch_running or self.export_running:
            return
        self.sync_document()
        jobs = [replace(d, regions=copy.deepcopy(d.regions), undo=[], redo=[]) for d in self.documents if d.reviewed]
        if not jobs:
            return
        if not folder:
            folder = QFileDialog.getExistingDirectory(self, "確認済み画像の保存先フォルダー")
        if not folder:
            return
        self.export_running = True
        self.export_errors, self.export_count = [], 0
        self.export_worker = ExportWorker(jobs, folder, self)
        self.export_worker.result.connect(self.batch_export_result)
        self.export_worker.finished.connect(self.batch_export_finished)
        self.progress.show()
        self.status.setText(f"確認済み {len(jobs)}枚を保存中…")
        self.update_enabled()
        self.export_worker.start()

    def batch_export_result(self, uid, path, error):
        document = next(d for d in self.documents if d.uid == uid)
        if error:
            document.error = error
            document.reviewed = False
            self.export_errors.append(f"{document.source.name}: {error}")
        else:
            document.exported = path
            self.export_count += 1
        self.update_batch_ui()

    def batch_export_finished(self):
        self.export_running = False
        self.progress.hide()
        self.status.setText(
            f"{self.export_count}枚を保存しました。"
            + (f" 失敗 {len(self.export_errors)}枚。" if self.export_errors else "")
        )
        self.update_enabled()
        if self.export_errors:
            self.error("\n".join(self.export_errors))
        self.export_worker.deleteLater()
        self.export_worker = None

    def save_batch_work(self):
        if self.busy or self.batch_running or self.export_running:
            return False
        self.sync_document()
        path, _ = QFileDialog.getSaveFileName(self, "すべての作業を保存", "mosaic.batch.json", "作業ファイル (*.json)")
        if not path:
            return False
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            save_session(path, self.documents)
            for document in self.documents:
                document.dirty = False
            self.dirty = False
            self.status.setText("すべての画像の作業と確認状態を保存しました。")
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def remove_current_image(self):
        if self.busy or self.batch_running or self.export_running or not self.documents:
            return
        # Reuse the single-document save/discard dialog; the source file is never deleted.
        if not self.confirm_discard(current_only=True):
            return
        index = self.document_index
        self.documents.pop(index)
        self.document_index = -1
        if self.documents:
            self.switch_document(min(index, len(self.documents) - 1))
        else:
            self.timer.stop()
            self.image = self.source = self.rendered = None
            self.regions = []
            self.undo_stack, self.redo_stack = [], []
            self.dirty = False
            self.canvas.regions = []
            self.canvas.picture.setPixmap(type(self.canvas.picture.pixmap())())
            self.canvas.size_ = (0, 0)
            self.canvas.selected = ""
            self.canvas.draw_regions()
            self.canvas.placeholder.setText("PNGをドロップ、または「開く」で選択")
            self.canvas.placeholder.show()
            self.setWindowTitle(APP_NAME)
            self.status.setText("")
            self.update_enabled()
