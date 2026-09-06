from pathlib import Path

import pytest

import embed
from embed import EmbedError, _vectors_from_payload
from settings import Settings


def test_vectors_from_payload_enforces_768d() -> None:
    payload = {
        "data": [
            {"index": 1, "embedding": [0.0] * 768},
            {"index": 0, "embedding": [1.0] * 768},
        ]
    }
    vectors = _vectors_from_payload(payload, 768, 2)
    assert vectors[0][0] == 1.0
    assert vectors[1][0] == 0.0
    assert len(vectors[0]) == 768


def test_vectors_from_payload_rejects_wrong_dimension() -> None:
    payload = {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}
    with pytest.raises(EmbedError, match="768"):
        _vectors_from_payload(payload, 768, 1)


def test_embed_query_uses_search_query_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_embed_texts(texts, settings, *, batch_size=32, prefix=None):
        captured["texts"] = texts
        captured["prefix"] = prefix
        return [[0.1] * settings.embed_dimensions]

    monkeypatch.setattr(embed, "embed_texts", fake_embed_texts)
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
        groq_api_key="gsk_test",
    )
    vector = embed.embed_query("pods onto nodes", settings)
    assert captured["texts"] == ["pods onto nodes"]
    assert captured["prefix"] == "search_query: "
    assert len(vector) == 768
