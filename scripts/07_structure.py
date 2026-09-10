#!/usr/bin/env python3
"""Stage 07 — Structured content validation & build manifest.

The agent builds the structured content model from verified OCR:
  content/chapters/chNN.yaml    chapter map (title, page span, topic ids)
  content/topics/chNN_tMM.yaml  one file per topic, schema below

SCHEMA (content/topics/*.yaml)
  id: ch01_t01                  # must match chapter prefix
  chapter: ch01
  title: "..."
  source_pages: [3, 4, 5]      # REQUIRED, non-empty, ints
  lesson:                       # REQUIRED, non-empty list of sections
    - id: l1                    # unique within topic
      heading: "..."
      blocks:
        - {type: p, text: "..."}
        - {type: bullets, items: ["..."]}
        - {type: table, id: t01, caption: "...", headers: [...], rows: [[...]]}
        - {type: figure, id: f01, file: "ch01_f01.png", caption: "..."}
        - {type: highyield, text: "..."}
        - {type: callout, variant: info|warning, text: "..."}
  followup:                     # OPTIONAL — ONLY if the book has a Follow Up
    source_pages: [5]           # REQUIRED if followup present
    blocks: [...]               # same block types
  active_recall:                # OPTIONAL; retrieval-based short Q/A
    - q: "..."
      a: "..."
      from: l2                  # REQUIRED: must reference a lesson section id
  questions:                    # OPTIONAL — ONLY the book's own questions
    - id: q01
      source_page: 6            # REQUIRED: page the question appears on
      stem: "..."
      options: {a: "...", b: "...", c: "...", d: "..."}
      answer: "b"               # from the book's Answer Key
      explanation: "..."        # from the book's Answer Key (null if book has none)
      answer_key_page: 40       # optional: where the key lives
      notes: "..."              # optional Answer Key notes

GUARDRAILS (hard errors → build fails):
  G1  question without source_page            (anti-fabrication)
  G2  active_recall item without valid `from` (anti-fabrication)
  G3  followup without source_pages           (anti-fabrication)
  G4  figure file missing on disk             (asset integrity)
  G5  topic id / chapter prefix mismatch
  G6  source page outside chapter span
  G7  duplicate question ids
  G8  topic without lesson content

Outputs: content/build-manifest.json (counts + per-chapter stats)
Usage: python3 scripts/07_structure.py [--strict]
"""
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import config, paths, log  # noqa: E402

BLOCK_TYPES = {"p", "bullets", "table", "figure", "highyield", "callout"}


class Errors(list):
    def err(self, topic: str, code: str, msg: str) -> None:
        self.append({"topic": topic, "code": code, "msg": msg})


def load_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def check_blocks(blocks: list, topic: str, section_id: str, errors: Errors) -> tuple[int, int]:
    n_tables = n_figures = 0
    if not isinstance(blocks, list):
        errors.err(topic, "E-SCHEMA", f"section {section_id}: blocks must be a list")
        return 0, 0
    for i, b in enumerate(blocks):
        if not isinstance(b, dict) or b.get("type") not in BLOCK_TYPES:
            errors.err(topic, "E-SCHEMA", f"section {section_id} block {i}: unknown block {b}")
            continue
        if b["type"] == "table":
            n_tables += 1
            if not b.get("headers") or not b.get("rows"):
                errors.err(topic, "E-SCHEMA", f"table {b.get('id','?')} needs headers+rows")
        elif b["type"] == "figure":
            n_figures += 1
            f = paths.IMAGES / b.get("file", "")
            if not f.exists():
                errors.err(topic, "G4", f"figure file missing: {f}")
        elif b["type"] == "p" and not b.get("text"):
            errors.err(topic, "E-SCHEMA", f"section {section_id} block {i}: p needs text")
        elif b["type"] == "bullets" and not b.get("items"):
            errors.err(topic, "E-SCHEMA", f"section {section_id} block {i}: bullets need items")
        elif b["type"] in ("highyield", "callout") and not b.get("text"):
            errors.err(topic, "E-SCHEMA", f"section {section_id} block {i}: {b['type']} needs text")
    return n_tables, n_figures


