"""Token-window chunking: 512 tokens / 64 overlap, tiktoken cl100k_base.

The tokenizer is documented in config.yaml (`tokenizer: cl100k_base`). Encoding
and decoding stay in tiktoken so the same source text always yields the same
chunk boundaries on re-index. This is not the nomic sentencepiece vocab; Groq
still embeds each chunk with nomic-embed-text-v1.5.
"""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken

# Defaults match config.yaml / DECISIONS.md. Tests import these names.
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
DEFAULT_TOKENIZER = "cl100k_base"


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    token_count: int
    start_token: int


def encoding_for(name: str = DEFAULT_TOKENIZER) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    tokenizer: str = DEFAULT_TOKENIZER,
) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and < chunk_size")

    enc = encoding_for(tokenizer)
    tokens = enc.encode(text)
    if not tokens:
        return []

    stride = chunk_size - chunk_overlap
    chunks: list[TextChunk] = []
    start = 0
    index = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        piece = enc.decode(tokens[start:end])
        chunks.append(
            TextChunk(
                index=index,
                text=piece,
                token_count=end - start,
                start_token=start,
            )
        )
        if end == len(tokens):
            break
        start += stride
        index += 1
    return chunks


def chunk_text_dynamic(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    tokenizer: str = DEFAULT_TOKENIZER,
) -> list[TextChunk]:
    """Split on headings / page marks, then apply the 512/64 window per section."""
    sections = _sections(text)
    if len(sections) <= 1:
        return chunk_text(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            tokenizer=tokenizer,
        )
    pieces: list[TextChunk] = []
    index = 0
    start_token = 0
    for section in sections:
        for piece in chunk_text(
            section,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            tokenizer=tokenizer,
        ):
            pieces.append(
                TextChunk(
                    index=index,
                    text=piece.text,
                    token_count=piece.token_count,
                    start_token=start_token,
                )
            )
            start_token += piece.token_count
            index += 1
    if not pieces:
        return chunk_text(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            tokenizer=tokenizer,
        )
    return pieces


def _sections(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for line in (text or "").splitlines(keepends=True):
        stripped = line.lstrip()
        boundary = stripped.startswith("#") or stripped.startswith("[page ")
        if boundary and buf:
            parts.append("".join(buf).strip())
            buf = [line]
        else:
            buf.append(line)
    if buf:
        parts.append("".join(buf).strip())
    return [part for part in parts if part]

