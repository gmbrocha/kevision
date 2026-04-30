from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from ..revision_state.models import ChangeItem, CloudCandidate, RevisionSet, SheetVersion
from ..workspace import WorkspaceStore


@dataclass(frozen=True)
class ReviewPacketResult:
    html_path: Path
    item_count: int
    asset_count: int


def build_review_packet(store: WorkspaceStore, output_path: Path | None = None) -> ReviewPacketResult:
    """Build a local browser packet for reviewing CloudHammer workbook rows.

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
        for item in store.data.change_items
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

        crop_asset = _copy_crop_asset(cloud, asset_dir, index)
        context_asset = _write_context_asset(cloud, sheet, asset_dir, index)
        asset_count += int(crop_asset is not None) + int(context_asset is not None)

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


def _copy_crop_asset(cloud: CloudCandidate, asset_dir: Path, index: int) -> Path | None:
    source = Path(cloud.image_path)
    if not source.exists():
        return None
    destination = asset_dir / f"{index:04d}_{cloud.id}_crop{source.suffix.lower() or '.png'}"
    shutil.copyfile(source, destination)
    return destination


def _write_context_asset(cloud: CloudCandidate, sheet: SheetVersion, asset_dir: Path, index: int) -> Path | None:
    source = Path(cloud.page_image_path or sheet.render_path)
    if not source.exists():
        return None

    with Image.open(source) as page:
        page = page.convert("RGB")
        x, y, width, height = _normalized_bbox(cloud.bbox)
        if width <= 0 or height <= 0:
            return None

        pad = max(160, int(max(width, height) * 1.6))
        left = max(0, x - pad)
        top = max(0, y - pad)
        right = min(page.width, x + width + pad)
        bottom = min(page.height, y + height + pad)
        context = page.crop((left, top, right, bottom))

        draw = ImageDraw.Draw(context)
        rect = (x - left, y - top, x + width - left, y + height - top)
        line_width = max(4, round(max(context.width, context.height) / 180))
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
    grid-template-columns: minmax(220px, 0.85fr) minmax(360px, 1.5fr);
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
  <div class="subhead">{item_count} CloudHammer rows. Each item shows the exported crop and a marked source-page context crop.</div>
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
    context_asset: Path | None,
    metadata: dict[str, str],
    output_path: Path,
) -> str:
    revision_label = revision_set.label if revision_set else sheet.revision_set_id
    crop_img = _image_tag(crop_asset, output_path, "Exported crop")
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
      <figcaption>Workbook Crop</figcaption>
      {crop_img}
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
