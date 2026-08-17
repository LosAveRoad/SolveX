from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class _Document:
    paper_id: str
    source: Path

    @property
    def manifest(self):
        return type("Manifest", (), {"paper_id": self.paper_id})()


class _Store:
    def __init__(self) -> None:
        self.indexed: list[_Document] = []
        self.deleted: list[str] = []
        self.reindexed: list[_Document] | None = None
        self.papers = []

    def index_document(self, document: _Document) -> int:
        self.indexed.append(document)
        return 3

    def delete_paper(self, paper_id: str) -> int:
        self.deleted.append(paper_id)
        return 2

    def list_papers(self):
        return self.papers

    def reindex(self, documents):
        self.reindexed = list(documents)
        return "solvex_papers__staging"


class _Service:
    def __init__(self, store: _Store) -> None:
        self.store = store
        self.search_calls = []
        self.search_results = ["hit"]
        self.formatted = "formatted result"

    def search(self, query: str, **filters):
        self.search_calls.append((query, filters))
        return self.search_results

    def format_search_hits(self, hits):
        assert list(hits) == self.search_results
        return self.formatted


@dataclass(frozen=True)
class _Runtime:
    service: _Service
    dense_model: str = "test/dense"
    default_top_k: int = 6


def _write_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "paper.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    return root


def _runtime(monkeypatch, *, default_top_k: int = 6):
    import knowledge

    store = _Store()
    service = _Service(store)
    runtime = _Runtime(service=service, default_top_k=default_top_k)
    monkeypatch.setattr(knowledge, "_build_runtime", lambda: runtime)
    return runtime


def test_help_does_not_create_knowledge_runtime(monkeypatch, capsys) -> None:
    import knowledge

    monkeypatch.setattr(
        knowledge,
        "_build_runtime",
        lambda: pytest.fail("--help must not load configuration, models, or Qdrant"),
    )

    with pytest.raises(SystemExit) as result:
        knowledge.main(["--help"])

    assert result.value.code == 0
    assert "ingest" in capsys.readouterr().out


def test_ingest_indexes_one_source_and_reports_its_paper_id(tmp_path: Path, monkeypatch, capsys) -> None:
    import knowledge

    runtime = _runtime(monkeypatch)
    source = _write_project(tmp_path / "paper")
    loaded = []

    def load(path, *, dense_model):
        loaded.append((Path(path), dense_model))
        return _Document("paper-one", Path(path))

    monkeypatch.setattr(knowledge, "_load_document", load)

    assert knowledge.main(["ingest", str(source)]) == 0

    assert loaded == [(source, "test/dense")]
    assert [document.paper_id for document in runtime.service.store.indexed] == ["paper-one"]
    assert "paper-one: 3 chunks" in capsys.readouterr().out


def test_recursive_ingest_continues_after_one_bad_source(tmp_path: Path, monkeypatch, capsys) -> None:
    import knowledge

    runtime = _runtime(monkeypatch)
    root = _write_project(tmp_path / "corpus")
    nested = _write_project(root / "nested")
    bad_archive = root / "bad.zip"
    bad_archive.write_bytes(b"not parsed by the loader")

    def load(path, *, dense_model):
        if Path(path) == bad_archive:
            raise ValueError("invalid paper archive")
        return _Document(f"paper-{Path(path).name}", Path(path))

    monkeypatch.setattr(knowledge, "_load_document", load)

    assert knowledge.main(["ingest", str(root), "--recursive"]) == 1

    assert [document.paper_id for document in runtime.service.store.indexed] == [
        "paper-corpus",
        "paper-nested",
    ]
    captured = capsys.readouterr()
    assert "failed to ingest" in captured.err
    assert "2 imported, 1 failed" in captured.out


def test_search_forwards_filters_uses_configured_default_and_bounds_output(monkeypatch, capsys) -> None:
    import knowledge

    runtime = _runtime(monkeypatch, default_top_k=7)
    runtime.service.formatted = "x" * 12_001

    assert knowledge.main(
        [
            "search",
            "network optimization",
            "--competition",
            "MCM",
            "--year",
            "2025",
            "--problem",
            "C",
            "--award",
            "Outstanding Winner",
            "--language",
            "en",
            "--methods",
            "optimization",
            "regression",
        ]
    ) == 0

    assert runtime.service.search_calls == [
        (
            "network optimization",
            {
                "top_k": 7,
                "competition": "MCM",
                "year": 2025,
                "problem": "C",
                "award": "Outstanding Winner",
                "language": "en",
                "methods": ["optimization", "regression"],
            },
        )
    ]
    assert len(capsys.readouterr().out.strip()) == 12_000


