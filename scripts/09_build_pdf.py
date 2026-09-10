#!/usr/bin/env python3
"""Stage 09 — Build PDF from the final HTML (Source of Truth).

SANDBOX DEVIATION (documented): WeasyPrint requires system Pango libraries
which cannot be installed here (no apt, restricted network). This renderer
implements the same contract — it consumes book/html/*.html (the single
document, no duplicated content) and produces print-ready A4 PDF:

  * parses the HTML contract (data-role / class / data-* attributes)
  * ReportLab paged layout: A4, margins, running header, page numbers
  * Persian shaping (arabic_reshaper + python-bidi), Vazirmatn fonts
  * page breaks: chapter → new page; keep heading with next block;
    tables split with repeated header; boxes keep together when they fit

Usage: python3 scripts/09_build_pdf.py [--out pdf/book.pdf]
"""
from __future__ import annotations

import html as html_mod
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config, paths, log, shape  # noqa: E402

from reportlab.lib.colors import HexColor, white, black  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas as _canvas  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    BaseDocTemplate, Frame, PageTemplate, Flowable, PageBreak, Spacer,
    NextPageTemplate, Table, TableStyle,
)

FONT = "Vazirmatn"
WEIGHTS = {
    "Vazirmatn-Light": "Light", "Vazirmatn": "Regular", "Vazirmatn-Medium": "Medium",
    "Vazirmatn-SemiBold": "SemiBold", "Vazirmatn-Bold": "Bold", "Vazirmatn-ExtraBold": "ExtraBold",
}
STATE = {"chapter_title": "", "book_title": "", "first_page": True}


def hexc(c: str) -> HexColor:
    c = str(c)
    return HexColor(c if c.startswith("#") else "#" + c)


def ascent(font: str, size: float) -> float:
    try:
        return pdfmetrics.ascent(font, size)
    except Exception:  # noqa: BLE001
        return size * 0.8


# ---------------------------------------------------------------- DOM parser
class Node:
    __slots__ = ("tag", "attrs", "children", "text_parts")

    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children: list[Node] = []
        self.text_parts: list[str] = []

    @property
    def cls(self) -> str:
        return self.attrs.get("class", "")

    def get(self, k, default=""):
        return self.attrs.get(k, default)

    def find_all(self, tag=None, cls=None) -> list[Node]:
        out = []
        for c in self.children:
            if (tag is None or c.tag == tag) and (cls is None or cls in c.cls.split()):
                out.append(c)
            out.extend(c.find_all(tag, cls))
        return out

    def find(self, tag=None, cls=None) -> Node | None:
        r = self.find_all(tag, cls)
        return r[0] if r else None

    def text(self) -> str:
        parts = []
        def walk(n: Node):
            parts.extend(n.text_parts)
            for c in n.children:
                walk(c)
        walk(self)
        return re.sub(r"\s+", " ", " ".join(parts)).strip()


