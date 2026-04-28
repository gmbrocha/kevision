from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.config import CloudHammerConfig
from cloudhammer.manifests import read_jsonl, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
Image.MAX_IMAGE_PIXELS = None


def resolve_render_path(path: str, rasterized_pages_dir: Path) -> Path:
    render_path = Path(path)
    if render_path.exists():
        return render_path
    candidate = rasterized_pages_dir / render_path.name
    return candidate if candidate.exists() else render_path


def drawing_bounds(width: int, height: int, args: argparse.Namespace) -> tuple[int, int, int, int]:
    left = int(width * args.left_margin)
    top = int(height * args.top_margin)
    right = int(width * (1.0 - args.right_margin))
    bottom = int(height * (1.0 - args.bottom_margin))
    return left, top, right, bottom


def ink_ratio(image: Image.Image) -> float:
    grayscale = image.convert("L")
    histogram = grayscale.histogram()
    ink_pixels = sum(histogram[:245])
    return ink_pixels / max(1, grayscale.width * grayscale.height)


def page_group_key(row: dict) -> str:
    pdf_path = str(row.get("pdf_path") or "")
    if "Revision #" in pdf_path:
        return pdf_path.split("Revision #", 1)[1].split("\\", 1)[0].split("/", 1)[0]
    return str(row.get("pdf_stem") or "unknown")


def choose_pages(rows: list[dict], count: int, rng: random.Random) -> list[dict]:
    by_revision: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_revision[page_group_key(row)].append(row)
    for group_rows in by_revision.values():
        rng.shuffle(group_rows)

    groups = list(by_revision)
    rng.shuffle(groups)
    chosen = []
    group_index = 0
    while len(chosen) < count and groups:
        group = groups[group_index % len(groups)]
        chosen.append(rng.choice(by_revision[group]))
        group_index += 1
    return chosen


def make_crop_id(row: dict, crop_index: int) -> str:
    render_stem = Path(str(row["render_path"])).stem
    return f"{render_stem}_random_{crop_index:04d}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create random drawing-area crops for quick GPT/human spot checks.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--pages-manifest", type=Path, default=ROOT / "data" / "manifests" / "pages.jsonl")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "random_drawing_crops")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--crop-size", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=20260424)
    parser.add_argument("--min-ink-ratio", type=float, default=0.002)
    parser.add_argument("--max-attempts-per-crop", type=int, default=50)
    parser.add_argument("--left-margin", type=float, default=0.04)
    parser.add_argument("--right-margin", type=float, default=0.18)
    parser.add_argument("--top-margin", type=float, default=0.06)
    parser.add_argument("--bottom-margin", type=float, default=0.12)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.count <= 0:
        parser.error("--count must be positive")
    if args.crop_size <= 0:
        parser.error("--crop-size must be positive")
    if not 0.0 <= args.min_ink_ratio <= 1.0:
        parser.error("--min-ink-ratio must be between 0 and 1")

    cfg = CloudHammerConfig.load(args.config)
    rasterized_pages_dir = cfg.path("rasterized_pages")
    output_dir = args.output_dir
    images_dir = output_dir / "images"
    manifest_path = output_dir / "manifest.jsonl"
    csv_path = output_dir / "review_sheet.csv"

    if output_dir.exists() and not args.overwrite:
        raise FileExistsError(f"{output_dir} already exists; pass --overwrite to replace/add files")
    images_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    for row in read_jsonl(args.pages_manifest):
        if row.get("page_kind") != "drawing":
            continue
        render_path = resolve_render_path(str(row["render_path"]), rasterized_pages_dir)
        if render_path.exists():
            row = dict(row)
            row["render_path"] = str(render_path)
            pages.append(row)

    if not pages:
        raise RuntimeError(f"No drawing pages with rasterized images found in {args.pages_manifest}")

    rng = random.Random(args.seed)
    selected_pages = choose_pages(pages, args.count, rng)
    rows_out = []

    for index, row in enumerate(selected_pages, start=1):
        render_path = Path(row["render_path"])
        with Image.open(render_path) as page_image:
            page_image.load()
            width, height = page_image.size
            left, top, right, bottom = drawing_bounds(width, height, args)
            if right - left < args.crop_size or bottom - top < args.crop_size:
                left, top, right, bottom = 0, 0, width, height

            crop = None
            crop_box = None
            crop_ink_ratio = 0.0
            for _ in range(args.max_attempts_per_crop):
                x1 = rng.randint(left, max(left, right - args.crop_size))
                y1 = rng.randint(top, max(top, bottom - args.crop_size))
                candidate_box = (x1, y1, x1 + args.crop_size, y1 + args.crop_size)
                candidate = page_image.crop(candidate_box)
                candidate_ink_ratio = ink_ratio(candidate)
                if candidate_ink_ratio >= args.min_ink_ratio:
                    crop = candidate
                    crop_box = candidate_box
                    crop_ink_ratio = candidate_ink_ratio
                    break
                crop = candidate
                crop_box = candidate_box
                crop_ink_ratio = candidate_ink_ratio

            assert crop is not None and crop_box is not None
            crop_id = make_crop_id(row, index)
            output_path = images_dir / f"{crop_id}.png"
            crop.save(output_path)
            x1, y1, x2, y2 = crop_box
            rows_out.append(
                {
                    "cloud_roi_id": crop_id,
                    "random_crop_id": crop_id,
                    "image_path": str(output_path.resolve()),
                    "roi_image_path": str(output_path.resolve()),
                    "render_path": str(render_path.resolve()),
                    "pdf_path": row.get("pdf_path", ""),
                    "pdf_stem": row.get("pdf_stem", ""),
                    "page_index": row.get("page_index", ""),
                    "page_number": row.get("page_number", ""),
                    "sheet_id": row.get("sheet_id", ""),
                    "sheet_title": row.get("sheet_title", ""),
                    "crop_box_page": [x1, y1, x2, y2],
                    "crop_size": args.crop_size,
                    "ink_ratio": round(crop_ink_ratio, 6),
                    "human_quick_label": "",
                    "human_notes": "",
                }
            )

    write_jsonl(manifest_path, rows_out)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "random_crop_id",
            "image_path",
            "sheet_id",
            "sheet_title",
            "page_number",
            "ink_ratio",
            "human_quick_label",
            "human_notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows_out:
            writer.writerow({field: row.get(field, "") for field in fieldnames})

    summary = {
        "count": len(rows_out),
        "crop_size": args.crop_size,
        "seed": args.seed,
        "output_dir": str(output_dir.resolve()),
        "images_dir": str(images_dir.resolve()),
        "manifest": str(manifest_path.resolve()),
        "review_sheet": str(csv_path.resolve()),
        "drawing_area_margins": {
            "left": args.left_margin,
            "right": args.right_margin,
            "top": args.top_margin,
            "bottom": args.bottom_margin,
        },
        "min_ink_ratio": args.min_ink_ratio,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
