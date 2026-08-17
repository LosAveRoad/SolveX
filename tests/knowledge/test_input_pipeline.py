from __future__ import annotations

import zipfile
from pathlib import Path

import pytest


def _manifest(main_tex: str = "main.tex") -> str:
    return "\n".join(
        [
            "schema_version: 1",
            "paper_id: bounded-input-test",
            "title: Bounded Input Test",
            "competition: MCM",
            "year: 2025",
            "problem: C",
            "award: Finalist",
            "language: en",
            f"main_tex: {main_tex}",
        ]
    )


def _make_source(tmp_path: Path, kind: str, files: dict[str, str]) -> Path:
    if kind == "directory":
        root = tmp_path / "paper"
        root.mkdir(parents=True)
        for name, contents in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents, encoding="utf-8")
        return root

    archive = tmp_path / "paper.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, contents in files.items():
            bundle.writestr(name, contents.encode("utf-8"))
    return archive


@pytest.mark.parametrize("kind", ["directory", "zip"])
def test_parse_budget_counts_every_repeated_include_for_each_source_type(
    tmp_path: Path, kind: str
) -> None:
    from app.knowledge.latex import LatexParseBudgetError, ParseBudget, parse_latex
    from app.knowledge.source import open_paper_source

    source_path = _make_source(
        tmp_path,
        kind,
        {
            "paper.yaml": _manifest(),
            "main.tex": "\\input{child}\n\\input{child}\n\\input{child}\n",
            "child.tex": "expanded body\n",
        },
    )

    with open_paper_source(source_path) as source:
        with pytest.raises(LatexParseBudgetError, match="include call"):
            parse_latex(source, budget=ParseBudget(max_include_calls=2))


@pytest.mark.parametrize("kind", ["directory", "zip"])
def test_parse_budget_rejects_include_depth_for_each_source_type(tmp_path: Path, kind: str) -> None:
    from app.knowledge.latex import LatexParseBudgetError, ParseBudget, parse_latex
    from app.knowledge.source import open_paper_source

    source_path = _make_source(
        tmp_path,
        kind,
        {
            "paper.yaml": _manifest(),
            "main.tex": "\\input{one}\n",
            "one.tex": "\\input{two}\n",
            "two.tex": "body\n",
        },
    )

    with open_paper_source(source_path) as source:
        with pytest.raises(LatexParseBudgetError, match="depth"):
            parse_latex(source, budget=ParseBudget(max_include_depth=1))


@pytest.mark.parametrize("kind", ["directory", "zip"])
def test_parse_budget_rejects_a_single_tex_source_for_each_source_type(
    tmp_path: Path, kind: str
) -> None:
    from app.knowledge.latex import LatexParseBudgetError, ParseBudget, parse_latex
    from app.knowledge.source import open_paper_source

    source_path = _make_source(
        tmp_path,
        kind,
        {"paper.yaml": _manifest(), "main.tex": "x" * 40},
    )

    with open_paper_source(source_path) as source:
        with pytest.raises(LatexParseBudgetError, match="single TeX"):
            parse_latex(source, budget=ParseBudget(max_single_tex_bytes=32))


def test_literal_and_macro_lines_are_non_structural_to_chunking(tmp_path: Path) -> None:
    from app.knowledge.chunking import build_chunks
    from app.knowledge.latex import parse_latex
    from app.knowledge.source import open_paper_source

    root = _make_source(
        tmp_path,
        "directory",
        {
            "paper.yaml": _manifest(),
            "main.tex": """\\section{Real}
\\begin{verbatim}
\\section{Literal}
\\begin{table}
one two three four five
\\end{table}
\\end{verbatim}
\\newcommand{\\ghost}{\\section{Macro Ghost}}
Visible conclusion.
""",
        },
    )

    with open_paper_source(root) as source:
        lines = parse_latex(source)

    assert not lines[1].structural
    assert not lines[2].structural
    assert not lines[6].structural
    chunks = build_chunks(lines, token_counter=lambda text: len(text.split()), max_tokens=3)
    assert all(chunk.section_path == ("Real",) for chunk in chunks)
    assert all(len(chunk.normalized_text.split()) <= 3 for chunk in chunks)


def test_public_open_and_parse_wrap_invalid_untrusted_paths_with_ingestion_errors(tmp_path: Path) -> None:
    from app.knowledge.errors import KnowledgeIngestionError
    from app.knowledge.latex import LatexIncludeError, parse_latex
    from app.knowledge.source import PaperSourceError, open_paper_source

    invalid_manifest = _make_source(
        tmp_path / "manifest",
        "directory",
        {"paper.yaml": _manifest("bad\x00.tex"), "main.tex": "body"},
    )
    with pytest.raises(PaperSourceError) as manifest_error:
        open_paper_source(invalid_manifest)
    assert isinstance(manifest_error.value, KnowledgeIngestionError)
    assert manifest_error.value.__cause__ is not None

    root = _make_source(
        tmp_path / "include",
        "directory",
        {"paper.yaml": _manifest(), "main.tex": "\\input{bad\x00.tex}"},
    )
    with open_paper_source(root) as source:
        with pytest.raises(LatexIncludeError) as include_error:
            parse_latex(source)
    assert isinstance(include_error.value, KnowledgeIngestionError)
    assert include_error.value.__cause__ is not None


@pytest.mark.parametrize("member_name", ["NUL.tex", "COM1.tex", "notes:stream.tex"])
def test_zip_rejects_windows_device_and_ads_member_paths(tmp_path: Path, member_name: str) -> None:
    from app.knowledge.errors import KnowledgeIngestionError
    from app.knowledge.source import open_paper_source

    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("paper.yaml", _manifest())
        bundle.writestr("main.tex", "body")
        bundle.writestr(member_name, "unsafe")

    with pytest.raises(KnowledgeIngestionError, match="unsafe archive member") as error:
        open_paper_source(archive)
    assert error.value.__cause__ is not None


def test_public_manifest_type_error_is_wrapped_by_open_paper_source(tmp_path: Path) -> None:
    from app.knowledge.errors import KnowledgeIngestionError
    from app.knowledge.source import PaperSourceError, open_paper_source

    root = _make_source(
        tmp_path,
        "directory",
        {"paper.yaml": _manifest("[not-a-path]"), "main.tex": "body"},
    )
    with pytest.raises(PaperSourceError) as error:
        open_paper_source(root)
    assert isinstance(error.value, KnowledgeIngestionError)
    assert error.value.__cause__ is not None


@pytest.mark.parametrize("public_entry", ["open", "load"])
def test_directory_manifest_size_is_bounded_before_parsing(
    tmp_path: Path, public_entry: str
) -> None:
    from app.knowledge.ingestion import load_paper_document
    from app.knowledge.source import MAX_EXTRACTABLE_MEMBER_BYTES, PaperSourceError, open_paper_source

    root = tmp_path / "paper"
    root.mkdir()
    (root / "paper.yaml").write_bytes(b"x" * (MAX_EXTRACTABLE_MEMBER_BYTES + 1))
    (root / "main.tex").write_text("body", encoding="utf-8")

    if public_entry == "open":
        operation = lambda: open_paper_source(root)
    else:
        operation = lambda: load_paper_document(root, token_counter=lambda text: 1)

    with pytest.raises(PaperSourceError, match="paper.yaml.*size") as error:
        operation()
    assert error.value.__cause__ is not None
