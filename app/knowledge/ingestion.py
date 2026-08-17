"""End-to-end local parsing of a paper into retrieval chunks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from app.knowledge.chunking import LatexChunk, TokenCounter, build_chunks
from app.knowledge.latex import ParseBudget, parse_latex
from app.knowledge.manifest import PaperManifest
from app.knowledge.source import open_paper_source


E5_TOKENIZER_MODEL = "intfloat/multilingual-e5-large"
MAX_CHUNK_TOKENS = 450
CHUNK_OVERLAP_TOKENS = 60


@dataclass(frozen=True)
class PaperDocument:
    """Validated paper metadata and its structured local source chunks."""

    manifest: PaperManifest
    chunks: tuple[LatexChunk, ...]


class E5TokenCounter:
    """Lazily count tokens with the tokenizer paired with the dense E5 model."""

    def __init__(self, model_name: str = E5_TOKENIZER_MODEL) -> None:
        self.model_name = model_name
        self._tokenizer = None
        self._lock = Lock()

    def __call__(self, text: str) -> int:
        with self._lock:
            return len(self._get_tokenizer().encode(text).ids)

    def _get_tokenizer(self):
        if self._tokenizer is None:
            try:
                from tokenizers import Tokenizer
            except ImportError as exc:
                raise RuntimeError(
                    "tokenizers is required to chunk papers with multilingual-e5-large"
                ) from exc
            self._tokenizer = Tokenizer.from_pretrained(self.model_name)
        return self._tokenizer


DEFAULT_TOKEN_COUNTER = E5TokenCounter()


def load_paper_document(
    source_path: str | Path,
    *,
    token_counter: TokenCounter | None = None,
    dense_model: str = E5_TOKENIZER_MODEL,
) -> PaperDocument:
    """Safely load a local source and return chunks without loading an embedding model."""

    counter = token_counter
    if counter is None:
        counter = DEFAULT_TOKEN_COUNTER if dense_model == E5_TOKENIZER_MODEL else E5TokenCounter(dense_model)
    with open_paper_source(source_path) as source:
        chunks = build_chunks(
            parse_latex(source, budget=ParseBudget()),
            token_counter=counter,
            max_tokens=MAX_CHUNK_TOKENS,
            overlap_tokens=CHUNK_OVERLAP_TOKENS,
        )
        return PaperDocument(manifest=source.manifest, chunks=tuple(chunks))
