"""Session-scoped audit traces for paper retrieval."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Iterator


_LOGGER = logging.getLogger(__name__)
_TRACE_PATH: ContextVar[Path | None] = ContextVar("paper_retrieval_trace_path", default=None)
_WRITE_LOCK = Lock()


def current_retrieval_trace_path() -> Path | None:
    """Return the active session trace path, if retrieval runs inside a flow."""

    return _TRACE_PATH.get()


@contextmanager
def retrieval_trace_path(path: Path) -> Iterator[None]:
    """Bind retrieval auditing to one flow execution and always restore the caller context."""

    token = _TRACE_PATH.set(Path(path))
    try:
        yield
    finally:
        _TRACE_PATH.reset(token)


def write_retrieval_trace(
    *,
    query: str,
    filters: dict[str, Any],
    top_k: int,
    hits: list[Any] | None = None,
    error: Exception | None = None,
) -> bool:
    """Append one JSONL record without ever including retrieved paper content."""

    path = current_retrieval_trace_path()
    if path is None:
        return False

    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "filters": {key: value for key, value in filters.items() if value is not None},
        "top_k": top_k,
    }
    if error is None:
        result_hits = hits or []
        record["hit_count"] = len(result_hits)
        record["hits"] = [
            {
                "paper_id": hit.paper_id,
                "chunk_id": hit.chunk_id,
                "score": hit.score,
            }
            for hit in result_hits
        ]
    else:
        record["warning"] = True
        record["error"] = str(error)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with _WRITE_LOCK:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
    except OSError:
        _LOGGER.warning("could not write paper retrieval trace", exc_info=True)
        return False
    return True
