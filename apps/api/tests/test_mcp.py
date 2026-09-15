"""C9: exactly two MCP tools over retrieve + the C5 trace store."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import main as main_mod
from citebench.mcp.client import ApiError, CitebenchApi
from citebench.mcp.server import TOOLS, handle_rpc, run_smoke, serve_stdio
from citebench_api.retrieval.retrieve import ChunkHit
from test_trace import FakePoster, valid_trace
from citebench_api.tracing.trace import emit_trace


class StarletteTransport:
    def __init__(self, client: TestClient) -> None:
        self._client = client

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        response = self._client.request(method, path, json=json_body)
        try:
            payload: Any = response.json()
        except ValueError:
            payload = {"detail": response.text}
        return response.status_code, payload


def _api(monkeypatch, retrieve_hits: list[ChunkHit] | None = None) -> CitebenchApi:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    if retrieve_hits is not None:

        def fake_retrieve(query: str, *args, **kwargs):
            return list(retrieve_hits)

        monkeypatch.setattr("citebench_api.routes.ask.retrieve", fake_retrieve)
    return CitebenchApi(StarletteTransport(TestClient(main_mod.app)))


def _call(api: CitebenchApi, name: str, arguments: dict[str, Any], *, req_id: int = 1) -> dict[str, Any]:
    reply = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        api,
    )
    assert reply is not None
    return reply


def _payload(reply: dict[str, Any]) -> Any:
    text = reply["result"]["content"][0]["text"]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def test_tools_list_is_exactly_two() -> None:
    names = [tool["name"] for tool in TOOLS]
    assert names == ["search_corpus", "get_trace"]
    reply = handle_rpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        CitebenchApi(StarletteTransport(TestClient(main_mod.app))),
    )
    assert reply is not None
    listed = [tool["name"] for tool in reply["result"]["tools"]]
    assert listed == ["search_corpus", "get_trace"]
    assert "marketplace" not in json.dumps(reply).lower()


def test_initialize_and_notification() -> None:
    api = CitebenchApi(StarletteTransport(TestClient(main_mod.app)))
    init = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        },
        api,
    )
    assert init is not None
    assert init["result"]["serverInfo"]["name"] == "citebench"
    assert init["result"]["capabilities"]["tools"] == {"listChanged": False}
    note = handle_rpc(
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        api,
    )
    assert note is None


def test_search_corpus_wraps_retrieve(monkeypatch) -> None:
    hits = [
        ChunkHit(
            chunk_id="k8s-scheduler:0",
            doc_id="k8s-scheduler",
            score=0.42,
            rank=1,
            rerank_skipped=False,
            text="kube-scheduler filters and scores nodes.",
            fused_score=0.03,
            rerank_score=0.42,
        )
    ]
    api = _api(monkeypatch, hits)
    reply = _call(api, "search_corpus", {"query": "how does the kube-scheduler place pods"})
    assert reply["result"].get("isError") is not True
    body = _payload(reply)
    assert body["hits"][0]["chunk_id"] == "k8s-scheduler:0"
    assert body["hits"][0]["rank"] == 1
    assert body["rerank_skipped"] is False


def test_search_corpus_blank_query(monkeypatch) -> None:
    api = _api(monkeypatch, [])
    reply = _call(api, "search_corpus", {"query": "   "})
    assert reply["result"].get("isError") is not True
    assert _payload(reply)["hits"] == []


def test_search_corpus_without_groq_key(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setattr("citebench_api.routes.ask.retrieve", lambda *_args, **_kwargs: [])
    api = CitebenchApi(StarletteTransport(TestClient(main_mod.app)))
    reply = _call(api, "search_corpus", {"query": "pods"})
    assert reply["result"].get("isError") is not True
    assert _payload(reply)["hits"] == []


def test_get_trace_by_run_id(monkeypatch) -> None:
    emit_trace(valid_trace(run_id="run-mcp"))
    api = _api(monkeypatch, [])
    reply = _call(api, "get_trace", {"run_id": "run-mcp"})
    assert reply["result"].get("isError") is not True
    body = _payload(reply)
    assert body["run_id"] == "run-mcp"
    assert body["query"].startswith("how does the kube-scheduler")
    kinds = [span["kind"] for span in body["spans"]]
    assert kinds[:2] == ["retrieve", "rerank"]


def test_get_trace_by_langfuse_id(monkeypatch) -> None:
    emit_trace(valid_trace(run_id="run-lf-mcp"), poster=FakePoster(trace_id="lf-mcp-9"))
    api = _api(monkeypatch, [])
    reply = _call(api, "get_trace", {"run_id": "lf-mcp-9"})
    assert reply["result"].get("isError") is not True
    body = _payload(reply)
    assert body["run_id"] == "run-lf-mcp"
    assert body["langfuse_trace_id"] == "lf-mcp-9"


def test_get_trace_missing(monkeypatch) -> None:
    api = _api(monkeypatch, [])
    reply = _call(api, "get_trace", {"run_id": "does-not-exist"})
    assert reply["result"]["isError"] is True
    assert "not found" in reply["result"]["content"][0]["text"]


def test_unknown_tool_is_error(monkeypatch) -> None:
    api = _api(monkeypatch, [])
    reply = _call(api, "browse_marketplace", {"q": "no"})
    assert reply["result"]["isError"] is True
    assert "search_corpus" in reply["result"]["content"][0]["text"]
    assert "get_trace" in reply["result"]["content"][0]["text"]


def test_unknown_rpc_method() -> None:
    api = CitebenchApi(StarletteTransport(TestClient(main_mod.app)))
    reply = handle_rpc({"jsonrpc": "2.0", "id": 9, "method": "resources/list"}, api)
    assert reply is not None
    assert reply["error"]["code"] == -32601


def test_search_corpus_rejects_non_string_query(monkeypatch) -> None:
    api = _api(monkeypatch, [])
    reply = _call(api, "search_corpus", {"query": 12})
    assert reply["result"]["isError"] is True


def test_http_client_maps_404() -> None:
    class Boom:
        def request(self, method, path, *, json_body=None):
            return 404, {"detail": "trace not found: x"}

    api = CitebenchApi(Boom())
    try:
        api.get_trace("x")
    except ApiError as exc:
        assert exc.status_code == 404
        assert "not found" in exc.detail
    else:
        raise AssertionError("expected ApiError")


def test_protocol_smoke_ok() -> None:
    assert run_smoke(live=False) == 0


def test_live_smoke_against_test_client(monkeypatch) -> None:
    emit_trace(valid_trace(run_id="run-smoke-live"))
    api = _api(monkeypatch, [])
    assert run_smoke(live=True, api=api) == 0


def test_stdio_tools_list_roundtrip(monkeypatch) -> None:
    stdin = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n")
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    serve_stdio(_api(monkeypatch, []))
    reply = json.loads(stdout.getvalue().strip().splitlines()[-1])
    assert [tool["name"] for tool in reply["result"]["tools"]] == [
        "search_corpus",
        "get_trace",
    ]


def test_tool_schemas_required_fields() -> None:
    by_name = {tool["name"]: tool for tool in TOOLS}
    assert by_name["search_corpus"]["inputSchema"]["required"] == ["query"]
    assert by_name["get_trace"]["inputSchema"]["required"] == ["run_id"]
    assert "marketplace" not in json.dumps(TOOLS).lower()


def test_readme_has_no_platform_creep() -> None:
    readme = Path(__file__).resolve().parents[3] / "README.md"
    text = readme.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "dify" not in lowered
    assert "agent catalog" not in lowered
    assert "docs/mcp.md" in text
    assert "search_corpus" in text
    assert "get_trace" in text
