import stat
import zipfile
from pathlib import Path

import pytest


def _write_paper(root: Path, *, main_tex: str = "main.tex") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "paper.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "paper_id: source-test",
                "title: Source Test",
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
    main_path = root / main_tex
    main_path.parent.mkdir(parents=True, exist_ok=True)
    main_path.write_text("\\section{Model}\nBody text.", encoding="utf-8")


def test_open_paper_source_reads_a_directory_manifest_and_main_file(tmp_path: Path) -> None:
    from app.knowledge.source import open_paper_source

    paper_root = tmp_path / "paper"
    _write_paper(paper_root, main_tex="tex/main.tex")

    with open_paper_source(paper_root) as source:
        assert source.root == paper_root.resolve()
        assert source.manifest.paper_id == "source-test"
        assert source.main_tex_path == (paper_root / "tex/main.tex").resolve()


def test_open_paper_source_requires_paper_yaml_in_a_directory(tmp_path: Path) -> None:
    from app.knowledge.source import PaperSourceError, open_paper_source

    with pytest.raises(PaperSourceError, match="paper.yaml"):
        open_paper_source(tmp_path)


def test_open_paper_source_extracts_a_zip_to_an_isolated_temporary_root(tmp_path: Path) -> None:
    from app.knowledge.source import open_paper_source

    paper_root = tmp_path / "paper"
    _write_paper(paper_root)
    archive = tmp_path / "paper.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in paper_root.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(paper_root).as_posix())

    with open_paper_source(archive) as source:
        assert source.manifest.title == "Source Test"
        assert source.main_tex_path.read_text(encoding="utf-8").startswith("\\section")
        assert source.root != paper_root.resolve()


def test_open_paper_source_requires_paper_yaml_at_the_extracted_zip_root(tmp_path: Path) -> None:
    from app.knowledge.source import PaperSourceError, open_paper_source

    paper_root = tmp_path / "paper"
    _write_paper(paper_root)
    archive = tmp_path / "wrapped-paper.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in paper_root.rglob("*"):
            if path.is_file():
                bundle.write(path, f"paper-wrapper/{path.relative_to(paper_root).as_posix()}")

    with pytest.raises(PaperSourceError, match="archive root"):
        open_paper_source(archive)


@pytest.mark.parametrize("member_name", ["../outside.txt", "/absolute.txt", "nested/../../outside.txt"])
def test_open_paper_source_rejects_zip_path_traversal(tmp_path: Path, member_name: str) -> None:
    from app.knowledge.source import UnsafeArchiveError, open_paper_source

    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(member_name, "not allowed")

    with pytest.raises(UnsafeArchiveError):
        open_paper_source(archive)


def test_open_paper_source_rejects_symbolic_links_in_zip(tmp_path: Path) -> None:
    from app.knowledge.source import UnsafeArchiveError, open_paper_source

    archive = tmp_path / "symlink.zip"
    link = zipfile.ZipInfo("paper-link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(link, "../outside")

    with pytest.raises(UnsafeArchiveError, match="symbolic link"):
        open_paper_source(archive)


def test_open_paper_source_rejects_a_main_tex_resolving_outside_the_root(tmp_path: Path) -> None:
    from app.knowledge.source import PaperSourceError, open_paper_source

    paper_root = tmp_path / "paper"
    _write_paper(paper_root)
    (paper_root / "main.tex").unlink()
    (paper_root / "paper.yaml").write_text(
        (paper_root / "paper.yaml").read_text(encoding="utf-8").replace(
            "main.tex", "../outside.tex"
        ),
        encoding="utf-8",
    )

    with pytest.raises(PaperSourceError):
        open_paper_source(paper_root)
