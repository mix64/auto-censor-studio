"""Material 3 Expressive inspired desktop primitives; no network dependencies."""

import os
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QRectF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontDatabase, QFontMetrics
from PySide6.QtWidgets import QPushButton, QSizePolicy, QSpinBox

COLORS = {
    "primary": "#6842BE",
    "on_primary": "#FFFFFF",
    "primary_container": "#E8DDFF",
    "on_primary_container": "#33196A",
    "surface": "#FAF7FC",
    "surface_low": "#FFFBFF",
    "surface_container": "#F0EAF5",
    "surface_high": "#E8E0EE",
    "on_surface": "#282230",
    "on_surface_variant": "#706778",
    "secondary_container": "#E7DFEF",
    "accent": "#D9EDA9",
    "on_accent": "#304613",
    "outline": "#D3CADA",
    "canvas": "#EBE7EF",
}
GLYPHS = {
    "add": 0xE145,
    "select": 0xF82F,
    "auto": 0xE65F,
    "check": 0xE668,
    "next": 0xE5CC,
    "close": 0xE5CD,
    "crop": 0xE3C2,
    "delete": 0xE92E,
    "download": 0xF090,
    "expand": 0xE5CF,
    "fit": 0xEA10,
    "folder": 0xE2C8,
    "grid": 0xE9B0,
    "help": 0xE8FD,
    "image": 0xE3F4,
    "more": 0xE5D3,
    "redo": 0xE15A,
    "tune": 0xE429,
    "undo": 0xE166,
    "visibility": 0xE8F4,
    "previous": 0xE5CB,
}
_icon_family = None


def icon_font(size=23):
    global _icon_family
    if _icon_family is None:
        font_id = QFontDatabase.addApplicationFont(
            str(Path(__file__).resolve().parents[1] / "assets" / "MaterialSymbolsRounded.ttf")
        )
        families = QFontDatabase.applicationFontFamilies(font_id)
        _icon_family = families[0] if families else "Segoe UI Symbol"
    font = QFont(_icon_family)
    font.setPixelSize(size)
    font.setWeight(QFont.Weight.Medium)
    return font


def reduced_motion():
    if os.name == "nt":
        try:
            import ctypes

            enabled = ctypes.c_int(1)
            ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
            return not enabled.value
        except Exception:
            pass
    return False


class MButton(QPushButton):
    """Pill buttons with spring-like shape response, state layers and focus rings."""

    def __init__(self, text="", icon=None, role="tonal", height=48, parent=None, tip=None):
        super().__init__(text, parent)
        self.symbol = icon
        self.role = role
        self.colors = COLORS
        self._morph = 0.0
        self._hover = False
        self.setFixedHeight(height)
        self.setMinimumWidth(height if not text else 70)
        if not text:
            self.setFixedWidth(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(tip or text or icon or "操作")
        if tip:
            self.setToolTip(tip)
        self.motion = QVariantAnimation(self)
        self.motion.setDuration(280)
        # Native easing avoids a Python callback lifetime dependency in Qt.
        curve = QEasingCurve(QEasingCurve.Type.OutBack)
        curve.setOvershoot(0.85)
        self.motion.setEasingCurve(curve)
        self.motion.valueChanged.connect(self._animate)
        self.pressed.connect(lambda: self._shape_to(1.0))
        self.released.connect(lambda: self._shape_to(0.50 if self.isChecked() else 0.0))
        self.toggled.connect(lambda checked: self._shape_to(0.50 if checked else 0.0))

    def _animate(self, value):
        self._morph = float(value)
        self.update()

    def set_colors(self, colors):
        self.colors = colors
        self.update()

    def _shape_to(self, value):
        self.motion.stop()
        if reduced_motion():
            self._animate(value)
        else:
            self.motion.setStartValue(self._morph)
            self.motion.setEndValue(value)
            self.motion.start()

    def sizeHint(self):
        font = QFont(self.font())
        font.setPixelSize(14)
        width = QFontMetrics(font).horizontalAdvance(self.text()) + (28 if self.symbol else 0) + 36
        return QSize(max(self.height(), width), self.height())

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palettes = {
            "primary": ("primary", "on_primary"),
            "accent": ("accent", "on_accent"),
            "tonal": ("secondary_container", "on_surface"),
            "ghost": ("surface", "on_surface_variant"),
            "segment": ("surface_container", "on_surface_variant"),
        }
        bg, fg = (QColor(self.colors[k]) for k in palettes[self.role])
        if self.isChecked():
            bg, fg = QColor(self.colors["primary_container"]), QColor(self.colors["on_primary_container"])
        if not self.isEnabled():
            bg, fg = QColor(self.colors["surface_high"]), QColor(self.colors.get("disabled", "#A59AAD"))
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        radius = self.height() / 2 - 2 - self._morph * 10
        radius = max(10, radius)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, radius, radius)
        if self.isEnabled() and (self._hover or self.isDown()):
            layer = QColor(fg)
            layer.setAlpha(22 if self.isDown() else 13)
            painter.setBrush(layer)
            painter.drawRoundedRect(rect, radius, radius)
        if self.hasFocus() and self.isEnabled():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(self.colors["primary"]), 2))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), radius + 1, radius + 1)
        font = QFont(self.font())
        font.setPixelSize(14)
        font.setWeight(
            QFont.Weight.DemiBold if self.role in ("primary", "accent") or self.isChecked() else QFont.Weight.Medium
        )
        text_width = QFontMetrics(font).horizontalAdvance(self.text())
        total = text_width + (30 if self.symbol and self.text() else 24 if self.symbol else 0)
        x = (self.width() - total) / 2
        painter.setPen(fg)
        if self.symbol:
            painter.setFont(icon_font())
            painter.drawText(QRectF(x, 0, 24, self.height()), Qt.AlignmentFlag.AlignCenter, chr(GLYPHS[self.symbol]))
            x += 30
        painter.setFont(font)
        if self.text():
            painter.drawText(QRectF(x, 0, text_width + 2, self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())


class HoverSpinBox(QSpinBox):
    """Spin box whose step arrows appear only while the pointer is over it.

    Qt style sheets misapply ``QSpinBox:hover::up-arrow`` to the idle state, so the
    hover is exposed as the ``hovered`` property for the style sheet to select on.
    """

    def _set_hovered(self, hovered):
        self.setProperty("hovered", hovered)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def enterEvent(self, event):
        self._set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_hovered(False)
        super().leaveEvent(event)
