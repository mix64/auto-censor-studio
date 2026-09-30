import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, QPointF, QPoint, QMimeData, QUrl
from PySide6.QtGui import QFontDatabase, QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from auto_censor_studio.ui.window import MainWindow
from auto_censor_studio.ui.theme import STYLE
from auto_censor_studio.core import fingerprint, Region


def add_test_fonts():
    # Qt's offscreen platform does not discover the Windows system fonts itself.
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("segoeui.ttf", "segoeuib.ttf", "YuGothR.ttc", "YuGothB.ttc"):
        if (fonts / name).exists():
            QFontDatabase.addApplicationFont(str(fonts / name))


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        add_test_fonts()
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.segment_patch = patch(
            "auto_censor_studio.services.segmentation.Segmenter.refine", side_effect=lambda image, region: region
        )
        self.segment_patch.start()
        self.folder = tempfile.TemporaryDirectory()
        self.source = Path(self.folder.name) / "日本語サンプル.png"
        y, x = np.mgrid[:600, :800]
        pixels = np.stack(((x * 7) % 256, (y * 9) % 256, (x + y) % 256), axis=2).astype("uint8")
        Image.fromarray(pixels).save(self.source)
        self.preferences_path = Path(self.folder.name) / "preferences.ini"
        self.window = MainWindow(self.preferences_path)
        self.window.show()
        self.window.open_path(self.source)
        self.app.processEvents()

    def tearDown(self):
        self.wait_for_worker()
        self.segment_patch.stop()
        self.window.dirty = False
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.folder.cleanup()

    def drag(self, start, end):
        view = self.window.canvas
        a, b = view.mapFromScene(QPointF(*start)), view.mapFromScene(QPointF(*end))
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=a)
        QTest.mouseMove(view.viewport(), b, delay=10)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=b)
        self.app.processEvents()

    def add_region(self):
        self.window.draw_btn.click()
        self.drag((100, 100), (300, 280))
        self.wait_for_worker()
        self.assertEqual(len(self.window.regions), 1)

    def wait_for_worker(self):
        for _ in range(200):
            if not self.window.busy:
                return
            QTest.qWait(10)
        self.fail("Worker did not finish")

    def test_drawing_moving_resizing_undo_redo_delete(self):
        w = self.window
        self.add_region()
        self.assertEqual(w.canvas.mode, "select")
        self.drag((200, 200), (250, 240))
        r = w.regions[0]
        self.assertAlmostEqual(r.x, 150, delta=3)
        self.assertAlmostEqual(r.y, 140, delta=3)
        self.drag((r.x + r.w, r.y + r.h), (450, 380))
        self.assertAlmostEqual(w.regions[0].x + w.regions[0].w, 450, delta=3)
        w.undo()
        self.assertAlmostEqual(w.regions[0].w, 200, delta=3)
        w.redo()
        self.assertAlmostEqual(w.regions[0].x + w.regions[0].w, 450, delta=3)
        w.canvas.select(w.regions[0].uid)
        w.remove_selected()
        self.assertEqual(len(w.regions), 0)
        w.undo()
        self.assertEqual(len(w.regions), 1)

    def test_export_and_project_buttons_round_trip(self):
        w = self.window
        self.add_region()
        w.block.setValue(24)
        w.margin.setValue(25)
        before = fingerprint(self.source)
        target = Path(self.folder.name) / "出力.png"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "PNG (*.png)")):
            w.export()
        self.assertTrue(target.exists())
        self.assertEqual(fingerprint(self.source), before)
        self.assertNotEqual(fingerprint(self.source), fingerprint(target))
        with Image.open(target) as saved:
            self.assertEqual(saved.size, (800, 600))
        project = Path(self.folder.name) / "作業.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(project), "")):
            self.assertTrue(w.save_work())
        self.assertFalse(w.dirty)
        w.load_work(project)
        self.assertEqual((w.block.value(), w.margin.value(), len(w.regions)), (24, 25, 1))

    def test_overwrite_replaces_source_after_confirmation_and_clears_regions(self):
        w = self.window
        self.add_region()
        before = fingerprint(self.source)
        with patch.object(w, "confirm_overwrite", return_value=False):
            w.overwrite_current()
        self.assertEqual(fingerprint(self.source), before)
        self.assertEqual(len(w.regions), 1)
        with patch.object(w, "confirm_overwrite", return_value=True):
            w.overwrite_current()
        self.assertNotEqual(fingerprint(self.source), before)
        with Image.open(self.source) as saved:
            self.assertEqual(saved.tobytes(), w.image.tobytes())
        self.assertEqual(w.regions, [])
        self.assertFalse(w.dirty)
        self.assertFalse(w.overwrite_action.isEnabled())
        document = w.current_document()
        self.assertEqual(document.digest, fingerprint(self.source))
        self.assertTrue(document.reviewed)
        self.assertFalse(list(Path(self.folder.name).glob(".mosaic-*")))

    def test_overwrite_refuses_a_source_changed_after_loading(self):
        w = self.window
        self.add_region()
        Image.new("RGB", (800, 600), "red").save(self.source)
        changed = fingerprint(self.source)
        with patch.object(w, "confirm_overwrite", return_value=True), patch.object(w, "error") as error:
            w.overwrite_current()
        error.assert_called_once()
        self.assertEqual(fingerprint(self.source), changed)
        self.assertEqual(len(w.regions), 1)

    def test_zero_detection_is_not_a_clearance_and_manual_regions_survive(self):
        w = self.window
        self.add_region()
        w.detected([])
        self.assertEqual(len(w.regions), 1)
        self.assertIn("修正不要という判定ではありません", w.status.text())

    def test_repeat_detection_keeps_larger_new_extent(self):
        w = self.window
        w.regions.append(Region(100, 100, 100, 100))
        w.detected([Region(90, 90, 120, 120, "penis", 0.9)])
        self.assertEqual(len(w.regions), 2)
        w.detected([Region(90, 90, 120, 120, "penis", 0.9)])
        self.assertEqual(len(w.regions), 2)

    def test_empty_canvas_accepts_drop(self):
        fresh = MainWindow(self.preferences_path)
        fresh.show()
        self.app.processEvents()
        try:
            self.assertTrue(fresh.canvas.isEnabled())
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(self.source))])
            enter = QDragEnterEvent(
                QPoint(50, 50),
                Qt.DropAction.CopyAction,
                mime,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            self.app.sendEvent(fresh.canvas.viewport(), enter)
            self.assertTrue(enter.isAccepted())
            drop = QDropEvent(
                QPointF(50, 50),
                Qt.DropAction.CopyAction,
                mime,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            self.app.sendEvent(fresh.canvas.viewport(), drop)
            self.assertEqual(fresh.source, self.source.resolve())
            self.assertTrue(fresh.detect_btn.isEnabled())
        finally:
            fresh.dirty = False
            fresh.close()
            fresh.deleteLater()

    def test_coarseness_and_settings_retain_values(self):
        w = self.window
        self.add_region()
        w.block.setValue(1)
        self.assertEqual(w.block.value(), 1)
        w.block.setValue(400)
        self.assertEqual(w.block.value(), 400)
        w.margin.setValue(25)
        self.assertEqual(w.margin.value(), 25)
        w.detection_options_action.trigger()
        self.app.processEvents()
        self.assertTrue(w.detection_dialog.isVisible())
        w.threshold.setValue(0.15)
        w.detection_dialog.accept()
        w.detection_options_action.trigger()
        self.assertEqual(w.threshold.value(), 0.15)
        w.detection_dialog.accept()
        w.outline.trigger()
        self.assertFalse(w.canvas.outlines)
        w.draw_btn.click()
        self.assertTrue(w.canvas.outlines)

    def test_detection_options_work_before_loading_and_defaults_survive_restart(self):
        fresh = MainWindow(self.preferences_path)
        try:
            self.assertTrue(fresh.detection_options_action.isEnabled())
            self.assertTrue(fresh.threshold.isEnabled())
            self.assertFalse(fresh.block.isEnabled())
            self.assertFalse(fresh.margin.isEnabled())
            fresh.threshold.setValue(0.45)
            fresh.tiled.setChecked(False)
            fresh.open_path(self.source)
            self.assertEqual(fresh.current_document().threshold, 0.45)
            self.assertFalse(fresh.current_document().tiled)
        finally:
            fresh.dirty = False
            for document in fresh.documents:
                document.dirty = False
            fresh.close()
            fresh.deleteLater()
        restarted = MainWindow(self.preferences_path)
        try:
            self.assertEqual(restarted.threshold.value(), 0.45)
            self.assertFalse(restarted.tiled.isChecked())
        finally:
            restarted.close()
            restarted.deleteLater()

    def test_dark_mode_persists_without_changing_the_image_or_edits(self):
        w = self.window
        self.add_region()
        w.timer.stop()
        w.refresh_image()
        pixels = w.rendered.tobytes()
        selected = w.canvas.selected
        edits = w.snapshot()
        undo_count = len(w.undo_stack)
        w.dark_action.trigger()
        self.app.processEvents()
        self.assertTrue(w.dark_mode)
        self.assertEqual(w.rendered.tobytes(), pixels)
        self.assertEqual(w.canvas.selected, selected)
        self.assertEqual(w.regions, edits)
        self.assertEqual(len(w.undo_stack), undo_count)
        self.assertTrue(w.dirty)
        dark_background = w.canvas.backgroundBrush().color()
        fresh = MainWindow(self.preferences_path)
        try:
            self.assertTrue(fresh.dark_action.isChecked())
            self.assertEqual(fresh.canvas.backgroundBrush().color(), dark_background)
            fresh.dark_action.trigger()
            self.assertFalse(fresh.dark_mode)
            self.assertNotEqual(fresh.canvas.backgroundBrush().color(), dark_background)
            self.assertFalse(fresh.preferences.value("appearance/dark", True, type=bool))
        finally:
            fresh.close()
            fresh.deleteLater()

    def lasso(self, points):
        view = self.window.canvas
        screen = [view.mapFromScene(QPointF(*p)) for p in points]
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=screen[0])
        for point in screen[1:]:
            QTest.mouseMove(view.viewport(), point, delay=5)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=screen[-1])
        self.app.processEvents()

    def test_lasso_vertex_edit_redraw_and_undo(self):
        w = self.window
        w.start_lasso()
        self.lasso([(100, 100), (350, 100), (350, 200), (200, 200), (200, 350), (100, 350)])
        self.assertEqual(len(w.regions), 1)
        self.assertTrue(w.regions[0].contours)
        self.assertEqual(w.canvas.mode, "select")
        before = w.snapshot()
        self.drag((350, 100), (420, 120))
        self.assertNotEqual(w.regions[0].contours, before[0].contours)
        w.undo()
        self.assertEqual(w.regions, before)
        w.canvas.select(w.regions[0].uid)
        uid = w.canvas.selected
        w.start_lasso(replace=True)
        self.lasso([(150, 150), (450, 170), (250, 380)])
        self.assertEqual(len(w.regions), 1)
        self.assertEqual(w.regions[0].uid, uid)
        self.assertEqual(len(w.regions[0].contours[0]), 3)
        w.undo()
        self.assertEqual(w.regions, before)

    def test_exclude_lasso_carves_region_and_undo_restores_it(self):
        w = self.window
        w.start_lasso()
        self.lasso([(100, 100), (300, 100), (300, 300), (100, 300)])
        uid = w.regions[0].uid
        before = w.snapshot()
        w.start_exclude()
        self.lasso([(250, 150), (380, 150), (380, 380), (250, 380)])
        self.assertEqual(w.canvas.mode, "select")
        self.assertEqual(len(w.regions), 1)
        self.assertEqual(w.regions[0].uid, uid)
        self.assertEqual(len(w.regions[0].excludes), 1)
        self.assertEqual(w.regions[0].contours, before[0].contours)
        self.assertTrue(w.clear_excludes_action.isEnabled())
        w.undo()
        self.assertEqual(w.regions, before)
        w.canvas.select(uid)
        w.start_exclude()
        self.lasso([(250, 150), (380, 150), (380, 380), (250, 380)])
        w.clear_excludes()
        self.assertIsNone(w.regions[0].excludes)

    def test_manual_box_is_refined_once_and_undo_removes_whole_action(self):
        def shape(image, region):
            region.contours = [[[0, 0.5], [0.5, 0], [1, 0.5], [0.5, 1]]]
            return region

        with patch("auto_censor_studio.services.segmentation.Segmenter.refine", side_effect=shape):
            self.add_region()
        self.assertIsNotNone(self.window.regions[0].contours)
        self.window.undo()
        self.assertEqual(self.window.regions, [])
        self.window.redo()
        self.assertIsNotNone(self.window.regions[0].contours)

    def test_lasso_escape_does_not_modify_document(self):
        w = self.window
        w.start_lasso()
        view = w.canvas
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(QPointF(100, 100)))
        QTest.mouseMove(view.viewport(), view.mapFromScene(QPointF(300, 150)))
        w.cancel_drawing()
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(QPointF(300, 150)))
        self.assertEqual(w.regions, [])
        self.assertFalse(w.dirty)

    def test_auto_detection_runs_contour_stage_in_worker(self):
        w = self.window
        candidate = Region(100, 100, 200, 180, "penis", 0.9)

        def shape(image, region):
            region.contours = [[[0, 0.5], [0.5, 0], [1, 0.5], [0.5, 1]]]
            return region

        with (
            patch.object(w.detector, "detect", return_value=[candidate]),
            patch.object(w.segmenter, "refine", side_effect=shape) as refine,
        ):
            w.detect()
            self.wait_for_worker()
            refine.assert_called_once()
        self.assertEqual(len(w.regions), 1)
        self.assertTrue(w.regions[0].contours)
        self.assertTrue(w.detect_btn.isEnabled())
        w.undo()
        self.assertEqual(w.regions, [])


if __name__ == "__main__":
    unittest.main()
