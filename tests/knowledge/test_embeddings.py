from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import sleep

import pytest


def test_embedding_provider_passes_one_lazy_persistent_default_cache_directory_to_both_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.knowledge.embeddings import KnowledgeEmbeddingProvider

    monkeypatch.delenv("FASTEMBED_CACHE_PATH", raising=False)
    created: list[tuple[str, str, str]] = []

    class FakeDense:
        def embed(self, texts):
            return [[1.0] for _ in texts]

    class FakeSparse:
        def embed(self, texts):
            return [type("Sparse", (), {"indices": [1], "values": [1.0]})() for _ in texts]

    def dense_factory(model_name: str, *, cache_dir: str):
        created.append(("dense", model_name, cache_dir))
        return FakeDense()

    def sparse_factory(model_name: str, *, cache_dir: str):
        created.append(("sparse", model_name, cache_dir))
        return FakeSparse()

    provider = KnowledgeEmbeddingProvider(
        dense_model="dense-test",
        sparse_model="sparse-test",
        dense_factory=dense_factory,
        sparse_factory=sparse_factory,
    )

    assert created == []
    provider.embed_documents(["paper"])

    expected = str(Path.home() / ".cache" / "solvex" / "fastembed")
    assert created == [
        ("dense", "dense-test", expected),
        ("sparse", "sparse-test", expected),
    ]


def test_embedding_provider_honors_fastembed_cache_path_without_creating_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.knowledge.embeddings import KnowledgeEmbeddingProvider

    cache_dir = tmp_path / "offline-fastembed-cache"
    created: list[tuple[str, str]] = []

    class FakeDense:
        def embed(self, texts):
            return [[1.0] for _ in texts]

    class FakeSparse:
        def query_embed(self, texts):
            return [type("Sparse", (), {"indices": [1], "values": [1.0]})() for _ in texts]

    def dense_factory(model_name: str, *, cache_dir: str):
        created.append(("dense", cache_dir))
        return FakeDense()

    def sparse_factory(model_name: str, *, cache_dir: str):
        created.append(("sparse", cache_dir))
        return FakeSparse()

    provider = KnowledgeEmbeddingProvider(
        dense_factory=dense_factory,
        sparse_factory=sparse_factory,
    )

    assert not cache_dir.exists()
    assert created == []
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(cache_dir))
    provider.embed_query("paper")

    assert created == [("dense", str(cache_dir)), ("sparse", str(cache_dir))]


def test_embedding_provider_lazily_loads_models_and_normalizes_vectors() -> None:
    from app.knowledge.embeddings import KnowledgeEmbeddingProvider

    created: list[tuple[str, str]] = []

    class FakeDense:
        def embed(self, texts):
            assert list(texts) == ["passage: mathematical model"]
            return [[1, 2.5]]

    class FakeSparse:
        def embed(self, texts):
            assert list(texts) == ["mathematical model"]
            return [type("Sparse", (), {"indices": [4, 9], "values": [0.3, 2]})()]

    def dense_factory(model_name: str, *, cache_dir: str):
        created.append(("dense", model_name))
        return FakeDense()

    def sparse_factory(model_name: str, *, cache_dir: str):
        created.append(("sparse", model_name))
        return FakeSparse()

    provider = KnowledgeEmbeddingProvider(
        dense_model="dense-test",
        sparse_model="sparse-test",
        dense_factory=dense_factory,
        sparse_factory=sparse_factory,
    )

    assert created == []
    embeddings = provider.embed_documents(["mathematical model"])

    assert created == [("dense", "dense-test"), ("sparse", "sparse-test")]
    assert embeddings.dense == [[1.0, 2.5]]
    assert embeddings.sparse[0].indices == [4, 9]
    assert embeddings.sparse[0].values == [0.3, 2.0]


def test_embedding_provider_uses_query_prefix_for_hybrid_query() -> None:
    from app.knowledge.embeddings import KnowledgeEmbeddingProvider

    class FakeDense:
        def embed(self, texts):
            assert list(texts) == ["query: what optimization model applies?"]
            return [[0.5, 1]]

    class FakeSparse:
        def query_embed(self, texts):
            assert list(texts) == ["what optimization model applies?"]
            return [type("Sparse", (), {"indices": [8], "values": [1]})()]

    provider = KnowledgeEmbeddingProvider(
        dense_factory=lambda _, *, cache_dir: FakeDense(),
        sparse_factory=lambda _, *, cache_dir: FakeSparse(),
    )

    embedding = provider.embed_query("what optimization model applies?")

    assert embedding.dense == [0.5, 1.0]
    assert embedding.sparse.indices == [8]


