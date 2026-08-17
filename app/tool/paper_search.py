"""Tool interface for the local excellent-paper knowledge base."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from pydantic import Field, PrivateAttr
from qdrant_client import QdrantClient

from app.config import KnowledgeSettings, config
from app.knowledge.service import MAX_SEARCH_OUTPUT_CHARS, KnowledgeService
from app.knowledge.store import KnowledgeStore
from app.knowledge.trace import write_retrieval_trace
from app.tool.base import BaseTool, ToolResult


_LOGGER = logging.getLogger(__name__)
MAX_TOP_K = 12


def _build_service(settings: KnowledgeSettings) -> KnowledgeService:
    """Construct Qdrant and embedding dependencies only on the first tool execution."""

    client = QdrantClient(url=settings.qdrant_url)
    store = KnowledgeStore(
        client,
        collection_name=settings.collection_name,
        dense_model=settings.dense_model,
        sparse_model=settings.sparse_model,
    )
    return KnowledgeService(store)


class PaperSearch(BaseTool):
    """Search locally indexed excellent papers with dense + BM25 retrieval."""

    name: str = "paper_search"
    description: str = (
        "Search locally indexed excellent competition papers for relevant modeling "
        "methods, assumptions, sections, and LaTeX examples."
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    default_top_k: int = Field(6, ge=1, le=MAX_TOP_K)
    service_factory: Callable[[KnowledgeSettings], KnowledgeService] = Field(
        default=_build_service,
        exclude=True,
        repr=False,
    )
    _service: KnowledgeService | None = PrivateAttr(default=None)

    def to_param(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The modeling or writing question to search for.",
                        },
                        "top_k": {
                            "type": "integer",
                            "default": self.default_top_k,
                            "minimum": 1,
                            "maximum": MAX_TOP_K,
                        },
                        "competition": {"type": "string"},
                        "year": {"type": "integer"},
                        "problem": {"type": "string"},
                        "award": {"type": "string"},
                        "language": {"type": "string"},
                        "methods": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        }

    async def execute(
        self,
        query: str,
        top_k: int | None = None,
        competition: str | None = None,
        year: int | None = None,
        problem: str | None = None,
        award: str | None = None,
        language: str | None = None,
        methods: list[str] | None = None,
    ) -> ToolResult:
        if not isinstance(query, str) or not query.strip():
            return ToolResult(error="query must be a non-empty string")
        effective_top_k = self.default_top_k if top_k is None else top_k
        invalid_top_k = (
            not isinstance(effective_top_k, int)
            or isinstance(effective_top_k, bool)
            or not 1 <= effective_top_k <= MAX_TOP_K
        )
        if invalid_top_k:
            return ToolResult(error="top_k must be between 1 and 12")
        if methods is not None and (
            not isinstance(methods, list)
            or not methods
            or any(not isinstance(method, str) or not method.strip() for method in methods)
        ):
            return ToolResult(error="methods must be a list of non-empty strings")

        filters = {
            "competition": competition,
            "year": year,
            "problem": problem,
            "award": award,
            "language": language,
            "methods": methods,
        }
        try:
            output = await asyncio.to_thread(
                self._search_and_trace,
                query,
                effective_top_k,
                filters,
            )
        except Exception as exc:
            _LOGGER.warning("paper knowledge base is unavailable: %s", exc)
            return ToolResult(error=f"Paper knowledge base is unavailable: {exc}")
        return ToolResult(output=output)

    def _search_and_trace(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any],
    ) -> str:
        try:
            service = self._get_service()
            hits = service.search(query, top_k=top_k, **filters)
            output = service.format_search_hits(hits)[:MAX_SEARCH_OUTPUT_CHARS]
            write_retrieval_trace(query=query, filters=filters, top_k=top_k, hits=hits)
            return output
        except Exception as exc:
            write_retrieval_trace(query=query, filters=filters, top_k=top_k, error=exc)
            raise

    def _get_service(self) -> KnowledgeService:
        if self._service is None:
            self._service = self.service_factory(config.knowledge)
        return self._service
