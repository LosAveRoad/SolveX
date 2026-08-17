"""Opt-in integration coverage for a local Qdrant paper index.

The expensive embedding model and Docker service are deliberately only exercised
when ``RUN_QDRANT_INTEGRATION=1`` is explicitly set.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest


QDRANT_URL = "http://127.0.0.1:6333"
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "synthetic_allocation_paper"
TARGET_SECTION = ("Integer Programming Formulation",)


def test_synthetic_fixture_is_a_complete_paper_with_an_included_method_section() -> None:
    """Keep the opt-in test corpus valid without downloading embedding weights."""

    from app.knowledge.ingestion import load_paper_document

    assert (FIXTURE_ROOT / "paper.yaml").is_file()
    assert (FIXTURE_ROOT / "main.tex").is_file()
    assert (FIXTURE_ROOT / "sections" / "method.tex").is_file()

    document = load_paper_document(
        FIXTURE_ROOT,
        token_counter=lambda text: len(text.split()),
    )

    assert document.manifest.paper_id == "integration-synthetic-allocation-001"
    assert document.manifest.methods == ["integer-programming", "resource-allocation"]
    assert len(document.chunks) > 5
    assert any(
        chunk.section_path == TARGET_SECTION and chunk.source_file == "sections/method.tex"
        for chunk in document.chunks
    )


@pytest.mark.skipif(
    os.environ.get("RUN_QDRANT_INTEGRATION") != "1",
    reason="set RUN_QDRANT_INTEGRATION=1 to run the real local Qdrant integration test",
)
def test_real_qdrant_indexes_the_fixture_idempotently_and_retrieves_the_method_section() -> None:
    """Exercise the configured loopback Qdrant service and real default FastEmbed models."""

    from qdrant_client import QdrantClient

    from app.knowledge.ingestion import load_paper_document
    from app.knowledge.store import KnowledgeStore

    client = QdrantClient(url=QDRANT_URL, timeout=20)
    collection_name = f"solvex_integration_{uuid4().hex}"
    store: KnowledgeStore | None = None

    try:
        _skip_unhealthy_qdrant(client)
        store = KnowledgeStore(client, collection_name=collection_name)
        document = load_paper_document(FIXTURE_ROOT)
        first_count = store.index_document(document)
        physical_collection = store.physical_collection
        first_total = client.count(physical_collection, exact=True).count

        second_count = store.index_document(document)
        second_total = client.count(physical_collection, exact=True).count

        assert first_count == second_count == first_total == second_total
        assert first_total > 0

        semantic_hits = store.search(
            "how to allocate patrol resources with an optimization model", top_k=5
        )
        method_hits = store.search(
            "integer programming",
            top_k=5,
            methods=["integer-programming"],
        )

        assert any(hit.section_path == TARGET_SECTION for hit in semantic_hits)
        assert any(hit.section_path == TARGET_SECTION for hit in method_hits)
    finally:
        if store is not None:
            _delete_test_collection(client, collection_name, store.physical_collection)
        client.close()


def _skip_unhealthy_qdrant(client: object) -> None:
    """Skip an opt-in test when Docker is not serving the required local endpoint."""

    try:
        client.get_collections()  # type: ignore[attr-defined]
    except Exception as exc:
        pytest.skip(f"Qdrant at {QDRANT_URL} is unavailable: {exc}")


def _delete_test_collection(client: object, alias_name: str, collection_name: str) -> None:
    """Remove only this test's unique alias and physical collection."""

    from qdrant_client import models

    if not client.collection_exists(collection_name):  # type: ignore[attr-defined]
        return
    aliases = client.get_aliases().aliases  # type: ignore[attr-defined]
    if any(alias.alias_name == alias_name for alias in aliases):
        client.update_collection_aliases(  # type: ignore[attr-defined]
            [
                models.DeleteAliasOperation(
                    delete_alias=models.DeleteAlias(alias_name=alias_name)
                )
            ]
        )
    client.delete_collection(collection_name)  # type: ignore[attr-defined]