def test_embedding_provider_serializes_model_loading_and_embedding_calls() -> None:
    from app.knowledge.embeddings import KnowledgeEmbeddingProvider

    state = {"created": 0, "active": 0, "maximum_active": 0}
    state_lock = Lock()

    class FakeDense:
        def embed(self, texts):
            with state_lock:
                state["active"] += 1
                state["maximum_active"] = max(state["maximum_active"], state["active"])
            try:
                sleep(0.01)
                return [[1.0] for _ in texts]
            finally:
                with state_lock:
                    state["active"] -= 1

    class FakeSparse:
        def embed(self, texts):
            return [type("Sparse", (), {"indices": [1], "values": [1.0]})() for _ in texts]

    def dense_factory(model_name: str, *, cache_dir: str):
        with state_lock:
            state["created"] += 1
        return FakeDense()

    provider = KnowledgeEmbeddingProvider(
        dense_factory=dense_factory,
        sparse_factory=lambda _, *, cache_dir: FakeSparse(),
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert list(executor.map(provider.embed_documents, [["paper"]] * 16))

    assert state["created"] == 1
    assert state["maximum_active"] == 1


def test_embedding_provider_uses_e5_dense_prefixes_but_raw_augmented_bm25_documents() -> None:
    from app.knowledge.embeddings import KnowledgeEmbeddingProvider

    dense_inputs: list[list[str]] = []
    sparse_inputs: list[list[str]] = []

    class FakeDense:
        def embed(self, texts):
            dense_inputs.append(list(texts))
            return [[1.0] for _ in dense_inputs[-1]]

    class FakeSparse:
        def embed(self, texts):
            sparse_inputs.append(list(texts))
            return [type("Sparse", (), {"indices": [1], "values": [1.0]})() for _ in sparse_inputs[-1]]

    provider = KnowledgeEmbeddingProvider(
        dense_factory=lambda _, *, cache_dir: FakeDense(),
        sparse_factory=lambda _, *, cache_dir: FakeSparse(),
    )

    provider.embed_documents(["English 中文建模 test"])

    assert dense_inputs == [["passage: English 中文建模 test"]]
    assert sparse_inputs == [["English 中文建模 test 中文 文建 建模"]]


def test_embedding_provider_uses_sparse_query_embed_without_an_e5_prefix() -> None:
    from app.knowledge.embeddings import KnowledgeEmbeddingProvider

    dense_inputs: list[list[str]] = []
    sparse_inputs: list[list[str]] = []

    class FakeDense:
        def embed(self, texts):
            dense_inputs.append(list(texts))
            return [[1.0] for _ in dense_inputs[-1]]

    class FakeSparse:
        def embed(self, texts):
            raise AssertionError("BM25 queries must call query_embed")

        def query_embed(self, texts):
            sparse_inputs.append(list(texts))
            return [type("Sparse", (), {"indices": [2], "values": [1.0]})() for _ in sparse_inputs[-1]]

    provider = KnowledgeEmbeddingProvider(
        dense_factory=lambda _, *, cache_dir: FakeDense(),
        sparse_factory=lambda _, *, cache_dir: FakeSparse(),
    )

    provider.embed_query("中文建模")

    assert dense_inputs == [["query: 中文建模"]]
    assert sparse_inputs == [["中文建模 中文 文建 建模"]]


def test_sparse_cjk_augmentation_preserves_raw_text_and_adds_adjacent_bigrams() -> None:
    from app.knowledge.embeddings import augment_sparse_text

    raw = "预测中文模型，English stays intact。"

    assert augment_sparse_text(raw) == (
        "预测中文模型，English stays intact。 预测 测中 中文 文模 模型"
    )


def test_embedding_provider_wraps_model_failures_as_knowledge_ingestion_errors() -> None:
    from app.knowledge.embeddings import KnowledgeEmbeddingError, KnowledgeEmbeddingProvider
    from app.knowledge.errors import KnowledgeIngestionError

    def broken_dense_factory(model_name: str, *, cache_dir: str):
        raise RuntimeError("model cache is unavailable")

    provider = KnowledgeEmbeddingProvider(
        dense_factory=broken_dense_factory,
        sparse_factory=lambda _, *, cache_dir: object(),
    )

    with pytest.raises(KnowledgeEmbeddingError, match="load") as error:
        provider.embed_documents(["paper"])

    assert isinstance(error.value, KnowledgeIngestionError)
    assert isinstance(error.value.__cause__, RuntimeError)


def test_embedding_provider_reads_dense_dimension_from_public_model_metadata_without_loading_weights() -> None:
    from app.knowledge.embeddings import KnowledgeEmbeddingProvider

    created: list[str] = []
    provider = KnowledgeEmbeddingProvider(
        dense_factory=lambda model_name, *, cache_dir: created.append(model_name),
        sparse_factory=lambda _, *, cache_dir: object(),
    )

    assert provider.dense_dimension() == 1024
    assert created == []


def test_embedding_provider_rejects_dense_models_without_a_declared_dimension() -> None:
    from app.knowledge.embeddings import KnowledgeEmbeddingError, KnowledgeEmbeddingProvider

    provider = KnowledgeEmbeddingProvider(dense_model="missing/model")

    with pytest.raises(KnowledgeEmbeddingError, match="does not declare a dense vector dimension"):
        provider.dense_dimension()


def test_embedding_provider_processes_dense_and_sparse_documents_in_batches_of_32() -> None:
    from app.knowledge.embeddings import KnowledgeEmbeddingProvider

    dense_batches: list[list[str]] = []
    sparse_batches: list[list[str]] = []

    class FakeDense:
        def embed(self, texts):
            batch = list(texts)
            dense_batches.append(batch)
            return [[1.0] for _ in batch]

    class FakeSparse:
        def embed(self, texts):
            batch = list(texts)
            sparse_batches.append(batch)
            return [type("Sparse", (), {"indices": [1], "values": [1.0]})() for _ in batch]

    documents = [f"document {index}" for index in range(65)]
    provider = KnowledgeEmbeddingProvider(
        dense_factory=lambda _, *, cache_dir: FakeDense(),
        sparse_factory=lambda _, *, cache_dir: FakeSparse(),
    )

    embeddings = provider.embed_documents(documents)

    assert [len(batch) for batch in dense_batches] == [32, 32, 1]
    assert [len(batch) for batch in sparse_batches] == [32, 32, 1]
    assert dense_batches[0][0] == "passage: document 0"
    assert sparse_batches[0][0] == "document 0"
    assert len(embeddings.dense) == len(embeddings.sparse) == 65
