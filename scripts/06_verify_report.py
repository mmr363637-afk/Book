#!/usr/bin/env python3
"""Stage 06 — Verification reconciliation (chunk-based).

The agent's second pass (reading qa/verify crops + full page image,
reconciling against the raw draft and the mechanical crosscheck) produces
ocr/verified/page_NNN.txt and optional per-page flags.

This script then mechanically reconciles:
  * every SENSITIVE token in the verified text (numbers, dosages, %, units,
    cut-offs, pH, negative-question words, Latin drug-like words) must be
    present in (raw draft ∪ mechanical crosscheck) — otherwise a FLAG is
    raised for image re-check;
  * line-level diff stats raw→verified are recorded;
  * flags accumulate in qa/flags/flags.jsonl and qa/flags/flags.md.

A page whose verified text exists and whose flags are all resolved gets
status=verified.

Usage:
  python3 scripts/06_verify_report.py --chunk 1-10
  python3 scripts/06_verify_report.py --resolve FLAG_ID [--note "..."]
  python3 scripts/06_verify_report.py --flags
"""
import argparse
import difflib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from lib import config, manifest, ocr_engine, paths, sensitive  # noqa: E402

FLAGS_JSONL = paths.FLAGS / "flags.jsonl"
FLAGS_MD = paths.FLAGS / "flags.md"


def load_flags() -> list[dict]:
    if not FLAGS_JSONL.exists():
        return []
    return [json.loads(l) for l in FLAGS_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]


def save_flags(flags: list[dict]) -> None:
    paths.FLAGS.mkdir(parents=True, exist_ok=True)
    with FLAGS_JSONL.open("w", encoding="utf-8") as f:
        for fl in flags:
            f.write(json.dumps(fl, ensure_ascii=False) + "\n")
    md = ["# OCR / Medical Flags", "",
          "| id | page | kind | token | status | note |", "|---|---|---|---|---|---|"]
    for fl in flags:
        md.append(f"| {fl['id']} | {fl['page']} | {fl['kind']} | `{fl['token']}` | {fl['status']} | {fl.get('note','')} |")
    FLAGS_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


def next_flag_id(flags: list[dict]) -> str:
    n = sum(1 for _ in flags) + 1
    while any(f["id"] == f"FLG{n:04d}" for f in flags):
        n += 1
    return f"FLG{n:04d}"


def reconcile_chunk(cfg, chunk) -> None:
    cc_cfg = cfg["pipeline"]["crosscheck"]["min_conf"]
    flags = load_flags()
    pages_report = []
    for page in chunk.pages:
        raw_p = paths.RAW / f"page_{page:03d}.txt"
        ver_p = paths.VERIFIED / f"page_{page:03d}.txt"
        if not ver_p.exists():
            pages_report.append({"page": page, "status": "missing_verified"})
            continue
        raw = raw_p.read_text(encoding="utf-8") if raw_p.exists() else ""
        ver = ver_p.read_text(encoding="utf-8")
        # corpus = sensitive tokens found in raw draft + single latin/numeric
        # fragments (for crosscheck tokens) + mechanical crosscheck tokens
        raw_sensitive_norms = {t["norm"] for t in sensitive.find_sensitive(raw)}
        raw_frag_norms = {sensitive.normalize(t) for t in re.findall(r"[A-Za-z0-9.%/µ\-+]+", raw)}
        cc_tokens = ocr_engine.token_set(
            ocr_engine.load_crosscheck(paths.RAW / f"page_{page:03d}.crosscheck.json"))
        cc_norm = {sensitive.normalize(t) for t in cc_tokens}
        corpus = raw_sensitive_norms | raw_frag_norms | cc_norm

        page_flags = 0
        new_flags = 0
        for tok in sensitive.find_sensitive(ver):
            if tok["norm"] in corpus:
                continue
            # already flagged?
            if any(f["page"] == page and f["token"] == tok["token"] and f["status"] == "open"
                   for f in flags):
                page_flags += 1
                continue
            fid = next_flag_id(flags)
            flags.append({
                "id": fid, "page": page, "kind": tok["kind"], "token": tok["token"],
                "status": "open", "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "note": "sensitive token not in raw draft nor mechanical crosscheck — re-check against image",
            })
            new_flags += 1
            page_flags += 1
        if page_flags:
            manifest.update(page, status="flagged", flags=page_flags,
                            verified=f"ocr/verified/page_{page:03d}.txt")
        else:
            manifest.update(page, status="verified", flags=0,
                            verified=f"ocr/verified/page_{page:03d}.txt")
        diff = difflib.SequenceMatcher(None, raw.splitlines(), ver.splitlines())
        ratio = diff.ratio()
        pages_report.append({"page": page, "status": "ok", "raw_vs_verified_similarity": round(ratio, 3),
                             "open_flags": page_flags})
    save_flags(flags)
    (paths.FLAGS / "verify-report.json").write_text(json.dumps(pages_report, ensure_ascii=False, indent=1),
                                                    encoding="utf-8")
    common.banner("06_verify_report", f"chunk {chunk}: "
                                      f"{sum(1 for r in pages_report if r['status']=='ok')} verified, "
                                      f"{sum(1 for r in pages_report if r['status']=='missing_verified')} missing verified text")
    for r in pages_report:
        if r["status"] == "missing_verified":
            print(f"  page {r['page']}: MISSING verified text (agent must write ocr/verified/page_{r['page']:03d}.txt)")


def show_flags() -> None:
    flags = load_flags()
    open_flags = [f for f in flags if f["status"] == "open"]
    print(f"open flags: {len(open_flags)} (total {len(flags)})")
    for f in open_flags:
        print(f"  {f['id']}  p{f['page']:03d}  [{f['kind']}] {f['token']}")


def resolve(fid: str, note: str) -> None:
    flags = load_flags()
    for f in flags:
        if f["id"] == fid:
            f["status"] = "resolved"
            f["note"] = note or f["note"]
            f["resolved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            save_flags(flags)
            print(f"{fid} resolved")
            return
    raise SystemExit(f"flag not found: {fid}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk")
    ap.add_argument("--flags", action="store_true")
    ap.add_argument("--resolve", metavar="FLAG_ID")
    ap.add_argument("--note")
    args = ap.parse_args()

    cfg = config.load_book_config()
    paths.ensure_dirs()
    if args.flags:
        show_flags()
        return
    if args.resolve:
        resolve(args.resolve, args.note or "")
        return
    if not args.chunk:
        raise SystemExit("need --chunk (or --flags / --resolve)")
    for ch in common.resolve_chunks(args, cfg):
        reconcile_chunk(cfg, ch)


if __name__ == "__main__":
    main()
