from pathlib import Path

import pytest


def _write_manifest(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "paper.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "paper_id: latex-hardening",
                "title: LaTeX Hardening",
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


def test_parse_latex_expands_only_body_includes_and_supports_unbraced_syntax(tmp_path: Path) -> None:
    from app.knowledge.latex import parse_latex
    from app.knowledge.source import open_paper_source

    root = tmp_path / "paper"
    _write_manifest(root)
    (root / "main.tex").write_text(
        """\\begin{verbatim}
\\input{missing-verbatim}
\\end{verbatim}
\\begin{lstlisting}
\\include missing-listing
\\end{lstlisting}
\\begin{minted}{python}
\\input{missing-minted}
\\end{minted}
\\begin{comment}
\\input{missing-comment}
\\end{comment}
\\newcommand{\\demo}[1]{\\input{missing-newcommand}}
\\renewcommand{\\demo}[1]{\\include{missing-renewcommand}}
\\providecommand{\\demo}[1]{\\input{missing-providecommand}}
\\def\\demo{\\input{missing-def}}
\\gdef\\demo{\\include{missing-gdef}}
\\input child
\\include nested/second
""",
        encoding="utf-8",
    )
    (root / "child.tex").write_text("Expanded child.", encoding="utf-8")
    (root / "nested").mkdir()
    (root / "nested" / "second.tex").write_text("Expanded second.", encoding="utf-8")

    with open_paper_source(root) as source:
        lines = parse_latex(source)

    text = "\n".join(line.text for line in lines)
    assert "Expanded child." in text
    assert "Expanded second." in text
    assert "missing-verbatim" in text
    assert "missing-newcommand" in text
    assert "missing-def" in text


def test_latex_include_failures_share_the_ingestion_error_base(tmp_path: Path) -> None:
    from app.knowledge.errors import KnowledgeIngestionError
    from app.knowledge.latex import LatexIncludeError, parse_latex
    from app.knowledge.source import open_paper_source

    root = tmp_path / "paper"
    _write_manifest(root)
    (root / "main.tex").write_text("\\input missing", encoding="utf-8")

    with open_paper_source(root) as source:
        with pytest.raises(KnowledgeIngestionError):
            parse_latex(source)
        with pytest.raises(LatexIncludeError):
            parse_latex(source)
