"""Background jobs. Workers exchange immutable job snapshots with the UI."""

import copy
import os
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from ..core.images import fingerprint, load_image, render, atomic_export
from .detection import Detector
from .segmentation import Segmenter


class DetectionThread(QThread):
    result = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, detector, segmenter, image, threshold, tiled, parent):
        super().__init__(parent)
        self.args = detector, segmenter, image, threshold, tiled

    def run(self):
        try:
            detector, segmenter, image, threshold, tiled = self.args
            found = detector.detect(
                image, threshold, tiled=tiled, progress=lambda a, b: self.progress.emit(f"自動検出中  {a} / {b} …")
            )
            shaped = []
            for index, region in enumerate(found):
                self.progress.emit(f"輪郭を抽出中  {index + 1} / {len(found)} …")
                shaped.append(segmenter.refine(image, region))
            self.result.emit(shaped)
        except Exception as exc:
            self.failed.emit(str(exc))


class ContourThread(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, segmenter, image, region, parent):
        super().__init__(parent)
        self.args = segmenter, image, copy.deepcopy(region)

    def run(self):
        try:
            segmenter, image, region = self.args
            self.result.emit(segmenter.refine(image, region))
        except Exception as exc:
            self.failed.emit(str(exc))


class BatchWorker(QThread):
    result = Signal(str, object, str)
    progress = Signal(str, str)

    def __init__(self, jobs, parent=None, detector=None, segmenter=None):
        super().__init__(parent)
        self.jobs = jobs
        self.detector = detector or Detector()
        self.segmenter = segmenter or Segmenter()

    def run(self):
        for index, job in enumerate(self.jobs):
            if self.isInterruptionRequested():
                break
            try:
                self.progress.emit(job.uid, f"{index + 1} / {len(self.jobs)} · {job.source.name}")
                if fingerprint(job.source) != job.digest:
                    raise ValueError("元画像が変更されています。読み込み直してください。")
                image = load_image(job.source)
                found = self.detector.detect(image, job.threshold, tiled=job.tiled)
                shaped = []
                for region in found:
                    if self.isInterruptionRequested():
                        break
                    shaped.append(self.segmenter.refine(image, region))
                if self.isInterruptionRequested():
                    break
                self.result.emit(job.uid, shaped, "")
                del image
            except Exception as exc:
                self.result.emit(job.uid, [], str(exc))


class ExportWorker(QThread):
    result = Signal(str, str, str)

    def __init__(self, jobs, folder, parent=None):
        super().__init__(parent)
        self.jobs, self.folder = jobs, Path(folder)

    def run(self):
        for job in self.jobs:
            target = None
            try:
                if fingerprint(job.source) != job.digest:
                    raise ValueError("確認後に元画像が変更されています。")
                image = load_image(job.source)
                output = render(image, job.regions, job.block, job.margin)
                # Reserve a fresh filename, including for equal stems in different folders.
                suffix = 1
                while True:
                    name = job.source.stem + "_mosaic" + (f"_{suffix}" if suffix > 1 else "") + ".png"
                    candidate = self.folder / name
                    try:
                        fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                        os.close(fd)
                        target = candidate
                        break
                    except FileExistsError:
                        suffix += 1
                atomic_export(output, target, job.source)
                self.result.emit(job.uid, str(target), "")
                del image, output
            except Exception as exc:
                if target is not None:
                    target.unlink(missing_ok=True)
                self.result.emit(job.uid, "", str(exc))
