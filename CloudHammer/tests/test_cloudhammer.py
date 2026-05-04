from __future__ import annotations

import json
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from cloudhammer.config import CloudHammerConfig
from cloudhammer.bootstrap.delta_stack import normalize_delta_payload
from cloudhammer.bootstrap.cloud_roi_extract import clip_bbox_xywh, derive_target_revision_digit
from cloudhammer.bootstrap.roi_extract import clip_square_roi
from cloudhammer.contracts.detections import CloudDetection, DetectionPage
from cloudhammer.data.yolo import _convert_voc_xml_to_yolo, _write_label
from cloudhammer.data.source_control import (
    audit_sources,
    page_index_for_row,
    revision_group_for_row,
    source_capped_rows,
    source_control_fields,
    source_id_for_row,
)
from cloudhammer.infer.candidate_release import attach_release_decisions, decide_candidate_release
from cloudhammer.infer.candidate_policy import classify_whole_cloud_candidate
from cloudhammer.infer.crop_tightening import CropTighteningParams, crop_metrics, tightened_crop_box_for_bbox
from cloudhammer.infer.detect import infer_page_image
from cloudhammer.infer.fragment_grouping import GroupingParams, group_fragment_detections
from cloudhammer.infer.merge import bbox_iou_xywh, nms_detections
from cloudhammer.infer.tiles import generate_tiles, tile_xyxy_to_page_xywh
from cloudhammer.infer.whole_clouds import (
    WholeCloudExportParams,
    build_whole_cloud_candidates_for_page,
    crop_box_for_candidate,
    whole_cloud_confidence,
)
from cloudhammer.page_catalog import classify_pdf_from_path, extract_sheet_id
from cloudhammer.page_filter import classify_roi_source_page
from cloudhammer.prelabel.openai_clouds import DEFAULT_MODEL, load_env_file, resolve_roi_image_path, validate_boxes, yolo_line
from cloudhammer.prelabel.gpt_review_queue import (
    classify_for_review,
    select_balanced,
    summarize_predictions,
    write_review_queue,
)
from cloudhammer.prelabel.manifest_dedupe import crop_box_xyxy, dedupe_manifest_rows, summarize_dedupe
from cloudhammer.prelabel.review_prep import copy_unreviewed_labels_for_labelimg
from scripts.build_balanced_expansion_review_batch import select_balanced_expansion
from scripts.build_source_split_manifest import _assign_source_disjoint_splits
from utilities.large_cloud_context_labeler import Box, ImageCanvas, Region, square_crop_around_labels, write_annotation


def test_page_path_classification() -> None:
    assert classify_pdf_from_path(Path("set/Narrative 1.pdf")) == "narrative"
    assert classify_pdf_from_path(Path("set/Project Specifications.pdf")) == "spec"
    assert classify_pdf_from_path(Path("set/Drawings.pdf")) is None


def test_sheet_id_extraction() -> None:
    assert extract_sheet_id("GENERAL NOTES\nGI104\nTITLE BLOCK") == "GI104"
    assert extract_sheet_id("sheet AE107.1 floor plan") == "AE107.1"


def test_roi_clipping_keeps_fixed_size_when_possible() -> None:
    assert clip_square_roi(40, 50, 100, 500, 400) == [0, 0, 100, 100]
    assert clip_square_roi(490, 390, 100, 500, 400) == [400, 300, 100, 100]
    assert clip_square_roi(250, 200, 100, 500, 400) == [200, 150, 100, 100]


def test_cloud_roi_bbox_clips_to_page() -> None:
    assert clip_bbox_xywh([-20, -10, 120, 90], 500, 400) == [0, 0, 120, 90]
    assert clip_bbox_xywh([480, 390, 120, 90], 500, 400) == [380, 310, 120, 90]


def test_roi_page_filter_excludes_index_and_cover_pages() -> None:
    index = classify_roi_source_page({"sheet_title": "Drawing Index", "pdf_stem": "Rev 3"})
    cover = classify_roi_source_page({"sheet_title": "Cover Sheet"})
    lockable_cover = classify_roi_source_page({"sheet_title": "LOCKABLE COVER"})
    plan = classify_roi_source_page({"sheet_title": "2ND FLOOR PLAN - SHELL"})
    assert index.is_excluded and index.exclude_reason == "index_page"
    assert cover.is_excluded and cover.exclude_reason == "cover_sheet"
    assert not lockable_cover.is_excluded
    assert not plan.is_excluded and plan.exclude_reason == "none"


