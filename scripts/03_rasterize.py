#!/usr/bin/env python3
"""Stage 03 — Rasterize pages (chunk-based).

PDF → ocr/pages/page_NNN.jpg at configured DPI. Chunk protocol: process
--chunk 1-20, save, free memory, next chunk. The page image is the FINAL
REFERENCE for all OCR verification.

Usage: python3 scripts/03_rasterize.py --chunk 1-20 [--dpi 180]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from lib import config, manifest, pdfx, paths  # noqa: E402
import pymupdf  # noqa: E402


def main() -> None:
    p = common.base_parser("03_rasterize")
    p.add_argument("--dpi", type=int, help="override config DPI")
    args = p.parse_args()

    cfg = config.load_book_config()
    src = paths.ROOT / cfg["book"]["source_pdf"]
    if not src.exists():
        raise SystemExit(f"source not found: {src}")
    dpi = args.dpi or cfg["pages"]["dpi"]
    quality = cfg["pages"]["jpeg_quality"]
    chunks = common.resolve_chunks(args, cfg)

    paths.ensure_dirs()
    doc = pymupdf.open(src)
    done = 0
    for ch in chunks:
        for page in ch.pages:
            out = paths.PAGES / f"page_{page:03d}.jpg"
            if out.exists() and out.stat().st_size > 10_000:
                manifest.update(page, status="rasterized", image=str(out.relative_to(paths.ROOT)),
                                image_dpi=dpi, has_text_layer=pdfx.has_text_layer(doc, page - 1))
                continue
            pix = pdfx.rasterize_page(doc, page - 1, dpi)
            pdfx.save_jpeg(pix, out, quality=quality)
            del pix  # free immediately
            manifest.update(page, status="rasterized", image=str(out.relative_to(paths.ROOT)),
                            image_dpi=dpi, has_text_layer=pdfx.has_text_layer(doc, page - 1))
            done += 1
        doc.close()
        # end of chunk: full memory release point
        doc = pymupdf.open(src) if ch != chunks[-1] else None
    if doc:
        doc.close()
    common.banner("03_rasterize", f"rasterized {done} new pages @ {dpi}dpi "
                                  f"(chunks: {', '.join(map(str, chunks))})")


if __name__ == "__main__":
    main()
