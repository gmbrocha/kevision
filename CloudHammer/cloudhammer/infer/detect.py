from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import cv2

from cloudhammer.config import CloudHammerConfig
from cloudhammer.contracts.detections import CloudDetection, DetectionPage, clip_xywh, write_detection_manifest
from cloudhammer.infer.merge import nms_detections
from cloudhammer.infer.tiles import generate_tiles, tile_xyxy_to_page_xywh
from cloudhammer.infer.visualize import draw_overlay, save_crops
from cloudhammer.manifests import read_jsonl
from cloudhammer.page_catalog import stable_page_key
from cloudhammer.runtime import configure_local_artifact_cache


CLOUDHAMMER_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = CLOUDHAMMER_ROOT.parent


def resolve_project_path(value: str | Path | None) -> Path:
    if value is None or str(value) == "":
        return Path("")
    candidate = Path(value)
    if candidate.exists():
        return candidate.resolve()
    parts = candidate.parts
    for anchor, root in (("CloudHammer", CLOUDHAMMER_ROOT), ("revision_sets", REPO_ROOT / "revision_sets")):
        for index, part in enumerate(parts):
            if part.lower() == anchor.lower():
                relocated = root.joinpath(*parts[index + 1 :])
                if relocated.exists():
                    return relocated.resolve()
    return candidate


def _load_yolo(cfg: CloudHammerConfig, model_path: str | Path):
    configure_local_artifact_cache(cfg)
    try:
        from ultralytics import YOLO  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("ultralytics is not installed. Install requirements-train.txt to run inference.") from exc
    return YOLO(str(model_path))


def infer_page_image(
    model,
    image_path: str | Path,
    tile_size: int,
    tile_overlap: int,
    confidence_threshold: float,
    nms_iou: float,
) -> list[CloudDetection]:
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(f"Could not read rendered page: {image_path}")
    height, width = image.shape[:2]
    detections: list[CloudDetection] = []
    for tile in generate_tiles(width, height, tile_size, tile_overlap):
        crop = image[tile.y : tile.y + tile.height, tile.x : tile.x + tile.width]
        crop_bgr = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        results = model.predict(source=crop_bgr, conf=confidence_threshold, verbose=False)
        if not results:
            continue
        boxes = getattr(results[0], "boxes", None)
        if boxes is None:
            continue
        for box in boxes:
            xyxy = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            bbox_page = clip_xywh(tile_xyxy_to_page_xywh(tile, tuple(float(v) for v in xyxy)), width, height)
            detections.append(
                CloudDetection(
                    confidence=conf,
                    bbox_page=bbox_page,
                    crop_path=None,
                    source_mode="page_tile",
                )
            )
    return nms_detections(detections, nms_iou)


def infer_pages_from_manifest(
    cfg: CloudHammerConfig,
    model_path: str | Path,
    pages_manifest: str | Path | None = None,
    limit: int | None = None,
    only_pdf_stem: str | None = None,
) -> dict[str, Path]:
    cfg.ensure_directories()
    model = _load_yolo(cfg, model_path)
    manifest = Path(pages_manifest) if pages_manifest is not None else cfg.path("manifests") / "pages.jsonl"
    outputs: dict[str, list[DetectionPage]] = defaultdict(list)
    processed = 0
    for row in read_jsonl(manifest):
        if row.get("page_kind") != "drawing":
            continue
        if only_pdf_stem and only_pdf_stem.lower() not in str(row.get("pdf_stem", "")).lower():
            continue
        render_path = resolve_project_path(row.get("render_path"))
        if not render_path or not render_path.exists():
            continue
        if limit is not None and processed >= limit:
            break
        detections = infer_page_image(
            model,
            render_path,
            tile_size=int(cfg.data["inference"]["tile_size"]),
            tile_overlap=int(cfg.data["inference"]["tile_overlap"]),
            confidence_threshold=float(cfg.data["inference"]["confidence_threshold"]),
            nms_iou=float(cfg.data["inference"]["nms_iou"]),
        )
        pdf_path = resolve_project_path(row.get("pdf_path"))
        key = stable_page_key(pdf_path, int(row["page_index"]))
        image = cv2.imread(str(render_path), cv2.IMREAD_GRAYSCALE)
        save_crops(image, detections, cfg.path("outputs") / "crops", key)
        draw_overlay(image, detections, cfg.path("outputs") / "overlays" / f"{key}_clouds.png")
        outputs[str(row["pdf_stem"])].append(
            DetectionPage(
                pdf=str(pdf_path),
                page=int(row["page_number"]),
                detections=detections,
                render_path=str(render_path),
            )
        )
        processed += 1

    written: dict[str, Path] = {}
    for pdf_stem, pages in outputs.items():
        out_path = cfg.path("outputs") / "detections" / f"{pdf_stem}.json"
        write_detection_manifest(out_path, pages, model=str(model_path))
        written[pdf_stem] = out_path
    return written
