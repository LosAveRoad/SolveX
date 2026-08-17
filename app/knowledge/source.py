"""Safe local loading of a paper directory or source archive."""

from __future__ import annotations

import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Optional, Type

import yaml
from pydantic import ValidationError

from app.knowledge.errors import KnowledgeIngestionError
from app.knowledge.manifest import PaperManifest
from app.knowledge.paths import RelativeTexPathError, validate_relative_tex_path


MAX_ZIP_MEMBERS = 2_000
MAX_TOTAL_EXTRACTED_BYTES = 25 * 1024 * 1024
MAX_EXTRACTABLE_MEMBER_BYTES = 5 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
ZIP_COPY_CHUNK_BYTES = 64 * 1024
_EXTRACTABLE_FILENAMES = {"paper.yaml"}
_EXTRACTABLE_SUFFIXES = {".tex", ".bib", ".sty", ".cls"}


class PaperSourceError(KnowledgeIngestionError):
    """Raised when a paper source cannot be loaded safely."""


class UnsafeArchiveError(PaperSourceError):
    """Raised when an archive contains an unsafe member."""


@dataclass
class PaperSource:
    """An opened paper source whose temporary extraction lives until closed."""

    root: Path
    manifest: PaperManifest
    _temporary_directory: Optional[tempfile.TemporaryDirectory] = None

    @property
    def main_tex_path(self) -> Path:
        try:
            main_tex = validate_relative_tex_path(self.manifest.main_tex, label="main_tex")
            path = (self.root / main_tex).resolve()
        except (OSError, RuntimeError, ValueError, RelativeTexPathError) as exc:
            raise PaperSourceError("could not resolve main_tex safely") from exc
        _ensure_inside_root(path, self.root, "main_tex")
        if not path.is_file():
            raise PaperSourceError(f"main_tex does not exist or is not a file: {self.manifest.main_tex}")
        return path

    def close(self) -> None:
        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()
            self._temporary_directory = None

    def __enter__(self) -> "PaperSource":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()


def open_paper_source(source_path: str | Path) -> PaperSource:
    """Open a paper directory or safely extract a ``.zip`` source archive."""

    try:
        source = Path(source_path)
        if source.is_dir():
            return _open_root(source.resolve())
        if source.is_file() and source.suffix.lower() == ".zip":
            temporary_directory = tempfile.TemporaryDirectory(prefix="solvex-paper-")
            try:
                extraction_root = Path(temporary_directory.name).resolve()
                _extract_safely(source, extraction_root)
                paper_root = _find_paper_root(extraction_root)
                opened = _open_root(paper_root)
                opened._temporary_directory = temporary_directory
                return opened
            except Exception:
                temporary_directory.cleanup()
                raise
        raise PaperSourceError(f"paper source must be a directory or .zip archive: {source}")
    except KnowledgeIngestionError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise PaperSourceError("could not open paper source") from exc


def _open_root(root: Path) -> PaperSource:
    try:
        manifest_path = (root / "paper.yaml").resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise PaperSourceError("could not resolve paper.yaml") from exc
    _ensure_inside_root(manifest_path, root, "paper.yaml")
    if not manifest_path.is_file():
        raise PaperSourceError(f"paper.yaml is required in paper root: {root}")
    data = _read_manifest_data(manifest_path)
    if not isinstance(data, dict):
        raise PaperSourceError("paper.yaml must contain a mapping")
    try:
        manifest = PaperManifest.model_validate(data)
    except ValidationError as exc:
        raise PaperSourceError(f"invalid paper.yaml: {exc}") from exc
    opened = PaperSource(root=root.resolve(), manifest=manifest)
    _ = opened.main_tex_path
    return opened


