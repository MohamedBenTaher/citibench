"""HTTP read client for the Compose API (retrieve + traces)."""

from __future__ import annotations

import os
from typing import Any, Protocol
from urllib.parse import quote

import httpx

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_TIMEOUT_S = 120.0


class Transport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]: ...


class ApiError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class UnreachableError(Exception):
    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"Citebench API unreachable at {url}: {reason}")
        self.url = url
        self.reason = reason


class HttpxTransport:
    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT_S) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(method, url, json=json_body)
        except httpx.HTTPError as exc:
            raise UnreachableError(self.base_url, str(exc)) from exc
        try:
            payload: Any = response.json()
        except ValueError:
            payload = {"detail": response.text}
        return response.status_code, payload


class CitebenchApi:
    """Thin read API over ``POST /retrieve`` and ``GET /traces/{id}``."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def retrieve(self, query: str) -> dict[str, Any]:
        status, payload = self._transport.request(
            "POST", "/retrieve", json_body={"query": query}
        )
        if status >= 400:
            raise ApiError(status, _detail(payload, f"retrieve failed ({status})"))
        if not isinstance(payload, dict):
            raise ApiError(500, "retrieve response must be an object")
        return payload

    def get_trace(self, run_id: str) -> dict[str, Any]:
        encoded = quote(run_id, safe="")
        status, payload = self._transport.request("GET", f"/traces/{encoded}")
        if status == 404:
            raise ApiError(404, _detail(payload, f"trace not found: {run_id}"))
        if status >= 400:
            raise ApiError(status, _detail(payload, f"get_trace failed ({status})"))
        if not isinstance(payload, dict):
            raise ApiError(500, "trace response must be an object")
        return payload

    def health(self) -> dict[str, Any]:
        status, payload = self._transport.request("GET", "/health")
        if status >= 400:
            raise ApiError(status, _detail(payload, f"health failed ({status})"))
        if not isinstance(payload, dict):
            raise ApiError(500, "health response must be an object")
        return payload


def api_url_from_env() -> str:
    return (os.environ.get("CITEBENCH_API_URL") or DEFAULT_API_URL).strip().rstrip("/")


def api_from_env() -> CitebenchApi:
    return CitebenchApi(HttpxTransport(api_url_from_env()))


def _detail(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail
        if detail is not None:
            return str(detail)
    return fallback
