"""Persian text shaping + line breaking for the PDF renderer.

ReportLab does not shape Arabic-script text, so every line is:
  1. reshaped (contextual letter forms) with arabic_reshaper
  2. reordered visually (RTL) with python-bidi
Line breaking is done on the *display-ordered* string so wrapped lines keep
correct visual order and alignment.
"""
import arabic_reshaper
from bidi.algorithm import get_display

from reportlab.pdfbase.pdfmetrics import stringWidth


def shape_line(text: str) -> str:
    """Shaping + bidi for a single visual line."""
    if not text:
        return text
    return get_display(arabic_reshaper.reshape(text))


def split_to_lines(text: str, fontname: str, size: float, max_width: float) -> list[str]:
    """Break `text` (logical order, may contain \n) into display-ordered
    visual lines, each fitting within max_width."""
    lines: list[str] = []
    for para in text.split("\n"):
        para = para.strip("\u200b")
        if not para:
            lines.append("")
            continue
        # Greedy word wrap on the logical string; each line is shaped once.
        words = para.split(" ")
        cur = ""
        for w in words:
            candidate = f"{cur} {w}".strip()
            width = stringWidth(shape_line(candidate), fontname, size)
            if width <= max_width or not cur:
                cur = candidate
            else:
                lines.append(shape_line(cur))
                cur = w
        lines.append(shape_line(cur))
    return lines


def fit_lines(text: str, fontname: str, size: float, max_width: float, leading: float) -> tuple[list[str], float]:
    lines = split_to_lines(text, fontname, size, max_width)
    return lines, leading * len(lines)


def line_height(size: float, leading: float) -> float:
    return leading