def test_target_revision_digit_derives_from_source_name() -> None:
    assert derive_target_revision_digit({"pdf_stem": "260219 - VA Biloxi Rev 4_Architectural 1"}) == "4"
    assert derive_target_revision_digit({"pdf_stem": "Revision_Set_7"}) == "7"
    assert derive_target_revision_digit({"pdf_stem": "260309 - Drawing Rev2- Steel Grab Bars"}) == "2"


def test_tiles_cover_page_and_map_coordinates() -> None:
    tiles = generate_tiles(width=300, height=260, tile_size=128, overlap=32)
    assert tiles[0].bbox == (0, 0, 128, 128)
    assert max(tile.x + tile.width for tile in tiles) == 300
    assert max(tile.y + tile.height for tile in tiles) == 260
    assert tile_xyxy_to_page_xywh(tiles[0], (10, 20, 30, 50)) == [10.0, 20.0, 20.0, 30.0]


def test_nms_removes_lower_confidence_overlap() -> None:
    detections = [
        CloudDetection(0.9, [0, 0, 100, 100], None, "page_tile"),
        CloudDetection(0.7, [10, 10, 100, 100], None, "page_tile"),
        CloudDetection(0.6, [220, 220, 40, 40], None, "page_tile"),
    ]
    kept = nms_detections(detections, 0.5)
    assert [det.confidence for det in kept] == [0.9, 0.6]
    assert bbox_iou_xywh(detections[0].bbox_page, detections[1].bbox_page) > 0.5


