"""Structure-aware chunking for LaTeX paper source."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.knowledge.errors import KnowledgeIngestionError
from app.knowledge.latex import LatexLine


TokenCounter = Callable[[str], int]
HARD_MAX_CHUNK_TOKENS = 450
_SECTION_COMMAND = re.compile(r"\\(section|subsection|subsubsection)\*?(?![A-Za-z@])")
_ABSTRACT_BEGIN = re.compile(r"\\begin\s*\{abstract\}")
_ABSTRACT_END = re.compile(r"\\end\s*\{abstract\}")
_ENVIRONMENT_BEGIN = re.compile(r"\\begin\s*\{([^{}]+)\}")
_ENVIRONMENT_END = re.compile(r"\\end\s*\{([^{}]+)\}")
_PROTECTED_ENVIRONMENTS = {
    "equation",
    "equation*",
    "align",
    "align*",
    "aligned",
    "gather",
    "gather*",
    "multline",
    "multline*",
    "displaymath",
    "table",
    "table*",
    "tabular",
    "tabular*",
}
_FORMAT_COMMANDS = re.compile(
    r"\\(?:textbf|textit|texttt|textrm|emph|underline|mathrm|mathbf|mathit|"
    r"operatorname|section|subsection|subsubsection|caption|title|author|date)\*?"
)
_REMOVE_COMMAND_WITH_ARGUMENT = re.compile(
    r"\\(?:documentclass|usepackage|includegraphics|label|cite|citep|citet|ref|pageref|url|href)"
    r"\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}"
)
_BEGIN_END_COMMAND = re.compile(r"\\(?:begin|end)\s*\{[^{}]*\}")
_COMMAND_NAME = re.compile(r"\\([A-Za-z@]+)\*?")


class ChunkingError(KnowledgeIngestionError):
    """Raised when a source unit cannot fit in a safe retrieval chunk."""


@dataclass(frozen=True)
class LatexChunk:
    """A retrieval-ready contiguous fragment from one source file and section."""

    raw_latex: str
    normalized_text: str
    section_path: tuple[str, ...]
    source_file: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class _Block:
    lines: tuple[LatexLine, ...]
    normalized_text: str


@dataclass(frozen=True)
class _AtomicGroup:
    lines: tuple[LatexLine, ...]
    protected: bool
    core_lines: tuple[LatexLine, ...] = ()
    leading_lines: tuple[LatexLine, ...] = ()
    trailing_lines: tuple[LatexLine, ...] = ()


def build_chunks(
    lines: Iterable[LatexLine],
    *,
    token_counter: TokenCounter,
    max_tokens: int = 450,
    overlap_tokens: int = 60,
) -> list[LatexChunk]:
    """Build bounded chunks without crossing a section or source-file boundary."""

    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if max_tokens > HARD_MAX_CHUNK_TOKENS:
        raise ValueError(f"max_tokens cannot exceed the hard {HARD_MAX_CHUNK_TOKENS}-token cap")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens cannot be negative")

    chunks: list[LatexChunk] = []
    for section_path, source_file, group in _structured_groups(list(lines)):
        blocks = _paragraph_blocks(group)
        split_blocks = [
            split_block
            for block in blocks
            for split_block in _split_oversized_block(block, token_counter, max_tokens)
        ]
        chunks.extend(
            _chunk_group(
                split_blocks,
                section_path=section_path,
                source_file=source_file,
                token_counter=token_counter,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
            )
        )
    return chunks


def normalize_latex(raw_latex: str) -> str:
    """Remove comments and layout syntax while retaining readable paper content."""

    text = "\n".join(_strip_comment(line) for line in raw_latex.splitlines())
    text = _REMOVE_COMMAND_WITH_ARGUMENT.sub(" ", text)
    text = _BEGIN_END_COMMAND.sub(" ", text)
    text = _FORMAT_COMMANDS.sub("", text)
    text = _COMMAND_NAME.sub(r" \1 ", text)
    text = text.replace("\\\\", " ")
    text = re.sub(r"[$&~{}]", " ", text)
    return " ".join(text.split())


def _structured_groups(
    lines: list[LatexLine],
) -> list[tuple[tuple[str, ...], str, list[LatexLine]]]:
    groups: list[tuple[tuple[str, ...], str, list[LatexLine]]] = []
    section_titles: list[str | None] = [None, None, None]
    in_abstract = False
    current_path: tuple[str, ...] = ("Preamble",)
    current_file: str | None = None
    current_lines: list[LatexLine] = []

    def flush() -> None:
        nonlocal current_lines
        if current_lines and current_file is not None:
            groups.append((current_path, current_file, current_lines))
        current_lines = []

    for line in lines:
        code = _code_before_comment(line.text) if line.structural else ""
        section_match = _read_section_command(code)
        is_abstract_begin = bool(_ABSTRACT_BEGIN.search(code))
        is_abstract_end = bool(_ABSTRACT_END.search(code))
        next_path = current_path
        if section_match:
            command, title = section_match
            level = {"section": 0, "subsection": 1, "subsubsection": 2}[command]
            section_titles[level] = _plain_title(title)
            for index in range(level + 1, len(section_titles)):
                section_titles[index] = None
            next_path = tuple(title for title in section_titles if title)
            in_abstract = False
        elif is_abstract_begin:
            next_path = ("Abstract",)
            in_abstract = True

        if current_file is not None and (line.source_file != current_file or next_path != current_path):
            flush()
        current_file = line.source_file
        current_path = next_path
        current_lines.append(line)
        if is_abstract_end and in_abstract:
            in_abstract = False
            flush()
            current_path = ("Preamble",)
            current_file = None
    flush()
    return groups


def _read_section_command(code: str) -> tuple[str, str] | None:
    match = _SECTION_COMMAND.search(code)
    if match is None:
        return None
    cursor = match.end()
    while cursor < len(code) and code[cursor].isspace():
        cursor += 1
    if cursor < len(code) and code[cursor] == "[":
        _, cursor = _read_balanced_delimiter(code, cursor, "[", "]")
        if cursor is None:
            return None
        while cursor < len(code) and code[cursor].isspace():
            cursor += 1
    if cursor >= len(code) or code[cursor] != "{":
        return None
    title, _ = _read_balanced_delimiter(code, cursor, "{", "}")
    if title is None:
        return None
    return match.group(1), title


def _read_balanced_delimiter(
    text: str, opening: int, open_character: str, close_character: str
) -> tuple[str | None, int | None]:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == open_character and not _is_escaped_delimiter(text, index):
            depth += 1
        elif text[index] == close_character and not _is_escaped_delimiter(text, index):
            depth -= 1
            if depth == 0:
                return text[opening + 1:index], index + 1
    return None, None


def _is_escaped_delimiter(text: str, index: int) -> bool:
    count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        count += 1
        cursor -= 1
    return count % 2 == 1


def _paragraph_blocks(lines: list[LatexLine]) -> list[_Block]:
    blocks: list[_Block] = []
    current: list[LatexLine] = []
    protected_depth = 0
    for line in lines:
        current.append(line)
        code = _code_before_comment(line.text) if line.structural else ""
        protected_depth += sum(
            1
            for match in _ENVIRONMENT_BEGIN.finditer(code)
            if match.group(1).strip() in _PROTECTED_ENVIRONMENTS
        )
        protected_depth -= sum(
            1
            for match in _ENVIRONMENT_END.finditer(code)
            if match.group(1).strip() in _PROTECTED_ENVIRONMENTS
        )
        if not line.text.strip() and protected_depth == 0:
            blocks.append(_make_block(current))
            current = []
    if current:
        blocks.append(_make_block(current))
    return blocks


def _make_block(lines: list[LatexLine]) -> _Block:
    frozen_lines = tuple(lines)
    return _Block(frozen_lines, normalize_latex("\n".join(line.text for line in frozen_lines)))


def _split_oversized_block(
    block: _Block, token_counter: TokenCounter, max_tokens: int
) -> list[_Block]:
    if _count_tokens(token_counter, block.normalized_text) <= max_tokens:
        return [block]
    atoms = _sever_oversize_protected_neighbors(
        _atomic_line_groups(block.lines), token_counter, max_tokens
    )
    result: list[_Block] = []
    current: list[LatexLine] = []
    for atom in atoms:
        atom_lines = list(atom.lines)
        atom_block = _make_block(atom_lines)
        if atom.protected and _count_tokens(token_counter, atom_block.normalized_text) > max_tokens:
            raise ChunkingError(
                "protected atom exceeds the hard token limit; reduce the source formula or table"
            )
        candidate = _make_block([*current, *atom_lines])
        if current and _count_tokens(token_counter, candidate.normalized_text) > max_tokens:
            result.append(_make_block(current))
            current = atom_lines
        else:
            current.extend(atom_lines)
        current_block = _make_block(current)
        if _count_tokens(token_counter, current_block.normalized_text) > max_tokens:
            split_lines = _split_single_line(atom_lines[0], token_counter, max_tokens)
            if current[:-1]:
                result.append(_make_block(current[:-1]))
            result.extend(_make_block([line]) for line in split_lines[:-1])
            current = [split_lines[-1]]
    if current:
        result.append(_make_block(current))
    return result


def _atomic_line_groups(lines: tuple[LatexLine, ...]) -> list[_AtomicGroup]:
    groups: list[_AtomicGroup] = []
    protected_lines: list[LatexLine] = []
    active_kind: str | None = None
    environment_depth = 0
    for line in lines:
        code = _code_before_comment(line.text) if line.structural else ""
        if active_kind is not None:
            protected_lines.append(line)
            if active_kind == "environment":
                environment_depth += _environment_delta(code)
                closed = environment_depth <= 0
            else:
                closed = _closes_delimiter(code, active_kind)
            if closed:
                core_lines = tuple(protected_lines)
                groups.append(_AtomicGroup(core_lines, protected=True, core_lines=core_lines))
                protected_lines = []
                active_kind = None
                environment_depth = 0
            continue
        if _has_protected_environment_begin(code):
            protected_lines = [line]
            environment_depth = _environment_delta(code)
            if environment_depth <= 0:
                core_lines = tuple(protected_lines)
                groups.append(_AtomicGroup(core_lines, protected=True, core_lines=core_lines))
                protected_lines = []
            else:
                active_kind = "environment"
            continue
        delimiter = _opening_delimiter(code)
        if delimiter is not None:
            protected_lines = [line]
            if _delimiter_closes_on_same_line(code, delimiter):
                core_lines = tuple(protected_lines)
                groups.append(_AtomicGroup(core_lines, protected=True, core_lines=core_lines))
                protected_lines = []
            else:
                active_kind = delimiter
            continue
        groups.append(_AtomicGroup((line,), protected=False))
    if protected_lines:
        core_lines = tuple(protected_lines)
        groups.append(_AtomicGroup(core_lines, protected=True, core_lines=core_lines))
    return _merge_protected_neighbors(groups)


def _has_protected_environment_begin(code: str) -> bool:
    return any(
        match.group(1).strip() in _PROTECTED_ENVIRONMENTS
        for match in _ENVIRONMENT_BEGIN.finditer(code)
    )


def _environment_delta(code: str) -> int:
    begins = sum(
        1
        for match in _ENVIRONMENT_BEGIN.finditer(code)
        if match.group(1).strip() in _PROTECTED_ENVIRONMENTS
    )
    ends = sum(
        1
        for match in _ENVIRONMENT_END.finditer(code)
        if match.group(1).strip() in _PROTECTED_ENVIRONMENTS
    )
    return begins - ends


def _opening_delimiter(code: str) -> str | None:
    if r"\[" in code:
        return "bracket"
    if r"\(" in code:
        return "parenthesis"
    if _unescaped_double_dollar_count(code):
        return "dollars"
    return None


def _delimiter_closes_on_same_line(code: str, delimiter: str) -> bool:
    if delimiter == "bracket":
        return code.find(r"\]", code.find(r"\[") + 2) >= 0
    if delimiter == "parenthesis":
        return code.find(r"\)", code.find(r"\(") + 2) >= 0
    return _unescaped_double_dollar_count(code) >= 2


def _closes_delimiter(code: str, delimiter: str) -> bool:
    if delimiter == "bracket":
        return r"\]" in code
    if delimiter == "parenthesis":
        return r"\)" in code
    return _unescaped_double_dollar_count(code) % 2 == 1


def _unescaped_double_dollar_count(code: str) -> int:
    count = 0
    index = 0
    while index < len(code) - 1:
        if code[index:index + 2] != "$$":
            index += 1
            continue
        backslashes = 0
        cursor = index - 1
        while cursor >= 0 and code[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            count += 1
            index += 2
        else:
            index += 1
    return count


def _merge_protected_neighbors(groups: list[_AtomicGroup]) -> list[_AtomicGroup]:
    merged: list[_AtomicGroup] = []
    index = 0
    while index < len(groups):
        group = groups[index]
        if not group.protected:
            merged.append(group)
            index += 1
            continue
        leading_lines: tuple[LatexLine, ...] = ()
        trailing_lines: tuple[LatexLine, ...] = ()
        if merged and not merged[-1].protected and _has_content(merged[-1]):
            leading_lines = merged.pop().lines
        if index + 1 < len(groups) and not groups[index + 1].protected and _has_content(groups[index + 1]):
            trailing_lines = groups[index + 1].lines
            index += 1
        core_lines = group.core_lines or group.lines
        merged.append(
            _AtomicGroup(
                (*leading_lines, *core_lines, *trailing_lines),
                protected=True,
                core_lines=core_lines,
                leading_lines=leading_lines,
                trailing_lines=trailing_lines,
            )
        )
        index += 1
    return merged


def _sever_oversize_protected_neighbors(
    groups: list[_AtomicGroup], token_counter: TokenCounter, max_tokens: int
) -> list[_AtomicGroup]:
    separated: list[_AtomicGroup] = []
    for group in groups:
        if not group.protected or _count_tokens(
            token_counter, _make_block(list(group.lines)).normalized_text
        ) <= max_tokens:
            separated.append(group)
            continue
        core_lines = group.core_lines or group.lines
        core_block = _make_block(list(core_lines))
        if _count_tokens(token_counter, core_block.normalized_text) > max_tokens:
            raise ChunkingError(
                "protected atom exceeds the hard token limit; reduce the source formula or table"
            )
        if group.leading_lines:
            separated.append(_AtomicGroup(group.leading_lines, protected=False))
        separated.append(
            _AtomicGroup(core_lines, protected=True, core_lines=core_lines)
        )
        if group.trailing_lines:
            separated.append(_AtomicGroup(group.trailing_lines, protected=False))
    return separated


def _has_content(group: _AtomicGroup) -> bool:
    return any(line.text.strip() for line in group.lines)


def _split_single_line(line: LatexLine, token_counter: TokenCounter, max_tokens: int) -> list[LatexLine]:
    pieces = re.findall(r"\S+\s*", line.text)
    if not pieces:
        raise ChunkingError("a source line cannot fit in the configured token limit")
    result: list[LatexLine] = []
    current = ""
    for piece in pieces:
        candidate = current + piece
        if current and _count_tokens(token_counter, normalize_latex(candidate)) > max_tokens:
            result.append(LatexLine(current, line.source_file, line.line_number, line.structural))
            current = piece
        else:
            current = candidate
        if _count_tokens(token_counter, normalize_latex(current)) > max_tokens:
            raise ChunkingError("a single token is larger than the configured token limit")
    if current:
        result.append(LatexLine(current, line.source_file, line.line_number, line.structural))
    return result


def _chunk_group(
    blocks: list[_Block],
    *,
    section_path: tuple[str, ...],
    source_file: str,
    token_counter: TokenCounter,
    max_tokens: int,
    overlap_tokens: int,
) -> list[LatexChunk]:
    chunks: list[LatexChunk] = []
    current: list[_Block] = []
    for block in blocks:
        candidate = [*current, block]
        if current and _count_blocks(token_counter, candidate) > max_tokens:
            chunk = _make_chunk(current, section_path, source_file)
            if chunk.normalized_text:
                chunks.append(chunk)
            current = _tail_overlap(current, token_counter, overlap_tokens)
            while current and _count_blocks(token_counter, [*current, block]) > max_tokens:
                current.pop(0)
        current.append(block)
    if current:
        chunk = _make_chunk(current, section_path, source_file)
        if chunk.normalized_text:
            chunks.append(chunk)
    return chunks


def _tail_overlap(blocks: list[_Block], token_counter: TokenCounter, overlap_tokens: int) -> list[_Block]:
    if overlap_tokens == 0:
        return []
    selected: list[_Block] = []
    for block in reversed(blocks):
        candidate = [block, *selected]
        if _count_blocks(token_counter, candidate) > overlap_tokens:
            break
        selected = candidate
    return selected


def _make_chunk(
    blocks: list[_Block], section_path: tuple[str, ...], source_file: str
) -> LatexChunk:
    lines = [line for block in blocks for line in block.lines]
    raw_latex = "\n".join(line.text for line in lines)
    return LatexChunk(
        raw_latex=raw_latex,
        normalized_text=normalize_latex(raw_latex),
        section_path=section_path,
        source_file=source_file,
        start_line=lines[0].line_number,
        end_line=lines[-1].line_number,
    )


def _count_blocks(token_counter: TokenCounter, blocks: list[_Block]) -> int:
    return _count_tokens(token_counter, "\n".join(block.normalized_text for block in blocks))


def _count_tokens(token_counter: TokenCounter, text: str) -> int:
    count = token_counter(text)
    if count < 0:
        raise ValueError("token_counter cannot return a negative value")
    return count


def _plain_title(value: str) -> str:
    return normalize_latex(value) or "Untitled"


def _code_before_comment(text: str) -> str:
    return _strip_comment(text)


def _strip_comment(text: str) -> str:
    for index, character in enumerate(text):
        if character != "%":
            continue
        backslashes = 0
        cursor = index - 1
        while cursor >= 0 and text[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            return text[:index]
    return text
