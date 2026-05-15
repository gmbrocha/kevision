from __future__ import annotations

import html
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from ..crop_adjustments import build_selected_review_overlay_image, selected_review_page_boxes
from ..review_queue import visible_change_items
from ..revision_state.models import ChangeItem, CloudCandidate, RevisionSet, SheetVersion
from ..workspace import WorkspaceStore
from .crop_comparison import build_cloud_comparison_image, find_previous_sheet_version


@dataclass(frozen=True)
class ReviewPacketResult:
    html_path: Path
    item_count: int
    asset_count: int


def build_review_packet(store: WorkspaceStore, output_path: Path | None = None) -> ReviewPacketResult:
    """Build a local browser packet for reviewing detected-region workbook rows.

    The workbook is still the canonical deliverable. This packet is a speed aid:
    it places each exported cloud crop next to a marked source-page context crop
    so the reviewer does not need to flip between Excel and the source PDF.
    """

    output_path = output_path or store.output_dir / "revision_changelog_review_packet.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    asset_dir = output_path.parent / f"{output_path.stem}_assets"
    asset_dir.mkdir(parents=True, exist_ok=True)

    sheets_by_id = {sheet.id: sheet for sheet in store.data.sheets}
    clouds_by_id = {cloud.id: cloud for cloud in store.data.clouds}
    revision_sets_by_id = {revision_set.id: revision_set for revision_set in store.data.revision_sets}

    items = [
        item
        for item in visible_change_items(store.data.change_items)
        if item.cloud_candidate_id
        and item.status == "approved"
        and item.provenance.get("extraction_method") == "cloudhammer_manifest"
    ]
    items.sort(key=lambda item: _sort_key(item, sheets_by_id, revision_sets_by_id))

    cards: list[str] = []
    asset_count = 0
    for index, item in enumerate(items, start=1):
        cloud = clouds_by_id.get(item.cloud_candidate_id or "")
        sheet = sheets_by_id.get(item.sheet_version_id)
        if not cloud or not sheet:
            continue

        crop_asset = _write_selected_crop_asset(store, item, cloud, asset_dir, index)
        comparison_asset = _write_comparison_asset(store, item, cloud, sheet, sheets_by_id, revision_sets_by_id, asset_dir, index)
        context_asset = _write_context_asset(item, cloud, sheet, asset_dir, index)
        asset_count += int(crop_asset is not None) + int(comparison_asset is not None) + int(context_asset is not None)

        revision_set = revision_sets_by_id.get(sheet.revision_set_id)
        metadata = _cloudhammer_metadata(item)
        cards.append(
            _render_card(
                index=index,
                item=item,
                cloud=cloud,
                sheet=sheet,
                revision_set=revision_set,
                crop_asset=crop_asset,
                comparison_asset=comparison_asset,
                context_asset=context_asset,
                metadata=metadata,
                output_path=output_path,
            )
        )

    output_path.write_text(_render_page(cards, item_count=len(cards)), encoding="utf-8")
    return ReviewPacketResult(html_path=output_path, item_count=len(cards), asset_count=asset_count)


def _sort_key(
    item: ChangeItem,
    sheets_by_id: dict[str, SheetVersion],
    revision_sets_by_id: dict[str, RevisionSet],
) -> tuple[int, str, int, str]:
    sheet = sheets_by_id.get(item.sheet_version_id)
    revision_set_number = 0
    page_number = 0
    sheet_id = item.sheet_id
    if sheet:
        page_number = sheet.page_number
        sheet_id = sheet.sheet_id
        revision_set = revision_sets_by_id.get(sheet.revision_set_id)
        if revision_set:
            revision_set_number = revision_set.set_number
    return (revision_set_number, sheet_id, page_number, item.id)


def _write_selected_crop_asset(store: WorkspaceStore, item: ChangeItem, cloud: CloudCandidate, asset_dir: Path, index: int) -> Path | None:
    destination = asset_dir / f"{index:04d}_{cloud.id}_selected.png"
    generated = build_selected_review_overlay_image(store, item, cloud, destination, include_all=False)
    if generated:
        if generated.resolve() != destination.resolve():
            shutil.copyfile(generated, destination)
            return destination
        return generated
    source = store.resolve_path(cloud.image_path)
    if not source.exists():
        return None
    shutil.copyfile(source, destination)
    return destination


def _write_comparison_asset(
    store: WorkspaceStore,
    item: ChangeItem,
    cloud: CloudCandidate,
    sheet: SheetVersion,
    sheets_by_id: dict[str, SheetVersion],
    revision_sets_by_id: dict[str, RevisionSet],
    asset_dir: Path,
    index: int,
) -> Path | None:
    previous_sheet = find_previous_sheet_version(sheet, list(sheets_by_id.values()), revision_sets_by_id)
    destination = asset_dir / f"{index:04d}_{cloud.id}_comparison.png"
    selected_boxes = selected_review_page_boxes(item, cloud)
    return build_cloud_comparison_image(
        store,
        cloud=cloud,
        current_sheet=sheet,
        previous_sheet=previous_sheet,
        output_path=destination,
        highlight_bboxes=selected_boxes or None,
    )


