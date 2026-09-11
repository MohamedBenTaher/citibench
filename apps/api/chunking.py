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
    section: str | None = None


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
    """Split on headings / page marks, then apply the 512/64 window per section.

    Each produced chunk carries the nearest heading path (e.g. ``A > B``) as
    ``section``; PDF page markers become the section label when no heading is
    active.
    """
    sections = _sections(text)
    if len(sections) <= 1:
        section = sections[0][0] if sections else None
        return [
            TextChunk(
                index=piece.index,
                text=piece.text,
                token_count=piece.token_count,
                start_token=piece.start_token,
                section=section,
            )
            for piece in chunk_text(
                text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                tokenizer=tokenizer,
            )
        ]
    pieces: list[TextChunk] = []
    index = 0
    start_token = 0
    for section_path, section in sections:
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
                    section=section_path,
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


def _sections(text: str) -> list[tuple[str | None, str]]:
    """Return (heading_path, body) blocks split on ``#`` headings / ``[page N]``."""
    parts: list[tuple[str | None, str]] = []
    buf: list[str] = []
    stack: list[tuple[int, str]] = []

    def current_section() -> str | None:
        return " > ".join(title for _level, title in stack) or None

    def flush() -> None:
        body = "".join(buf).strip()
        if body:
            parts.append((current_section(), body))

    for line in (text or "").splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            flush()
            buf.clear()
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped.lstrip("#").strip()
            stack[:] = [item for item in stack if item[0] < level]
            stack.append((level, title))
            buf.append(line)
        elif stripped.startswith("[page "):
            flush()
            buf.clear()
            label = stripped.split("]", 1)[0].lstrip("[") if "]" in stripped else stripped.strip()
            if not stack or stack[-1][0] == 0:
                stack[:] = [(0, label)]
            buf.append(line)
        else:
            buf.append(line)
    flush()
    return parts

