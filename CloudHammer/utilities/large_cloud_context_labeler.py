from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cloudhammer.manifests import read_jsonl  # noqa: E402

try:
    from PyQt5.QtCore import QPoint, QRectF, Qt, pyqtSignal
    from PyQt5.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
    from PyQt5.QtWidgets import (
        QAction,
        QApplication,
        QDockWidget,
        QFileDialog,
        QGraphicsItem,
        QGraphicsPixmapItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsSimpleTextItem,
        QGraphicsView,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QStatusBar,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError as exc:  # pragma: no cover - import-time user guidance
    raise SystemExit("PyQt5 is required. Use the project .venv that already runs LabelImg.") from exc


SCHEMA = "cloudhammer.large_cloud_context.v1"
MIN_BOX_SIDE = 5.0


@dataclass
class Box:
    x1: float
    y1: float
    x2: float
    y2: float
    class_name: str = "cloud_whole"

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    def to_payload(self) -> dict[str, Any]:
        return {
            "class_name": self.class_name,
            "box": xyxy_payload((self.x1, self.y1, self.x2, self.y2)),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any], default_class_name: str) -> "Box":
        raw = payload.get("box", payload)
        return cls(
            x1=float(raw["x1"]),
            y1=float(raw["y1"]),
            x2=float(raw["x2"]),
            y2=float(raw["y2"]),
            class_name=str(payload.get("class_name") or default_class_name),
        )


@dataclass
class Region:
    id: str
    crop_box: Box | None = None
    labels: list[Box] = field(default_factory=list)

    def to_payload(self, crop_image_path: Path | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "crop_box": None if self.crop_box is None else xyxy_payload(box_tuple(self.crop_box)),
            "labels": [label.to_payload() for label in self.labels],
        }
        if crop_image_path is not None:
            payload["crop_image_path"] = str(crop_image_path)
            if self.crop_box is not None:
                payload["labels_crop_xyxy"] = [
                    {
                        "class_name": label.class_name,
                        "box": xyxy_payload(translate_box_to_crop(label, self.crop_box)),
                    }
                    for label in self.labels
                ]
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any], default_class_name: str) -> "Region":
        crop_raw = payload.get("crop_box")
        return cls(
            id=str(payload.get("id") or "region_001"),
            crop_box=Box.from_payload(crop_raw, "context_crop") if crop_raw else None,
            labels=[Box.from_payload(item, default_class_name) for item in payload.get("labels", [])],
        )


def box_tuple(box: Box) -> tuple[float, float, float, float]:
    return (box.x1, box.y1, box.x2, box.y2)


def xyxy_payload(box: tuple[float, float, float, float]) -> dict[str, float]:
    x1, y1, x2, y2 = normalize_xyxy(box)
    return {
        "x1": round(x1, 3),
        "y1": round(y1, 3),
        "x2": round(x2, 3),
        "y2": round(y2, 3),
        "width": round(max(0.0, x2 - x1), 3),
        "height": round(max(0.0, y2 - y1), 3),
    }


