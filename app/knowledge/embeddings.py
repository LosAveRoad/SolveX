"""Lazy local embedding support for the paper knowledge base."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import re
from threading import RLock
from typing import Any

from qdrant_client import models

from app.knowledge.errors import KnowledgeIngestionError


EMBEDDING_BATCH_SIZE = 32


class KnowledgeEmbeddingError(KnowledgeIngestionError):
    """Raised when an embedding model returns an unusable embedding."""


@dataclass(frozen=True)
class EmbeddingBatch:
    """Dense and sparse vectors aligned with the submitted text order."""

    dense: list[list[float]]
    sparse: list[models.SparseVector]


@dataclass(frozen=True)
class QueryEmbedding:
    """The two vector representations used by a hybrid query."""

    dense: list[float]
    sparse: models.SparseVector


class KnowledgeEmbeddingProvider:
    """Load FastEmbed models only when an embedding is first requested."""

    def __init__(
        self,
        *,
        dense_model: str = "intfloat/multilingual-e5-large",
        sparse_model: str = "Qdrant/bm25",
        dense_factory: Callable[..., Any] | None = None,
        sparse_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.dense_model = dense_model
        self.sparse_model = sparse_model
        self._dense_factory = dense_factory
        self._sparse_factory = sparse_factory
        self._dense_embedding: Any | None = None
        self._sparse_embedding: Any | None = None
        self._dense_dimension: int | None = None
        self._cache_dir: str | None = None
        self._lock = RLock()

    def dense_dimension(self) -> int:
        """Read the configured dense model dimension from FastEmbed's static registry."""

        with self._lock:
            if self._dense_dimension is not None:
                return self._dense_dimension
            try:
                from fastembed import TextEmbedding

                definitions = TextEmbedding.list_supported_models()
            except Exception as exc:
                raise KnowledgeEmbeddingError("could not read dense embedding model metadata") from exc
            definition = next(
                (entry for entry in definitions if entry.get("model") == self.dense_model),
                None,
            )
            dimension = definition.get("dim") if definition is not None else None
            if not isinstance(dimension, int) or isinstance(dimension, bool) or dimension <= 0:
                raise KnowledgeEmbeddingError(
                    f"dense model {self.dense_model!r} does not declare a dense vector dimension"
                )
            self._dense_dimension = dimension
            return dimension

    def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Embed paper chunks using the E5 passage prefix."""

        documents = list(texts)
        if not documents:
            return EmbeddingBatch(dense=[], sparse=[])
        dense_texts = [f"passage: {text}" for text in documents]
        sparse_texts = [augment_sparse_text(text) for text in documents]
        with self._lock:
            dense_embedding, sparse_embedding = self._models()
            try:
                dense: list[list[float]] = []
                sparse: list[models.SparseVector] = []
                for dense_batch, sparse_batch in zip(
                    _batches(dense_texts), _batches(sparse_texts), strict=True
                ):
                    dense.extend(
                        _as_float_list(vector) for vector in dense_embedding.embed(dense_batch)
                    )
                    sparse.extend(
                        _as_sparse_vector(vector) for vector in sparse_embedding.embed(sparse_batch)
                    )
            except KnowledgeEmbeddingError:
                raise
            except Exception as exc:
                raise KnowledgeEmbeddingError("could not embed paper documents") from exc
        return _embedding_batch(dense, sparse, len(documents))

    def embed_query(self, query: str) -> QueryEmbedding:
        """Embed one user query using the E5 query prefix."""

        with self._lock:
            dense_embedding, sparse_embedding = self._models()
            try:
                dense = [_as_float_list(vector) for vector in dense_embedding.embed([f"query: {query}"])]
                sparse = [
                    _as_sparse_vector(vector)
                    for vector in sparse_embedding.query_embed([augment_sparse_text(query)])
                ]
            except KnowledgeEmbeddingError:
                raise
            except Exception as exc:
                raise KnowledgeEmbeddingError("could not embed paper query") from exc
        batch = _embedding_batch(dense, sparse, 1)
        return QueryEmbedding(dense=batch.dense[0], sparse=batch.sparse[0])

    def _models(self) -> tuple[Any, Any]:
        cache_dir = self._get_cache_dir()
        if self._dense_embedding is None:
            factory = self._dense_factory
            if factory is None:
                from fastembed import TextEmbedding

                factory = TextEmbedding
            try:
                self._dense_embedding = factory(self.dense_model, cache_dir=cache_dir)
            except Exception as exc:
                raise KnowledgeEmbeddingError("could not load dense embedding model") from exc
        if self._sparse_embedding is None:
            factory = self._sparse_factory
            if factory is None:
                from fastembed import SparseTextEmbedding

                factory = SparseTextEmbedding
            try:
                self._sparse_embedding = factory(self.sparse_model, cache_dir=cache_dir)
            except Exception as exc:
                raise KnowledgeEmbeddingError("could not load sparse embedding model") from exc
        return self._dense_embedding, self._sparse_embedding

    def _get_cache_dir(self) -> str:
        if self._cache_dir is None:
            configured = os.environ.get("FASTEMBED_CACHE_PATH")
            cache_dir = (
                Path(configured).expanduser()
                if configured
                else Path.home() / ".cache" / "solvex" / "fastembed"
            )
            self._cache_dir = str(cache_dir)
        return self._cache_dir


_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def augment_sparse_text(raw_text: str) -> str:
    """Append CJK bigrams so whitespace-tokenized BM25 can match Chinese phrases."""

    bigrams = [
        run[index : index + 2]
        for run in _CJK_RUN.findall(raw_text)
        for index in range(len(run) - 1)
    ]
    return raw_text if not bigrams else f"{raw_text} {' '.join(bigrams)}"


def _embedding_batch(
    dense: list[list[float]],
    sparse: list[models.SparseVector],
    expected_count: int,
) -> EmbeddingBatch:
    if len(dense) != expected_count or len(sparse) != expected_count:
        raise KnowledgeEmbeddingError("embedding model returned a mismatched number of vectors")
    return EmbeddingBatch(dense=dense, sparse=sparse)


def _batches(texts: list[str]) -> list[list[str]]:
    return [texts[index : index + EMBEDDING_BATCH_SIZE] for index in range(0, len(texts), EMBEDDING_BATCH_SIZE)]


def _as_float_list(vector: Any) -> list[float]:
    return [float(value) for value in vector]


def _as_sparse_vector(vector: Any) -> models.SparseVector:
    try:
        indices = [int(value) for value in vector.indices]
        values = [float(value) for value in vector.values]
    except AttributeError as exc:
        raise KnowledgeEmbeddingError("sparse embedding is missing indices or values") from exc
    if len(indices) != len(values):
        raise KnowledgeEmbeddingError("sparse embedding indices and values have different lengths")
    return models.SparseVector(indices=indices, values=values)
