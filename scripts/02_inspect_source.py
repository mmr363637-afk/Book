#!/usr/bin/env python3
"""Stage 02 — Source analysis (no OCR yet).

Produces:
  qa/inspect-report.json        per-page audit (ink stats, text-layer presence)
  qa/inspect/contact_sheet_NN.jpg  20-page contact sheets for visual review
  content/source-analysis.md    draft report (stats + structural findings)

The agent reviews the contact sheets and completes the "structural findings"
section (chapter map, TOC location, tables/figures/questions/answer-key
presence) — this drives config/book.yaml:chapters.

Usage: python3 scripts/02_inspect_source.py [--sheet-pages 20]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config, pdfx, paths, log  # noqa: E402
import pymupdf  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


def make_contact_sheet(doc, start: int, end: int, thumb_w: int = 240, cols: int = 4, out_path: Path = None) -> None:
    import io
    thumbs = []
    for i in range(start, end):
        pix = doc[i].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        ratio = thumb_w / img.width
        img = img.resize((thumb_w, int(img.height * ratio)))
        thumbs.append(img)
        del pix, img
    rows = (len(thumbs) + cols - 1) // cols
    th = thumbs[0].height
    sheet = Image.new("RGB", (cols * (thumb_w + 14) + 14, rows * (th + 34) + 14), "white")
    d = ImageDraw.Draw(sheet)
    for idx, (img, pageno) in enumerate(zip(thumbs, range(start + 1, end + 1))):
        r, c = divmod(idx, cols)
        x = 14 + c * (thumb_w + 14)
        y = 14 + r * (th + 34)
        d.text((x, y), f"p{pageno:03d}", fill=(20, 60, 120))
        sheet.paste(img, (x, y + 18))
    sheet.save(out_path, "JPEG", quality=80)


def classify(rec: dict) -> str:
    if rec.get("error"):
        return "error"
    if rec["ink_frac"] < 0.002:
        return "blank"
    if rec["ink_frac"] > 0.35:
        return "dense"
    if rec["top_ink_frac"] > 0.15 and rec["ink_frac"] < 0.12:
        return "title-like"
    if rec["has_text_layer"]:
        return "text-layer"
    return "scanned"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-pages", type=int, default=20)
    args = ap.parse_args()

    cfg = config.load_book_config()
    src = paths.ROOT / cfg["book"]["source_pdf"]
    if not src.exists():
        raise SystemExit(f"source not found: {src} — run stage 01 first")

    paths.ensure_dirs()
    (paths.QA / "inspect").mkdir(exist_ok=True)

    doc = pymupdf.open(src)
    records = pdfx.audit_pages(src)
    doc.close()
    for rec in records:
        rec["class"] = classify(rec)

    (paths.QA / "inspect-report.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")

    # contact sheets
    n = len(records)
    sheets = []
    for s in range(0, n, args.sheet_pages):
        e = min(n, s + args.sheet_pages)
        p = paths.QA / "inspect" / f"contact_sheet_{s // args.sheet_pages + 1:02d}.jpg"
        # re-open just for thumbnails (cheap, bounded memory)
        d2 = pymupdf.open(src)
        make_contact_sheet(d2, s, e, out_path=p)
        d2.close()
        sheets.append(str(p.relative_to(paths.ROOT)))

    # stats summary
    from collections import Counter
    cls = Counter(r["class"] for r in records)
    scanned_pages = sum(1 for r in records if not r["has_text_layer"])
    summary = {
        "total_pages": n,
        "scanned_pages": scanned_pages,
        "text_layer_pages": n - scanned_pages,
        "class_counts": dict(cls),
        "sheets": sheets,
    }

    md = f"""# Source Analysis — {src.name}

_Auto-generated stage-02 report. The "Structural findings" section below is
completed by the agent after reviewing the contact sheets._

## Machine statistics

- Total pages: **{n}**
- Scanned (no text layer): **{scanned_pages}** · with text layer: **{n - scanned_pages}**
- Page size: {cfg['pages'].get('size', 'see source-metadata.json')}
- Page class distribution: {dict(cls)}

## Contact sheets (visual review)

""" + "\n".join(f"- {s}" for s in sheets) + """

## Structural findings

_To be completed after reviewing contact sheets:_

- [ ] Chapter list with start/end pages → `config/book.yaml:chapters`
- [ ] TOC location and format
- [ ] Tables: present? which pages?
- [ ] Figures/diagrams/algorithms: present? which pages?
- [ ] Question bank: present? format? where is the Answer Key?
- [ ] Follow Up sections: present? per-topic or per-chapter?
- [ ] Language mix (Persian / English) and any other scripts
- [ ] Physical defects: skewed scans, dark margins, stamps, handwritten notes
"""
    (paths.CONTENT / "source-analysis.md").write_text(md, encoding="utf-8")

    log.info("02_inspect", f"audited {n} pages; {scanned_pages} scanned; "
                            f"{len(sheets)} contact sheets")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
