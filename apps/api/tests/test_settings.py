from pathlib import Path

import pytest

from settings import GROQ_KEY_HELP, Settings, require_groq_key


def test_require_groq_key_fails_clearly() -> None:
    settings = Settings(
        provider="groq",
        embed_model="nomic-embed-text-v1.5",
        embed_dimensions=768,
        embed_api_base="https://api.groq.com/openai/v1",
        embed_document_prefix="search_document: ",
        chunk_size=512,
        chunk_overlap=64,
        tokenizer="cl100k_base",
        database_url="postgresql://citebench:citebench@127.0.0.1:5432/citebench",
        corpus_dir=Path("."),
        manifest_path=Path("MANIFEST.md"),
        groq_api_key="",
    )
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        require_groq_key(settings)
    assert "console.groq.com/keys" in GROQ_KEY_HELP
    assert "second embed provider" in GROQ_KEY_HELP
