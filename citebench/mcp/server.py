"""stdio JSON-RPC MCP with exactly two tools: search_corpus, get_trace."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Literal, assert_never

from citebench.mcp.client import (
    ApiError,
    CitebenchApi,
    UnreachableError,
    api_from_env,
    api_url_from_env,
)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "citebench"
SERVER_VERSION = "0.9.0"
TOOL_SEARCH = "search_corpus"
TOOL_TRACE = "get_trace"
ToolName = Literal["search_corpus", "get_trace"]

TOOLS: list[dict[str, Any]] = [
    {
        "name": TOOL_SEARCH,
        "description": (
            "Hybrid retrieve over the frozen Citebench corpus "
            "(dense + FTS, RRF k=60, FlashRank top-8). Wraps POST /retrieve."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": TOOL_TRACE,
        "description": (
            "Fetch one C5 RunTrace from the local store by run_id, "
            "or by langfuse_trace_id when that id is present on the run. "
            "Wraps GET /traces/{id}."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Citebench run_id or Langfuse trace id",
                }
            },
            "required": ["run_id"],
            "additionalProperties": False,
        },
    },
]


def handle_rpc(message: dict[str, Any], api: CitebenchApi) -> dict[str, Any] | None:
    """Handle one JSON-RPC message. Notifications return None."""
    method = message.get("method")
    req_id = message.get("id")
    if not isinstance(method, str):
        return _rpc_error(req_id, -32600, "Invalid Request: method required")
    if req_id is None:
        return None
    params = message.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _rpc_error(req_id, -32602, "Invalid params")

    match method:
        case "initialize":
            return _ok(req_id, _initialize_result(params))
        case "tools/list":
            return _ok(req_id, {"tools": list(TOOLS)})
        case "tools/call":
            return _ok(req_id, _call_tool(params, api))
        case "ping":
            return _ok(req_id, {})
        case _:
            return _rpc_error(req_id, -32601, f"Method not found: {method}")


def serve_stdio(api: CitebenchApi | None = None) -> None:
    client = api if api is not None else api_from_env()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(
                json.dumps(_rpc_error(None, -32700, f"Parse error: {exc}")) + "\n"
            )
            sys.stdout.flush()
            continue
        if not isinstance(message, dict):
            sys.stdout.write(
                json.dumps(_rpc_error(None, -32600, "Invalid Request")) + "\n"
            )
            sys.stdout.flush()
            continue
        reply = handle_rpc(message, client)
        if reply is None:
            continue
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m citebench.mcp")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Exercise tools/list plus both tools (fake API, or --live)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="With --smoke, call the Compose API at CITEBENCH_API_URL",
    )
    args = parser.parse_args(argv)
    if args.live and not args.smoke:
        parser.error("--live requires --smoke")
    if args.smoke:
        return run_smoke(live=args.live)
    serve_stdio()
    return 0


def run_smoke(*, live: bool = False, api: CitebenchApi | None = None) -> int:
    """Protocol check. ``--live`` also hits the running API."""
    if api is None:
        api = api_from_env() if live else CitebenchApi(_SmokeTransport())
    if live:
        try:
            health = api.health()
        except (ApiError, UnreachableError) as exc:
            print(
                f"API not reachable ({api_url_from_env()}): {exc}\n"
                "Start the Compose stack, then retry:\n"
                "  docker compose up --build\n"
                "  python -m citebench.mcp --smoke --live",
                file=sys.stderr,
            )
            return 2
        print(f"health={health}")

    listed = handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, api)
    assert listed is not None
    names = [tool["name"] for tool in listed["result"]["tools"]]
    if names != [TOOL_SEARCH, TOOL_TRACE]:
        print(f"unexpected tools: {names}", file=sys.stderr)
        return 1
    print(f"tools={names}")

    search = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": TOOL_SEARCH,
                "arguments": {"query": "how does the kube-scheduler place pods"},
            },
        },
        api,
    )
    assert search is not None
    print(f"search_corpus isError={_is_error(search)} keys={_result_keys(search)}")

    missing = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": TOOL_TRACE, "arguments": {"run_id": "smoke-missing"}},
        },
        api,
    )
    assert missing is not None
    print(f"get_trace(missing) isError={_is_error(missing)}")
    print("smoke ok")
    return 0


def _initialize_result(params: dict[str, Any]) -> dict[str, Any]:
    requested = params.get("protocolVersion")
    version = requested if isinstance(requested, str) and requested else PROTOCOL_VERSION
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "instructions": (
            "Citebench MCP. Two tools only: search_corpus (hybrid retrieve) "
            "and get_trace (C5 RunTrace by run_id or langfuse_trace_id). "
            "Not a marketplace and not extra connectors."
        ),
    }


def _call_tool(params: dict[str, Any], api: CitebenchApi) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(name, str) or not name:
        return _tool_error("tool name is required")
    if not isinstance(arguments, dict):
        return _tool_error("arguments must be an object")
    try:
        tool = _tool_name(name)
    except ValueError:
        return _tool_error(
            f"unknown tool {name!r}; this server exposes only "
            f"{TOOL_SEARCH} and {TOOL_TRACE}"
        )
    try:
        payload = _dispatch(tool, arguments, api)
    except (ApiError, UnreachableError, ValueError) as exc:
        return _tool_error(str(exc))
    return _tool_text(json.dumps(payload, default=str))


def _dispatch(name: ToolName, arguments: dict[str, Any], api: CitebenchApi) -> dict[str, Any]:
    match name:
        case "search_corpus":
            query = arguments.get("query")
            if not isinstance(query, str):
                raise ValueError("search_corpus requires string argument 'query'")
            return api.retrieve(query)
        case "get_trace":
            run_id = arguments.get("run_id")
            if not isinstance(run_id, str) or not run_id.strip():
                raise ValueError("get_trace requires string argument 'run_id'")
            return api.get_trace(run_id.strip())
        case _:
            assert_never(name)


def _tool_name(name: str) -> ToolName:
    if name == TOOL_SEARCH:
        return "search_corpus"
    if name == TOOL_TRACE:
        return "get_trace"
    raise ValueError(name)


def _tool_text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _tool_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _ok(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _is_error(reply: dict[str, Any]) -> bool:
    result = reply.get("result")
    return isinstance(result, dict) and bool(result.get("isError"))


def _result_keys(reply: dict[str, Any]) -> list[str]:
    result = reply.get("result")
    if not isinstance(result, dict):
        return []
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return []
    first = content[0]
    if not isinstance(first, dict):
        return []
    text = first.get("text")
    if not isinstance(text, str):
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    return list(payload) if isinstance(payload, dict) else []


class _SmokeTransport:
    """In-process stand-in so ``--smoke`` does not need Compose."""

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        if method == "GET" and path == "/health":
            return 200, {"status": "ok"}
        if method == "POST" and path == "/retrieve":
            query = (json_body or {}).get("query", "")
            return 200, {"hits": [], "rerank_skipped": False, "query": query}
        if method == "GET" and path.startswith("/traces/"):
            return 404, {"detail": "trace not found: smoke-missing"}
        return 404, {"detail": f"not found: {method} {path}"}
