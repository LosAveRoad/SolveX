import io
import zipfile
from pathlib import Path

import pytest


def _manifest() -> bytes:
    return b"\n".join(
        [
            b"schema_version: 1",
            b"paper_id: hardening-test",
            b"title: Hardening Test",
            b"competition: MCM",
            b"year: 2025",
            b"problem: C",
            b"award: Finalist",
            b"language: en",
            b"main_tex: main.tex",
        ]
    )


def _write_archive(path: Path, extra_members: int = 0) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("paper.yaml", _manifest())
        archive.writestr("main.tex", "\\section{Model}\nBody")
        for index in range(extra_members):
            archive.writestr(f"extra-{index}.txt", "ignored")


def test_zip_rejects_more_than_the_member_budget(tmp_path: Path) -> None:
    from app.knowledge.errors import KnowledgeIngestionError
    from app.knowledge.source import MAX_ZIP_MEMBERS, open_paper_source

    archive = tmp_path / "too-many.zip"
    _write_archive(archive, extra_members=MAX_ZIP_MEMBERS)

    with pytest.raises(KnowledgeIngestionError, match="member"):
        open_paper_source(archive)


def test_zip_rejects_an_oversize_latex_member_before_extraction(tmp_path: Path) -> None:
    from app.knowledge.errors import KnowledgeIngestionError
    from app.knowledge.source import MAX_EXTRACTABLE_MEMBER_BYTES, open_paper_source

    archive = tmp_path / "large-member.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        bundle.writestr("paper.yaml", _manifest())
        bundle.writestr("main.tex", b"x" * (MAX_EXTRACTABLE_MEMBER_BYTES + 1))

    with pytest.raises(KnowledgeIngestionError, match="member size"):
        open_paper_source(archive)


def test_zip_rejects_a_high_compression_ratio_source_member(tmp_path: Path) -> None:
    from app.knowledge.errors import KnowledgeIngestionError
    from app.knowledge.source import open_paper_source

    archive = tmp_path / "compressed.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("paper.yaml", _manifest())
        bundle.writestr("main.tex", b"x" * (1024 * 1024))

    with pytest.raises(KnowledgeIngestionError, match="compression ratio"):
        open_paper_source(archive)


def test_zip_streaming_copy_enforces_actual_extraction_budget(tmp_path: Path, monkeypatch) -> None:
    import app.knowledge.source as source_module
    from app.knowledge.errors import KnowledgeIngestionError

    class FakeArchive:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

        def infolist(self):
            manifest = zipfile.ZipInfo("paper.yaml")
            manifest.file_size = len(_manifest())
            manifest.compress_size = len(_manifest())
            source_members = []
            for index in range(6):
                member = zipfile.ZipInfo(f"source-{index}.tex")
                member.file_size = 1
                member.compress_size = 1
                source_members.append(member)
            return [manifest, *source_members]

        def open(self, member):
            if member.filename == "paper.yaml":
                return io.BytesIO(_manifest())
            return io.BytesIO(b"x" * source_module.MAX_EXTRACTABLE_MEMBER_BYTES)

    archive = tmp_path / "streaming.zip"
    archive.write_bytes(b"placeholder")
    monkeypatch.setattr(source_module.zipfile, "ZipFile", lambda path: FakeArchive())

    with pytest.raises(KnowledgeIngestionError, match="extraction budget"):
        source_module.open_paper_source(archive)


def test_directory_manifest_symlink_and_invalid_manifest_share_the_ingestion_error(tmp_path: Path) -> None:
    from app.knowledge.errors import KnowledgeIngestionError
    from app.knowledge.source import open_paper_source

    invalid_root = tmp_path / "invalid"
    invalid_root.mkdir()
    (invalid_root / "paper.yaml").write_bytes(b"\xff\xfe")
    with pytest.raises(KnowledgeIngestionError):
        open_paper_source(invalid_root)

    symlink_root = tmp_path / "symlink"
    symlink_root.mkdir()
    (symlink_root / "main.tex").write_text("body", encoding="utf-8")
    outside_manifest = tmp_path / "outside-paper.yaml"
    outside_manifest.write_bytes(_manifest())
    try:
        (symlink_root / "paper.yaml").symlink_to(outside_manifest)
    except OSError:
        pytest.skip("creating a file symlink is unavailable on this Windows host")
    with pytest.raises(KnowledgeIngestionError, match="paper.yaml escapes"):
        open_paper_source(symlink_root)


def test_all_public_ingestion_failures_share_the_common_base() -> None:
    from app.knowledge.chunking import ChunkingError
    from app.knowledge.errors import KnowledgeIngestionError
    from app.knowledge.latex import LatexIncludeError
    from app.knowledge.source import PaperSourceError

    assert issubclass(PaperSourceError, KnowledgeIngestionError)
    assert issubclass(LatexIncludeError, KnowledgeIngestionError)
    assert issubclass(ChunkingError, KnowledgeIngestionError)