class TreeBuilder(HTMLParser):
    VOID = {"img", "meta", "link", "br", "hr", "input"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if data.strip():
            self.stack[-1].text_parts.append(data)


def parse_html(path: Path) -> Node:
    b = TreeBuilder()
    b.feed(path.read_text(encoding="utf-8"))
    return b.root


# ---------------------------------------------------------------- flowables
class _W(Flowable):
    """Base for all custom flowables: auto-records available width (aw)
    into _width during wrap(), for use in draw()."""

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        w = cls.__dict__.get("wrap")
        if w is None:
            return

        def wrapped(self, aw, ah):
            self._width = aw
            return w(self, aw, ah)

        cls.wrap = wrapped


class RtlText(_W):
    """A shaped RTL/LTR-mixed paragraph, right-aligned within the frame."""

    def __init__(self, text, font="Vazirmatn", size=10.5, leading=17, color="1a2733",
                 space_before=0, space_after=6, indent_right=0, align="right"):
        super().__init__()
        self.raw = text or ""
        self.font = font
        self.size = size
        self.leading = leading
        self.color = color
        self.space_before = space_before
        self.space_after = space_after
        self.indent_right = indent_right
        self.align = align
        self._lines = []
        self._h = 0

    def wrap(self, aw, ah):
        w = aw - self.indent_right
        self._lines = shape.split_to_lines(self.raw, self.font, self.size, w) if self.raw else [""]
        self._h = self.space_before + self.leading * len(self._lines) + self.space_after
        return aw, self._h

    def split(self, aw, ah):
        if self._h <= ah:
            return []
        return [self]  # keep whole (short paragraphs); long ones pre-split by caller

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(hexc(self.color))
        c.setFont(self.font, self.size)
        top = self._h - self.space_after
        x = self._width - self.indent_right
        for i, line in enumerate(self._lines):
            y = top - i * self.leading - ascent(self.font, self.size)
            if self.align == "center":
                c.drawCentredString(self._width / 2, y, line)
            else:
                c.drawRightString(x, y, line)
        c.restoreState()


class BulletItem(_W):
    def __init__(self, text, font="Vazirmatn", size=10.5, leading=17, color="1a2733", space_after=3):
        super().__init__()
        self.text = text
        self.font = font
        self.size = size
        self.leading = leading
        self.color = color
        self.space_after = space_after
        self._lines = []
        self._h = 0

    def wrap(self, aw, ah):
        self._lines = shape.split_to_lines(self.text, self.font, self.size, aw - 16)
        self._h = self.leading * len(self._lines) + self.space_after
        return aw, self._h

    def split(self, aw, ah):
        return [] if self._h <= ah else [self]

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(hexc(self.color))
        c.setFont(self.font, self.size)
        top = self._h - self.space_after
        x_right = self._width
        for i, line in enumerate(self._lines):
            y = top - i * self.leading - ascent(self.font, self.size)
            if i == 0:
                c.drawRightString(x_right, y, "•")
                c.drawRightString(x_right - 12, y, line)
            else:
                c.drawRightString(x_right - 12, y, line)
        c.restoreState()


class SectionTitle(_W):
    """h3 lesson-section heading: teal, rule above, keep-with-next."""

    def __init__(self, text, size=12, color="0e6e6a", space_before=14, space_after=6):
        super().__init__()
        self.text = text
        self.size = size
        self.color = color
        self.space_before = space_before
        self.space_after = space_after
        self._h = 0

    def wrap(self, aw, ah):
        line = shape.shape_line(self.text)
        self._h = self.space_before + self.size + 4 + self.space_after
        return aw, self._h

    def split(self, aw, ah):
        return []

    def draw(self):
        c = self.canv
        c.saveState()
        y = self._h - self.space_before - ascent("Vazirmatn-Bold", self.size)
        c.setStrokeColor(hexc("d8e2e3"))
        c.setLineWidth(0.7)
        c.line(0, self._h - self.space_before + 6, self._width, self._h - self.space_before + 6)
        c.setFillColor(hexc(self.color))
        c.setFont("Vazirmatn-Bold", self.size)
        c.drawRightString(self._width, y, shape.shape_line(self.text))
        c.restoreState()


class TopicTitle(_W):
    def __init__(self, text, size=14.5):
        super().__init__()
        self.text = text
        self.size = size
        self._h = 0

    def wrap(self, aw, ah):
        self._h = 8 + self.size + 10
        return aw, self._h

    def split(self, aw, ah):
        return []

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(hexc("0e6e6a"))
        # right-edge accent bar (RTL)
        c.setFillColor(hexc("#0e6e6a"))
        c.rect(self._width - 4, 0, 4, self._h - 18, fill=1, stroke=0)
        c.setFont("Vazirmatn-ExtraBold", self.size)
        c.drawRightString(self._width - 14, self.size * 0.75, shape.shape_line(self.text))
        c.setStrokeColor(hexc("#0e6e6a"))
        c.setLineWidth(1.2)
        c.line(0, 2, self._width - 10, 2)
        c.restoreState()


class ChapterTitleFlow(_W):
    def __init__(self, title, subtitle=""):
        super().__init__()
        self.title = title
        self.subtitle = subtitle
        self._h = 0

    def wrap(self, aw, ah):
        sub_h = (24 if self.subtitle else 0)
        self._h = 30 + 34 + 14 + sub_h + 10
        return aw, self._h

    def split(self, aw, ah):
        return []

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(hexc("#0e6e6a"))
        c.setFont("Vazirmatn-ExtraBold", 26)
        c.drawCentredString(self._width / 2, self._h - ascent("Vazirmatn-ExtraBold", 26) - 24,
                            shape.shape_line(self.title))
        c.setStrokeColor(hexc("#e3a92c"))
        c.setLineWidth(2.4)
        c.line(self._width / 2 - 60, self._h - 44, self._width / 2 + 60, self._h - 44)
        if self.subtitle:
            c.setFillColor(hexc("#4a5a6a"))
            c.setFont("Vazirmatn-Medium", 12)
            c.drawCentredString(self._width / 2, self._h - 62, shape.shape_line(self.subtitle))
        c.restoreState()
        STATE["chapter_title"] = self.title


class BoxFlow(_W):
    """High-yield / callout box: rounded rect + label + text, keeps together."""

    def __init__(self, text, kind="highyield"):
        super().__init__()
        self.text = text
        if kind == "highyield":
            self.bg, self.border, self.label = "fff6df", "e3a92c", "✦ نکته کلیدی"
        else:
            self.bg, self.border, self.label = "eaf1fb", "3f6fb5", "یادآوری"
        self._h = 0

    def wrap(self, aw, ah):
        t = RtlText(self.text, size=10.5, leading=17, color="3a3a2a" if self.bg == "fff6df" else "2a3a4a",
                    space_after=0)
        t.wrap(aw - 24, ah)
        self._inner_lines = t._lines
        # height: top pad 10 + label 13 + gap 5 + lines*17 + bottom pad 9
        self._h = 17 * len(t._lines) + 37
        self._fits = self._h <= ah
        return aw, self._h

    def split(self, aw, ah):
        if self._fits:
            return []
        return [self]

    def draw(self):
        c = self.canv
        c.saveState()
        pad = 10
        c.setFillColor(hexc(self.bg))
        c.setStrokeColor(hexc(self.border))
        c.setLineWidth(1.1)
        # RTL: thicker accent on the right edge
        c.roundRect(0, 0, self._width, self._h, 6, fill=1, stroke=0)
        c.setFillColor(hexc(self.border))
        c.rect(self._width - 3.5, 0, 3.5, self._h, fill=1, stroke=0)
        c.setStrokeColor(hexc(self.border))
        c.setLineWidth(0.8)
        c.roundRect(0, 0, self._width, self._h, 6, fill=0, stroke=1)
        # label
        c.setFont("Vazirmatn-Bold", 9)
        c.setFillColor(hexc(self.border))
        c.drawRightString(self._width - pad, self._h - 18.5, shape.shape_line(self.label))
        # body
        c.setFillColor(hexc("3a3a2a") if self.bg == "fff6df" else hexc("2a3a4a"))
        c.setFont("Vazirmatn", 10.5)
        for i, line in enumerate(self._inner_lines):
            c.drawRightString(self._width - pad, self._h - 32.4 - i * 17, line)
        c.restoreState()


class CellText(_W):
    def __init__(self, text, header=False, size=9.5):
        super().__init__()
        self.text = text or ""
        self.header = header
        self.size = size
        self._lines = []
        self._h = 0

    def wrap(self, aw, ah):
        self._lines = shape.split_to_lines(self.text, "Vazirmatn-Medium" if self.header else "Vazirmatn",
                                           self.size, aw - 8)
        self._h = 13 * len(self._lines)
        return aw, self._h

    def split(self, aw, ah):
        return []

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(white if self.header else hexc("#1a2733"))
        c.setFont("Vazirmatn-Medium" if self.header else "Vazirmatn", self.size)
        for i, line in enumerate(self._lines):
            c.drawRightString(self._width - 4, self._h - i * 13 - self.size * 0.8, line)
        c.restoreState()


class TableFlow(_W):
    """Data table; splits across pages with repeated header (RTL column order)."""

    def __init__(self, headers, rows, caption=""):
        super().__init__()
        self.headers = headers
        self.rows = rows
        self.caption = caption
        self._tbl = None
        self._h = 0
        self._w = 0

    def _build(self, avail_w):
        ncols = len(self.headers)
        # per-column content width (original order), then reverse for RTL
        all_cells = [[self.headers[i] for i in range(ncols)]] + [
            [r[i] if i < len(r) else "" for i in range(ncols)] for r in self.rows]
        col_w = []
        for i in range(ncols):
            w = 0
            for row in all_cells:
                line = shape.shape_line(str(row[i]))
                w = max(w, pdfmetrics.stringWidth(line, "Vazirmatn", 9.5))
            col_w.append(min(max(w + 10, 34), avail_w * 0.45))
        scale = avail_w / sum(col_w) if sum(col_w) else 1
        col_w = [max(28, w * scale) for w in col_w]
        rev = list(range(ncols - 1, -1, -1))  # column 0 of table = last header (leftmost)
        data = [[CellText(self.headers[rev[j]], header=True) for j in range(ncols)]]
        for r in self.rows:
            data.append([CellText(r[rev[j]] if rev[j] < len(r) else "", header=False) for j in range(ncols)])
        self._tbl = Table(data, colWidths=col_w, repeatRows=1, hAlign="LEFT")
        self._tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), hexc("#0e6e6a")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, hexc("#f4f8f8")]),
            ("GRID", (0, 0), (-1, -1), 0.5, hexc("#c9d6d8")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ]))

    def wrap(self, aw, ah):
        if self._tbl is None:
            self._build(aw)
        self._w, self._h = self._tbl.wrap(aw, ah)
        cap_h = 16 if self.caption else 0
        return aw, self._h + cap_h

    def split(self, aw, ah):
        if self._tbl is None:
            self._build(aw)
        cap_h = 16 if self.caption else 0
        parts = self._tbl.split(aw, ah - cap_h)
        if len(parts) <= 1:
            return []
        return parts  # platypus Tables know how to draw themselves

    def draw(self):
        self.canv.saveState()
        self._tbl.drawOn(self.canv, 0, 16 if self.caption else 0)
        if self.caption:
            c = self.canv
            c.setFont("Vazirmatn-Medium", 9)
            c.setFillColor(hexc("#4a5a6a"))
            c.drawCentredString(self._width / 2, 2, shape.shape_line(self.caption))
        self.canv.restoreState()


