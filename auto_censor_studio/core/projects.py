"""Validated, backward-compatible single-image project files."""

from dataclasses import asdict
from pathlib import Path
import json
import math
import os
import tempfile
import uuid
from .regions import Region, LABEL_NAMES
from .images import fingerprint, load_image, minimum_block


def save_project(path, source, regions, block, margin):
    data = {
        "version": 2,
        "source": str(Path(source).resolve()),
        "sha256": fingerprint(source),
        "regions": [asdict(r) for r in regions],
        "block": int(block),
        "margin": int(margin),
    }
    target = Path(path).resolve()
    if target == Path(source).resolve():
        raise ValueError("元画像と同じ場所には保存できません。")
    fd, temp = tempfile.mkstemp(prefix=".mosaic-project-", suffix=".json", dir=target.parent)
    os.close(fd)
    try:
        Path(temp).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, target)
    finally:
        Path(temp).unlink(missing_ok=True)


def read_project(path):
    if Path(path).stat().st_size > 16_000_000:
        raise ValueError("作業ファイルのサイズが大きすぎます。")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return read_project_data(data)


def read_project_data(data):
    if data.get("version") not in (1, 2):
        raise ValueError("この作業ファイルの形式には未対応です。")
    source = Path(data["source"])
    if fingerprint(source) != data["sha256"]:
        raise ValueError("元画像が変更されています。画像を開き直して範囲を確認してください。")
    image = load_image(source)
    block, margin = data["block"], data["margin"]
    if not isinstance(block, int) or not minimum_block(image.size) <= block <= max(1000, minimum_block(image.size)):
        raise ValueError("ブロックサイズが不正です。")
    if not isinstance(margin, int) or not 0 <= margin <= 100:
        raise ValueError("余白設定が不正です。")
    entries = data["regions"]
    if not isinstance(entries, list) or len(entries) > 1000:
        raise ValueError("範囲の件数が不正です。")
    regions = []
    for entry in entries:
        # The nipple class is never applied, even if a project file contains it.
        # Manual regions carry the "manual" label and are always kept.
        if entry.get("label") == "nipple_f":
            continue
        r = Region(**entry)
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (r.x, r.y, r.w, r.h, r.score)):
            raise ValueError("範囲の座標が不正です。")
        if not (
            0 <= r.x < image.width
            and 0 <= r.y < image.height
            and r.w > 0
            and r.h > 0
            and r.x + r.w <= image.width + 0.01
            and r.y + r.h <= image.height + 0.01
        ):
            raise ValueError("画像の外側にある範囲は読み込めません。")
        if r.label not in LABEL_NAMES or not 0 <= r.score <= 1:
            raise ValueError("範囲の種類が不正です。")
        if r.contours is not None:
            if not isinstance(r.contours, list) or not 1 <= len(r.contours) <= 64:
                raise ValueError("輪郭の形式が不正です。")
            for ring in r.contours:
                if not isinstance(ring, list) or not 3 <= len(ring) <= 2048:
                    raise ValueError("輪郭の点数が不正です。")
                for point in ring:
                    if (
                        not isinstance(point, list)
                        or len(point) != 2
                        or not all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in point)
                    ):
                        raise ValueError("輪郭の座標が不正です。")
        r.uid = uuid.uuid4().hex
        regions.append(r)
    return source, image, regions, block, margin
