"""Conservative LaTeX source expansion for locally supplied papers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.knowledge.errors import KnowledgeIngestionError
from app.knowledge.paths import RelativeTexPathError, validate_relative_tex_path
from app.knowledge.source import PaperSource


_INCLUDE_COMMAND = re.compile(r"\\(?:input|include)\b")
_BIBLIOGRAPHY_COMMAND = re.compile(
    r"\\(?:bibliography|addbibresource)\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}"
)
_BIBLIOGRAPHY_BEGIN = re.compile(r"\\begin\s*\{thebibliography\}")
_BIBLIOGRAPHY_END = re.compile(r"\\end\s*\{thebibliography\}")
_PROTECTED_LITERAL_ENVIRONMENTS = {"verbatim", "lstlisting", "minted", "comment"}
_ENVIRONMENT_BEGIN = re.compile(r"\\begin\s*\{([^{}]+)\}")
_ENVIRONMENT_END = re.compile(r"\\end\s*\{([^{}]+)\}")
_MACRO_DEFINITION = re.compile(r"\\(?:newcommand|renewcommand|providecommand|def|gdef)\b")
MAX_TEX_SOURCE_BYTES = 5 * 1024 * 1024
MAX_PARSED_TEXT_BYTES = 25 * 1024 * 1024
MAX_INCLUDE_CALLS = 512
MAX_INCLUDE_DEPTH = 32
MAX_EXPANDED_LINES = 200_000


class LatexIncludeError(KnowledgeIngestionError):
    """Raised when a LaTeX include cannot be resolved safely."""


class LatexParseBudgetError(LatexIncludeError):
    """Raised when an untrusted source exceeds bounded parser resources."""


@dataclass
class ParseBudget:
    """Shared resource limits for one complete recursive source expansion."""

    max_single_tex_bytes: int = MAX_TEX_SOURCE_BYTES
    max_total_text_bytes: int = MAX_PARSED_TEXT_BYTES
    max_include_calls: int = MAX_INCLUDE_CALLS
    max_include_depth: int = MAX_INCLUDE_DEPTH
    max_expanded_lines: int = MAX_EXPANDED_LINES
    read_bytes: int = 0
    expanded_bytes: int = 0
    include_calls: int = 0
    expanded_lines: int = 0

    def check_source_size(self, size: int, path: Path) -> None:
        if size > self.max_single_tex_bytes:
            raise LatexParseBudgetError(
                f"single TeX source exceeds the {self.max_single_tex_bytes}-byte budget: {path}"
            )

    def consume_read_bytes(self, size: int) -> None:
        self.read_bytes += size
        if self.read_bytes > self.max_total_text_bytes:
            raise LatexParseBudgetError(
                f"total TeX source read exceeds the {self.max_total_text_bytes}-byte budget"
            )

    def consume_include_call(self) -> None:
        self.include_calls += 1
        if self.include_calls > self.max_include_calls:
            raise LatexParseBudgetError(
                f"include call budget exceeds {self.max_include_calls}"
            )

    def check_depth(self, depth: int) -> None:
        if depth > self.max_include_depth:
            raise LatexParseBudgetError(
                f"include depth exceeds {self.max_include_depth}"
            )

    def consume_expanded_line(self, text: str) -> None:
        self.expanded_lines += 1
        if self.expanded_lines > self.max_expanded_lines:
            raise LatexParseBudgetError(
                f"expanded line budget exceeds {self.max_expanded_lines}"
            )
        self.expanded_bytes += len(text.encode("utf-8")) + 1
        if self.expanded_bytes > self.max_total_text_bytes:
            raise LatexParseBudgetError(
                f"expanded TeX text exceeds the {self.max_total_text_bytes}-byte budget"
            )


@dataclass(frozen=True)
class LatexLine:
    """A source line after recursively expanding safe include directives."""

    text: str
    source_file: str
    line_number: int
    structural: bool = True


def parse_latex(source: PaperSource, *, budget: ParseBudget | None = None) -> list[LatexLine]:
    """Expand ``\\input``/``\\include`` without executing any TeX command."""

    parse_budget = budget or ParseBudget()
    try:
        expanded = _expand_file(
            source.main_tex_path, source.root, stack=[], budget=parse_budget, depth=0
        )
        return _exclude_bibliography(expanded)
    except KnowledgeIngestionError:
        raise
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise LatexIncludeError("could not parse LaTeX source") from exc


def _expand_file(
    path: Path,
    root: Path,
    stack: list[Path],
    *,
    budget: ParseBudget,
    depth: int,
) -> list[LatexLine]:
    budget.check_depth(depth)
    try:
        resolved_path = path.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise LatexIncludeError(f"could not resolve included file: {path}") from exc
    _ensure_inside_root(resolved_path, root)
    if resolved_path in stack:
        chain = " -> ".join(item.relative_to(root).as_posix() for item in [*stack, resolved_path])
        raise LatexIncludeError(f"include cycle detected: {chain}")
    if not resolved_path.is_file():
        raise LatexIncludeError(f"included file does not exist: {path}")

    try:
        budget.check_source_size(resolved_path.stat().st_size, resolved_path)
        input_file = resolved_path.open(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise LatexIncludeError(f"could not read included file: {resolved_path}") from exc

    try:
        relative_file = resolved_path.relative_to(root.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError) as exc:
        raise LatexIncludeError(f"include escapes the paper root: {resolved_path}") from exc
    next_stack = [*stack, resolved_path]
    result: list[LatexLine] = []
    literal_environment: str | None = None
    macro_brace_depth = 0
    try:
        with input_file:
            for line_number, physical_line in enumerate(input_file, start=1):
                budget.consume_read_bytes(len(physical_line.encode("utf-8")))
                text = physical_line.rstrip("\r\n")
                comment_index = _find_comment_start(text)
                executable_prefix = text if comment_index is None else text[:comment_index]
                if literal_environment is not None:
                    _append_line(result, budget, text, relative_file, line_number, structural=False)
                    if _ends_literal_environment(executable_prefix, literal_environment):
                        literal_environment = None
                    continue
                opened_environment = _opens_literal_environment(executable_prefix)
                if opened_environment is not None:
                    _append_line(result, budget, text, relative_file, line_number, structural=False)
                    if not _ends_literal_environment_after_open(executable_prefix, opened_environment):
                        literal_environment = opened_environment
                    continue
                if macro_brace_depth:
                    _append_line(result, budget, text, relative_file, line_number, structural=False)
                    macro_brace_depth += _brace_delta(executable_prefix)
                    if macro_brace_depth <= 0:
                        macro_brace_depth = 0
                    continue
                if _MACRO_DEFINITION.search(executable_prefix):
                    _append_line(result, budget, text, relative_file, line_number, structural=False)
                    macro_brace_depth = max(_brace_delta(executable_prefix), 0)
                    continue
                offset = 0
                for start, end, include_name in _iter_include_directives(executable_prefix):
                    prefix = text[offset:start]
                    if prefix:
                        _append_line(result, budget, prefix, relative_file, line_number)
                    budget.consume_include_call()
                    include_path = _resolve_include(include_name, resolved_path.parent, root)
                    result.extend(
                        _expand_file(
                            include_path,
                            root,
                            next_stack,
                            budget=budget,
                            depth=depth + 1,
                        )
                    )
                    offset = end
                remainder = text[offset:]
                if remainder:
                    _append_line(result, budget, remainder, relative_file, line_number)
    except (OSError, UnicodeError) as exc:
        raise LatexIncludeError(f"could not read included file: {resolved_path}") from exc
    return result


def _append_line(
    result: list[LatexLine],
    budget: ParseBudget,
    text: str,
    source_file: str,
    line_number: int,
    *,
    structural: bool = True,
) -> None:
    budget.consume_expanded_line(text)
    result.append(LatexLine(text, source_file, line_number, structural))


def _iter_include_directives(text: str):
    for match in _INCLUDE_COMMAND.finditer(text):
        if _is_escaped_command(text, match.start()):
            continue
        cursor = match.end()
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text):
            continue
        if text[cursor] == "{":
            argument, end = _read_braced_argument(text, cursor)
            if argument is None:
                continue
        else:
            end = cursor
            while end < len(text) and not text[end].isspace():
                end += 1
            argument = text[cursor:end]
        if argument:
            yield match.start(), end, argument


def _read_braced_argument(text: str, opening: int) -> tuple[str | None, int]:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{" and not _is_escaped_character(text, index):
            depth += 1
        elif text[index] == "}" and not _is_escaped_character(text, index):
            depth -= 1
            if depth == 0:
                return text[opening + 1:index], index + 1
    return None, opening


def _opens_literal_environment(code: str) -> str | None:
    for match in _ENVIRONMENT_BEGIN.finditer(code):
        environment = match.group(1).strip()
        if environment in _PROTECTED_LITERAL_ENVIRONMENTS:
            return environment
    return None


def _ends_literal_environment(code: str, environment: str) -> bool:
    return any(match.group(1).strip() == environment for match in _ENVIRONMENT_END.finditer(code))


def _ends_literal_environment_after_open(code: str, environment: str) -> bool:
    begin = re.search(rf"\\begin\s*\{{{re.escape(environment)}\}}", code)
    if begin is None:
        return False
    return bool(re.search(rf"\\end\s*\{{{re.escape(environment)}\}}", code[begin.end():]))


def _brace_delta(code: str) -> int:
    return sum(
        1 if character == "{" else -1
        for index, character in enumerate(code)
        if character in "{}" and not _is_escaped_character(code, index)
    )


def _is_escaped_command(text: str, index: int) -> bool:
    return _backslash_count(text, index - 1) % 2 == 1


def _is_escaped_character(text: str, index: int) -> bool:
    return _backslash_count(text, index - 1) % 2 == 1


def _backslash_count(text: str, index: int) -> int:
    count = 0
    while index >= 0 and text[index] == "\\":
        count += 1
        index -= 1
    return count


def _resolve_include(include_name: str, parent: Path, root: Path) -> Path:
    name = include_name.strip()
    try:
        safe_name = validate_relative_tex_path(name, label="include")
    except RelativeTexPathError as exc:
        raise LatexIncludeError(f"include escapes the paper root: {include_name!r}") from exc
    candidate = parent / safe_name
    if not candidate.suffix:
        candidate = candidate.with_suffix(".tex")
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise LatexIncludeError(f"could not resolve include: {include_name!r}") from exc
    _ensure_inside_root(resolved, root)
    if not resolved.is_file():
        raise LatexIncludeError(f"included file does not exist: {include_name}")
    return resolved


def _exclude_bibliography(lines: list[LatexLine]) -> list[LatexLine]:
    filtered: list[LatexLine] = []
    inside_bibliography = False
    for line in lines:
        if not line.structural:
            if not inside_bibliography:
                filtered.append(line)
            continue
        comment_index = _find_comment_start(line.text)
        code = line.text if comment_index is None else line.text[:comment_index]
        comment = "" if comment_index is None else line.text[comment_index:]
        if inside_bibliography:
            if _BIBLIOGRAPHY_END.search(code):
                inside_bibliography = False
            continue
        if _BIBLIOGRAPHY_BEGIN.search(code):
            if not _BIBLIOGRAPHY_END.search(code):
                inside_bibliography = True
            continue
        cleaned = _BIBLIOGRAPHY_COMMAND.sub("", code)
        if cleaned or comment:
            filtered.append(
                LatexLine(cleaned + comment, line.source_file, line.line_number, line.structural)
            )
    return filtered


def _find_comment_start(text: str) -> int | None:
    for index, character in enumerate(text):
        if character != "%":
            continue
        backslashes = 0
        cursor = index - 1
        while cursor >= 0 and text[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            return index
    return None


def _ensure_inside_root(path: Path, root: Path) -> None:
    try:
        path.relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise LatexIncludeError(f"include escapes the paper root: {path}") from exc
