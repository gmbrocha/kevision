from __future__ import annotations

import os
from pathlib import Path

import pytest

from cloudhammer.bootstrap.delta_stack import normalize_delta_payload
from cloudhammer.bootstrap.cloud_roi_extract import clip_bbox_xywh, derive_target_revision_digit
from cloudhammer.bootstrap.roi_extract import clip_square_roi
from cloudhammer.contracts.detections import CloudDetection
from cloudhammer.data.yolo import _convert_voc_xml_to_yolo, _write_label
from cloudhammer.infer.merge import bbox_iou_xywh, nms_detections
from cloudhammer.infer.tiles import generate_tiles, tile_xyxy_to_page_xywh
from cloudhammer.page_catalog import classify_pdf_from_path, extract_sheet_id
from cloudhammer.page_filter import classify_roi_source_page
from cloudhammer.prelabel.openai_clouds import DEFAULT_MODEL, load_env_file, validate_boxes, yolo_line


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