class FigureFlow(_W):
    def __init__(self, img_path: Path, caption=""):
        super().__init__()
        self.img_path = img_path
        self.caption = caption
        self._w = 0
        self._h = 0

    def wrap(self, aw, ah):
        from PIL import Image
        with Image.open(self.img_path) as im:
            iw, ih = im.size
        max_w = aw * 0.86
        scale = min(1.0, max_w / iw)
        self._w = iw * scale
        self._h = ih * scale + (16 if self.caption else 0)
        return self._w, self._h

    def split(self, aw, ah):
        return [] if self._h <= ah else [self]

    def draw(self):
        c = self.canv
        c.saveState()
        from PIL import Image
        with Image.open(self.img_path) as im:
            iw, ih = im.size
        cap_h = 16 if self.caption else 0
        h = self._h - cap_h
        x = (self._width - self._w) / 2
        c.drawImage(str(self.img_path), x, cap_h, width=self._w, height=h,
                    preserveAspectRatio=True, anchor="c")
        if self.caption:
            c.setFont("Vazirmatn-Medium", 9)
            c.setFillColor(hexc("#4a5a6a"))
            c.drawCentredString(self._width / 2, 2, shape.shape_line(self.caption))
        c.restoreState()


class QuestionCard(_W):
    def __init__(self, qid, source_page, stem, options, answer, explanation, notes):
        super().__init__()
        self.qid = qid
        self.source_page = source_page
        self.stem = stem
        self.options = options  # list[(key, text)]
        self.answer = answer
        self.explanation = explanation
        self.notes = notes
        self._h = 0

    def wrap(self, aw, ah):
        c_width = aw - 20
        h = 8 + 14  # head
        lines = shape.split_to_lines(self.stem, "Vazirmatn", 10.5, c_width)
        h += 17 * len(lines) + 4
        for k, v in self.options:
            ol = shape.split_to_lines(v, "Vazirmatn", 10.5, c_width - 20)
            h += 17 * len(ol) + 3
        h += 26  # answer bar
        if self.explanation:
            el = shape.split_to_lines(self.explanation, "Vazirmatn", 9.8, c_width)
            h += 14 * len(el) + 8
        if self.notes:
            nl = shape.split_to_lines(self.notes, "Vazirmatn-Light", 9.3, c_width)
            h += 13 * len(nl) + 6
        h += 8  # bottom pad
        self._h = h
        self._c_width = c_width
        self._stem_lines = lines
        self._opt_lines = [shape.split_to_lines(v, "Vazirmatn", 10.5, c_width - 20) for _, v in self.options]
        self._expl_lines = shape.split_to_lines(self.explanation, "Vazirmatn", 9.8, c_width) if self.explanation else []
        self._notes_lines = shape.split_to_lines(self.notes, "Vazirmatn-Light", 9.3, c_width) if self.notes else []
        return aw, self._h

    def split(self, aw, ah):
        return [] if self._h <= ah else [self]

    def draw(self):
        c = self.canv
        c.saveState()
        pad = 10
        # card background
        c.setFillColor(hexc("#f7f9fa"))
        c.setStrokeColor(hexc("#9db4b8"))
        c.setLineWidth(0.9)
        c.roundRect(0, 0, self._width, self._h, 5, fill=1, stroke=1)
        y = self._h - pad
        # head
        c.setFont("Vazirmatn-Bold", 9)
        c.setFillColor(hexc("#0e6e6a"))
        head = f"سؤال {self.qid}  ·  صفحه منبع: {self.source_page}"
        c.drawRightString(self._width - pad, y - 9, shape.shape_line(head))
        y -= 24
        # stem
        c.setFont("Vazirmatn-Medium", 10.5)
        c.setFillColor(hexc("#1a2733"))
        for line in self._stem_lines:
            c.drawRightString(self._width - pad, y - 10.5 * 0.8, line)
            y -= 17
        y -= 4
        # options
        for (k, _v), olines in zip(self.options, self._opt_lines):
            c.setFont("Vazirmatn", 10.5)
            correct = (k == self.answer)
            for i, line in enumerate(olines):
                yy = y - 10.5 * 0.8
                if i == 0:
                    c.setFillColor(hexc("#0e6e6a") if correct else hexc("#4a5a6a"))
                    c.setFont("Vazirmatn-Bold", 10.5)
                    c.drawRightString(self._width - pad, yy, k.upper())
                    c.setFont("Vazirmatn", 10.5)
                    c.setFillColor(hexc("#0e6e6a") if correct else hexc("#1a2733"))
                    c.drawRightString(self._width - pad - 18, yy, line)
                else:
                    c.setFillColor(hexc("#1a2733"))
                    c.drawRightString(self._width - pad - 18, yy, line)
                y -= 17
            y -= 3
        # answer bar
        y -= 4
        c.setFillColor(hexc("#e7f2f1"))
        c.setStrokeColor(hexc("#0e6e6a"))
        c.setLineWidth(0.8)
        c.roundRect(pad, y - 18, self._width - 2 * pad, 22, 4, fill=1, stroke=1)
        c.setFont("Vazirmatn-Bold", 10.5)
        c.setFillColor(hexc("#0e6e6a"))
        c.drawRightString(self._width - pad - 8, y - 10, shape.shape_line(f"پاسخ: {self.answer.upper()}"))
        y -= 26
        if self._expl_lines:
            c.setFont("Vazirmatn", 9.8)
            c.setFillColor(hexc("#33424f"))
            for i, line in enumerate(self._expl_lines):
                c.drawRightString(self._width - pad, y - 9.8 * 0.8 - i * 14, line)
            y -= 14 * len(self._expl_lines) + 8
        if self._notes_lines:
            c.setFont("Vazirmatn-Light", 9.3)
            c.setFillColor(hexc("#6a7a86"))
            for i, line in enumerate(self._notes_lines):
                c.drawRightString(self._width - pad, y - 9.3 * 0.8 - i * 13, line)
        c.restoreState()


