"""Config loading helpers."""
import copy
import yaml

from .paths import book_config_path, render_config_path

_BOOK_DEFAULTS = {
    "book": {
        "title": "", "title_en": "", "author": "", "publisher": "",
        "language": "fa", "source_pdf": "", "sha256": "", "registered_at": "",
    },
    "pages": {"total": 0, "dpi": 180, "jpeg_quality": 82},
    "pipeline": {
        "chunk_size": 10,
        "ocr_mode": "vision",
        "crosscheck": {"enabled": True, "min_conf": 0.60, "latin_only": True},
    },
    "chapters": [],
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_book_config() -> dict:
    data = {}
    if book_config_path().exists():
        data = yaml.safe_load(book_config_path().read_text(encoding="utf-8")) or {}
    return _deep_merge(_BOOK_DEFAULTS, data)


def save_book_config(cfg: dict) -> None:
    book_config_path().write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def load_render_config() -> dict:
    return yaml.safe_load(render_config_path().read_text(encoding="utf-8")) or {}
