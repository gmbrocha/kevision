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

from cloudhammer.contracts.detections import CloudDetection, xywh_to_xyxy, xyxy_to_xywh  # noqa: E402
from cloudhammer.infer.fragment_grouping import GroupingParams, group_fragment_detections  # noqa: E402
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


SCHEMA = "cloudhammer.whole_cloud_split_review.v1"
DEFAULT_MANIFEST = (
    ROOT
    / "runs"
    / "whole_cloud_candidates_broad_deduped_lowconf_context_20260428"
    / "policy_v1"
    / "needs_split_review.jsonl"
)
DEFAULT_REVIEW_LOG = (
    ROOT
    / "data"
    / "whole_cloud_split_reviews"
    / "whole_cloud_candidates_broad_deduped_lowconf_context_20260428.split_review.jsonl"
)

STATUS_LABELS = {
    "current_ok": "Current OK",
    "split_variant_1": "Use Split 1",
    "split_variant_2": "Use Split 2",
    "split_variant_3": "Use Split 3",
    "split_variant_4": "Use Split 4",
    "still_overmerged": "Still Overmerged",
    "false_positive": "False Positive",
    "partial": "Partial",
    "uncertain": "Uncertain",
}

STATUS_KEYS = {
    Qt.Key_G: "current_ok",
    Qt.Key_1: "split_variant_1",
    Qt.Key_2: "split_variant_2",
    Qt.Key_3: "split_variant_3",
    Qt.Key_4: "split_variant_4",
    Qt.Key_O: "still_overmerged",
    Qt.Key_F: "false_positive",
    Qt.Key_P: "partial",
    Qt.Key_U: "uncertain",
}

VARIANT_PARAMS: list[tuple[str, GroupingParams]] = [
    (
        "tight",
        GroupingParams(
            expansion_ratio=0.12,
            min_padding=20.0,
            max_padding=90.0,
            group_margin_ratio=0.05,
            min_group_margin=10.0,
            max_group_margin=120.0,
            split_min_members=3,
            split_min_partition_members=1,
            split_gap_ratio=0.08,
            split_min_gap=120.0,
            split_max_fill_ratio=0.65,
        ),
    ),
    (
        "balanced",
        GroupingParams(
            expansion_ratio=0.22,
            min_padding=45.0,
            max_padding=180.0,
            group_margin_ratio=0.06,
            min_group_margin=15.0,
            max_group_margin=180.0,
            split_min_members=4,
            split_min_partition_members=1,
            split_gap_ratio=0.10,
            split_min_gap=180.0,
            split_max_fill_ratio=0.55,
        ),
    ),
    (
        "relaxed_current",
        GroupingParams(
            expansion_ratio=0.55,
            min_padding=120.0,
            max_padding=850.0,
            group_margin_ratio=0.08,
            min_group_margin=25.0,
            max_group_margin=350.0,
            split_min_members=4,
            split_min_partition_members=1,
            split_gap_ratio=0.10,
            split_min_gap=240.0,
            split_max_fill_ratio=0.55,
        ),
    ),
    (
        "very_tight",
        GroupingParams(
            expansion_ratio=0.04,
            min_padding=8.0,
            max_padding=45.0,
            group_margin_ratio=0.04,
            min_group_margin=8.0,
            max_group_margin=80.0,
            split_min_members=2,
            split_min_partition_members=1,
            split_gap_ratio=0.06,
            split_min_gap=80.0,
            split_max_fill_ratio=0.75,
        ),
    ),
]

BOX_COLORS = [
    QColor(255, 128, 0),
    QColor(0, 170, 255),
    QColor(180, 80, 255),
    QColor(220, 190, 0),
    QColor(0, 190, 150),
    QColor(255, 70, 120),
]
BOX_COLOR_NAMES = ["orange", "cyan", "purple", "yellow", "teal", "pink"]


@dataclass(frozen=True)
class SplitProposal:
    variant_index: int
    name: str
    groups: list[dict[str, Any]]

    @property
    def status(self) -> str:
        return f"split_variant_{self.variant_index}"

    @property
    def group_count(self) -> int:
        return len(self.groups)


