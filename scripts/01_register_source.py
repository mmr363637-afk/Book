#!/usr/bin/env python3
"""Stage 01 — Register source PDF.

Finds input/*.pdf, records sha256 + page count + size into config/book.yaml
and qa/source-metadata.json. Idempotent; refuses to proceed if two different
PDFs were registered with different hashes without --force.

Usage: python3 scripts/01_register_source.py [--file input/xxx.pdf] [--force]
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config, pdfx, paths, log  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="explicit pdf path (default: single file in input/)")
    ap.add_argument("--force", action="store_true", help="re-register even if hash differs")
    args = ap.parse_args()

    paths.ensure_dirs()
    if args.file:
        src = Path(args.file).resolve()
        if not src.exists():
            raise SystemExit(f"file not found: {src}")
    else:
        pdfs = sorted(paths.INPUT.glob("*.pdf"))
        if not pdfs:
            raise SystemExit(
                "no PDF found in input/. Place the scanned book there, then re-run.\n"
                "  $ cp /path/to/book.pdf input/source.pdf"
            )
        if len(pdfs) > 1:
            raise SystemExit(f"multiple PDFs in input/: {pdfs}; use --file to choose")
        src = pdfs[0]

    digest = pdfx.sha256_of(src)
    meta = pdfx.pdf_meta(src)

    cfg = config.load_book_config()
    prev = cfg["book"].get("sha256")
    if prev and prev != digest and not args.force:
        raise SystemExit(
            f"source hash changed: {prev[:12]}… → {digest[:12]}…\n"
            "This usually means the book PDF was replaced. Re-run with --force\n"
            "to reset registration (and re-run stages 02+ on affected chunks)."
        )

    cfg["book"].update({
        "source_pdf": str(src.relative_to(paths.ROOT)),
        "sha256": digest,
        "registered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    })
    cfg["pages"]["total"] = meta["pages"]
    config.save_book_config(cfg)

    (paths.QA / "source-metadata.json").write_text(
        json.dumps({"source": str(src), "sha256": digest, **meta}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("01_register", f"registered {src.name}: {meta['pages']} pages, "
                            f"size {meta['page_size_pt'][0]}x{meta['page_size_pt'][1]}pt, sha256 {digest[:16]}…")
    print(f"OK: {meta['pages']} pages registered from {src.name}")


if __name__ == "__main__":
    main()