def test_page_inference_sends_three_channel_tiles_to_yolo(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    cv2.imwrite(str(image_path), np.zeros((40, 40), dtype=np.uint8))

    class FakeModel:
        def __init__(self) -> None:
            self.shapes: list[tuple[int, ...]] = []

        def predict(self, source, conf: float, verbose: bool):  # type: ignore[no-untyped-def]
            self.shapes.append(tuple(source.shape))
            return []

    model = FakeModel()

    detections = infer_page_image(
        model,
        image_path,
        tile_size=24,
        tile_overlap=8,
        confidence_threshold=0.5,
        nms_iou=0.5,
    )

    assert detections == []
    assert model.shapes
    assert all(shape[-1] == 3 for shape in model.shapes)


def test_delta_normalization_contract() -> None:
    payload = {
        "pdf_path": "drawing.pdf",
        "page_index": 3,
        "target_digit": "2",
        "canonical_side_px": 120,
        "active_deltas": [
            {
                "digit": "2",
                "status": "active",
                "center": {"x": 10, "y": 20},
                "triangle": {
                    "apex": {"x": 10, "y": 0},
                    "left_base": {"x": 0, "y": 30},
                    "right_base": {"x": 20, "y": 30},
                },
                "score": 0.9,
                "geometry_score": 0.8,
                "side_support": 0.7,
                "base_support": 0.6,
                "interior_ink_ratio": 0.05,
            }
        ],
    }
    normalized = normalize_delta_payload(payload)
    assert normalized["pdf_path"] == "drawing.pdf"
    assert normalized["page_index"] == 3
    assert normalized["active_deltas"][0]["center"] == {"x": 10.0, "y": 20.0}


def test_voc_conversion_allows_multiple_cloud_boxes_only(tmp_path: Path) -> None:
    xml_path = tmp_path / "labels.xml"
    out_path = tmp_path / "labels.txt"
    xml_path.write_text(
        """<annotation>
  <size><width>200</width><height>100</height></size>
  <object><name>cloud_motif</name><bndbox><xmin>10</xmin><ymin>10</ymin><xmax>50</xmax><ymax>30</ymax></bndbox></object>
  <object><name>triangle</name><bndbox><xmin>60</xmin><ymin>20</ymin><xmax>80</xmax><ymax>40</ymax></bndbox></object>
  <object><name>cloud_motif</name><bndbox><xmin>100</xmin><ymin>50</ymin><xmax>180</xmax><ymax>90</ymax></bndbox></object>
</annotation>""",
        encoding="utf-8",
    )
    _convert_voc_xml_to_yolo(xml_path, out_path)
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(line.startswith("0 ") for line in lines)


def test_yolo_txt_rejects_non_cloud_class_ids(tmp_path: Path) -> None:
    label_path = tmp_path / "bad.txt"
    out_path = tmp_path / "out.txt"
    label_path.write_text("1 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="supports only class 0"):
        _write_label(label_path, out_path)


def test_api_box_validation_scales_to_original_image() -> None:
    payload = {
        "has_cloud": True,
        "boxes": [
            {"x1": 100, "y1": 50, "x2": 300, "y2": 200, "confidence": 0.9, "visual_type": "thin"},
            {"x1": 10, "y1": 10, "x2": 14, "y2": 14, "confidence": 0.99, "visual_type": "bold"},
            {"x1": 0, "y1": 0, "x2": 900, "y2": 900, "confidence": 0.99, "visual_type": "bold"},
            {"x1": 10, "y1": 10, "x2": 200, "y2": 200, "confidence": 0.2, "visual_type": "bold"},
        ],
    }
    accepted = validate_boxes(payload, 512, 512, 2048, 2048, min_confidence=0.6)
    assert len(accepted) == 1
    assert accepted[0]["visual_type"] == "thin"
    assert accepted[0]["original_box"]["x1"] == 400
    assert accepted[0]["original_box"]["y2"] == 800


def test_yolo_line_uses_class_zero() -> None:
    line = yolo_line({"x1": 100, "y1": 50, "x2": 300, "y2": 150}, 400, 200)
    assert line == "0 0.50000000 0.50000000 0.50000000 0.50000000"


def test_api_prelabel_defaults_to_gpt_54() -> None:
    assert DEFAULT_MODEL == "gpt-5.4"


def test_load_env_file_sets_missing_values_without_overwriting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=from-file\n"
        "export CLOUDHAMMER_TEST_VALUE='quoted value'\n"
        "EXISTING=value-from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CLOUDHAMMER_TEST_VALUE", raising=False)
    monkeypatch.setenv("EXISTING", "from-env")

    assert load_env_file(env_path)
    assert os.environ["OPENAI_API_KEY"] == "from-file"
    assert os.environ["CLOUDHAMMER_TEST_VALUE"] == "quoted value"
    assert os.environ["EXISTING"] == "from-env"


def test_review_prep_copies_only_txt_without_overwriting(tmp_path: Path) -> None:
    src = tmp_path / "api_cloud_labels_unreviewed"
    dst = tmp_path / "cloud_labels_reviewed"
    src.mkdir()
    src.joinpath("roi_001.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    src.joinpath("roi_001.png").write_text("not an image copy candidate", encoding="utf-8")
    dst.mkdir()
    dst.joinpath("roi_001.txt").write_text("corrected\n", encoding="utf-8")

    result = copy_unreviewed_labels_for_labelimg(
        CloudHammerConfig(root=tmp_path, data={"paths": {}}),
        source_dir=src,
        reviewed_dir=dst,
    )

    assert result == {"copied": 0, "skipped": 1, "source_count": 1}
    assert dst.joinpath("roi_001.txt").read_text(encoding="utf-8") == "corrected\n"
    assert dst.joinpath("classes.txt").read_text(encoding="utf-8") == "cloud_motif\n"
    assert not dst.joinpath("roi_001.png").exists()


def test_source_control_normalizes_current_crop_id_formats() -> None:
    row = {"cloud_roi_id": "eval_symbol_text_fp_hn_Revision_1_-_Drawing_Changes_6cbee960_p0001_whole_006"}

    assert source_id_for_row(row) == "Revision_1_-_Drawing_Changes_6cbee960"
    assert page_index_for_row(row) == 1
    assert revision_group_for_row(row) == "Revision #1 - Drawing Changes"

    rev7 = {"cloud_roi_id": "Revision_Set_7_37f6066a_p0003_random_0199"}
    assert source_id_for_row(rev7) == "Revision_Set_7_37f6066a"
    assert page_index_for_row(rev7) == 3
    assert revision_group_for_row(rev7) == "Revision #7 - RFI 141 - Deteriorated Attic Wood"


def test_source_audit_detects_source_split_leakage() -> None:
    rows = [
        {"cloud_roi_id": "Revision_1_-_Drawing_Changes_6cbee960_p0001_m001", "split": "train"},
        {"cloud_roi_id": "Revision_1_-_Drawing_Changes_6cbee960_p0002_m001", "split": "val"},
        {"cloud_roi_id": "260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3_p0001_m001", "split": "train"},
    ]

    summary = audit_sources(rows)

    assert "Revision_1_-_Drawing_Changes_6cbee960" in summary["mixed_split_sources"]
    assert not summary["mixed_split_source_pages"]


def test_source_split_builder_excludes_quasi_holdout_and_caps_pages() -> None:
    rows = [
        {"cloud_roi_id": f"Revision_1_-_Drawing_Changes_6cbee960_p0001_m{index:03d}", "has_cloud": True}
        for index in range(5)
    ]
    rows.extend(
        {"cloud_roi_id": f"Revision_Set_7_37f6066a_p0003_m{index:03d}", "has_cloud": True}
        for index in range(3)
    )

    assigned, holdout = _assign_source_disjoint_splits(
        rows,
        val_fraction=0.5,
        quasi_holdout_revisions={"Revision #7 - RFI 141 - Deteriorated Attic Wood"},
    )
    capped = source_capped_rows(assigned, max_rows_per_source=10, max_rows_per_source_page=2)

    assert len(holdout) == 3
    assert all(row["split"] == "quasi_holdout" for row in holdout)
    assert len(capped) == 2
    assert all(row["source_page_key"].endswith(":p0001") for row in capped)


def test_balanced_expansion_batch_respects_existing_ids_and_holdout(tmp_path: Path) -> None:
    image = tmp_path / "crop.png"
    image.write_text("placeholder", encoding="utf-8")
    candidates = [
        {
            "cloud_roi_id": "Revision_1_-_Drawing_Changes_6cbee960_p0001_random_0001",
            "image_path": str(image),
            "review_bucket": "gpt_negative_spotcheck",
        },
        {
            "cloud_roi_id": "Revision_1_-_Drawing_Changes_6cbee960_p0001_random_0002",
            "image_path": str(image),
            "review_bucket": "high_conf_positive",
            "max_confidence": "0.95",
        },
        {
            "cloud_roi_id": "Revision_Set_7_37f6066a_p0003_random_0001",
            "image_path": str(image),
            "review_bucket": "high_conf_positive",
            "max_confidence": "0.96",
        },
    ]

    selected, summary = select_balanced_expansion(
        candidates,
        existing_ids={"Revision_1_-_Drawing_Changes_6cbee960_p0001_random_0002"},
        api_labeled_ids=set(),
        target_count=10,
        quotas={"normal_hard_negative": 5, "high_conf_positive": 5},
        max_rows_per_source=5,
        max_rows_per_source_page=5,
        excluded_revisions={"Revision #7 - RFI 141 - Deteriorated Attic Wood"},
    )

    assert [source_control_fields(row)["source_page_index"] for row in selected] == [1]
    assert [row["cloud_roi_id"] for row in selected] == ["Revision_1_-_Drawing_Changes_6cbee960_p0001_random_0001"]
    assert summary["skipped"]["existing_reviewed"] == 1
    assert summary["skipped"]["quasi_holdout_excluded"] == 1


def test_prelabel_resolves_migrated_absolute_roi_path(tmp_path: Path) -> None:
    image_dir = tmp_path / "data" / "cloud_roi_images"
    image_dir.mkdir(parents=True)
    image_path = image_dir / "roi_001.png"
    image_path.write_text("placeholder", encoding="utf-8")
    cfg = CloudHammerConfig(root=tmp_path, data={"paths": {"cloud_roi_images": "data/cloud_roi_images"}})

    resolved = resolve_roi_image_path({"roi_image_path": "F:\\old\\CloudHammer\\data\\cloud_roi_images\\roi_001.png"}, cfg)

    assert resolved == image_path.resolve()


def _prediction_row(
    roi_id: str,
    revision: str,
    candidate_source: str,
    accepted_boxes: list[dict] | None = None,
    has_cloud: bool = True,
    status: str = "ok",
    parsed_boxes: list[dict] | None = None,
) -> dict:
    boxes = accepted_boxes or []
    return {
        "cloud_roi_id": roi_id,
        "status": status,
        "has_cloud": has_cloud,
        "accepted_box_count": len(boxes),
        "accepted_boxes": boxes,
        "parsed_response": {"boxes": parsed_boxes or []},
        "manifest_row": {
            "candidate_source": candidate_source,
            "pdf_path": str(Path("revision_sets") / revision / "drawing.pdf"),
        },
    }


def test_gpt_review_classification_buckets() -> None:
    assert (
        classify_for_review(
            _prediction_row(
                "high",
                "Revision #1 - Drawing Changes",
                "target_marker_neighborhood",
                [{"confidence": 0.95, "visual_type": "bold"}],
            )
        )
        == "high_conf_positive"
    )
    assert (
        classify_for_review(
            _prediction_row(
                "weird",
                "Revision #1 - Drawing Changes",
                "target_marker_neighborhood",
                [{"confidence": 0.95, "visual_type": "faint"}],
            )
        )
        == "weird_multi_faint_partial"
    )
    assert (
        classify_for_review(
            _prediction_row("hardneg", "Revision #5 - RFI 126", "target_marker_neighborhood", [], has_cloud=False)
        )
        == "hard_negative_marker_no_cloud"
    )
    assert (
        classify_for_review(
            _prediction_row("spot", "Revision #7 - RFI 141", "random_standard_drawing_crop", [], has_cloud=False)
        )
        == "gpt_negative_spotcheck"
    )
    assert (
        classify_for_review(
            _prediction_row("ambig", "Revision #2 - Mod 5", "random_standard_drawing_crop", [], parsed_boxes=[{}])
        )
        == "ambiguous_positive"
    )


def test_gpt_prelabel_summary_tracks_manifest_completeness() -> None:
    predictions = [
        _prediction_row(
            "one",
            "Revision #1 - Drawing Changes",
            "target_marker_neighborhood",
            [{"confidence": 0.91, "visual_type": "bold"}],
        ),
        _prediction_row("two", "Revision #5 - RFI 126", "random_standard_drawing_crop", [], has_cloud=False),
    ]
    manifest = [
        {"cloud_roi_id": "one"},
        {"cloud_roi_id": "two"},
        {"cloud_roi_id": "three"},
    ]

    summary = summarize_predictions(predictions, manifest)

    assert summary["prediction_rows"] == 2
    assert summary["expected_rows"] == 3
    assert summary["missing_predictions"] == ["three"]
    assert summary["status"] == {"ok": 2}
    assert summary["review_bucket"]["high_conf_positive"] == 1
    assert summary["review_bucket"]["gpt_negative_spotcheck"] == 1


def test_select_balanced_spreads_rows_across_revision_and_source() -> None:
    rows = [
        _prediction_row(f"r1_{idx}", "Revision #1 - Drawing Changes", "target_marker_neighborhood")
        for idx in range(5)
    ] + [
        _prediction_row(f"r5_{idx}", "Revision #5 - RFI 126", "random_standard_drawing_crop")
        for idx in range(5)
    ]

    selected = select_balanced(rows, limit=4, seed=1)

    selected_ids = {row["cloud_roi_id"] for row in selected}
    assert len(selected_ids) == 4
    assert any(item.startswith("r1_") for item in selected_ids)
    assert any(item.startswith("r5_") for item in selected_ids)


def test_write_review_queue_copies_into_isolated_queue(tmp_path: Path) -> None:
    src_image = tmp_path / "source.png"
    src_label = tmp_path / "source.txt"
    src_overlay = tmp_path / "source.jpg"
    src_image.write_text("image", encoding="utf-8")
    src_label.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    src_overlay.write_text("overlay", encoding="utf-8")
    row = _prediction_row(
        "roi_001",
        "Revision #1 - Drawing Changes",
        "target_marker_neighborhood",
        [{"confidence": 0.95, "visual_type": "bold"}],
    )
    row["source_image_path"] = str(src_image)
    row["label_path"] = str(src_label)
    row["review_image_path"] = str(src_overlay)

    result = write_review_queue(tmp_path / "queues", "high_conf_positive", [row])

    queue_dir = tmp_path / "queues" / "high_conf_positive"
    assert result.count == 1
    assert queue_dir.joinpath("images", "roi_001.png").read_text(encoding="utf-8") == "image"
    assert queue_dir.joinpath("labels", "roi_001.txt").read_text(encoding="utf-8").startswith("0 ")
    assert queue_dir.joinpath("labels", "classes.txt").read_text(encoding="utf-8") == "cloud_motif\n"
    assert queue_dir.joinpath("gpt_overlays", "roi_001.jpg").read_text(encoding="utf-8") == "overlay"
    assert queue_dir.joinpath("images.txt").read_text(encoding="utf-8").strip().endswith("roi_001.png")


def test_manifest_dedupe_parses_crop_box_formats() -> None:
    assert crop_box_xyxy({"roi_bbox_page": [10, 20, 100, 200]}) == (10.0, 20.0, 110.0, 220.0)
    assert crop_box_xyxy({"crop_box_page": [10, 20, 100, 200]}) == (10.0, 20.0, 100.0, 200.0)


def test_manifest_dedupe_excludes_same_page_shifted_crop() -> None:
    rows = [
        {
            "cloud_roi_id": "marker",
            "candidate_source": "target_marker_neighborhood",
            "pdf_path": "set/page.pdf",
            "page_index": 1,
            "roi_bbox_page": [0, 0, 100, 100],
            "cloud_likeness": 0.8,
        },
        {
            "cloud_roi_id": "random_overlap",
            "candidate_source": "random_standard_drawing_crop",
            "pdf_path": "set/page.pdf",
            "page_index": 1,
            "crop_box_page": [20, 10, 120, 110],
            "cloud_likeness": 0.9,
        },
        {
            "cloud_roi_id": "other_page",
            "candidate_source": "random_standard_drawing_crop",
            "pdf_path": "set/page.pdf",
            "page_index": 2,
            "crop_box_page": [20, 10, 120, 110],
            "cloud_likeness": 0.9,
        },
    ]

    decisions = dedupe_manifest_rows(rows, iou_threshold=0.30, overlap_smaller_threshold=0.65)

    assert [decision.kept for decision in decisions] == [True, False, True]
    assert decisions[1].duplicate_of == "marker"
    summary = summarize_dedupe(decisions)
    assert summary["input_rows"] == 3
    assert summary["kept_rows"] == 2
    assert summary["excluded_rows"] == 1


def test_large_cloud_auto_crop_is_square_and_contains_labels() -> None:
    labels = [
        Box(10, 20, 110, 80, "cloud_whole"),
        Box(140, 70, 220, 140, "cloud_whole"),
    ]

    crop = square_crop_around_labels(labels, image_width=300, image_height=300, margin_percent=10)

    assert crop is not None
    assert crop.x1 >= 0
    assert crop.y1 >= 0
    assert crop.x2 <= 300
    assert crop.y2 <= 300
    assert crop.width == pytest.approx(crop.height)
    assert crop.x1 <= 10
    assert crop.y1 <= 20
    assert crop.x2 >= 220
    assert crop.y2 >= 140


def test_large_cloud_annotation_exports_crop_and_crop_coordinates(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    cv2.imwrite(str(image_path), np.full((100, 120), 255, dtype=np.uint8))
    region = Region(
        id="region_001",
        crop_box=Box(10, 20, 90, 100, "context_crop"),
        labels=[Box(30, 40, 70, 80, "cloud_whole")],
    )
    sidecar_path = tmp_path / "labels" / "page.largecloud.json"
    crop_dir = tmp_path / "crops"

    write_annotation(image_path, sidecar_path, crop_dir, [region], "cloud_whole")

    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    crop_path = Path(payload["regions"][0]["crop_image_path"])
    exported = cv2.imread(str(crop_path), cv2.IMREAD_UNCHANGED)
    assert payload["schema"] == "cloudhammer.large_cloud_context.v1"
    assert crop_path.exists()
    assert exported.shape[:2] == (80, 80)
    assert payload["regions"][0]["labels_crop_xyxy"][0]["box"]["x1"] == 20
    assert payload["regions"][0]["labels_crop_xyxy"][0]["box"]["y1"] == 20


def test_large_cloud_canvas_draw_regions_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    image_path = tmp_path / "page.png"
    cv2.imwrite(str(image_path), np.full((100, 100), 255, dtype=np.uint8))
    canvas = ImageCanvas()
    canvas.load_image(image_path)

    canvas.draw_regions(
        [
            Region(
                id="region_001",
                crop_box=Box(5, 5, 60, 60, "context_crop"),
                labels=[Box(10, 10, 40, 40, "cloud_whole")],
            )
        ],
        active_region=0,
    )

    assert app is not None
    assert len(canvas.scene_obj.items()) > 1


def test_fragment_grouping_merges_nearby_boxes() -> None:
    detections = [
        CloudDetection(0.9, [100, 100, 80, 40], None, "page_tile"),
        CloudDetection(0.8, [250, 110, 70, 45], None, "page_tile"),
        CloudDetection(0.7, [900, 900, 60, 60], None, "page_tile"),
    ]

    groups = group_fragment_detections(
        detections,
        image_width=1200,
        image_height=1200,
        params=GroupingParams(expansion_ratio=0.7, min_padding=60, max_padding=120, group_margin_ratio=0.0),
    )

    member_counts = sorted(group.metadata["member_count"] for group in groups)
    assert member_counts == [1, 2]
    merged = next(group for group in groups if group.metadata["member_count"] == 2)
    x, y, w, h = merged.bbox_page
    assert x <= 100
    assert y <= 100
    assert x + w >= 320
    assert y + h >= 155
    assert merged.source_mode == "fragment_group"


def test_fragment_grouping_preserves_far_singletons() -> None:
    detections = [
        CloudDetection(0.9, [10, 10, 40, 40], None, "page_tile"),
        CloudDetection(0.8, [500, 500, 40, 40], None, "page_tile"),
    ]

    groups = group_fragment_detections(
        detections,
        image_width=800,
        image_height=800,
        params=GroupingParams(expansion_ratio=0.2, min_padding=20, max_padding=40),
    )

    assert len(groups) == 2
    assert all(group.metadata["member_count"] == 1 for group in groups)


def test_fragment_grouping_splits_oversized_low_fill_component() -> None:
    detections = [
        CloudDetection(0.90, [100, 100, 200, 120], None, "page_tile"),
        CloudDetection(0.85, [110, 500, 190, 110], None, "page_tile"),
        CloudDetection(0.80, [500, 110, 190, 120], None, "page_tile"),
        CloudDetection(0.88, [120, 1200, 180, 120], None, "page_tile"),
        CloudDetection(0.84, [500, 1210, 170, 110], None, "page_tile"),
        CloudDetection(0.78, [900, 1220, 160, 100], None, "page_tile"),
    ]

    groups = group_fragment_detections(
        detections,
        image_width=1400,
        image_height=1600,
        params=GroupingParams(
            expansion_ratio=1.2,
            min_padding=350,
            max_padding=500,
            group_margin_ratio=0.0,
            split_min_members=6,
            split_min_partition_members=3,
            split_min_gap=400,
            split_gap_ratio=0.1,
            split_max_fill_ratio=0.3,
        ),
    )

    assert len(groups) == 2
    assert sorted(group.metadata["member_count"] for group in groups) == [3, 3]


def test_fragment_grouping_can_refine_overmerged_sparse_groups() -> None:
    detections = [
        CloudDetection(0.92, [100, 100, 180, 90], None, "page_tile"),
        CloudDetection(0.91, [290, 100, 180, 90], None, "page_tile"),
        CloudDetection(0.90, [760, 100, 180, 90], None, "page_tile"),
        CloudDetection(0.89, [950, 100, 180, 90], None, "page_tile"),
    ]

    groups = group_fragment_detections(
        detections,
        image_width=1400,
        image_height=500,
        params=GroupingParams(
            expansion_ratio=1.5,
            min_padding=300,
            max_padding=500,
            group_margin_ratio=0.0,
            min_group_margin=0,
            max_group_margin=0,
            split_min_members=10,
            overmerge_refinement_enabled=True,
            overmerge_refinement_profile="very_tight",
            overmerge_refine_min_members=4,
            overmerge_refine_max_fill_ratio=1.0,
        ),
    )

    assert len(groups) == 2
    assert sorted(group.metadata["member_count"] for group in groups) == [2, 2]


def test_whole_cloud_candidate_adds_crop_box_and_confidence_metadata() -> None:
    page = DetectionPage(
        pdf="revision.pdf",
        page=1,
        render_path="page.png",
        detections=[
            CloudDetection(
                0.85,
                [100, 120, 300, 180],
                None,
                "fragment_group",
                metadata={"member_count": 3, "member_confidences": [0.85, 0.8, 0.75]},
            )
        ],
    )

    candidates = build_whole_cloud_candidates_for_page(
        page,
        image_width=800,
        image_height=600,
        params=WholeCloudExportParams(crop_margin_ratio=0.1, min_crop_margin=25, max_crop_margin=50),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_mode == "whole_cloud_candidate"
    assert candidate.confidence > 0.8
    assert candidate.metadata["size_bucket"] == "small"
    crop = candidate.metadata["crop_box_page"]
    assert crop[0] < 100
    assert crop[1] < 120
    assert crop[0] + crop[2] > 400
    assert crop[1] + crop[3] > 300


def test_whole_cloud_crop_box_clips_to_page_bounds() -> None:
    crop = crop_box_for_candidate(
        [5, 10, 100, 120],
        image_width=180,
        image_height=160,
        params=WholeCloudExportParams(crop_margin_ratio=0.5, min_crop_margin=50, max_crop_margin=80),
    )

    assert crop[0] == 0
    assert crop[1] == 0
    assert crop[0] + crop[2] <= 180
    assert crop[1] + crop[3] <= 160


def test_whole_cloud_confidence_rewards_multi_fragment_groups() -> None:
    singleton = CloudDetection(0.75, [0, 0, 100, 80], None, "fragment_group", metadata={"member_count": 1})
    multi = CloudDetection(
        0.75,
        [0, 0, 300, 180],
        None,
        "fragment_group",
        metadata={"member_count": 4, "member_confidences": [0.75, 0.72, 0.7, 0.68]},
    )

    assert whole_cloud_confidence(multi, 1000, 1000) > whole_cloud_confidence(singleton, 1000, 1000)


def test_tightened_crop_box_uses_smaller_adaptive_margin() -> None:
    crop = tightened_crop_box_for_bbox(
        (100.0, 120.0, 400.0, 280.0),
        page_width=800,
        page_height=600,
        params=CropTighteningParams(margin_ratio=0.1, min_margin=35, max_margin=80, min_crop_side=120),
    )

    assert crop == (65.0, 85.0, 435.0, 315.0)
    metrics = crop_metrics((0.0, 0.0, 700.0, 500.0), crop, (100.0, 120.0, 400.0, 280.0))
    assert metrics["area_ratio_vs_original"] < 0.25
    assert metrics["area_reduction_pct"] > 75.0


def test_tightened_crop_box_clips_to_page_bounds() -> None:
    crop = tightened_crop_box_for_bbox(
        (5.0, 10.0, 80.0, 90.0),
        page_width=120,
        page_height=110,
        params=CropTighteningParams(margin_ratio=0.5, min_margin=50, max_margin=80, min_crop_side=100),
    )

    assert crop[0] == 0.0
    assert crop[1] == 0.0
    assert crop[2] <= 120.0
    assert crop[3] <= 110.0


def test_whole_cloud_candidate_policy_buckets_review_risk() -> None:
    assert (
        classify_whole_cloud_candidate(
            {"whole_cloud_confidence": 0.3, "member_count": 1, "group_fill_ratio": 0.5}
        )["policy_bucket"]
        == "likely_false_positive"
    )
    assert (
        classify_whole_cloud_candidate(
            {"whole_cloud_confidence": 0.9, "member_count": 3, "group_fill_ratio": 0.4}
        )["policy_bucket"]
        == "auto_deliverable_candidate"
    )
    assert (
        classify_whole_cloud_candidate(
            {"whole_cloud_confidence": 0.98, "member_count": 11, "group_fill_ratio": 0.2}
        )["policy_bucket"]
        == "needs_split_review"
    )
    assert (
        classify_whole_cloud_candidate(
            {"whole_cloud_confidence": 0.55, "member_count": 1, "group_fill_ratio": 0.5}
        )["policy_bucket"]
        == "low_priority_review"
    )


def test_release_decision_uses_human_review_before_policy() -> None:
    auto_overmerged = decide_candidate_release(
        {
            "policy_bucket": "auto_deliverable_candidate",
            "review_status": "overmerged",
        }
    )
    likely_fp_accepted = decide_candidate_release(
        {
            "policy_bucket": "likely_false_positive",
            "review_status": "accept",
        }
    )

    assert auto_overmerged.action == "needs_split_review"
    assert not auto_overmerged.include_in_default_release
    assert likely_fp_accepted.action == "release_candidate"
    assert likely_fp_accepted.include_in_default_release


def test_attach_release_decisions_routes_unreviewed_policy_buckets() -> None:
    rows = attach_release_decisions(
        [
            {"candidate_id": "a", "policy_bucket": "auto_deliverable_candidate"},
            {"candidate_id": "b", "policy_bucket": "needs_split_review"},
            {"candidate_id": "c", "policy_bucket": "likely_false_positive"},
            {"candidate_id": "d", "policy_bucket": "review_candidate"},
        ]
    )

    assert [row["release_action"] for row in rows] == [
        "release_candidate",
        "needs_split_review",
        "quarantine_likely_false_positive",
        "review_candidate",
    ]
