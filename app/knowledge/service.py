"""Application-facing retrieval limits for paper search."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from app.knowledge.store import SearchHit


MAX_SEARCH_OUTPUT_CHARS = 12_000


class KnowledgeService:
    """Delegate retrieval while keeping returned LaTex within the tool budget."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def search(self, query: str, **filters: Any) -> list[SearchHit]:
        hits = self.store.search(query, **filters)
        remaining = MAX_SEARCH_OUTPUT_CHARS
        capped: list[SearchHit] = []
        for hit in hits:
            if remaining <= 0:
                break
            raw_latex = hit.raw_latex[:remaining]
            capped.append(replace(hit, raw_latex=raw_latex))
            remaining -= len(raw_latex)
        return capped

    def format_search_hits(self, hits: Iterable[SearchHit]) -> str:
        """Format search results into the bounded text returned by a paper-search tool."""

        remaining = MAX_SEARCH_OUTPUT_CHARS
        rendered_hits: list[str] = []
        for hit in hits:
            if remaining <= 0:
                break
            rendered = _format_hit(hit)
            rendered_hits.append(rendered[:remaining])
            remaining -= len(rendered_hits[-1])
        return "".join(rendered_hits)


KnowledgeSearchService = KnowledgeService


def _format_hit(hit: SearchHit) -> str:
    return (
        "Paper ID: " + _bounded_field(hit.paper_id, 512) + "\n"
        + "Title: " + _bounded_field(hit.title, 2_048) + "\n"
        + "Section: " + _bounded_field(" / ".join(hit.section_path), 1_024) + "\n"
        + "Source file: " + _bounded_field(hit.source_file, 1_024) + "\n"
        + "Chunk ID: " + _bounded_field(hit.chunk_id, 512) + "\n"
        + f"Score: {hit.score:.6f}\n"
        + "Raw LaTeX:\n"
        + hit.raw_latex
        + "\n\n"
    )


def _bounded_field(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"
