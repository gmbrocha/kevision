from __future__ import annotations

import shutil
from pathlib import Path

from cloudhammer.config import CloudHammerConfig


def copy_unreviewed_labels_for_labelimg(
    cfg: CloudHammerConfig,
    source_dir: str | Path | None = None,
    reviewed_dir: str | Path | None = None,
    overwrite: bool = False,
    class_name: str = "cloud_motif",
) -> dict[str, int]:
    src = Path(source_dir) if source_dir is not None else cfg.path("api_cloud_labels_unreviewed")
    dst = Path(reviewed_dir) if reviewed_dir is not None else cfg.path("cloud_labels_reviewed")
    src = src.resolve()
    dst = dst.resolve()
    dst.mkdir(parents=True, exist_ok=True)
    dst.joinpath("classes.txt").write_text(f"{class_name}\n", encoding="utf-8")

    copied = 0
    skipped = 0
    for label_path in sorted(src.glob("*.txt")):
        out_path = dst / label_path.name
        if out_path.exists() and not overwrite:
            skipped += 1
            continue
        shutil.copy2(label_path, out_path)
        copied += 1

    return {"copied": copied, "skipped": skipped, "source_count": len(list(src.glob("*.txt")))}
