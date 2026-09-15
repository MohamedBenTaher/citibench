from pathlib import Path

import pytest

from citebench_api.retrieval import embed as embed
from citebench_api.retrieval.embed import EmbedError, _vectors_from_payload
from citebench_api.config import Settings


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


def _settings(
    *,
    groq_api_key: str = "gsk_test",
    api_base: str = "https://api.groq.com/openai/v1",
    embed_backend: str = "groq_then_local",
) -> Settings:
    return Settings(
        provider="groq",
        embed_model="nomic-embed-text-v1.5",
        embed_dimensions=768,
        embed_api_base=api_base,
        embed_document_prefix="search_document: ",
        chunk_size=512,
        chunk_overlap=64,
        tokenizer="cl100k_base",
        database_url="postgresql://citebench:citebench@127.0.0.1:5432/citebench",
        corpus_dir=Path("."),
        manifest_path=Path("MANIFEST.md"),
        groq_api_key=groq_api_key,
        embed_backend=embed_backend,
    )


class _FakeResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        raise AssertionError("404 responses must not be parsed")


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.posts: list[dict[str, object]] = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def post(self, url: str, headers: dict, json: dict) -> _FakeResponse:
        self.posts.append({"url": url, "json": json})
        return self._response


def test_model_candidates_include_underscore_alias() -> None:
    assert embed._model_candidates("nomic-embed-text-v1.5") == [
        "nomic-embed-text-v1.5",
        "nomic-embed-text-v1_5",
    ]


def test_groq_model_not_found_falls_back_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    embed.reset_embed_cache()
    fake = _FakeClient(
        _FakeResponse(
            404,
            '{"error":{"message":"The model `nomic-embed-text-v1_5` does not exist or you do not have access to it.","type":"invalid_request_error","code":"model_not_found"}}',
        )
    )
    monkeypatch.setattr(embed.httpx, "Client", lambda **_kwargs: fake)
    monkeypatch.setattr(
        embed,
        "_embed_local",
        lambda texts, dims, batch_size=32: [[0.25] * dims for _ in texts],
    )
    vectors = embed.embed_texts(["a pod is a deployable unit"], _settings())
    assert len(vectors) == 1
    assert len(vectors[0]) == 768
    assert fake.posts
    assert fake.posts[0]["json"]["model"] == "nomic-embed-text-v1.5"


def test_custom_embed_host_404_does_not_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    embed.reset_embed_cache()
    fake = _FakeClient(_FakeResponse(404, '{"error":{"code":"model_not_found"}}'))
    monkeypatch.setattr(embed.httpx, "Client", lambda **_kwargs: fake)

    def boom(*_args, **_kwargs):
        raise AssertionError("local fallback must not run for a custom embed host")

    monkeypatch.setattr(embed, "_embed_local", boom)
    with pytest.raises(EmbedError, match="404"):
        embed.embed_texts(
            ["hello"],
            _settings(api_base="http://127.0.0.1:9/openai/v1"),
        )


def test_local_backend_skips_groq_even_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    embed.reset_embed_cache()

    def boom(*_args, **_kwargs):
        raise AssertionError("groq must not be called")

    monkeypatch.setattr(embed, "_embed_via_groq", boom)
    monkeypatch.setattr(
        embed,
        "_embed_local",
        lambda texts, dims, batch_size=32: [[0.75] * dims for _ in texts],
    )
    vectors = embed.embed_texts(["hello"], _settings(embed_backend="local"))
    assert len(vectors) == 1
    assert len(vectors[0]) == 768
    assert vectors[0][0] == 0.75


def test_no_groq_key_uses_local(monkeypatch: pytest.MonkeyPatch) -> None:
    embed.reset_embed_cache()

    def fake_local(texts, dims, batch_size=32):
        assert texts == ["search_document: hello"]
        return [[0.5] * dims]

    monkeypatch.setattr(embed, "_embed_local", fake_local)
    vectors = embed.embed_texts(["hello"], _settings(groq_api_key=""))
    assert vectors[0][0] == 0.5
