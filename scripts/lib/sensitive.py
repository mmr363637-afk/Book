"""Sensitive medical tokens — the classes of strings where OCR errors are
dangerous and where the verified text must be reconciled against the page
image. Used by 06_verify_report.py and 10_qa.py."""
import re
import unicodedata

_PATTERNS: dict[str, re.Pattern] = {
    "percent": re.compile(r"\d+(?:[.,]\d+)?\s*[%٪]"),
    "dose": re.compile(
        r"\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|ug|g|ml|mmol|µmol|umol|IU|mIU|TE|U|g%)\b",
        re.IGNORECASE,
    ),
    "lab_value": re.compile(r"\d+(?:[.,]\d+)?\s*(?:/\s*(?:mmol|mg|µg|umol|g)|mmol/L|mg/dL|mg/L|ng/mL|U/L)"),
    "pressure": re.compile(r"\d+(?:[.,]\d+)?\s*mmHg"),
    "pH": re.compile(r"pH\s*[<>≥≤=]*\s*\d+(?:[.,]\d+)?", re.IGNORECASE),
    "cutoff": re.compile(
        r"(?:cut[- ]?off|threshold|criterion|criteria|حد\s*\u06a9\u0627\u0631\u06cc|آ\u06af\u0627\u062d)\s*[:=\u201c\u201d]?\s*[<>≥≤±]?\s*\d+(?:[.,]\d+)?",
        re.IGNORECASE,
    ),
    "inequality": re.compile(r"[<>≥≤]\s*\d+(?:[.,]\d+)?"),
    "negative_question": re.compile(r"نیست|به\s*جز|بجز|ما|کدام(?!-)\s"),
    "answer_word": re.compile(r"درست\s*است|غلط\s*است|صحیح|غلط"),
    "year": re.compile(r"\b(?:19|20)\d{2}\b"),
    "ratio": re.compile(r"\d+\s*[:/]\s*\d+"),
    "drug_latin": re.compile(r"\b[A-Z][a-zA-Z\-]{3,}(?:\s*\d{1,2})?\b"),
}

# Persian digits → ASCII
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize(token: str) -> str:
    """Canonical form used for set-membership cross-checks."""
    t = unicodedata.normalize("NFC", token)
    t = t.translate(_FA_DIGITS)
    t = t.replace("٬", ",").replace("٫", ".").replace("٪", "%")
    t = re.sub(r"\s+", " ", t).strip()
    return t.lower()


def find_sensitive(text: str) -> list[dict]:
    """Return all sensitive tokens found in `text`, each with kind + span."""
    found = []
    for kind, pat in _PATTERNS.items():
        for m in pat.finditer(text):
            tok = m.group(0)
            if kind == "drug_latin" and len(tok) < 4:
                continue
            found.append({"kind": kind, "token": tok, "norm": normalize(tok), "span": list(m.span())})
    # de-duplicate by (norm, kind), keep first
    seen = set()
    out = []
    for f in found:
        key = (f["norm"], f["kind"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out
