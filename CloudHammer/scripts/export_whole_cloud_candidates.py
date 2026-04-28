from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.contracts.detections import DetectionPage, load_detection_manifest, write_detection_manifest
from cloudhammer.infer.whole_clouds import (
    WholeCloudExportParams,
    containment_xyxy,
    export_whole_cloud_page,
    iou_xyxy,
    round_box,
)
from cloudhammer.manifests import write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]


def draw_candidate_overlay(image, page: DetectionPage, output_path: Path) -> None:
    if len(image.shape) == 2:
        overlay = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        overlay = image.copy()

    for index, det in enumerate(page.detections, start=1):
        x, y, w, h = [int(round(value)) for value in det.bbox_page]
        crop = det.metadata.get("crop_box_page") or det.bbox_page
        cx, cy, cw, ch = [int(round(value)) for value in crop]
        tier = str(det.metadata.get("confidence_tier", "medium"))
        color = (0, 180, 0) if tier == "high" else (0, 165, 255) if tier == "medium" else (0, 0, 220)
        cv2.rectangle(overlay, (cx, cy), (cx + cw, cy + ch), (170, 170, 170), 3)
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 7)
        cv2.putText(
            overlay,
            f"W{index} {det.confidence:.2f} {det.metadata.get('size_bucket', '')}",
            (x, max(35, y - 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            color,
            3,
            cv2.LINE_AA,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), overlay)


def source_name_for(path: Path) -> str:
    return path.stem


def process_grouped_file(
    grouped_path: Path,
    output_dir: Path,
    params: WholeCloudExportParams,
    write_overlays: bool,
) -> dict[str, Any]:
    pages = load_detection_manifest(grouped_path)
    whole_pages: list[DetectionPage] = []
    rows: list[dict[str, Any]] = []
    page_summaries: list[dict[str, Any]] = []
    crop_dir = output_dir / "crops" / source_name_for(grouped_path)

    for page in pages:
        whole_page, page_rows = export_whole_cloud_page(page, crop_dir, params)
        if whole_page is None:
            continue
        whole_pages.append(whole_page)
        rows.extend(page_rows)
        if write_overlays and page.render_path:
            image = cv2.imread(page.render_path, cv2.IMREAD_GRAYSCALE)
            if image is not None:
                overlay_path = output_dir / "overlays" / f"{Path(page.render_path).stem}_whole_clouds.png"
                draw_candidate_overlay(image, whole_page, overlay_path)
            else:
                overlay_path = None
        else:
            overlay_path = None
        page_summaries.append(
            {
                "pdf": page.pdf,
                "pdf_stem": source_name_for(grouped_path),
                "page": page.page,
                "render_path": page.render_path,
                "candidate_count": len(whole_page.detections),
                "size_buckets": dict(Counter(row["size_bucket"] for row in page_rows)),
                "confidence_tiers": dict(Counter(row["confidence_tier"] for row in page_rows)),
                "overlay_path": None if overlay_path is None else str(overlay_path),
            }
        )

    detection_path = output_dir / "detections_whole" / grouped_path.name
    write_detection_manifest(detection_path, whole_pages, model=f"whole_cloud_candidates_from:{grouped_path}")
    return {
        "source_grouped_detection_json": str(grouped_path),
        "whole_detection_json": str(detection_path),
        "rows": rows,
        "pages": page_summaries,
    }


def thumbnail_for_row(row: dict[str, Any], thumb_size: int) -> np.ndarray | None:
    image = cv2.imread(str(row["crop_image_path"]), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    height, width = image.shape[:2]
    scale = min(thumb_size / max(1, width), thumb_size / max(1, height))
    resized = cv2.resize(image, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_AREA)
    canvas = np.full((thumb_size + 44, thumb_size, 3), 255, dtype=np.uint8)
    y = (thumb_size - resized.shape[0]) // 2
    x = (thumb_size - resized.shape[1]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)
    label = f"{row['candidate_id'][-13:]} {row['whole_cloud_confidence']:.2f} {row['size_bucket']}"
    cv2.putText(canvas, label, (5, thumb_size + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(
        canvas,
        f"n={row['member_count']} p{row['page_number']}",
        (5, thumb_size + 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (0, 0, 0),
        1,
        cv2.LINE_AA,
    )
    return canvas


def write_contact_sheet(rows: list[dict[str, Any]], output_path: Path, thumb_size: int = 260, cols: int = 5) -> None:
    thumbs = [thumb for row in rows if (thumb := thumbnail_for_row(row, thumb_size)) is not None]
    if not thumbs:
        return
    rows_count = int(np.ceil(len(thumbs) / cols))
    cell_height, cell_width = thumbs[0].shape[:2]
    sheet = np.full((rows_count * cell_height, cols * cell_width, 3), 245, dtype=np.uint8)
    for index, thumb in enumerate(thumbs):
        row = index // cols
        col = index % cols
        sheet[row * cell_height : (row + 1) * cell_height, col * cell_width : (col + 1) * cell_width] = thumb
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), sheet)


def label_box_from_payload(payload: dict[str, Any]) -> tuple[float, float, float, float]:
    box = payload["box"]
    return (float(box["x1"]), float(box["y1"]), float(box["x2"]), float(box["y2"]))


def load_manual_large_cloud_labels(labels_dir: Path) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    for sidecar in sorted(labels_dir.glob("*.largecloud.json")):
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        render_path = str(payload.get("image_path") or "")
        for region in payload.get("regions", []):
            for label_index, label in enumerate(region.get("labels", []), start=1):
                labels.append(
                    {
                        "sidecar_path": str(sidecar),
                        "render_path": render_path,
                        "render_stem": Path(render_path).stem,
                        "region_id": region.get("id"),
                        "label_index": label_index,
                        "label_box_xyxy": label_box_from_payload(label),
                    }
                )
    return labels


def audit_against_manual_labels(rows: list[dict[str, Any]], labels_dir: Path, output_dir: Path) -> dict[str, Any]:
    labels = load_manual_large_cloud_labels(labels_dir)
    candidates_by_render: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        candidates_by_render[Path(str(row.get("render_path") or "")).stem].append(row)

    audit_rows: list[dict[str, Any]] = []
    for label in labels:
        best: dict[str, Any] | None = None
        for candidate in candidates_by_render.get(label["render_stem"], []):
            candidate_box = tuple(float(value) for value in candidate["bbox_page_xyxy"])
            crop_box = tuple(float(value) for value in candidate["crop_box_page_xyxy"])
            label_box = label["label_box_xyxy"]
            score = {
                "candidate_id": candidate["candidate_id"],
                "candidate_box_iou": iou_xyxy(label_box, candidate_box),
                "label_containment_in_candidate_box": containment_xyxy(label_box, candidate_box),
                "label_containment_in_crop": containment_xyxy(label_box, crop_box),
                "candidate_confidence": candidate["whole_cloud_confidence"],
                "size_bucket": candidate["size_bucket"],
                "crop_image_path": candidate["crop_image_path"],
            }
            if best is None or (
                score["label_containment_in_crop"],
                score["label_containment_in_candidate_box"],
                score["candidate_box_iou"],
            ) > (
                best["label_containment_in_crop"],
                best["label_containment_in_candidate_box"],
                best["candidate_box_iou"],
            ):
                best = score
        row = dict(label)
        row["label_box_xyxy"] = round_box(row["label_box_xyxy"])
        if best is None:
            row.update(
                {
                    "matched": False,
                    "candidate_id": None,
                    "candidate_box_iou": 0.0,
                    "label_containment_in_candidate_box": 0.0,
                    "label_containment_in_crop": 0.0,
                }
            )
        else:
            row.update(best)
            row["matched"] = best["label_containment_in_crop"] >= 0.95 and (
                best["candidate_box_iou"] >= 0.15 or best["label_containment_in_candidate_box"] >= 0.75
            )
        audit_rows.append(row)

    ious = [row["candidate_box_iou"] for row in audit_rows]
    crop_containments = [row["label_containment_in_crop"] for row in audit_rows]
    candidate_containments = [row["label_containment_in_candidate_box"] for row in audit_rows]
    summary = {
        "manual_label_dir": str(labels_dir),
        "manual_labels": len(labels),
        "matched_labels": sum(1 for row in audit_rows if row["matched"]),
        "crop_contains_95_count": sum(1 for row in audit_rows if row["label_containment_in_crop"] >= 0.95),
        "candidate_contains_75_count": sum(
            1 for row in audit_rows if row["label_containment_in_candidate_box"] >= 0.75
        ),
        "iou_15_count": sum(1 for row in audit_rows if row["candidate_box_iou"] >= 0.15),
        "iou_25_count": sum(1 for row in audit_rows if row["candidate_box_iou"] >= 0.25),
        "median_iou": statistics.median(ious) if ious else 0.0,
        "median_crop_containment": statistics.median(crop_containments) if crop_containments else 0.0,
        "median_candidate_containment": statistics.median(candidate_containments) if candidate_containments else 0.0,
    }
    write_jsonl(output_dir / "manual_large_cloud_audit.jsonl", audit_rows)
    write_json(output_dir / "manual_large_cloud_audit_summary.json", summary)
    write_manual_audit_markdown(summary, audit_rows, output_dir / "manual_large_cloud_audit_summary.md")
    return summary


def write_summary_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Whole Cloud Candidate Export",
        "",
        f"Source grouped detections: `{summary['source_grouped_detections_dir']}`",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Totals",
        "",
        f"- pages: `{summary['totals']['pages']}`",
        f"- candidates: `{summary['totals']['candidates']}`",
        f"- high confidence: `{summary['totals']['confidence_tiers'].get('high', 0)}`",
        f"- medium confidence: `{summary['totals']['confidence_tiers'].get('medium', 0)}`",
        f"- low confidence: `{summary['totals']['confidence_tiers'].get('low', 0)}`",
        "",
        "## Size Buckets",
        "",
        "| Bucket | Count |",
        "| --- | ---: |",
    ]
    for bucket, count in sorted(summary["totals"]["size_buckets"].items()):
        lines.append(f"| `{bucket}` | `{count}` |")
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- manifest: `{Path(summary['manifest_path']).name}`",
            "- candidate crops: `crops/`",
            "- whole detection JSON: `detections_whole/`",
            "- debug overlays: `overlays/`",
            "- contact sheets: `contact_sheets/`",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manual_audit_markdown(summary: dict[str, Any], audit_rows: list[dict[str, Any]], output_path: Path) -> None:
    lines = [
        "# Manual Large Cloud Candidate Audit",
        "",
        f"Manual labels: `{summary['manual_labels']}`",
        f"Matched labels: `{summary['matched_labels']}`",
        f"Crop contains >=95%: `{summary['crop_contains_95_count']}`",
        f"Candidate box contains >=75%: `{summary['candidate_contains_75_count']}`",
        f"IoU >=0.25: `{summary['iou_25_count']}`",
        f"Median IoU: `{summary['median_iou']:.3f}`",
        f"Median crop containment: `{summary['median_crop_containment']:.3f}`",
        "",
        "## Weakest Manual Matches",
        "",
        "| Render | Region | Label | Matched | IoU | Candidate containment | Crop containment | Candidate |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | --- |",
    ]
    weakest = sorted(
        audit_rows,
        key=lambda row: (
            float(row.get("label_containment_in_crop", 0.0)),
            float(row.get("label_containment_in_candidate_box", 0.0)),
            float(row.get("candidate_box_iou", 0.0)),
        ),
    )[:25]
    for row in weakest:
        lines.append(
            f"| `{row['render_stem']}` | `{row['region_id']}` | `{row['label_index']}` | "
            f"`{row['matched']}` | `{row['candidate_box_iou']:.3f}` | "
            f"`{row['label_containment_in_candidate_box']:.3f}` | "
            f"`{row['label_containment_in_crop']:.3f}` | `{row.get('candidate_id')}` |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export whole-cloud candidate crops from grouped motif detections.")
    parser.add_argument(
        "--grouped-detections-dir",
        type=Path,
        default=ROOT / "runs" / "fragment_grouping_fullpage_all_broad_deduped_20260428" / "detections_grouped",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "runs" / "whole_cloud_candidates_broad_deduped_20260428",
    )
    parser.add_argument("--large-labels-dir", type=Path, default=ROOT / "data" / "large_cloud_context_labels_20260428")
    parser.add_argument("--crop-margin-ratio", type=float, default=0.12)
    parser.add_argument("--min-crop-margin", type=float, default=48.0)
    parser.add_argument("--max-crop-margin", type=float, default=650.0)
    parser.add_argument("--min-candidate-confidence", type=float, default=0.0)
    parser.add_argument("--min-box-side", type=float, default=20.0)
    parser.add_argument("--no-overlays", action="store_true")
    args = parser.parse_args()

    params = WholeCloudExportParams(
        crop_margin_ratio=args.crop_margin_ratio,
        min_crop_margin=args.min_crop_margin,
        max_crop_margin=args.max_crop_margin,
        min_candidate_confidence=args.min_candidate_confidence,
        min_box_side=args.min_box_side,
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    results = [
        process_grouped_file(path, output_dir, params, write_overlays=not args.no_overlays)
        for path in sorted(args.grouped_detections_dir.glob("*.json"))
    ]
    rows = [row for result in results for row in result["rows"]]
    pages = [page for result in results for page in result["pages"]]
    manifest_path = output_dir / "whole_cloud_candidates_manifest.jsonl"
    write_jsonl(manifest_path, rows)

    by_size = Counter(row["size_bucket"] for row in rows)
    by_tier = Counter(row["confidence_tier"] for row in rows)
    summary: dict[str, Any] = {
        "schema": "cloudhammer.whole_cloud_candidate_export.v1",
        "source_grouped_detections_dir": str(args.grouped_detections_dir.resolve()),
        "output_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "params": params.__dict__,
        "results": [{key: value for key, value in result.items() if key != "rows"} for result in results],
        "totals": {
            "pages": len(pages),
            "candidates": len(rows),
            "size_buckets": dict(by_size),
            "confidence_tiers": dict(by_tier),
        },
    }

    if rows:
        contact_dir = output_dir / "contact_sheets"
        write_contact_sheet(sorted(rows, key=lambda row: row["whole_cloud_confidence"], reverse=True)[:40], contact_dir / "top_confidence.png")
        write_contact_sheet(sorted(rows, key=lambda row: row["bbox_area"], reverse=True)[:40], contact_dir / "largest_candidates.png")
        write_contact_sheet(sorted(rows, key=lambda row: row["whole_cloud_confidence"])[:40], contact_dir / "lowest_confidence.png")
        for bucket in sorted(by_size):
            write_contact_sheet([row for row in rows if row["size_bucket"] == bucket][:40], contact_dir / f"{bucket}_sample.png")

    if args.large_labels_dir.exists():
        summary["manual_large_cloud_audit"] = audit_against_manual_labels(rows, args.large_labels_dir, output_dir)

    summary_path = output_dir / "whole_cloud_candidates_summary.json"
    write_json(summary_path, summary)
    write_summary_markdown(summary, output_dir / "whole_cloud_candidates_summary.md")

    print(f"wrote {manifest_path}")
    print(
        "pages={pages} candidates={candidates} sizes={sizes} tiers={tiers}".format(
            pages=summary["totals"]["pages"],
            candidates=summary["totals"]["candidates"],
            sizes=dict(by_size),
            tiers=dict(by_tier),
        )
    )
    if "manual_large_cloud_audit" in summary:
        audit = summary["manual_large_cloud_audit"]
        print(
            "manual_audit labels={labels} matched={matched} crop95={crop95}".format(
                labels=audit["manual_labels"],
                matched=audit["matched_labels"],
                crop95=audit["crop_contains_95_count"],
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

