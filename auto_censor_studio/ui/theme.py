"""Material 3 Expressive colors for the compact, single-toolbar editor."""

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QSizePolicy
from .widgets import MButton

THEMES = {
    False: dict(
        primary="#6842BE",
        on_primary="#FFFFFF",
        primary_container="#E8DDFF",
        on_primary_container="#33196A",
        surface="#FAF7FC",
        surface_low="#FFFBFF",
        surface_container="#F0EAF5",
        surface_high="#E8E0EE",
        canvas="#F0EAF5",
        on_surface="#282230",
        on_surface_variant="#706778",
        secondary_container="#E7DFEF",
        outline="#D3CADA",
        disabled="#8C8296",
    ),
    True: dict(
        primary="#CFB8FF",
        on_primary="#391B72",
        primary_container="#51308E",
        on_primary_container="#EBDDFF",
        surface="#17131C",
        surface_low="#1F1A25",
        surface_container="#241E2C",
        surface_high="#302937",
        canvas="#211C28",
        on_surface="#EBE1F2",
        on_surface_variant="#CBC1D3",
        secondary_container="#3E344B",
        outline="#51465D",
        disabled="#8F849B",
    ),
}
COLORS = THEMES[False]


class EmptyState(QLabel):
    def __init__(self, parent=None):
        super().__init__("PNGをドロップ、または「開く」で選択", parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setObjectName("placeholder")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


class ElideLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(20)
        self.setObjectName("secondaryText")

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        text = self.fontMetrics().elidedText(self.text().replace("\n", "  "), Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignVCenter, text)


BASE_STYLE = """
QWidget { font-family: 'Yu Gothic UI', 'Segoe UI'; font-size: 14px; }
QLabel { background: transparent; }
QLabel#secondaryText { font-size: 12px; }
QSpinBox, QDoubleSpinBox { min-height: 24px; border: 2px solid transparent; border-radius: 12px; padding: 6px 8px; }
QSpinBox::up-button, QSpinBox::down-button { subcontrol-origin: border; width: 18px; border: none; border-radius: 6px; background: transparent; }
QSpinBox::up-button { subcontrol-position: top right; margin: 4px 4px 0 0; }
QSpinBox::down-button { subcontrol-position: bottom right; margin: 0 4px 4px 0; }
QSpinBox::up-arrow, QSpinBox::down-arrow { image: none; width: 12px; height: 12px; }
QMenu { padding: 8px; border-radius: 16px; }
QMenu::item { padding: 10px 20px; border-radius: 10px; }
QMenu::indicator { width: 18px; height: 18px; }
QCheckBox { spacing: 10px; padding: 6px 0; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; }
QProgressBar { border: none; border-radius: 2px; }
QProgressBar::chunk { border-radius: 2px; }
QPushButton { min-height: 24px; border: none; border-radius: 16px; padding: 8px 16px; }
QScrollBar:vertical { width: 10px; margin: 2px; }
QScrollBar:horizontal { height: 10px; margin: 2px; }
QScrollBar::handle { border-radius: 4px; min-width: 24px; min-height: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip { padding: 8px 12px; border-radius: 8px; }
"""


def theme_style(dark):
    c = THEMES[bool(dark)]
    check = (
        Path(__file__).resolve().parents[1] / "assets" / ("check-dark.svg" if dark else "check-white.svg")
    ).as_posix()
    arrow = (
        Path(__file__).resolve().parents[1] / "assets" / ("expand-dark.svg" if dark else "expand-light.svg")
    ).as_posix()
    up = (
        Path(__file__).resolve().parents[1] / "assets" / ("collapse-dark.svg" if dark else "collapse-light.svg")
    ).as_posix()
    return (
        BASE_STYLE
        + f"""
QWidget {{ color: {c["on_surface"]}; }}
QMainWindow, QDialog {{ background: {c["surface"]}; }}
QFrame#stage {{ background: {c["canvas"]}; border-radius: 24px; }}
QGraphicsView {{ background: {c["canvas"]}; border: none; }}
QLabel#placeholder, QLabel#secondaryText {{ color: {c["on_surface_variant"]}; }}
QSpinBox, QDoubleSpinBox {{ background: {c["secondary_container"]}; color: {c["on_surface"]}; selection-background-color: {c["primary"]}; selection-color: {c["on_primary"]}; }}
QComboBox {{ background: {c["surface_container"]}; color: {c["on_surface"]}; border: 1px solid {c["outline"]}; border-radius: 12px; padding: 4px 10px; }}
QComboBox:focus {{ border-color: {c["primary"]}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{ image: url({arrow}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {c["surface_container"]}; color: {c["on_surface"]}; selection-background-color: {c["primary_container"]}; selection-color: {c["on_primary_container"]}; padding: 6px; }}
QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {c["primary"]}; }}
QSpinBox[hovered="true"]::up-arrow {{ image: url({up}); }}
QSpinBox[hovered="true"]::down-arrow {{ image: url({arrow}); }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {c["primary_container"]}; }}
QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {c["disabled"]}; background: {c["surface_high"]}; }}
QPushButton {{ background: {c["secondary_container"]}; }}
QPushButton:hover, QPushButton:checked {{ background: {c["primary_container"]}; color: {c["on_primary_container"]}; }}
QPushButton:focus {{ border: 2px solid {c["primary"]}; }}
QPushButton:disabled {{ color: {c["disabled"]}; background: {c["surface_high"]}; }}
QMenu {{ background: {c["surface_container"]}; color: {c["on_surface"]}; border: 1px solid {c["outline"]}; }}
QMenu::item:selected {{ background: {c["primary_container"]}; color: {c["on_primary_container"]}; }}
QMenu::item:disabled {{ color: {c["disabled"]}; }}
QMenu::separator {{ height: 1px; background: {c["outline"]}; margin: 5px 12px; }}
QCheckBox::indicator {{ border: 2px solid {c["on_surface_variant"]}; }}
QCheckBox::indicator:checked {{ background: {c["primary"]}; border-color: {c["primary"]}; image: url({check}); }}
QCheckBox:focus {{ color: {c["primary"]}; }}
QProgressBar {{ background: {c["primary_container"]}; }}
QProgressBar::chunk {{ background: {c["primary"]}; }}
QScrollBar {{ background: {c["canvas"]}; }}
QScrollBar::handle {{ background: {c["outline"]}; }}
QToolTip {{ background: {c["on_surface"]}; color: {c["surface"]}; border: none; }}
"""
    )


STYLE = theme_style(False)


def apply_theme(window, dark):
    """Color the application chrome without modifying image pixels or edit state."""
    c = THEMES[bool(dark)]
    palette = QPalette()
    roles = {
        "Window": c["surface"],
        "WindowText": c["on_surface"],
        "Base": c["surface_low"],
        "AlternateBase": c["surface_container"],
        "Text": c["on_surface"],
        "Button": c["secondary_container"],
        "ButtonText": c["on_surface"],
        "ToolTipBase": c["on_surface"],
        "ToolTipText": c["surface"],
        "BrightText": "#FFFFFF",
        "Highlight": c["primary"],
        "HighlightedText": c["on_primary"],
        "Link": c["primary"],
        "PlaceholderText": c["on_surface_variant"],
        "Light": c["surface_high"],
        "Midlight": c["surface_container"],
        "Mid": c["outline"],
        "Dark": c["outline"],
        "Shadow": "#111111",
    }
    for role, color in roles.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in ("WindowText", "Text", "ButtonText"):
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), QColor(c["disabled"]))
    application = QApplication.instance()
    application.setPalette(palette)
    application.setStyleSheet(theme_style(dark))
    for button in window.findChildren(MButton):
        button.set_colors(c)
    window.canvas.setBackgroundBrush(QColor(c["canvas"]))
    window.canvas.viewport().update()
    # Color only this application's own title bars on supported Windows versions.
    if application.platformName() == "windows":
        try:
            import ctypes

            value = ctypes.c_int(bool(dark))
            for widget in (window, window.detection_dialog):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(int(widget.winId())), 20, ctypes.byref(value), ctypes.sizeof(value)
                )
        except (AttributeError, OSError):
            pass