def test_search_rejects_top_k_outside_public_limit_without_runtime(monkeypatch, capsys) -> None:
    import knowledge

    monkeypatch.setattr(
        knowledge,
        "_build_runtime",
        lambda: pytest.fail("invalid input must not load the knowledge runtime"),
    )

    assert knowledge.main(["search", "anything", "--top-k", "13"]) == 2

    assert "top-k must be between 1 and 12" in capsys.readouterr().err


def test_list_prints_indexed_paper_metadata(monkeypatch, capsys) -> None:
    import knowledge

    runtime = _runtime(monkeypatch)
    runtime.service.store.papers = [
        type(
            "Summary",
            (),
            {
                "paper_id": "mcm-2025-c-outstanding-01",
                "title": "Example Title",
                "competition": "MCM",
                "year": 2025,
                "problem": "C",
                "award": "Outstanding Winner",
                "language": "en",
                "methods": ("optimization", "regression"),
                "chunk_count": 6,
            },
        )()
    ]

    assert knowledge.main(["list"]) == 0

    output = capsys.readouterr().out
    assert "mcm-2025-c-outstanding-01" in output
    assert "optimization, regression" in output
    assert "6 chunks" in output


def test_delete_requires_yes_before_creating_runtime(monkeypatch, capsys) -> None:
    import knowledge

    monkeypatch.setattr(
        knowledge,
        "_build_runtime",
        lambda: pytest.fail("confirmation refusal must not contact Qdrant"),
    )

    assert knowledge.main(["delete", "paper-one"]) == 2

    assert "--yes" in capsys.readouterr().err


def test_delete_with_yes_removes_the_whole_paper(monkeypatch, capsys) -> None:
    import knowledge

    runtime = _runtime(monkeypatch)

    assert knowledge.main(["delete", "paper-one", "--yes"]) == 0

    assert runtime.service.store.deleted == ["paper-one"]
    assert "deleted 2 chunks for paper-one" in capsys.readouterr().out


def test_reindex_does_not_switch_alias_when_any_source_fails_to_load(tmp_path: Path, monkeypatch, capsys) -> None:
    import knowledge

    runtime = _runtime(monkeypatch)
    root = _write_project(tmp_path / "corpus")
    bad = _write_project(root / "bad")

    def load(path, *, dense_model):
        if Path(path) == bad:
            raise ValueError("invalid paper")
        return _Document("good", Path(path))

    monkeypatch.setattr(knowledge, "_load_document", load)

    assert knowledge.main(["reindex", str(root), "--yes"]) == 1

    assert runtime.service.store.reindexed is None
    assert "reindex aborted" in capsys.readouterr().err


def test_reindex_requires_yes_and_rejects_an_empty_corpus(tmp_path: Path, monkeypatch, capsys) -> None:
    import knowledge

    root = tmp_path / "empty"
    root.mkdir()
    monkeypatch.setattr(
        knowledge,
        "_build_runtime",
        lambda: pytest.fail("empty corpus must not create a knowledge runtime"),
    )

    assert knowledge.main(["reindex", str(root)]) == 2
    assert knowledge.main(["reindex", str(root), "--yes"]) == 1

    captured = capsys.readouterr()
    assert "--yes" in captured.err
    assert "no valid paper sources" in captured.err


def test_reindex_loads_every_source_before_the_single_alias_swap(tmp_path: Path, monkeypatch, capsys) -> None:
    import knowledge

    runtime = _runtime(monkeypatch)
    root = _write_project(tmp_path / "corpus")
    nested = _write_project(root / "nested")
    loaded = []

    def load(path, *, dense_model):
        loaded.append(Path(path))
        return _Document(f"paper-{Path(path).name}", Path(path))

    monkeypatch.setattr(knowledge, "_load_document", load)

    assert knowledge.main(["reindex", str(root), "--yes"]) == 0

    assert loaded == [root, nested]
    assert [document.paper_id for document in runtime.service.store.reindexed] == [
        "paper-corpus",
        "paper-nested",
    ]
    assert "reindexed 2 papers" in capsys.readouterr().out
