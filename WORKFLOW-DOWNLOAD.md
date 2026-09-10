# 🤖 Workflow دانلود خودکار PDF (اختیاری)

این فایل راهنمای ساخت Workflow خودکار برای دانلود PDF از `sv3.admlink.ir` است.

## چرا Workflow پوش نشد؟

توکن GitHub App که Arena استفاده می‌کند اجازه `workflows` ندارد:
```
refusing to allow a GitHub App to create or update workflow `.github/workflows/download-pdf.yml` without `workflows` permission
```
این یک محدودیت امنیتی GitHub است و فقط از طریق وب‌سایت GitHub قابل ایجاد است.

## نحوه ساخت دستی (1 دقیقه)

1. به ریپازیتوری خود در GitHub بروید: https://github.com/mmr363637-afk/Book
2. برنچ را روی `arena/01a088aa-book` بگذارید
3. روی `Add file` → `Create new file` کلیک کنید
4. مسیر فایل را وارد کنید: `.github/workflows/download-pdf.yml`
5. محتوای زیر را کپی-پیست کنید:

```yaml
name: 📚 Download QB Surgery PDF

on:
  push:
    branches: [ "arena/01a088aa-book" ]
    paths:
      - '.github/workflows/download-pdf.yml'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  download:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: arena/01a088aa-book
          fetch-depth: 0

      - name: Try download PDF from admlink
        run: |
          set -e
          mkdir -p "جراحی"
          URL="https://sv3.admlink.ir/bot/dl/1564757/471703080/QB_جراحی_۱۴۰۴___جلد_اول__.pdf"
          URL_ENC="https://sv3.admlink.ir/bot/dl/1564757/471703080/QB_%D8%AC%D8%B1%D8%A7%D8%AD%DB%8C_%DB%B1%DB%B4%DB%B0%DB%B4___%D8%AC%D9%84%D8%AF_%D8%A7%D9%88%D9%84__.pdf"
          if curl -L -k -A "Mozilla/5.0" --retry 3 -o "جراحی/QB_جراحی_۱۴۰۴___جلد_اول__.pdf" "$URL"; then
            echo "✅ Downloaded via URL 1"
          else
            curl -L -k -A "Mozilla/5.0" --retry 3 -o "جراحی/QB_جراحی_۱۴۰۴___جلد_اول__.pdf" "$URL_ENC"
          fi
          ls -lh "جراحی/"
          file "جراحی/QB_جراحی_۱۴۰۴___جلد_اول__.pdf"

      - name: Commit and push PDF
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          # Handle LFS if >100MB
          SIZE=$(stat -c%s "جراحی/QB_جراحی_۱۴۰۴___جلد_اول__.pdf")
          if [ "$SIZE" -gt 104857600 ]; then
            git lfs install
            git lfs track "جراحی/*.pdf"
            git add .gitattributes
          fi
          git add "جراحی/QB_جراحی_۱۴۰۴___جلد_اول__.pdf"
          git commit -m "📚 افزودن فایل PDF QB جراحی ۱۴۰۴ جلد اول" || echo "Nothing to commit"
          git push origin HEAD:arena/01a088aa-book
```

6. روی `Commit changes` کلیک کنید (Direct to `arena/01a088aa-book`)
7. سپس به تب `Actions` بروید → Workflow را انتخاب کنید → `Run workflow` → Branch: `arena/01a088aa-book` → `Run`

> **نکته:** اگر دانلود در GitHub Actions هم به دلیل بلاک IP دیتاسنتر شکست خورد، تنها راه باقی‌مانده آپلود دستی فایل است (روش پیشنهادی: Attach در Arena).

---

## روش پیشنهادی (ساده‌تر)

فایل `QB_جراحی_۱۴۰۴___جلد_اول__.pdf` را روی سیستم خود دانلود کنید و در چت Arena به صورت **Attach File** ارسال کنید — من فوراً آن را به `جراحی/` اضافه و push می‌کنم.

