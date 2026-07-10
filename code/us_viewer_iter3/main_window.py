import json
import math
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QImage, QPen, QPixmap, QBrush, QPainterPath
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QInputDialog,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .config import DEFAULT_SCALE_NUMERATOR, MAJOR_TICK_UNITS, parse_depth_and_scale
from .cutting_items import BoxPlusHandle, CirclePlusHandle
from .cutting_plan import (
    BUTTERFLY_ANGLES,
    DEFAULT_CUT_DEPTH_PIXEL,
    MAX_CUT_ANGLE,
    MIN_ANGLE_GAP,
    MIN_CUT_ANGLE,
    NORMAL_ANGLES,
    POINT_NAMES,
    CuttingPlanPoint,
    is_butterfly_name,
)
from .dataset_io import find_patient_dirs, find_sagittal_image, find_transverse_images
from .serialization import list_to_qpoint, qpoint_to_list
from .widgets import CurrentLineHandle, ImageView, PlanningHandle, SagittalView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("术中前列腺超声可视化工具 v3")
        self.resize(1500, 850)

        self.dataset_dir = None
        self.patient_dirs = []
        self.patient_index = -1
        self.sagittal_path = None
        self.transverse_paths = []

        self.line_start = None
        self.line_end = None
        self.zero_point = None
        self.planning_length_pixel = None
        self.depth = None
        self.scale_numerator = DEFAULT_SCALE_NUMERATOR
        self.scale_10mm_pixel = None
        self.tick_pixel_step = 10.0
        self.t_values = {"zero": 0.0, "start": 0.0, "current": 0.5, "end": 1.0}
        self.scale_confirmed = False
        self.cut_plan = {}
        self.selected_cut_name = ""
        self.cut_sagittal_items = []
        self.cut_sagittal_handles = {}
        self.cut_transverse_items = []
        self.cut_transverse_handles = {}
        self._updating_cut_panel = False
        self.mask_visible = False
        self.mask_data = None
        self.mask_patient_id = None
        self.mask_item = None
        self._dragging_sagittal_cut = False
        self._active_sagittal_cut_name = None
        self._cut_save_pending = False

        self.sagittal_scene = QGraphicsScene(self)
        self.sagittal_pixmap_item = QGraphicsPixmapItem()
        self.sagittal_scene.addItem(self.sagittal_pixmap_item)

        self.line_item = None
        self.tick_items = []
        self.handles = {}

        self.sagittal_view = SagittalView(self)
        self.sagittal_view.setScene(self.sagittal_scene)
        self.transverse_view = ImageView()

        self.patient_label = QLabel("未加载")
        self.patient_label.setMinimumWidth(260)
        self.slice_label = QLabel("")
        self.transverse_name_label = QLabel("")
        self.transverse_name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.hint_label = QLabel("")

        load_button = QPushButton("加载文件夹")
        prev_button = QPushButton("上一例")
        next_button = QPushButton("下一例")
        init_button = QPushButton("初始化刻度线")
        load_button.clicked.connect(self.load_folder)
        prev_button.clicked.connect(self.prev_patient)
        next_button.clicked.connect(self.next_patient)
        init_button.clicked.connect(self.start_init_line)
        confirm_scale_button = QPushButton("确认刻度线")
        init_cut_button = QPushButton("初始化切割区域")
        import_cut_button = QPushButton("导入规划JSON")
        mask_button = QPushButton("显示mask")
        mask_button.setCheckable(True)
        confirm_scale_button.clicked.connect(self.confirm_scale_line)
        init_cut_button.clicked.connect(self.initialize_cutting_plan)
        import_cut_button.clicked.connect(self.import_cutting_json)
        mask_button.toggled.connect(self.toggle_mask_overlay)

        toolbar = QHBoxLayout()
        toolbar.addWidget(load_button)
        toolbar.addWidget(prev_button)
        toolbar.addWidget(next_button)
        toolbar.addWidget(init_button)
        toolbar.addWidget(confirm_scale_button)
        toolbar.addWidget(init_cut_button)
        toolbar.addWidget(import_cut_button)
        toolbar.addWidget(mask_button)
        toolbar.addSpacing(20)
        toolbar.addWidget(self.patient_label)
        toolbar.addWidget(self.slice_label)
        toolbar.addStretch()
        toolbar.addWidget(self.hint_label)

        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("矢状面"))
        left_panel.addWidget(self.sagittal_view, 1)

        right_panel = QVBoxLayout()
        right_panel.addWidget(QLabel("横断面"))
        right_panel.addWidget(self.transverse_name_label)
        right_panel.addWidget(self.transverse_view, 1)

        self.cut_point_combo = QComboBox()
        self.cut_index_spin = QSpinBox()
        self.cut_index_spin.setMinimum(1)
        self.cut_center_x_spin = QDoubleSpinBox()
        self.cut_center_y_spin = QDoubleSpinBox()
        self.cut_radius_spin = QDoubleSpinBox()
        self.cut_angle_spins = [QDoubleSpinBox() for _ in range(4)]
        for spin in [self.cut_center_x_spin, self.cut_center_y_spin, self.cut_radius_spin, *self.cut_angle_spins]:
            spin.setRange(-10000.0, 10000.0)
            spin.setDecimals(2)
        self.cut_radius_spin.setMinimum(1.0)
        self.cut_radius_spin.setMaximum(10000.0)
        for spin in self.cut_angle_spins:
            spin.setRange(MIN_CUT_ANGLE, MAX_CUT_ANGLE)
        self.cut_point_combo.currentTextChanged.connect(self.select_cut_point)
        self.cut_index_spin.valueChanged.connect(self.apply_cut_panel_values)
        self.cut_center_x_spin.valueChanged.connect(self.apply_cut_panel_values)
        self.cut_center_y_spin.valueChanged.connect(self.apply_cut_panel_values)
        self.cut_radius_spin.valueChanged.connect(self.apply_cut_panel_values)
        for spin in self.cut_angle_spins:
            spin.valueChanged.connect(self.apply_cut_panel_values)

        cut_form = QFormLayout()
        cut_form.addRow("Point", self.cut_point_combo)
        cut_form.addRow("Transverse", self.cut_index_spin)
        cut_form.addRow("Center X", self.cut_center_x_spin)
        cut_form.addRow("Center Y", self.cut_center_y_spin)
        cut_form.addRow("Radius", self.cut_radius_spin)
        for idx, spin in enumerate(self.cut_angle_spins, start=1):
            cut_form.addRow(f"Angle {idx}", spin)
        right_panel.addLayout(cut_form)

        content = QHBoxLayout()
        content.addLayout(left_panel, 1)
        content.addLayout(right_panel, 1)

        root = QVBoxLayout()
        root.addLayout(toolbar)
        root.addLayout(content, 1)

        widget = QWidget()
        widget.setLayout(root)
        self.setCentralWidget(widget)
        self.setStatusBar(QStatusBar())

    def load_folder(self):
        initial = str(Path.cwd() / "dataset") if (Path.cwd() / "dataset").exists() else str(Path.cwd())
        selected = QFileDialog.getExistingDirectory(self, "选择 dataset 文件夹", initial)
        if selected:
            self.open_dataset(Path(selected))

    def open_dataset(self, dataset_dir: Path):
        self.save_current_patient_state()
        patient_dirs = find_patient_dirs(dataset_dir)
        if not patient_dirs:
            QMessageBox.warning(self, "未找到数据", "所选文件夹下没有可用病人目录。")
            return
        self.dataset_dir = dataset_dir
        self.patient_dirs = patient_dirs
        self.patient_index = 0
        self.load_patient()

    def load_patient(self):
        if not self.patient_dirs:
            return
        patient_dir = self.patient_dirs[self.patient_index]
        self.sagittal_path = find_sagittal_image(patient_dir)
        self.transverse_paths = find_transverse_images(patient_dir)
        self.clear_overlay()

        pixmap = QPixmap(str(self.sagittal_path))
        self.sagittal_pixmap_item.setPixmap(pixmap)
        self.sagittal_scene.setSceneRect(QRectF(pixmap.rect()))
        self.fit_sagittal_view()

        self.patient_label.setText(f"{patient_dir.name}  ({self.patient_index + 1}/{len(self.patient_dirs)})")
        self.statusBar().showMessage(str(patient_dir), 5000)
        self.load_planning_json()
        self.load_cutting_json()
        self.update_transverse_image()

    def fit_sagittal_view(self):
        if not self.sagittal_pixmap_item.pixmap().isNull():
            self.sagittal_view.fitInView(self.sagittal_scene.sceneRect(), Qt.KeepAspectRatio)

    def prev_patient(self):
        if not self.patient_dirs:
            return
        self.save_current_patient_state()
        self.patient_index = (self.patient_index - 1) % len(self.patient_dirs)
        self.load_patient()

    def next_patient(self):
        if not self.patient_dirs:
            return
        self.save_current_patient_state()
        self.patient_index = (self.patient_index + 1) % len(self.patient_dirs)
        self.load_patient()

    def start_init_line(self):
        if not self.sagittal_path:
            QMessageBox.information(self, "提示", "请先加载 dataset 文件夹。")
            return
        depth, ok = QInputDialog.getText(self, "输入 depth", "请输入depth（可选：depth,系数；默认系数790）")
        if not ok:
            return
        depth = depth.strip()
        if not depth:
            QMessageBox.warning(self, "输入无效", "depth 不能为空。")
            return
        try:
            depth_value, scale_numerator, scale_10mm_pixel = parse_depth_and_scale(depth)
        except Exception as exc:
            QMessageBox.warning(self, "输入无效", f"无法根据输入计算 scale_10mm_pixel。\n{exc}")
            return

        rect = self.sagittal_scene.sceneRect()
        zero = QPointF(rect.width() / 6.0, rect.height() / 2.0)
        start = QPointF(rect.width() / 3.0, rect.height() / 2.0)
        direction = QPointF(start.x() - zero.x(), start.y() - zero.y())
        if math.hypot(direction.x(), direction.y()) < 1e-9:
            QMessageBox.warning(self, "初始化失败", "无法根据默认点生成方向。")
            return

        self.depth = depth_value
        self.scale_numerator = scale_numerator
        self.scale_10mm_pixel = scale_10mm_pixel
        self.tick_pixel_step = scale_10mm_pixel / 10.0
        self.planning_length_pixel = self.tick_pixel_step * len(self.transverse_paths)
        sign = 1.0 if direction.x() >= 0 else -1.0
        end_x = zero.x() + sign * self.planning_length_pixel
        slope = direction.y() / direction.x() if abs(direction.x()) > 1e-9 else 0.0
        end = QPointF(end_x, zero.y() + slope * (end_x - zero.x()))

        self.zero_point = zero
        self.scale_confirmed = False
        self.clear_cutting_overlay()
        self.hint_label.setText(f"规划线已初始化：depth={depth_value:g}, scale_10mm_pixel={scale_10mm_pixel:g}")
        self.statusBar().showMessage("规划线已按 depth 自动初始化，可拖动零点、起点和当前虚线。")
        self.set_planning_line(start, end, reset_handles=True)
        self.save_planning_json()

    def confirm_scale_line(self):
        if self.line_start is None or self.line_end is None or self.zero_point is None:
            QMessageBox.information(self, "提示", "请先初始化刻度线。")
            return
        self.scale_confirmed = True
        self.statusBar().showMessage("刻度线已确认，可以初始化切割区域。", 5000)

    def cut_point_names(self):
        return list(self.cut_plan.keys())

    def ordered_cut_points(self):
        names = self.cut_point_names()
        return sorted(self.cut_plan.items(), key=lambda item: (item[1].transverse_index, names.index(item[0])))

    def refresh_cut_point_combo(self):
        current = self.selected_cut_name
        self._updating_cut_panel = True
        try:
            self.cut_point_combo.blockSignals(True)
            self.cut_point_combo.clear()
            self.cut_point_combo.addItems(self.cut_point_names())
            if current in self.cut_plan:
                self.cut_point_combo.setCurrentText(current)
            elif self.cut_plan:
                self.selected_cut_name = self.cut_point_names()[0]
                self.cut_point_combo.setCurrentText(self.selected_cut_name)
            else:
                self.selected_cut_name = ""
        finally:
            self.cut_point_combo.blockSignals(False)
            self._updating_cut_panel = False

    def is_butterfly_point(self, point: CuttingPlanPoint):
        return len(point.angles) == 4 or len(getattr(point, "radii", [])) == 2

    def default_angles_for_name(self, name: str):
        return BUTTERFLY_ANGLES.copy() if is_butterfly_name(name) else NORMAL_ANGLES.copy()

    def x_for_transverse_index(self, index: int):
        return self.point_at_zero_distance(index * max(float(self.tick_pixel_step), 1.0)).x()

    def sagittal_point_from_transverse(self, index: int, radius: float):
        x = self.x_for_transverse_index(index)
        return QPointF(x, self.baseline_y_at_x(x) + self.clamp_cut_radius(radius))

    def initialize_cutting_plan(self):
        if not self.scale_confirmed:
            QMessageBox.information(self, "提示", "请先确认刻度线。")
            return
        if self.line_start is None or self.line_end is None:
            return
        center = self.default_transverse_center()
        sign = self.horizontal_sign()
        start_x = self.line_start.x()
        span = abs(self.line_end.x() - self.line_start.x())
        self.cut_plan = {}
        for idx, name in enumerate(POINT_NAMES):
            x = start_x + sign * span * (idx + 1) / (len(POINT_NAMES) + 1)
            radius = self.clamp_cut_radius(DEFAULT_CUT_DEPTH_PIXEL)
            y = self.baseline_y_at_x(x) + radius
            sagittal_point = QPointF(x, y)
            angles = self.normalize_cut_angles(self.default_angles_for_name(name))
            self.cut_plan[name] = CuttingPlanPoint(
                name=name,
                sagittal_point=sagittal_point,
                transverse_index=self.current_index_from_x(x),
                center=QPointF(center),
                radius=radius,
                angles=angles,
                radii=self.normalize_cut_radii(radius, 2 if is_butterfly_name(name) else 1),
            )
        self.selected_cut_name = "ML"
        self.refresh_cut_point_combo()
        self.redraw_cutting_overlay()
        self.update_cut_panel()
        self.update_transverse_cut_overlay()
        self.save_cutting_json()

    def set_planning_line(self, start: QPointF, end: QPointF, reset_handles=False):
        self.line_start = start
        self.line_end = end
        if self.planning_length_pixel is None:
            zero = self.zero_point if self.zero_point is not None else start
            self.planning_length_pixel = abs(end.x() - zero.x())
        self.update_end_from_zero_start()
        if reset_handles:
            middle_frame_distance = self.tick_pixel_step * max(0, len(self.transverse_paths) - 1) / 2.0
            current = self.point_at_zero_distance(middle_frame_distance)
            self.t_values = {
                "zero": 0.0,
                "start": self.project_zero_end_t(start),
                "current": self.project_zero_end_t(current),
                "end": 1.0,
            }
        self.redraw_overlay()
        self.update_transverse_image()

    def clear_overlay(self):
        self.clear_cutting_overlay()
        self.cut_plan = {}
        self.scale_confirmed = False
        for item in list(self.tick_items):
            self.sagittal_scene.removeItem(item)
        self.tick_items = []
        for handle in list(self.handles.values()):
            self.sagittal_scene.removeItem(handle)
        self.handles = {}
        if self.line_item:
            self.sagittal_scene.removeItem(self.line_item)
        self.line_item = None
        self.line_start = None
        self.line_end = None
        self.zero_point = None
        self.planning_length_pixel = None
        self.depth = None
        self.scale_numerator = DEFAULT_SCALE_NUMERATOR
        self.scale_10mm_pixel = None
        self.tick_pixel_step = 10.0
        self.t_values = {"zero": 0.0, "start": 0.0, "current": 0.5, "end": 1.0}
        self.hint_label.setText("")

    def redraw_overlay(self):
        for item in list(self.tick_items):
            self.sagittal_scene.removeItem(item)
        self.tick_items = []
        if self.line_item:
            self.sagittal_scene.removeItem(self.line_item)
        if self.line_start is None or self.line_end is None:
            return

        self.line_item = QGraphicsLineItem(
            self.line_start.x(), self.line_start.y(), self.line_end.x(), self.line_end.y()
        )
        self.line_item.setPen(QPen(QColor(230, 0, 0), 3))
        self.line_item.setZValue(10)
        self.sagittal_scene.addItem(self.line_item)
        self.draw_ticks()
        self.ensure_handles()
        self.update_handle_positions()
        if self.cut_plan:
            self.redraw_cutting_overlay()

    def draw_ticks(self):
        horizontal_length = abs(self.line_end.x() - self.line_start.x())
        if horizontal_length < 1:
            return
        tick_step = max(float(self.tick_pixel_step), 1.0)
        tick_count = int(horizontal_length // tick_step)
        font = QFont("Arial", 9)
        sign = self.horizontal_sign()

        for i in range(tick_count + 1):
            x = self.line_start.x() + sign * i * tick_step
            y = self.baseline_y_at_x(x)
            major = i % MAJOR_TICK_UNITS == 0
            half_len = 9 if major else 5
            tick = QGraphicsLineItem(x, y - half_len, x, y + half_len)
            tick.setPen(QPen(QColor(230, 0, 0), 2 if major else 1))
            tick.setZValue(11)
            self.sagittal_scene.addItem(tick)
            self.tick_items.append(tick)

            if major and i > 0:
                text = QGraphicsTextItem(str(i))
                text.setDefaultTextColor(QColor(230, 0, 0))
                text.setFont(font)
                text.setPos(x - 10, y - 28)
                text.setZValue(12)
                self.sagittal_scene.addItem(text)
                self.tick_items.append(text)

    def ensure_handles(self):
        colors = {
            "zero": QColor(180, 80, 255),
            "start": QColor(30, 120, 255),
            "end": QColor(30, 180, 80),
        }
        if "current" not in self.handles:
            handle = CurrentLineHandle(self)
            self.handles["current"] = handle
            self.sagittal_scene.addItem(handle)
        for role, color in colors.items():
            if role not in self.handles:
                handle = PlanningHandle(self, role, color)
                if role == "end":
                    handle.setFlag(QGraphicsItem.ItemIsMovable, False)
                self.handles[role] = handle
                self.sagittal_scene.addItem(handle)

    def update_handle_positions(self):
        if "zero" in self.handles and self.zero_point is not None:
            self.handles["zero"].set_position_silent(self.zero_point)
        if "start" in self.handles and self.line_start is not None:
            self.handles["start"].set_position_silent(self.line_start)
        if "end" in self.handles and self.line_end is not None:
            self.handles["end"].set_position_silent(self.line_end)
        if "current" in self.handles:
            rect = self.sagittal_scene.sceneRect()
            self.handles["current"].set_bounds(rect.top(), rect.bottom())
            current_point = self.point_at_zero_end_t(self.t_values["current"])
            x = self.current_x_from_drag_x(current_point.x())
            self.handles["current"].set_position_silent(QPointF(x, 0.0))

    def update_end_from_zero_start(self):
        if self.zero_point is None or self.line_start is None:
            return
        dx = self.line_start.x() - self.zero_point.x()
        if abs(dx) < 1e-9:
            return
        planning_length = self.planning_length_pixel
        if planning_length is None:
            planning_length = abs(self.line_end.x() - self.zero_point.x())
            self.planning_length_pixel = planning_length
        sign = 1.0 if dx >= 0 else -1.0
        end_x = self.zero_point.x() + sign * planning_length
        self.line_end = QPointF(end_x, self.baseline_y_at_x(end_x))

    def baseline_y_at_x(self, x: float):
        if self.zero_point is None or self.line_start is None:
            return 0.0
        dx = self.line_start.x() - self.zero_point.x()
        if abs(dx) < 1e-9:
            return self.line_start.y()
        slope = (self.line_start.y() - self.zero_point.y()) / dx
        return self.zero_point.y() + slope * (x - self.zero_point.x())

    def horizontal_sign(self):
        if self.zero_point is None or self.line_start is None:
            return 1.0
        return 1.0 if self.line_start.x() >= self.zero_point.x() else -1.0

    def tick_x_for_mark_index(self, index: int):
        if self.line_start is None:
            return 0.0
        return self.line_start.x() + self.horizontal_sign() * max(float(self.tick_pixel_step), 1.0) * index

    def mark_index_from_x(self, x: float):
        if self.line_start is None:
            return 0
        signed_distance = (x - self.line_start.x()) * self.horizontal_sign()
        tick_step = max(float(self.tick_pixel_step), 1.0)
        max_index = max(0, int(abs(self.line_end.x() - self.line_start.x()) // tick_step))
        index = int(round(signed_distance / tick_step))
        return max(0, min(max_index, index))

    def clamp_x_to_zero_end(self, x: float):
        zero = self.zero_point if self.zero_point is not None else self.line_start
        if zero is None or self.line_end is None:
            return x
        sign = self.horizontal_sign()
        signed_distance = (x - zero.x()) * sign
        max_distance = abs(self.line_end.x() - zero.x())
        signed_distance = max(0.0, min(max_distance, signed_distance))
        return zero.x() + sign * signed_distance

    def current_x_from_drag_x(self, x: float):
        x = self.clamp_x_to_zero_end(x)
        if self.line_start is None:
            return x
        if (x - self.line_start.x()) * self.horizontal_sign() < 0:
            return x
        return self.tick_x_for_mark_index(self.mark_index_from_x(x))

    def current_index_from_x(self, x: float):
        zero = self.zero_point if self.zero_point is not None else self.line_start
        if zero is None or not self.transverse_paths:
            return 0
        signed_distance = (x - zero.x()) * self.horizontal_sign()
        tick_step = max(float(self.tick_pixel_step), 1.0)
        index = int(round(signed_distance / tick_step))
        return max(0, min(len(self.transverse_paths) - 1, index))

    def index_to_display(self, index: int):
        return int(index) + 1

    def display_to_index(self, display_index: int):
        if not self.transverse_paths:
            return 0
        return max(0, min(len(self.transverse_paths) - 1, int(display_index) - 1))

    def handle_point(self, role):
        if role == "zero":
            return self.zero_point
        if role == "start":
            return self.line_start
        if role == "end":
            return self.line_end
        return self.point_at_zero_end_t(self.t_values["current"])

    def point_at_zero_end_t(self, t: float):
        t = max(0.0, min(1.0, t))
        zero = self.zero_point if self.zero_point is not None else self.line_start
        if zero is None or self.line_end is None:
            return QPointF()
        return QPointF(
            zero.x() + (self.line_end.x() - zero.x()) * t,
            zero.y() + (self.line_end.y() - zero.y()) * t,
        )

    def point_at_zero_distance(self, distance: float):
        zero = self.zero_point if self.zero_point is not None else self.line_start
        if zero is None or self.line_end is None:
            return QPointF()
        horizontal_length = abs(self.line_end.x() - zero.x())
        distance = max(0.0, min(horizontal_length, distance))
        x = zero.x() + self.horizontal_sign() * distance
        return QPointF(x, self.baseline_y_at_x(x))

    def project_segment_t(self, point: QPointF, start: QPointF, end: QPointF, clamp=True):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        denom = dx * dx + dy * dy
        if denom < 1e-9:
            return 0.0
        t = ((point.x() - start.x()) * dx + (point.y() - start.y()) * dy) / denom
        if clamp:
            return max(0.0, min(1.0, t))
        return t

    def project_zero_end_t(self, point: QPointF):
        zero = self.zero_point if self.zero_point is not None else self.line_start
        if zero is None or self.line_end is None:
            return 0.0
        return self.project_segment_t(point, zero, self.line_end)

    def constrain_handle_position(self, role, value):
        if self.line_start is None or self.line_end is None:
            return value
        if role == "zero":
            if math.hypot(value.x() - self.line_start.x(), value.y() - self.line_start.y()) < 1.0:
                return self.zero_point
            return value
        if role == "start":
            zero = self.zero_point if self.zero_point is not None else self.line_start
            if math.hypot(value.x() - zero.x(), value.y() - zero.y()) < 1.0:
                return self.line_start
            return value
        if role == "end":
            return self.line_end
        x = self.current_x_from_drag_x(value.x())
        return QPointF(x, 0.0)

    def handle_moved(self, role):
        handle = self.handles[role]
        if role == "zero":
            self.zero_point = handle.pos()
            self.update_end_from_zero_start()
            self.t_values["zero"] = 0.0
            self.t_values["start"] = self.project_zero_end_t(self.line_start)
            self.t_values["current"] = min(self.t_values["current"], 1.0)
            self.redraw_overlay()
        elif role == "start":
            self.line_start = handle.pos()
            self.update_end_from_zero_start()
            self.t_values["start"] = self.project_zero_end_t(self.line_start)
            self.t_values["current"] = min(self.t_values["current"], 1.0)
            self.redraw_overlay()
        elif role == "end":
            self.update_handle_positions()
        else:
            x = self.current_x_from_drag_x(handle.pos().x())
            y = self.baseline_y_at_x(x)
            self.t_values["current"] = self.project_zero_end_t(QPointF(x, y))
            self.update_handle_positions()
        self.update_transverse_image()
        self.save_planning_json()

    def current_slice_index(self):
        if not self.transverse_paths:
            return 0
        if self.line_start is None or self.line_end is None:
            return 0
        current_point = self.point_at_zero_end_t(self.t_values["current"])
        return self.current_index_from_x(current_point.x())

    def update_transverse_image(self):
        if not self.transverse_paths:
            self.slice_label.setText("")
            self.transverse_name_label.setText("")
            self.clear_mask_overlay()
            return
        index = self.current_slice_index()
        self.transverse_view.set_image(self.transverse_paths[index])
        self.slice_label.setText(f"横断面 {index + 1}/{len(self.transverse_paths)}")
        self.transverse_name_label.setText(self.transverse_paths[index].name)
        self.update_mask_overlay()
        self.update_transverse_cut_overlay()

    def mask_path_for_current_patient(self):
        if not self.patient_dirs or self.patient_index < 0:
            return None
        patient_id = self.patient_dirs[self.patient_index].name
        candidates = []
        if self.dataset_dir is not None:
            candidates.append(self.dataset_dir.parent / "seg" / f"{patient_id}.nii.gz")
        candidates.append(Path.cwd() / "data" / "seg" / f"{patient_id}.nii.gz")
        workspace_root = Path(__file__).resolve().parents[2]
        candidates.append(workspace_root / "data" / "seg" / f"{patient_id}.nii.gz")
        for path in candidates:
            if path.exists():
                return path
        return None

    def load_mask_for_current_patient(self):
        if not self.patient_dirs or self.patient_index < 0:
            return False
        patient_id = self.patient_dirs[self.patient_index].name
        if self.mask_patient_id == patient_id and self.mask_data is not None:
            return True
        self.mask_data = None
        self.mask_patient_id = None
        path = self.mask_path_for_current_patient()
        if path is None:
            self.statusBar().showMessage(f"未找到 mask: {patient_id}.nii.gz", 5000)
            return False
        try:
            image = nib.load(str(path))
            self.mask_data = np.asanyarray(image.dataobj)
            self.mask_patient_id = patient_id
            return True
        except Exception as exc:
            self.statusBar().showMessage(f"读取 mask 失败: {exc}", 8000)
            return False

    def toggle_mask_overlay(self, checked: bool):
        self.mask_visible = checked
        if not checked:
            self.clear_mask_overlay()
            return
        self.update_mask_overlay()

    def clear_mask_overlay(self):
        if self.mask_item is not None:
            scene = self.transverse_view.scene()
            scene.removeItem(self.mask_item)
            self.mask_item = None

    def update_mask_overlay(self):
        self.clear_mask_overlay()
        if not self.mask_visible or not self.transverse_paths:
            return
        if not self.load_mask_for_current_patient():
            return
        index = self.current_slice_index()
        if self.mask_data is None or self.mask_data.ndim < 3 or index >= self.mask_data.shape[2]:
            self.statusBar().showMessage("当前横断面超出 mask 切片范围", 5000)
            return
        mask_slice = np.asarray(self.mask_data[:, :, index]).T
        scene_rect = self.transverse_view.scene().sceneRect()
        width = int(scene_rect.width())
        height = int(scene_rect.height())
        if width <= 0 or height <= 0:
            return
        if mask_slice.shape != (height, width):
            if mask_slice.shape == (width, height):
                mask_slice = mask_slice.T
            else:
                self.statusBar().showMessage(
                    f"mask 尺寸 {mask_slice.shape[::-1]} 与横断面图像 {(width, height)} 不一致",
                    8000,
                )
                return
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        colors = {
            1: (0, 220, 0, 255),
            2: (230, 0, 0, 255),
            3: (40, 80, 255, 255),
            4: (255, 230, 0, 255),
        }
        structure = np.ones((3, 3), dtype=bool)
        for label, color in colors.items():
            binary = mask_slice == label
            if not np.any(binary):
                continue
            eroded = ndimage.binary_erosion(binary, structure=structure, border_value=0)
            edge = binary & ~eroded
            edge = ndimage.binary_dilation(edge, structure=structure, iterations=1)
            rgba[edge] = color
        image = QImage(rgba.data, width, height, width * 4, QImage.Format_RGBA8888).copy()
        self.mask_item = QGraphicsPixmapItem(QPixmap.fromImage(image))
        self.mask_item.setZValue(38)
        self.transverse_view.scene().addItem(self.mask_item)

    def clear_cutting_overlay(self):
        for item in self.cut_sagittal_items:
            self.sagittal_scene.removeItem(item)
        self.cut_sagittal_items = []
        for handle in self.cut_sagittal_handles.values():
            self.sagittal_scene.removeItem(handle)
        self.cut_sagittal_handles = {}
        self.clear_transverse_cut_overlay()

    def clear_transverse_cut_overlay(self):
        scene = self.transverse_view.scene()
        for item in self.cut_transverse_items:
            scene.removeItem(item)
        self.cut_transverse_items = []
        for handle in self.cut_transverse_handles.values():
            scene.removeItem(handle)
        self.cut_transverse_handles = {}

    def clear_transverse_cut_items(self):
        scene = self.transverse_view.scene()
        for item in self.cut_transverse_items:
            scene.removeItem(item)
        self.cut_transverse_items = []

    def redraw_cutting_overlay(self):
        for item in self.cut_sagittal_items:
            self.sagittal_scene.removeItem(item)
        self.cut_sagittal_items = []
        if not self.cut_plan:
            return
        display_points = {}
        ordered_points = self.ordered_cut_points()
        for name, point in ordered_points:
            display_points[name] = self.sagittal_point_for_radius(point, self.point_primary_radius(point))
        for (_, left), (_, right) in zip(ordered_points, ordered_points[1:]):
            if not (self.is_butterfly_point(left) and self.is_butterfly_point(right)):
                continue
            left_r, left_l = self.butterfly_side_points(left)
            right_r, right_l = self.butterfly_side_points(right)
            pairs = [(left_r, right_r), (left_l, right_l)]
            radii = [
                (self.point_radii(left)[0] + self.point_radii(right)[0]) / 2.0,
                (self.point_radii(left)[1] + self.point_radii(right)[1]) / 2.0,
            ]
            small_pair = pairs[0] if radii[0] <= radii[1] else pairs[1]
            large_pair = pairs[1] if radii[0] <= radii[1] else pairs[0]
            for pair, color in [
                (large_pair, QColor(180, 120, 220, 45)),
                (small_pair, QColor(110, 60, 170, 90)),
            ]:
                start, finish = pair
                path = QPainterPath(start)
                path.lineTo(finish)
                path.lineTo(QPointF(finish.x(), self.baseline_y_at_x(finish.x())))
                path.lineTo(QPointF(start.x(), self.baseline_y_at_x(start.x())))
                path.closeSubpath()
                item = QGraphicsPathItem(path)
                item.setBrush(QBrush(color))
                item.setPen(QPen(Qt.NoPen))
                item.setZValue(15)
                self.sagittal_scene.addItem(item)
                self.cut_sagittal_items.append(item)
        dashed_pen = QPen(QColor(230, 170, 40), 1.2)
        dashed_pen.setStyle(Qt.DashLine)
        solid_pen = QPen(QColor(230, 170, 40), 1.4)
        line_pairs = []
        for (left_name, left), (right_name, right) in zip(ordered_points, ordered_points[1:]):
            if self.is_butterfly_point(left) and self.is_butterfly_point(right):
                left_r, left_l = self.butterfly_side_points(left)
                right_r, right_l = self.butterfly_side_points(right)
                line_pairs.extend([(left_r, right_r), (left_l, right_l)])
            else:
                line_pairs.append((display_points[left_name], display_points[right_name]))
        for p1, p2 in line_pairs:
            if math.hypot(p1.x() - p2.x(), p1.y() - p2.y()) < 1e-6:
                continue
            line = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
            line.setPen(solid_pen)
            line.setZValue(30)
            self.sagittal_scene.addItem(line)
            self.cut_sagittal_items.append(line)
        for label, handle in self.cut_sagittal_handles.items():
            if self._dragging_sagittal_cut and label == self._active_sagittal_cut_name:
                continue
            handle.hide()
        for name, point in ordered_points:
            point = self.cut_plan[name]
            visual_points = [(name, display_points[name])]
            if self.is_butterfly_point(point):
                side_r, side_l = self.butterfly_side_points(point)
                if math.hypot(side_r.x() - side_l.x(), side_r.y() - side_l.y()) >= 1.0:
                    visual_points = [(f"{name}R", side_r), (f"{name}L", side_l)]
            for label, visual_point in visual_points:
                baseline = self.baseline_y_at_x(visual_point.x())
                vline = QGraphicsLineItem(visual_point.x(), baseline, visual_point.x(), visual_point.y())
                vline.setPen(dashed_pen)
                vline.setZValue(25)
                self.sagittal_scene.addItem(vline)
                self.cut_sagittal_items.append(vline)
                color = "#00cc55" if name == "ML" else "#f0a020"
                if label == name:
                    handle = self.cut_sagittal_handles.get(name)
                    if handle is None:
                        handle = BoxPlusHandle(self, "sagittal_cut", name, color)
                        self.cut_sagittal_handles[name] = handle
                        self.sagittal_scene.addItem(handle)
                    handle.show()
                    if not (self._dragging_sagittal_cut and name == self._active_sagittal_cut_name):
                        handle.set_position_silent(visual_point)
                else:
                    handle = self.cut_sagittal_handles.get(label)
                    if handle is None:
                        handle = BoxPlusHandle(self, "sagittal_cut", label, color)
                        self.cut_sagittal_handles[label] = handle
                        self.sagittal_scene.addItem(handle)
                    handle.show()
                    if not (self._dragging_sagittal_cut and label == self._active_sagittal_cut_name):
                        handle.set_position_silent(visual_point)

    def default_transverse_center(self):
        rect = self.transverse_view.scene().sceneRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return QPointF(560.0, 420.0)
        return rect.center()

    def max_cut_radius_pixel(self):
        if self.depth and self.depth > 0:
            return self.scale_numerator * 3.0 / self.depth
        if self.scale_10mm_pixel and self.scale_10mm_pixel > 0:
            return self.scale_10mm_pixel * 3.0
        return 10000.0

    def clamp_cut_radius(self, radius: float):
        return max(1.0, min(float(radius), self.max_cut_radius_pixel()))

    def required_radius_count(self, angles):
        return 2 if len(angles) == 4 else 1

    def normalize_cut_radii(self, radii, count=1, fallback=None):
        if radii is None:
            values = []
        elif isinstance(radii, (int, float)):
            values = [float(radii)]
        else:
            values = [float(value) for value in radii]
        if not values:
            values = [float(fallback if fallback is not None else DEFAULT_CUT_DEPTH_PIXEL)]
        if count == 2 and len(values) == 1:
            values = [values[0], values[0]]
        if len(values) < count:
            values.extend([values[-1]] * (count - len(values)))
        return [self.clamp_cut_radius(value) for value in values[:count]]

    def point_radii(self, point: CuttingPlanPoint):
        return self.normalize_cut_radii(
            getattr(point, "radii", None),
            self.required_radius_count(point.angles),
            getattr(point, "radius", DEFAULT_CUT_DEPTH_PIXEL),
        )

    def point_primary_radius(self, point: CuttingPlanPoint):
        radii = self.point_radii(point)
        return min(radii) if len(radii) == 2 else radii[0]

    def set_point_radii(self, point: CuttingPlanPoint, radii):
        count = self.required_radius_count(point.angles)
        point.radii = self.normalize_cut_radii(radii, count, getattr(point, "radius", DEFAULT_CUT_DEPTH_PIXEL))
        point.radius = min(point.radii) if count == 2 else point.radii[0]

    def sagittal_point_for_radius(self, point: CuttingPlanPoint, radius: float):
        return QPointF(point.sagittal_point.x(), self.baseline_y_at_x(point.sagittal_point.x()) + radius)

    def butterfly_side_points(self, point: CuttingPlanPoint):
        radii = self.point_radii(point)
        if len(radii) < 2:
            p = self.sagittal_point_for_radius(point, radii[0])
            return p, p
        return self.sagittal_point_for_radius(point, radii[0]), self.sagittal_point_for_radius(point, radii[1])

    def parse_sagittal_cut_name(self, name: str):
        if name not in self.cut_plan and len(name) > 1:
            base_name = name[:-1]
            if base_name in self.cut_plan and self.is_butterfly_point(self.cut_plan[base_name]):
                if name.endswith("R"):
                    return base_name, 0
                if name.endswith("L"):
                    return base_name, 1
        return name, None

    def begin_sagittal_cut_drag(self, name=None):
        self._dragging_sagittal_cut = True
        self._active_sagittal_cut_name = name

    def end_sagittal_cut_drag(self):
        self._dragging_sagittal_cut = False
        self.redraw_cutting_overlay()
        if self.selected_cut_name in self.cut_plan and self.cut_point_combo.currentText() != self.selected_cut_name:
            self.cut_point_combo.setCurrentText(self.selected_cut_name)
        self.update_cut_panel()
        self.update_transverse_cut_overlay()
        if self._cut_save_pending:
            self._cut_save_pending = False
            self.save_cutting_json()
        self._active_sagittal_cut_name = None

    def normalize_cut_angles(self, angles):
        count = len(angles)
        values = [max(MIN_CUT_ANGLE, min(MAX_CUT_ANGLE, float(value))) for value in angles]
        if count <= 1:
            return values
        values = sorted(values, reverse=True)
        min_first = MIN_CUT_ANGLE + MIN_ANGLE_GAP * (count - 1)
        values[0] = max(values[0], min_first)
        values[0] = min(values[0], MAX_CUT_ANGLE)
        for idx in range(1, count):
            max_allowed = values[idx - 1] - MIN_ANGLE_GAP
            min_allowed = MIN_CUT_ANGLE + MIN_ANGLE_GAP * (count - idx - 1)
            values[idx] = max(min_allowed, min(values[idx], max_allowed))
        return values

    def constrain_angle_at_index(self, angles, index: int, value: float):
        values = self.normalize_cut_angles(angles)
        if index < 0 or index >= len(values):
            return values
        lower = MIN_CUT_ANGLE if index == len(values) - 1 else values[index + 1] + MIN_ANGLE_GAP
        upper = MAX_CUT_ANGLE if index == 0 else values[index - 1] - MIN_ANGLE_GAP
        values[index] = max(lower, min(upper, float(value)))
        return self.normalize_cut_angles(values)

    def is_butterfly_index(self, index: int):
        if len(self.cut_plan) < 2:
            return False
        ordered = self.ordered_cut_points()
        for (_, left), (_, right) in zip(ordered, ordered[1:]):
            if not (self.is_butterfly_point(left) and self.is_butterfly_point(right)):
                continue
            start = min(left.transverse_index, right.transverse_index)
            end = max(left.transverse_index, right.transverse_index)
            if start <= index <= end:
                return True
        return False

    def default_angles_for_index(self, index: int):
        return BUTTERFLY_ANGLES.copy() if self.is_butterfly_index(index) else NORMAL_ANGLES.copy()

    def cut_display_index_range(self):
        if not self.cut_plan:
            return None
        indices = [point.transverse_index for point in self.cut_plan.values()]
        return min(indices), max(indices)

    def is_cut_display_index(self, index: int):
        display_range = self.cut_display_index_range()
        if display_range is None:
            return False
        return display_range[0] <= index <= display_range[1]

    def key_point_at_index(self, index: int):
        for name, point in self.cut_plan.items():
            if point.transverse_index == index:
                return name, point
        return None, None

    def copy_cut_region(self, source: CuttingPlanPoint, index: int, angles=None):
        target_angles = self.normalize_cut_angles(angles if angles is not None else source.angles)
        radii = self.normalize_cut_radii(
            getattr(source, "radii", None),
            self.required_radius_count(target_angles),
            getattr(source, "radius", DEFAULT_CUT_DEPTH_PIXEL),
        )
        return CuttingPlanPoint(
            "CURRENT",
            QPointF(),
            index,
            QPointF(source.center),
            min(radii) if len(radii) == 2 else radii[0],
            target_angles,
            radii,
        )

    def interpolate_angles(self, left: CuttingPlanPoint, right: CuttingPlanPoint, t: float, index: int):
        default_angles = self.default_angles_for_index(index)
        count = len(default_angles)
        left_angles = self.angles_for_count(left, count)
        right_angles = self.angles_for_count(right, count)
        return [left_angles[i] + (right_angles[i] - left_angles[i]) * t for i in range(count)]

    def angles_for_count(self, point: CuttingPlanPoint, count: int):
        angles = self.normalize_cut_angles(point.angles)
        if len(angles) == count:
            return angles
        if count == 2 and len(angles) == 4:
            return self.normalize_cut_angles([angles[0], angles[3]])
        if count == 4 and len(angles) == 2:
            middle = (angles[0] + angles[1]) / 2.0
            return self.normalize_cut_angles([angles[0], middle, middle, angles[1]])
        return self.normalize_cut_angles((angles + self.default_angles_for_index(point.transverse_index))[:count])

    def interpolate_radii(self, left: CuttingPlanPoint, right: CuttingPlanPoint, t: float, angle_count: int):
        count = 2 if angle_count == 4 else 1
        left_values = self.radii_for_count(left, count)
        right_values = self.radii_for_count(right, count)
        return self.normalize_cut_radii(
            [left_values[i] + (right_values[i] - left_values[i]) * t for i in range(count)],
            count,
        )

    def radii_for_count(self, point: CuttingPlanPoint, count: int):
        radii = self.point_radii(point)
        if len(radii) == count:
            return radii
        if count == 1 and len(radii) == 2:
            return [min(radii)]
        if count == 2 and len(radii) == 1:
            return [radii[0], radii[0]]
        return self.normalize_cut_radii(radii, count, getattr(point, "radius", DEFAULT_CUT_DEPTH_PIXEL))

    def interpolated_cut_region(self, index: int):
        if not self.cut_plan:
            return None
        ordered = [point for _, point in self.ordered_cut_points()]
        _, key_point = self.key_point_at_index(index)
        if key_point is not None:
            return self.copy_cut_region(key_point, index)
        if index <= ordered[0].transverse_index:
            return self.copy_cut_region(ordered[0], index, self.default_angles_for_index(index))
        if index >= ordered[-1].transverse_index:
            return self.copy_cut_region(ordered[-1], index, self.default_angles_for_index(index))
        for left, right in zip(ordered, ordered[1:]):
            if left.transverse_index <= index <= right.transverse_index:
                span = max(1, right.transverse_index - left.transverse_index)
                t = (index - left.transverse_index) / span
                center = QPointF(
                    left.center.x() + (right.center.x() - left.center.x()) * t,
                    left.center.y() + (right.center.y() - left.center.y()) * t,
                )
                angles = self.interpolate_angles(left, right, t, index)
                radii = self.interpolate_radii(left, right, t, len(angles))
                return CuttingPlanPoint("CURRENT", QPointF(), index, center, min(radii) if len(radii) == 2 else radii[0], angles, radii)
        return self.copy_cut_region(ordered[0], index, self.default_angles_for_index(index))

    def current_cut_region(self, index=None):
        if index is None:
            index = self.current_slice_index()
        if not self.is_cut_display_index(index):
            return None
        return self.interpolated_cut_region(index)

    def store_current_slice_region(self, region: CuttingPlanPoint):
        index = max(0, min(len(self.transverse_paths) - 1, int(region.transverse_index)))
        name, key_point = self.key_point_at_index(index)
        if key_point is None:
            return False
        key_point.center = QPointF(region.center)
        key_point.angles = self.normalize_cut_angles(region.angles)
        self.set_point_radii(key_point, getattr(region, "radii", [region.radius]))
        baseline = self.baseline_y_at_x(key_point.sagittal_point.x())
        key_point.sagittal_point = QPointF(key_point.sagittal_point.x(), baseline + self.point_primary_radius(key_point))
        self.selected_cut_name = name
        self.cut_point_combo.setCurrentText(name)
        return True

    def angle_point(self, center: QPointF, radius: float, angle: float):
        radians = math.radians(angle)
        return QPointF(center.x() - radius * math.sin(radians), center.y() + radius * math.cos(radians))

    def build_sector_path(self, center: QPointF, radius: float, angle1: float, angle2: float):
        path = QPainterPath(center)
        steps = 48
        for i in range(steps + 1):
            angle = angle1 + (angle2 - angle1) * i / steps
            path.lineTo(self.angle_point(center, radius, angle))
        path.lineTo(center)
        path.closeSubpath()
        return path

    def build_annular_sector_path(self, center: QPointF, inner_radius: float, outer_radius: float, angle1: float, angle2: float):
        inner_radius = max(0.0, min(inner_radius, outer_radius))
        path = QPainterPath(self.angle_point(center, outer_radius, angle1))
        steps = 48
        for i in range(steps + 1):
            angle = angle1 + (angle2 - angle1) * i / steps
            path.lineTo(self.angle_point(center, outer_radius, angle))
        for i in range(steps, -1, -1):
            angle = angle1 + (angle2 - angle1) * i / steps
            path.lineTo(self.angle_point(center, inner_radius, angle))
        path.closeSubpath()
        return path

    def update_transverse_cut_overlay(self):
        self.clear_transverse_cut_items()
        if not self.cut_plan or not self.transverse_paths:
            return
        index = self.current_slice_index()
        region = self.current_cut_region(index)
        if not region:
            for handle in self.cut_transverse_handles.values():
                handle.hide()
            return
        scene = self.transverse_view.scene()
        center = region.center
        angles = region.angles
        radii = self.normalize_cut_radii(getattr(region, "radii", [region.radius]), self.required_radius_count(angles), region.radius)
        if len(angles) == 4:
            r_right, r_left = radii
            small_radius = min(r_right, r_left)
            large_radius = max(r_right, r_left)
            items = [
                (self.build_annular_sector_path(center, small_radius, large_radius, angles[1], angles[2]), QColor(240, 170, 80, 70), QColor(240, 170, 80)),
                (self.build_sector_path(center, small_radius, angles[1], angles[2]), QColor(210, 95, 20, 120), QColor(210, 95, 20)),
                (self.build_sector_path(center, r_right, angles[0], angles[1]), None, QColor(40, 210, 220)),
                (self.build_sector_path(center, r_left, angles[2], angles[3]), None, QColor(40, 210, 220)),
            ]
            handle_angles = angles
            handle_radii = [r_right, r_right, r_left, r_left]
        else:
            items = [(self.build_sector_path(center, radii[0], angles[0], angles[1]), None, QColor(40, 210, 220))]
            handle_angles = angles
            handle_radii = [radii[0]] * len(angles)
        for path, brush_color, pen_color in items:
            item = QGraphicsPathItem(path)
            item.setBrush(QBrush(brush_color) if brush_color is not None else QBrush(Qt.NoBrush))
            item.setPen(QPen(pen_color, 1.2, Qt.DashLine))
            item.setZValue(40)
            scene.addItem(item)
            self.cut_transverse_items.append(item)
        _, key_point = self.key_point_at_index(index)
        if key_point is None:
            for handle in self.cut_transverse_handles.values():
                handle.hide()
            return
        center_handle = self.cut_transverse_handles.get("center")
        if center_handle is None:
            center_handle = CirclePlusHandle(self, "transverse_cut", "C", "#f0a020", 11)
            self.cut_transverse_handles["center"] = center_handle
            scene.addItem(center_handle)
        center_handle.show()
        center_handle.set_position_silent(center)
        for idx, angle in enumerate(handle_angles):
            key = f"angle{idx}"
            handle = self.cut_transverse_handles.get(key)
            if handle is None:
                handle = CirclePlusHandle(self, "transverse_cut", f"A{idx + 1}", "#f0a020", 10)
                self.cut_transverse_handles[key] = handle
                scene.addItem(handle)
            handle.show()
            handle.set_position_silent(self.angle_point(center, handle_radii[idx], angle))
        for idx in range(len(handle_angles), 4):
            key = f"angle{idx}"
            handle = self.cut_transverse_handles.pop(key, None)
            if handle is not None:
                scene.removeItem(handle)

    def constrain_sagittal_cut_point(self, name, value):
        if self.line_start is None or self.line_end is None:
            return value
        base_name, _ = self.parse_sagittal_cut_name(name)
        if base_name not in self.cut_plan:
            return value
        rect = self.sagittal_scene.sceneRect()
        x = max(rect.left(), min(rect.right(), value.x()))
        baseline = self.baseline_y_at_x(x)
        max_y = min(rect.bottom(), baseline + self.max_cut_radius_pixel())
        y = max(baseline + 1.0, min(max_y, value.y()))
        return QPointF(x, y)

    def sagittal_cut_point_moved(self, name, pos):
        base_name, side_index = self.parse_sagittal_cut_name(name)
        if base_name not in self.cut_plan:
            return
        baseline = self.baseline_y_at_x(pos.x())
        point = self.cut_plan[base_name]
        point.sagittal_point = QPointF(pos.x(), baseline + self.point_primary_radius(point))
        point.transverse_index = self.current_index_from_x(pos.x())
        depth = self.clamp_cut_radius(pos.y() - baseline)
        if side_index is None:
            self.set_point_radii(point, depth)
        else:
            radii = self.point_radii(point)
            if side_index < len(radii):
                radii[side_index] = depth
            self.set_point_radii(point, radii)
        point.sagittal_point = QPointF(pos.x(), baseline + self.point_primary_radius(point))
        self.selected_cut_name = base_name
        if self._dragging_sagittal_cut:
            self._cut_save_pending = True
            self.redraw_cutting_overlay()
            self.update_transverse_cut_overlay()
            return
        self.cut_point_combo.setCurrentText(base_name)
        self.redraw_cutting_overlay()
        self.update_cut_panel()
        self.update_transverse_cut_overlay()
        self.save_cutting_json()

    def constrain_transverse_cut_point(self, name, value):
        if name == "C":
            return value
        index = self.current_slice_index()
        _, key_point = self.key_point_at_index(index)
        if key_point is None:
            return value
        region = self.current_cut_region(index)
        if region is None:
            return value
        dx = value.x() - region.center.x()
        dy = value.y() - region.center.y()
        radius = self.clamp_cut_radius(math.hypot(dx, dy))
        angle = math.degrees(math.atan2(-dx, dy))
        if name.startswith("A"):
            idx = int(name[1:]) - 1
            if idx < len(region.angles):
                angle = self.constrain_angle_at_index(region.angles, idx, angle)[idx]
        return self.angle_point(region.center, radius, angle)

    def transverse_cut_point_moved(self, handle_name, pos):
        index = self.current_slice_index()
        _, key_point = self.key_point_at_index(index)
        if key_point is None:
            self.update_transverse_cut_overlay()
            return
        region = self.current_cut_region(index)
        if region is None:
            return
        if handle_name == "C":
            region.center = pos
        else:
            dx = pos.x() - region.center.x()
            dy = pos.y() - region.center.y()
            new_radius = self.clamp_cut_radius(math.hypot(dx, dy))
            region.radii = self.normalize_cut_radii(getattr(region, "radii", [region.radius]), self.required_radius_count(region.angles), region.radius)
            angle = math.degrees(math.atan2(-dx, dy))
            if handle_name.startswith("A"):
                idx = int(handle_name[1:]) - 1
                if idx < len(region.angles):
                    region.angles = self.constrain_angle_at_index(region.angles, idx, angle)
                    if len(region.radii) == 2:
                        region.radii[0 if idx < 2 else 1] = new_radius
                    else:
                        region.radii[0] = new_radius
                    region.radius = min(region.radii) if len(region.radii) == 2 else region.radii[0]
        if not self.store_current_slice_region(region):
            self.update_transverse_cut_overlay()
            return
        self.redraw_cutting_overlay()
        self.update_cut_panel()
        self.update_transverse_cut_overlay()
        self.save_cutting_json()

    def select_cut_point(self, name):
        if name and name in self.cut_plan:
            self.selected_cut_name = name
            self.update_cut_panel()
            self.update_transverse_cut_overlay()

    def update_cut_panel(self):
        self._updating_cut_panel = True
        try:
            if self.selected_cut_name not in self.cut_plan:
                return
            point = self.cut_plan[self.selected_cut_name]
            self.cut_index_spin.setMaximum(max(1, len(self.transverse_paths)))
            self.cut_radius_spin.setMaximum(self.max_cut_radius_pixel())
            self.cut_index_spin.setValue(self.index_to_display(point.transverse_index))
            self.cut_center_x_spin.setValue(point.center.x())
            self.cut_center_y_spin.setValue(point.center.y())
            self.cut_radius_spin.setValue(self.point_primary_radius(point))
            for idx, spin in enumerate(self.cut_angle_spins):
                spin.setEnabled(idx < len(point.angles))
                spin.setValue(point.angles[idx] if idx < len(point.angles) else 0.0)
        finally:
            self._updating_cut_panel = False

    def apply_cut_panel_values(self):
        if self._updating_cut_panel or self.selected_cut_name not in self.cut_plan:
            return
        point = self.cut_plan[self.selected_cut_name]
        point.transverse_index = self.display_to_index(self.cut_index_spin.value())
        point.center = QPointF(self.cut_center_x_spin.value(), self.cut_center_y_spin.value())
        self.set_point_radii(point, self.clamp_cut_radius(self.cut_radius_spin.value()))
        point.angles = self.normalize_cut_angles(
            [self.cut_angle_spins[idx].value() for idx in range(len(point.angles))]
        )
        self.set_point_radii(point, self.point_radii(point))
        point.sagittal_point = self.sagittal_point_from_transverse(point.transverse_index, self.point_primary_radius(point))
        self.redraw_cutting_overlay()
        self.update_cut_panel()
        self.update_transverse_cut_overlay()
        self.save_cutting_json()

    def planning_json_path(self):
        if not self.patient_dirs or self.patient_index < 0:
            return None
        return self.patient_dirs[self.patient_index] / "planning_line_iter3.json"

    def save_current_patient_state(self):
        self.save_planning_json()
        self.save_cutting_json()

    def save_planning_json(self):
        path = self.planning_json_path()
        if not path or self.line_start is None or self.line_end is None:
            return
        data = {
            "patient_id": self.patient_dirs[self.patient_index].name,
            "sagittal_image": str(self.sagittal_path.relative_to(self.patient_dirs[self.patient_index])),
            "transverse_count": len(self.transverse_paths),
            "depth": self.depth,
            "scale_numerator": self.scale_numerator,
            "scale_10mm_pixel": self.scale_10mm_pixel,
            "zero_point": qpoint_to_list(self.zero_point) if self.zero_point is not None else None,
            "planning_length_pixel": self.planning_length_pixel,
            "line": {
                "start": qpoint_to_list(self.line_start),
                "end": qpoint_to_list(self.line_end),
            },
            "handles": {
                role: {
                    "t": round(value, 6),
                    "point": qpoint_to_list(self.handle_point(role)),
                }
                for role, value in self.t_values.items()
            },
            "current_transverse_index": self.index_to_display(self.current_slice_index()),
            "tick_pixel_step": self.tick_pixel_step,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_planning_json(self):
        path = self.planning_json_path()
        if not path or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            line = data["line"]
            handles = data.get("handles", {})
            self.depth = data.get("depth")
            self.scale_numerator = float(data.get("scale_numerator", DEFAULT_SCALE_NUMERATOR))
            scale_10mm_pixel = data.get("scale_10mm_pixel")
            self.scale_10mm_pixel = float(scale_10mm_pixel) if scale_10mm_pixel is not None else None
            self.tick_pixel_step = float(
                data.get("tick_pixel_step")
                or (self.scale_10mm_pixel / 10.0 if self.scale_10mm_pixel else 10.0)
            )
            zero_point = data.get("zero_point")
            self.zero_point = list_to_qpoint(zero_point) if zero_point else None
            saved_planning_length = data.get("planning_length_pixel")
            self.planning_length_pixel = float(saved_planning_length) if saved_planning_length is not None else None
            self.t_values = {
                "zero": float(handles.get("zero", {}).get("t", 0.0)),
                "start": float(handles.get("start", {}).get("t", 0.0)),
                "current": float(handles.get("current", {}).get("t", 0.5)),
                "end": float(handles.get("end", {}).get("t", 1.0)),
            }
            self.set_planning_line(list_to_qpoint(line["start"]), list_to_qpoint(line["end"]))
        except Exception as exc:
            self.statusBar().showMessage(f"读取 planning_line_iter3.json 失败: {exc}", 8000)

    def cutting_json_path(self):
        if not self.patient_dirs or self.patient_index < 0:
            return None
        return self.patient_dirs[self.patient_index] / "cutting_plan_iter3.json"

    def cutting_json_read_path(self):
        if not self.patient_dirs or self.patient_index < 0:
            return None
        patient_dir = self.patient_dirs[self.patient_index]
        for filename in ["cutting_plan_iter3.json", "cutting_plan_import.json"]:
            path = patient_dir / filename
            if path.exists():
                return path
        return None

    def save_cutting_json(self):
        path = self.cutting_json_path()
        if not path or not self.cut_plan:
            return
        data = {
            "version": 5,
            "patient_id": self.patient_dirs[self.patient_index].name,
            "scale_confirmed": self.scale_confirmed,
            "selected": self.selected_cut_name,
            "points": {},
        }
        for name, point in self.cut_plan.items():
            point.angles = self.normalize_cut_angles(point.angles)
            self.set_point_radii(point, self.point_radii(point))
            data["points"][name] = {
                "sagittal": {
                    "point": qpoint_to_list(point.sagittal_point),
                    "transverse_index": self.index_to_display(point.transverse_index),
                    "depth_pixel": self.point_primary_radius(point),
                },
                "transverse": {
                    "center": qpoint_to_list(point.center),
                    "r": point.radii,
                    "angles": point.angles,
                },
            }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_cutting_json(self):
        if self.line_start is None or self.zero_point is None:
            QMessageBox.information(self, "提示", "请先初始化并确认刻度线，再导入规划 JSON。")
            return
        filename, _ = QFileDialog.getOpenFileName(self, "导入规划 JSON", "", "JSON Files (*.json);;All Files (*)")
        if not filename:
            return
        if self.load_cutting_json_from_path(Path(filename)):
            self.save_cutting_json()

    def load_cutting_json(self):
        path = self.cutting_json_read_path()
        if not path or not path.exists():
            return
        self.load_cutting_json_from_path(path)

    def load_cutting_json_from_path(self, path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            points = data.get("points", {})
            version = int(data.get("version", 1))
            self.cut_plan = {}
            for point_key, raw in points.items():
                if not isinstance(raw, dict):
                    continue
                raw = points[point_key]
                key_index = None
                try:
                    key_index = int(point_key)
                except (TypeError, ValueError):
                    pass
                name = str(raw.get("name", point_key))
                if "transverse" in raw or "sagittal" in raw:
                    sagittal = raw.get("sagittal", {})
                    transverse = raw.get("transverse", {})
                    raw_index = int(
                        sagittal.get(
                            "transverse_index",
                            transverse.get("transverse_index", key_index if key_index is not None else (1 if version >= 3 else 0)),
                        )
                    )
                    transverse_index = self.display_to_index(raw_index) if version >= 3 else raw_index
                    raw_sagittal_point = sagittal.get("point")
                    fallback_radius = transverse.get("radius", sagittal.get("depth_pixel", DEFAULT_CUT_DEPTH_PIXEL))
                else:
                    sagittal = {}
                    transverse = raw
                    raw_index = int(transverse.get("transverse_index", key_index if key_index is not None else 1))
                    transverse_index = self.display_to_index(raw_index)
                    raw_sagittal_point = None
                    fallback_radius = transverse.get("radius", DEFAULT_CUT_DEPTH_PIXEL)
                if self.transverse_paths:
                    transverse_index = max(0, min(len(self.transverse_paths) - 1, transverse_index))
                raw_radii = transverse.get("r", None)
                raw_angles = transverse.get("angles")
                if raw_angles is None:
                    if isinstance(raw_radii, (list, tuple)) and len(raw_radii) == 2:
                        raw_angles = BUTTERFLY_ANGLES
                    else:
                        raw_angles = self.default_angles_for_name(name)
                angles = self.normalize_cut_angles(raw_angles)
                radii = self.normalize_cut_radii(raw_radii, self.required_radius_count(angles), fallback_radius)
                primary_radius = min(radii) if len(radii) == 2 else radii[0]
                if raw_sagittal_point is None:
                    sagittal_point = self.sagittal_point_from_transverse(transverse_index, primary_radius)
                else:
                    sagittal_point = list_to_qpoint(raw_sagittal_point)
                point = CuttingPlanPoint(
                    name=name,
                    sagittal_point=sagittal_point,
                    transverse_index=transverse_index,
                    center=list_to_qpoint(transverse.get("center", [0, 0])),
                    radius=primary_radius,
                    angles=angles,
                    radii=radii,
                )
                baseline = self.baseline_y_at_x(point.sagittal_point.x())
                point.sagittal_point = QPointF(point.sagittal_point.x(), baseline + self.point_primary_radius(point))
                self.cut_plan[name] = point
            self.scale_confirmed = bool(data.get("scale_confirmed", bool(self.cut_plan)))
            self.selected_cut_name = data.get("selected", "")
            if self.selected_cut_name not in self.cut_plan and self.cut_plan:
                self.selected_cut_name = self.cut_point_names()[0]
            self.refresh_cut_point_combo()
            self.redraw_cutting_overlay()
            self.update_cut_panel()
            self.update_transverse_cut_overlay()
            return True
        except Exception as exc:
            self.statusBar().showMessage(f"读取 cutting_plan_iter3/import json 失败: {exc}", 8000)
            return False

    def closeEvent(self, event):
        self.save_current_patient_state()
        super().closeEvent(event)
