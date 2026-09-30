"""Pinned model registry and explicit, checksum-verified setup downloads."""

from dataclasses import dataclass
from pathlib import Path
import argparse
import os
import tempfile
from urllib.request import urlopen

from .core.images import fingerprint
from .paths import model_directory


@dataclass(frozen=True)
class ModelSpec:
    filename: str
    url: str
    sha256: str
    megabytes: int = 0


SAM_BASE = "https://huggingface.co/Acly/MobileSAM/resolve/0d3b403339b4674a82493d5e97964dd78089ddc8"
MODELS = {
    "detector": ModelSpec(
        "anime-censor-v1-s.onnx",
        "https://huggingface.co/deepghs/anime_censor_detection/resolve/0cf62fd6b28213b40ae0c0055f92e7ae6a96bdc2/censor_detect_v1.0_s/model.onnx",
        "2c2524824d7d320c5619a0a73702a2e2186f619067c823d211e94f7cfe489cba",
        45,
    ),
    "encoder": ModelSpec(
        "mobile_sam_image_encoder.onnx",
        f"{SAM_BASE}/mobile_sam_image_encoder.onnx",
        "580f5fb648ea1062c0aabc26217aed56921985f03f0cbbd852bba81d760cc749",
        28,
    ),
    "decoder": ModelSpec(
        "sam_mask_decoder_single.onnx",
        f"{SAM_BASE}/sam_mask_decoder_single.onnx",
        "93915fc7c993ab9d59ab8c9ccd3bce37f7509c81ab4150a74abd4d2abbd8570d",
        17,
    ),
}


def verified_model(key):
    spec = MODELS[key]
    target = model_directory() / spec.filename
    if not target.is_file() or fingerprint(target) != spec.sha256:
        raise ValueError(f"モデルが未準備または破損しています: {spec.filename}\nアプリを起動し直してください。")
    return target


def missing_models(directory=None):
    target_dir = Path(directory) if directory else model_directory()
    return [
        spec
        for spec in MODELS.values()
        if not (target_dir / spec.filename).is_file() or fingerprint(target_dir / spec.filename) != spec.sha256
    ]


def download_models(directory=None, should_stop=None):
    target_dir = Path(directory) if directory else model_directory()
    target_dir.mkdir(parents=True, exist_ok=True)
    for spec in MODELS.values():
        target = target_dir / spec.filename
        if target.is_file() and fingerprint(target) == spec.sha256:
            print(f"Verified: {spec.filename}")
            continue
        fd, temporary = tempfile.mkstemp(prefix=".download-", dir=target_dir)
        try:
            with os.fdopen(fd, "wb") as output, urlopen(spec.url, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    if should_stop and should_stop():
                        raise InterruptedError("Download cancelled")
                    output.write(chunk)
            if fingerprint(temporary) != spec.sha256:
                raise ValueError(f"Checksum mismatch: {spec.filename}")
            os.replace(temporary, target)
            print(f"Downloaded and verified: {spec.filename}")
        finally:
            Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, help="Override model download destination")
    args = parser.parse_args()
    download_models(args.directory)


if __name__ == "__main__":
    main()
