import pytest

import chat
from chat import ChatError, groq_chat
from test_generate import make_settings


@pytest.fixture(autouse=True)
def _reset_http_client() -> None:
    chat.reset_http_client()


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
        self.post_count = 0

    def post(self, _url: str, headers: dict, json: dict) -> _FakeResponse:
        del headers
        self.post_count += 1
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
    monkeypatch.setattr(chat, "_get_http_client", lambda: fake)
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

    monkeypatch.setattr(chat, "_get_http_client", lambda: AuthClient())
    with pytest.raises(ChatError, match="401"):
        groq_chat([{"role": "user", "content": "pods"}], make_settings())


def test_groq_chat_reuses_client(monkeypatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(chat, "_get_http_client", lambda: fake)
    settings = make_settings()
    messages = [{"role": "user", "content": "pods"}]
    groq_chat(messages, settings)
    groq_chat(messages, settings)
    assert fake.post_count == 2
