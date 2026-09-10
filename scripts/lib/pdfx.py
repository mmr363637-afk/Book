"""PyMuPDF helpers: source registration, page rasterization, page auditing."""
import hashlib
import json

import pymupdf  # PyMuPDF


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pdf_meta(path) -> dict:
    doc = pymupdf.open(path)
    info = doc.metadata or {}
    meta = {
        "pages": doc.page_count,
        "page_size_pt": [round(doc[0].rect.width, 1), round(doc[0].rect.height, 1)],
        "metadata": {
            "title": info.get("title") or "",
            "author": info.get("author") or "",
            "creator": info.get("creator") or "",
            "producer": info.get("producer") or "",
        },
        "embedded_fonts": len(doc.get_page_fonts(0)) if doc.page_count else 0,
    }
    doc.close()
    return meta


def has_text_layer(doc, page: int, min_chars: int = 40) -> bool:
    """A scanned page has no (or almost no) extractable text."""
    text = doc[page].get_text("text").strip()
    return len(text) >= min_chars


def rasterize_page(doc, page: int, dpi: int) -> "pymupdf.Pixmap":
    """Render one page to a pixmap (160 dpi default). Callers must free it."""
    zoom = dpi / 72.0
    pix = doc[page].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return pix


def ink_stats(doc, page: int, sample_dpi: int = 50) -> dict:
    """Cheap per-page image stats used by source analysis (stage 2)."""
    from PIL import Image
    import io

    pix = rasterize_page(doc, page, sample_dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    pix.agg = 0  # release underlying buffer reference
    pixels = list(img.getdata())
    n = len(pixels)
    mean = sum(pixels) / n
    dark = sum(1 for p in pixels if p < 128) / n
    # vertical profile: fraction of dark pixels in top 15% vs rest
    w, h = img.size
    top = list(img.crop((0, 0, w, max(1, int(h * 0.15)))).getdata())
    top_dark = sum(1 for p in top if p < 128) / len(top)
    return {"mean_gray": round(mean, 1), "ink_frac": round(dark, 4), "top_ink_frac": round(top_dark, 4)}


def save_jpeg(pix, path, quality: int = 82) -> None:
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    img.save(path, "JPEG", quality=quality, optimize=True)


def audit_pages(path) -> list[dict]:
    """Stage 2: per-page audit without OCR. Returns list of records."""
    doc = pymupdf.open(path)
    records = []
    for i in range(doc.page_count):
        try:
            stats = ink_stats(doc, i)
        except Exception as e:  # noqa: BLE001
            stats = {"error": str(e)}
        records.append({
            "page": i + 1,
            "has_text_layer": has_text_layer(doc, i),
            **stats,
        })
    doc.close()
    return records
