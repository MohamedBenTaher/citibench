"""OpenAI-compatible embeddings stand-in for offline ingest verification.

Not a second product embed provider. Production ingest still requires
GROQ_API_KEY and talks to api.groq.com unless GROQ_API_BASE is pointed here.
"""

from __future__ import annotations

import hashlib

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Citebench fake Groq embeddings")


class EmbeddingRequest(BaseModel):
    model: str
    input: str | list[str]
    encoding_format: str | None = None


def _vector(text: str, dimensions: int = 768) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    blob = digest
    while len(values) < dimensions:
        blob = hashlib.sha256(blob).digest()
        for byte in blob:
            values.append((byte / 127.5) - 1.0)
            if len(values) == dimensions:
                break
    return values


@app.post("/openai/v1/embeddings")
def create_embeddings(body: EmbeddingRequest) -> dict:
    texts = body.input if isinstance(body.input, list) else [body.input]
    data = [
        {"object": "embedding", "index": index, "embedding": _vector(text)}
        for index, text in enumerate(texts)
    ]
    return {"object": "list", "model": body.model, "data": data, "usage": {"prompt_tokens": 0, "total_tokens": 0}}
