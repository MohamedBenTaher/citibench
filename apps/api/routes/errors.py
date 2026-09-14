"""Mapping service-layer errors to HTTP status codes."""

from __future__ import annotations

from fastapi import HTTPException


def runtime_http_error(exc: RuntimeError) -> HTTPException:
    message = str(exc)
    if "rejected by Groq" in message:
        return HTTPException(status_code=401, detail=message)
    if "GROQ_API_KEY" in message:
        return HTTPException(status_code=503, detail=message)
    return HTTPException(status_code=500, detail=message)