@dataclass(frozen=True)
class Candidate:
    row: dict[str, Any]
    index: int
    proposals: list[SplitProposal]

    @property
    def candidate_id(self) -> str:
        return str(self.row["candidate_id"])

    @property
    def crop_path(self) -> Path:
        return Path(str(self.row["crop_image_path"]))

    @property
    def confidence(self) -> float:
        return float(self.row.get("whole_cloud_confidence", self.row.get("confidence", 0.0)))

    @property
    def member_count(self) -> int:
        return int(self.row.get("member_count") or 0)

    @property
    def fill_ratio(self) -> float:
        value = self.row.get("group_fill_ratio")
        return 0.0 if value is None else float(value)


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


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


def make_member_detections(row: dict[str, Any]) -> list[CloudDetection]:
    boxes = row.get("member_boxes_page_xyxy") or []
    confidences = row.get("member_confidences") or []
    detections: list[CloudDetection] = []
    for index, box in enumerate(boxes):
        if not isinstance(box, list) or len(box) != 4:
            continue
        confidence = float(confidences[index]) if index < len(confidences) else float(row.get("confidence") or 0.0)
        detections.append(
            CloudDetection(
                confidence=confidence,
                bbox_page=xyxy_to_xywh(tuple(float(value) for value in box)),
                crop_path=None,
                source_mode="page_tile",
            )
        )
    return detections


def proposal_from_groups(index: int, name: str, groups: list[CloudDetection]) -> SplitProposal:
    return SplitProposal(
        variant_index=index,
        name=name,
        groups=[
            {
                "bbox_page_xyxy": list(xywh_to_xyxy(group.bbox_page)),
                "bbox_page_xywh": group.bbox_page,
                "confidence": group.confidence,
                "member_count": group.metadata.get("member_count"),
                "member_indexes": group.metadata.get("member_indexes"),
                "fill_ratio": group.metadata.get("fill_ratio"),
            }
            for group in groups
        ],
    )


def build_split_proposals(row: dict[str, Any]) -> list[SplitProposal]:
    detections = make_member_detections(row)
    if not detections:
        return []
    page_width = int(row.get("page_width") or 1)
    page_height = int(row.get("page_height") or 1)
    proposals: list[SplitProposal] = []
    seen: set[tuple[tuple[int, int, int, int], ...]] = set()
    for index, (name, params) in enumerate(VARIANT_PARAMS, start=1):
        groups = group_fragment_detections(detections, page_width, page_height, params)
        signature = tuple(
            sorted(tuple(int(round(value)) for value in xywh_to_xyxy(group.bbox_page)) for group in groups)
        )
        if signature in seen:
            continue
        seen.add(signature)
        proposals.append(proposal_from_groups(len(proposals) + 1, name, groups))
    return proposals


def load_candidates(manifest_path: Path) -> list[Candidate]:
    rows = list(read_jsonl(manifest_path))
    candidates = [
        Candidate(row=row, index=index, proposals=build_split_proposals(row))
        for index, row in enumerate(rows, start=1)
    ]
    return sorted(candidates, key=lambda item: (-item.member_count, item.fill_ratio, -item.confidence, item.candidate_id))


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


def selected_proposal(candidate: Candidate, status: str) -> SplitProposal | None:
    if not status.startswith("split_variant_"):
        return None
    try:
        index = int(status.rsplit("_", 1)[1])
    except ValueError:
        return None
    return next((proposal for proposal in candidate.proposals if proposal.variant_index == index), None)


def review_record(candidate: Candidate, status: str, manifest_path: Path) -> dict[str, Any]:
    row = candidate.row
    proposal = selected_proposal(candidate, status)
    return {
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
        "size_bucket": row.get("size_bucket"),
        "member_count": row.get("member_count"),
        "group_fill_ratio": row.get("group_fill_ratio"),
        "bbox_page_xyxy": row.get("bbox_page_xyxy"),
        "crop_box_page_xyxy": row.get("crop_box_page_xyxy"),
        "proposal": None
        if proposal is None
        else {
            "variant_index": proposal.variant_index,
            "name": proposal.name,
            "group_count": proposal.group_count,
            "groups": proposal.groups,
        },
        "proposal_summaries": [
            {"variant_index": proposal.variant_index, "name": proposal.name, "group_count": proposal.group_count}
            for proposal in candidate.proposals
        ],
    }


def append_review(review_log: Path, record: dict[str, Any]) -> None:
    review_log.parent.mkdir(parents=True, exist_ok=True)
    with review_log.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()