class SourcePageNote(_W):
    def __init__(self, text):
        super().__init__()
        self.text = text
        self._h = 16

    def wrap(self, aw, ah):
        return aw, self._h

    def split(self, aw, ah):
        return []

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont("Vazirmatn-Light", 8.5)
        c.setFillColor(hexc("#8a98a3"))
        c.drawRightString(self._width, 4, shape.shape_line(self.text))
        c.restoreState()


# ---------------------------------------------------------------- builders
def build_from_html(root: Node, cfg: dict, doc) -> list:
    flows: list = []
    rcfg = doc.rcfg
    chapters = root.find_all(cls="chapter")
    first = True
    for ch in chapters:
        if not first:
            flows.append(PageBreak())
        first = False
        head = ch.find(cls="chapter-head")
        title = head.find("h1").text() if head and head.find("h1") else ch.get("data-chapter", "")
        sub_node = head.find(cls="chapter-sub") if head else None
        flows.append(Spacer(1, 10))
        flows.append(ChapterTitleFlow(title, sub_node.text() if sub_node else ""))
        flows.append(Spacer(1, 18))
        for topic in ch.find_all(cls="topic"):
            tnode = topic.find(cls="topic-title")
            if tnode:
                flows.append(TopicTitle(tnode.text()))
                flows.append(Spacer(1, 8))
            lesson = topic.find(cls="lesson")
            if lesson:
                for sec in lesson.find_all(cls="lesson-section"):
                    h3 = sec.find("h3")
                    if h3:
                        from reportlab.platypus import KeepTogether
                        flows.append(KeepTogether([SectionTitle(h3.text())]))
                    for b in sec.children:
                        flows.extend(build_block(b, rcfg))
            fu = topic.find(cls="followup")
            if fu:
                flows.append(Spacer(1, 10))
                flows.append(SectionTitle("Follow Up", size=13))
                for b in fu.children:
                    if b.tag in ("div", "ul", "figure") and b.cls:
                        flows.extend(build_block(b, rcfg))
                    elif b.tag == "p":
                        flows.append(RtlText(b.text(), size=rcfg["fonts"]["body_size"],
                                             leading=rcfg["fonts"]["body_leading"], space_after=7,
                                             indent_right=10))
            recall = topic.find(cls="recall")
            if recall:
                flows.append(Spacer(1, 10))
                flows.append(SectionTitle("Active Recall — به یاد آورید", size=13))
                ol = recall.find("ol")
                if ol:
                    for i, li in enumerate(ol.find_all(tag="li"), 1):
                        rq = li.find(tag="span", cls="rq")
                        ra = li.find(tag="span", cls="ra")
                        q = rq.text() if rq else li.text()
                        a = ra.text() if ra else ""
                        lines = shape.split_to_lines(f"{i}. {q}", "Vazirmatn-Medium", 10.5, doc.frame_w - 16)
                        if a:
                            lines2 = shape.split_to_lines(f"   پاسخ: {a}", "Vazirmatn-Light", 9.8, doc.frame_w - 20)
                        else:
                            lines2 = []
                        flows.append(_MultiLine(lines, lines2))
            tests = topic.find(cls="tests")
            if tests:
                flows.append(Spacer(1, 12))
                flows.append(SectionTitle("تست‌های این موضوع", size=13))
                for qart in tests.find_all(cls="question"):
                    opts = []
                    for li in qart.find_all(cls="opt"):
                        opts.append((li.get("data-opt"), li.text()))
                    expl = qart.find(cls="explanation")
                    notes = qart.find(cls="key-notes")
                    card = QuestionCard(
                        qart.get("data-qid"), qart.get("data-source-page"),
                        (qart.find(cls="stem") or _txt_node(qart)).text(),
                        opts, qart.find(cls="answer-key") and _answer_letter(qart) or "",
                        expl.text() if expl else "", notes.text() if notes else "")
                    flows.append(KeepTogether([card]))
            ftr = topic.find(cls="topic-pages")
            if ftr:
                flows.append(Spacer(1, 6))
                flows.append(SourcePageNote(ftr.text()))
            flows.append(Spacer(1, 14))
    return flows


