"""Per-image editing state and multi-image session serialization."""

from dataclasses import dataclass, field, asdict
from pathlib import Path
import uuid
import json
import os
import tempfile
from .projects import read_project_data


@dataclass
class Document:
    source: Path
    digest: str
    block: int
    margin: int = 15
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)
    regions: list = field(default_factory=list)
    undo: list = field(default_factory=list)
    redo: list = field(default_factory=list)
    dirty: bool = False
    detected: bool = False
    reviewed: bool = False
    exported: str = ""
    error: str = ""
    notice: str = ""
    threshold: float = 0.3
    tiled: bool = True

    def title(self):
        if self.error:
            return "失敗"
        if self.exported:
            return "保存済み"
        if self.reviewed:
            return "確認済み"
        return "確認待ち" if self.detected else "未処理"


def save_session(path, documents):
    target = Path(path).resolve()
    if target in [d.source.resolve() for d in documents]:
        raise ValueError("元画像には上書きできません。")
    data = {
        "kind": "mosaic-batch",
        "version": 1,
        "documents": [
            dict(
                version=2,
                source=str(d.source),
                sha256=d.digest,
                regions=[asdict(r) for r in d.regions],
                block=d.block,
                margin=d.margin,
                reviewed=d.reviewed,
                detected=d.detected,
                threshold=d.threshold,
                tiled=d.tiled,
            )
            for d in documents
        ],
    }
    fd, temp = tempfile.mkstemp(prefix=".mosaic-batch-", suffix=".json", dir=target.parent)
    os.close(fd)
    try:
        Path(temp).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, target)
    finally:
        Path(temp).unlink(missing_ok=True)


def load_session(path):
    if Path(path).stat().st_size > 64_000_000:
        raise ValueError("作業ファイルが大きすぎます。")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("kind") != "mosaic-batch" or data.get("version") != 1:
        raise ValueError("一括作業ファイルの形式が不正です。")
    entries = data.get("documents")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 1000:
        raise ValueError("画像の件数が不正です。")
    documents = []
    for entry in entries:
        source, image, regions, block, margin = read_project_data(entry)
        threshold = entry.get("threshold", 0.3)
        if not isinstance(threshold, (float, int)) or not 0.05 <= threshold <= 0.95:
            raise ValueError("検出しきい値が不正です。")
        documents.append(
            Document(
                source.resolve(),
                entry["sha256"],
                block,
                margin,
                regions=regions,
                reviewed=entry.get("reviewed") is True,
                detected=entry.get("detected") is True,
                threshold=threshold,
                tiled=entry.get("tiled", True) is True,
            )
        )
        del image
    if len({d.source for d in documents}) != len(documents):
        raise ValueError("作業内に同じ画像が重複しています。")
    return documents
