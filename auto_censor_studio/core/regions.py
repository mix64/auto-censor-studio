"""Region geometry and binary coverage masks, independent of the UI."""

from dataclasses import dataclass
import math
import uuid
import numpy as np

LABEL_NAMES = {"penis": "男性器", "pussy": "女性器", "manual": "手動範囲"}


@dataclass
class Region:
    x: float
    y: float
    w: float
    h: float
    label: str = "manual"
    score: float = 1.0
    uid: str = ""
    # Closed outer contours in normalized box coordinates; None is a plain rectangle.
    contours: list | None = None

    def __post_init__(self):
        if not self.uid:
            self.uid = uuid.uuid4().hex

    def rect(self):
        return self.x, self.y, self.x + self.w, self.y + self.h

    def points(self):
        return [[(self.x + u * self.w, self.y + v * self.h) for u, v in ring] for ring in (self.contours or [])]

    def set_points(self, rings):
        points = [p for ring in rings for p in ring]
        x0, y0 = min(p[0] for p in points), min(p[1] for p in points)
        x1, y1 = max(p[0] for p in points), max(p[1] for p in points)
        if x1 - x0 < 1 or y1 - y0 < 1:
            return False
        self.x, self.y, self.w, self.h = x0, y0, x1 - x0, y1 - y0
        self.contours = [[[(x - x0) / self.w, (y - y0) / self.h] for x, y in ring] for ring in rings]
        return True


def expanded_box(region, size, margin):
    width, height = size
    dx, dy = region.w * margin / 100, region.h * margin / 100
    return (
        max(0, math.floor(region.x - dx)),
        max(0, math.floor(region.y - dy)),
        min(width, math.ceil(region.x + region.w + dx)),
        min(height, math.ceil(region.y + region.h + dy)),
    )


def region_mask(region, size, margin=0):
    """Return a local binary mask and its origin. Never blend original detail at edges."""
    import cv2

    x0, y0, x1, y1 = expanded_box(region, size, margin)
    mask = np.zeros((max(0, y1 - y0), max(0, x1 - x0)), dtype=np.uint8)
    if not mask.size:
        return mask, (x0, y0)
    if not region.contours:
        mask[:] = 255
    else:
        for ring in region.points():
            points = np.rint(np.asarray(ring) - [x0, y0]).astype(np.int32)
            cv2.fillPoly(mask, [points], 255)
        # Expand the silhouette itself, not its rectangular bounding box.
        radius = math.ceil(min(region.w, region.h) * margin / 100)
        if radius:
            distance = cv2.distanceTransform(255 - mask, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
            mask = (distance <= radius).astype(np.uint8) * 255
    return mask, (x0, y0)


def region_contains(region, x, y):
    if not (region.x <= x <= region.x + region.w and region.y <= y <= region.y + region.h):
        return False
    if not region.contours:
        return True
    import cv2

    return any(
        cv2.pointPolygonTest(np.asarray(ring, dtype=np.float32), (float(x), float(y)), False) >= 0
        for ring in region.points()
    )


def region_covers(existing, candidate):
    """A contour's empty corners must not suppress a new detection on repeat runs."""
    a, (ax, ay) = region_mask(
        candidate,
        (
            math.ceil(max(existing.rect()[2], candidate.rect()[2])),
            math.ceil(max(existing.rect()[3], candidate.rect()[3])),
        ),
    )
    b, (bx, by) = region_mask(
        existing,
        (max(ax + a.shape[1], math.ceil(existing.rect()[2])), max(ay + a.shape[0], math.ceil(existing.rect()[3]))),
    )
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + a.shape[1], bx + b.shape[1]), min(ay + a.shape[0], by + b.shape[0])
    if x1 <= x0 or y1 <= y0:
        return False
    overlap = np.count_nonzero(a[y0 - ay : y1 - ay, x0 - ax : x1 - ax] & b[y0 - by : y1 - by, x0 - bx : x1 - bx])
    return overlap >= np.count_nonzero(a) * 0.995


def intersection_over_union(a, b):
    ax0, ay0, ax1, ay1 = a.rect()
    bx0, by0, bx1, by1 = b.rect()
    overlap = max(0, min(ax1, bx1) - max(ax0, bx0)) * max(0, min(ay1, by1) - max(ay0, by0))
    return overlap / max(a.w * a.h + b.w * b.h - overlap, 1e-9)


def suppress(regions, threshold=0.5):
    kept = []
    for r in sorted(regions, key=lambda x: x.score, reverse=True):
        if not any(r.label == other.label and intersection_over_union(r, other) > threshold for other in kept):
            kept.append(r)
    return kept
