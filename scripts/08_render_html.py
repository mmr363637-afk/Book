#!/usr/bin/env python3
"""Stage 08 — Render HTML (the Source of Truth for presentation).

Reads content/chapters + content/topics YAML and emits:
  book/html/index.html          cover + TOC (book shell, links chapters)
  book/html/chapters/chNN.html  one file per chapter

HTML CONTRACT (data-role attributes — the PDF renderer, stage 09,
consumes the same document; no content is duplicated for the PDF):
  article.chapter > header.chapter-head (h1 + .chapter-sub)
  section.topic[data-topic]
    h2.topic-title
    section.lesson > div.lesson-section[data-section]
    section.followup[data-followup]
    section.recall > ol.recall-list > li[data-from]
    section.tests > article.question[data-qid][data-source-page]
Blocks: p | ul.bullets | table.data-table | figure>img | div.highyield | div.callout
"""
import html
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config, paths, log  # noqa: E402


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def render_block(b: dict) -> str:
    t = b["type"]
    if t == "p":
        return f"<p>{esc(b['text'])}</p>"
    if t == "bullets":
        items = "\n".join(f"      <li>{esc(i)}</li>" for i in b["items"])
        return f"    <ul class=\"bullets\">\n{items}\n    </ul>"
    if t == "table":
        head = "".join(f"<th>{esc(h)}</th>" for h in b["headers"])
        rows = []
        for r in b["rows"]:
            cells = "".join(f"<td>{esc(c)}</td>" for c in r)
            rows.append(f"        <tr>{cells}</tr>")
        caption = f"<figcaption>{esc(b['caption'])}</figcaption>" if b.get("caption") else ""
        return (f"    <figure class=\"table-fig\" data-table=\"{esc(b.get('id',''))}\">\n"
                f"      <table class=\"data-table\">\n        <thead><tr>{head}</tr></thead>\n"
                f"        <tbody>\n" + "\n".join(rows) + f"\n        </tbody>\n      </table>\n"
                f"      {caption}\n    </figure>")
    if t == "figure":
        cap = f"<figcaption>{esc(b['caption'])}</figcaption>" if b.get("caption") else ""
        return (f"    <figure class=\"img-fig\" data-figure=\"{esc(b.get('id',''))}\">\n"
                f"      <img src=\"../images/{esc(b['file'])}\" alt=\"{esc(b.get('caption',''))}\">\n"
                f"      {cap}\n    </figure>")
    if t == "highyield":
        return f"    <div class=\"highyield\"><span class=\"box-label\">✦ نکته کلیدی</span>{esc(b['text'])}</div>"
    if t == "callout":
        variant = b.get("variant", "info")
        return f"    <div class=\"callout {variant}\">{esc(b['text'])}</div>"
    return f"<!-- unhandled block {t} -->"


def render_topic(data: dict) -> str:
    parts = [f"  <section class=\"topic\" data-topic=\"{esc(data['id'])}\">"]
    parts.append(f"    <h2 class=\"topic-title\">{esc(data['title'])}</h2>")
    parts.append("    <section class=\"lesson\">")
    for s in data.get("lesson", []):
        parts.append(f"      <div class=\"lesson-section\" data-section=\"{esc(s.get('id',''))}\">")
        if s.get("heading"):
            parts.append(f"        <h3>{esc(s['heading'])}</h3>")
        for b in s.get("blocks", []):
            parts.append(render_block(b))
        parts.append("      </div>")
    parts.append("    </section>")

    fu = data.get("followup")
    if fu:
        parts.append(f"    <section class=\"followup\" data-followup=\"1\" data-source-pages=\"{esc(str(fu.get('source_pages','')))}\">")
        parts.append("      <h2 class=\"fu-title\">Follow Up</h2>")
        for b in fu.get("blocks", []):
            parts.append(render_block(b))
        parts.append("    </section>")

    recall = data.get("active_recall") or []
    if recall:
        parts.append("    <section class=\"recall\">")
        parts.append("      <h2 class=\"recall-title\">Active Recall</h2>")
        parts.append("      <ol class=\"recall-list\">")
        for r in recall:
            parts.append(f"        <li data-from=\"{esc(r.get('from',''))}\">"
                         f"<span class=\"rq\">{esc(r['q'])}</span>"
                         f"<span class=\"ra\">{esc(r.get('a',''))}</span></li>")
        parts.append("      </ol>")
        parts.append("    </section>")

    qs = data.get("questions") or []
    if qs:
        parts.append("    <section class=\"tests\">")
        parts.append("      <h2 class=\"tests-title\">تست‌های این موضوع</h2>")
        for q in qs:
            opts = q.get("options", {})
            opt_items = "\n".join(
                f"          <li class=\"opt {('correct' if k == q.get('answer') else '')}\" data-opt=\"{esc(k)}\">{esc(v)}</li>"
                for k, v in sorted(opts.items()))
            expl = f"        <div class=\"explanation\">{esc(q['explanation'])}</div>" if q.get("explanation") else ""
            notes = f"        <div class=\"key-notes\">{esc(q['notes'])}</div>" if q.get("notes") else ""
            ans = q.get("answer", "")
            parts.append(
                f"      <article class=\"question\" data-qid=\"{esc(q.get('id',''))}\" "
                f"data-source-page=\"{esc(q.get('source_page',''))}\">\n"
                f"        <div class=\"q-head\"><span class=\"q-num\">{esc(q.get('id',''))}</span></div>\n"
                f"        <p class=\"stem\">{esc(q['stem'])}</p>\n"
                f"        <ol class=\"options\">\n{opt_items}\n        </ol>\n"
                f"        <div class=\"answer-key\" data-answer=\"{esc(ans)}\"><span class=\"ans-label\">پاسخ:</span> {esc(ans.upper() if ans else '')}</div>\n"
                f"{expl}\n{notes}\n"
                f"      </article>")
        parts.append("    </section>")

    parts.append(f"    <footer class=\"topic-pages\">منبع: صفحات {esc('، '.join(map(str, data.get('source_pages', []))))}</footer>")
    parts.append("  </section>")
    return "\n".join(parts)


