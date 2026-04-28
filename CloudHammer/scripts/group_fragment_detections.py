from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.contracts.detections import DetectionPage, load_detection_manifest, write_detection_manifest
from cloudhammer.infer.fragment_grouping import GroupingParams, grouping_summary, group_fragment_detections


ROOT = Path(__file__).resolve().parents[1]


def draw_group_overlay(image, fragments, groups, output_path: Path) -> None:
    if len(image.shape) == 2:
        overlay = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        overlay = image.copy()

    for index, det in enumerate(fragments, start=1):
        x, y, w, h = [int(round(v)) for v in det.bbox_page]
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (170, 170, 170), 3)
        cv2.putText(
            overlay,
            str(index),
            (x, max(20, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (120, 120, 120),
            2,
            cv2.LINE_AA,
        )

    for index, det in enumerate(groups, start=1):
        x, y, w, h = [int(round(v)) for v in det.bbox_page]
        member_count = int(det.metadata.get("member_count", 1))
        color = (0, 130, 255) if member_count > 1 else (0, 190, 0)
        thickness = 8 if member_count > 1 else 4
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, thickness)
        cv2.putText(
            overlay,
            f"G{index} n={member_count} {det.confidence:.2f}",
            (x, max(28, y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            color,
            3,
            cv2.LINE_AA,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), overlay)


def overlay_name_for(page: DetectionPage) -> str:
    if page.detections and page.detections[0].crop_path:
        crop_stem = Path(page.detections[0].crop_path).stem
        base = crop_stem.rsplit("_cloud_", 1)[0]
        return f"{base}_grouped.png"
    return f"{Path(page.pdf).stem}_p{page.page:04d}_grouped.png"


def process_detection_file(det_path: Path, output_dir: Path, params: GroupingParams) -> dict:
    pages = load_detection_manifest(det_path)
    grouped_pages: list[DetectionPage] = []
    page_summaries = []
    for page in pages:
        if not page.render_path:
            continue
        image = cv2.imread(page.render_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            continue
        height, width = image.shape[:2]
        groups = group_fragment_detections(page.detections, width, height, params)
        grouped_pages.append(
            DetectionPage(
                pdf=page.pdf,
                page=page.page,
                detections=groups,
                render_path=page.render_path,
            )
        )
        overlay_path = output_dir / "overlays" / overlay_name_for(page)
        draw_group_overlay(image, page.detections, groups, overlay_path)
        page_summary = grouping_summary(page.detections, groups)
        page_summary.update(
            {
                "pdf": page.pdf,
                "pdf_stem": det_path.stem,
                "page": page.page,
                "render_path": page.render_path,
                "overlay_path": str(overlay_path),
            }
        )
        page_summaries.append(page_summary)

    grouped_json = output_dir / "detections_grouped" / det_path.name
    write_detection_manifest(grouped_json, grouped_pages, model=f"grouped_from:{det_path}")
    return {
        "source_detection_json": str(det_path),
        "grouped_detection_json": str(grouped_json),
        "pages": page_summaries,
    }


def write_markdown_summary(summary: dict, path: Path) -> None:
    lines = [
        "# Fragment Grouping Summary",
        "",
        f"Source detections: `{summary['source_dir']}`",
        f"Output dir: `{summary['output_dir']}`",
        "",
        f"Pages: `{summary['totals']['pages']}`",
        f"Fragments: `{summary['totals']['fragments']}`",
        f"Grouped candidates: `{summary['totals']['groups']}`",
        f"Multi-fragment groups: `{summary['totals']['multi_fragment_groups']}`",
        "",
        "## By Page",
        "",
        "| Source | Page | Fragments | Groups | Multi-fragment groups | Largest group | Overlay |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for page in summary["pages"]:
        lines.append(
            f"| `{page['pdf_stem']}` | `{page['page']}` | `{page['fragment_count']}` | "
            f"`{page['group_count']}` | `{page['multi_fragment_group_count']}` | "
            f"`{page['largest_group_member_count']}` | `{Path(page['overlay_path']).name}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Group full-page cloud motif fragments into whole-cloud candidates.")
    parser.add_argument(
        "--detections-dir",
        type=Path,
        default=ROOT / "runs" / "fullpage_eval_broad_deduped_20260428" / "outputs" / "detections",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "runs" / "fragment_grouping_broad_deduped_20260428",
    )
    parser.add_argument("--expansion-ratio", type=float, default=0.55)
    parser.add_argument("--min-padding", type=float, default=120.0)
    parser.add_argument("--max-padding", type=float, default=850.0)
    parser.add_argument("--group-margin-ratio", type=float, default=0.08)
    parser.add_argument("--min-group-margin", type=float, default=25.0)
    parser.add_argument("--max-group-margin", type=float, default=350.0)
    parser.add_argument("--split-min-members", type=int, default=7)
    parser.add_argument("--split-min-partition-members", type=int, default=3)
    parser.add_argument("--split-gap-ratio", type=float, default=0.16)
    parser.add_argument("--split-min-gap", type=float, default=550.0)
    parser.add_argument("--split-max-fill-ratio", type=float, default=0.28)
    parser.add_argument("--overmerge-refinement", action="store_true")
    parser.add_argument(
        "--overmerge-refinement-profile",
        choices=["very_tight", "tight", "balanced", "review_v1"],
        default="review_v1",
    )
    parser.add_argument("--overmerge-refine-min-members", type=int, default=9)
    parser.add_argument("--overmerge-refine-max-fill-ratio", type=float, default=0.15)
    args = parser.parse_args()

    params = GroupingParams(
        expansion_ratio=args.expansion_ratio,
        min_padding=args.min_padding,
        max_padding=args.max_padding,
        group_margin_ratio=args.group_margin_ratio,
        min_group_margin=args.min_group_margin,
        max_group_margin=args.max_group_margin,
        split_min_members=args.split_min_members,
        split_min_partition_members=args.split_min_partition_members,
        split_gap_ratio=args.split_gap_ratio,
        split_min_gap=args.split_min_gap,
        split_max_fill_ratio=args.split_max_fill_ratio,
        overmerge_refinement_enabled=args.overmerge_refinement,
        overmerge_refinement_profile=args.overmerge_refinement_profile,
        overmerge_refine_min_members=args.overmerge_refine_min_members,
        overmerge_refine_max_fill_ratio=args.overmerge_refine_max_fill_ratio,
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    results = [
        process_detection_file(det_path, output_dir, params)
        for det_path in sorted(args.detections_dir.glob("*.json"))
    ]
    pages = [page for result in results for page in result["pages"]]
    summary = {
        "source_dir": str(args.detections_dir.resolve()),
        "output_dir": str(output_dir),
        "params": params.__dict__,
        "results": results,
        "pages": pages,
        "totals": {
            "pages": len(pages),
            "fragments": sum(page["fragment_count"] for page in pages),
            "groups": sum(page["group_count"] for page in pages),
            "multi_fragment_groups": sum(page["multi_fragment_group_count"] for page in pages),
        },
    }
    summary_path = output_dir / "fragment_grouping_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown_summary(summary, output_dir / "fragment_grouping_summary.md")

    print(f"wrote {summary_path}")
    print(
        "pages={pages} fragments={fragments} groups={groups} multi_fragment_groups={multi}".format(
            pages=summary["totals"]["pages"],
            fragments=summary["totals"]["fragments"],
            groups=summary["totals"]["groups"],
            multi=summary["totals"]["multi_fragment_groups"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