def _write_context_asset(item: ChangeItem, cloud: CloudCandidate, sheet: SheetVersion, asset_dir: Path, index: int) -> Path | None:
    source = Path(cloud.page_image_path or sheet.render_path)
    if not source.exists():
        return None

    with Image.open(source) as page:
        page = page.convert("RGB")
        selected_boxes = selected_review_page_boxes(item, cloud)
        normalized_boxes = [
            _scale_bbox_to_image(_normalized_bbox(box), page.size, sheet)
            for box in selected_boxes
        ]
        normalized_boxes = [box for box in normalized_boxes if box[2] > 0 and box[3] > 0]
        if not normalized_boxes:
            return None
        x = min(box[0] for box in normalized_boxes)
        y = min(box[1] for box in normalized_boxes)
        right_box = max(box[0] + box[2] for box in normalized_boxes)
        bottom_box = max(box[1] + box[3] for box in normalized_boxes)
        width = right_box - x
        height = bottom_box - y
        if width <= 0 or height <= 0:
            return None

        pad = max(160, int(max(width, height) * 1.6))
        left = max(0, x - pad)
        top = max(0, y - pad)
        right = min(page.width, x + width + pad)
        bottom = min(page.height, y + height + pad)
        context = page.crop((left, top, right, bottom))

        draw = ImageDraw.Draw(context)
        line_width = max(4, round(max(context.width, context.height) / 180))
        for box in normalized_boxes:
            rect = (box[0] - left, box[1] - top, box[0] + box[2] - left, box[1] + box[3] - top)
            for offset in range(line_width):
                draw.rectangle(
                    (
                        rect[0] - offset,
                        rect[1] - offset,
                        rect[2] + offset,
                        rect[3] + offset,
                    ),
                    outline=(0, 180, 70),
                )

        destination = asset_dir / f"{index:04d}_{cloud.id}_context.png"
        context.save(destination, optimize=True)
        return destination


def _normalized_bbox(values: list[int]) -> tuple[int, int, int, int]:
    if len(values) < 4:
        return (0, 0, 0, 0)
    x, y, width, height = [int(value) for value in values[:4]]
    if width < 0:
        x += width
        width = abs(width)
    if height < 0:
        y += height
        height = abs(height)
    return (x, y, width, height)


def _scale_bbox_to_image(
    box: tuple[int, int, int, int],
    image_size: tuple[int, int],
    sheet: SheetVersion,
) -> tuple[int, int, int, int]:
    image_width, image_height = image_size
    sheet_width = float(sheet.width or image_width or 1)
    sheet_height = float(sheet.height or image_height or 1)
    scale_x = image_width / sheet_width if sheet_width else 1.0
    scale_y = image_height / sheet_height if sheet_height else 1.0
    x, y, width, height = box
    left = max(0, min(image_width, math.floor(x * scale_x)))
    top = max(0, min(image_height, math.floor(y * scale_y)))
    right = max(0, min(image_width, math.ceil((x + width) * scale_x)))
    bottom = max(0, min(image_height, math.ceil((y + height) * scale_y)))
    return (left, top, max(0, right - left), max(0, bottom - top))


def _parse_cloudhammer_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for key in ("candidate", "policy", "review", "confidence"):
        match = re.search(rf"{key}=([^;]+)", text)
        if match:
            metadata[key] = match.group(1).strip()
    return metadata


def _cloudhammer_metadata(item: ChangeItem) -> dict[str, str]:
    metadata = _parse_cloudhammer_metadata(item.raw_text)
    provenance = item.provenance or {}
    mapping = {
        "candidate": "cloudhammer_candidate_id",
        "policy": "policy_bucket",
        "review": "review_status",
        "confidence": "cloud_confidence",
    }
    for display_key, provenance_key in mapping.items():
        if display_key in metadata:
            continue
        value = provenance.get(provenance_key)
        if value not in (None, ""):
            metadata[display_key] = str(value)
    return metadata


