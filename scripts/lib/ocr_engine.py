"""Mechanical OCR layer — LATIN/NUMERIC TOKEN CROSS-CHECK.

Architecture note (important):
  The *primary* OCR in this project is vision-based: the agent reads the
  original page images directly (raw draft pass + verification pass), because
  in this sandbox no Persian-capable OCR engine model can be downloaded
  (HuggingFace / modelscope / release-asset hosts are network-blocked).

  This module provides the independent *mechanical* second opinion for the
  token classes where it is strong: Latin letters, digits, units — i.e. drug
  names, dosages, lab values, percentages, years. Its output (with confidence
  and bbox) is stored per page and reconciled against the agent's verified
  text by 06_verify_report.py. A disagreement is a flag, not an error.

  The interface is engine-agnostic: on a machine with internet access you can
  drop in tesseract/fa or PaddleOCR-fa by implementing `run_on_image`.
"""
import json
import re
from pathlib import Path

_LATIN_TOKEN = re.compile(r"^[!-~ ]+$")  # printable ASCII


class LatinCrosscheck:
    def __init__(self, min_conf: float = 0.6):
        self.min_conf = min_conf
        self._ocr = None

    def _load(self):
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
        return self._ocr

    def run_on_image(self, image_path: Path) -> list[dict]:
        """Return [{token, conf, bbox}] for ASCII-token candidates only."""
        ocr = self._load()
        result, _elapsed = ocr(str(image_path))
        tokens = []
        if not result:
            return tokens
        for line in result:
            # line: [bbox, text, score]
            bbox, text, score = line[0], str(line[1]), float(line[2])
            for part in re.split(r"\s+", text.strip()):
                part = part.strip(".,;:()[]{}")
                if not part or not _LATIN_TOKEN.match(part):
                    continue
                if score < self.min_conf:
                    continue
                # keep only tokens with at least one alnum
                if not re.search(r"[0-9A-Za-z]", part):
                    continue
                tokens.append({
                    "token": part,
                    "conf": round(score, 3),
                    "bbox": [[int(x), int(y)] for x, y in bbox],
                })
        return tokens


def save_crosscheck(image_path: Path, out_path: Path, tokens: list[dict]) -> None:
    out_path.write_text(
        json.dumps({"image": str(image_path), "tokens": tokens}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


def load_crosscheck(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("tokens", [])


def token_set(tokens: list[dict]) -> set[str]:
    return {t["token"] for t in tokens}