def _txt_node(text):
    n = Node("p", {})
    n.text_parts = [text]
    return n


def _answer_letter(qart: Node) -> str:
    ak = qart.find(cls="answer-key")
    return (ak.get("data-answer") if ak else "") or ""


class _MultiLine(_W):
    def __init__(self, qlines, alines):
        super().__init__()
        self.qlines = qlines
        self.alines = alines
        self._h = 0

    def wrap(self, aw, ah):
        self._h = 17 * len(self.qlines) + 14 * len(self.alines) + 8
        return aw, self._h

    def split(self, aw, ah):
        return [] if self._h <= ah else [self]

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(hexc("#1a2733"))
        c.setFont("Vazirmatn-Medium", 10.5)
        y = self._h - 10.5 * 0.8
        for line in self.qlines:
            c.drawRightString(self._width, y, line)
            y -= 17
        c.setFont("Vazirmatn-Light", 9.8)
        c.setFillColor(hexc("#5a6a76"))
        for line in self.alines:
            c.drawRightString(self._width - 14, y - 9.8 * 0.8, line)
            y -= 14
        c.restoreState()


def build_block(b: Node, rcfg) -> list:
    out = []
    if b.tag == "p" and not b.cls:
        out.append(RtlText(b.text(), size=rcfg["fonts"]["body_size"],
                           leading=rcfg["fonts"]["body_leading"], space_after=7))
    elif b.tag == "ul" and "bullets" in b.cls:
        for li in b.find_all(tag="li"):
            out.append(BulletItem(li.text()))
        out.append(Spacer(1, 4))
    elif b.tag == "figure" and "table-fig" in b.cls:
        tbl = b.find(tag="table")
        if tbl:
            th = tbl.find("thead")
            headers = [td.text() for td in th.find_all("th")] if th else []
            rows = [[td.text() for td in tr.find_all("td")] for tr in tbl.find("tbody").find_all("tr")] if tbl.find("tbody") else []
            cap = b.find("figcaption")
            out.append(TableFlow(headers, rows, cap.text() if cap else ""))
            out.append(Spacer(1, 6))
    elif b.tag == "figure" and "img-fig" in b.cls:
        img = b.find("img")
        if img:
            src = Path(img.get("src"))
            if not src.is_absolute():
                src = (Path("book/html") / img.get("src")).resolve()
            cap = b.find("figcaption")
            if src.exists():
                out.append(FigureFlow(src, cap.text() if cap else ""))
                out.append(Spacer(1, 6))
    elif b.tag == "div" and "highyield" in b.cls:
        out.append(BoxFlow(_box_text(b), "highyield"))
        out.append(Spacer(1, 6))
    elif b.tag == "div" and "callout" in b.cls:
        out.append(BoxFlow(_box_text(b), "callout"))
        out.append(Spacer(1, 6))
    return out


