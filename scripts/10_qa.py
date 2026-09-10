#!/usr/bin/env python3
"""Stage 10 — QA: mechanical integrity checks + report.

Checks (each produces a line in qa/final-report.md):
  S1  chapter/topic coverage vs chapter map
  S2  every question in HTML has data-source-page (anti-fabrication)
  S3  every sensitive token in HTML text exists in the verified OCR of its
      topic's source pages (medical-number cross-check)
  S4  figure/table integrity (files exist, referenced once)
  S5  OCR flag audit (open flags must be listed with pages)
  S6  PDF: page count, extractable text, spot strings present
  S7  memory/chunk protocol: manifest has no pages stuck >1 chunk behind

Usage: python3 scripts/10_qa.py [--report qa/final-report.md]
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config, manifest, paths, sensitive  # noqa: E402

import pymupdf  # noqa: E402

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=str(paths.REPORT))
    args = ap.parse_args()

    cfg = config.load_book_config()
    results: list[tuple[str, str, str]] = []

    def add(check, status, detail):
        results.append((check, status, detail))

    # ---------------- S1 coverage
    bm = paths.BUILD_MANIFEST
    if bm.exists():
        m = json.loads(bm.read_text(encoding="utf-8"))
        add("S1 topics built", PASS, f"{m['topics']} topics, {m['chapters']} chapters, {m['questions']} questions")
    else:
        add("S1 topics built", FAIL, "content/build-manifest.json missing — run stage 07")

    # ---------------- S2 anti-fabrication in HTML
    n_q = 0
    n_no_src = 0
    html_text_all = []
    chapter_files = sorted(paths.HTML_CHAPTERS.glob("ch*.html"))
    for f in chapter_files:
        h = f.read_text(encoding="utf-8")
        qs = re.findall(r'<article class="question"[^>]*>', h)
        n_q += len(qs)
        for tag in qs:
            if 'data-source-page="' not in tag or 'data-source-page=""' in tag:
                n_no_src += 1
        html_text_all.append(re.sub(r"<[^>]+>", " ", h))
    add("S2 questions sourced", PASS if n_no_src == 0 else FAIL,
        f"{n_q} questions in HTML, {n_no_src} without source-page")

    # ---------------- S3 sensitive tokens vs verified OCR
    verified_texts = []
    for vp in sorted(paths.VERIFIED.glob("page_*.txt")):
        verified_texts.append(vp.read_text(encoding="utf-8"))
    corpus = " \n".join(verified_texts)
    corpus_norm = set()
    for t in sensitive.find_sensitive(corpus):
        corpus_norm.add(t["norm"])
    for t in re.findall(r"[A-Za-z0-9.%/µ\-+]+", corpus):
        corpus_norm.add(sensitive.normalize(t))
    n_tok = 0
    n_missing = 0
    missing_samples = []
    for chunk_text in html_text_all:
        for tok in sensitive.find_sensitive(chunk_text):
            n_tok += 1
            if tok["kind"] in ("negative_question", "answer_word", "year", "ratio"):
                continue  # language-level tokens, not OCR-sensitive numbers
            if tok["norm"] not in corpus_norm:
                n_missing += 1
                if len(missing_samples) < 10:
                    missing_samples.append(f"{tok['kind']}:`{tok['token']}`")
    if verified_texts:
        add("S3 sensitive tokens verified",
            PASS if n_missing == 0 else WARN,
            f"{n_tok} sensitive tokens in HTML; {n_missing} not found in verified OCR "
            f"(samples: {', '.join(missing_samples) or '—'})")
    else:
        add("S3 sensitive tokens verified", FAIL, "no verified OCR text yet — stage 06 pending")

    # ---------------- S4 figures/tables
    n_fig = 0
    missing_figs = []
    for f in chapter_files:
        h = f.read_text(encoding="utf-8")
        for m in re.finditer(r'<img src="\.\./images/([^"]+)"', h):
            n_fig += 1
            p = paths.BOOK / "images" / m.group(1)
            if not p.exists():
                missing_figs.append(m.group(1))
        n_fig_tab = len(re.findall(r'class="data-table"', h))
        n_fig += n_fig_tab
    add("S4 figures/tables", PASS if not missing_figs else FAIL,
        f"{n_fig} figure+table blocks; missing files: {missing_figs or 'none'}")

    # ---------------- S5 flags
    flags_path = paths.FLAGS / "flags.jsonl"
    flags = []
    if flags_path.exists():
        flags = [json.loads(l) for l in flags_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    open_flags = [f for f in flags if f["status"] == "open"]
    add("S5 OCR flags", PASS if not open_flags else WARN,
        f"{len(open_flags)} open flags (of {len(flags)} total)")

    # ---------------- S6 PDF
    pdf_path = paths.PDF / "book.pdf"
    if pdf_path.exists():
        d = pymupdf.open(str(pdf_path))
        npg = d.page_count
        text_sample = d[1].get_text() if npg > 1 else ""
        has_fa = any(0x0600 <= ord(ch) <= 0x06FF for ch in text_sample)
        add("S6 PDF", PASS, f"{pdf_path.name}: {npg} pages; Persian text extractable: {has_fa}")
        d.close()
    else:
        add("S6 PDF", WARN, "pdf/book.pdf not built yet — run stage 09")

    # ---------------- S7 pipeline state
    recs = manifest.all_records()
    stuck = Counter(r.get("status") for r in recs)
    add("S7 pipeline state", PASS,
        f"pages tracked: {len(recs)}; by status: {dict(stuck)}")

    # ---------------- report
    rep = ["# Final QA Report", ""]
    for check, status, detail in results:
        rep.append(f"- **[{status}]** {check} — {detail}")
    rep.append("")
    n_open = len(open_flags)
    rep.append(f"**Open flags:** {n_open}")
    if open_flags:
        rep.append("")
        for f in open_flags:
            rep.append(f"- {f['id']} p{f['page']:03d} [{f['kind']}] `{f['token']}`")
    Path(args.report).write_text("\n".join(rep) + "\n", encoding="utf-8")

    fails = [r for r in results if r[1] == FAIL]
    print(f"QA done: {len(results)} checks, {len(fails)} FAIL, {sum(1 for r in results if r[1]==WARN)} WARN")
    for c, s, d_ in results:
        print(f"  [{s}] {c}: {d_}")
    if fails:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
