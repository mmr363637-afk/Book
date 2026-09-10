# راهنمای آپلود فایل PDF

اگر دانلود خودکار در GitHub Actions به دلیل بلاک شدن IP دیتاسنتر موفق نشد، لطفاً این مراحل را به صورت دستی انجام دهید:

## روش ۱: آپلود از طریق Arena (پیشنهادی)
1. فایل `QB_جراحی_۱۴۰۴___جلد_اول__.pdf` را روی سیستم خود دانلود کنید (لینک: https://sv3.admlink.ir/bot/dl/1564757/471703080/QB_جراحی_۱۴۰۴___جلد_اول__.pdf )
2. در چت Arena روی دکمه 📎 Attach File کلیک کنید و PDF را آپلود کنید
3. من فایل را به ریپازیتوری اضافه و push می‌کنم

## روش ۲: آپلود دستی به GitHub
```bash
git clone https://github.com/mmr363637-afk/Book.git
cd Book
git checkout arena/01a088aa-book
# فایل PDF دانلود شده را کپی کنید به:
mkdir -p "جراحی"
cp ~/Downloads/QB_جراحی_۱۴۰۴___جلد_اول__.pdf "جراحی/"
git add "جراحی/QB_جراحی_۱۴۰۴___جلد_اول__.pdf"
git commit -m "افزودن فایل PDF QB جراحی ۱۴۰۴ جلد اول"
git push origin arena/01a088aa-book
```

## روش ۳: استفاده از GitHub Actions
این ریپو دارای Workflow خودکار است (`.github/workflows/download-pdf.yml`).
- هر بار که این Workflow تغییر کند یا دستی اجرا شود، سعی می‌کند فایل را دانلود کند.
- برای اجرای دستی: به تب Actions در GitHub بروید → Download QB Surgery PDF → Run workflow → Branch: arena/01a088aa-book

---

اگر فایل حجیم‌تر از 100MB باشد، به صورت خودکار از Git LFS استفاده می‌شود.