def _render_page(cards: list[str], *, item_count: int) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ScopeLedger Review Packet</title>
<style>
  body {{
    margin: 0;
    background: #f5f5f3;
    color: #171717;
    font-family: Arial, Helvetica, sans-serif;
  }}
  header {{
    position: sticky;
    top: 0;
    z-index: 2;
    padding: 14px 18px;
    border-bottom: 1px solid #cfcfca;
    background: #ffffff;
  }}
  h1 {{
    margin: 0;
    font-size: 18px;
    font-weight: 700;
  }}
  .subhead {{
    margin-top: 4px;
    color: #555;
    font-size: 13px;
  }}
  main {{
    display: grid;
    gap: 16px;
    padding: 16px;
  }}
  article {{
    border: 1px solid #c9c9c3;
    border-radius: 6px;
    background: #fff;
    overflow: hidden;
  }}
  .meta {{
    display: grid;
    grid-template-columns: repeat(5, minmax(120px, 1fr));
    gap: 8px 14px;
    padding: 12px 14px;
    border-bottom: 1px solid #deded9;
    font-size: 13px;
  }}
  .label {{
    display: block;
    color: #666;
    font-size: 11px;
    line-height: 1.4;
    text-transform: uppercase;
  }}
  .value {{
    font-weight: 700;
  }}
  .images {{
    display: grid;
    grid-template-columns: minmax(220px, 0.8fr) minmax(360px, 1.35fr) minmax(360px, 1.35fr);
    gap: 12px;
    align-items: start;
    padding: 12px;
  }}
  figure {{
    margin: 0;
  }}
  figcaption {{
    margin-bottom: 6px;
    color: #555;
    font-size: 12px;
    font-weight: 700;
  }}
  img {{
    display: block;
    max-width: 100%;
    height: auto;
    border: 1px solid #d4d4cf;
    background: #fafafa;
  }}
  .text {{
    padding: 0 14px 14px;
    color: #333;
    font-size: 12px;
    line-height: 1.35;
    word-break: break-word;
  }}
  a {{
    color: #1459a8;
  }}
  @media (max-width: 900px) {{
    .meta, .images {{
      grid-template-columns: 1fr;
    }}
  }}
</style>
</head>
<body>
<header>
  <h1>ScopeLedger Review Packet</h1>
  <div class="subhead">{item_count} detected rows. Each item shows selected visual evidence, previous/current comparison, and marked source-page context.</div>
</header>
<main>
{''.join(cards)}
</main>
</body>
</html>
"""


def _render_card(
    *,
    index: int,
    item: ChangeItem,
    cloud: CloudCandidate,
    sheet: SheetVersion,
    revision_set: RevisionSet | None,
    crop_asset: Path | None,
    comparison_asset: Path | None,
    context_asset: Path | None,
    metadata: dict[str, str],
    output_path: Path,
) -> str:
    revision_label = revision_set.label if revision_set else sheet.revision_set_id
    crop_img = _image_tag(crop_asset, output_path, "Exported crop")
    comparison_img = _image_tag(comparison_asset, output_path, "Previous and current comparison")
    context_img = _image_tag(context_asset, output_path, "Source-page context")
    candidate = metadata.get("candidate", cloud.id)
    policy = metadata.get("policy", "")
    review = metadata.get("review", "")
    confidence = metadata.get("confidence", f"{cloud.confidence:.3f}")
    source_pdf = Path(sheet.source_pdf).name if sheet.source_pdf else ""

    return f"""<article id="row-{index:04d}">
  <div class="meta">
    {_meta_cell("Row", str(index))}
    {_meta_cell("Sheet", _display_sheet_id(sheet.sheet_id))}
    {_meta_cell("Revision Set", revision_label)}
    {_meta_cell("Page", str(sheet.page_number))}
    {_meta_cell("Confidence", confidence)}
    {_meta_cell("Policy", policy)}
    {_meta_cell("Review", review)}
    {_meta_cell("Candidate", candidate)}
    {_meta_cell("Source PDF", source_pdf)}
    {_meta_cell("Cloud ID", cloud.id)}
  </div>
  <div class="images">
    <figure>
      <figcaption>Selected Evidence</figcaption>
      {crop_img}
    </figure>
    <figure>
      <figcaption>Previous / Current</figcaption>
      {comparison_img}
    </figure>
    <figure>
      <figcaption>Source Context</figcaption>
      {context_img}
    </figure>
  </div>
  <div class="text">{html.escape(item.reviewer_text or item.raw_text)}</div>
</article>
"""


def _meta_cell(label: str, value: str) -> str:
    return f"<div><span class=\"label\">{html.escape(label)}</span><span class=\"value\">{html.escape(value or '-')}</span></div>"


def _image_tag(path: Path | None, output_path: Path, alt: str) -> str:
    if not path:
        return "<div>Image unavailable</div>"
    relative = path.relative_to(output_path.parent).as_posix()
    return f"<a href=\"{html.escape(relative)}\"><img src=\"{html.escape(relative)}\" alt=\"{html.escape(alt)}\"></a>"


def _display_sheet_id(sheet_id: str) -> str:
    match = re.match(r"^([A-Z]+)(\d.*)$", sheet_id)
    if not match:
        return sheet_id
    return f"{match.group(1)}-{match.group(2)}"
