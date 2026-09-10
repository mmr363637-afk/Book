# Pipeline Architecture & Contracts

## 1. Design principles

1. **HTML is the Source of Truth for presentation.** The PDF (stage 09) parses
   `book/html/*.html`. No content is ever duplicated for the PDF.
2. **The page image is the final reference for content.** OCR (any kind) is an
   extraction aid. Every sensitive token in the final book must be reconciled
   against (raw draft ∪ mechanical crosscheck ∪ page image) — unexplained
   tokens become flags.
3. **Chunk-based processing.** Every stage accepts `--chunk 1-20`. Memory is
   released at chunk boundaries. The book is never held in RAM at once.
4. **Stages are independently re-runnable.** State lives in files
   (`ocr/manifest.jsonl`, content YAMLs, qa reports), never in agent context.
5. **Anti-fabrication by construction.** Tests, answer keys, and follow-ups
   that cannot be anchored to a source page fail the build (stage 07).

## 2. Stage contracts

| Stage | Input | Output | Re-runnable on |
|---|---|---|---|
| 01 register | input/*.pdf | config/book.yaml, qa/source-metadata.json | yes (hash-checked) |
| 02 inspect | registered pdf | qa/inspect-report.json, contact sheets, content/source-analysis.md | yes |
| 03 rasterize | pdf | ocr/pages/page_NNN.jpg, manifest | per chunk (skips existing) |
| 04 ocr-prepare | pages | crosscheck.json + draft stubs, manifest=awaiting_draft | per chunk |
| — agent draft | page images | ocr/raw/page_NNN.txt, manifest=drafted | per page |
| 05 verify-prepare | pdf page N | qa/verify/page_NNN/band_*.jpg | per page |
| — agent verify | image + bands + raw | ocr/verified/page_NNN.txt | per page |
| 06 verify-report | raw+verified+crosscheck | manifest=verified/flagged, qa/flags/* | per chunk |
| — agent structure | verified text | content/chapters, content/topics | per topic |
| 07 structure | content/* | content/build-manifest.json (+ FAIL on violations) | whole (fast) |
| 08 render-html | content/* | book/html/* | whole (fast) |
| 09 build-pdf | book/html/* | pdf/book.pdf | whole |
| 10 qa | everything | qa/final-report.md | whole |

## 3. Manifest protocol (ocr/manifest.jsonl)

One JSON line per page:

```json
{"page": 12, "image": "ocr/pages/page_012.jpg", "image_dpi": 180,
 "status": "drafted", "has_text_layer": false,
 "raw": "ocr/raw/page_012.txt", "verified": null, "flags": 0}
```

Statuses: `rasterized → awaiting_draft → drafted → verified | flagged`.
`flagged` pages must be re-checked against the image; resolution is recorded
in qa/flags (FLGnnnn, status open→resolved).

## 4. Sensitive-token classes (lib/sensitive.py)

percent · dose (mg/mcg/g/ml/mmol/IU…) · lab value (x/yy, mmol/L, mg/dL…) ·
pressure (mmHg) · pH · cut-off/criterion/inequality (`> n`, `< n`) ·
negative-question words (نیست/به‌جز/کدام) · answer words (درست است/غلط است) ·
years · ratios · Latin drug-like words.

Rule: any such token in **verified** text that appears in neither the raw
draft nor the mechanical crosscheck is FLAGGED for image re-check. In stage 10
the same rule is inverted: any such token in the **final HTML** must exist in
the verified-OCR corpus, otherwise it is reported (possible fabrication or
typo).

## 5. Memory protocol

- Stage 03 re-opens the PDF per chunk; pixmaps are deleted immediately.
- Stage 02 audits at 50 dpi and closes the document.
- Stage 05 renders one page at a time.
- Agent passes read one page image (or three band crops) at a time.
- No stage loads all page images or the whole book text.

## 6. Git checkpoint protocol

Commit after each significant step with message prefix `stage:`:

```
stage: 02 source analysis — chapter map identified (8 chapters)
stage: chunk 1-10 OCR complete (0 open flags)
stage: chunk 1-10 structured content (14 topics, 38 questions)
stage: pilot complete (chapter 1: HTML 42 pages, PDF 40 pages)
stage: pilot QA fixes (print css, table split)
stage: production chunk 11-30 …
stage: final QA
```

Any stage can be re-run from the last checkpoint without redoing earlier ones.

## 7. QA taxonomy (stage 10 + agent review)

- **Source QA** — nothing from the source omitted (coverage of verified pages
  vs topic source_pages; contact-sheet review).
- **OCR QA** — open flags list; raw↔verified similarity stats.
- **Medical QA** — sensitive-token cross-checks (S3).
- **Structure QA** — order درسنامه → Follow Up → Active Recall → Tests
  enforced by the HTML contract (08 emits sections in that order).
- **Test QA** — S2: every question in HTML carries `data-source-page`;
  stage-07 G1 guarantees the source page and the book's answer.
- **Visual QA** — agent renders sample PDF pages to images and inspects.
- **PDF QA** — S6: page count, extractable Persian text, spot strings.

## 8. HTML contract (consumed by stage 09)

```
article.chapter[data-chapter]
  header.chapter-head > h1 + div.chapter-sub
  section.topic[data-topic]
    h2.topic-title
    section.lesson
      div.lesson-section[data-section]
        h3 | p | ul.bullets>li | figure.table-fig>table.data-table
        | figure.img-fig>img | div.highyield | div.callout
    section.followup[data-followup]
    section.recall > ol.recall-list > li > span.rq + span.ra
    section.tests > article.question[data-qid][data-source-page]
      div.q-head > span.q-num | p.stem | ol.options > li.opt[data-opt]
      div.answer-key[data-answer] | div.explanation | div.key-notes
    footer.topic-pages
```

## 9. Swapping components

- OCR engine: implement `run_on_image(path) -> [{token, conf, bbox}]` in
  `lib/ocr_engine.py` (tesseract-fa / PaddleOCR-fa on a connected machine).
- PDF engine: replace `scripts/09_build_pdf.py` with a WeasyPrint call on the
  same HTML (needs Pango). Design tokens in `config/render.yaml` +
  `book/css/book.css` stay the contract.
- Fonts: any TTF family with Persian + Latin coverage; register in stage 09.

## 10. Scaling plan (when the book is large)

- Page images are committed as JPEG@180dpi. If the repo exceeds ~200 MB or
  500 pages, migrate `ocr/pages` to Git LFS and keep `ocr/raw`,
  `ocr/verified`, `content/`, `book/`, `pdf/` in regular Git.
- Keep chunk size 10–20 pages; process chapter-by-chapter in the declared
  chapter order; commit per chunk.