class CandidateView(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
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
        self._draw_boxes(candidate, pixmap.width(), pixmap.height())
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
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        self._apply_zoom(1.18 if delta > 0 else 1 / 1.18)
        event.accept()

    def _translate_fn(self, row: dict[str, Any], image_width: int, image_height: int):
        crop_box = box_from_row(row, "crop_box_page_xyxy")
        if crop_box is None:
            return None
        crop_x1, crop_y1, crop_x2, crop_y2 = crop_box
        crop_width = max(1.0, crop_x2 - crop_x1)
        crop_height = max(1.0, crop_y2 - crop_y1)

        def translate(box: tuple[float, float, float, float]) -> QRectF:
            x1, y1, x2, y2 = box
            sx = image_width / crop_width
            sy = image_height / crop_height
            return QRectF((x1 - crop_x1) * sx, (y1 - crop_y1) * sy, (x2 - x1) * sx, (y2 - y1) * sy)

        return translate

    def _draw_boxes(self, candidate: Candidate, image_width: int, image_height: int) -> None:
        translate = self._translate_fn(candidate.row, image_width, image_height)
        if translate is None:
            return

        for member in candidate.row.get("member_boxes_page_xyxy") or []:
            if isinstance(member, list) and len(member) == 4:
                rect = QGraphicsRectItem(translate(tuple(float(value) for value in member)))
                rect.setPen(QPen(QColor(130, 130, 130), 3))
                self.scene_obj.addItem(rect)

        candidate_box = box_from_row(candidate.row, "bbox_page_xyxy")
        if candidate_box is not None:
            rect = QGraphicsRectItem(translate(candidate_box))
            rect.setPen(QPen(QColor(0, 190, 80), 5))
            self.scene_obj.addItem(rect)
            label = QGraphicsSimpleTextItem("current group")
            label.setBrush(QColor(0, 110, 50))
            label.setPos(rect.rect().x(), max(0.0, rect.rect().y() - 24))
            self.scene_obj.addItem(label)

        for proposal in candidate.proposals:
            if proposal.variant_index > 4:
                continue
            base_color = BOX_COLORS[(proposal.variant_index - 1) % len(BOX_COLORS)]
            for group_index, group in enumerate(proposal.groups, start=1):
                box = group.get("bbox_page_xyxy")
                if not isinstance(box, list) or len(box) != 4:
                    continue
                rect = QGraphicsRectItem(translate(tuple(float(value) for value in box)))
                rect.setPen(QPen(base_color, 3, Qt.DashLine))
                self.scene_obj.addItem(rect)
                label = QGraphicsSimpleTextItem(f"{proposal.variant_index}.{group_index}")
                label.setBrush(base_color)
                label.setPos(rect.rect().x(), max(0.0, rect.rect().y() - 20))
                self.scene_obj.addItem(label)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._fit_to_window and self.scene_obj.items():
            self.fitInView(self.scene_obj.sceneRect(), Qt.KeepAspectRatio)


class SplitReviewerWindow(QMainWindow):
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
        self.info.setMinimumWidth(260)
        self.info.setMaximumWidth(390)
        self.info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(260)
        self.list_widget.setMaximumWidth(390)
        self.list_widget.setTextElideMode(Qt.ElideMiddle)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setUniformItemSizes(True)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._build_toolbar()
        self._build_dock()
        self.setWindowTitle("CloudHammer Whole-Cloud Split Reviewer")
        self.resize(1500, 980)
        self.load_current()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Split Review")
        self.addToolBar(toolbar)
        actions = [
            ("Current OK", "G", lambda: self.mark("current_ok")),
            ("Use Split 1", "1", lambda: self.mark("split_variant_1")),
            ("Use Split 2", "2", lambda: self.mark("split_variant_2")),
            ("Use Split 3", "3", lambda: self.mark("split_variant_3")),
            ("Use Split 4", "4", lambda: self.mark("split_variant_4")),
            ("Still Over", "O", lambda: self.mark("still_overmerged")),
            ("False +", "F", lambda: self.mark("false_positive")),
            ("Partial", "P", lambda: self.mark("partial")),
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
        dock = QDockWidget("Split Candidate", self)
        dock.setMinimumWidth(270)
        dock.setMaximumWidth(430)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(self.info)
        layout.addWidget(self.list_widget)

        for row_defs in [
            [("G", "current_ok"), ("1", "split_variant_1"), ("2", "split_variant_2"), ("3", "split_variant_3")],
            [("4", "split_variant_4"), ("O", "still_overmerged"), ("F", "false_positive"), ("P", "partial"), ("U", "uncertain")],
        ]:
            button_row = QHBoxLayout()
            for label, status in row_defs:
                button = QPushButton(label)
                button.setToolTip(STATUS_LABELS[status])
                button.setMaximumWidth(68)
                button.clicked.connect(lambda checked=False, value=status: self.mark(value))
                button_row.addWidget(button)
            layout.addLayout(button_row)

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
        self.resizeDocks([dock], [320], Qt.Horizontal)

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
        logging.info("Loaded split candidate %s", candidate.candidate_id)

    def _refresh_info(self, candidate: Candidate) -> None:
        reviewed = len(self.latest_reviews)
        total = len(self.candidates)
        current_review = self.latest_reviews.get(candidate.candidate_id)
        status = "unreviewed" if current_review is None else str(current_review.get("status"))
        row = candidate.row
        proposal_lines = []
        for proposal in candidate.proposals:
            if proposal.variant_index > 4:
                continue
            color_name = BOX_COLOR_NAMES[(proposal.variant_index - 1) % len(BOX_COLOR_NAMES)]
            proposal_lines.append(
                f"{proposal.variant_index}: {color_name} dashed, {proposal.name} -> {proposal.group_count} groups"
            )
        lines = [
            f"Index: {self.index + 1} / {total}",
            f"Reviewed: {reviewed} / {total}",
            f"Status: {status}",
            "",
            f"ID: {compact_middle(candidate.candidate_id, 42)}",
            f"Confidence: {candidate.confidence:.3f}",
            f"Members: {candidate.member_count}",
            f"Fill: {candidate.fill_ratio:.3f}",
            f"Prior review: {row.get('review_status')}",
            f"Page: {compact_middle(str(row.get('pdf_stem')), 34)} p{row.get('page_number')}",
            "",
            "Splits:",
            *proposal_lines,
            "",
            "Green = current. Gray = members.",
            "Dashed colors are keyed by number.",
            "Press that number if its dashed boxes are best.",
            "Wheel zooms. Drag pans. 0 fits.",
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
                f"{candidate.index:03d} {status[:6]:6s} "
                f"n={candidate.member_count:02d} f={candidate.fill_ratio:.2f} "
                f"{compact_middle(candidate.candidate_id, 32)}"
            )
            item.setToolTip(candidate.candidate_id)
            self.list_widget.addItem(item)
        self.list_widget.setCurrentRow(self.index)

    def mark(self, status: str) -> None:
        if status not in STATUS_LABELS:
            return
        candidate = self.current()
        if status.startswith("split_variant_") and selected_proposal(candidate, status) is None:
            QMessageBox.information(self, "No Proposal", f"{STATUS_LABELS[status]} is not available for this candidate.")
            return
        record = review_record(candidate, status, self.manifest_path)
        append_review(self.review_log, record)
        self.latest_reviews[candidate.candidate_id] = record
        logging.info("Reviewed split candidate %s as %s", candidate.candidate_id, status)
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
        QMessageBox.information(self, "Review Complete", "All split candidates in this queue have a current review.")

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        key = event.key()
        if key in STATUS_KEYS:
            self.mark(STATUS_KEYS[key])
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
    parser = argparse.ArgumentParser(description="Review split proposals for overmerged whole-cloud candidates.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--review-log", type=Path, default=DEFAULT_REVIEW_LOG)
    parser.add_argument("--log-path", type=Path, default=None)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    review_log = args.review_log.resolve()
    log_path = (args.log_path or review_log.with_suffix(".log")).resolve()
    configure_logging(log_path)
    candidates = load_candidates(manifest_path)
    latest_reviews = load_latest_reviews(review_log)
    logging.info(
        "Starting split reviewer manifest=%s review_log=%s candidates=%s reviewed=%s",
        manifest_path,
        review_log,
        len(candidates),
        len(latest_reviews),
    )

    app = QApplication(sys.argv)
    window = SplitReviewerWindow(candidates, manifest_path, review_log, latest_reviews)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