def _box_text(b: Node) -> str:
    # strip the label span, keep the rest
    parts = []
    for c in b.children:
        if c.tag == "span":
            continue
        parts.extend(c.text_parts)
        for cc in c.children:
            parts.extend(cc.text_parts)
    t = re.sub(r"\s+", " ", " ".join(parts)).strip()
    return t or b.text()


# ---------------------------------------------------------------- page decor
def cover_page(canv: "_canvas.Canvas", doc) -> None:
    STATE["first_page"] = True
    w, h = A4
    canv.saveState()
    canv.setFillColor(hexc("#0e6e6a"))
    canv.rect(0, 0, w, h, fill=1, stroke=0)
    canv.setFillColor(hexc("#e3a92c"))
    canv.rect(0, h - 14, w, 14, fill=1, stroke=0)
    canv.rect(0, 0, w, 14, fill=1, stroke=0)
    STATE["first_page"] = False
    canv.restoreState()


def body_page(canv: "_canvas.Canvas", doc) -> None:
    w, h = A4
    canv.saveState()
    # running header
    canv.setFont("Vazirmatn-Light", 8.5)
    canv.setFillColor(hexc("#8a98a3"))
    rc = config.load_book_config()
    book_title = (rc["book"].get("title") or "").strip()
    if book_title:
        canv.drawString(40, h - 30, shape.shape_line(book_title))
    canv.setStrokeColor(hexc("#d8e2e3"))
    canv.setLineWidth(0.6)
    canv.line(40, h - 38, w - 40, h - 38)
    # footer: page number
    canv.setFont("Vazirmatn-Medium", 9)
    canv.setFillColor(hexc("#5a6a76"))
    canv.drawCentredString(w / 2, 24, str(doc.page))
    canv.restoreState()