def validate_topic(data: dict, chapter_spans: dict, errors: Errors) -> dict:
    tid = data.get("id", "?")
    stats = {"id": tid, "tables": 0, "figures": 0, "questions": 0, "recall": 0,
             "has_followup": False, "source_pages": []}

    chap = data.get("chapter")
    if not chap or not chap.startswith("ch"):
        errors.err(tid, "G5", f"bad chapter ref: {chap}")
        return stats
    if tid.startswith(chap + "_t"):
        pass
    else:
        errors.err(tid, "G5", f"topic id {tid} does not match chapter {chap}")

    span = chapter_spans.get(chap)
    sp = data.get("source_pages")
    if not isinstance(sp, list) or not sp:
        errors.err(tid, "G6", "source_pages required (non-empty list)")
        sp = []
    stats["source_pages"] = sp
    if span:
        for p in sp:
            if not isinstance(p, int) or not (span[0] <= p <= span[1]):
                errors.err(tid, "G6", f"source page {p} outside chapter span {span}")

    lesson = data.get("lesson")
    if not isinstance(lesson, list) or not lesson:
        errors.err(tid, "G8", "lesson required (non-empty list of sections)")
        lesson = []
    section_ids = set()
    for s in lesson:
        sid = s.get("id")
        if not sid:
            errors.err(tid, "E-SCHEMA", "lesson section without id")
            continue
        section_ids.add(sid)
        t, f = check_blocks(s.get("blocks", []), tid, sid, errors)
        stats["tables"] += t
        stats["figures"] += f

    fu = data.get("followup")
    if fu is not None:
        stats["has_followup"] = True
        fps = fu.get("source_pages")
        if not isinstance(fps, list) or not fps:
            errors.err(tid, "G3", "followup requires source_pages")
        else:
            check_blocks(fu.get("blocks", []), tid, "followup", errors)

    recall = data.get("active_recall") or []
    stats["recall"] = len(recall)
    for i, r in enumerate(recall):
        frm = r.get("from")
        if not r.get("q"):
            errors.err(tid, "G2", f"active_recall[{i}] missing q")
        if frm not in section_ids:
            errors.err(tid, "G2", f"active_recall[{i}] from='{frm}' not a lesson section")

    qs = data.get("questions") or []
    seen_q = set()
    for i, q in enumerate(qs):
        qid = q.get("id") or f"q{i+1:02d}"
        if qid in seen_q:
            errors.err(tid, "G7", f"duplicate question id {qid}")
        seen_q.add(qid)
        spg = q.get("source_page")
        if not isinstance(spg, int):
            errors.err(tid, "G1", f"question {qid}: source_page required (int) — anti-fabrication")
        elif sp and not (min(sp) <= spg <= max(sp)) and span and not (span[0] <= spg <= span[1]):
            errors.err(tid, "G6", f"question {qid}: source_page {spg} outside topic/chapter span")
        opts = q.get("options")
        if not isinstance(opts, dict) or len(opts) < 2:
            errors.err(tid, "E-SCHEMA", f"question {qid}: options dict required")
        if "answer" not in q or q["answer"] in (None, ""):
            errors.err(tid, "G1", f"question {qid}: answer required (from the book's Answer Key)")
        stats["questions"] += 1

    return stats


def main() -> None:
    ap = __import__("argparse").ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="warn-level issues also fail (default: all errors fail)")
    args = ap.parse_args()

    cfg = config.load_book_config()
    paths.ensure_dirs()
    errors = Errors()

    chapter_spans = {}
    chapters = []
    for cp in sorted(paths.CHAPTERS.glob("ch*.yaml")):
        c = load_yaml(cp)
        if not c.get("id") or not c.get("title"):
            errors.err(cp.name, "E-SCHEMA", "chapter needs id+title")
            continue
        s, e = c.get("start_page"), c.get("end_page")
        if not isinstance(s, int) or not isinstance(e, int) or e < s:
            errors.err(c["id"], "E-SCHEMA", "chapter needs start_page<=end_page ints")
            continue
        chapter_spans[c["id"]] = (s, e)
        chapters.append(c)

    topic_stats = []
    for tp in sorted(paths.TOPICS.glob("ch*_t*.yaml")):
        data = load_yaml(tp)
        topic_stats.append(validate_topic(data, chapter_spans, errors))

    # chapter ↔ topic consistency
    chapter_topics = {}
    for t in topic_stats:
        chapter_topics.setdefault(t["id"].rsplit("_t", 1)[0], []).append(t["id"])
    for c in chapters:
        declared = c.get("topics") or []
        if declared:
            for d in declared:
                if d not in chapter_topics.get(c["id"], []):
                    errors.err(c["id"], "E-SCHEMA", f"declared topic {d} has no file")

    total_q = sum(t["questions"] for t in topic_stats)
    total_t = sum(t["tables"] for t in topic_stats)
    total_f = sum(t["figures"] for t in topic_stats)
    total_r = sum(t["recall"] for t in topic_stats)
    manifest_out = {
        "chapters": len(chapters),
        "topics": len(topic_stats),
        "questions": total_q,
        "recall_items": total_r,
        "tables": total_t,
        "figures": total_f,
        "topics_with_followup": sum(1 for t in topic_stats if t["has_followup"]),
        "topics": topic_stats,
        "chapter_spans": {k: list(v) for k, v in chapter_spans.items()},
        "errors": len(errors),
    }
    paths.BUILD_MANIFEST.write_text(json.dumps(manifest_out, ensure_ascii=False, indent=1), encoding="utf-8")

    if errors:
        for e in errors:
            print(f"  ERROR {e['code']} [{e['topic']}] {e['msg']}")
        log.info("07_structure", f"FAILED with {len(errors)} errors")
        raise SystemExit(1)

    log.info("07_structure", f"OK: {len(chapters)} chapters, {len(topic_stats)} topics, "
                             f"{total_q} questions, {total_r} recall, {total_t} tables, {total_f} figures")
    print(f"OK: {len(topic_stats)} topics, {total_q} questions, {total_t} tables, {total_f} figures — "
          f"manifest at content/build-manifest.json")


if __name__ == "__main__":
    main()
