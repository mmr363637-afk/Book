"""Append-only run log (qa/run-log.md) so every stage execution is auditable."""
from datetime import datetime, timezone

from .paths import RUN_LOG, QA


def log(stage: str, message: str) -> None:
    QA.mkdir(parents=True, exist_ok=True)
    if not RUN_LOG.exists():
        RUN_LOG.write_text("# Run Log\n\n", encoding="utf-8")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(f"- `{ts}` **{stage}** — {message}\n")


def info(stage: str, message: str) -> None:
    log(stage, message)
    print(f"[{stage}] {message}")
