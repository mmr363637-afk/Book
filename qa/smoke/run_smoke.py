#!/usr/bin/env python3
"""Pipeline SELF-TEST (mechanical) — NOT book content.

Builds a 2-page synthetic fixture PDF (clearly marked), then runs stages
01→03→04→06→07→08→09→10 end-to-end in a sandboxed way and asserts the chain
works. Cleans up after itself (config restored, smoke content removed).

Run: python3 qa/smoke/run_smoke.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "qa" / "smoke"
WORK = SMOKE / "work"
sys.path.insert(0, str(ROOT / "scripts"))

FIXTURE_TEXT_1 = (
    "فصل نمونه — Smoke Test (این صفحه از محتوای کتاب نیست)\n"
    "بیماری X با عوارض Y همراه است. دوز استاندارد 50 mg به‌صورت خوراکی هر 8 ساعت می‌باشد.\n"
    "Cut-off تشخیصی: > 40 mmol/L و pH خون 7.4\n"
    "جدول آزمایش‌ها: قند خون 100 mg/dL — هموگلوبین 14 g/dL — سدیم 140 mmol/L\n"
    "کدام گزینه از عوارض جانبی این دارو نیست؟"
)
FIXTURE_TEXT_2 = (
    "گزینه‌ها: A خارش پوستی — B کهیر — C اختلال بینایی — D بی‌خوابی\n"
    "پاسخ: D — اختلال بینایی از عوارض شناخته‌شده نیست.\n"
    "Follow Up: بیمار باید 2 هفته بعد برای تکرار آزمایش مراجعه کند."
)


def build_fixture() -> Path:
    import arabic_reshaper
    from bidi.algorithm import get_display
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("Vazirmatn", str(ROOT / "book" / "fonts" / "Vazirmatn-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Vazirmatn-Bold", str(ROOT / "book" / "fonts" / "Vazirmatn-Bold.ttf")))

    def shaped(t):
        return get_display(arabic_reshaper.reshape(t))

    out = WORK / "fixture.pdf"
    c = canvas.Canvas(str(out), pagesize=A4)
    for i, text in enumerate([FIXTURE_TEXT_1, FIXTURE_TEXT_2], 1):
        y = 760
        c.setFont("Vazirmatn-Bold", 15)
        first, _, rest = text.partition("\n")
        c.drawRightString(540, y, shaped(first))
        y -= 34
        c.setFont("Vazirmatn", 12)
        for line in rest.split("\n"):
            c.drawRightString(540, y, shaped(line))
            y -= 24
        c.setFont("Vazirmatn-Light" if False else "Vazirmatn", 9)
        c.drawString(50, 40, f"smoke fixture page {i} — NOT book content")
        c.showPage()
    c.save()
    return out


def run(args, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / args[0])] + args[1:],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=600, **kw)


def main() -> None:
    failures = []

    def check(name, cond, detail=""):
        print(f"  {'OK ' if cond else 'FAIL'} {name} {detail}")
        if not cond:
            failures.append(name)

    cfg_path = ROOT / "config" / "book.yaml"
    cfg_backup = cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else None
    saved_paths = {}
    try:
        WORK.mkdir(parents=True, exist_ok=True)
        fixture = build_fixture()
        (ROOT / "input" / "smoke_fixture.pdf").parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixture, ROOT / "input" / "smoke_fixture.pdf")

        # ---- stage 01
        r = run(["01_register_source.py", "--file", "input/smoke_fixture.pdf"])
        check("01 register", r.returncode == 0, r.stderr.strip()[-200:] if r.returncode else f"({r.stdout.strip()})")

        # ---- stage 03
        r = run(["03_rasterize.py", "--chunk", "1-2"])
        check("03 rasterize", r.returncode == 0 and (ROOT / "ocr" / "pages" / "page_001.jpg").exists(),
              r.stderr.strip()[-200:] if r.returncode else "")

        # ---- stage 04 (mechanical crosscheck on fixture)
        r = run(["04_ocr_raw.py", "--chunk", "1-2"])
        check("04 ocr-prepare", r.returncode == 0, r.stderr.strip()[-200:] if r.returncode else "")
        cc1 = json.loads((ROOT / "ocr" / "raw" / "page_001.crosscheck.json").read_text()) \
            if (ROOT / "ocr" / "raw" / "page_001.crosscheck.json").exists() else {"tokens": []}
        check("04 crosscheck found latin tokens", len(cc1["tokens"]) >= 2,
              f"({len(cc1['tokens'])} tokens: {[t['token'] for t in cc1['tokens'][:5]]})")

        # ---- agent-equivalent: raw drafts + verified (mechanical stand-in for smoke)
        (ROOT / "ocr" / "raw" / "page_001.txt").write_text(FIXTURE_TEXT_1, encoding="utf-8")
        (ROOT / "ocr" / "raw" / "page_002.txt").write_text(FIXTURE_TEXT_2, encoding="utf-8")
        (ROOT / "ocr" / "verified" / "page_001.txt").write_text(FIXTURE_TEXT_1, encoding="utf-8")
        (ROOT / "ocr" / "verified" / "page_002.txt").write_text(FIXTURE_TEXT_2, encoding="utf-8")

        # ---- stage 06
        r = run(["06_verify_report.py", "--chunk", "1-2"])
        check("06 verify-report", r.returncode == 0, r.stderr.strip()[-200:] if r.returncode else "")
        man_path = ROOT / "ocr" / "manifest.jsonl"
        manifest = [json.loads(l) for l in man_path.read_text().splitlines() if l] if man_path.exists() else []
        m1 = next((m for m in manifest if m["page"] == 1), {})
        check("06 page1 verified, no flags", m1.get("status") == "verified" and m1.get("flags", 0) == 0,
              f"(status={m1.get('status')}, flags={m1.get('flags')})")

        # ---- content: smoke chapter + topic (marked as smoke)
        (ROOT / "content" / "chapters" / "ch01.yaml").write_text(
            "id: ch01\ntitle: \"فصل نمونه (Smoke)\"\nstart_page: 1\nend_page: 2\ntopics: [ch01_t01]\n",
            encoding="utf-8")
        (ROOT / "content" / "topics" / "ch01_t01.yaml").write_text("""
