"""Box-prompted MobileSAM contour extraction, entirely on the local CPU."""

import copy
import math
import os
import cv2
import numpy as np
from PIL import Image
from ..models import verified_model


class Segmenter:
    def __init__(self):
        self.encoder = self.decoder = None

    def initialize(self):
        if self.encoder is not None and self.decoder is not None:
            return
        import onnxruntime as ort

        ort.disable_telemetry_events()
        sessions = []
        for key in ("encoder", "decoder"):
            path = verified_model(key)
            options = ort.SessionOptions()
            options.intra_op_num_threads = min(4, os.cpu_count() or 2)
            options.inter_op_num_threads = 1
            sessions.append(ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"]))
        self.encoder, self.decoder = sessions

    def refine(self, image, region):
        self.initialize()
        result = copy.deepcopy(region)
        # Local context keeps small parts detailed even on very large illustrations.
        pad = max(region.w, region.h) * 0.65
        x0, y0 = max(0, math.floor(region.x - pad)), max(0, math.floor(region.y - pad))
        x1, y1 = (
            min(image.width, math.ceil(region.x + region.w + pad)),
            min(image.height, math.ceil(region.y + region.h + pad)),
        )
        crop = image.crop((x0, y0, x1, y1))
        scale = 1024 / max(crop.size)
        width, height = max(1, int(crop.width * scale + 0.5)), max(1, int(crop.height * scale + 0.5))
        # This encoder includes channel normalization and padding. Input is RGB 0..255 HWC.
        rgb = np.asarray(crop.resize((width, height), Image.Resampling.BILINEAR), dtype=np.float32)
        embedding = self.encoder.run(None, {"input_image": rgb})[0]
        coords = np.array(
            [[[region.x - x0, region.y - y0], [region.x + region.w - x0, region.y + region.h - y0], [0, 0]]], np.float32
        )
        coords *= [width / crop.width, height / crop.height]
        # Two box corners (2,3) plus a padding prompt (-1), no invented foreground click.
        masks, scores, _ = self.decoder.run(
            None,
            {
                "image_embeddings": embedding,
                "point_coords": coords,
                "point_labels": np.array([[2, 3, -1]], np.float32),
                "mask_input": np.zeros((1, 1, 256, 256), np.float32),
                "has_mask_input": np.zeros(1, np.float32),
                # Decode at bounded resolution before scaling contours back to the original.
                "orig_im_size": np.array([height, width], np.float32),
            },
        )
        mask = (masks[0, 0] > 0).astype(np.uint8)
        # Reject empty/uncertain masks rather than silently removing coverage.
        if not np.isfinite(scores).all() or float(scores.flat[0]) < 0.60 or np.count_nonzero(mask) < 9:
            return result
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rings = []
        for contour in contours:
            if cv2.contourArea(contour) < 4:
                continue
            # Keep all meaningful islands; fill interior holes so fine details cannot leak.
            epsilon = 1.5
            simplified = cv2.approxPolyDP(contour, epsilon, True)
            while len(simplified) > 96:
                epsilon *= 1.5
                simplified = cv2.approxPolyDP(contour, epsilon, True)
            if len(simplified) >= 3:
                rings.append(
                    [
                        (float(x) * crop.width / width + x0, float(y) * crop.height / height + y0)
                        for x, y in simplified[:, 0]
                    ]
                )
        if rings and len(rings) <= 64:
            result.set_points(rings)
        return result
