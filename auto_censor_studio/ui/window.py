from __future__ import annotations

import copy
from pathlib import Path
from .. import APP_NAME

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow,
    QFileDialog,
    QMessageBox,
)

from .theme import apply_theme
from .branding import application_icon

from ..core import minimum_block, render, atomic_export, save_project, read_project, region_covers
from ..services.segmentation import Segmenter
from ..services.detection import Detector
from .batch_controller import BatchMixin
from ..core.documents import Document, load_session


from .canvas import Canvas
from ..services.workers import DetectionThread, ContourThread
from ..paths import data_directory


class MainWindow(BatchMixin, QMainWindow):
    def __init__(self, preferences_path=None):
        super().__init__()
        settings_path = preferences_path or (data_directory() / "preferences.ini")
        self.preferences = QSettings(str(settings_path), QSettings.Format.IniFormat, self)
        self.image = None
        self.source = None
        self.rendered = None
        self.regions = []
        self.undo_stack, self.redo_stack = [], []
        self.dirty = False
        self.busy = False
        self.init_batch()
        self.original_held = False
        self.detector = Detector()
        self.segmenter = Segmenter()
        self.worker = None
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(application_icon())
        self.resize(960, 700)
        self.setMinimumSize(720, 450)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh_image)
        self.build_ui()
        dark = self.preferences.value("appearance/dark", False, type=bool)
        self.set_dark_mode(dark, persist=False)
        self.shortcuts = []
        for key, fn in [
            ("Ctrl+O", self.open_dialog),
            ("Ctrl+S", self.export),
            ("Ctrl+Z", self.undo),
            ("Ctrl+Y", self.redo),
            ("Delete", self.remove_selected),
            ("Escape", self.cancel_drawing),
        ]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(fn)
            self.shortcuts.append(shortcut)
        self.update_enabled()

    def build_ui(self):
        from .layout import build_ui

        build_ui(self, Canvas)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "mosaic_controls"):
            return
        compact = self.width() < 840
        if compact != self.compact_toolbar:
            self.compact_toolbar = compact
            if compact:
                self.toolbar_layout.removeWidget(self.mosaic_controls)
                self.toolbar_group.addWidget(self.mosaic_controls, 0, Qt.AlignmentFlag.AlignLeft)
            else:
                self.toolbar_group.removeWidget(self.mosaic_controls)
                self.toolbar_layout.insertWidget(self.toolbar_layout.indexOf(self.undo_btn) + 1, self.mosaic_controls)

    def detection_options_changed(self):
        if self._switching:
            return
        self.preferences.setValue("detection/threshold", self.threshold.value())
        self.preferences.setValue("detection/tiled", self.tiled.isChecked())
        self.preferences.sync()
        document = self.current_document()
        if document and self.image is not None:
            document.threshold = self.threshold.value()
            document.tiled = self.tiled.isChecked()
            document.dirty = self.dirty = True
            self.setWindowTitle(f"* {self.source.name} — {APP_NAME}")

    def set_dark_mode(self, enabled, persist=True):
        self.dark_mode = bool(enabled)
        self.dark_action.blockSignals(True)
        self.dark_action.setChecked(self.dark_mode)
        self.dark_action.blockSignals(False)
        apply_theme(self, self.dark_mode)
        if persist:
            self.preferences.setValue("appearance/dark", self.dark_mode)
            self.preferences.sync()

    def update_enabled(self):
        has_image = self.image is not None
        editing = has_image and not self.edit_locked()
        for widget in (
            self.detect_btn,
            self.draw_btn,
            self.lasso_action,
            self.block,
            self.margin,
            self.save_btn,
            self.original,
            self.project_save_btn,
            self.outline,
        ):
            widget.setEnabled(editing)
        options_enabled = not self.edit_locked() and not self.batch_running
        for widget in (self.detection_options_action, self.threshold, self.tiled):
            widget.setEnabled(options_enabled)
        self.canvas.setEnabled(not self.edit_locked())
        self.open_btn.setEnabled(not self.busy and not self.export_running)
        self.project_open_btn.setEnabled(not self.busy and not self.batch_running and not self.export_running)
        self.project_save_btn.setEnabled(
            bool(self.documents) and not self.busy and not self.batch_running and not self.export_running
        )
        self.detect_btn.setEnabled(editing and not self.batch_running)
        self.draw_btn.setEnabled(editing and not self.batch_running)
        self.delete_btn.setEnabled(editing and bool(self.canvas.selected))
        self.redraw_action.setEnabled(editing and bool(self.canvas.selected))
        self.refine_action.setEnabled(editing and not self.batch_running and bool(self.canvas.selected))
        self.undo_btn.setEnabled(editing and bool(self.undo_stack))
        self.redo_btn.setEnabled(editing and bool(self.redo_stack))
        self.update_batch_ui()

    def error(self, message):
        QMessageBox.warning(self, "処理を完了できませんでした", str(message))

    def confirm_discard(self, current_only=False):
        self.sync_document()
        pending = [d for d in self.documents if d.dirty]
        if not self.dirty and (current_only or not pending):
            return True
        dialog = QMessageBox(self)
        dialog.setWindowTitle("編集中の作業")
        dialog.setText(f"保存していない作業があります（{1 if current_only else max(1, len(pending))}枚）。")
        save = dialog.addButton("作業を保存", QMessageBox.ButtonRole.AcceptRole)
        discard = dialog.addButton("破棄して進む", QMessageBox.ButtonRole.DestructiveRole)
        cancel = dialog.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel)
        dialog.exec()
        if dialog.clickedButton() == save:
            return self.save_work()
        return dialog.clickedButton() == discard

    def open_dialog(self):
        if self.busy or self.export_running:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "PNGを追加（複数選択可）", str(self.source.parent) if self.source else "", "PNG (*.png)"
        )
        if paths:
            self.open_paths(paths)

    def open_path(self, path):
        self.open_paths([path])

    def install_document(self, source, image, regions, block, margin):
        self.timer.stop()
        self.source, self.image, self.regions = source, image, regions
        self.undo_stack, self.redo_stack = [], []
        self.canvas.regions = self.regions
        self.canvas.selected = ""
        self.canvas.drag = None
        self.cancel_drawing()
        self.canvas.size_ = image.size
        self.canvas.margin = margin
        for widget in (self.block, self.margin):
            widget.blockSignals(True)
        minimum = minimum_block(image.size)
        self.block.setRange(minimum, max(1000, minimum))
        self.block.setValue(block)
        self.margin.setValue(margin)
        for widget in (self.block, self.margin):
            widget.blockSignals(False)
        self.block.setToolTip(f"1ブロックの一辺。この画像の目安は{minimum}px以上です。")
        self.rendered = render(image, regions, block, margin)
        self.original.setChecked(False)
        self.draw_btn.setChecked(False)
        self.canvas.set_image(self.rendered, new=True)
        self.refresh_regions()
        self.dirty = False
        self.setWindowTitle(f"{source.name} — {APP_NAME}")
        self.status.setText(f"{image.width:,} × {image.height:,} px" if not regions else "作業を読み込みました。")
        self.update_enabled()
        self.canvas.setFocus(Qt.FocusReason.OtherFocusReason)

    def mark_dirty(self):
        self.dirty = True
        document = self.current_document()
        if document and not self._switching:
            document.reviewed = False
            document.exported = ""
            document.dirty = True
            document.error = ""
        self.setWindowTitle(f"* {self.source.name} — {APP_NAME}")
        self.update_batch_ui()

    def set_mode(self, mode):
        self.canvas.mode = mode
        self.canvas.lasso = None
        self.canvas.replace_uid = ""
        self.canvas.setCursor(Qt.CursorShape.CrossCursor if mode in ("draw", "lasso") else Qt.CursorShape.ArrowCursor)
        if not self.outline.isChecked():
            self.outline.setChecked(True)

    def start_lasso(self, replace=False):
        if self.image is None or self.edit_locked():
            return
        self.draw_btn.setChecked(False)
        self.set_mode("lasso")
        self.canvas.replace_uid = self.canvas.selected if replace else ""
        self.status.setText("輪郭をドラッグで囲んで離すと確定 · Escでキャンセル")

    def cancel_drawing(self):
        if self.busy:
            return
        if self.canvas.drag:
            self.regions[:] = self.canvas.drag[4]
            self.canvas.drag = None
            self.canvas.selected = ""
        self.draw_btn.setChecked(False)
        self.set_mode("select")
        self.canvas.draw_regions()

    def snapshot(self):
        return copy.deepcopy(self.regions)

    def remember(self, before=None):
        self.undo_stack.append(before if before is not None else self.snapshot())
        self.undo_stack = self.undo_stack[-50:]
        self.redo_stack.clear()

    def canvas_edited(self, before):
        self.remember(before)
        was_box = self.canvas.mode == "draw"
        if self.canvas.mode in ("draw", "lasso"):
            self.cancel_drawing()
        self.changed()
        if was_box:
            self.refine_selected(remember=False)

    def refine_selected(self, remember=True):
        if self.edit_locked() or self.batch_running or self.image is None:
            return
        region = next((r for r in self.regions if r.uid == self.canvas.selected), None)
        if region is None:
            return
        self.busy = True
        self.progress.show()
        self.status.setText("輪郭を抽出中…")
        self.update_enabled()
        self.worker = ContourThread(self.segmenter, self.image, region, self)
        self.worker.result.connect(lambda result: self.contour_ready(result, remember))
        self.worker.failed.connect(self.contour_error)
        self.worker.finished.connect(self.detection_finished)
        self.worker.start()

    def contour_ready(self, result, remember):
        if result.contours:
            if remember:
                self.remember()
            self.regions[:] = [result if r.uid == result.uid else r for r in self.regions]
            self.changed()
            self.status.setText("輪郭を抽出しました。点をドラッグで調整できます。")
        else:
            self.status.setText(
                "輪郭を抽出できなかったため四角い範囲を保持しました。右クリック → 輪郭を描き直すで修正できます。"
            )

    def contour_error(self, message):
        self.status.setText("輪郭抽出に失敗したため元の範囲を保持しました。")
        self.error(message)

    def changed(self):
        self.mark_dirty()
        self.refresh_regions()
        self.timer.start(80)
        self.status.setText(f"{len(self.regions)}か所を編集中")
        self.update_enabled()

    def mosaic_changed(self):
        if self.image is None:
            return
        self.canvas.margin = self.margin.value()
        self.canvas.draw_regions()
        self.mark_dirty()
        self.timer.start(120)
        self.status.setText("仕上がりを確認してください。")
        self.update_enabled()

    def refresh_image(self):
        if self.image is None:
            return
        self.rendered = render(self.image, self.regions, self.block.value(), self.margin.value())
        self.canvas.set_image(self.image if self.original_held else self.rendered)

    def refresh_regions(self):
        self.canvas.regions = self.regions
        self.canvas.draw_regions()

    def selection_changed(self, uid):
        self.update_enabled()

    def remove_selected(self):
        if self.edit_locked() or not self.canvas.selected:
            return
        self.remember()
        self.regions[:] = [r for r in self.regions if r.uid != self.canvas.selected]
        self.canvas.selected = ""
        self.changed()

    def undo(self):
        if self.edit_locked() or not self.undo_stack:
            return
        self.redo_stack.append(self.snapshot())
        self.regions[:] = self.undo_stack.pop()
        self.canvas.selected = ""
        self.changed()

    def redo(self):
        if self.edit_locked() or not self.redo_stack:
            return
        self.undo_stack.append(self.snapshot())
        self.regions[:] = self.redo_stack.pop()
        self.canvas.selected = ""
        self.changed()

    def toggle_outlines(self, enabled):
        self.canvas.outlines = enabled
        self.canvas.draw_regions()

    def show_original(self, enabled):
        self.original_held = enabled
        if self.image is not None:
            self.canvas.set_image(self.image if enabled else self.rendered)

    def detect(self):
        if self.image is None or self.edit_locked() or self.batch_running:
            return
        self.busy = True
        self.progress.show()
        self.status.setText("モデルを読み込んでいます…")
        self.update_enabled()
        self.worker = DetectionThread(
            self.detector, self.segmenter, self.image, self.threshold.value(), self.tiled.isChecked(), self
        )
        self.worker.progress.connect(self.status.setText)
        self.worker.result.connect(self.detected)
        self.worker.failed.connect(self.detection_error)
        self.worker.finished.connect(self.detection_finished)
        self.worker.start()

    def detected(self, found):
        document = self.current_document()
        if document:
            document.detected = True
            document.reviewed = False
            document.exported = ""
            document.error = ""
            document.dirty = True
            self.dirty = True
        # Preserve all user-edited and manually added regions on repeat detection.
        # Skip only candidates already covered. An existing partial box must not hide
        # a newly detected, larger extent merely because their IoU is high.
        added = [r for r in found if not any(region_covers(old, r) for old in self.regions)]
        if added:
            self.remember()
            self.regions.extend(added)
            self.changed()
        if not found:
            self.status.setText(
                "候補は0件でした。修正不要という判定ではありません。画像を確認し、必要な範囲を手動追加してください。"
            )
        else:
            fallback = sum(not r.contours for r in added)
            self.status.setText(
                f"{len(found)}件を検出 / {len(added)}件を追加。輪郭と見落としを確認してください。"
                + (f" {fallback}件は輪郭を抽出できず四角い範囲を保持。" if fallback else "")
            )

    def detection_error(self, message):
        self.status.setText("自動検出に失敗しました。手動での範囲追加は利用できます。")
        self.error(message)

    def detection_finished(self):
        self.busy = False
        self.progress.hide()
        self.update_enabled()

    def export(self):
        if self.image is None or self.edit_locked():
            return
        proposed = self.source.with_name(self.source.stem + "_mosaic.png")
        target, chosen = QFileDialog.getSaveFileName(
            self, "処理済み画像を保存", str(proposed), "PNG (*.png);;JPEG (*.jpg)"
        )
        if not target:
            return
        if not Path(target).suffix:
            target += ".jpg" if chosen.startswith("JPEG") else ".png"
        try:
            self.timer.stop()
            self.refresh_image()
            atomic_export(self.rendered, target, self.source)
            count = len(self.regions)
            self.status.setText(
                f"保存しました · {count}か所\n{Path(target).name}"
                + ("\n範囲0件のため画像にモザイクはありません。" if not count else "")
            )
            # Exporting pixels does not save the editable project.
        except Exception as exc:
            self.error(exc)

    def save_work(self):
        if self.busy or self.batch_running or self.export_running:
            return False
        if len(self.documents) > 1:
            return self.save_batch_work()
        if self.image is None:
            return False
        proposed = self.source.with_name(self.source.stem + ".mosaic.json")
        target, _ = QFileDialog.getSaveFileName(
            self, "編集できる作業ファイルを保存", str(proposed), "作業ファイル (*.json)"
        )
        if not target:
            return False
        if not target.lower().endswith(".json"):
            target += ".json"
        try:
            save_project(target, self.source, self.regions, self.block.value(), self.margin.value())
            self.dirty = False
            self.setWindowTitle(f"{self.source.name} — {APP_NAME}")
            self.status.setText("作業を保存しました。元画像と作業ファイルを保管してください。")
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def open_work(self):
        if self.busy or self.batch_running or self.export_running or not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "作業を開く", "", "作業ファイル (*.json)")
        if path:
            self.load_work(path)

    def load_work(self, path):
        if self.busy or self.batch_running or self.export_running:
            return
        try:
            import json
            from ..core import fingerprint

            if Path(path).stat().st_size > 64_000_000:
                raise ValueError("作業ファイルが大きすぎます。")
            header = json.loads(Path(path).read_text(encoding="utf-8"))
            if header.get("kind") == "mosaic-batch":
                documents = load_session(path)
            else:
                source, image, regions, block, margin = read_project(path)
                documents = [Document(source.resolve(), fingerprint(source), block, margin, regions=regions)]
            self.documents = documents
            self.document_index = -1
            self.switch_document(0)
        except Exception as exc:
            self.error(exc)

    def closeEvent(self, event):
        if self.busy or self.batch_running or self.export_running:
            self.status.setText("処理中です。一括処理は「停止」で止めてから閉じられます。")
            event.ignore()
        elif self.confirm_discard():
            event.accept()
        else:
            event.ignore()