def body_page_end(canv: "_canvas.Canvas", doc) -> None:
    """Page end: running header — chapter title (only known after draw())."""
    w, h = A4
    if doc.page <= 1 or not STATE["chapter_title"]:
        return
    canv.saveState()
    canv.setFont("Vazirmatn-Light", 8.5)
    canv.setFillColor(hexc("#8a98a3"))
    canv.drawRightString(w - 40, h - 30, shape.shape_line(STATE["chapter_title"]))
    canv.restoreState()


class BookDoc(BaseDocTemplate):
    def __init__(self, filename, rcfg):
        self.rcfg = rcfg
        self.frame_w = 0
        super().__init__(str(filename), pagesize=A4)
        pg = rcfg["page"]
        self.leftMargin = pg["margin_inner"]
        self.rightMargin = pg["margin_outer"]
        self.topMargin = pg["margin_top"]
        self.bottomMargin = pg["margin_bottom"]
        w, h = A4
        fw = w - self.leftMargin - self.rightMargin
        fh = h - self.topMargin - self.bottomMargin
        self.frame_w = fw
        frame = Frame(self.leftMargin, self.bottomMargin, fw, fh, id="main",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[frame], onPage=cover_page),
            PageTemplate(id="body", frames=[frame], onPage=body_page, onPageEnd=body_page_end),
        ])


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()

    rcfg = config.load_render_config()
    cfg = config.load_book_config()
    paths.ensure_dirs()

    # register fonts
    for name, weight in WEIGHTS.items():
        pdfmetrics.registerFont(TTFont(name, str(paths.FONTS / f"Vazirmatn-{weight}.ttf")))

    out = Path(args.out) if args.out else paths.PDF / "book.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    index = paths.HTML / "index.html"
    if not index.exists():
        raise SystemExit("book/html/index.html missing — run stage 08 first")

    # cover flows from index.html
    root = parse_html(index)
    cover_node = root.find(cls="cover")
    cover_flows: list = []
    if cover_node:
        title = cover_node.find("h1")
        if title:
            cover_flows.append(Spacer(1, 180))
            cover_flows.append(_CoverTitle(title.text()))
        sub_en = cover_node.find(cls="cover-title-en")
        if sub_en:
            cover_flows.append(Spacer(1, 14))
            cover_flows.append(RtlText(sub_en.text(), font="Vazirmatn-Light", size=13,
                                       color="ffffff", align="center", space_after=10))
        author = cover_node.find(cls="cover-author")
        if author:
            cover_flows.append(RtlText(author.text(), font="Vazirmatn", size=11,
                                       color="d8e8e7", align="center"))
        meta = cover_node.find(cls="cover-meta")
        if meta:
            cover_flows.append(Spacer(1, 40))
            cover_flows.append(RtlText(meta.text(), font="Vazirmatn-Light", size=9.5,
                                       color="b8d2d0", align="center"))

    doc = BookDoc(out, rcfg)
    flows = []
    flows.append(NextPageTemplate("body"))
    flows.extend(cover_flows)
    flows.append(PageBreak())
    # chapters
    for cfile in sorted(paths.HTML_CHAPTERS.glob("ch*.html")):
        root = parse_html(cfile)
        flows.extend(build_from_html(root, cfg, doc))

    doc.build(flows)
    import pymupdf
    d = pymupdf.open(str(out))
    npages = d.page_count
    d.close()
    log.info("09_build_pdf", f"built {out.name}: {npages} pages")
    print(f"OK: {out} ({npages} pages)")


class _CoverTitle(_W):
    def __init__(self, text):
        super().__init__()
        self.text = text
        self._h = 0

    def wrap(self, aw, ah):
        self._lines = shape.split_to_lines(self.text, "Vazirmatn-ExtraBold", 30, aw)
        self._h = 40 * len(self._lines)
        return aw, self._h

    def split(self, aw, ah):
        return []

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont("Vazirmatn-ExtraBold", 30)
        c.setFillColor(white)
        for i, line in enumerate(self._lines):
            c.drawCentredString(self._width / 2, self._h - i * 40 - ascent("Vazirmatn-ExtraBold", 30), line)
        c.restoreState()


if __name__ == "__main__":
    main()