id: ch01_t01
chapter: ch01
title: "Topic نمونه (Smoke)"
source_pages: [1, 2]
lesson:
  - id: l1
    heading: "نکته نمونه"
    blocks:
      - {type: p, text: "دوز استاندارد 50 mg به‌صورت خوراکی هر 8 ساعت می‌باشد."}
      - {type: bullets, items: ["قند خون 100 mg/dL", "هموگلوبین 14 g/dL", "سدیم 140 mmol/L"]}
      - {type: highyield, text: "Cut-off تشخیصی: > 40 mmol/L و pH خون 7.4"}
followup:
  source_pages: [2]
  blocks:
    - {type: p, text: "بیمار باید 2 هفته بعد برای تکرار آزمایش مراجعه کند."}
active_recall:
  - {q: "دوز استاندارد چقدر است؟", a: "50 mg هر 8 ساعت", from: l1}
questions:
  - id: q01
    source_page: 2
    stem: "کدام گزینه از عوارض جانبی این دارو نیست؟"
    options: {a: "خارش پوستی", b: "کهیر", c: "اختلال بینایی", d: "بی‌خوابی"}
    answer: "d"
    explanation: "اختلال بینایی از عوارض شناخته‌شده نیست."
""", encoding="utf-8")

        # ---- guardrail negative test: a question WITHOUT source_page must FAIL
        bad_topic = (ROOT / "content" / "topics" / "ch01_t99.yaml")
        bad_topic.write_text("""
id: ch01_t99
chapter: ch01
title: "bad"
source_pages: [1]
lesson:
  - id: l1
    heading: "x"
    blocks:
      - {type: p, text: "x"}
questions:
  - id: q01
    stem: "سؤال بدون صفحه منبع (fake)"
    options: {a: "1", b: "2"}
    answer: "a"
