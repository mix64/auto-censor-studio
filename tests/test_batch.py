import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtTest import QTest
from PySide6.QtCore import QMimeData, QUrl, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from auto_censor_studio.ui.window import MainWindow
from auto_censor_studio.services.workers import BatchWorker
from auto_censor_studio.core.documents import load_session
from auto_censor_studio.core import Region, fingerprint


class FakeDetector:
    def detect(self, image, threshold, tiled=False):
        return [Region(10, 10, 40, 40, "penis", 0.9)]


class FakeSegmenter:
    def refine(self, image, region):
        region.contours = [[[0, 0.5], [0.5, 0], [1, 0.5], [0.5, 1]]]
        return region


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = []
        for i in range(3):
            folder = self.root / str(i)
            folder.mkdir()
            path = folder / "同じ名前.png"
            Image.new("RGB", (100 + i * 10, 100), (40 + i * 40, 80, 140)).save(path)
            self.paths.append(path)
        self.w = MainWindow(self.root / "prefs.ini")
        self.w.show()
        self.w.open_paths(self.paths)

    def tearDown(self):
        if self.w.batch_running:
            self.w.batch_worker.requestInterruption()
            self.wait(lambda: not self.w.batch_running)
        self.wait(lambda: not self.w.export_running and not self.w.busy)
        self.w.dirty = False
        for d in self.w.documents:
            d.dirty = False
        self.w.close()
        self.w.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def wait(self, predicate):
        deadline = time.monotonic() + 10
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate())

    def start(self, detector=None):
        with patch(
            "auto_censor_studio.ui.batch_controller.BatchWorker",
            side_effect=lambda jobs, parent: BatchWorker(jobs, parent, detector or FakeDetector(), FakeSegmenter()),
        ):
            self.w.start_batch()

    def test_switch_preserves_edits_undo_settings_and_invalidates_review(self):
        w = self.w
        self.assertEqual(len(w.documents), 3)
        w.remember()
        w.regions.append(Region(10, 10, 30, 30))
        w.changed()
        w.block.setValue(16)
        w.margin.setValue(8)
        w.switch_document(1)
        self.assertEqual(w.regions, [])
        w.switch_document(0)
        self.assertEqual(len(w.regions), 1)
        self.assertEqual((w.block.value(), w.margin.value()), (16, 8))
        w.undo()
        self.assertEqual(w.regions, [])
        w.redo()
        self.assertEqual(len(w.regions), 1)
        w.mark_reviewed()
        self.assertTrue(w.documents[0].reviewed)
        w.switch_document(0)
        w.block.setValue(20)
        self.assertFalse(w.documents[0].reviewed)
        w.open_paths([self.paths[0]])
        self.assertEqual(len(w.documents), 3)

    def test_worker_results_stay_with_correct_image_and_ready_images_can_be_reviewed(self):
        w = self.w
        gate = threading.Event()

        class GatedDetector(FakeDetector):
            def detect(self, image, threshold, tiled=False):
                if image.width == 110:
                    gate.wait(5)
                return super().detect(image, threshold, tiled)

        try:
            self.start(GatedDetector())
            self.wait(lambda: w.documents[0].detected)
            self.assertTrue(w.batch_running)
            self.assertFalse(w.edit_locked())
            w.mark_reviewed()
            self.assertTrue(w.documents[0].reviewed)
            w.switch_document(2)
            self.assertTrue(w.edit_locked())
            self.assertFalse(w.review_btn.isEnabled())
            gate.set()
            self.wait(lambda: not w.batch_running)
            self.assertTrue(all(d.detected for d in w.documents))
            self.assertTrue(w.documents[0].reviewed)
            self.assertTrue(all(len(d.regions) == 1 for d in w.documents))
            self.assertEqual(w.regions[0].uid, w.documents[2].regions[0].uid)
        finally:
            gate.set()

    def test_one_failure_does_not_abort_others_and_stop_retains_completed_work(self):
        w = self.w
        self.paths[1].write_bytes(b"broken PNG")
        self.start()
        self.wait(lambda: not w.batch_running)
        self.assertTrue(w.documents[0].detected)
        self.assertTrue(w.documents[1].error)
        self.assertTrue(w.documents[2].detected)
        self.assertEqual(len(w.batch_errors), 1)
        w.switch_document(1)
        self.assertIsNone(w.image)
        self.assertFalse(w.review_btn.isEnabled())
        w.remove_current_image()
        self.assertEqual(len(w.documents), 2)
        self.assertIsNotNone(w.image)

    def test_cancellation_leaves_remaining_images_retryable(self):
        w = self.w
        gate = threading.Event()

        class GatedDetector(FakeDetector):
            def detect(self, image, threshold, tiled=False):
                if image.width == 110:
                    gate.wait(5)
                return super().detect(image, threshold, tiled)

        try:
            self.start(GatedDetector())
            self.wait(lambda: w.documents[0].detected)
            w.start_batch()
            gate.set()
            self.wait(lambda: not w.batch_running)
            self.assertTrue(w.documents[0].detected)
            self.assertFalse(w.documents[2].detected)
            self.assertFalse(w.batch_pending)
            self.start()
            self.wait(lambda: not w.batch_running)
            self.assertTrue(all(d.detected for d in w.documents))
            self.assertEqual(len(w.documents[0].regions), 1)
        finally:
            gate.set()

    def test_reviewed_only_export_avoids_overwrite_and_rejects_changed_source(self):
        w = self.w
        self.start()
        self.wait(lambda: not w.batch_running)
        w.switch_document(0)
        w.mark_reviewed()
        w.mark_reviewed()
        hashes = [fingerprint(p) for p in self.paths]
        output = self.root / "export"
        output.mkdir()
        sentinel = output / "同じ名前_mosaic.png"
        sentinel.write_bytes(b"existing file")
        w.export_reviewed(output)
        self.wait(lambda: not w.export_running)
        self.assertEqual(w.export_count, 2)
        self.assertEqual(len(list(output.glob("*.png"))), 3)
        self.assertEqual(sentinel.read_bytes(), b"existing file")
        self.assertFalse(w.documents[2].exported)
        self.assertEqual(hashes, [fingerprint(p) for p in self.paths])
        Image.new("RGB", (100, 100), "red").save(self.paths[0])
        with patch.object(w, "error"):
            w.export_reviewed(output)
            self.wait(lambda: not w.export_running)
        self.assertEqual(w.export_count, 1)
        self.assertFalse(w.documents[0].reviewed)

    def test_batch_project_roundtrip_and_save_all_from_close_flow(self):
        w = self.w
        self.start()
        self.wait(lambda: not w.batch_running)
        w.mark_reviewed()
        session = self.root / "batch.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(session), "")):
            self.assertTrue(w.save_work())
        self.assertTrue(all(not d.dirty for d in w.documents))
        w.load_work(session)
        self.assertEqual(len(w.documents), 3)
        self.assertTrue(w.documents[0].reviewed)
        self.assertTrue(all(d.regions[0].contours for d in w.documents))
        self.assertEqual(len(load_session(session)), 3)

    def test_multiple_drop_and_non_current_dirty_close_prompt(self):
        w = self.w
        new = self.root / "extra.png"
        Image.new("RGB", (80, 80), "red").save(new)
        other = self.root / "extra2.png"
        Image.new("RGB", (80, 80), "blue").save(other)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in [new, other]])
        enter = QDragEnterEvent(
            QPoint(50, 50), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
        )
        self.app.sendEvent(w.canvas.viewport(), enter)
        drop = QDropEvent(
            QPointF(50, 50), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
        )
        self.app.sendEvent(w.canvas.viewport(), drop)
        self.assertEqual(len(w.documents), 5)
        w.documents[0].dirty = True
        w.dirty = False
        with patch.object(QMessageBox, "exec"), patch.object(QMessageBox, "clickedButton", return_value=None):
            self.assertFalse(w.confirm_discard())


if __name__ == "__main__":
    unittest.main()