def render_chapter(ch: dict, topics: list[dict]) -> str:
    body = []
    for t in topics:
        body.append(render_topic(t))
    sub = ch.get("subtitle", "")
    sub_html = f"  <div class=\"chapter-sub\">{esc(sub)}</div>" if sub else ""
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(ch['title'])}</title>
<link rel="stylesheet" href="../css/book.css">
</head>
<body>
<article class="chapter" data-chapter="{esc(ch['id'])}">
  <header class="chapter-head">
    <h1>{esc(ch['title'])}</h1>
{sub_html}
  </header>
{chr(10).join(body)}
</article>
</body>
</html>
"""


def render_index(cfg: dict, chapters: list[dict], topics: list[dict]) -> str:
    toc = []
    for c in chapters:
        chap_topics = [t for t in topics if t.get("chapter") == c["id"]]
        toc.append(f"    <li class=\"toc-chapter\"><a href=\"chapters/{c['id']}.html\">{esc(c['title'])}</a>")
        if chap_topics:
            toc.append("      <ul>")
            for t in chap_topics:
                toc.append(f"        <li><a href=\"chapters/{c['id']}.html#{t['id']}\">{esc(t['title'])}</a></li>")
            toc.append("      </ul>")
        toc.append("    </li>")
    b = cfg["book"]
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(b.get('title') or 'کتاب')}</title>
<link rel="stylesheet" href="css/book.css">
</head>
<body>
<div class="cover">
  <div class="cover-inner">
    <div class="cover-kicker">Medical Book — Reconstructed Edition</div>
    <h1 class="cover-title">{esc(b.get('title') or '…')}</h1>
    {'<div class="cover-title-en">' + esc(b['title_en']) + '</div>' if b.get('title_en') else ''}
    {'<div class="cover-author">' + esc(b['author']) + '</div>' if b.get('author') else ''}
    <div class="cover-meta">بازسازی آموزشی از نسخه اسکن‌شده · {cfg['pages']['total']} صفحه منبع</div>
  </div>
</div>
<nav class="toc">
  <h1>فهرست مطالب</h1>
  <ol>
{chr(10).join(toc)}
  </ol>
</nav>
</body>
</html>
"""


def main() -> None:
    cfg = config.load_book_config()
    paths.ensure_dirs()

    chapters = []
    for cp in sorted(paths.CHAPTERS.glob("ch*.yaml")):
        c = yaml.safe_load(cp.read_text(encoding="utf-8")) or {}
        if c.get("id"):
            chapters.append(c)
    topics = []
    for tp in sorted(paths.TOPICS.glob("ch*_t*.yaml")):
        t = yaml.safe_load(tp.read_text(encoding="utf-8")) or {}
        if t.get("id"):
            topics.append(t)
    if not chapters:
        raise SystemExit("no chapters found in content/chapters/")

    for c in chapters:
        (paths.HTML_CHAPTERS / f"{c['id']}.html").write_text(
            render_chapter(c, [t for t in topics if t.get("chapter") == c["id"]]), encoding="utf-8")
    (paths.HTML / "index.html").write_text(render_index(cfg, chapters, topics), encoding="utf-8")

    log.info("08_render_html", f"rendered index + {len(chapters)} chapters, {len(topics)} topics")
    print(f"OK: book/html/index.html + {len(chapters)} chapter files, {len(topics)} topics")


if __name__ == "__main__":
    main()
