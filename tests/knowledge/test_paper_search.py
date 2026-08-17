import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import config
from app.knowledge.store import KnowledgeStoreError, SearchHit
from app.knowledge.trace import current_retrieval_trace_path, retrieval_trace_path
from app.tool.paper_search import PaperSearch


if "boto3" not in sys.modules:
    try:
        __import__("boto3")
    except ModuleNotFoundError:
        sys.modules["boto3"] = SimpleNamespace(client=lambda *_args, **_kwargs: None)

if "arxiv" not in sys.modules:
    try:
        __import__("arxiv")
    except ModuleNotFoundError:
        sys.modules["arxiv"] = SimpleNamespace()


def _hit(*, score: float = 0.75) -> SearchHit:
    return SearchHit(
        paper_id="mcm-2025-c-outstanding-01",
        title="An excellent paper",
        competition="MCM",
        year=2025,
        problem="C",
        award="Outstanding Winner",
        language="en",
        methods=("optimization",),
        section_path=("Model",),
        source_file="main.tex",
        chunk_id="chunk-1",
        score=score,
        raw_latex="\\section{Model}",
    )


class _Service:
    def __init__(self, *, output: str = "formatted", error: Exception | None = None):
        self.output = output
        self.error = error
        self.search_calls = []

    def search(self, query, **filters):
        self.search_calls.append((query, filters))
        if self.error:
            raise self.error
        return [_hit()]

    def format_search_hits(self, hits):
        assert list(hits)
        return self.output


@pytest.mark.asyncio
async def test_paper_search_runs_sync_service_in_worker_and_forwards_filters(monkeypatch):
    service = _Service()
    tool = PaperSearch(default_top_k=7, service_factory=lambda _: service)
    called = False

    async def fake_to_thread(function, *args, **kwargs):
        nonlocal called
        called = True
        return function(*args, **kwargs)

    monkeypatch.setattr("app.tool.paper_search.asyncio.to_thread", fake_to_thread)

    result = await tool.execute(
        "network optimization",
        competition="MCM",
        year=2025,
        methods=["optimization"],
    )

    assert called is True
    assert result.error is None
    assert result.output == "formatted"
    schema = tool.to_param()["function"]["parameters"]
    assert schema["required"] == ["query"]
    assert schema["properties"]["top_k"]["default"] == 7
    assert set(schema["properties"]) >= {
        "query", "competition", "year", "problem", "award", "language", "methods"
    }
    assert service.search_calls == [
        (
            "network optimization",
            {
                "top_k": 7,
                "competition": "MCM",
                "year": 2025,
                "problem": None,
                "award": None,
                "language": None,
                "methods": ["optimization"],
            },
        )
    ]


@pytest.mark.asyncio
async def test_paper_search_rejects_top_k_outside_public_limit():
    tool = PaperSearch(service_factory=lambda _: _Service())

    result = await tool.execute("anything", top_k=13)

    assert result.error == "top_k must be between 1 and 12"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "methods",
    ["integer_programming", ["optimization", 1], [""], ["  "]],
)
async def test_paper_search_rejects_invalid_methods_without_calling_store(methods):
    service = _Service()
    tool = PaperSearch(service_factory=lambda _: service)

    result = await tool.execute("anything", methods=methods)

    assert result.error == "methods must be a list of non-empty strings"
    assert service.search_calls == []


@pytest.mark.asyncio
async def test_paper_search_rejects_an_empty_methods_list_without_calling_store():
    service = _Service()
    tool = PaperSearch(service_factory=lambda _: service)

    result = await tool.execute("anything", methods=[])

    assert result.error == "methods must be a list of non-empty strings"
    assert service.search_calls == []


def test_paper_search_rejects_an_invalid_default_top_k_at_construction():
    with pytest.raises(ValueError, match="default_top_k"):
        PaperSearch(default_top_k=13)


@pytest.mark.asyncio
async def test_paper_search_enforces_total_output_limit():
    tool = PaperSearch(service_factory=lambda _: _Service(output="x" * 12_001))

    result = await tool.execute("anything")

    assert result.error is None
    assert len(result.output) == 12_000


@pytest.mark.asyncio
async def test_paper_search_constructs_its_service_only_on_first_execution():
    factory_calls = 0
    service = _Service()

    def factory(_):
        nonlocal factory_calls
        factory_calls += 1
        return service

    tool = PaperSearch(service_factory=factory)
    assert factory_calls == 0

    await tool.execute("first")
    await tool.execute("second")

    assert factory_calls == 1


