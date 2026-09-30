"""Render the editable SVG master into app PNG and multi-resolution Windows ICO."""

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def main():
    assets = Path(__file__).resolve().parents[1] / "auto_censor_studio" / "assets"
    renderer = QSvgRenderer(str(assets / "app-icon.svg"))
    if not renderer.isValid():
        raise ValueError("Invalid app icon SVG")
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    if not image.save(str(assets / "app-icon.png")):
        raise OSError("Could not write app icon PNG")
    with Image.open(assets / "app-icon.png") as png:
        png.save(
            assets / "app-icon.ico",
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )


if __name__ == "__main__":
    main()