def _read_manifest_data(manifest_path: Path) -> object:
    """Read a directory manifest with the same per-member limit as ZIP input."""

    try:
        _check_manifest_size(manifest_path.stat().st_size)
        with manifest_path.open("rb") as manifest_file:
            raw_data = manifest_file.read(MAX_EXTRACTABLE_MEMBER_BYTES + 1)
        _check_manifest_size(len(raw_data))
        return yaml.safe_load(raw_data.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        raise PaperSourceError(f"could not read paper.yaml: {exc}") from exc


def _check_manifest_size(size: int) -> None:
    if size > MAX_EXTRACTABLE_MEMBER_BYTES:
        raise ValueError(
            f"paper.yaml size exceeds {MAX_EXTRACTABLE_MEMBER_BYTES} bytes"
        )


def _extract_safely(archive_path: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_ZIP_MEMBERS:
                raise UnsafeArchiveError(
                    f"archive exceeds the {MAX_ZIP_MEMBERS}-member budget"
                )
            extractable_members: list[zipfile.ZipInfo] = []
            declared_total = 0
            for member in members:
                _validate_archive_member(member)
                if member.is_dir() or not _is_extractable_member(member.filename):
                    continue
                _validate_extractable_member_budget(member)
                declared_total += member.file_size
                if declared_total > MAX_TOTAL_EXTRACTED_BYTES:
                    raise UnsafeArchiveError(
                        f"archive exceeds the {MAX_TOTAL_EXTRACTED_BYTES}-byte extraction budget"
                    )
                extractable_members.append(member)

            extracted_total = 0
            for member in extractable_members:
                target = (destination / member.filename).resolve()
                _ensure_inside_root(target, destination, "archive member")
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted_total = _copy_member_stream(
                    archive, member, target, extracted_total
                )
    except KnowledgeIngestionError:
        raise
    except (OSError, UnicodeError, RuntimeError, zipfile.BadZipFile) as exc:
        raise PaperSourceError(f"invalid zip archive: {archive_path}") from exc


def _validate_archive_member(member: zipfile.ZipInfo) -> None:
    name = member.filename
    mode = member.external_attr >> 16
    try:
        validate_relative_tex_path(name.rstrip("/\\"), label="archive member")
    except RelativeTexPathError as exc:
        raise UnsafeArchiveError(f"unsafe archive member path: {name!r}") from exc
    if stat.S_ISLNK(mode):
        raise UnsafeArchiveError(f"archive member is a symbolic link: {name!r}")


def _is_extractable_member(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return path.name.lower() in _EXTRACTABLE_FILENAMES or path.suffix.lower() in _EXTRACTABLE_SUFFIXES


def _validate_extractable_member_budget(member: zipfile.ZipInfo) -> None:
    if member.file_size > MAX_EXTRACTABLE_MEMBER_BYTES:
        raise UnsafeArchiveError(
            f"archive member size exceeds {MAX_EXTRACTABLE_MEMBER_BYTES} bytes: {member.filename!r}"
        )
    if member.file_size and not member.compress_size:
        raise UnsafeArchiveError(
            f"archive compression ratio exceeds {MAX_COMPRESSION_RATIO}: {member.filename!r}"
        )
    if member.compress_size and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO:
        raise UnsafeArchiveError(
            f"archive compression ratio exceeds {MAX_COMPRESSION_RATIO}: {member.filename!r}"
        )


def _copy_member_stream(
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    target: Path,
    extracted_total: int,
) -> int:
    member_total = 0
    with archive.open(member) as input_file, target.open("wb") as output_file:
        while chunk := input_file.read(ZIP_COPY_CHUNK_BYTES):
            member_total += len(chunk)
            extracted_total += len(chunk)
            if member_total > MAX_EXTRACTABLE_MEMBER_BYTES:
                raise UnsafeArchiveError(
                    f"archive member size exceeds {MAX_EXTRACTABLE_MEMBER_BYTES} bytes: {member.filename!r}"
                )
            if extracted_total > MAX_TOTAL_EXTRACTED_BYTES:
                raise UnsafeArchiveError(
                    f"archive exceeds the {MAX_TOTAL_EXTRACTED_BYTES}-byte extraction budget"
                )
            output_file.write(chunk)
    return extracted_total


def _find_paper_root(extraction_root: Path) -> Path:
    if (extraction_root / "paper.yaml").is_file():
        return extraction_root
    raise PaperSourceError("paper.yaml is required at the archive root")


def _ensure_inside_root(path: Path, root: Path, label: str) -> None:
    try:
        path.relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise PaperSourceError(f"{label} escapes the paper root") from exc
