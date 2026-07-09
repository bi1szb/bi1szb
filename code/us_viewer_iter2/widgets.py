from pathlib import Path

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

from .config import HANDLE_RADIUS


class PlanningHandle(QGraphicsEllipseItem):
    def __init__(self, viewer, role, color):
        super().__init__(-HANDLE_RADIUS, -HANDLE_RADIUS, HANDLE_RADIUS * 2, HANDLE_RADIUS * 2)
        self.viewer = viewer
        self.role = role
        self.setBrush(color)
        self.setPen(QPen(QColor("white"), 2))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(30)
        self._updating = False

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and not self._updating:
            return self.viewer.constrain_handle_position(self.role, value)
        if change == QGraphicsItem.ItemPositionHasChanged and not self._updating:
            self.viewer.handle_moved(self.role)
        return super().itemChange(change, value)

    def set_position_silent(self, pos: QPointF):
        self._updating = True
        self.setPos(pos)
        self._updating = False


class CurrentLineHandle(QGraphicsLineItem):
    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        pen = QPen(QColor(255, 120, 0), 2)
        pen.setStyle(Qt.DashLine)
        self.setPen(pen)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setCursor(Qt.SizeHorCursor)
        self.setZValue(35)
        self._updating = False

    def set_bounds(self, top: float, bottom: float):
        self.setLine(0, top, 0, bottom)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and not self._updating:
            return self.viewer.constrain_handle_position("current", value)
        if change == QGraphicsItem.ItemPositionHasChanged and not self._updating:
            self.viewer.handle_moved("current")
        return super().itemChange(change, value)

    def set_position_silent(self, pos: QPointF):
        self._updating = True
        self.setPos(QPointF(pos.x(), 0.0))
        self._updating = False


class SagittalView(QGraphicsView):
    def __init__(self, parent):
        super().__init__()
        self.parent_window = parent
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.parent_window.fit_sagittal_view()


class ImageView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setScene(QGraphicsScene(self))
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene().addItem(self.pixmap_item)

    def set_image(self, image_path: Path):
        pixmap = QPixmap(str(image_path))
        self.pixmap_item.setPixmap(pixmap)
        self.scene().setSceneRect(QRectF(pixmap.rect()))
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.pixmap_item.pixmap().isNull():
            self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
