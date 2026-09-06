import pytest

from chat import ChatError, groq_chat
from test_generate import make_settings


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        if self._payload is None:
            raise AssertionError("error responses must not be parsed")
        return self._payload


class _FakeClient:
    def __init__(self) -> None:
        self.models: list[str] = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def post(self, _url: str, headers: dict, json: dict) -> _FakeResponse:
        del headers
        model = str(json["model"])
        self.models.append(model)
        if model == "llama-3.1-8b-instant":
            return _FakeResponse(
                404,
                text='{"error":{"message":"The model `llama-3.1-8b-instant` does not exist","code":"model_not_found"}}',
            )
        return _FakeResponse(
            200,
            payload={
                "choices": [{"message": {"content": '{"abstain": true, "answer": "I don\'t know"}'}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            },
        )


def test_chat_candidates_include_gpt_oss_fallback() -> None:
    from chat import _chat_candidates

    assert _chat_candidates("llama-3.1-8b-instant") == [
        "llama-3.1-8b-instant",
        "openai/gpt-oss-20b",
    ]
    assert _chat_candidates("openai/gpt-oss-20b") == ["openai/gpt-oss-20b"]


def test_retired_llama_falls_back_to_gpt_oss(monkeypatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr("chat.httpx.Client", lambda **_kwargs: fake)
    result = groq_chat(
        [{"role": "user", "content": "pods"}],
        make_settings(chat_model="llama-3.1-8b-instant"),
    )
    assert fake.models == ["llama-3.1-8b-instant", "openai/gpt-oss-20b"]
    assert result.completion_tokens == 2


def test_401_does_not_fallback(monkeypatch) -> None:
    class AuthClient(_FakeClient):
        def post(self, _url: str, headers: dict, json: dict) -> _FakeResponse:
            del headers, json
            return _FakeResponse(401, text="unauthorized")

    monkeypatch.setattr("chat.httpx.Client", lambda **_kwargs: AuthClient())
    with pytest.raises(ChatError, match="401"):
        groq_chat([{"role": "user", "content": "pods"}], make_settings())
