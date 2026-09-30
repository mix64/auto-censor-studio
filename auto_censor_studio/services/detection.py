"""Local YOLO detection; only the two supported output labels are retained."""

import math
import os
import numpy as np
from PIL import Image
from ..core.regions import Region, suppress
from ..models import verified_model

LABELS = ("nipple_f", "penis", "pussy")
DETECTION_LABELS = frozenset({"penis", "pussy"})


def decode(output, original_size, threshold, offset=(0, 0), resolution=640):
    """Decode this model's [1, 4 + 3 classes, anchors] YOLO output."""
    rows = output[0]
    if rows.ndim != 2 or rows.shape[0] != 7:
        raise ValueError(f"検出モデルの出力形式が想定と異なります: {output.shape}")
    indices = np.flatnonzero(rows[4:].max(axis=0) >= threshold)
    width, height = original_size
    found = []
    for i in indices:
        item = rows[:, i]
        label = LABELS[int(np.argmax(item[4:]))]
        if label not in DETECTION_LABELS or not np.isfinite(item).all():
            continue
        cx, cy, w, h = map(float, item[:4])
        x0, x1 = np.clip([(cx - w / 2) * width / resolution, (cx + w / 2) * width / resolution], 0, width)
        y0, y1 = np.clip([(cy - h / 2) * height / resolution, (cy + h / 2) * height / resolution], 0, height)
        if x1 > x0 and y1 > y0:
            found.append(
                Region(
                    float(x0 + offset[0]),
                    float(y0 + offset[1]),
                    float(x1 - x0),
                    float(y1 - y0),
                    label,
                    float(item[4:].max()),
                )
            )
    return suppress(found)


class Detector:
    def __init__(self):
        self.session = None

    def initialize(self):
        if self.session is None:
            model = verified_model("detector")
            import onnxruntime as ort

            ort.disable_telemetry_events()
            options = ort.SessionOptions()
            options.intra_op_num_threads = min(4, os.cpu_count() or 2)
            options.inter_op_num_threads = 1
            self.session = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])

    def detect(self, image, threshold=0.3, *, tiled=False, progress=None):
        self.initialize()
        crops = [(0, 0, image.width, image.height)]
        if tiled and max(image.size) > 900:
            # Four overlapping views plus the full image. Bounded inference time.
            cw, ch = math.ceil(image.width * 0.65), math.ceil(image.height * 0.65)
            crops += [(x, y, x + cw, y + ch) for y in (0, image.height - ch) for x in (0, image.width - cw)]
        found = []
        for index, box in enumerate(crops):
            if progress:
                progress(index + 1, len(crops))
            crop = image.crop(box)
            # Match the model publisher's default: RGB, square resize, CHW, /255.
            resized = crop.resize((640, 640), Image.Resampling.BICUBIC)
            tensor = np.asarray(resized, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
            output = self.session.run(None, {self.session.get_inputs()[0].name: tensor})[0]
            found.extend(decode(output, crop.size, threshold, offset=box[:2]))
        return suppress(found)