def normalize_xyxy(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def clamp_xyxy(
    box: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = normalize_xyxy(box)
    return (
        max(0.0, min(float(image_width), x1)),
        max(0.0, min(float(image_height), y1)),
        max(0.0, min(float(image_width), x2)),
        max(0.0, min(float(image_height), y2)),
    )


def square_box_around(
    box: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = clamp_xyxy(box, image_width, image_height)
    side = max(x2 - x1, y2 - y1, MIN_BOX_SIDE)
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    side = min(side, float(image_width), float(image_height))
    sx1 = cx - side / 2
    sy1 = cy - side / 2
    sx2 = sx1 + side
    sy2 = sy1 + side
    if sx1 < 0:
        sx2 -= sx1
        sx1 = 0.0
    if sy1 < 0:
        sy2 -= sy1
        sy1 = 0.0
    if sx2 > image_width:
        sx1 -= sx2 - image_width
        sx2 = float(image_width)
    if sy2 > image_height:
        sy1 -= sy2 - image_height
        sy2 = float(image_height)
    return clamp_xyxy((sx1, sy1, sx2, sy2), image_width, image_height)


def square_crop_around_labels(
    labels: list[Box],
    image_width: int,
    image_height: int,
    margin_percent: int = 15,
) -> Box | None:
    if not labels:
        return None
    x1 = min(label.x1 for label in labels)
    y1 = min(label.y1 for label in labels)
    x2 = max(label.x2 for label in labels)
    y2 = max(label.y2 for label in labels)
    margin = max(x2 - x1, y2 - y1) * max(0.0, margin_percent / 100.0)
    sx1, sy1, sx2, sy2 = square_box_around((x1 - margin, y1 - margin, x2 + margin, y2 + margin), image_width, image_height)
    return Box(sx1, sy1, sx2, sy2, "context_crop")


def translate_box_to_crop(label: Box, crop: Box) -> tuple[float, float, float, float]:
    return (
        max(0.0, label.x1 - crop.x1),
        max(0.0, label.y1 - crop.y1),
        min(crop.width, label.x2 - crop.x1),
        min(crop.height, label.y2 - crop.y1),
    )


def region_id(index: int) -> str:
    return f"region_{index + 1:03d}"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def install_exception_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path),
        filemode="a",
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:  # type: ignore[no-untyped-def]
        logging.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            QMessageBox.critical(None, "Large Cloud Context Labeler Error", f"{exc_type.__name__}: {exc_value}")
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception


def sidecar_path_for(image_path: Path, output_dir: Path) -> Path:
    return output_dir / f"{image_path.stem}.largecloud.json"


def crop_path_for(image_path: Path, crop_dir: Path, index: int) -> Path:
    return crop_dir / f"{image_path.stem}_{region_id(index)}.png"


def export_region_crop(image_path: Path, crop_box: Box, crop_path: Path) -> None:
    image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"Could not read image for crop export: {image_path}")
    height, width = image.shape[:2]
    x1, y1, x2, y2 = clamp_xyxy(box_tuple(crop_box), width, height)
    xi1, yi1, xi2, yi2 = [int(round(v)) for v in (x1, y1, x2, y2)]
    if xi2 <= xi1 or yi2 <= yi1:
        raise ValueError(f"Invalid crop box for {image_path}: {crop_box}")
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(crop_path), image[yi1:yi2, xi1:xi2])


def image_size(path: Path) -> tuple[int, int]:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    height, width = image.shape[:2]
    return width, height


def load_regions(path: Path, default_class_name: str) -> list[Region]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Region.from_payload(item, default_class_name) for item in payload.get("regions", [])]


def write_annotation(
    image_path: Path,
    sidecar_path: Path,
    crop_dir: Path,
    regions: list[Region],
    class_name: str,
    source_manifest_row: dict[str, Any] | None = None,
) -> None:
    width, height = image_size(image_path)
    crop_paths: dict[int, Path] = {}
    for index, region in enumerate(regions):
        if region.crop_box is None:
            continue
        crop_path = crop_path_for(image_path, crop_dir, index)
        export_region_crop(image_path, region.crop_box, crop_path)
        crop_paths[index] = crop_path

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "updated_at": now_utc(),
        "image_path": str(image_path.resolve()),
        "image_width": width,
        "image_height": height,
        "coordinate_space": "source_image_pixels",
        "default_class_name": class_name,
        "regions": [region.to_payload(crop_paths.get(index)) for index, region in enumerate(regions)],
    }
    if source_manifest_row is not None:
        payload["source_manifest_row"] = source_manifest_row
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_images_from_manifest(manifest_path: Path) -> tuple[list[Path], dict[str, dict[str, Any]]]:
    images: list[Path] = []
    rows_by_image: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(manifest_path):
        render_path = row.get("render_path") or row.get("image_path") or row.get("path")
        if not render_path:
            continue
        path = Path(render_path)
        if path.exists():
            resolved = path.resolve()
            images.append(resolved)
            rows_by_image[str(resolved)] = row
    return images, rows_by_image


