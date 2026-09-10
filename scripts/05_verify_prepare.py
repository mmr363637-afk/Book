#!/usr/bin/env python3
"""Stage 05 — Verification prep (per page).

Creates high-detail crops of the page image for the agent's verification
pass: full view (existing), plus three horizontal bands re-rendered at a
higher DPI for close reading of small print, tables, options, numbers.

Outputs: qa/verify/page_NNN/band_{top,mid,bottom}.jpg

Usage: python3 scripts/05_verify_prepare.py --page 12
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config, manifest, paths  # noqa: E402
import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--dpi", type=int, default=240)
    args = ap.parse_args()

    if manifest.get(args.page) is None:
        raise SystemExit(f"page {args.page} unknown in manifest")

    cfg = config.load_book_config()
    src = paths.ROOT / cfg["book"]["source_pdf"]

    outdir = paths.VERIFY / f"page_{args.page:03d}"
    outdir.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(src)
    page = doc[args.page - 1]
    rect = page.rect
    h = rect.height / 3
    bands = {
        "top": pymupdf.Rect(0, 0, rect.width, h + 6),
        "mid": pymupdf.Rect(0, h - 6, rect.width, 2 * h + 6),
        "bottom": pymupdf.Rect(0, 2 * h - 6, rect.width, rect.height),
    }
    zoom = args.dpi / 72.0
    for name, clip in bands.items():
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img.save(outdir / f"band_{name}.jpg", "JPEG", quality=85)
        del pix, img
    doc.close()
    print(f"verification crops ready: {outdir}")


if __name__ == "__main__":
    main()
