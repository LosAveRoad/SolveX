"""Manage the local Qdrant knowledge base of excellent LaTeX papers.

The command parser deliberately has no SolveX imports.  This keeps ``--help``
safe to use on hosts that have not downloaded embedding models or started
Qdrant yet; configuration, the Qdrant client, and embedding metadata are only
created after a data-changing or query command has been selected.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


MAX_TOP_K = 12
MAX_SEARCH_OUTPUT_CHARS = 12_000


@dataclass(frozen=True)
class KnowledgeRuntime:
    """Dependencies resolved only while a knowledge-base command is running."""

    service: Any
    dense_model: str
    default_top_k: int


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser without reading configuration or connecting to Qdrant."""

    parser = argparse.ArgumentParser(
        description="Import and search the local SolveX excellent-paper knowledge base."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="import one paper directory or ZIP")
    ingest.add_argument("path", help="paper directory or ZIP archive")
    ingest.add_argument(
        "--recursive",
        action="store_true",
        help="find paper.yaml projects and ZIP archives below a corpus directory",
    )

    commands.add_parser("list", help="list indexed papers")

    search = commands.add_parser("search", help="hybrid-search indexed paper chunks")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=None)
    _add_metadata_filters(search)

    delete = commands.add_parser("delete", help="delete every chunk for one paper")
    delete.add_argument("paper_id")
    delete.add_argument("--yes", action="store_true", help="confirm deletion")

    reindex = commands.add_parser(
        "reindex", help="build a fresh collection and atomically switch its alias"
    )
    reindex.add_argument("corpus_root", help="directory containing paper projects or ZIPs")
    reindex.add_argument("--yes", action="store_true", help="confirm alias replacement")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return a process exit status for tests and scripts."""

    args = build_parser().parse_args(argv)
    try:
        if args.command == "ingest":
            return _run_ingest(args)
        if args.command == "list":
            return _run_list()
        if args.command == "search":
            return _run_search(args)
        if args.command == "delete":
            return _run_delete(args)
        if args.command == "reindex":
            return _run_reindex(args)
    except Exception as exc:
        _error(f"knowledge-base command failed: {exc}")
        return 1
    _error("unknown knowledge-base command")
    return 2


def _add_metadata_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--competition")
    parser.add_argument("--year", type=int)
    parser.add_argument("--problem")
    parser.add_argument("--award")
    parser.add_argument("--language")
    parser.add_argument("--methods", nargs="+", metavar="METHOD")


def _run_ingest(args: argparse.Namespace) -> int:
    source = Path(args.path)
    try:
        sources = _discover_sources(source, recursive=args.recursive, allow_file=True)
    except ValueError as exc:
        _error(str(exc))
        return 1
    if not sources:
        _error(f"no valid paper sources found under {source}")
        return 1

    runtime = _build_runtime()
    succeeded = 0
    failed = 0
    for paper_source in sources:
        try:
            document = _load_document(paper_source, dense_model=runtime.dense_model)
            chunk_count = runtime.service.store.index_document(document)
        except Exception as exc:
            failed += 1
            _error(f"failed to ingest {paper_source}: {exc}")
            continue
        succeeded += 1
        print(f"indexed {document.manifest.paper_id}: {chunk_count} chunks")
    print(f"ingest summary: {succeeded} imported, {failed} failed")
    return 0 if failed == 0 else 1


def _run_list() -> int:
    runtime = _build_runtime()
    papers = runtime.service.store.list_papers()
    if not papers:
        print("no papers indexed")
        return 0
    for paper in papers:
        methods = ", ".join(paper.methods) or "-"
        print(
            f"{paper.paper_id}\t{paper.title}\t{paper.competition} {paper.year} "
            f"{paper.problem}\t{paper.award}\t{paper.language}\t{methods}\t"
            f"{paper.chunk_count} chunks"
        )
    return 0


def _run_search(args: argparse.Namespace) -> int:
    if args.top_k is not None and not 1 <= args.top_k <= MAX_TOP_K:
        _error("top-k must be between 1 and 12")
        return 2
    runtime = _build_runtime()
    top_k = runtime.default_top_k if args.top_k is None else args.top_k
    hits = runtime.service.search(
        args.query,
        top_k=top_k,
        competition=args.competition,
        year=args.year,
        problem=args.problem,
        award=args.award,
        language=args.language,
        methods=args.methods,
    )
    if not hits:
        print("no matching paper chunks")
        return 0
    rendered = runtime.service.format_search_hits(hits)
    print(rendered[:MAX_SEARCH_OUTPUT_CHARS])
    return 0


def _run_delete(args: argparse.Namespace) -> int:
    if not args.yes:
        _error("refusing to delete without --yes")
        return 2
    runtime = _build_runtime()
    chunk_count = runtime.service.store.delete_paper(args.paper_id)
    print(f"deleted {chunk_count} chunks for {args.paper_id}")
    return 0


def _run_reindex(args: argparse.Namespace) -> int:
    if not args.yes:
        _error("refusing to reindex without --yes")
        return 2
    root = Path(args.corpus_root)
    try:
        sources = _discover_sources(root, recursive=True, allow_file=False)
    except ValueError as exc:
        _error(str(exc))
        return 1
    if not sources:
        _error(f"no valid paper sources found under {root}; refusing to switch to an empty index")
        return 1

    runtime = _build_runtime()
    documents = []
    has_failures = False
    for paper_source in sources:
        try:
            documents.append(_load_document(paper_source, dense_model=runtime.dense_model))
        except Exception as exc:
            has_failures = True
            _error(f"failed to load {paper_source} for reindex: {exc}")
    if has_failures:
        _error("reindex aborted: one or more paper sources could not be loaded; alias was not changed")
        return 1

    target = runtime.service.store.reindex(documents)
    print(f"reindexed {len(documents)} papers into {target}")
    return 0


def _discover_sources(root: Path, *, recursive: bool, allow_file: bool) -> list[Path]:
    """Find project roots and ZIP archives without parsing them or loading a model."""

    if not root.exists():
        raise ValueError(f"input path does not exist: {root}")
    if root.is_file():
        if not allow_file or root.suffix.lower() != ".zip":
            raise ValueError(f"paper source must be a directory or .zip archive: {root}")
        return [root]
    if not root.is_dir():
        raise ValueError(f"input path must be a directory: {root}")
    if not recursive:
        return [root]

    candidates: dict[Path, None] = {}
    if (root / "paper.yaml").is_file():
        candidates[root.resolve()] = None
    for manifest in root.rglob("paper.yaml"):
        candidates[manifest.parent.resolve()] = None
    for archive in root.rglob("*.zip"):
        candidates[archive.resolve()] = None
    return sorted(candidates, key=lambda path: str(path).casefold())


def _build_runtime() -> KnowledgeRuntime:
    """Create synchronous Qdrant dependencies only for a selected command."""

    from qdrant_client import QdrantClient

    from app.config import config
    from app.knowledge.service import KnowledgeService
    from app.knowledge.store import KnowledgeStore

    settings = config.knowledge
    client = QdrantClient(url=settings.qdrant_url)
    store = KnowledgeStore(
        client,
        collection_name=settings.collection_name,
        dense_model=settings.dense_model,
        sparse_model=settings.sparse_model,
    )
    return KnowledgeRuntime(
        service=KnowledgeService(store),
        dense_model=settings.dense_model,
        default_top_k=settings.default_top_k,
    )


def _load_document(source: Path, *, dense_model: str):
    from app.knowledge.ingestion import load_paper_document

    return load_paper_document(source, dense_model=dense_model)


def _error(message: str) -> None:
    print(message, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
