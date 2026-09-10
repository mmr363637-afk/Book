"""ocr/manifest.jsonl — one JSON record per page, the single source of truth
for pipeline state. Format:

  {"page": 1, "image": "ocr/pages/page_001.jpg", "image_dpi": 180,
   "status": "rasterized|awaiting_draft|drafted|verified|flagged",
   "has_text_layer": false, "raw": "ocr/raw/page_001.txt",
   "verified": "ocr/verified/page_001.txt", "flags": 2}
"""
import json

from .paths import MANIFEST, OCR

_STATUSES = ["rasterized", "awaiting_draft", "drafted", "verified", "flagged"]


def _read_all() -> dict[int, dict]:
    if not MANIFEST.exists():
        return {}
    out = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        out[rec["page"]] = rec
    return out


def _write_all(records: dict[int, dict]) -> None:
    OCR.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", encoding="utf-8") as f:
        for page in sorted(records):
            f.write(json.dumps(records[page], ensure_ascii=False) + "\n")


def get(page: int) -> dict | None:
    return _read_all().get(page)


def update(page: int, **fields) -> dict:
    records = _read_all()
    rec = records.get(page, {"page": page})
    rec.update(fields)
    if "status" in fields and fields["status"] not in _STATUSES:
        raise ValueError(f"unknown status {fields['status']}")
    records[page] = rec
    _write_all(records)
    return rec


def for_pages(pages) -> list[dict]:
    records = _read_all()
    return [records[p] for p in pages if p in records]


def all_records() -> list[dict]:
    records = _read_all()
    return [records[p] for p in sorted(records)]


def queue(status: str | None = None) -> list[dict]:
    return [r for r in all_records() if status is None or r.get("status") == status]
