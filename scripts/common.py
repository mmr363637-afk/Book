"""Shared CLI plumbing for stage scripts."""
import argparse

from lib import chunk, config, paths, log


def base_parser(stage: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(stage, description=stage)
    p.add_argument("--chunk", help="page range: '1-20' or '1,5,9' or 'all'")
    return p


def resolve_chunks(args, cfg: dict) -> list[chunk.Chunk]:
    total = cfg["pages"]["total"] or None
    if args.chunk is None:
        if not total:
            raise SystemExit("no --chunk given and pages.total unknown; run stage 01 first")
        return [chunk.Chunk(1, total)]
    if args.chunk == "all":
        if not total:
            raise SystemExit("pages.total unknown; run stage 01 first")
        return [chunk.Chunk(1, total)]
    return chunk.parse_range(args.chunk, total)


def banner(stage: str, message: str) -> None:
    paths.ensure_dirs()
    log.info(stage, message)