""", encoding="utf-8")
        r = run(["07_structure.py"])
        check("07 REJECTS fabricated question", r.returncode != 0 and "G1" in r.stdout, r.stdout.strip()[-120:])
        bad_topic.unlink()

        # ---- stage 07 happy path
        r = run(["07_structure.py"])
        check("07 structure", r.returncode == 0, r.stderr.strip()[-200:] if r.returncode else "")

        # ---- stage 08
        r = run(["08_render_html.py"])
        check("08 render-html", r.returncode == 0 and (ROOT / "book" / "html" / "chapters" / "ch01.html").exists(),
              r.stderr.strip()[-300:] if r.returncode else "")

        # ---- stage 09
        r = run(["09_build_pdf.py", "--out", "qa/smoke/work/smoke.pdf"])
        check("09 build-pdf", r.returncode == 0, (r.stderr.strip() or r.stdout.strip())[-400:] if r.returncode else "")

        # ---- stage 10
        r = run(["10_qa.py", "--report", "qa/smoke/work/qa-report.md"])
        check("10 qa exit ok", r.returncode == 0, (r.stdout.strip() or r.stderr.strip())[-400:] if r.returncode else "")

        # ---- PDF content assertions
        import pymupdf
        d = pymupdf.open(str(WORK / "smoke.pdf"))
        all_text = "".join(d[i].get_text() for i in range(d.page_count))
        d.close()
        check("pdf has pages", (WORK / "smoke.pdf").stat().st_size > 5000,
              f"({(WORK / 'smoke.pdf').stat().st_size} bytes)")
        import arabic_reshaper
        # PyMuPDF reorders Arabic extraction to logical order → reshape-only probe
        probe = arabic_reshaper.reshape("کدام گزینه")
        check("pdf contains question text", probe in all_text, "")
        check("pdf contains dose", "50" in all_text and "mg" in all_text)
        check("pdf contains answer", "د" in all_text or "D" in all_text)

        # ---- render PDF page 1 to PNG for visual inspection
        import pymupdf as m2
        d = m2.open(str(WORK / "smoke.pdf"))
        d[0].get_pixmap(dpi=110).save(str(WORK / "smoke_page1.png"))
        d.close()

    finally:
        # ---- cleanup: restore config, remove smoke artifacts
        if cfg_backup is not None:
            cfg_path.write_text(cfg_backup, encoding="utf-8")
        for p in [ROOT / "input" / "smoke_fixture.pdf",
                  ROOT / "content" / "chapters" / "ch01.yaml",
                  ROOT / "content" / "topics" / "ch01_t01.yaml"]:
            if p.exists():
                p.unlink()
        for p in [ROOT / "ocr" / "pages" / "page_001.jpg", ROOT / "ocr" / "pages" / "page_002.jpg",
                  ROOT / "ocr" / "raw" / "page_001.txt", ROOT / "ocr" / "raw" / "page_002.txt",
                  ROOT / "ocr" / "raw" / "page_001.crosscheck.json", ROOT / "ocr" / "raw" / "page_002.crosscheck.json",
                  ROOT / "ocr" / "verified" / "page_001.txt", ROOT / "ocr" / "verified" / "page_002.txt",
                  ROOT / "book" / "html" / "chapters" / "ch01.html"]:
            if p.exists():
                p.unlink()
        if (ROOT / "ocr" / "manifest.jsonl").exists():
            lines = [l for l in (ROOT / "ocr" / "manifest.jsonl").read_text().splitlines()
                     if l.strip() and json.loads(l).get("page", 0) > 2]
            (ROOT / "ocr" / "manifest.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""))
        if (ROOT / "content" / "build-manifest.json").exists():
            (ROOT / "content" / "build-manifest.json").unlink()
        if (ROOT / "qa" / "flags" / "flags.jsonl").exists() and not (ROOT / "qa" / "flags" / "flags.jsonl").read_text().strip():
            (ROOT / "qa" / "flags" / "flags.jsonl").unlink()

    report = SMOKE / "smoke-report.md"
    report.write_text(
        "# Smoke Test Report\n\n"
        f"Result: {'PASS' if not failures else 'FAIL: ' + ', '.join(failures)}\n\n"
        "Fixture artifacts kept in qa/smoke/work/ (smoke.pdf, smoke_page1.png, qa-report.md).\n",
        encoding="utf-8")
    print(f"\nSMOKE RESULT: {'PASS' if not failures else 'FAIL — ' + ', '.join(failures)}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
