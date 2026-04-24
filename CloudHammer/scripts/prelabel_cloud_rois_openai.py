from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.config import CloudHammerConfig
from cloudhammer.prelabel.openai_clouds import DEFAULT_MODEL, prelabel_cloud_rois


def main() -> int:
    parser = argparse.ArgumentParser(description="Use OpenAI vision to prelabel cloud_motif ROI crops.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--detail", choices=["low", "auto", "high"], default="auto")
    parser.add_argument("--max-dim", type=int, default=1024)
    parser.add_argument("--min-confidence", type=float, default=0.60)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--image-format", choices=["png", "jpeg", "webp"], default="png")
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--request-delay", type=float, default=0.5)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-initial-delay", type=float, default=2.0)
    parser.add_argument("--flush-every", type=int, default=25)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.max_dim < 256:
        parser.error("--max-dim must be at least 256")
    if not 0.0 <= args.min_confidence <= 1.0:
        parser.error("--min-confidence must be between 0 and 1")
    if args.request_delay < 0:
        parser.error("--request-delay must be non-negative")
    if args.max_retries < 0:
        parser.error("--max-retries must be non-negative")
    if args.retry_initial_delay < 0:
        parser.error("--retry-initial-delay must be non-negative")
    if args.flush_every < 1:
        parser.error("--flush-every must be at least 1")

    cfg = CloudHammerConfig.load(args.config)
    prelabel_cloud_rois(
        cfg,
        manifest_path=args.manifest,
        limit=args.limit,
        overwrite=args.overwrite,
        model=args.model,
        detail=args.detail,
        max_dim=args.max_dim,
        min_confidence=args.min_confidence,
        dry_run=args.dry_run,
        image_format=args.image_format,
        env_file=args.env_file,
        request_delay=args.request_delay,
        max_retries=args.max_retries,
        retry_initial_delay=args.retry_initial_delay,
        flush_every=args.flush_every,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
