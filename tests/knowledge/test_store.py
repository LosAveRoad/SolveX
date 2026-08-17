from __future__ import annotations

from types import SimpleNamespace

import pytest


class FakeQdrantClient:
    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}
        self.collections: dict[str, object] = {}
        self.created: list[tuple[str, dict[str, object]]] = []
        self.payload_indexes: list[tuple[str, str, object]] = []
        self.alias_updates: list[list[object]] = []
        self.points: dict[str, dict[str, object]] = {}
        self.queries: list[dict[str, object]] = []
        self.query_response: list[object] = []
        self.deleted_collections: list[str] = []
        self.count_calls: list[str] = []
        self.upserts: list[tuple[str, list[object]]] = []

    def get_aliases(self):
        return SimpleNamespace(
            aliases=[
                SimpleNamespace(alias_name=name, collection_name=collection)
                for name, collection in self.aliases.items()
            ]
        )

    def create_collection(self, collection_name: str, **kwargs):
        self.collections[collection_name] = SimpleNamespace(metadata=kwargs.get("metadata"))
        self.created.append((collection_name, kwargs))
        return True

    def create_payload_index(self, collection_name: str, field_name: str, field_schema):
        self.payload_indexes.append((collection_name, field_name, field_schema))
        return True

    def update_collection_aliases(self, change_aliases_operations):
        self.alias_updates.append(list(change_aliases_operations))
        for operation in change_aliases_operations:
            if getattr(operation, "create_alias", None):
                create = operation.create_alias
                self.aliases[create.alias_name] = create.collection_name
            if getattr(operation, "delete_alias", None):
                self.aliases.pop(operation.delete_alias.alias_name, None)
        return True

    def upsert(self, collection_name: str, points, wait: bool = True):
        self.upserts.append((collection_name, list(points)))
        collection = self.points.setdefault(collection_name, {})
        for point in points:
            collection[str(point.id)] = point
        return True

    def scroll(
        self,
        collection_name: str,
        scroll_filter=None,
        limit: int = 10,
        offset=None,
        with_payload=True,
        with_vectors=False,
    ):
        points = [
            point
            for point in self.points.get(collection_name, {}).values()
            if _matches_filter(point.payload, scroll_filter)
        ]
        return [SimpleNamespace(id=point.id, payload=point.payload) for point in points], None

    def delete(self, collection_name: str, points_selector, wait: bool = True):
        collection = self.points.setdefault(collection_name, {})
        for point_id in points_selector:
            collection.pop(str(point_id), None)
        return True

    def query_points(self, collection_name: str, **kwargs):
        self.queries.append({"collection_name": collection_name, **kwargs})
        return SimpleNamespace(points=self.query_response)

    def get_collection(self, collection_name: str):
        return self.collections[collection_name]

    def count(self, collection_name: str, exact: bool = True):
        self.count_calls.append(collection_name)
        return SimpleNamespace(count=len(self.points.get(collection_name, {})))

    def delete_collection(self, collection_name: str):
        self.deleted_collections.append(collection_name)
        self.collections.pop(collection_name, None)
        self.points.pop(collection_name, None)
        return True


class FixedDimensionEmbeddings:
    def dense_dimension(self):
        return 1024


def _matches_filter(payload, query_filter) -> bool:
    if query_filter is None:
        return True
    for condition in query_filter.must or []:
        value = payload.get(condition.key)
        match = condition.match
        if getattr(match, "value", None) is not None and value != match.value:
            return False
        if getattr(match, "any", None) is not None:
            expected = set(match.any)
            values = value if isinstance(value, list) else [value]
            if not expected.intersection(values):
                return False
    return True


