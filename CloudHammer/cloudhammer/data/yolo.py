from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from cloudhammer.manifests import read_jsonl


CLASS_NAME = "cloud_motif"
ALLOWED_CLASS_IDS = {"0"}


def _convert_voc_xml_to_yolo(xml_path: Path, output_path: Path) -> None:
    root = ET.parse(xml_path).getroot()
    size = root.find("size")
    if size is None:
        raise ValueError(f"VOC XML missing size block: {xml_path}")
    width = float(size.findtext("width") or 0)
    height = float(size.findtext("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError(f"VOC XML has invalid image size: {xml_path}")
    lines: list[str] = []
    for obj in root.findall("object"):
        label_name = (obj.findtext("name") or "").strip()
        if label_name and label_name != CLASS_NAME:
            continue
        bnd = obj.find("bndbox")
        if bnd is None:
            continue
        xmin = float(bnd.findtext("xmin") or 0)
        ymin = float(bnd.findtext("ymin") or 0)
        xmax = float(bnd.findtext("xmax") or 0)
        ymax = float(bnd.findtext("ymax") or 0)
        cx = ((xmin + xmax) / 2.0) / width
        cy = ((ymin + ymax) / 2.0) / height
        bw = max(0.0, xmax - xmin) / width
        bh = max(0.0, ymax - ymin) / height
        lines.append(f"0 {cx:.8f} {cy:.8f} {bw:.8f} {bh:.8f}")
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _validate_and_copy_yolo_txt(label_path: Path, output_path: Path) -> None:
    lines_out: list[str] = []
    for line_number, raw_line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid YOLO label line {line_number} in {label_path}: expected 5 fields")
        if parts[0] not in ALLOWED_CLASS_IDS:
            raise ValueError(
                f"Unsupported class id {parts[0]!r} in {label_path}; "
                f"CloudHammer supports only class 0 ({CLASS_NAME})"
            )
        for value in parts[1:]:
            coordinate = float(value)
            if not 0.0 <= coordinate <= 1.0:
                raise ValueError(f"YOLO coordinate out of range in {label_path}: {line}")
        lines_out.append(" ".join(parts))
    output_path.write_text("\n".join(lines_out) + ("\n" if lines_out else ""), encoding="utf-8")


def _write_label(label_path: Path | None, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if label_path is None or not label_path.exists():
        output_path.write_text("", encoding="utf-8")
        return
    if label_path.suffix.lower() == ".xml":
        _convert_voc_xml_to_yolo(label_path, output_path)
        return
    if label_path.suffix.lower() == ".txt":
        _validate_and_copy_yolo_txt(label_path, output_path)
        return
    raise ValueError(f"Unsupported label format: {label_path}")


def build_yolo_dataset(roi_manifest_path: str | Path, dataset_dir: str | Path) -> Path:
    out_dir = Path(dataset_dir)
    for split in ("train", "val", "test"):
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    for row in read_jsonl(roi_manifest_path):
        if row.get("is_excluded"):
            continue
        split = row.get("split") or "train"
        if split not in {"train", "val", "test"}:
            split = "train"
        image_path = Path(row["roi_image_path"])
        if not image_path.exists():
            continue
        image_out = out_dir / "images" / split / image_path.name
        shutil.copy2(image_path, image_out)
        label_path = Path(row["label_path"]) if row.get("label_path") else None
        label_out = out_dir / "labels" / split / f"{image_path.stem}.txt"
        _write_label(label_path, label_out)

    data_yaml = out_dir / "cloudhammer.yaml"
    data_yaml.write_text(
        "\n".join(
            [
                f"path: {out_dir.resolve()}",
                "train: images/train",
                "val: images/val",
                "test: images/test",
                "names:",
                f"  0: {CLASS_NAME}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return data_yaml
