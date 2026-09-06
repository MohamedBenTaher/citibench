"""Load Citebench config.yaml plus process environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "/app/config.yaml"))
DEFAULT_CORPUS_DIR = Path(os.environ.get("CORPUS_DIR", "/app/corpus"))


def _repo_root() -> Path | None:
    """apps/api/settings.py → repo root. None when the image has no extra parents."""
    parts = Path(__file__).resolve().parents
    if len(parts) > 2:
        return parts[2]
    return None


_REPO_ROOT = _repo_root()
_LOCAL_CONFIG = (_REPO_ROOT / "config.yaml") if _REPO_ROOT else None
_LOCAL_CORPUS = (_REPO_ROOT / "corpus") if _REPO_ROOT else None

GROQ_KEY_HELP = (
    "GROQ_API_KEY is not set. Citebench C2 embeddings use only Groq's "
    "OpenAI-compatible API (model nomic-embed-text-v1.5). Export the key "
    "(https://console.groq.com/keys) or pass it into Compose as GROQ_API_KEY. "
    "Do not configure a second embed provider."
)


@dataclass(frozen=True)
class Settings:
    provider: str
    embed_model: str
    embed_dimensions: int
    embed_api_base: str
    embed_document_prefix: str
    chunk_size: int
    chunk_overlap: int
    tokenizer: str
    database_url: str
    corpus_dir: Path
    manifest_path: Path
    groq_api_key: str


def _resolve_config_path() -> Path:
    if DEFAULT_CONFIG_PATH.is_file():
        return DEFAULT_CONFIG_PATH
    if _LOCAL_CONFIG is not None and _LOCAL_CONFIG.is_file():
        return _LOCAL_CONFIG
    raise FileNotFoundError(
        f"config.yaml not found at {DEFAULT_CONFIG_PATH} or {_LOCAL_CONFIG}"
    )


def _resolve_corpus_dir() -> Path:
    if DEFAULT_CORPUS_DIR.is_dir():
        return DEFAULT_CORPUS_DIR
    if _LOCAL_CORPUS is not None and _LOCAL_CORPUS.is_dir():
        return _LOCAL_CORPUS
    raise FileNotFoundError(
        f"corpus dir not found at {DEFAULT_CORPUS_DIR} or {_LOCAL_CORPUS}"
    )


def load_settings() -> Settings:
    raw = yaml.safe_load(_resolve_config_path().read_text(encoding="utf-8")) or {}
    corpus_dir = _resolve_corpus_dir()
    return Settings(
        provider=str(raw.get("provider", "groq")),
        embed_model=str(raw.get("embed_model", "nomic-embed-text-v1.5")),
        embed_dimensions=int(raw.get("embed_dimensions", 768)),
        embed_api_base=str(
            os.environ.get("GROQ_API_BASE")
            or raw.get("embed_api_base")
            or "https://api.groq.com/openai/v1"
        ).rstrip("/"),
        embed_document_prefix=str(raw.get("embed_document_prefix", "search_document: ")),
        chunk_size=int(raw.get("chunk_size", 512)),
        chunk_overlap=int(raw.get("chunk_overlap", 64)),
        tokenizer=str(raw.get("tokenizer", "cl100k_base")),
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql://citebench:citebench@127.0.0.1:5432/citebench",
        ),
        corpus_dir=corpus_dir,
        manifest_path=corpus_dir / "MANIFEST.md",
        groq_api_key=os.environ.get("GROQ_API_KEY", "").strip(),
    )


def require_groq_key(settings: Settings) -> str:
    if not settings.groq_api_key:
        raise RuntimeError(GROQ_KEY_HELP)
    return settings.groq_api_key
