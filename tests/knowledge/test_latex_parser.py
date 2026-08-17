from pathlib import Path

import pytest


def _write_manifest(root: Path, main_tex: str = "main.tex") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "paper.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "paper_id: parser-test",
                "title: Parser Test",
                "competition: MCM",
                "year: 2025",
                "problem: C",
                "award: Finalist",
                "language: en",
                f"main_tex: {main_tex}",
            ]
        ),
        encoding="utf-8",
    )


def test_parse_latex_expands_nested_input_and_include_with_source_locations(tmp_path: Path) -> None:
    from app.knowledge.latex import parse_latex
    from app.knowledge.source import open_paper_source

    root = tmp_path / "paper"
    _write_manifest(root)
    (root / "main.tex").write_text(
        "\\section{Main}\nBefore.\n\\input{parts/first}\nAfter.", encoding="utf-8"
    )
    (root / "parts").mkdir()
    (root / "parts" / "first.tex").write_text(
        "First.\n\\include{nested/second}", encoding="utf-8"
    )
    (root / "parts" / "nested").mkdir()
    (root / "parts" / "nested" / "second.tex").write_text("Second.", encoding="utf-8")

    with open_paper_source(root) as source:
        lines = parse_latex(source)

    assert [line.text for line in lines] == ["\\section{Main}", "Before.", "First.", "Second.", "After."]
    assert [(line.source_file, line.line_number) for line in lines] == [
        ("main.tex", 1),
        ("main.tex", 2),
        ("parts/first.tex", 1),
        ("parts/nested/second.tex", 1),
        ("main.tex", 4),
    ]


def test_parse_latex_rejects_missing_or_circular_or_escaping_includes(tmp_path: Path) -> None:
    from app.knowledge.latex import LatexIncludeError, parse_latex
    from app.knowledge.source import open_paper_source

    missing_root = tmp_path / "missing"
    _write_manifest(missing_root)
    (missing_root / "main.tex").write_text("\\input{no-such-file}", encoding="utf-8")
    with open_paper_source(missing_root) as source:
        with pytest.raises(LatexIncludeError, match="does not exist"):
            parse_latex(source)

    cycle_root = tmp_path / "cycle"
    _write_manifest(cycle_root)
    (cycle_root / "main.tex").write_text("\\input{other}", encoding="utf-8")
    (cycle_root / "other.tex").write_text("\\input{main}", encoding="utf-8")
    with open_paper_source(cycle_root) as source:
        with pytest.raises(LatexIncludeError, match="cycle"):
            parse_latex(source)

    escape_root = tmp_path / "escape"
    _write_manifest(escape_root)
    (escape_root / "main.tex").write_text("\\input{../outside}", encoding="utf-8")
    (tmp_path / "outside.tex").write_text("outside", encoding="utf-8")
    with open_paper_source(escape_root) as source:
        with pytest.raises(LatexIncludeError, match="escapes"):
            parse_latex(source)


def test_parse_latex_ignores_bibliography_and_never_expands_commented_input(tmp_path: Path) -> None:
    from app.knowledge.latex import parse_latex
    from app.knowledge.source import open_paper_source

    root = tmp_path / "paper"
    _write_manifest(root)
    (root / "main.tex").write_text(
        "\\section{Model}\n"
        "Visible body. % \\input{missing-file}\n"
        "\\bibliography{references}\n"
        "\\addbibresource{references.bib}\n"
        "\\begin{thebibliography}{9}\n"
        "\\bibitem{ignored} Ignored reference.\n"
        "\\end{thebibliography}\n"
        "\\write18{must-not-run}\n",
        encoding="utf-8",
    )

    with open_paper_source(root) as source:
        lines = parse_latex(source)

    text = "\n".join(line.text for line in lines)
    assert "Visible body." in text
    assert "missing-file" in text
    assert "bibliography" not in text
    assert "Ignored reference" not in text
    assert "\\write18{must-not-run}" in text
