# Medical Book Reconstruction & Publishing Pipeline
# Usage: make <target>  (CHUNK="1-10" PAGE=12 for chunked targets)
CHUNK ?= 1-10
PAGE  ?= 1
PY    ?= python3

.PHONY: setup status register inspect rasterize ocr-prepare ocr-status ocr-drafted \
        verify-prepare verify-report structure html pdf qa clean

setup: ## install Python dependencies (first run / new environment)
	pip3 install --break-system-packages -r requirements.txt

status: ## pipeline state dashboard
	$(PY) scripts/04_ocr_raw.py --status

register: ## stage 01 — register source PDF (input/*.pdf)
	$(PY) scripts/01_register_source.py

inspect: ## stage 02 — source analysis (contact sheets + audit)
	$(PY) scripts/02_inspect_source.py

rasterize: ## stage 03 — chunk PDF→page images
	$(PY) scripts/03_rasterize.py --chunk $(CHUNK)

ocr-prepare: ## stage 04 — prepare OCR chunk (crosscheck + draft stubs)
	$(PY) scripts/04_ocr_raw.py --chunk $(CHUNK)

ocr-status: ## stage 04 — draft queue
	$(PY) scripts/04_ocr_raw.py --status

verify-prepare: ## stage 05 — detail crops for one page
	$(PY) scripts/05_verify_prepare.py --page $(PAGE)

verify-report: ## stage 06 — reconcile chunk, raise flags
	$(PY) scripts/06_verify_report.py --chunk $(CHUNK)

structure: ## stage 07 — validate structured content (anti-fabrication gates)
	$(PY) scripts/07_structure.py

html: ## stage 08 — render HTML (source of truth)
	$(PY) scripts/08_render_html.py

pdf: ## stage 09 — build PDF from HTML
	$(PY) scripts/09_build_pdf.py

qa: ## stage 10 — QA checks + report
	$(PY) scripts/10_qa.py
