from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
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
        QGraphicsEllipseItem,
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
        QInputDialog,
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
MARKER_ORPHAN_REPAIR_FLAG = "marker_orphan_repair_needed"
MARKER_ORPHAN_DIRECT_MERGE_GAP = 30.0
MARKER_ORPHAN_AMBIGUOUS_MERGE_GAP = 45.0
DEFAULT_MANIFEST = (
    ROOT
    / "runs"
    / "whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428"
    / "release_v1"
    / "split_review_queue.jsonl"
)
DEFAULT_REVIEW_LOG = (
    ROOT
    / "data"
    / "whole_cloud_split_reviews"
    / "whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428.release_v1.split_review.jsonl"
)
DEFAULT_DELTA_MANIFEST = ROOT / "data" / "manifests" / "delta_manifest.jsonl"

STATUS_LABELS = {
    "current_ok": "Current OK",
    "manual_split": "Manual Split",
    "split_variant_1": "Use Split 1",
    "split_variant_2": "Use Split 2",
    "split_variant_3": "Use Split 3",
    "split_variant_4": "Use Split 4",
    "split_variant_5": "Use Split 5",
    "split_variant_6": "Use Split 6",
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
    Qt.Key_5: "split_variant_5",
    Qt.Key_6: "split_variant_6",
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
    (
        "micro_gap",
        GroupingParams(
            expansion_ratio=0.01,
            min_padding=2.0,
            max_padding=18.0,
            group_margin_ratio=0.03,
            min_group_margin=4.0,
            max_group_margin=40.0,
            split_min_members=2,
            split_min_partition_members=1,
            split_gap_ratio=0.025,
            split_min_gap=25.0,
            split_max_fill_ratio=0.90,
        ),
    ),
    (
        "no_expand",
        GroupingParams(
            expansion_ratio=0.0,
            min_padding=0.0,
            max_padding=0.0,
            group_margin_ratio=0.02,
            min_group_margin=2.0,
            max_group_margin=25.0,
            split_min_members=2,
            split_min_partition_members=1,
            split_gap_ratio=0.01,
            split_min_gap=8.0,
            split_max_fill_ratio=0.95,
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
MANUAL_GROUP_COLORS = [
    QColor(255, 128, 0),
    QColor(0, 170, 255),
    QColor(180, 80, 255),
    QColor(220, 190, 0),
    QColor(0, 190, 150),
    QColor(255, 70, 120),
]


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
        return resolve_cloudhammer_path(str(self.row["crop_image_path"]))

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


def pdf_stem_key(path_text: str) -> str:
    return Path(path_text).stem.casefold()


def infer_page_index(row: dict[str, Any]) -> int | None:
    value = row.get("page_index")
    if value is not None and value != "":
        return int(value)
    page_number = row.get("page_number")
    if page_number is None or page_number == "":
        return None
    return int(page_number) - 1


def infer_target_digit(row: dict[str, Any]) -> str | None:
    text = " ".join(str(row.get(key) or "") for key in ("pdf_path", "pdf_stem", "revision", "candidate_id"))
    match = re.search(r"Revision\s*#\s*(\d+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\bRev(?:ision)?\s*[_#-]?\s*(\d+)\b", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def load_delta_marker_index(path: Path = DEFAULT_DELTA_MANIFEST) -> dict[tuple[str, int], list[dict[str, Any]]]:
    index: dict[tuple[str, int], list[dict[str, Any]]] = {}
    if not path.exists():
        return index
    for row in read_jsonl(path):
        page_index = int(row.get("page_index") or 0)
        key = (pdf_stem_key(str(row.get("pdf_path") or "")), page_index)
        markers: list[dict[str, Any]] = []
        for marker in row.get("active_deltas") or []:
            center = marker.get("center") or {}
            triangle = marker.get("triangle") or {}
            if "x" not in center or "y" not in center:
                continue
            markers.append(
                {
                    "digit": None if marker.get("digit") is None else str(marker.get("digit")),
                    "center": {"x": float(center["x"]), "y": float(center["y"])},
                    "triangle": triangle,
                    "score": float(marker.get("score") or 0.0),
                    "side_support": float(marker.get("side_support") or 0.0),
                    "base_support": float(marker.get("base_support") or 0.0),
                    "geometry_score": float(marker.get("geometry_score") or 0.0),
                }
            )
        index.setdefault(key, []).extend(markers)
    return index


def attach_marker_context(row: dict[str, Any], marker_index: dict[tuple[str, int], list[dict[str, Any]]]) -> dict[str, Any]:
    updated = dict(row)
    page_index = infer_page_index(row)
    markers: list[dict[str, Any]] = []
    if page_index is not None:
        markers = marker_index.get((pdf_stem_key(str(row.get("pdf_path") or row.get("pdf_stem") or "")), page_index), [])
        if not markers and row.get("pdf_stem"):
            markers = marker_index.get((pdf_stem_key(str(row.get("pdf_stem"))), page_index), [])
    target_digit = infer_target_digit(row)
    updated["revision_marker_context"] = {
        "target_digit": target_digit,
        "page_marker_count": len(markers),
        "matching_page_marker_count": len([m for m in markers if target_digit is None or m.get("digit") == target_digit]),
        "markers": markers,
    }
    return updated


def distance_point_to_box(point: dict[str, float], box: list[float] | tuple[float, float, float, float]) -> float:
    x = float(point["x"])
    y = float(point["y"])
    x1, y1, x2, y2 = [float(value) for value in box]
    dx = max(x1 - x, 0.0, x - x2)
    dy = max(y1 - y, 0.0, y - y2)
    return math.hypot(dx, dy)


def markers_for_candidate(candidate: Candidate, matching_only: bool = True) -> list[dict[str, Any]]:
    context = candidate.row.get("revision_marker_context") or {}
    markers = list(context.get("markers") or [])
    target_digit = context.get("target_digit")
    if matching_only and target_digit is not None:
        markers = [marker for marker in markers if marker.get("digit") == target_digit]
    return markers


def nearest_marker_distance_to_box(
    markers: list[dict[str, Any]],
    box: list[float] | tuple[float, float, float, float] | None,
) -> float | None:
    if not markers or box is None:
        return None
    return min(distance_point_to_box(marker["center"], box) for marker in markers)


def markers_near_box(
    markers: list[dict[str, Any]],
    box: list[float] | tuple[float, float, float, float] | None,
    margin: float,
) -> list[dict[str, Any]]:
    if box is None:
        return []
    x1, y1, x2, y2 = [float(value) for value in box]
    return [
        marker
        for marker in markers
        if x1 - margin <= float(marker["center"]["x"]) <= x2 + margin
        and y1 - margin <= float(marker["center"]["y"]) <= y2 + margin
    ]


def matching_crop_markers_for_candidate(candidate: Candidate) -> list[dict[str, Any]]:
    crop_box = box_from_row(candidate.row, "crop_box_page_xyxy")
    return markers_near_box(markers_for_candidate(candidate, matching_only=True), crop_box, 0.0)


def box_distance(
    left: list[float] | tuple[float, float, float, float],
    right: list[float] | tuple[float, float, float, float],
) -> float:
    lx1, ly1, lx2, ly2 = [float(value) for value in left]
    rx1, ry1, rx2, ry2 = [float(value) for value in right]
    dx = max(rx1 - lx2, lx1 - rx2, 0.0)
    dy = max(ry1 - ly2, ly1 - ry2, 0.0)
    return math.hypot(dx, dy)


def group_box(group: dict[str, Any]) -> tuple[float, float, float, float] | None:
    values = group.get("bbox_page_xyxy")
    if not isinstance(values, list) or len(values) != 4:
        return None
    return tuple(float(value) for value in values)


def marker_box(marker: dict[str, Any]) -> tuple[float, float, float, float]:
    points: list[dict[str, Any]] = []
    triangle = marker.get("triangle") or {}
    for key in ("apex", "left_base", "right_base"):
        point = triangle.get(key)
        if isinstance(point, dict) and "x" in point and "y" in point:
            points.append(point)
    if not points:
        center = marker["center"]
        x = float(center["x"])
        y = float(center["y"])
        return (x, y, x, y)
    xs = [float(point["x"]) for point in points]
    ys = [float(point["y"]) for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def analyze_proposal_marker_consistency(
    proposal: SplitProposal,
    markers: list[dict[str, Any]],
) -> dict[str, Any]:
    boxes = [group_box(group) for group in proposal.groups]
    marker_boxes = [marker_box(marker) for marker in markers]
    marker_owners: list[int | None] = []
    marker_support_distances_by_group: dict[int, float] = {}
    for marker_index, marker in enumerate(markers):
        owner = None
        owner_distance = None
        owner_area = None
        for index, box in enumerate(boxes, start=1):
            if box is None:
                continue
            marker_distance = box_distance(box, marker_boxes[marker_index])
            # Touching/overlapping the triangle outline is support. We also
            # allow a small slack because marker boxes and detector boxes are
            # both imperfect page-space proxies.
            if marker_distance <= 40.0:
                area = area_xyxy(box)
                if (
                    owner_distance is None
                    or marker_distance < owner_distance
                    or (marker_distance == owner_distance and (owner_area is None or area < owner_area))
                ):
                    owner = index
                    owner_distance = marker_distance
                    owner_area = area
        if owner is not None and owner_distance is not None:
            current = marker_support_distances_by_group.get(owner)
            if current is None or owner_distance < current:
                marker_support_distances_by_group[owner] = owner_distance
        marker_owners.append(owner)

    owned_groups: set[int] = {owner for owner in marker_owners if owner is not None}
    orphan_groups: list[dict[str, Any]] = []
    merge_suspects: list[dict[str, Any]] = []
    ambiguous_merge_suspects: list[dict[str, Any]] = []
    drop_suspects: list[dict[str, Any]] = []
    marked_boxes = [(index, box) for index, box in enumerate(boxes, start=1) if box is not None and index in owned_groups]
    marker_centers = [
        (float(marker["center"]["x"]), float(marker["center"]["y"]))
        for marker in markers
    ]
    marker_centers_by_owner: dict[int, list[tuple[float, float]]] = {}
    for marker_index, owner in enumerate(marker_owners):
        if owner is None:
            continue
        marker_centers_by_owner.setdefault(owner, []).append(marker_centers[marker_index])

    for index, box in enumerate(boxes, start=1):
        if box is None or index in owned_groups:
            continue
        orphan_center = box_center(box)
        nearest_marker_index = None
        nearest_marker_distance = None
        nearest_marker_center_distance = None
        for marker_index, marker_bbox in enumerate(marker_boxes):
            distance = box_distance(box, marker_bbox)
            if nearest_marker_distance is None or distance < nearest_marker_distance:
                nearest_marker_index = marker_index
                nearest_marker_distance = distance
            center_distance = point_distance(orphan_center, marker_centers[marker_index])
            if nearest_marker_center_distance is None or center_distance < nearest_marker_center_distance:
                nearest_marker_center_distance = center_distance
        nearest_sibling_index = None
        nearest_sibling_gap = None
        for sibling_index, sibling_box in marked_boxes:
            gap = box_distance(box, sibling_box)
            if nearest_sibling_gap is None or gap < nearest_sibling_gap:
                nearest_sibling_index = sibling_index
                nearest_sibling_gap = gap
        width = box[2] - box[0]
        height = box[3] - box[1]
        local_threshold = max(160.0, min(500.0, max(width, height) * 0.25))
        marker_center_threshold = max(750.0, min(1600.0, max(width, height) * 0.9))
        marker_owner = marker_owners[nearest_marker_index] if nearest_marker_index is not None else None
        plausible_merge_targets: list[dict[str, Any]] = []
        for sibling_index, sibling_box in marked_boxes:
            gap = box_distance(box, sibling_box)
            if gap > MARKER_ORPHAN_AMBIGUOUS_MERGE_GAP:
                continue
            sibling_marker_center_distance = None
            for marker_center in marker_centers_by_owner.get(sibling_index, []):
                distance = point_distance(orphan_center, marker_center)
                if sibling_marker_center_distance is None or distance < sibling_marker_center_distance:
                    sibling_marker_center_distance = distance
            reason = None
            if sibling_marker_center_distance is not None and sibling_marker_center_distance <= marker_center_threshold:
                reason = "near_sibling_marker_center"
            elif (
                gap <= MARKER_ORPHAN_DIRECT_MERGE_GAP
                and nearest_marker_center_distance is not None
                and nearest_marker_center_distance <= marker_center_threshold
            ):
                reason = "tight_neighbor_near_marker_context"
            if reason is None:
                continue
            plausible_merge_targets.append(
                {
                    "group_index": sibling_index,
                    "gap": gap,
                    "owned_marker_center_distance": sibling_marker_center_distance,
                    "reason": reason,
                }
            )
        orphan = {
            "group_index": index,
            "nearest_marker_distance": nearest_marker_distance,
            "nearest_marker_center_distance": nearest_marker_center_distance,
            "nearest_marker_owner_group": marker_owner,
            "nearest_marked_sibling_group": nearest_sibling_index,
            "nearest_marked_sibling_gap": nearest_sibling_gap,
            "local_neighbor_threshold": local_threshold,
            "marker_center_threshold": marker_center_threshold,
            "direct_merge_gap_threshold": MARKER_ORPHAN_DIRECT_MERGE_GAP,
            "ambiguous_merge_gap_threshold": MARKER_ORPHAN_AMBIGUOUS_MERGE_GAP,
            "plausible_merge_targets": plausible_merge_targets,
        }
        orphan_groups.append(orphan)
        direct_merge_targets = [
            target
            for target in plausible_merge_targets
            if float(target["gap"]) <= MARKER_ORPHAN_DIRECT_MERGE_GAP
        ]
        if len(plausible_merge_targets) == 1 and len(direct_merge_targets) == 1:
            orphan["repair_hint"] = "merge"
            orphan["merge_target_group"] = plausible_merge_targets[0]["group_index"]
            merge_suspects.append(orphan)
        elif plausible_merge_targets:
            orphan["repair_hint"] = "merge_ambiguous"
            ambiguous_merge_suspects.append(orphan)
        else:
            orphan["repair_hint"] = "drop"
            orphan["drop_reason"] = "no_marked_sibling" if nearest_sibling_index is None else "marked_sibling_too_far"
            drop_suspects.append(orphan)

    return {
        "proposal_index": proposal.variant_index,
        "proposal_name": proposal.name,
        "group_count": proposal.group_count,
        "marker_count": len(markers),
        "owned_group_count": len(owned_groups),
        "owned_groups": sorted(owned_groups),
        "marker_support_distances_by_group": marker_support_distances_by_group,
        "orphan_group_count": len(orphan_groups),
        "orphan_groups": orphan_groups,
        "merge_suspect_count": len(merge_suspects),
        "merge_suspects": merge_suspects,
        "ambiguous_merge_suspect_count": len(ambiguous_merge_suspects),
        "ambiguous_merge_suspects": ambiguous_merge_suspects,
        "drop_suspect_count": len(drop_suspects),
        "drop_suspects": drop_suspects,
        "repair_suspect_count": len(merge_suspects) + len(ambiguous_merge_suspects) + len(drop_suspects),
    }


def format_marker_consistency(analysis: dict[str, Any]) -> str:
    proposal_index = analysis["proposal_index"]
    proposal_name = analysis["proposal_name"]
    group_count = analysis["group_count"]
    owned = analysis["owned_group_count"]
    orphans = analysis["orphan_group_count"]
    merge_count = analysis["merge_suspect_count"]
    ambiguous_count = analysis.get("ambiguous_merge_suspect_count", 0)
    drop_count = analysis.get("drop_suspect_count", 0)
    if analysis["marker_count"] == 0:
        return f"Auto {proposal_index} {proposal_name}: no marker signal"
    if orphans == 0:
        return f"Auto {proposal_index} {proposal_name}: clean, {owned}/{group_count} boxes touch markers"
    if merge_count or ambiguous_count or drop_count:
        hints = []
        for suspect in analysis["merge_suspects"][:3]:
            group_index = suspect["group_index"]
            sibling_index = suspect.get("merge_target_group") or suspect["nearest_marked_sibling_group"]
            marker_distance = compact_distance(suspect["nearest_marker_distance"])
            sibling_gap = compact_distance(suspect["nearest_marked_sibling_gap"])
            hints.append(f"merge Box {group_index}->Box {sibling_index} marker gap {marker_distance}, box gap {sibling_gap}")
        remaining_hint_slots = max(0, 3 - len(hints))
        for suspect in analysis.get("ambiguous_merge_suspects", [])[:remaining_hint_slots]:
            group_index = suspect["group_index"]
            target_groups = ",".join(str(target["group_index"]) for target in suspect.get("plausible_merge_targets", []))
            marker_distance = compact_distance(suspect.get("nearest_marker_center_distance"))
            hints.append(f"ambiguous Box {group_index}->[{target_groups}] marker center {marker_distance}")
        remaining_hint_slots = max(0, 3 - len(hints))
        for suspect in analysis.get("drop_suspects", [])[:remaining_hint_slots]:
            group_index = suspect["group_index"]
            marker_distance = compact_distance(suspect.get("nearest_marker_center_distance"))
            sibling_gap = compact_distance(suspect["nearest_marked_sibling_gap"])
            hints.append(f"drop Box {group_index} marker center {marker_distance}, sibling gap {sibling_gap}")
        suffix = "; ".join(hints)
        if merge_count + ambiguous_count + drop_count > len(hints):
            suffix += "; ..."
        return (
            f"Auto {proposal_index} {proposal_name}: REPAIR? "
            f"{merge_count} merge, {ambiguous_count} ambiguous, {drop_count} drop orphan(s), "
            f"{owned}/{group_count} touch markers. {suffix}"
        )
    return f"Auto {proposal_index} {proposal_name}: {orphans} orphan box(es), {owned}/{group_count} touch markers"


def marker_analysis_for_status(candidate: Candidate, status: str) -> dict[str, Any] | None:
    proposal = selected_proposal(candidate, status)
    if proposal is None:
        return None
    return analyze_proposal_marker_consistency(proposal, matching_crop_markers_for_candidate(candidate))


def parse_repair_override_text(text: str) -> list[dict[str, int]]:
    overrides: list[dict[str, int]] = []
    if not text.strip():
        return overrides
    for raw_part in re.split(r"[,;\n]+", text):
        part = raw_part.strip()
        if not part:
            continue
        match = re.fullmatch(
            r"(?:box\s*)?(?:(\d+)\.)?(\d+)\s*(?:->|=>|to)\s*(?:box\s*)?(?:(\d+)\.)?(\d+)",
            part,
            re.IGNORECASE,
        )
        if match is None:
            raise ValueError(f"Could not parse repair target: {part!r}. Use forms like 4.5->4.6 or 5->6.")
        orphan_group = int(match.group(2))
        target_group = int(match.group(4))
        overrides.append({"orphan_group": orphan_group, "target_group": target_group})
    return overrides


def apply_repair_overrides(
    marker_consistency: dict[str, Any],
    overrides: list[dict[str, int]],
) -> dict[str, Any]:
    if not overrides:
        return marker_consistency
    updated = dict(marker_consistency)
    updated["manual_repair_overrides"] = overrides
    override_targets = {override["orphan_group"]: override["target_group"] for override in overrides}
    resolved: list[dict[str, Any]] = []
    remaining_ambiguous: list[dict[str, Any]] = []
    for suspect in marker_consistency.get("ambiguous_merge_suspects", []):
        group_index = int(suspect.get("group_index"))
        target_group = override_targets.get(group_index)
        if target_group is None:
            remaining_ambiguous.append(suspect)
            continue
        resolved_suspect = dict(suspect)
        resolved_suspect["repair_hint"] = "merge_manual_target"
        resolved_suspect["merge_target_group"] = target_group
        resolved.append(resolved_suspect)
    updated["resolved_ambiguous_merge_suspects"] = resolved
    updated["ambiguous_merge_suspects"] = remaining_ambiguous
    updated["ambiguous_merge_suspect_count"] = len(remaining_ambiguous)
    updated["manual_resolved_merge_suspect_count"] = len(resolved)
    updated["repair_suspect_count"] = (
        int(updated.get("merge_suspect_count") or 0)
        + int(updated.get("ambiguous_merge_suspect_count") or 0)
        + int(updated.get("drop_suspect_count") or 0)
        + int(updated.get("manual_resolved_merge_suspect_count") or 0)
    )
    return updated


def compact_distance(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.0f}px"


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
    marker_index = load_delta_marker_index()
    rows = [attach_marker_context(row, marker_index) for row in read_jsonl(manifest_path)]
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


def area_xyxy(box: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def box_center(box: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def point_distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def union_xyxy(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def manual_split_proposal(candidate: Candidate, assignments: dict[int, int]) -> dict[str, Any] | None:
    member_boxes = candidate.row.get("member_boxes_page_xyxy") or []
    member_confidences = candidate.row.get("member_confidences") or []
    groups_by_number: dict[int, list[int]] = {}
    for member_index, group_number in assignments.items():
        if group_number <= 0 or member_index < 0 or member_index >= len(member_boxes):
            continue
        box = member_boxes[member_index]
        if isinstance(box, list) and len(box) == 4:
            groups_by_number.setdefault(group_number, []).append(member_index)
    if len(groups_by_number) < 2:
        return None

    groups: list[dict[str, Any]] = []
    for group_number, indexes in sorted(groups_by_number.items()):
        boxes = [tuple(float(value) for value in member_boxes[index]) for index in indexes]
        group_box = union_xyxy(boxes)
        confidences = [
            float(member_confidences[index])
            if index < len(member_confidences)
            else float(candidate.row.get("whole_cloud_confidence") or candidate.row.get("confidence") or 0.0)
            for index in indexes
        ]
        member_area = sum(area_xyxy(box) for box in boxes)
        group_area = area_xyxy(group_box)
        groups.append(
            {
                "bbox_page_xyxy": [round(value, 3) for value in group_box],
                "bbox_page_xywh": xyxy_to_xywh(group_box),
                "confidence": max(confidences) if confidences else candidate.confidence,
                "member_count": len(indexes),
                "member_indexes": [index + 1 for index in indexes],
                "fill_ratio": 0.0 if group_area <= 0 else member_area / group_area,
                "manual_group_number": group_number,
            }
        )
    return {
        "variant_index": "manual",
        "name": "manual_fragment_groups",
        "group_count": len(groups),
        "groups": groups,
    }


def review_record(
    candidate: Candidate,
    status: str,
    manifest_path: Path,
    manual_assignments: dict[int, int] | None = None,
    review_flags: list[str] | None = None,
    status_detail: str | None = None,
    marker_consistency: dict[str, Any] | None = None,
    repair_overrides: list[dict[str, int]] | None = None,
) -> dict[str, Any]:
    row = candidate.row
    proposal = manual_split_proposal(candidate, manual_assignments or {}) if status == "manual_split" else selected_proposal(candidate, status)
    if isinstance(proposal, SplitProposal):
        proposal_record = {
            "variant_index": proposal.variant_index,
            "name": proposal.name,
            "group_count": proposal.group_count,
            "groups": proposal.groups,
        }
    else:
        proposal_record = proposal
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
        "size_bucket": row.get("size_bucket"),
        "member_count": row.get("member_count"),
        "group_fill_ratio": row.get("group_fill_ratio"),
        "bbox_page_xyxy": row.get("bbox_page_xyxy"),
        "crop_box_page_xyxy": row.get("crop_box_page_xyxy"),
        "proposal": proposal_record,
        "proposal_summaries": [
            {"variant_index": proposal.variant_index, "name": proposal.name, "group_count": proposal.group_count}
            for proposal in candidate.proposals
        ],
    }
    if review_flags:
        record["review_flags"] = review_flags
    if status_detail:
        record["status_detail"] = status_detail
    if marker_consistency is not None:
        record["marker_consistency"] = marker_consistency
    if repair_overrides:
        record["repair_overrides"] = repair_overrides
    return record


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
        self.candidate: Candidate | None = None
        self.manual_mode = False
        self.active_manual_group = 1
        self.manual_assignments: dict[int, int] = {}
        self.member_items: dict[int, QGraphicsRectItem] = {}
        self.member_areas: dict[int, float] = {}
        self.proposal_visibility: dict[int, bool] = {index: True for index in range(1, 7)}
        self.proposal_items: dict[int, list[Any]] = {}
        self.marker_visible = True
        self.marker_items: list[Any] = []
        self.on_manual_changed = None

    def load_candidate(self, candidate: Candidate, manual_assignments: dict[int, int] | None = None) -> None:
        self.candidate = candidate
        self.manual_assignments = dict(manual_assignments or {})
        self.member_items = {}
        self.member_areas = {}
        self.proposal_items = {}
        self.marker_items = []
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

    def set_manual_mode(self, enabled: bool) -> None:
        self.manual_mode = enabled
        self.setDragMode(QGraphicsView.NoDrag if enabled else QGraphicsView.ScrollHandDrag)
        self._refresh_member_pens()

    def set_active_manual_group(self, group_number: int) -> None:
        self.active_manual_group = max(1, min(len(MANUAL_GROUP_COLORS), group_number))
        self._refresh_member_pens()
        if self.on_manual_changed is not None:
            self.on_manual_changed()

    def set_proposal_visible(self, proposal_index: int, visible: bool) -> None:
        self.proposal_visibility[proposal_index] = visible
        for item in self.proposal_items.get(proposal_index, []):
            item.setVisible(visible)

    def set_all_proposals_visible(self, visible: bool) -> None:
        for proposal_index in range(1, 7):
            self.set_proposal_visible(proposal_index, visible)

    def set_markers_visible(self, visible: bool) -> None:
        self.marker_visible = visible
        for item in self.marker_items:
            item.setVisible(visible)

    def clear_manual_assignments(self) -> None:
        self.manual_assignments.clear()
        self._refresh_member_pens()
        if self.on_manual_changed is not None:
            self.on_manual_changed()

    def manual_group_counts(self) -> dict[int, int]:
        counts: dict[int, int] = {}
        for group_number in self.manual_assignments.values():
            counts[group_number] = counts.get(group_number, 0) + 1
        return dict(sorted(counts.items()))

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

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if not self.manual_mode:
            super().mousePressEvent(event)
            return
        scene_pos = self.mapToScene(event.pos())
        member_indexes = self._member_indexes_at(scene_pos)
        if not member_indexes:
            return
        reverse = bool(event.modifiers() & Qt.ShiftModifier)
        member_index = self._pick_member_index(member_indexes, reverse=reverse)
        if member_index is None:
            return
        if event.button() == Qt.RightButton:
            self.manual_assignments.pop(member_index, None)
        else:
            self.manual_assignments[member_index] = self.active_manual_group
        self._refresh_member_pens()
        if self.on_manual_changed is not None:
            self.on_manual_changed()
        event.accept()

    def _member_indexes_at(self, scene_pos) -> list[int]:
        indexes: list[int] = []
        for item in self.scene_obj.items(scene_pos):
            value = item.data(0)
            if value is not None:
                try:
                    indexes.append(int(value))
                except (TypeError, ValueError):
                    continue
        return list(dict.fromkeys(indexes))

    def _pick_member_index(self, member_indexes: list[int], reverse: bool = False) -> int | None:
        ordered = sorted(
            member_indexes,
            key=lambda index: self.member_areas.get(index, 0.0),
            reverse=reverse,
        )
        for member_index in ordered:
            if member_index not in self.manual_assignments:
                return member_index
        for member_index in ordered:
            if self.manual_assignments.get(member_index) != self.active_manual_group:
                return member_index
        return ordered[0] if ordered else None

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

    def _translate_point_fn(self, row: dict[str, Any], image_width: int, image_height: int):
        crop_box = box_from_row(row, "crop_box_page_xyxy")
        if crop_box is None:
            return None
        crop_x1, crop_y1, crop_x2, crop_y2 = crop_box
        crop_width = max(1.0, crop_x2 - crop_x1)
        crop_height = max(1.0, crop_y2 - crop_y1)

        def translate_point(point: dict[str, Any]) -> tuple[float, float]:
            sx = image_width / crop_width
            sy = image_height / crop_height
            return ((float(point["x"]) - crop_x1) * sx, (float(point["y"]) - crop_y1) * sy)

        return translate_point

    def _draw_boxes(self, candidate: Candidate, image_width: int, image_height: int) -> None:
        translate = self._translate_fn(candidate.row, image_width, image_height)
        if translate is None:
            return

        for member in candidate.row.get("member_boxes_page_xyxy") or []:
            member_index = len(self.member_items)
            if isinstance(member, list) and len(member) == 4:
                member_box = tuple(float(value) for value in member)
                rect = QGraphicsRectItem(translate(member_box))
                rect.setData(0, member_index)
                rect.setPen(self._member_pen(member_index))
                self.scene_obj.addItem(rect)
                self.member_items[member_index] = rect
                self.member_areas[member_index] = area_xyxy(member_box)
                assigned_group = self.manual_assignments.get(member_index)
                if assigned_group:
                    label = QGraphicsSimpleTextItem(str(assigned_group))
                    label.setBrush(MANUAL_GROUP_COLORS[(assigned_group - 1) % len(MANUAL_GROUP_COLORS)])
                    label.setPos(rect.rect().x(), rect.rect().y())
                    self.scene_obj.addItem(label)

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
            if proposal.variant_index > 6:
                continue
            base_color = BOX_COLORS[(proposal.variant_index - 1) % len(BOX_COLORS)]
            for group_index, group in enumerate(proposal.groups, start=1):
                box = group.get("bbox_page_xyxy")
                if not isinstance(box, list) or len(box) != 4:
                    continue
                rect = QGraphicsRectItem(translate(tuple(float(value) for value in box)))
                rect.setPen(QPen(base_color, 3, Qt.DashLine))
                self.scene_obj.addItem(rect)
                label_text = f"{proposal.variant_index}.{group_index}"
                label = QGraphicsSimpleTextItem(label_text)
                label.setBrush(base_color)
                label_x = rect.rect().x()
                label_y = max(0.0, rect.rect().y() - 20)
                label.setPos(label_x + 3, label_y + 2)
                backing = QGraphicsRectItem(label_x, label_y, 42, 20)
                backing.setBrush(QColor(255, 255, 255, 220))
                backing.setPen(QPen(base_color, 2))
                self.scene_obj.addItem(backing)
                self.scene_obj.addItem(label)
                visible = self.proposal_visibility.get(proposal.variant_index, True)
                rect.setVisible(visible)
                backing.setVisible(visible)
                label.setVisible(visible)
                self.proposal_items.setdefault(proposal.variant_index, []).extend([rect, backing, label])

        self._draw_markers(candidate, image_width, image_height)

    def _draw_markers(self, candidate: Candidate, image_width: int, image_height: int) -> None:
        translate_point = self._translate_point_fn(candidate.row, image_width, image_height)
        if translate_point is None:
            return
        context = candidate.row.get("revision_marker_context") or {}
        target_digit = context.get("target_digit")
        markers = context.get("markers") or []
        crop_box = box_from_row(candidate.row, "crop_box_page_xyxy")
        if crop_box is None:
            return
        x1, y1, x2, y2 = crop_box
        margin = max(250.0, max(x2 - x1, y2 - y1) * 0.08)
        visible_marker_index = 0
        for marker in markers:
            center = marker.get("center") or {}
            if "x" not in center or "y" not in center:
                continue
            cx = float(center["x"])
            cy = float(center["y"])
            if cx < x1 - margin or cx > x2 + margin or cy < y1 - margin or cy > y2 + margin:
                continue
            visible_marker_index += 1
            digit = marker.get("digit")
            color = QColor(0, 150, 255) if target_digit is None or digit == target_digit else QColor(170, 170, 170)
            pen = QPen(color, 5 if target_digit is None or digit == target_digit else 3, Qt.SolidLine)
            sx, sy = translate_point(center)
            dot = QGraphicsEllipseItem(sx - 7, sy - 7, 14, 14)
            dot.setPen(QPen(color, 4))
            dot.setVisible(self.marker_visible)
            self.scene_obj.addItem(dot)
            self.marker_items.append(dot)
            h_line = self.scene_obj.addLine(sx - 14, sy, sx + 14, sy, QPen(color, 3))
            v_line = self.scene_obj.addLine(sx, sy - 14, sx, sy + 14, QPen(color, 3))
            h_line.setVisible(self.marker_visible)
            v_line.setVisible(self.marker_visible)
            self.marker_items.extend([h_line, v_line])
            points = []
            triangle = marker.get("triangle") or {}
            for key in ("apex", "left_base", "right_base"):
                point = triangle.get(key)
                if isinstance(point, dict) and "x" in point and "y" in point:
                    points.append(translate_point(point))
            if len(points) == 3:
                for start, end in ((0, 1), (1, 2), (2, 0)):
                    line = self.scene_obj.addLine(points[start][0], points[start][1], points[end][0], points[end][1], pen)
                    line.setVisible(self.marker_visible)
                    self.marker_items.append(line)
            label = QGraphicsSimpleTextItem(f"M{visible_marker_index} rev {digit or '?'}")
            label.setBrush(color)
            label.setPos(sx + 8, sy + 8)
            label.setVisible(self.marker_visible)
            self.scene_obj.addItem(label)
            self.marker_items.append(label)

    def _member_pen(self, member_index: int) -> QPen:
        group_number = self.manual_assignments.get(member_index)
        if not group_number:
            return QPen(QColor(130, 130, 130), 4 if self.manual_mode else 3)
        color = MANUAL_GROUP_COLORS[(group_number - 1) % len(MANUAL_GROUP_COLORS)]
        if group_number == self.active_manual_group:
            return QPen(color, 8)
        return QPen(QColor(color.red(), color.green(), color.blue(), 115), 3, Qt.DotLine)

    def _refresh_member_pens(self) -> None:
        for member_index, item in self.member_items.items():
            item.setPen(self._member_pen(member_index))

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
        self.manual_assignments_by_id: dict[str, dict[int, int]] = {}
        self.group_buttons: list[QPushButton] = []
        self.proposal_buttons: list[QPushButton] = []
        self.split_actions: list[QAction] = []
        self.repair_actions: list[QAction] = []

        self.view = CandidateView()
        self.view.on_manual_changed = self._manual_changed
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
            ("Use Split 5", "5", lambda: self.mark("split_variant_5")),
            ("Use Split 6", "6", lambda: self.mark("split_variant_6")),
            ("Repair 1", "Ctrl+1", lambda: self.mark_best_with_marker_repair("split_variant_1")),
            ("Repair 2", "Ctrl+2", lambda: self.mark_best_with_marker_repair("split_variant_2")),
            ("Repair 3", "Ctrl+3", lambda: self.mark_best_with_marker_repair("split_variant_3")),
            ("Repair 4", "Ctrl+4", lambda: self.mark_best_with_marker_repair("split_variant_4")),
            ("Repair 5", "Ctrl+5", lambda: self.mark_best_with_marker_repair("split_variant_5")),
            ("Repair 6", "Ctrl+6", lambda: self.mark_best_with_marker_repair("split_variant_6")),
            ("Manual", "M", self.toggle_manual_mode),
            ("Save Manual", "Ctrl+S", self.save_manual_split),
            ("Clear Manual", "C", self.clear_manual_split),
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
            if shortcut in {"1", "2", "3", "4", "5", "6"}:
                self.split_actions.append(action)
            if shortcut in {"Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4", "Ctrl+5", "Ctrl+6"}:
                self.repair_actions.append(action)

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
            [("4", "split_variant_4"), ("5", "split_variant_5"), ("6", "split_variant_6"), ("O", "still_overmerged")],
            [("F", "false_positive"), ("P", "partial"), ("U", "uncertain")],
        ]:
            button_row = QHBoxLayout()
            for label, status in row_defs:
                button = QPushButton(label)
                button.setToolTip(STATUS_LABELS[status])
                button.setMaximumWidth(68)
                button.clicked.connect(lambda checked=False, value=status: self.mark(value))
                button_row.addWidget(button)
            layout.addLayout(button_row)

        repair_hint_label = QLabel("Repair+number records the selected auto split with marker-orphan repair needed.")
        repair_hint_label.setWordWrap(True)
        layout.addWidget(repair_hint_label)

        for row_defs in [
            [(1, "R+1"), (2, "R+2"), (3, "R+3")],
            [(4, "R+4"), (5, "R+5"), (6, "R+6")],
        ]:
            button_row = QHBoxLayout()
            for variant_index, label in row_defs:
                status = f"split_variant_{variant_index}"
                button = QPushButton(label)
                button.setToolTip(
                    f"Ctrl+{variant_index}: {STATUS_LABELS[status]}, but flag marker-orphan repair needed"
                )
                button.clicked.connect(lambda checked=False, value=status: self.mark_best_with_marker_repair(value))
                button_row.addWidget(button)
            layout.addLayout(button_row)

        proposal_row = QHBoxLayout()
        for proposal_index, color_name in enumerate(BOX_COLOR_NAMES, start=1):
            proposal_button = QPushButton(f"Auto {proposal_index}")
            proposal_button.setCheckable(True)
            proposal_button.setChecked(True)
            proposal_button.setToolTip(f"Show/hide auto split {proposal_index}: {color_name}")
            proposal_button.clicked.connect(lambda checked=False, value=proposal_index: self.toggle_proposal_visibility(value, checked))
            proposal_row.addWidget(proposal_button)
            self.proposal_buttons.append(proposal_button)
        layout.addLayout(proposal_row)

        proposal_all_row = QHBoxLayout()
        hide_auto_button = QPushButton("Hide Auto")
        hide_auto_button.clicked.connect(lambda checked=False: self.set_all_proposals_visible(False))
        show_auto_button = QPushButton("Show Auto")
        show_auto_button.clicked.connect(lambda checked=False: self.set_all_proposals_visible(True))
        self.marker_button = QPushButton("Markers")
        self.marker_button.setCheckable(True)
        self.marker_button.setChecked(True)
        self.marker_button.clicked.connect(self.toggle_markers)
        proposal_all_row.addWidget(hide_auto_button)
        proposal_all_row.addWidget(show_auto_button)
        proposal_all_row.addWidget(self.marker_button)
        layout.addLayout(proposal_all_row)
        self._refresh_proposal_buttons()

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

        manual_row = QHBoxLayout()
        manual_button = QPushButton("Manual")
        manual_button.setToolTip("M: toggle manual grouping mode")
        manual_button.clicked.connect(self.toggle_manual_mode)
        save_manual_button = QPushButton("Save")
        save_manual_button.setToolTip("Ctrl+S: save manual fragment groups")
        save_manual_button.clicked.connect(self.save_manual_split)
        clear_manual_button = QPushButton("Clear")
        clear_manual_button.setToolTip("C: clear manual fragment groups for this candidate")
        clear_manual_button.clicked.connect(self.clear_manual_split)
        manual_row.addWidget(manual_button)
        manual_row.addWidget(save_manual_button)
        manual_row.addWidget(clear_manual_button)
        layout.addLayout(manual_row)

        group_row = QHBoxLayout()
        for group_number, color_name in enumerate(BOX_COLOR_NAMES, start=1):
            group_button = QPushButton(f"G{group_number}")
            group_button.setToolTip(f"Manual group {group_number}: {color_name}")
            group_button.setCheckable(True)
            group_button.setMinimumWidth(54)
            group_button.clicked.connect(lambda checked=False, value=group_number: self.set_manual_group(value))
            group_row.addWidget(group_button)
            self.group_buttons.append(group_button)
        layout.addLayout(group_row)
        self._refresh_manual_group_buttons()

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
        assignments = self.manual_assignments_by_id.get(candidate.candidate_id, {})
        self.view.load_candidate(candidate, assignments)
        self._refresh_info(candidate)
        self._refresh_proposal_buttons()
        logging.info("Loaded split candidate %s", candidate.candidate_id)

    def _refresh_info(self, candidate: Candidate) -> None:
        reviewed = len(self.latest_reviews)
        total = len(self.candidates)
        current_review = self.latest_reviews.get(candidate.candidate_id)
        status = "unreviewed" if current_review is None else str(current_review.get("status"))
        row = candidate.row
        proposal_lines = []
        marker_lines = self._marker_summary_lines(candidate)
        for proposal in candidate.proposals:
            if proposal.variant_index > 6:
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
            "Markers:",
            *marker_lines,
            "",
            "Green = current. Gray = members.",
            "Dashed colors are keyed by number.",
            "Auto buttons show/hide each dashed proposal overlay.",
            "Press that number if its dashed boxes are best.",
            "Use R+number or Ctrl+number when the auto split is best but marker-orphan repair is needed.",
            "M toggles manual mode. In manual mode, click gray fragments to assign the active group; right-click clears one.",
            f"Active manual group: G{self.view.active_manual_group} ({BOX_COLOR_NAMES[self.view.active_manual_group - 1]}).",
            "Regular click prefers the smallest overlapping member; Shift+click prefers the largest.",
            "Ctrl+S saves manual groups. C clears manual groups.",
            f"Manual: {'on' if self.view.manual_mode else 'off'} {self.view.manual_group_counts()}",
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

    def mark_best_with_marker_repair(self, status: str) -> None:
        if status not in STATUS_LABELS:
            return
        candidate = self.current()
        proposal = selected_proposal(candidate, status)
        if proposal is None:
            QMessageBox.information(self, "No Proposal", f"{STATUS_LABELS[status]} is not available for this candidate.")
            return
        marker_consistency = marker_analysis_for_status(candidate, status)
        repair_overrides: list[dict[str, int]] = []
        if marker_consistency is not None and marker_consistency.get("ambiguous_merge_suspect_count"):
            hint_lines = []
            for suspect in marker_consistency.get("ambiguous_merge_suspects", []):
                group_index = suspect.get("group_index")
                targets = ", ".join(
                    f"{proposal.variant_index}.{target.get('group_index')}"
                    for target in suspect.get("plausible_merge_targets", [])
                )
                hint_lines.append(f"{proposal.variant_index}.{group_index} -> [{targets}]")
            prompt = (
                "Optional: resolve ambiguous merge targets.\n"
                "Use comma-separated mappings like 4.5->4.6. Leave blank to keep ambiguous.\n\n"
                + "\n".join(hint_lines)
            )
            while True:
                text, ok = QInputDialog.getText(self, "Repair Targets", prompt)
                if not ok:
                    return
                try:
                    repair_overrides = parse_repair_override_text(str(text))
                except ValueError as exc:
                    QMessageBox.information(self, "Repair Target Format", str(exc))
                    continue
                break
            marker_consistency = apply_repair_overrides(marker_consistency, repair_overrides)
        record = review_record(
            candidate,
            status,
            self.manifest_path,
            review_flags=[MARKER_ORPHAN_REPAIR_FLAG],
            status_detail="best_with_marker_orphan_repair",
            marker_consistency=marker_consistency,
            repair_overrides=repair_overrides,
        )
        append_review(self.review_log, record)
        self.latest_reviews[candidate.candidate_id] = record
        logging.info(
            "Reviewed split candidate %s as %s with %s",
            candidate.candidate_id,
            status,
            MARKER_ORPHAN_REPAIR_FLAG,
        )
        self.next_unreviewed()

    def _manual_changed(self) -> None:
        if not self.candidates:
            return
        candidate = self.current()
        self.manual_assignments_by_id[candidate.candidate_id] = dict(self.view.manual_assignments)
        self._refresh_manual_group_buttons()
        self._refresh_info(candidate)

    def toggle_proposal_visibility(self, proposal_index: int, visible: bool) -> None:
        self.view.set_proposal_visible(proposal_index, visible)
        self._refresh_proposal_buttons()

    def set_all_proposals_visible(self, visible: bool) -> None:
        self.view.set_all_proposals_visible(visible)
        for button in self.proposal_buttons:
            button.setChecked(visible)
        self._refresh_proposal_buttons()

    def toggle_markers(self, visible: bool) -> None:
        self.view.set_markers_visible(visible)
        self.marker_button.setText("Markers" if visible else "Markers off")

    def toggle_manual_mode(self) -> None:
        self.view.set_manual_mode(not self.view.manual_mode)
        self._refresh_manual_group_buttons()
        self._refresh_info(self.current())

    def set_manual_group(self, group_number: int) -> None:
        self.view.set_active_manual_group(group_number)
        if not self.view.manual_mode:
            self.view.set_manual_mode(True)
        self._refresh_manual_group_buttons()
        self._refresh_info(self.current())

    def _refresh_manual_group_buttons(self) -> None:
        counts = self.view.manual_group_counts()
        for group_number, button in enumerate(self.group_buttons, start=1):
            color = MANUAL_GROUP_COLORS[group_number - 1]
            active = group_number == self.view.active_manual_group
            count = counts.get(group_number, 0)
            button.setChecked(active)
            button.setText(f"ACTIVE G{group_number}" if active else f"G{group_number}")
            button.setToolTip(f"Manual group {group_number}: {BOX_COLOR_NAMES[group_number - 1]} ({count} fragments)")
            if active:
                button.setStyleSheet(
                    f"QPushButton {{ background-color: {color.name()}; color: black; font-weight: bold; }}"
                )
            elif count:
                button.setStyleSheet(
                    f"QPushButton {{ border: 2px solid {color.name()}; color: {color.name()}; }}"
                )
            else:
                button.setStyleSheet("")
        for action in self.split_actions:
            action.setEnabled(not self.view.manual_mode)
        for action in self.repair_actions:
            action.setEnabled(not self.view.manual_mode)

    def _refresh_proposal_buttons(self) -> None:
        for proposal_index, button in enumerate(self.proposal_buttons, start=1):
            color = BOX_COLORS[proposal_index - 1]
            visible = self.view.proposal_visibility.get(proposal_index, True)
            button.setChecked(visible)
            button.setText(f"Auto {proposal_index}" if visible else f"Auto {proposal_index} off")
            if visible:
                button.setStyleSheet(f"QPushButton {{ border: 2px dashed {color.name()}; }}")
            else:
                button.setStyleSheet("QPushButton { color: #777; }")

    def _marker_summary_lines(self, candidate: Candidate) -> list[str]:
        context = candidate.row.get("revision_marker_context") or {}
        target_digit = context.get("target_digit")
        all_markers = list(context.get("markers") or [])
        matching_markers = markers_for_candidate(candidate, matching_only=True)
        parent_box = box_from_row(candidate.row, "bbox_page_xyxy")
        crop_box = box_from_row(candidate.row, "crop_box_page_xyxy")
        crop_margin = 0.0
        crop_markers = markers_near_box(all_markers, crop_box, crop_margin)
        matching_crop_markers = markers_near_box(matching_markers, crop_box, crop_margin)
        nearest_parent = nearest_marker_distance_to_box(matching_crop_markers or matching_markers, parent_box)
        lines = [
            f"Target digit: {target_digit or '?'}",
            f"Markers in crop: {len(crop_markers)}; matching in crop: {len(matching_crop_markers)}",
            f"Markers on page: {len(all_markers)}; matching on page: {len(matching_markers)}",
            f"Parent bbox nearest matching marker: {compact_distance(nearest_parent)}",
        ]
        for proposal in candidate.proposals[:6]:
            lines.append(format_marker_consistency(analyze_proposal_marker_consistency(proposal, matching_crop_markers)))
        return lines

    def clear_manual_split(self) -> None:
        if not self.candidates:
            return
        candidate = self.current()
        self.manual_assignments_by_id.pop(candidate.candidate_id, None)
        self.view.clear_manual_assignments()
        self._refresh_info(candidate)

    def save_manual_split(self) -> None:
        if not self.candidates:
            return
        candidate = self.current()
        assignments = dict(self.view.manual_assignments)
        proposal = manual_split_proposal(candidate, assignments)
        if proposal is None:
            QMessageBox.information(
                self,
                "Manual Split Needs Groups",
                "Assign fragments into at least two manual groups before saving.",
            )
            return
        record = review_record(candidate, "manual_split", self.manifest_path, assignments)
        append_review(self.review_log, record)
        self.latest_reviews[candidate.candidate_id] = record
        self.manual_assignments_by_id[candidate.candidate_id] = assignments
        logging.info("Reviewed split candidate %s as manual_split", candidate.candidate_id)
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
        if event.modifiers() & Qt.ControlModifier and Qt.Key_1 <= key <= Qt.Key_6:
            if not self.view.manual_mode:
                self.mark_best_with_marker_repair(f"split_variant_{key - Qt.Key_0}")
            return
        if self.view.manual_mode and Qt.Key_1 <= key <= Qt.Key_6:
            self.set_manual_group(key - Qt.Key_0)
            return
        if key in STATUS_KEYS:
            self.mark(STATUS_KEYS[key])
            return
        if key == Qt.Key_M:
            self.toggle_manual_mode()
            return
        if key == Qt.Key_C:
            self.clear_manual_split()
            return
        if key in {Qt.Key_Return, Qt.Key_Enter} and self.view.manual_mode:
            self.save_manual_split()
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
