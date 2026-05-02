from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cloudhammer.manifests import read_jsonl  # noqa: E402

try:
    from PyQt5.QtCore import QRectF, Qt
    from PyQt5.QtGui import QColor, QKeySequence, QPen, QPixmap
    from PyQt5.QtWidgets import (
        QAction,
        QApplication,
        QDockWidget,
        QGraphicsPixmapItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsSimpleTextItem,
        QGraphicsView,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSizePolicy,
        QStatusBar,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError as exc:  # pragma: no cover - import-time user guidance
    raise SystemExit("PyQt5 is required. Use the project .venv that already runs LabelImg.") from exc


SCHEMA = "cloudhammer.whole_cloud_candidate_review.v1"
DEFAULT_MANIFEST = (
    ROOT
    / "runs"
    / "whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428"
    / "release_v1"
    / "review_queue.jsonl"
)
DEFAULT_REVIEW_LOG = (
    ROOT
    / "data"
    / "whole_cloud_candidate_reviews"
    / "whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428.release_v1.review.jsonl"
)

STATUS_LABELS = {
    "accept": "Accept",
    "false_positive": "False Positive",
    "partial": "Partial",
    "overmerged": "Overmerged",
    "duplicate": "Duplicate",
    "uncertain": "Uncertain",
}

STATUS_KEYS = {
    Qt.Key_A: "accept",
    Qt.Key_F: "false_positive",
    Qt.Key_P: "partial",
    Qt.Key_O: "overmerged",
    Qt.Key_D: "duplicate",
    Qt.Key_U: "uncertain",
}

FALSE_POSITIVE_REASONS = {
    "repeating_section_scallop": {
        "label": "Texture FP",
        "tags": ["hard_negative", "repeating_section_scallop", "insulation_edge_texture"],
        "description": "Repeated scallop/insulation-like section texture, not a revision cloud.",
    },
    "text_glyph_arcs": {
        "label": "Text FP",
        "tags": ["hard_negative", "text_glyph_arcs"],
        "description": "Text or glyph arcs mistaken for cloud motif fragments.",
    },
    "circular_symbol_fixture": {
        "label": "Symbol FP",
        "tags": ["hard_negative", "circular_symbol_fixture", "symbol_geometry"],
        "description": "Circular symbol, fixture, or annotation geometry mistaken for cloud motif fragments.",
    },
}


@dataclass(frozen=True)
class Candidate:
    row: dict[str, Any]
    index: int

    @property
    def candidate_id(self) -> str:
        return str(self.row["candidate_id"])

    @property
    def crop_path(self) -> Path:
        return resolve_cloudhammer_path(str(self.row["crop_image_path"]))

    @property
    def confidence(self) -> float:
        return float(self.row.get("whole_cloud_confidence", self.row.get("confidence", 0.0)))

    @property
    def size_bucket(self) -> str:
        return str(self.row.get("size_bucket") or "unknown")

    @property
    def member_count(self) -> int:
        return int(self.row.get("member_count") or 0)


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def load_candidates(manifest_path: Path) -> list[Candidate]:
    rows = list(read_jsonl(manifest_path))
    return [Candidate(row=row, index=index) for index, row in enumerate(rows, start=1)]


def sort_candidates(candidates: list[Candidate], order: str) -> list[Candidate]:
    if order == "confidence_asc":
        return sorted(candidates, key=lambda item: (item.confidence, item.size_bucket, item.candidate_id))
    if order == "confidence_desc":
        return sorted(candidates, key=lambda item: (-item.confidence, item.size_bucket, item.candidate_id))
    if order == "size_then_confidence":
        size_order = {"xlarge": 0, "large": 1, "medium": 2, "small": 3}
        return sorted(candidates, key=lambda item: (size_order.get(item.size_bucket, 9), item.confidence))
    return candidates


def load_latest_reviews(review_log: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not review_log.exists():
        return latest
    for line_number, line in enumerate(review_log.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logging.warning("Skipping malformed review line %s in %s", line_number, review_log)
            continue
        candidate_id = str(record.get("candidate_id") or "")
        if candidate_id:
            latest[candidate_id] = record
    return latest


def review_record(
    candidate: Candidate,
    status: str,
    manifest_path: Path,
    false_positive_reason: str | None = None,
) -> dict[str, Any]:
    row = candidate.row
    record = {
        "schema": SCHEMA,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": os.environ.get("USERNAME") or os.environ.get("USER") or "unknown",
        "candidate_id": candidate.candidate_id,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "manifest_path": str(manifest_path),
        "crop_image_path": str(candidate.crop_path),
        "pdf_path": row.get("pdf_path"),
        "pdf_stem": row.get("pdf_stem"),
        "page_number": row.get("page_number"),
        "whole_cloud_confidence": row.get("whole_cloud_confidence"),
        "confidence_tier": row.get("confidence_tier"),
        "size_bucket": row.get("size_bucket"),
        "member_count": row.get("member_count"),
        "bbox_page_xyxy": row.get("bbox_page_xyxy"),
        "crop_box_page_xyxy": row.get("crop_box_page_xyxy"),
    }
    if false_positive_reason:
        reason = FALSE_POSITIVE_REASONS[false_positive_reason]
        record["false_positive_reason"] = false_positive_reason
        record["false_positive_reason_label"] = reason["label"]
        record["review_tags"] = reason["tags"]
        record["review_note"] = reason["description"]
    return record


def append_review(review_log: Path, record: dict[str, Any]) -> None:
    review_log.parent.mkdir(parents=True, exist_ok=True)
    with review_log.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()


def box_from_row(row: dict[str, Any], key: str) -> tuple[float, float, float, float] | None:
    values = row.get(key)
    if not isinstance(values, list) or len(values) != 4:
        return None
    return tuple(float(value) for value in values)


def compact_middle(value: str, max_chars: int = 54) -> str:
    if len(value) <= max_chars:
        return value
    keep = max(8, (max_chars - 3) // 2)
    return f"{value[:keep]}...{value[-keep:]}"


def resolve_cloudhammer_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.exists():
        return path.resolve()
    parts = path.parts
    for index, part in enumerate(parts):
        if part.lower() == "cloudhammer":
            relocated = ROOT.joinpath(*parts[index + 1 :])
            if relocated.exists():
                return relocated.resolve()
    return path


class CandidateView(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        self.setRenderHints(self.renderHints())
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setInteractive(True)
        self.setMouseTracking(True)
        self.pixmap_item: QGraphicsPixmapItem | None = None
        self._fit_to_window = True
        self._zoom_steps = 0

    def load_candidate(self, candidate: Candidate) -> None:
        self.scene_obj.clear()
        self.resetTransform()
        self._fit_to_window = True
        self._zoom_steps = 0
        pixmap = QPixmap(str(candidate.crop_path))
        if pixmap.isNull():
            text = self.scene_obj.addText(f"Could not load image:\n{candidate.crop_path}")
            text.setDefaultTextColor(QColor(180, 0, 0))
            self.fitInView(self.scene_obj.itemsBoundingRect(), Qt.KeepAspectRatio)
            return
        self.pixmap_item = self.scene_obj.addPixmap(pixmap)
        self.scene_obj.setSceneRect(QRectF(pixmap.rect()))
        self._draw_evidence_boxes(candidate, pixmap.width(), pixmap.height())
        self.fit_to_window()

    def fit_to_window(self) -> None:
        if not self.scene_obj.items():
            return
        self.resetTransform()
        self.fitInView(self.scene_obj.sceneRect(), Qt.KeepAspectRatio)
        self._fit_to_window = True
        self._zoom_steps = 0

    def zoom_in(self) -> None:
        self._apply_zoom(1.18)

    def zoom_out(self) -> None:
        self._apply_zoom(1 / 1.18)

    def _apply_zoom(self, factor: float) -> None:
        next_steps = self._zoom_steps + (1 if factor > 1 else -1)
        if next_steps < -12 or next_steps > 30:
            return
        self._fit_to_window = False
        self._zoom_steps = next_steps
        self.scale(factor, factor)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if not self.scene_obj.items():
            return
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        self._apply_zoom(1.18 if delta > 0 else 1 / 1.18)
        event.accept()

    def _draw_evidence_boxes(self, candidate: Candidate, image_width: int, image_height: int) -> None:
        row = candidate.row
        crop_box = box_from_row(row, "crop_box_page_xyxy")
        if crop_box is None:
            return
        crop_x1, crop_y1, crop_x2, crop_y2 = crop_box
        crop_width = max(1.0, crop_x2 - crop_x1)
        crop_height = max(1.0, crop_y2 - crop_y1)

        def translate(box: tuple[float, float, float, float]) -> QRectF:
            x1, y1, x2, y2 = box
            sx = image_width / crop_width
            sy = image_height / crop_height
            return QRectF((x1 - crop_x1) * sx, (y1 - crop_y1) * sy, (x2 - x1) * sx, (y2 - y1) * sy)

        for member in row.get("member_boxes_page_xyxy") or []:
            if isinstance(member, list) and len(member) == 4:
                rect = QGraphicsRectItem(translate(tuple(float(value) for value in member)))
                rect.setPen(QPen(QColor(135, 135, 135), 3))
                self.scene_obj.addItem(rect)

        candidate_box = box_from_row(row, "bbox_page_xyxy")
        if candidate_box is not None:
            rect = QGraphicsRectItem(translate(candidate_box))
            rect.setPen(QPen(QColor(0, 190, 80), 5))
            self.scene_obj.addItem(rect)
            label = QGraphicsSimpleTextItem("model/group box")
            label.setBrush(QColor(0, 110, 50))
            label.setPos(rect.rect().x(), max(0.0, rect.rect().y() - 24))
            self.scene_obj.addItem(label)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._fit_to_window and self.scene_obj.items():
            self.fitInView(self.scene_obj.sceneRect(), Qt.KeepAspectRatio)


class ReviewerWindow(QMainWindow):
    def __init__(
        self,
        candidates: list[Candidate],
        manifest_path: Path,
        review_log: Path,
        latest_reviews: dict[str, dict[str, Any]],
    ) -> None:
        super().__init__()
        self.candidates = candidates
        self.manifest_path = manifest_path
        self.review_log = review_log
        self.latest_reviews = latest_reviews
        self.index = self._first_unreviewed_index()

        self.view = CandidateView()
        self.setCentralWidget(self.view)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setMinimumWidth(230)
        self.info.setMaximumWidth(360)
        self.info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(230)
        self.list_widget.setMaximumWidth(380)
        self.list_widget.setTextElideMode(Qt.ElideMiddle)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setUniformItemSizes(True)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._build_toolbar()
        self._build_dock()
        self.setWindowTitle("CloudHammer Whole-Cloud Candidate Reviewer")
        self.resize(1400, 950)
        self.load_current()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Review")
        self.addToolBar(toolbar)
        actions = [
            ("Accept", "A", lambda: self.mark("accept")),
            ("False +", "F", lambda: self.mark("false_positive")),
            ("Texture FP", "T", lambda: self.mark_false_positive_reason("repeating_section_scallop")),
            ("Text FP", "Ctrl+T", lambda: self.mark_false_positive_reason("text_glyph_arcs")),
            ("Symbol FP", "S", lambda: self.mark_false_positive_reason("circular_symbol_fixture")),
            ("Partial", "P", lambda: self.mark("partial")),
            ("Overmerged", "O", lambda: self.mark("overmerged")),
            ("Duplicate", "D", lambda: self.mark("duplicate")),
            ("Uncertain", "U", lambda: self.mark("uncertain")),
            ("Prev", "Left", self.previous_candidate),
            ("Next", "Right", self.next_candidate),
            ("Next Open", "N", self.next_unreviewed),
            ("Fit", "0", self.view.fit_to_window),
            ("Zoom In", "=", self.view.zoom_in),
            ("Zoom Out", "-", self.view.zoom_out),
        ]
        for label, shortcut, callback in actions:
            action = QAction(label, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            toolbar.addAction(action)

    def _build_dock(self) -> None:
        dock = QDockWidget("Candidate", self)
        dock.setMinimumWidth(240)
        dock.setMaximumWidth(420)
        container = QWidget()
        container.setMinimumWidth(230)
        container.setMaximumWidth(400)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(self.info)
        layout.addWidget(self.list_widget)

        button_row_top = QHBoxLayout()
        button_row_bottom = QHBoxLayout()
        for label, status in [
            ("A", "accept"),
            ("F", "false_positive"),
            ("P", "partial"),
            ("O", "overmerged"),
            ("D", "duplicate"),
            ("U", "uncertain"),
        ][:3]:
            button = QPushButton(label)
            button.setToolTip(STATUS_LABELS[status])
            button.setMaximumWidth(72)
            button.clicked.connect(lambda checked=False, value=status: self.mark(value))
            button_row_top.addWidget(button)
        for label, status in [
            ("A", "accept"),
            ("F", "false_positive"),
            ("P", "partial"),
            ("O", "overmerged"),
            ("D", "duplicate"),
            ("U", "uncertain"),
        ][3:]:
            button = QPushButton(label)
            button.setToolTip(STATUS_LABELS[status])
            button.setMaximumWidth(72)
            button.clicked.connect(lambda checked=False, value=status: self.mark(value))
            button_row_bottom.addWidget(button)
        layout.addLayout(button_row_top)
        layout.addLayout(button_row_bottom)

        reason_row = QHBoxLayout()
        texture_fp_button = QPushButton("Texture FP")
        texture_fp_button.setToolTip("T: false positive, repeated scallop/insulation-like section texture")
        texture_fp_button.clicked.connect(lambda checked=False: self.mark_false_positive_reason("repeating_section_scallop"))
        text_fp_button = QPushButton("Text FP")
        text_fp_button.setToolTip("Ctrl+T: false positive, text/glyph arcs")
        text_fp_button.clicked.connect(lambda checked=False: self.mark_false_positive_reason("text_glyph_arcs"))
        symbol_fp_button = QPushButton("Symbol FP")
        symbol_fp_button.setToolTip("S: false positive, circular symbol/fixture geometry")
        symbol_fp_button.clicked.connect(lambda checked=False: self.mark_false_positive_reason("circular_symbol_fixture"))
        reason_row.addWidget(texture_fp_button)
        reason_row.addWidget(text_fp_button)
        reason_row.addWidget(symbol_fp_button)
        layout.addLayout(reason_row)

        nav_row = QHBoxLayout()
        prev_button = QPushButton("Prev")
        prev_button.clicked.connect(self.previous_candidate)
        next_button = QPushButton("Next")
        next_button.clicked.connect(self.next_candidate)
        next_open_button = QPushButton("Next Open")
        next_open_button.clicked.connect(self.next_unreviewed)
        nav_row.addWidget(prev_button)
        nav_row.addWidget(next_button)
        nav_row.addWidget(next_open_button)
        layout.addLayout(nav_row)

        dock.setWidget(container)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.resizeDocks([dock], [300], Qt.Horizontal)

    def _first_unreviewed_index(self) -> int:
        for index, candidate in enumerate(self.candidates):
            if candidate.candidate_id not in self.latest_reviews:
                return index
        return 0

    def current(self) -> Candidate:
        return self.candidates[self.index]

    def load_current(self) -> None:
        if not self.candidates:
            QMessageBox.information(self, "No Candidates", "No candidates found in manifest.")
            return
        candidate = self.current()
        self.view.load_candidate(candidate)
        self._refresh_info(candidate)
        logging.info("Loaded candidate %s", candidate.candidate_id)

    def _refresh_info(self, candidate: Candidate) -> None:
        reviewed = len(self.latest_reviews)
        total = len(self.candidates)
        current_review = self.latest_reviews.get(candidate.candidate_id)
        status = "unreviewed" if current_review is None else str(current_review.get("status"))
        row = candidate.row
        crop_name = candidate.crop_path.name
        review_name = self.review_log.name
        marker_bucket = row.get("marker_anchor_bucket")
        marker_lines = []
        if marker_bucket is not None:
            nearest_bbox = row.get("nearest_matching_marker_bbox_distance")
            nearest_center = row.get("nearest_matching_marker_center_distance")
            nearest_bbox_text = "-" if nearest_bbox is None else f"{float(nearest_bbox):.0f}px"
            nearest_center_text = "-" if nearest_center is None else f"{float(nearest_center):.0f}px"
            marker_lines = [
                "",
                "Markers:",
                f"Anchor: {marker_bucket}",
                f"Target digit: {row.get('target_digit') or '?'}",
                f"Page/crop matching: {row.get('matching_page_marker_count')} / {row.get('matching_markers_in_crop')}",
                f"Nearest bbox/center: {nearest_bbox_text} / {nearest_center_text}",
            ]
        lines = [
            f"Index: {self.index + 1} / {total}",
            f"Reviewed: {reviewed} / {total}",
            f"Status: {status}",
            "",
            f"ID: {compact_middle(candidate.candidate_id, 42)}",
            f"Confidence: {candidate.confidence:.3f} ({row.get('confidence_tier')})",
            f"Size: {candidate.size_bucket}",
            f"Members: {candidate.member_count}",
            f"Policy: {row.get('policy_bucket', 'unbucketed')}",
            f"Page: {compact_middle(str(row.get('pdf_stem')), 34)} p{row.get('page_number')}",
            "",
            f"Crop: {compact_middle(crop_name, 42)}",
            f"Log: {compact_middle(review_name, 42)}",
            *marker_lines,
            "",
            "Wheel zooms. Drag pans. 0 fits.",
            "T marks repeated scallop/insulation texture as a tagged false positive.",
            "Ctrl+T marks text/glyph arcs as a tagged false positive.",
            "S marks circular symbol/fixture geometry as a tagged false positive.",
        ]
        self.info.setToolTip(f"{candidate.candidate_id}\n\n{candidate.crop_path}\n\n{self.review_log}")
        self.info.setText("\n".join(lines))
        self.status_bar.showMessage(f"{candidate.candidate_id} | {status}")
        self._refresh_history_list()

    def _refresh_history_list(self) -> None:
        self.list_widget.clear()
        for candidate in self.candidates:
            review = self.latest_reviews.get(candidate.candidate_id)
            status = "-" if review is None else str(review.get("status"))
            item = QListWidgetItem(
                f"{candidate.index:03d} {status[:5]:5s} {candidate.confidence:.2f} "
                f"{candidate.size_bucket[:3]:3s} n={candidate.member_count} "
                f"{compact_middle(candidate.candidate_id, 34)}"
            )
            item.setToolTip(candidate.candidate_id)
            self.list_widget.addItem(item)
        self.list_widget.setCurrentRow(self.index)

    def mark(self, status: str) -> None:
        if status not in STATUS_LABELS:
            return
        candidate = self.current()
        record = review_record(candidate, status, self.manifest_path)
        append_review(self.review_log, record)
        self.latest_reviews[candidate.candidate_id] = record
        logging.info("Reviewed candidate %s as %s", candidate.candidate_id, status)
        self.next_unreviewed()

    def mark_false_positive_reason(self, false_positive_reason: str) -> None:
        if false_positive_reason not in FALSE_POSITIVE_REASONS:
            return
        candidate = self.current()
        record = review_record(candidate, "false_positive", self.manifest_path, false_positive_reason=false_positive_reason)
        append_review(self.review_log, record)
        self.latest_reviews[candidate.candidate_id] = record
        logging.info(
            "Reviewed candidate %s as false_positive reason=%s",
            candidate.candidate_id,
            false_positive_reason,
        )
        self.next_unreviewed()

    def next_candidate(self) -> None:
        if not self.candidates:
            return
        self.index = min(len(self.candidates) - 1, self.index + 1)
        self.load_current()

    def previous_candidate(self) -> None:
        if not self.candidates:
            return
        self.index = max(0, self.index - 1)
        self.load_current()

    def next_unreviewed(self) -> None:
        if not self.candidates:
            return
        for offset in range(1, len(self.candidates) + 1):
            next_index = (self.index + offset) % len(self.candidates)
            if self.candidates[next_index].candidate_id not in self.latest_reviews:
                self.index = next_index
                self.load_current()
                return
        self.load_current()
        QMessageBox.information(self, "Review Complete", "All candidates in this queue have a current review.")

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        key = event.key()
        if event.modifiers() & Qt.ControlModifier and key == Qt.Key_T:
            self.mark_false_positive_reason("text_glyph_arcs")
            return
        if key in STATUS_KEYS:
            self.mark(STATUS_KEYS[key])
            return
        if key == Qt.Key_S:
            self.mark_false_positive_reason("circular_symbol_fixture")
            return
        if key == Qt.Key_T:
            self.mark_false_positive_reason("repeating_section_scallop")
            return
        if key in {Qt.Key_Right, Qt.Key_Space}:
            self.next_candidate()
            return
        if key == Qt.Key_Left:
            self.previous_candidate()
            return
        if key == Qt.Key_N:
            self.next_unreviewed()
            return
        if key == Qt.Key_0:
            self.view.fit_to_window()
            return
        if key in {Qt.Key_Plus, Qt.Key_Equal}:
            self.view.zoom_in()
            return
        if key == Qt.Key_Minus:
            self.view.zoom_out()
            return
        super().keyPressEvent(event)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review whole-cloud candidate crops with fast triage hotkeys.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--review-log", type=Path, default=DEFAULT_REVIEW_LOG)
    parser.add_argument(
        "--order",
        choices=["manifest", "confidence_asc", "confidence_desc", "size_then_confidence"],
        default="confidence_asc",
    )
    parser.add_argument("--log-path", type=Path, default=None)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    review_log = args.review_log.resolve()
    log_path = (args.log_path or review_log.with_suffix(".log")).resolve()
    configure_logging(log_path)

    candidates = sort_candidates(load_candidates(manifest_path), args.order)
    latest_reviews = load_latest_reviews(review_log)
    logging.info(
        "Starting reviewer manifest=%s review_log=%s candidates=%s reviewed=%s order=%s",
        manifest_path,
        review_log,
        len(candidates),
        len(latest_reviews),
        args.order,
    )

    app = QApplication(sys.argv)
    window = ReviewerWindow(candidates, manifest_path, review_log, latest_reviews)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
