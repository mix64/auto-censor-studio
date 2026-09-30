"""PNG decoding, metadata removal, mosaic rendering and atomic export."""

from pathlib import Path
import hashlib
import math
import os
import tempfile
import io
from PIL import Image, ImageCms, ImageOps
from .regions import region_mask

MAX_PIXELS = 50_000_000


def minimum_block(size):
    return max(4, math.ceil(max(size) / 100))


def fingerprint(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_image(path):
    if Path(path).suffix.lower() != ".png":
        raise ValueError("PNGファイルを選んでください。")
    with Image.open(path) as file:
        if file.format != "PNG":
            raise ValueError("PNG形式の画像を選んでください。")
        if getattr(file, "n_frames", 1) != 1:
            raise ValueError("アニメーションには未対応です。静止画を書き出して開いてください。")
        if file.width * file.height > MAX_PIXELS:
            raise ValueError("画像は5,000万画素以下にしてください。")
        image = ImageOps.exif_transpose(file)
        profile = file.info.get("icc_profile")
        alpha = image.convert("RGBA").getchannel("A")
        if profile:
            try:
                image = ImageCms.profileToProfile(
                    image,
                    ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                    ImageCms.createProfile("sRGB"),
                    outputMode="RGB",
                )
            except (ValueError, OSError, ImageCms.PyCMSError):
                image = image.convert("RGB")
        else:
            image = image.convert("RGB")
        white = Image.new("RGB", image.size, "white")
        white.paste(image, (0, 0), alpha)
        # Copy pixel values only; do not propagate EXIF thumbnails or other metadata.
        return Image.frombytes("RGB", white.size, white.tobytes())


def render(image, regions, block, margin):
    """Use a single global grid, so overlapping regions cannot weaken each other."""
    block = int(block)
    if block < minimum_block(image.size):
        raise ValueError("ブロックサイズが画像サイズに対する初期目安を下回っています。")
    result = image.copy()
    if not regions:
        return result
    width, height = image.size
    padded_w = math.ceil(width / block) * block
    padded_h = math.ceil(height / block) * block
    padded = Image.new("RGB", (padded_w, padded_h))
    padded.paste(image, (0, 0))
    if padded_w > width:
        edge = image.crop((width - 1, 0, width, height))
        padded.paste(edge.resize((padded_w - width, height), Image.Resampling.NEAREST), (width, 0))
    if padded_h > height:
        edge = padded.crop((0, height - 1, padded_w, height))
        padded.paste(edge.resize((padded_w, padded_h - height), Image.Resampling.NEAREST), (0, height))
    mosaic = padded.resize((padded_w // block, padded_h // block), Image.Resampling.BOX)
    mosaic = mosaic.resize((padded_w, padded_h), Image.Resampling.NEAREST)
    for region in regions:
        mask, (x, y) = region_mask(region, image.size, margin)
        if mask.size:
            box = (x, y, x + mask.shape[1], y + mask.shape[0])
            result.paste(mosaic.crop(box), (x, y), Image.fromarray(mask))
    return result


def atomic_export(image, target, source):
    target, source = Path(target).resolve(), Path(source).resolve()
    if target == source or (target.exists() and os.path.samefile(target, source)):
        raise ValueError("元画像は上書きできません。別のファイル名を指定してください。")
    suffix = target.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("保存形式は .png または .jpg を指定してください。")
    clean = Image.frombytes("RGB", image.size, image.convert("RGB").tobytes())
    fd, name = tempfile.mkstemp(prefix=".mosaic-", suffix=suffix, dir=target.parent)
    os.close(fd)
    try:
        if suffix == ".png":
            clean.save(name, format="PNG")
        else:
            clean.save(name, format="JPEG", quality=95, subsampling=0)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)
