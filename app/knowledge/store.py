"""Qdrant collection lifecycle for the local paper knowledge base."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from qdrant_client import models

from app.knowledge.embeddings import KnowledgeEmbeddingProvider
from app.knowledge.ingestion import PaperDocument


T = TypeVar("T")
COLLECTION_SCHEMA_VERSION = 2
REINDEX_SMOKE_QUERY = "knowledge base smoke test"
MAX_CHUNKS_PER_PAPER = 1_000
_INDEX_FIELDS = {
    "paper_id": models.PayloadSchemaType.KEYWORD,
    "title": models.PayloadSchemaType.KEYWORD,
    "competition": models.PayloadSchemaType.KEYWORD,
    "year": models.PayloadSchemaType.INTEGER,
    "problem": models.PayloadSchemaType.KEYWORD,
    "award": models.PayloadSchemaType.KEYWORD,
    "language": models.PayloadSchemaType.KEYWORD,
    "methods": models.PayloadSchemaType.KEYWORD,
    "content_hash": models.PayloadSchemaType.KEYWORD,
    "record_type": models.PayloadSchemaType.KEYWORD,
}
_LOGGER = logging.getLogger(__name__)


class KnowledgeStoreError(RuntimeError):
    """A Qdrant operation required by the knowledge store failed."""


class IndexSchemaMismatchError(KnowledgeStoreError):
    """The configured stable alias points at vectors from another schema."""


class AmbiguousReindexError(KnowledgeStoreError):
    """An alias-switch timeout left the active collection state unknowable."""


@dataclass(frozen=True)
class PaperSummary:
    """One paper represented in the collection, with its indexed chunk count."""

    paper_id: str
    title: str
    competition: str
    year: int
    problem: str
    award: str
    language: str
    methods: tuple[str, ...]
    chunk_count: int


@dataclass(frozen=True)
class SearchHit:
    """A paper chunk returned by hybrid retrieval."""

    paper_id: str
    title: str
    competition: str
    year: int
    problem: str
    award: str
    language: str
    methods: tuple[str, ...]
    section_path: tuple[str, ...]
    source_file: str
    chunk_id: str
    score: float
    raw_latex: str


class KnowledgeStore:
    """Provision a schema-versioned physical collection behind a stable alias."""

    def __init__(
        self,
        client: Any,
        *,
        collection_name: str = "solvex_papers",
        dense_model: str = "intfloat/multilingual-e5-large",
        sparse_model: str = "Qdrant/bm25",
        embedding_provider: Any | None = None,
    ) -> None:
        self.client = client
        self.collection_name = collection_name
        self.dense_model = dense_model
        self.sparse_model = sparse_model
        self.embedding_provider = embedding_provider or KnowledgeEmbeddingProvider(
            dense_model=dense_model,
            sparse_model=sparse_model,
        )
        self.dense_dimension = self._resolve_dense_dimension()
        self.schema_fingerprint = _schema_fingerprint(
            dense_model,
            sparse_model,
            self.dense_dimension,
        )
        self.physical_collection = f"{collection_name}__{self.schema_fingerprint[:16]}"

    def ensure_collection(self) -> str:
        """Return the physical collection currently bound to the stable alias."""

        current = self._alias_target()
        if current is not None:
            if not current.endswith(self.schema_fingerprint[:16]):
                raise IndexSchemaMismatchError(
                    f"alias {self.collection_name!r} targets {current!r}, which does not "
                    f"match knowledge schema fingerprint {self.schema_fingerprint}"
                )
            self._verify_collection_fingerprint(current)
            return current

        self._create_physical_collection(self.physical_collection)
        self._call(
            "create collection alias",
            self.client.update_collection_aliases,
            [
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(
                        collection_name=self.physical_collection,
                        alias_name=self.collection_name,
                    )
                )
            ],
        )
        return self.physical_collection

    def index_document(
        self,
        document: PaperDocument,
        *,
        collection_name: str | None = None,
    ) -> int:
        """Embed and atomically upsert all chunks from one validated paper."""

        chunks = list(document.chunks)
        if len(chunks) > MAX_CHUNKS_PER_PAPER:
            raise KnowledgeStoreError(
                f"paper {document.manifest.paper_id!r} exceeds the maximum "
                f"{MAX_CHUNKS_PER_PAPER} chunks"
            )
        target = collection_name or self.ensure_collection()
        if not chunks:
            stale_ids = self._paper_point_ids(target, document.manifest.paper_id)
            if stale_ids:
                self._call(
                    "delete stale paper chunks",
                    self.client.delete,
                    target,
                    list(stale_ids),
                    wait=True,
                )
            return 0
        embeddings = self._embed_documents([chunk.normalized_text for chunk in chunks])
        if len(embeddings.dense) != len(chunks) or len(embeddings.sparse) != len(chunks):
            raise KnowledgeStoreError("embedding provider returned a mismatched number of vectors")
        indexed_at = datetime.now(timezone.utc).isoformat()
        points = [
            models.PointStruct(
                id=deterministic_point_id(
                    document.manifest.paper_id,
                    chunk.source_file,
                    chunk.section_path,
                    chunk.start_line,
                    chunk.end_line,
                    chunk_index,
                ),
                vector={
                    "dense": embeddings.dense[chunk_index],
                    "sparse": embeddings.sparse[chunk_index],
                },
                payload=_chunk_payload(document, chunk, chunk_index, indexed_at),
            )
            for chunk_index, chunk in enumerate(chunks)
        ]
        self._call("upsert paper chunks", self.client.upsert, target, points, wait=True)
        new_ids = {str(point.id) for point in points}
        stale_ids = self._paper_point_ids(target, document.manifest.paper_id) - new_ids
        if stale_ids:
            self._call(
                "delete stale paper chunks",
                self.client.delete,
                target,
                list(stale_ids),
                wait=True,
            )
        return len(points)

    def delete_paper(self, paper_id: str) -> int:
        """Delete every indexed chunk belonging to one paper."""

        target = self.ensure_collection()
        point_ids = self._paper_point_ids(target, paper_id)
        if point_ids:
            self._call(
                "delete paper chunks",
                self.client.delete,
                target,
                list(point_ids),
                wait=True,
            )
        return len(point_ids)

    def list_papers(self) -> list[PaperSummary]:
        """List each indexed paper once, with its current number of chunks."""

        target = self.ensure_collection()
        records = self._scroll_records(
            target,
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="record_type", match=models.MatchValue(value="chunk")
                    )
                ]
            ),
            with_payload=True,
        )
        papers: dict[str, PaperSummary] = {}
        for record in records:
            payload = record.payload or {}
            paper_id = payload["paper_id"]
            summary = papers.get(paper_id)
            if summary is None:
                papers[paper_id] = PaperSummary(
                    paper_id=paper_id,
                    title=payload["title"],
                    competition=payload["competition"],
                    year=payload["year"],
                    problem=payload["problem"],
                    award=payload["award"],
                    language=payload["language"],
                    methods=tuple(payload.get("methods", [])),
                    chunk_count=1,
                )
            else:
                papers[paper_id] = PaperSummary(
                    **{**summary.__dict__, "chunk_count": summary.chunk_count + 1}
                )
        return [papers[paper_id] for paper_id in sorted(papers)]

    def search(
        self,
        query: str,
        *,
        top_k: int = 6,
        competition: str | None = None,
        year: int | None = None,
        problem: str | None = None,
        award: str | None = None,
        language: str | None = None,
        methods: list[str] | tuple[str, ...] | None = None,
    ) -> list[SearchHit]:
        """Run RRF over dense and BM25 results for indexed paper chunks."""

        if top_k < 1:
            raise ValueError("top_k must be positive")
        limit = min(top_k, 12)
        target = self.ensure_collection()
        embedding = self._embed_query(query)
        query_filter = _search_filter(
            competition=competition,
            year=year,
            problem=problem,
            award=award,
            language=language,
            methods=methods,
        )
        prefetch_limit = max(20, limit * 4)
        response = self._call(
            "run hybrid paper search",
            self.client.query_points,
            target,
            prefetch=[
                models.Prefetch(
                    query=embedding.dense,
                    using="dense",
                    filter=query_filter,
                    limit=prefetch_limit,
                ),
                models.Prefetch(
                    query=embedding.sparse,
                    using="sparse",
                    filter=query_filter,
                    limit=prefetch_limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [_search_hit(record) for record in response.points]

    def reindex(self, documents: Iterable[PaperDocument]) -> str:
        """Build a fresh collection and atomically point the stable alias at it."""

        old_target = self._alias_target()
        staging = f"{self.physical_collection}__staging_{uuid4().hex[:12]}"
        try:
            # A collection can exist even if a later payload-index request fails.
            self._create_physical_collection(staging)
            indexed_chunks = 0
            for document in documents:
                indexed_chunks += self.index_document(document, collection_name=staging)
            self._verify_staging_collection(staging, smoke_query=indexed_chunks > 0)
        except Exception:
            self._cleanup_collection(staging)
            raise

        operations = _alias_switch_operations(
            alias_name=self.collection_name,
            old_target=old_target,
            staging=staging,
        )
        try:
            self._call("switch collection alias", self.client.update_collection_aliases, operations)
        except KnowledgeStoreError as switch_error:
            try:
                observed_target = self._alias_target()
            except KnowledgeStoreError as alias_read_error:
                raise AmbiguousReindexError(
                    "could not determine alias state after the collection-alias switch failed; "
                    "leaving both old and staging collections intact"
                ) from alias_read_error
            if observed_target == staging:
                _LOGGER.warning(
                    "collection alias switch raised an error but %s now targets staging %s",
                    self.collection_name,
                    staging,
                )
            elif observed_target == old_target:
                self._cleanup_collection(staging)
                raise switch_error
            else:
                raise AmbiguousReindexError(
                    "could not determine alias state after the collection-alias switch failed; "
                    "leaving both old and staging collections intact"
                ) from switch_error

        self._delete_old_collection_best_effort(old_target, staging)
        return staging

    def _verify_staging_collection(self, collection_name: str, *, smoke_query: bool) -> None:
        self._verify_collection_fingerprint(collection_name)
        self._call("smoke-read staging collection", self.client.count, collection_name, exact=True)
        if smoke_query:
            self._smoke_query_staging_collection(collection_name)

    def _smoke_query_staging_collection(self, collection_name: str) -> None:
        embedding = self._embed_query(REINDEX_SMOKE_QUERY)
        chunk_filter = _search_filter(
            competition=None,
            year=None,
            problem=None,
            award=None,
            language=None,
            methods=None,
        )
        self._call(
            "smoke-query staging collection",
            self.client.query_points,
            collection_name,
            prefetch=[
                models.Prefetch(
                    query=embedding.dense,
                    using="dense",
                    filter=chunk_filter,
                    limit=1,
                ),
                models.Prefetch(
                    query=embedding.sparse,
                    using="sparse",
                    filter=chunk_filter,
                    limit=1,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=chunk_filter,
            limit=1,
            with_payload=False,
            with_vectors=False,
        )

    def _verify_collection_fingerprint(self, collection_name: str) -> None:
        info = self._call("verify staging collection", self.client.get_collection, collection_name)
        metadata = getattr(info, "metadata", None)
        if metadata is None:
            metadata = getattr(getattr(info, "config", None), "metadata", None)
        if not isinstance(metadata, dict) or metadata.get("knowledge_schema_fingerprint") != self.schema_fingerprint:
            raise IndexSchemaMismatchError(
                f"collection {collection_name!r} has an unexpected knowledge schema fingerprint"
            )

    def _delete_old_collection_best_effort(
        self,
        old_target: str | None,
        staging: str,
    ) -> None:
        if old_target is None or old_target == staging:
            return
        try:
            self._call("delete old collection", self.client.delete_collection, old_target)
        except KnowledgeStoreError:
            _LOGGER.warning(
                "could not remove old collection %s after switching alias %s; retaining it for cleanup",
                old_target,
                self.collection_name,
                exc_info=True,
            )

    def _cleanup_collection(self, collection_name: str) -> None:
        try:
            self._call("delete failed staging collection", self.client.delete_collection, collection_name)
        except Exception:
            _LOGGER.exception("could not clean up failed staging collection %s", collection_name)

    def _paper_point_ids(self, collection_name: str, paper_id: str) -> set[str]:
        records = self._scroll_records(
            collection_name,
            _paper_filter(paper_id),
            with_payload=False,
        )
        return {str(record.id) for record in records}

    def _scroll_records(
        self,
        collection_name: str,
        scroll_filter: models.Filter,
        *,
        with_payload: bool,
    ) -> list[Any]:
        records: list[Any] = []
        offset: Any = None
        while True:
            page, offset = self._call(
                "scroll collection points",
                self.client.scroll,
                collection_name,
                scroll_filter=scroll_filter,
                limit=256,
                offset=offset,
                with_payload=with_payload,
                with_vectors=False,
            )
            records.extend(page)
            if offset is None:
                return records

    def _create_physical_collection(self, collection_name: str) -> None:
        self._call(
            "create collection",
            self.client.create_collection,
            collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=self.dense_dimension,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
            metadata={"knowledge_schema_fingerprint": self.schema_fingerprint},
        )
        for field_name, field_schema in _INDEX_FIELDS.items():
            self._call(
                f"create payload index {field_name}",
                self.client.create_payload_index,
                collection_name,
                field_name,
                field_schema,
            )

    def _alias_target(self) -> str | None:
        aliases = self._call("read collection aliases", self.client.get_aliases)
        for alias in aliases.aliases:
            if alias.alias_name == self.collection_name:
                return alias.collection_name
        return None

    def _resolve_dense_dimension(self) -> int:
        try:
            dimension = self.embedding_provider.dense_dimension()
        except Exception as exc:
            raise KnowledgeStoreError(
                f"could not determine dense vector dimension for model {self.dense_model!r}"
            ) from exc
        if not isinstance(dimension, int) or isinstance(dimension, bool) or dimension <= 0:
            raise KnowledgeStoreError("embedding provider returned an invalid dense vector dimension")
        return dimension

    def _embed_documents(self, texts: list[str]) -> Any:
        try:
            return self.embedding_provider.embed_documents(texts)
        except Exception as exc:
            raise KnowledgeStoreError("could not embed paper document chunks") from exc

    def _embed_query(self, query: str) -> Any:
        try:
            return self.embedding_provider.embed_query(query)
        except Exception as exc:
            raise KnowledgeStoreError("could not embed paper query") from exc

    @staticmethod
    def _call(action: str, operation: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        try:
            return operation(*args, **kwargs)
        except KnowledgeStoreError:
            raise
        except Exception as exc:
            raise KnowledgeStoreError(f"could not {action}: {exc}") from exc


def _schema_fingerprint(dense_model: str, sparse_model: str, dense_dimension: int) -> str:
    payload = json.dumps(
        {
            "schema_version": COLLECTION_SCHEMA_VERSION,
            "dense_model": dense_model,
            "sparse_model": sparse_model,
            "dense_dimension": dense_dimension,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _alias_switch_operations(
    *,
    alias_name: str,
    old_target: str | None,
    staging: str,
) -> list[Any]:
    operations: list[Any] = []
    if old_target is not None:
        operations.append(
            models.DeleteAliasOperation(
                delete_alias=models.DeleteAlias(alias_name=alias_name)
            )
        )
    operations.append(
        models.CreateAliasOperation(
            create_alias=models.CreateAlias(
                collection_name=staging,
                alias_name=alias_name,
            )
        )
    )
    return operations


def deterministic_point_id(
    paper_id: str,
    source_file: str,
    section_path: tuple[str, ...],
    start_line: int,
    end_line: int,
    chunk_index: int,
) -> UUID:
    """Return a repeatable UUIDv5 for one source-local chunk position."""

    canonical_section_path = "\x1e".join(
        " ".join(section.split()) for section in section_path
    )
    value = "\x1f".join(
        [
            paper_id,
            source_file,
            canonical_section_path,
            str(start_line),
            str(end_line),
            str(chunk_index),
        ]
    )
    return uuid5(NAMESPACE_URL, f"solvex-paper-chunk:{value}")


def _paper_filter(paper_id: str) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="record_type", match=models.MatchValue(value="chunk")
            ),
            models.FieldCondition(
                key="paper_id", match=models.MatchValue(value=paper_id)
            ),
        ]
    )


def _search_filter(
    *,
    competition: str | None,
    year: int | None,
    problem: str | None,
    award: str | None,
    language: str | None,
    methods: list[str] | tuple[str, ...] | None,
) -> models.Filter:
    conditions = [
        models.FieldCondition(
            key="record_type", match=models.MatchValue(value="chunk")
        )
    ]
    for key, value in (
        ("competition", competition),
        ("year", year),
        ("problem", problem),
        ("award", award),
        ("language", language),
    ):
        if value is not None:
            conditions.append(
                models.FieldCondition(key=key, match=models.MatchValue(value=value))
            )
    if methods:
        conditions.append(
            models.FieldCondition(key="methods", match=models.MatchAny(any=list(methods)))
        )
    return models.Filter(must=conditions)


def _search_hit(record: Any) -> SearchHit:
    payload = record.payload or {}
    return SearchHit(
        paper_id=payload["paper_id"],
        title=payload["title"],
        competition=payload["competition"],
        year=payload["year"],
        problem=payload["problem"],
        award=payload["award"],
        language=payload["language"],
        methods=tuple(payload.get("methods", [])),
        section_path=tuple(payload.get("section_path", [])),
        source_file=payload["source_file"],
        chunk_id=str(record.id),
        score=float(record.score),
        raw_latex=payload["raw_latex"],
    )


def _chunk_payload(document: PaperDocument, chunk: Any, chunk_index: int, indexed_at: str) -> dict[str, Any]:
    manifest = document.manifest
    return {
        "record_type": "chunk",
        "schema_version": manifest.schema_version,
        "paper_id": manifest.paper_id,
        "title": manifest.title,
        "competition": manifest.competition,
        "year": manifest.year,
        "problem": manifest.problem,
        "award": manifest.award,
        "language": manifest.language,
        "methods": manifest.methods,
        "main_tex": manifest.main_tex,
        "section_path": list(chunk.section_path),
        "source_file": chunk.source_file,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "chunk_index": chunk_index,
        "content_hash": hashlib.sha256(chunk.raw_latex.encode("utf-8")).hexdigest(),
        "raw_latex": chunk.raw_latex,
        "normalized_text": chunk.normalized_text,
        "indexed_at": indexed_at,
    }
