from PyQt5.QtCore import QPointF


def qpoint_to_list(point: QPointF):
    return [round(point.x(), 3), round(point.y(), 3)]


def list_to_qpoint(values):
    return QPointF(float(values[0]), float(values[1]))
