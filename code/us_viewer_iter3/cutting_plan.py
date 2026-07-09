from dataclasses import dataclass, field

from PyQt5.QtCore import QPointF


POINT_NAMES = ["ML", "BN", "MP", "VZ", "END"]
NORMAL_ANGLES = [60.0, -60.0]
BUTTERFLY_ANGLES = [60.0, 30.0, -30.0, -60.0]
DEFAULT_CUT_DEPTH_PIXEL = 80.0
MIN_CUT_ANGLE = -115.0
MAX_CUT_ANGLE = 115.0
MIN_ANGLE_GAP = 0.1


@dataclass
class CuttingPlanPoint:
    name: str
    sagittal_point: QPointF
    transverse_index: int
    center: QPointF
    radius: float
    angles: list[float] = field(default_factory=list)
    radii: list[float] = field(default_factory=list)

    def __post_init__(self):
        if not self.radii:
            self.radii = [float(self.radius)]


def is_butterfly_name(name: str):
    return name in {"VZ", "END"}
