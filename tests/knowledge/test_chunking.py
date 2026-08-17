from app.knowledge.latex import LatexLine
import pytest


def _word_counter(text: str) -> int:
    return len(text.split())


def test_build_chunks_preserves_raw_latex_and_normalizes_comments_and_formatting() -> None:
    from app.knowledge.chunking import build_chunks

    lines = [
        LatexLine("\\section{Method}", "main.tex", 1),
        LatexLine("We use \\textbf{weighted regression}. % internal note", "main.tex", 2),
        LatexLine("\\begin{equation}", "main.tex", 3),
        LatexLine("y = \\alpha x^2", "main.tex", 4),
        LatexLine("\\end{equation}", "main.tex", 5),
    ]

    chunks = build_chunks(lines, token_counter=_word_counter)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.section_path == ("Method",)
    assert chunk.source_file == "main.tex"
    assert (chunk.start_line, chunk.end_line) == (1, 5)
    assert "\\textbf{weighted regression}. % internal note" in chunk.raw_latex
    assert "\\begin{equation}" in chunk.raw_latex
    assert "internal note" not in chunk.normalized_text
    assert "textbf" not in chunk.normalized_text
    assert "weighted regression" in chunk.normalized_text
    assert "alpha x^2" in chunk.normalized_text


def test_build_chunks_respects_token_cap_and_overlaps_only_inside_a_section() -> None:
    from app.knowledge.chunking import build_chunks

    lines = [
        LatexLine("\\section{First}", "main.tex", 1),
        LatexLine("one two", "main.tex", 2),
        LatexLine("", "main.tex", 3),
        LatexLine("three four", "main.tex", 4),
        LatexLine("", "main.tex", 5),
        LatexLine("five six", "main.tex", 6),
        LatexLine("\\section{Second}", "main.tex", 7),
        LatexLine("seven eight", "main.tex", 8),
    ]

    chunks = build_chunks(lines, token_counter=_word_counter, max_tokens=5, overlap_tokens=2)

    assert all(_word_counter(chunk.normalized_text) <= 5 for chunk in chunks)
    first_section = [chunk for chunk in chunks if chunk.section_path == ("First",)]
    assert len(first_section) == 2
    assert "three four" in first_section[0].normalized_text
    assert "three four" in first_section[1].normalized_text
    second_section = [chunk for chunk in chunks if chunk.section_path == ("Second",)]
    assert len(second_section) == 1
    assert "five six" not in second_section[0].normalized_text


def test_build_chunks_keeps_formula_and_table_environments_whole() -> None:
    from app.knowledge.chunking import build_chunks

    lines = [
        LatexLine("\\section{Results}", "main.tex", 1),
        LatexLine("The fitted model is", "main.tex", 2),
        LatexLine("\\begin{equation}", "main.tex", 3),
        LatexLine("score = a + bx", "main.tex", 4),
        LatexLine("\\end{equation}", "main.tex", 5),
        LatexLine("and is stable.", "main.tex", 6),
        LatexLine("", "main.tex", 7),
        LatexLine("\\begin{table}", "main.tex", 8),
        LatexLine("\\caption{Metrics}", "main.tex", 9),
        LatexLine("\\end{table}", "main.tex", 10),
    ]

    chunks = build_chunks(lines, token_counter=_word_counter, max_tokens=20)

    formula_chunk = next(chunk for chunk in chunks if "\\begin{equation}" in chunk.raw_latex)
    assert "\\end{equation}" in formula_chunk.raw_latex
    assert "The fitted model is" in formula_chunk.raw_latex
    assert "and is stable." in formula_chunk.raw_latex
    table_chunk = next(chunk for chunk in chunks if "\\begin{table}" in chunk.raw_latex)
    assert "\\end{table}" in table_chunk.raw_latex


def test_build_chunks_does_not_combine_different_source_files() -> None:
    from app.knowledge.chunking import build_chunks

    lines = [
        LatexLine("\\section{Method}", "main.tex", 1),
        LatexLine("Main file introduction.", "main.tex", 2),
        LatexLine("Included file content.", "parts/model.tex", 1),
    ]

    chunks = build_chunks(lines, token_counter=_word_counter)

    assert [chunk.source_file for chunk in chunks] == ["main.tex", "parts/model.tex"]


def test_build_chunks_stops_the_abstract_section_at_its_end() -> None:
    from app.knowledge.chunking import build_chunks

    lines = [
        LatexLine("\\begin{abstract}", "main.tex", 1),
        LatexLine("Summary text.", "main.tex", 2),
        LatexLine("\\end{abstract}", "main.tex", 3),
        LatexLine("Text outside the abstract.", "main.tex", 4),
    ]

    chunks = build_chunks(lines, token_counter=_word_counter)

    assert [chunk.section_path for chunk in chunks] == [("Abstract",), ("Preamble",)]