def read_images_from_path(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() in {".txt"}:
            return [Path(line.strip()).resolve() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [path.resolve()]
    suffixes = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
    return sorted(item.resolve() for item in path.iterdir() if item.suffix.lower() in suffixes)


class ImageCanvas(QGraphicsView):
    box_created = pyqtSignal(str, tuple)
    selection_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.mode = "label"
        self.image_width = 0
        self.image_height = 0
        self.pixmap_item: QGraphicsPixmapItem | None = None
        self.drawing = False
        self.panning = False
        self.pan_last = QPoint()
        self.start_point = None
        self.temp_rect: QGraphicsRectItem | None = None

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def load_image(self, image_path: Path) -> None:
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            raise FileNotFoundError(f"Could not load image: {image_path}")
        self.scene_obj.clear()
        self.pixmap_item = self.scene_obj.addPixmap(pixmap)
        self.pixmap_item.setZValue(-10)
        self.image_width = pixmap.width()
        self.image_height = pixmap.height()
        self.setSceneRect(QRectF(0, 0, self.image_width, self.image_height))
        self.resetTransform()
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def draw_regions(self, regions: list[Region], active_region: int) -> None:
        for item in list(self.scene_obj.items()):
            if item is not self.pixmap_item:
                self.scene_obj.removeItem(item)
        for r_index, region in enumerate(regions):
            active = r_index == active_region
            for l_index, label in enumerate(region.labels):
                self._add_rect_item(label, "label", r_index, l_index, active)
            if region.crop_box is not None:
                self._add_rect_item(region.crop_box, "crop", r_index, -1, active)

    def selected_ref(self) -> tuple[str, int, int] | None:
        for item in self.scene_obj.selectedItems():
            kind = item.data(0)
            if kind in {"label", "crop"}:
                return (str(kind), int(item.data(1)), int(item.data(2)))
        return None

    def _add_rect_item(self, box: Box, kind: str, region_index: int, label_index: int, active: bool) -> None:
        rect = QRectF(box.x1, box.y1, box.width, box.height)
        item = QGraphicsRectItem(rect)
        if kind == "crop":
            color = QColor(255, 136, 0) if active else QColor(190, 125, 55)
            pen = QPen(color, 5 if active else 3)
            pen.setStyle(Qt.SolidLine if active else Qt.DashLine)
            z = 5 if active else 1
            text = f"R{region_index + 1} crop"
        else:
            color = QColor(0, 190, 80) if active else QColor(90, 150, 120)
            pen = QPen(color, 4 if active else 2)
            z = 10 if active else 2
            text = f"R{region_index + 1} L{label_index + 1}"
        item.setPen(pen)
        item.setBrush(QBrush(Qt.NoBrush))
        item.setFlags(QGraphicsItem.ItemIsSelectable)
        item.setData(0, kind)
        item.setData(1, region_index)
        item.setData(2, label_index)
        item.setZValue(z)
        self.scene_obj.addItem(item)
        label_item = QGraphicsSimpleTextItem(text)
        label_item.setBrush(QBrush(color))
        label_item.setPos(box.x1 + 4, max(0.0, box.y1 - 22))
        label_item.setZValue(z + 1)
        self.scene_obj.addItem(label_item)

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() in {Qt.RightButton, Qt.MiddleButton}:
            self.panning = True
            self.pan_last = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item is not None and item.data(0) in {"label", "crop"}:
                super().mousePressEvent(event)
                self.selection_changed.emit()
                return
            scene_point = self.mapToScene(event.pos())
            if not self.sceneRect().contains(scene_point):
                return
            self.drawing = True
            self.start_point = scene_point
            self.temp_rect = QGraphicsRectItem(QRectF(scene_point, scene_point))
            color = QColor(255, 136, 0) if self.mode == "crop" else QColor(0, 190, 80)
            self.temp_rect.setPen(QPen(color, 3, Qt.DashLine))
            self.temp_rect.setZValue(99)
            self.scene_obj.addItem(self.temp_rect)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.panning:
            delta = event.pos() - self.pan_last
            self.pan_last = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            return
        if self.drawing and self.temp_rect is not None and self.start_point is not None:
            scene_point = self.mapToScene(event.pos())
            scene_point.setX(max(0.0, min(float(self.image_width), scene_point.x())))
            scene_point.setY(max(0.0, min(float(self.image_height), scene_point.y())))
            self.temp_rect.setRect(QRectF(self.start_point, scene_point).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.panning and event.button() in {Qt.RightButton, Qt.MiddleButton}:
            self.panning = False
            self.setCursor(Qt.ArrowCursor)
            return
        if self.drawing and event.button() == Qt.LeftButton and self.temp_rect is not None:
            rect = self.temp_rect.rect()
            self.scene_obj.removeItem(self.temp_rect)
            self.temp_rect = None
            self.drawing = False
            self.start_point = None
            if rect.width() >= MIN_BOX_SIDE and rect.height() >= MIN_BOX_SIDE:
                box = clamp_xyxy((rect.left(), rect.top(), rect.right(), rect.bottom()), self.image_width, self.image_height)
                if self.mode == "crop":
                    box = square_box_around(box, self.image_width, self.image_height)
                self.box_created.emit(self.mode, box)
            return
        super().mouseReleaseEvent(event)


class LargeCloudContextLabeler(QMainWindow):
    def __init__(
        self,
        image_paths: list[Path],
        output_dir: Path,
        crop_dir: Path,
        class_name: str,
        rows_by_image: dict[str, dict[str, Any]] | None = None,
        initial_index: int = 0,
    ) -> None:
        super().__init__()
        if not image_paths:
            raise ValueError("No images to label.")
        self.image_paths = image_paths
        self.output_dir = output_dir
        self.crop_dir = crop_dir
        self.class_name = class_name
        self.rows_by_image = rows_by_image or {}
        self.index = max(0, min(initial_index, len(image_paths) - 1))
        self.regions: list[Region] = []
        self.active_region = 0

        self.canvas = ImageCanvas()
        self.canvas.box_created.connect(self.on_box_created)
        self.canvas.selection_changed.connect(self.refresh_status)
        self.setCentralWidget(self.canvas)

        self.region_list = QListWidget()
        self.region_list.currentRowChanged.connect(self.on_region_selected)
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(0, 100)
        self.margin_spin.setValue(15)
        self.info_label = QLabel()
        self._build_actions()
        self._build_dock()
        self.setStatusBar(QStatusBar())
        self.resize(1500, 950)
        self.load_current()

    def _build_actions(self) -> None:
        toolbar = QToolBar("Large Cloud Context")
        self.addToolBar(toolbar)

        actions = [
            ("Prev", "P", self.prev_image),
            ("Next", "N", self.next_image),
            ("Save", "Ctrl+S", self.save_current),
            ("Save + Next", "Ctrl+N", self.save_and_next),
            ("Label Mode", "B", lambda: self.set_mode("label")),
            ("Crop Mode", "R", lambda: self.set_mode("crop")),
            ("New Region", "Ctrl+R", self.new_region),
            ("Auto Crop", "A", self.auto_crop_active),
            ("Delete Selected", "Del", self.delete_selected),
            ("Delete Region", "Ctrl+Del", self.delete_active_region),
            ("Fit", "F", lambda: self.canvas.fitInView(self.canvas.sceneRect(), Qt.KeepAspectRatio)),
            ("Help", "H", self.show_help),
            ("Open", "Ctrl+O", self.open_images_dialog),
        ]
        for text, shortcut, callback in actions:
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Auto-crop margin %"))
        toolbar.addWidget(self.margin_spin)

    def _build_dock(self) -> None:
        dock = QDockWidget("Regions", self)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(self.info_label)
        layout.addWidget(self.region_list)
        row = QHBoxLayout()
        new_btn = QPushButton("New Region")
        new_btn.clicked.connect(self.new_region)
        auto_btn = QPushButton("Auto Crop")
        auto_btn.clicked.connect(self.auto_crop_active)
        row.addWidget(new_btn)
        row.addWidget(auto_btn)
        layout.addLayout(row)
        dock.setWidget(panel)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    @property
    def image_path(self) -> Path:
        return self.image_paths[self.index]

    @property
    def sidecar_path(self) -> Path:
        return sidecar_path_for(self.image_path, self.output_dir)

    def ensure_region(self) -> Region:
        if not self.regions:
            self.regions.append(Region(region_id(0)))
            self.active_region = 0
        self.active_region = max(0, min(self.active_region, len(self.regions) - 1))
        return self.regions[self.active_region]

    def load_current(self) -> None:
        self.regions = load_regions(self.sidecar_path, self.class_name)
        if not self.regions:
            self.regions = [Region(region_id(0))]
        self.active_region = 0
        self.canvas.load_image(self.image_path)
        self.redraw()
        self.setWindowTitle(f"Large Cloud Context Labeler - {self.index + 1}/{len(self.image_paths)} - {self.image_path.name}")
        self.refresh_status()

    def redraw(self) -> None:
        self.canvas.draw_regions(self.regions, self.active_region)
        self.refresh_region_list()

    def refresh_region_list(self) -> None:
        self.region_list.blockSignals(True)
        self.region_list.clear()
        for index, region in enumerate(self.regions):
            crop = "crop" if region.crop_box is not None else "no crop"
            self.region_list.addItem(f"{region.id}: labels={len(region.labels)} {crop}")
        self.region_list.setCurrentRow(self.active_region)
        self.region_list.blockSignals(False)

    def refresh_status(self) -> None:
        total_labels = sum(len(region.labels) for region in self.regions)
        cropped = sum(1 for region in self.regions if region.crop_box is not None)
        self.info_label.setText(
            f"Image {self.index + 1}/{len(self.image_paths)}\n"
            f"{self.image_path.name}\n"
            f"Regions: {len(self.regions)} | labels: {total_labels} | crops: {cropped}\n"
            f"Sidecar: {self.sidecar_path.name}"
        )
        self.statusBar().showMessage(
            f"mode={self.canvas.mode} active=R{self.active_region + 1} "
            f"labels={total_labels} crops={cropped}"
        )

    def set_mode(self, mode: str) -> None:
        self.canvas.set_mode(mode)
        self.refresh_status()

    def on_box_created(self, mode: str, box_tuple_value: tuple) -> None:
        region = self.ensure_region()
        if mode == "crop":
            region.crop_box = Box(*box_tuple_value, "context_crop")
        else:
            region.labels.append(Box(*box_tuple_value, self.class_name))
        self.redraw()

    def on_region_selected(self, row: int) -> None:
        if row < 0 or row >= len(self.regions):
            return
        self.active_region = row
        self.redraw()

    def new_region(self) -> None:
        self.regions.append(Region(region_id(len(self.regions))))
        self.active_region = len(self.regions) - 1
        self.redraw()

    def delete_active_region(self) -> None:
        if not self.regions:
            return
        del self.regions[self.active_region]
        if not self.regions:
            self.regions.append(Region(region_id(0)))
        for index, region in enumerate(self.regions):
            region.id = region_id(index)
        self.active_region = max(0, min(self.active_region, len(self.regions) - 1))
        self.redraw()

    def delete_selected(self) -> None:
        selected = self.canvas.selected_ref()
        if selected is None:
            return
        kind, region_index, label_index = selected
        if region_index < 0 or region_index >= len(self.regions):
            return
        if kind == "crop":
            self.regions[region_index].crop_box = None
        elif kind == "label" and 0 <= label_index < len(self.regions[region_index].labels):
            del self.regions[region_index].labels[label_index]
        self.redraw()

    def auto_crop_active(self) -> None:
        region = self.ensure_region()
        crop = square_crop_around_labels(
            region.labels,
            self.canvas.image_width,
            self.canvas.image_height,
            margin_percent=int(self.margin_spin.value()),
        )
        if crop is None:
            QMessageBox.information(self, "Auto Crop", "Draw at least one label box in the active region first.")
            return
        region.crop_box = crop
        self.redraw()

    def save_current(self) -> None:
        source_row = self.rows_by_image.get(str(self.image_path.resolve()))
        write_annotation(
            self.image_path,
            self.sidecar_path,
            self.crop_dir,
            self.regions,
            self.class_name,
            source_manifest_row=source_row,
        )
        self.statusBar().showMessage(f"Saved {self.sidecar_path}", 5000)

    def save_and_next(self) -> None:
        self.save_current()
        self.next_image()

    def next_image(self) -> None:
        if self.index >= len(self.image_paths) - 1:
            self.statusBar().showMessage("Already at final image.", 3000)
            return
        self.index += 1
        self.load_current()

    def prev_image(self) -> None:
        if self.index <= 0:
            self.statusBar().showMessage("Already at first image.", 3000)
            return
        self.index -= 1
        self.load_current()

    def open_images_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open image", str(ROOT), "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)")
        if not path:
            return
        resolved = Path(path).resolve()
        self.image_paths = [resolved]
        self.rows_by_image = {}
        self.index = 0
        self.load_current()

    def show_help(self) -> None:
        QMessageBox.information(
            self,
            "Large Cloud Context Labeler",
            "Basic workflow:\n\n"
            "1. In Label Mode (B), drag boxes around whole visible clouds.\n"
            "2. Press A to auto-create a square context crop around this region's labels.\n"
            "3. Use Crop Mode (R) only if you want to manually draw/replace that crop.\n"
            "4. Press Ctrl+S to save, or Ctrl+N to save and move next.\n\n"
            "Multiple clouds on one page:\n"
            "- Press Ctrl+R for a new region, then repeat the label/crop steps.\n\n"
            "Navigation:\n"
            "- Mouse wheel zooms. Right or middle drag pans. F fits the page.\n"
            "- Delete removes the selected box. Ctrl+Delete removes the active region.",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Label whole-cloud boxes and per-region context crops on rendered pages. "
            "Saves CloudHammer large-cloud context JSON plus exported crop images."
        )
    )
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--images", type=Path, default=None, help="Image file, directory, or txt file of image paths.")
    source.add_argument("--manifest", type=Path, default=None, help="JSONL manifest with render_path/image_path rows.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "large_cloud_context_labels")
    parser.add_argument("--crop-dir", type=Path, default=ROOT / "data" / "large_cloud_context_crops")
    parser.add_argument("--class-name", type=str, default="cloud_whole")
    parser.add_argument("--initial-index", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    install_exception_logging(args.output_dir.resolve() / "large_cloud_context_labeler.log")
    rows_by_image: dict[str, dict[str, Any]] = {}
    if args.manifest is not None:
        image_paths, rows_by_image = read_images_from_manifest(args.manifest)
    elif args.images is not None:
        image_paths = read_images_from_path(args.images)
    else:
        default_manifest = ROOT / "data" / "manifests" / "pages_standard_drawings_no_index_20260427.jsonl"
        image_paths, rows_by_image = read_images_from_manifest(default_manifest)

    app = QApplication(sys.argv)
    window = LargeCloudContextLabeler(
        image_paths=image_paths,
        output_dir=args.output_dir.resolve(),
        crop_dir=args.crop_dir.resolve(),
        class_name=args.class_name,
        rows_by_image=rows_by_image,
        initial_index=args.initial_index,
    )
    window.show()
    return int(app.exec_())


if __name__ == "__main__":
    raise SystemExit(main())