def test_ensure_collection_creates_named_vectors_indexes_and_stable_alias() -> None:
    from app.knowledge.store import KnowledgeStore
    from qdrant_client import models

    client = FakeQdrantClient()
    store = KnowledgeStore(
        client,
        collection_name="solvex_papers",
        dense_model="intfloat/multilingual-e5-large",
        sparse_model="Qdrant/bm25",
    )

    target = store.ensure_collection()

    assert target == client.aliases["solvex_papers"]
    assert target.startswith("solvex_papers__")
    _, kwargs = client.created[0]
    dense = kwargs["vectors_config"]["dense"]
    assert dense.size == 1024
    assert dense.distance == models.Distance.COSINE
    assert set(kwargs["sparse_vectors_config"]) == {"sparse"}
    assert kwargs["sparse_vectors_config"]["sparse"].modifier == models.Modifier.IDF
    assert kwargs["metadata"]["knowledge_schema_fingerprint"] == store.schema_fingerprint
    assert dict((name, schema) for _, name, schema in client.payload_indexes) == {
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


def test_collection_uses_the_embedding_provider_dense_dimension() -> None:
    from app.knowledge.store import KnowledgeStore

    class CustomDimensionEmbeddings:
        def dense_dimension(self):
            return 7

    client = FakeQdrantClient()
    store = KnowledgeStore(client, embedding_provider=CustomDimensionEmbeddings())

    store.ensure_collection()

    assert client.created[0][1]["vectors_config"]["dense"].size == 7


def test_real_qdrant_memory_collection_uses_sparse_idf_modifier() -> None:
    from qdrant_client import QdrantClient, models

    from app.knowledge.store import KnowledgeStore

    class ThreeDimensionalEmbeddings:
        def dense_dimension(self):
            return 3

    client = QdrantClient(":memory:")
    store = KnowledgeStore(client, collection_name="memory_papers", embedding_provider=ThreeDimensionalEmbeddings())

    with pytest.warns(UserWarning, match="Payload indexes have no effect"):
        target = store.ensure_collection()
    info = client.get_collection(target)

    assert info.config.params.vectors["dense"].size == 3
    assert info.config.params.sparse_vectors["sparse"].modifier == models.Modifier.IDF


def test_ensure_collection_rejects_an_alias_for_another_embedding_schema() -> None:
    from app.knowledge.store import IndexSchemaMismatchError, KnowledgeStore

    client = FakeQdrantClient()
    client.aliases["solvex_papers"] = "solvex_papers__old_schema"
    store = KnowledgeStore(client, collection_name="solvex_papers")

    with pytest.raises(IndexSchemaMismatchError, match="fingerprint"):
        store.ensure_collection()

    assert client.created == []


def test_ensure_collection_checks_the_alias_target_metadata_fingerprint() -> None:
    from app.knowledge.store import IndexSchemaMismatchError, KnowledgeStore

    client = FakeQdrantClient()
    store = KnowledgeStore(client)
    client.aliases[store.collection_name] = store.physical_collection
    client.collections[store.physical_collection] = SimpleNamespace(
        metadata={"knowledge_schema_fingerprint": "wrong"}
    )

    with pytest.raises(IndexSchemaMismatchError, match="fingerprint"):
        store.ensure_collection()


def test_index_document_upserts_deterministic_chunk_points_with_source_payload() -> None:
    from app.knowledge.chunking import LatexChunk
    from app.knowledge.embeddings import EmbeddingBatch
    from app.knowledge.ingestion import PaperDocument
    from app.knowledge.manifest import PaperManifest
    from app.knowledge.store import KnowledgeStore
    from qdrant_client import models

    class FakeEmbeddings(FixedDimensionEmbeddings):
        def embed_documents(self, texts):
            assert list(texts) == ["first model paragraph", "second model paragraph"]
            return EmbeddingBatch(
                dense=[[0.1] * 1024, [0.2] * 1024],
                sparse=[
                    models.SparseVector(indices=[1], values=[0.5]),
                    models.SparseVector(indices=[2], values=[0.6]),
                ],
            )

    document = PaperDocument(
        manifest=PaperManifest(
            schema_version=1,
            paper_id="mcm-2025-c-01",
            title="A Good Model",
            competition="MCM",
            year=2025,
            problem="C",
            award="Outstanding Winner",
            language="en",
            methods=["optimization", "regression"],
            main_tex="main.tex",
        ),
        chunks=(
            LatexChunk(
                raw_latex="First raw \\alpha",
                normalized_text="first model paragraph",
                section_path=("Method",),
                source_file="main.tex",
                start_line=10,
                end_line=11,
            ),
            LatexChunk(
                raw_latex="Second raw",
                normalized_text="second model paragraph",
                section_path=("Method", "Fit"),
                source_file="parts/model.tex",
                start_line=2,
                end_line=4,
            ),
        ),
    )
    client = FakeQdrantClient()
    store = KnowledgeStore(client, embedding_provider=FakeEmbeddings())

    indexed = store.index_document(document)

    assert indexed == 2
    stored = list(client.points[store.physical_collection].values())
    assert len(stored) == 2
    assert all(set(point.vector) == {"dense", "sparse"} for point in stored)
    first = stored[0]
    assert first.payload["paper_id"] == "mcm-2025-c-01"
    assert first.payload["schema_version"] == 1
    assert first.payload["main_tex"] == "main.tex"
    assert first.payload["section_path"] == ["Method"]
    assert first.payload["source_file"] == "main.tex"
    assert first.payload["start_line"] == 10
    assert first.payload["end_line"] == 11
    assert first.payload["chunk_index"] == 0
    assert first.payload["record_type"] == "chunk"
    assert first.payload["raw_latex"] == "First raw \\alpha"
    assert first.payload["normalized_text"] == "first model paragraph"
    assert isinstance(first.payload["content_hash"], str)
    assert isinstance(first.payload["indexed_at"], str)


def test_chunk_point_ids_are_deterministic_and_source_specific() -> None:
    from app.knowledge.store import deterministic_point_id

    first = deterministic_point_id("paper-a", "main.tex", ("Method", "Fit Model"), 10, 12, 0)

    assert first == deterministic_point_id(
        "paper-a", "main.tex", (" Method ", "Fit   Model"), 10, 12, 0
    )
    assert first != deterministic_point_id("paper-a", "main.tex", ("Method", "Fit Model"), 10, 12, 1)
    assert first != deterministic_point_id("paper-a", "parts/main.tex", ("Method", "Fit Model"), 10, 12, 0)
    assert first != deterministic_point_id("paper-a", "main.tex", ("Results", "Fit Model"), 10, 12, 0)
    assert first.version == 5


def test_reimport_removes_stale_chunks_only_after_the_new_points_are_upserted() -> None:
    from app.knowledge.chunking import LatexChunk
    from app.knowledge.embeddings import EmbeddingBatch
    from app.knowledge.ingestion import PaperDocument
    from app.knowledge.manifest import PaperManifest
    from app.knowledge.store import KnowledgeStore
    from qdrant_client import models

    manifest = PaperManifest(
        schema_version=1,
        paper_id="same-paper",
        title="Same Paper",
        competition="MCM",
        year=2025,
        problem="A",
        award="Finalist",
        language="en",
        methods=["regression"],
        main_tex="main.tex",
    )

    def document(*texts: str) -> PaperDocument:
        return PaperDocument(
            manifest=manifest,
            chunks=tuple(
                LatexChunk(
                    raw_latex=text,
                    normalized_text=text,
                    section_path=("Method",),
                    source_file="main.tex",
                    start_line=10 + index,
                    end_line=10 + index,
                )
                for index, text in enumerate(texts)
            ),
        )

    class FakeEmbeddings(FixedDimensionEmbeddings):
        def embed_documents(self, texts):
            values = list(texts)
            return EmbeddingBatch(
                dense=[[float(index)] * 1024 for index in range(len(values))],
                sparse=[models.SparseVector(indices=[index], values=[1.0]) for index in range(len(values))],
            )

    client = FakeQdrantClient()
    store = KnowledgeStore(client, embedding_provider=FakeEmbeddings())
    store.index_document(document("old first", "obsolete second"))

    store.index_document(document("updated first"))

    remaining = list(client.points[store.physical_collection].values())
    assert len(remaining) == 1
    assert remaining[0].payload["raw_latex"] == "updated first"


def test_reimport_with_no_chunks_removes_existing_chunks_for_that_paper() -> None:
    from app.knowledge.chunking import LatexChunk
    from app.knowledge.embeddings import EmbeddingBatch
    from app.knowledge.ingestion import PaperDocument
    from app.knowledge.manifest import PaperManifest
    from app.knowledge.store import KnowledgeStore
    from qdrant_client import models

    class FakeEmbeddings(FixedDimensionEmbeddings):
        def embed_documents(self, texts):
            return EmbeddingBatch(
                dense=[[0.0] * 1024],
                sparse=[models.SparseVector(indices=[1], values=[1.0])],
            )

    manifest = PaperManifest(
        schema_version=1,
        paper_id="empty-reimport",
        title="Empty Reimport",
        competition="MCM",
        year=2025,
        problem="A",
        award="Finalist",
        language="en",
        methods=[],
        main_tex="main.tex",
    )
    client = FakeQdrantClient()
    store = KnowledgeStore(client, embedding_provider=FakeEmbeddings())
    store.index_document(
        PaperDocument(
            manifest=manifest,
            chunks=(LatexChunk("text", "text", ("Method",), "main.tex", 1, 1),),
        )
    )

    assert store.index_document(PaperDocument(manifest=manifest, chunks=())) == 0
    assert client.points[store.physical_collection] == {}


def test_index_document_rejects_a_paper_with_more_than_1000_chunks_before_embedding() -> None:
    from app.knowledge.chunking import LatexChunk
    from app.knowledge.ingestion import PaperDocument
    from app.knowledge.manifest import PaperManifest
    from app.knowledge.store import KnowledgeStore, KnowledgeStoreError, MAX_CHUNKS_PER_PAPER

    class NoEmbeddingAllowed(FixedDimensionEmbeddings):
        def embed_documents(self, texts):
            raise AssertionError("oversized papers must be rejected before embedding")

    document = PaperDocument(
        manifest=PaperManifest(
            schema_version=1,
            paper_id="too-many-chunks",
            title="Too Many",
            competition="MCM",
            year=2025,
            problem="A",
            award="Finalist",
            language="en",
            methods=[],
            main_tex="main.tex",
        ),
        chunks=tuple(
            LatexChunk("text", "text", ("Method",), "main.tex", index, index)
            for index in range(MAX_CHUNKS_PER_PAPER + 1)
        ),
    )
    store = KnowledgeStore(FakeQdrantClient(), embedding_provider=NoEmbeddingAllowed())

    with pytest.raises(KnowledgeStoreError, match="maximum 1000 chunks"):
        store.index_document(document)


def test_index_document_upserts_all_batched_embeddings_once_before_removing_stale_chunks() -> None:
    from app.knowledge.chunking import LatexChunk
    from app.knowledge.embeddings import EmbeddingBatch
    from app.knowledge.ingestion import PaperDocument
    from app.knowledge.manifest import PaperManifest
    from app.knowledge.store import KnowledgeStore
    from qdrant_client import models

    class FakeEmbeddings(FixedDimensionEmbeddings):
        def embed_documents(self, texts):
            values = list(texts)
            return EmbeddingBatch(
                dense=[[0.1] * 1024 for _ in values],
                sparse=[models.SparseVector(indices=[1], values=[1.0]) for _ in values],
            )

    manifest = PaperManifest(
        schema_version=1,
        paper_id="batch-paper",
        title="Batch Paper",
        competition="MCM",
        year=2025,
        problem="A",
        award="Finalist",
        language="en",
        methods=[],
        main_tex="main.tex",
    )

    def document(chunk_count: int) -> PaperDocument:
        return PaperDocument(
            manifest=manifest,
            chunks=tuple(
                LatexChunk(
                    f"raw {index}",
                    f"normalized {index}",
                    ("Method",),
                    "main.tex",
                    index,
                    index,
                )
                for index in range(chunk_count)
            ),
        )

    client = FakeQdrantClient()
    store = KnowledgeStore(client, embedding_provider=FakeEmbeddings())
    store.index_document(document(33))
    client.upserts.clear()

    store.index_document(document(1))

    assert len(client.upserts) == 1
    assert len(client.upserts[0][1]) == 1
    assert len(client.points[store.physical_collection]) == 1


def test_store_wraps_document_embedding_provider_errors_and_preserves_the_cause() -> None:
    from app.knowledge.chunking import LatexChunk
    from app.knowledge.embeddings import KnowledgeEmbeddingError
    from app.knowledge.ingestion import PaperDocument
    from app.knowledge.manifest import PaperManifest
    from app.knowledge.store import KnowledgeStore, KnowledgeStoreError

    class BrokenEmbeddings(FixedDimensionEmbeddings):
        def embed_documents(self, texts):
            raise KnowledgeEmbeddingError("dense runtime failed")

    document = PaperDocument(
        manifest=PaperManifest(
            schema_version=1,
            paper_id="broken-paper",
            title="Broken",
            competition="MCM",
            year=2025,
            problem="A",
            award="Finalist",
            language="en",
            methods=[],
            main_tex="main.tex",
        ),
        chunks=(LatexChunk("text", "text", ("Method",), "main.tex", 1, 1),),
    )

    with pytest.raises(KnowledgeStoreError, match="embed paper document chunks") as error:
        KnowledgeStore(FakeQdrantClient(), embedding_provider=BrokenEmbeddings()).index_document(document)

    assert isinstance(error.value.__cause__, KnowledgeEmbeddingError)


def test_store_wraps_query_embedding_provider_errors_and_preserves_the_cause() -> None:
    from app.knowledge.embeddings import KnowledgeEmbeddingError
    from app.knowledge.store import KnowledgeStore, KnowledgeStoreError

    class BrokenEmbeddings(FixedDimensionEmbeddings):
        def embed_query(self, query):
            raise KnowledgeEmbeddingError("sparse runtime failed")

    with pytest.raises(KnowledgeStoreError, match="embed paper query") as error:
        KnowledgeStore(FakeQdrantClient(), embedding_provider=BrokenEmbeddings()).search("query")

    assert isinstance(error.value.__cause__, KnowledgeEmbeddingError)


def test_list_and_delete_paper_preserve_other_papers() -> None:
    from app.knowledge.chunking import LatexChunk
    from app.knowledge.embeddings import EmbeddingBatch
    from app.knowledge.ingestion import PaperDocument
    from app.knowledge.manifest import PaperManifest
    from app.knowledge.store import KnowledgeStore
    from qdrant_client import models

    class FakeEmbeddings(FixedDimensionEmbeddings):
        def embed_documents(self, texts):
            return EmbeddingBatch(
                dense=[[0.0] * 1024 for _ in texts],
                sparse=[models.SparseVector(indices=[1], values=[1.0]) for _ in texts],
            )

    def paper(paper_id: str, title: str) -> PaperDocument:
        return PaperDocument(
            manifest=PaperManifest(
                schema_version=1,
                paper_id=paper_id,
                title=title,
                competition="MCM",
                year=2025,
                problem="B",
                award="Meritorious Winner",
                language="en",
                methods=["optimization"],
                main_tex="main.tex",
            ),
            chunks=(
                LatexChunk(
                    raw_latex=title,
                    normalized_text=title,
                    section_path=("Abstract",),
                    source_file="main.tex",
                    start_line=1,
                    end_line=1,
                ),
            ),
        )

    client = FakeQdrantClient()
    store = KnowledgeStore(client, embedding_provider=FakeEmbeddings())
    store.index_document(paper("paper-a", "Paper A"))
    store.index_document(paper("paper-b", "Paper B"))

    papers = store.list_papers()
    assert [(paper.paper_id, paper.title, paper.chunk_count) for paper in papers] == [
        ("paper-a", "Paper A", 1),
        ("paper-b", "Paper B", 1),
    ]

    assert store.delete_paper("paper-a") == 1
    assert [point.payload["paper_id"] for point in client.points[store.physical_collection].values()] == [
        "paper-b"
    ]


def test_search_uses_rrf_prefetches_exact_metadata_and_any_method_filter() -> None:
    from app.knowledge.embeddings import QueryEmbedding
    from app.knowledge.store import KnowledgeStore
    from qdrant_client import models

    class FakeEmbeddings(FixedDimensionEmbeddings):
        def embed_query(self, query):
            assert query == "robust optimization model"
            return QueryEmbedding(
                dense=[0.25] * 1024,
                sparse=models.SparseVector(indices=[2, 8], values=[1.0, 0.3]),
            )

    client = FakeQdrantClient()
    client.query_response = [
        SimpleNamespace(
            id="chunk-1",
            score=0.91,
            payload={
                "paper_id": "paper-a",
                "title": "Paper A",
                "competition": "MCM",
                "year": 2025,
                "problem": "C",
                "award": "Outstanding Winner",
                "language": "en",
                "methods": ["optimization"],
                "section_path": ["Method", "Robust Model"],
                "source_file": "main.tex",
                "raw_latex": "\\alpha x",
            },
        )
    ]
    store = KnowledgeStore(client, embedding_provider=FakeEmbeddings())

    hits = store.search(
        "robust optimization model",
        top_k=99,
        competition="MCM",
        year=2025,
        problem="C",
        award="Outstanding Winner",
        language="en",
        methods=["optimization", "robustness"],
    )

    assert [(hit.chunk_id, hit.score, hit.section_path) for hit in hits] == [
        ("chunk-1", 0.91, ("Method", "Robust Model"))
    ]
    query = client.queries[0]
    assert query["limit"] == 12
    assert isinstance(query["query"], models.FusionQuery)
    assert query["query"].fusion == models.Fusion.RRF
    assert [(prefetch.using, prefetch.limit) for prefetch in query["prefetch"]] == [
        ("dense", 48),
        ("sparse", 48),
    ]
    assert query["prefetch"][0].query == [0.25] * 1024
    assert query["prefetch"][1].query.indices == [2, 8]
    conditions = {condition.key: condition.match for condition in query["query_filter"].must}
    assert conditions["record_type"].value == "chunk"
    assert conditions["competition"].value == "MCM"
    assert conditions["year"].value == 2025
    assert conditions["methods"].any == ["optimization", "robustness"]


def test_reindex_builds_staging_then_atomically_swaps_alias_and_removes_old_collection() -> None:
    from app.knowledge.chunking import LatexChunk
    from app.knowledge.embeddings import EmbeddingBatch, QueryEmbedding
    from app.knowledge.ingestion import PaperDocument
    from app.knowledge.manifest import PaperManifest
    from app.knowledge.store import KnowledgeStore
    from qdrant_client import models

    class FakeEmbeddings(FixedDimensionEmbeddings):
        def embed_documents(self, texts):
            values = list(texts)
            return EmbeddingBatch(
                dense=[[0.1] * 1024 for _ in values],
                sparse=[models.SparseVector(indices=[1], values=[1.0]) for _ in values],
            )

        def embed_query(self, query):
            assert query == "knowledge base smoke test"
            return QueryEmbedding(
                dense=[0.2] * 1024,
                sparse=models.SparseVector(indices=[2], values=[1.0]),
            )

    document = PaperDocument(
        manifest=PaperManifest(
            schema_version=1,
            paper_id="new-paper",
            title="New Paper",
            competition="MCM",
            year=2025,
            problem="C",
            award="Finalist",
            language="en",
            methods=["optimization"],
            main_tex="main.tex",
        ),
        chunks=(
            LatexChunk("new", "new", ("Method",), "main.tex", 1, 1),
        ),
    )
    client = FakeQdrantClient()
    client.aliases["solvex_papers"] = "solvex_papers__old"
    client.collections["solvex_papers__old"] = SimpleNamespace(metadata={})
    store = KnowledgeStore(client, embedding_provider=FakeEmbeddings())

    target = store.reindex([document])

    assert target == client.aliases["solvex_papers"]
    assert target.startswith(f"{store.physical_collection}__staging_")
    assert client.count_calls == [target]
    assert client.deleted_collections == ["solvex_papers__old"]
    assert len(client.alias_updates[-1]) == 2
    assert client.queries[0]["collection_name"] == target
    assert [(item.using, item.limit) for item in client.queries[0]["prefetch"]] == [
        ("dense", 1),
        ("sparse", 1),
    ]
    assert isinstance(client.queries[0]["query"], models.FusionQuery)


def test_reindex_failure_cleans_staging_without_changing_existing_alias() -> None:
    from app.knowledge.chunking import LatexChunk
    from app.knowledge.ingestion import PaperDocument
    from app.knowledge.manifest import PaperManifest
    from app.knowledge.store import KnowledgeStore, KnowledgeStoreError

    class FailingEmbeddings(FixedDimensionEmbeddings):
        def embed_documents(self, texts):
            raise RuntimeError("embedding failed")

    document = PaperDocument(
        manifest=PaperManifest(
            schema_version=1,
            paper_id="bad-paper",
            title="Bad Paper",
            competition="MCM",
            year=2025,
            problem="C",
            award="Finalist",
            language="en",
            methods=[],
            main_tex="main.tex",
        ),
        chunks=(LatexChunk("bad", "bad", ("Method",), "main.tex", 1, 1),),
    )
    client = FakeQdrantClient()
    client.aliases["solvex_papers"] = "solvex_papers__old"
    client.collections["solvex_papers__old"] = SimpleNamespace(metadata={})
    store = KnowledgeStore(client, embedding_provider=FailingEmbeddings())

    with pytest.raises(KnowledgeStoreError, match="embed paper document chunks") as error:
        store.reindex([document])

    assert isinstance(error.value.__cause__, RuntimeError)
    assert client.aliases["solvex_papers"] == "solvex_papers__old"
    assert len(client.deleted_collections) == 1
    assert client.alias_updates == []


def test_reindex_smoke_query_failure_keeps_old_alias_and_cleans_staging() -> None:
    from app.knowledge.chunking import LatexChunk
    from app.knowledge.embeddings import EmbeddingBatch, QueryEmbedding
    from app.knowledge.ingestion import PaperDocument
    from app.knowledge.manifest import PaperManifest
    from app.knowledge.store import KnowledgeStore, KnowledgeStoreError
    from qdrant_client import models

    class SmokeQueryFails(FakeQdrantClient):
        def query_points(self, collection_name: str, **kwargs):
            raise RuntimeError("staging query failed")

    class FakeEmbeddings(FixedDimensionEmbeddings):
        def embed_documents(self, texts):
            return EmbeddingBatch(
                dense=[[0.1] * 1024],
                sparse=[models.SparseVector(indices=[1], values=[1.0])],
            )

        def embed_query(self, query):
            return QueryEmbedding(
                dense=[0.2] * 1024,
                sparse=models.SparseVector(indices=[2], values=[1.0]),
            )

    document = PaperDocument(
        manifest=PaperManifest(
            schema_version=1,
            paper_id="smoke-paper",
            title="Smoke Paper",
            competition="MCM",
            year=2025,
            problem="C",
            award="Finalist",
            language="en",
            methods=[],
            main_tex="main.tex",
        ),
        chunks=(LatexChunk("text", "text", ("Method",), "main.tex", 1, 1),),
    )
    client = SmokeQueryFails()
    client.aliases["solvex_papers"] = "solvex_papers__old"
    client.collections["solvex_papers__old"] = SimpleNamespace(metadata={})
    store = KnowledgeStore(client, embedding_provider=FakeEmbeddings())

    with pytest.raises(KnowledgeStoreError, match="smoke-query staging collection"):
        store.reindex([document])

    assert client.aliases["solvex_papers"] == "solvex_papers__old"
    assert len(client.deleted_collections) == 1
    assert client.alias_updates == []


def test_reindex_empty_staging_only_performs_schema_and_count_smoke_checks() -> None:
    from app.knowledge.store import KnowledgeStore

    class EmptyCorpusEmbeddings(FixedDimensionEmbeddings):
        def embed_query(self, query):
            raise AssertionError("an empty staging collection must not run a vector query")

    client = FakeQdrantClient()
    client.aliases["solvex_papers"] = "solvex_papers__old"
    client.collections["solvex_papers__old"] = SimpleNamespace(metadata={})
    store = KnowledgeStore(client, embedding_provider=EmptyCorpusEmbeddings())

    target = store.reindex([])

    assert client.count_calls == [target]
    assert client.queries == []


def test_reindex_cleans_a_partially_created_staging_collection() -> None:
    from app.knowledge.store import KnowledgeStore, KnowledgeStoreError

    class IndexCreationFails(FakeQdrantClient):
        def create_payload_index(self, collection_name: str, field_name: str, field_schema):
            raise RuntimeError("index creation failed")

    client = IndexCreationFails()
    client.aliases["solvex_papers"] = "solvex_papers__old"
    client.collections["solvex_papers__old"] = SimpleNamespace(metadata={})
    store = KnowledgeStore(client)

    with pytest.raises(KnowledgeStoreError, match="create payload index"):
        store.reindex([])

    assert client.aliases["solvex_papers"] == "solvex_papers__old"
    assert len(client.deleted_collections) == 1


def test_reindex_keeps_new_alias_when_old_collection_cleanup_fails() -> None:
    from app.knowledge.store import KnowledgeStore

    class OldCleanupFails(FakeQdrantClient):
        def delete_collection(self, collection_name: str):
            if collection_name == "solvex_papers__old":
                raise RuntimeError("old cleanup unavailable")
            return super().delete_collection(collection_name)

    client = OldCleanupFails()
    client.aliases["solvex_papers"] = "solvex_papers__old"
    client.collections["solvex_papers__old"] = SimpleNamespace(metadata={})
    store = KnowledgeStore(client)

    target = store.reindex([])

    assert client.aliases["solvex_papers"] == target
    assert client.deleted_collections == []


def test_reindex_treats_alias_timeout_as_success_when_alias_now_points_to_staging() -> None:
    from app.knowledge.store import KnowledgeStore

    class CommitThenTimeout(FakeQdrantClient):
        def update_collection_aliases(self, change_aliases_operations):
            super().update_collection_aliases(change_aliases_operations)
            raise TimeoutError("request timed out after commit")

    client = CommitThenTimeout()
    client.aliases["solvex_papers"] = "solvex_papers__old"
    client.collections["solvex_papers__old"] = SimpleNamespace(metadata={})
    store = KnowledgeStore(client)

    target = store.reindex([])

    assert client.aliases["solvex_papers"] == target
    assert client.deleted_collections == ["solvex_papers__old"]


def test_reindex_cleans_staging_when_alias_timeout_left_the_old_target_in_place() -> None:
    from app.knowledge.store import KnowledgeStore, KnowledgeStoreError

    class TimeoutBeforeCommit(FakeQdrantClient):
        def update_collection_aliases(self, change_aliases_operations):
            raise TimeoutError("request timed out before commit")

    client = TimeoutBeforeCommit()
    client.aliases["solvex_papers"] = "solvex_papers__old"
    client.collections["solvex_papers__old"] = SimpleNamespace(metadata={})
    store = KnowledgeStore(client)

    with pytest.raises(KnowledgeStoreError, match="switch collection alias"):
        store.reindex([])

    assert client.aliases["solvex_papers"] == "solvex_papers__old"
    assert len(client.deleted_collections) == 1
    assert client.deleted_collections[0].startswith(f"{store.physical_collection}__staging_")


def test_reindex_preserves_staging_when_alias_state_cannot_be_read_after_timeout() -> None:
    from app.knowledge.store import AmbiguousReindexError, KnowledgeStore

    class TimeoutAndUnreadableAliases(FakeQdrantClient):
        def __init__(self) -> None:
            super().__init__()
            self.alias_reads = 0

        def get_aliases(self):
            self.alias_reads += 1
            if self.alias_reads > 1:
                raise ConnectionError("alias state unavailable")
            return super().get_aliases()

        def update_collection_aliases(self, change_aliases_operations):
            raise TimeoutError("request timed out")

    client = TimeoutAndUnreadableAliases()
    client.aliases["solvex_papers"] = "solvex_papers__old"
    client.collections["solvex_papers__old"] = SimpleNamespace(metadata={})
    store = KnowledgeStore(client)

    with pytest.raises(AmbiguousReindexError, match="could not determine alias state"):
        store.reindex([])

    assert client.aliases["solvex_papers"] == "solvex_papers__old"
    assert client.deleted_collections == []


def test_qdrant_client_failure_is_exposed_as_a_knowledge_store_error() -> None:
    from app.knowledge.store import KnowledgeStore, KnowledgeStoreError

    class BrokenClient:
        def get_aliases(self):
            raise ConnectionError("Qdrant is unavailable")

    with pytest.raises(KnowledgeStoreError, match="read collection aliases") as error:
        KnowledgeStore(BrokenClient()).ensure_collection()

    assert isinstance(error.value.__cause__, ConnectionError)
