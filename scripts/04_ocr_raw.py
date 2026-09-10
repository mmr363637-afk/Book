#!/usr/bin/env python3
"""Stage 04 — OCR RAW DRAFT (chunk-based, two-layer design).

Layer 1 (mechanical, automatic): the bundled PP-OCRv4 Latin engine runs over
every page image and extracts ASCII tokens (drug names, numbers, units) with
confidence + bbox → ocr/raw/page_NNN.crosscheck.json.

Layer 2 (vision, agent): for every page the agent reads the ORIGINAL page
image (the final reference) and writes the full first-pass transcription to
ocr/raw/page_NNN.txt. This is the RAW DRAFT — expected to contain minor
errors, fixed in the verification pass (stage 06).

The script prepares the chunk (images check + crosscheck + task stubs) and
maintains the draft queue:

  $ python3 scripts/04_ocr_raw.py --chunk 1-10     # prepare chunk
  $ python3 scripts/04_ocr_raw.py --status         # show draft queue

Queue states: awaiting_draft → drafted → verified.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from lib import config, manifest, ocr_engine, paths  # noqa: E402

STUB = """<!-- RAW DRAFT — page {page:03d}
     image (FINAL REFERENCE): {image}
     crosscheck (mechanical Latin tokens, conf>= {min_conf}): see page_{page:03d}.crosscheck.json
     Protocol: full transcription, reading the image top-to-bottom.
     Keep original language mix. Mark truly illegible spots with [ILLEGIBLE].
     Do NOT correct or clean up — this is the raw first pass.
     When done, mark status drafted:  python3 scripts/04_ocr_raw.py --mark-drafted {page}
-->
"""


def prepare_chunk(cfg, chunk) -> None:
    cc_cfg = cfg["pipeline"]["crosscheck"]
    cc = ocr_engine.LatinCrosscheck(min_conf=cc_cfg["min_conf"]) if cc_cfg["enabled"] else None
    for page in chunk.pages:
        rec = manifest.get(page)
        if rec is None:
            raise SystemExit(f"page {page} not rasterized — run stage 03 first")
        img = paths.ROOT / rec["image"]
        if not img.exists():
            raise SystemExit(f"image missing: {img}")
        raw_txt = paths.RAW / f"page_{page:03d}.txt"
        cc_path = paths.RAW / f"page_{page:03d}.crosscheck.json"
        if cc is not None and not cc_path.exists():
            tokens = cc.run_on_image(img)
            ocr_engine.save_crosscheck(img, cc_path, tokens)
        if not raw_txt.exists():
            raw_txt.write_text(STUB.format(page=page, image=rec["image"], min_conf=cc_cfg["min_conf"]),
                                encoding="utf-8")
        manifest.update(page, status="awaiting_draft")
    n_tokens = 0
    for page in chunk.pages:
        n_tokens += len(ocr_engine.load_crosscheck(paths.RAW / f"page_{page:03d}.crosscheck.json"))
    common.banner("04_ocr_raw", f"chunk {chunk} prepared; {n_tokens} mechanical Latin tokens "
                                f"collected for crosscheck; agent must now write raw drafts from page images")


def mark_drafted(pages) -> None:
    for page in pages:
        txt = paths.RAW / f"page_{page:03d}.txt"
        if not txt.exists() or len(txt.read_text(encoding="utf-8").strip()) < 40:
            raise SystemExit(f"page {page}: raw draft missing or too short — cannot mark drafted")
        manifest.update(page, status="drafted", raw=f"ocr/raw/page_{page:03d}.txt")
    print(f"marked drafted: {sorted(pages)}")


def status() -> None:
    from collections import Counter
    q = manifest.queue()
    counts = Counter(r.get("status", "?") for r in q)
    total_pages = len(q)
    print(f"pages tracked: {total_pages}")
    for s in ["rasterized", "awaiting_draft", "drafted", "verified", "flagged"]:
        print(f"  {s:14s} {counts.get(s, 0)}")
    pending = [r["page"] for r in q if r.get("status") == "awaiting_draft"]
    if pending:
        runs = compress(pending)
        print(f"awaiting_draft pages: {runs}")


def compress(pages: list[int]) -> str:
    if not pages:
        return ""
    out, start, prev = [], pages[0], pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
        else:
            out.append(f"{start}-{prev}" if start != prev else f"{start}")
            start = prev = p
    out.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ", ".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--mark-drafted", help="comma pages to mark drafted after agent wrote drafts")
    args = ap.parse_args()

    cfg = config.load_book_config()
    paths.ensure_dirs()

    if args.status:
        status()
        return
    if args.mark_drafted:
        mark_drafted([int(x) for x in args.mark_drafted.split(",") if x.strip()])
        return
    if not args.chunk:
        raise SystemExit("need --chunk (or --status / --mark-drafted)")
    for ch in common.resolve_chunks(args, cfg):
        prepare_chunk(cfg, ch)


if __name__ == "__main__":
    main()
