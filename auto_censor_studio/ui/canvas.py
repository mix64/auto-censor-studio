from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QPen, QBrush, QPixmap, QImage, QPainter, QPainterPath, QPainterPathStroker
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
)

from .theme import EmptyState, COLORS

from ..core import Region, expanded_box, region_contains


def pixmap(image):
    data = image.tobytes()
    qimage = QImage(data, image.width, image.height, image.width * 3, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimage)


class Canvas(QGraphicsView):
    edited = Signal(object)
    selection = Signal(str)
    zoomed = Signal(int)
    fileDropped = Signal(str)
    filesDropped = Signal(object)

    def __init__(self):
        super().__init__()
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.picture = self.scene_.addPixmap(QPixmap())
        self.picture.setZValue(-10)
        self.regions = []
        self.overlays = []
        self.size_ = (0, 0)
        self.selected = ""
        self.mode = "select"
        self.margin = 15
        self.outlines = True
        self.drag = None
        self.lasso = None
        self.replace_uid = ""
        self.pan = None
        self.fit_active = True
        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setBackgroundBrush(QColor(COLORS["canvas"]))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMinimumSize(420, 260)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.placeholder = EmptyState(self.viewport())

    def set_image(self, image, new=False):
        self.placeholder.hide()
        self.picture.setPixmap(pixmap(image))
        self.size_ = image.size
        self.scene_.setSceneRect(QRectF(0, 0, *image.size))
        if new:
            self.fit_image()

    def fit_image(self):
        if self.size_[0]:
            self.fitInView(self.scene_.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self.fit_active = True
            self.zoomed.emit(round(self.transform().m11() * 100))
            self.draw_regions()

    def actual_size(self):
        self.resetTransform()
        self.fit_active = False
        self.zoomed.emit(100)
        self.draw_regions()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "placeholder"):
            self.placeholder.setGeometry(self.viewport().rect())
        if self.fit_active:
            self.fit_image()

    def wheelEvent(self, event):
        if not self.size_[0]:
            return
        current = self.transform().m11()
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        target = min(12, max(0.02, current * factor))
        self.scale(target / current, target / current)
        self.fit_active = False
        self.zoomed.emit(round(target * 100))
        self.draw_regions()
        event.accept()

    def draw_regions(self):
        for item in self.overlays:
            self.scene_.removeItem(item)
        self.overlays = []
        if not self.outlines:
            return
        scale = max(self.transform().m11(), 0.001)
        for r in self.regions:
            active = r.uid == self.selected
            color = QColor("#b6f0cf" if active else "#81a8ff")
            x0, y0, x1, y1 = expanded_box(r, self.size_, self.margin)
            pen = QPen(QColor(129, 168, 255, 100), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            path = QPainterPath()
            for ring in r.points():
                path.moveTo(*ring[0])
                for point in ring[1:]:
                    path.lineTo(*point)
                path.closeSubpath()
            if r.contours:
                stroke = QPainterPathStroker()
                stroke.setWidth(2 * min(r.w, r.h) * self.margin / 100)
                stroke.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                outer_path = path.united(stroke.createStroke(path)) if self.margin else path
                outer = self.scene_.addPath(outer_path, pen)
            else:
                outer = self.scene_.addRect(QRectF(x0, y0, x1 - x0, y1 - y0), pen)
            self.overlays.append(outer)
            pen = QPen(color, 2 if active else 1.5)
            pen.setCosmetic(True)
            rect = (
                self.scene_.addPath(path, pen) if r.contours else self.scene_.addRect(QRectF(r.x, r.y, r.w, r.h), pen)
            )
            self.overlays.append(rect)
            if active:
                handles = (
                    [point for ring in r.points() for point in ring]
                    if r.contours
                    else [(r.x, r.y), (r.x + r.w, r.y), (r.x, r.y + r.h), (r.x + r.w, r.y + r.h)]
                )
                for x, y in handles:
                    handle = self.scene_.addRect(
                        QRectF(x - 4 / scale, y - 4 / scale, 8 / scale, 8 / scale),
                        QPen(Qt.PenStyle.NoPen),
                        QBrush(color),
                    )
                    self.overlays.append(handle)
        if self.lasso:
            path = QPainterPath(QPointF(*self.lasso[0]))
            for point in self.lasso[1:]:
                path.lineTo(*point)
            pen = QPen(QColor("#CFB8FF"), 2)
            pen.setCosmetic(True)
            self.overlays.append(self.scene_.addPath(path, pen))

    def select(self, uid):
        self.selected = uid
        self.draw_regions()
        self.selection.emit(uid)

    def bound(self, point):
        return QPointF(min(self.size_[0], max(0, point.x())), min(self.size_[1], max(0, point.y())))

    def mousePressEvent(self, event):
        if not self.size_[0] or not self.isEnabled():
            return super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.pan = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        if not self.outlines:
            return
        point = self.mapToScene(event.position().toPoint())
        if not QRectF(0, 0, *self.size_).contains(point):
            return
        before = copy.deepcopy(self.regions)
        if self.mode == "lasso":
            self.lasso = [(point.x(), point.y())]
            self.lasso_before = before
            return
        if self.mode == "draw":
            r = Region(point.x(), point.y(), 0, 0)
            self.regions.append(r)
            self.select(r.uid)
            self.drag = ("draw", r, point, copy.deepcopy(r), before, None)
            return
        selected = next((r for r in self.regions if r.uid == self.selected), None)
        if selected:
            if selected.contours:
                radius = 7 / self.transform().m11()
                for ring_index, ring in enumerate(selected.points()):
                    for point_index, (x, y) in enumerate(ring):
                        if abs(point.x() - x) <= radius and abs(point.y() - y) <= radius:
                            self.drag = (
                                "vertex",
                                selected,
                                point,
                                copy.deepcopy(selected),
                                before,
                                (ring_index, point_index),
                            )
                            return
            corners = [
                (selected.x, selected.y),
                (selected.x + selected.w, selected.y),
                (selected.x, selected.y + selected.h),
                (selected.x + selected.w, selected.y + selected.h),
            ]
            radius = 12 / self.transform().m11()
            for i, (x, y) in enumerate([] if selected.contours else corners):
                if abs(point.x() - x) <= radius and abs(point.y() - y) <= radius:
                    anchor = QPointF(*corners[3 - i])
                    self.drag = ("resize", selected, point, copy.deepcopy(selected), before, anchor)
                    return
        hit = next((r for r in reversed(self.regions) if region_contains(r, point.x(), point.y())), None)
        self.select(hit.uid if hit else "")
        if hit:
            self.drag = ("move", hit, point, copy.deepcopy(hit), before, None)

    def mouseMoveEvent(self, event):
        if self.pan is not None:
            delta = event.position() - self.pan
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            self.pan = event.position()
            return
        if self.lasso is not None:
            point = self.bound(self.mapToScene(event.position().toPoint()))
            last = QPointF(*self.lasso[-1])
            if (point - last).manhattanLength() * self.transform().m11() >= 2:
                self.lasso.append((point.x(), point.y()))
            self.draw_regions()
            return
        if self.drag:
            mode, r, start, old, before, anchor = self.drag
            point = self.bound(self.mapToScene(event.position().toPoint()))
            if mode == "vertex":
                rings = old.points()
                rings[anchor[0]][anchor[1]] = (point.x(), point.y())
                r.set_points(rings)
            elif mode == "move":
                r.x = min(self.size_[0] - r.w, max(0, old.x + point.x() - start.x()))
                r.y = min(self.size_[1] - r.h, max(0, old.y + point.y() - start.y()))
            else:
                origin = anchor if mode == "resize" else start
                rect = QRectF(origin, point).normalized()
                r.x, r.y, r.w, r.h = rect.x(), rect.y(), rect.width(), rect.height()
            self.draw_regions()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton and self.pan is None:
            return super().mouseReleaseEvent(event)
        if self.pan is not None:
            self.pan = None
            self.unsetCursor()
            return
        if self.lasso is not None:
            import cv2
            import numpy as np

            point = self.bound(self.mapToScene(event.position().toPoint()))
            self.lasso.append((point.x(), point.y()))
            points = np.asarray(self.lasso, dtype=np.float32)
            self.lasso = None
            if len(points) >= 3 and abs(cv2.contourArea(points)) >= 4:
                simplified = cv2.approxPolyDP(points, max(0.5, 1 / self.transform().m11()), True).reshape(-1, 2)
                if 3 <= len(simplified) <= 2048:
                    r = next((r for r in self.regions if r.uid == self.replace_uid), None)
                    new = r is None
                    r = r or Region(0, 0, 1, 1)
                    if r.set_points([simplified.tolist()]):
                        if new:
                            self.regions.append(r)
                        self.select(r.uid)
                        self.edited.emit(self.lasso_before)
            self.replace_uid = ""
            self.draw_regions()
            return
        if self.drag:
            mode, r, _, old, before, _ = self.drag
            self.drag = None
            if r.w < 2 or r.h < 2:
                if mode == "draw":
                    self.regions.remove(r)
                    self.selected = ""
                else:
                    r.x, r.y, r.w, r.h = old.x, old.y, old.w, old.h
            self.draw_regions()
            if self.regions != before:
                self.edited.emit(before)
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
