# Medical Book Reconstruction & Publishing Pipeline

سیستم بازسازی و انتشار یک کتاب پزشکی اسکن‌شده:

```
PDF اسکن‌شده → OCR (دو‌لایه) → استخراج ساختاری → بازسازی آموزشی → HTML → PDF
```

**اصل:** HTML منبع اصلی (Source of Truth) است؛ PDF فقط از HTML ساخته می‌شود.
**اصل دوم:** تصویر اصلی هر صفحه مرجع نهایی است؛ OCR (هر نوعی که باشد) فقط استخراج اولیه است.
**اصل سوم:** هر مرحله chunk-based است — هیچ‌وقت کل کتاب در یک مرحله/Context پردازش نمی‌شود.

---

## معماری

```
input/source.pdf
   │  01 register        → config/book.yaml (sha256, pages)
   │  02 inspect         → qa/inspect-report.json + contact sheets → ساختار کتاب شناخته می‌شود
   │  03 rasterize       → ocr/pages/page_NNN.jpg          (مرجع نهایی بصری)
   │  04 ocr-prepare     → ocr/raw/page_NNN.crosscheck.json (لایه مکانیکی: توکن‌های لاتین/اعداد)
   │                       ocr/raw/page_NNN.txt             (دیفال → توسط Agent از تصویر پر می‌شود)
   │  05 verify-prepare  → qa/verify/page_NNN/band_*.jpg    (برش‌های دقیق)
   │  (Agent: pass دوم — مقایسه با تصویر، رفع خطا، ثبت Flag)
   │  06 verify-report   → ocr/verified/page_NNN.txt + qa/flags/flags.jsonl
   │  07 structure       → content/chapters + content/topics (YAML) + guardrailها
   │  08 render-html     → book/html/index.html + chapters/*.html   ← SOURCE OF TRUTH
   │  09 build-pdf       → pdf/book.pdf                          (فقط از HTML)
   │  10 qa              → qa/final-report.md
   ▼
کتاب نهایی (HTML در مرورگر + PDF چاپ A4)
```

## ساختار دایرکتوری

```
Book/
├── input/              PDF منبع
├── ocr/
│   ├── pages/          تصویر هر صفحه (مرجع نهایی) — page_001.jpg …
│   ├── raw/            OCR خام: دِرافت + crosscheck مکانیکی — page_001.txt/.crosscheck.json
│   ├── verified/       OCR اعتبارسنجی‌شده — page_001.txt
│   └── manifest.jsonl  وضعیت هر صفحه (رسانهٔ کنترل Pipeline)
├── content/
│   ├── source-analysis.md    گزارش ساختاری منبع (مرحله ۲)
│   ├── chapters/chNN.yaml    نقشهٔ فصل‌ها
│   ├── topics/chNN_tMM.yaml  مدل ساختاری هر Topic (درسنامه/FollowUp/Recall/تست‌ها)
│   ├── lexicon.yaml          واژه‌نامهٔ داروها/بیماری‌ها (در حین کار رشد می‌کند)
│   └── build-manifest.json   خروجی مرحله ۰۷
├── book/
│   ├── html/           ← خروجی اصلی (Source of Truth)
│   ├── css/            استایل (screen + print)
│   ├── fonts/          Vazirmatn
│   └── images/          تصاویر استخراج‌شده از منبع
├── pdf/                خروجی نهایی (فقط از HTML)
├── qa/
│   ├── inspect/        contact sheets مرحله ۰۲
│   ├── flags/          فلگ‌های OCR/پزشکی + گزارش‌ها
│   ├── smoke/          self-test مکانیکی Pipeline
│   ├── run-log.md      لاگ اجرا
│   └── final-report.md گزارش QA نهایی
├── scripts/            مراحل Pipeline (01…10) + lib/
├── config/             book.yaml (میتادیتا + نقشهٔ فصل‌ها) · render.yaml (طراحی)
├── docs/pipeline.md    مستند معماری و قراردادها
└── Makefile            ورودی‌های مرحله‌به‌مرحله
```

## مدل آموزشی هر Topic (content/topics/*.yaml)

```
درسنامه (lesson)  →  Follow Up (فقط اگر در کتاب هست)  →  Active Recall (از محتوای همان topic)
        →  تست‌ها (فقط تست‌های خود کتاب، با source_page)  →  Answer Key (از خود کتاب)
```

Guardrailهای سخت (مرحله ۰۷) که ساخت جعلی را بلاک می‌کنند:

| کد | قاعده |
|---|---|
| G1 | تست بدون `source_page` یا بدون `answer` → خطا (anti-fabrication) |
| G2 | Active Recall بدون `from` به بخش درسنامه → خطا (باید از محتوای topic باشد) |
| G3 | Follow Up بدون `source_pages` → خطا (فقط Follow Up خود کتاب مجاز است) |
| G4 | فایل تصویر موجود نباشد → خطا |
| G6 | شمارهٔ صفحه خارج از بازهٔ فصل → خطا |

## چرخهٔ کاری (chunk-based)

هر بار فقط یک chunk (پیش‌فرض ۱۰ صفحه):

```bash
make rasterize CHUNK=1-10     # PDF → تصاویر
make ocr-prepare CHUNK=1-10   # crosscheck مکانیکی + استابلایهٔ دِرافت
# ← Agent: خواندن تصویر هر صفحه → نوشتن ocr/raw/page_NNN.txt
make ocr-drafted CHUNK=1-10   # (یا --mark-drafted)
make verify-prepare PAGE=1    # برش‌های دقیق برای صفحه‌هایی که حساس‌اند
# ← Agent: pass دوم با برش‌ها → نوشتن ocr/verified/page_NNN.txt
make verify-report CHUNK=1-10 # تطبیق mechanical + ثبت Flag
# ← Agent: ساخت YAMLهای topic از verified text
make structure                # guardrails
make html && make pdf
make qa
git add -A && git commit -m "stage: chunk 1-10 complete"   # checkpoint
```

## وضعیت فعلی پروژه

> ✅ Pipeline پیاده‌سازی و smoke-test شده است (زنجیرهٔ کامل ۰۱→۱۰ سبز،
> شامل guardrail ضد‌ساخت تست‌ها).
> ⏳ در انتظار دریافت PDF اسکن‌شده کتاب در `input/` برای شروع مرحلهٔ
> تحلیل منبع و Pilot.

Self-test: `python3 qa/smoke/run_smoke.py`

## انحرافات ثبت‌شده از محیط (Sandbox Deviations)

1. **WeasyPrint در دسترس نیست** (وابسته به کتابخانهٔ سیستمی Pango که قابل نصب نیست).
   مرحله ۰۹ یک renderer بر پایهٔ ReportLab است که **همان HTML را مصرف می‌کند**
   (محتوای مستقلی برای PDF تولید نمی‌شود) — قرارداد خروجی (A4، RTL، فونت، page-break)
   مطابق طراحی است. روی محیطی با Pango می‌توان `09_build_pdf.py` را به WeasyPrint عوض کرد.
2. **مدل OCR فارسی مکانیکی قابل دانلود نیست** (HuggingFace/modelscope مسدودند).
   لایهٔ مکانیکی = موتور PP-OCRv4 لاتین/عدد (crosscheck برای اعداد/دوزها/نام داروها)؛
   لایهٔ اصلی OCR = خواندن مستقیم تصویر صفحه توسط Agent (دو pass: دِرافت + verify).
   این طراحی در عمل قوی‌تر از OCR خالص مکانیکی است، چون «تصویر مرجع نهایی» مستقیماً
   داخل حلقهٔ تولید متن قرار می‌گیرد.