@pytest.mark.parametrize(
    ("opening", "closing"),
    [(r"\[", r"\]"), ("$$", "$$"), (r"\(", r"\)")],
)
def test_build_chunks_severs_neighbors_before_exceeding_the_hard_math_limit(
    opening: str, closing: str
) -> None:
    from app.knowledge.chunking import build_chunks

    lines = [
        LatexLine("\\section{Results}", "main.tex", 1),
        LatexLine("Before formula text.", "main.tex", 2),
        LatexLine(opening, "main.tex", 3),
        LatexLine("x y", "main.tex", 4),
        LatexLine(closing, "main.tex", 5),
        LatexLine("After formula text continues.", "main.tex", 6),
        LatexLine("", "main.tex", 7),
        LatexLine("A later paragraph.", "main.tex", 8),
    ]

    chunks = build_chunks(lines, token_counter=_word_counter, max_tokens=5, overlap_tokens=0)

    formula_chunk = next(chunk for chunk in chunks if opening in chunk.raw_latex)
    assert closing in formula_chunk.raw_latex
    assert "Before formula text." not in formula_chunk.raw_latex
    assert "After formula text continues." not in formula_chunk.raw_latex
    assert all(_word_counter(chunk.normalized_text) <= 5 for chunk in chunks)


@pytest.mark.parametrize("environment", ["equation", "table"])
def test_build_chunks_severs_environment_neighbors_before_exceeding_the_hard_limit(
    environment: str,
) -> None:
    from app.knowledge.chunking import build_chunks

    lines = [
        LatexLine("\\section{Results}", "main.tex", 1),
        LatexLine("Before environment text.", "main.tex", 2),
        LatexLine(f"\\begin{{{environment}}}", "main.tex", 3),
        LatexLine("one two three four five six", "main.tex", 4),
        LatexLine(f"\\end{{{environment}}}", "main.tex", 5),
        LatexLine("After environment text.", "main.tex", 6),
        LatexLine("", "main.tex", 7),
        LatexLine("Later paragraph.", "main.tex", 8),
    ]

    chunks = build_chunks(lines, token_counter=_word_counter, max_tokens=6, overlap_tokens=0)

    environment_chunk = next(chunk for chunk in chunks if f"\\begin{{{environment}}}" in chunk.raw_latex)
    assert f"\\end{{{environment}}}" in environment_chunk.raw_latex
    assert "Before environment text." not in environment_chunk.raw_latex
    assert "After environment text." not in environment_chunk.raw_latex
    assert all(_word_counter(chunk.normalized_text) <= 6 for chunk in chunks)


@pytest.mark.parametrize("environment", ["equation", "table"])
def test_build_chunks_rejects_a_single_protected_atom_above_the_hard_limit(
    environment: str,
) -> None:
    from app.knowledge.chunking import ChunkingError, build_chunks

    lines = [
        LatexLine(f"\\begin{{{environment}}}", "main.tex", 1),
        LatexLine("one two three four five", "main.tex", 2),
        LatexLine(f"\\end{{{environment}}}", "main.tex", 3),
    ]

    with pytest.raises(ChunkingError, match="protected atom exceeds"):
        build_chunks(lines, token_counter=_word_counter, max_tokens=4)


def test_build_chunks_tracks_long_section_titles_with_optional_short_titles_and_nested_braces() -> None:
    from app.knowledge.chunking import build_chunks

    lines = [
        LatexLine(r"\section[Summary]{Long {Nested} Title}", "main.tex", 1),
        LatexLine("Section text.", "main.tex", 2),
        LatexLine(r"\subsection[Method]{Method {Version 2}}", "main.tex", 3),
        LatexLine("Subsection text.", "main.tex", 4),
        LatexLine(r"\subsubsection{Detail {A}}", "main.tex", 5),
        LatexLine("Detail text.", "main.tex", 6),
    ]

    chunks = build_chunks(lines, token_counter=_word_counter)

    assert [chunk.section_path for chunk in chunks] == [
        ("Long Nested Title",),
        ("Long Nested Title", "Method Version 2"),
        ("Long Nested Title", "Method Version 2", "Detail A"),
    ]


def test_build_chunks_never_accepts_a_limit_above_the_hard_450_token_cap() -> None:
    from app.knowledge.chunking import build_chunks

    with pytest.raises(ValueError, match="450"):
        build_chunks(
            [LatexLine("one two", "main.tex", 1)],
            token_counter=_word_counter,
            max_tokens=451,
        )
