"""Shared validation for untrusted relative TeX paths."""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath

from app.knowledge.errors import KnowledgeIngestionError


class RelativeTexPathError(KnowledgeIngestionError):
    """Raised when a path cannot safely name a file inside a paper root."""


_WINDOWS_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def validate_relative_tex_path(value: str, *, label: str) -> str:
    """Return a safe relative path or reject platform-specific escape hatches."""

    if not isinstance(value, str) or not value or "\x00" in value:
        raise RelativeTexPathError(f"{label} must be a non-empty relative path")
    posix_path = PurePosixPath(value.replace("\\", "/"))
    windows_path = PureWindowsPath(value)
    parts = posix_path.parts
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or ".." in parts
        or any(":" in part for part in parts)
        or any(_is_windows_device_name(part) for part in parts)
    ):
        raise RelativeTexPathError(f"{label} must be a relative path inside the paper root")
    return value


def _is_windows_device_name(part: str) -> bool:
    base = part.rstrip(" . ").split(".", 1)[0].upper()
    return base in _WINDOWS_DEVICE_NAMES
