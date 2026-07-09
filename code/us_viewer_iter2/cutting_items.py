from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QGraphicsItem


class BoxPlusHandle(QGraphicsItem):
    def __init__(self, viewer, role, name, color, size=12):
        super().__init__()
        self.viewer = viewer
        self.role = role
        self.name = name
        self.color = QColor(color)
        self.size = size
        self._updating = False
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(60)

    def label_width(self):
        return max(44.0, float(len(self.name or "") * 8 + 14), self.size + 4.0)

    def boundingRect(self):
        width = self.label_width()
        return QRectF(-width / 2, -self.size / 2 - 2, width, self.size + 20)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self.color, 1.5))
        painter.setBrush(Qt.NoBrush)
        half = self.size / 2
        painter.drawRect(QRectF(-half, -half, self.size, self.size))
        painter.drawLine(QPointF(0, -half + 2), QPointF(0, half - 2))
        painter.drawLine(QPointF(-half + 2, 0), QPointF(half - 2, 0))
        if self.name:
            width = self.label_width()
            painter.drawText(QRectF(-width / 2, half + 2, width, 14), Qt.AlignCenter, self.name)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and not self._updating:
            if self.role == "sagittal_cut":
                return self.viewer.constrain_sagittal_cut_point(self.name, value)
            if self.role == "transverse_cut":
                return self.viewer.constrain_transverse_cut_point(self.name, value)
        if change == QGraphicsItem.ItemPositionHasChanged and not self._updating:
            if self.role == "sagittal_cut":
                self.viewer.sagittal_cut_point_moved(self.name, self.pos())
            elif self.role == "transverse_cut":
                self.viewer.transverse_cut_point_moved(self.name, self.pos())
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if self.role == "sagittal_cut":
            self.viewer.begin_sagittal_cut_drag(self.name)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.role == "sagittal_cut":
            self.viewer.end_sagittal_cut_drag()

    def set_position_silent(self, pos):
        self._updating = True
        self.setPos(pos)
        self._updating = False


class CirclePlusHandle(BoxPlusHandle):
    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self.color, 1.5))
        painter.setBrush(Qt.NoBrush)
        half = self.size / 2
        painter.drawEllipse(QRectF(-half, -half, self.size, self.size))
        painter.drawLine(QPointF(0, -half + 2), QPointF(0, half - 2))
        painter.drawLine(QPointF(-half + 2, 0), QPointF(half - 2, 0))
        if self.name:
            width = self.label_width()
            painter.drawText(QRectF(-width / 2, half + 2, width, 14), Qt.AlignCenter, self.name)
