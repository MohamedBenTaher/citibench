"""OpenAI-compatible embeddings stand-in for offline ingest verification.

Not a second product embed provider. Production ingest uses local nomic
unless GROQ_API_BASE is pointed here (or Groq still hosts the model).
"""

from __future__ import annotations

import hashlib
import json
import re

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


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    response_format: dict | None = None


@app.post("/openai/v1/embeddings")
def create_embeddings(body: EmbeddingRequest) -> dict:
    texts = body.input if isinstance(body.input, list) else [body.input]
    data = [
        {"object": "embedding", "index": index, "embedding": _vector(text)}
        for index, text in enumerate(texts)
    ]
    return {"object": "list", "model": body.model, "data": data, "usage": {"prompt_tokens": 0, "total_tokens": 0}}


@app.post("/openai/v1/chat/completions")
def create_chat_completion(body: ChatRequest) -> dict:
    user = " ".join(message.content for message in body.messages if message.role == "user")
    lowered = user.lower()
    if "innovx" in lowered or "acme" in lowered:
        content = '{"abstain": true, "answer": "I don\'t know", "citation_ids": []}'
    else:
        match = re.search(r"chunk_id=([A-Za-z0-9:._-]+)", user)
        chunk_id = match.group(1) if match else ""
        if chunk_id:
            content = json.dumps(
                {
                    "abstain": False,
                    "answer": "Answer grounded in the first retrieved chunk.",
                    "citation_ids": [chunk_id],
                }
            )
        else:
            content = '{"abstain": true, "answer": "I don\'t know", "citation_ids": []}'
    return {
        "id": "fake-chat",
        "object": "chat.completion",
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 16, "completion_tokens": 12, "total_tokens": 28},
    }