@pytest.mark.asyncio
async def test_paper_search_writes_success_trace_without_latex(tmp_path: Path):
    trace_path = tmp_path / "01_modeling" / "retrieval_trace.jsonl"
    tool = PaperSearch(service_factory=lambda _: _Service())

    with retrieval_trace_path(trace_path):
        result = await tool.execute("network optimization", language="en")

    assert result.error is None
    records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["query"] == "network optimization"
    assert records[0]["filters"] == {"language": "en"}
    assert records[0]["top_k"] == 6
    assert records[0]["hit_count"] == 1
    assert records[0]["hits"] == [
        {
            "paper_id": "mcm-2025-c-outstanding-01",
            "chunk_id": "chunk-1",
            "score": 0.75,
        }
    ]
    assert "raw_latex" not in trace_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_paper_search_returns_error_and_writes_warning_trace(tmp_path: Path):
    trace_path = tmp_path / "01_modeling" / "retrieval_trace.jsonl"
    tool = PaperSearch(
        service_factory=lambda _: _Service(error=KnowledgeStoreError("Qdrant offline"))
    )

    with retrieval_trace_path(trace_path):
        result = await tool.execute("network optimization")

    assert result.output is None
    assert result.error == "Paper knowledge base is unavailable: Qdrant offline"
    record = json.loads(trace_path.read_text(encoding="utf-8"))
    assert record["warning"] is True
    assert record["error"] == "Qdrant offline"
    assert "hits" not in record


@pytest.mark.asyncio
async def test_paper_search_does_not_write_trace_without_a_session_context(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tool = PaperSearch(service_factory=lambda _: _Service())

    result = await tool.execute("anything")

    assert result.error is None
    assert current_retrieval_trace_path() is None
    assert not list(tmp_path.rglob("retrieval_trace.jsonl"))


def test_agent_tool_lists_follow_knowledge_flag_without_sharing_collections(monkeypatch):
    from app.agent.modeling import ModelingAgent
    from app.agent.writing import WritingAgent
    from app.llm import LLM

    fake_llm = object.__new__(LLM)

    monkeypatch.setattr(config.knowledge, "enabled", False)
    disabled_modeling = ModelingAgent(llm=fake_llm)
    disabled_writing = WritingAgent(llm=fake_llm)
    assert "paper_search" not in disabled_modeling.available_tools.tool_map
    assert "paper_search" not in disabled_writing.available_tools.tool_map

    monkeypatch.setattr(config.knowledge, "enabled", True)
    enabled_modeling = ModelingAgent(llm=fake_llm)
    enabled_writing = WritingAgent(llm=fake_llm)
    another_enabled_modeling = ModelingAgent(llm=fake_llm)
    assert "paper_search" in enabled_modeling.available_tools.tool_map
    assert "paper_search" in enabled_writing.available_tools.tool_map
    assert enabled_modeling.available_tools is not another_enabled_modeling.available_tools


def test_agent_prompts_describe_safe_local_paper_use():
    from app.prompt.modeling import SYSTEM_PROMPT as modeling_prompt
    from app.prompt.writing import SYSTEM_PROMPT as writing_prompt

    assert "paper_search" in modeling_prompt
    assert "before ArXiv/Tavily" in modeling_prompt
    assert "paper_search" in writing_prompt
    assert "only from this run" in writing_prompt
    assert "Do not copy passages" in writing_prompt
    assert "not automatically added to the bibliography" in writing_prompt


@pytest.mark.asyncio
async def test_flow_binds_trace_context_and_resets_it_after_error(tmp_path: Path, monkeypatch):
    from app.flow.solvex_flow import SolveXFlow
    from app.knowledge.trace import write_retrieval_trace

    flow = SolveXFlow(agents={})

    async def fake_execute(*args, **kwargs):
        assert current_retrieval_trace_path() == (
            tmp_path / "01_modeling" / "retrieval_trace.jsonl"
        )
        write_retrieval_trace(
            query="test query",
            filters={},
            top_k=6,
            hits=[_hit()],
        )
        raise RuntimeError("expected")

    monkeypatch.setattr(flow, "_execute", fake_execute)

    with pytest.raises(RuntimeError, match="expected"):
        await flow.execute("problem", workspace=str(tmp_path))

    trace_path = tmp_path / "01_modeling" / "retrieval_trace.jsonl"
    assert trace_path.exists()
    assert current_retrieval_trace_path() is None
