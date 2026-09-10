"""Project path constants. Everything lives under the repo root."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

INPUT = ROOT / "input"
CONFIG = ROOT / "config"

OCR = ROOT / "ocr"
RAW = OCR / "raw"
VERIFIED = OCR / "verified"
PAGES = OCR / "pages"
MANIFEST = OCR / "manifest.jsonl"

CONTENT = ROOT / "content"
CHAPTERS = CONTENT / "chapters"
TOPICS = CONTENT / "topics"
QUESTIONS = CONTENT / "questions"
BUILD_MANIFEST = CONTENT / "build-manifest.json"
LEXICON = CONTENT / "lexicon.yaml"

BOOK = ROOT / "book"
HTML = BOOK / "html"
HTML_CHAPTERS = HTML / "chapters"
CSS = BOOK / "css"
IMAGES = BOOK / "images"
FONTS = BOOK / "fonts"
ASSETS = BOOK / "assets"

PDF = ROOT / "pdf"

QA = ROOT / "qa"
FLAGS = QA / "flags"
VERIFY = QA / "verify"
SMOKE = QA / "smoke"
RUN_LOG = QA / "run-log.md"
REPORT = QA / "final-report.md"

ALL_DIRS = [
    INPUT, CONFIG, OCR, RAW, VERIFIED, PAGES,
    CONTENT, CHAPTERS, TOPICS, QUESTIONS,
    BOOK, HTML, HTML_CHAPTERS, CSS, IMAGES, FONTS, ASSETS,
    PDF, QA, FLAGS, VERIFY, SMOKE,
]


def ensure_dirs() -> None:
    for p in ALL_DIRS:
        p.mkdir(parents=True, exist_ok=True)


def book_config_path() -> Path:
    return CONFIG / "book.yaml"


def render_config_path() -> Path:
    return CONFIG / "render.yaml"
