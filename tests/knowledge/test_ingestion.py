from pathlib import Path
from types import SimpleNamespace
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep


def test_load_paper_document_returns_validated_manifest_and_structured_chunks(tmp_path: Path) -> None:
    from app.knowledge.ingestion import load_paper_document

    root = tmp_path / "paper"
    root.mkdir()
    (root / "paper.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "paper_id: end-to-end-test",
                "title: End to End Test",
                "competition: MCM",
                "year: 2025",
                "problem: C",
                "award: Finalist",
                "language: en",
                "methods: [regression]",
                "main_tex: main.tex",
            ]
        ),
        encoding="utf-8",
    )
    (root / "main.tex").write_text(
        "\\begin{abstract}\nSummary of the model.\n\\end{abstract}\n\\input{method}",
        encoding="utf-8",
    )
    (root / "method.tex").write_text(
        "\\section{Method}\nWe fit a regression model.", encoding="utf-8"
    )

    document = load_paper_document(root, token_counter=lambda text: len(text.split()))

    assert document.manifest.methods == ["regression"]
    assert [chunk.section_path for chunk in document.chunks] == [("Abstract",), ("Method",)]
    assert document.chunks[1].source_file == "method.tex"


def test_e5_token_counter_is_lazy_and_uses_the_public_tokenizers_api(monkeypatch) -> None:
    import app.knowledge.ingestion as ingestion

    load_calls: list[str] = []

    class FakeTokenizer:
        @classmethod
        def from_pretrained(cls, model_name: str):
            load_calls.append(model_name)
            return cls()

        def encode(self, text: str):
            return SimpleNamespace(ids=[1, 2, 3])

    monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(Tokenizer=FakeTokenizer))

    counter = ingestion.E5TokenCounter()

    assert ingestion.E5_TOKENIZER_MODEL == "intfloat/multilingual-e5-large"
    assert load_calls == []
    assert counter("a mathematical model") == 3
    assert load_calls == ["intfloat/multilingual-e5-large"]
    assert counter("second call") == 3
    assert load_calls == ["intfloat/multilingual-e5-large"]


def test_load_paper_document_uses_fixed_production_chunk_limits(tmp_path: Path, monkeypatch) -> None:
    import app.knowledge.ingestion as ingestion

    root = tmp_path / "paper"
    root.mkdir()
    (root / "paper.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "paper_id: limits-test",
                "title: Limits Test",
                "competition: MCM",
                "year: 2025",
                "problem: C",
                "award: Finalist",
                "language: en",
                "main_tex: main.tex",
            ]
        ),
        encoding="utf-8",
    )
    (root / "main.tex").write_text("\\section{Method}\nBody", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_build_chunks(lines, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(ingestion, "build_chunks", fake_build_chunks)

    document = ingestion.load_paper_document(root, token_counter=lambda text: 1)

    assert document.chunks == ()
    assert ingestion.MAX_CHUNK_TOKENS == 450
    assert ingestion.CHUNK_OVERLAP_TOKENS == 60
    assert captured["max_tokens"] == 450
    assert captured["overlap_tokens"] == 60


def test_load_paper_document_constructs_the_default_counter_for_a_configured_dense_model(
    tmp_path: Path, monkeypatch
) -> None:
    import app.knowledge.ingestion as ingestion

    root = tmp_path / "paper"
    root.mkdir()
    (root / "paper.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "paper_id: model-test",
                "title: Model Test",
                "competition: MCM",
                "year: 2025",
                "problem: C",
                "award: Finalist",
                "language: en",
                "main_tex: main.tex",
            ]
        ),
        encoding="utf-8",
    )
    (root / "main.tex").write_text("\\section{Method}\nBody", encoding="utf-8")
    constructed: list[str] = []

    class FakeCounter:
        def __init__(self, model_name: str) -> None:
            constructed.append(model_name)

        def __call__(self, text: str) -> int:
            return 1

    monkeypatch.setattr(ingestion, "E5TokenCounter", FakeCounter)

    ingestion.load_paper_document(root, dense_model="custom/dense-model")

    assert constructed == ["custom/dense-model"]


def test_e5_token_counter_serializes_encoding_and_caches_the_configured_model(monkeypatch) -> None:
    import app.knowledge.ingestion as ingestion

    state = {"loads": [], "active": 0, "maximum_active": 0}
    state_lock = Lock()

    class FakeTokenizer:
        @classmethod
        def from_pretrained(cls, model_name: str):
            state["loads"].append(model_name)
            return cls()

        def encode(self, text: str):
            with state_lock:
                state["active"] += 1
                state["maximum_active"] = max(state["maximum_active"], state["active"])
            try:
                sleep(0.01)
                return SimpleNamespace(ids=[1, 2])
            finally:
                with state_lock:
                    state["active"] -= 1

    monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(Tokenizer=FakeTokenizer))
    counter = ingestion.E5TokenCounter("custom/dense-model")

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert list(executor.map(counter, ["paper"] * 16)) == [2] * 16

    assert state["loads"] == ["custom/dense-model"]
    assert state["maximum_active"] == 1
