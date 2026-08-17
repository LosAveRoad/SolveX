from __future__ import annotations

from app.knowledge.store import SearchHit


def test_search_service_caps_total_raw_latex_output_at_12000_characters() -> None:
    from app.knowledge.service import KnowledgeSearchService

    def hit(chunk_id: str, raw_latex: str) -> SearchHit:
        return SearchHit(
            paper_id="paper-a",
            title="Paper A",
            competition="MCM",
            year=2025,
            problem="A",
            award="Finalist",
            language="en",
            methods=("optimization",),
            section_path=("Method",),
            source_file="main.tex",
            chunk_id=chunk_id,
            score=1.0,
            raw_latex=raw_latex,
        )

    class FakeStore:
        def search(self, *args, **kwargs):
            return [hit("first", "a" * 7000), hit("second", "b" * 7000)]

    results = KnowledgeSearchService(FakeStore()).search("model")

    assert [result.chunk_id for result in results] == ["first", "second"]
    assert sum(len(result.raw_latex) for result in results) == 12000
    assert results[1].raw_latex == "b" * 5000


def test_format_search_hits_caps_the_final_tool_text_with_long_metadata_and_latex() -> None:
    from app.knowledge.service import KnowledgeSearchService

    hit = SearchHit(
        paper_id="paper-" + "p" * 2_000,
        title="title-" + "t" * 4_000,
        competition="MCM",
        year=2025,
        problem="C",
        award="Outstanding Winner",
        language="en",
        methods=("optimization",),
        section_path=("Methods " + "s" * 2_000,),
        source_file="parts/" + "f" * 2_000 + ".tex",
        chunk_id="chunk-" + "c" * 2_000,
        score=0.987654,
        raw_latex="\\begin{equation}" + "x" * 16_000,
    )

    formatted = KnowledgeSearchService(object()).format_search_hits([hit])

    assert len(formatted) <= 12_000
    for label in ("Paper ID:", "Title:", "Section:", "Source file:", "Chunk ID:", "Score:", "Raw LaTeX:"):
        assert label in formatted
    assert "\\begin{equation}" in formatted
