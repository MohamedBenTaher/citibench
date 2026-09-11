"""C5 RunTrace emit: Langfuse is the named backend; local store is fallback/UI."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Protocol
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

log = logging.getLogger("citebench.trace")

TRACE_NAME = "citebench.run"
_TEXT_REF_RE = re.compile(r"^[A-Za-z0-9._:-]+#[A-Za-z0-9._:-]+$")
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_BODY_KEYS = frozenset({"text", "body", "chunk_text", "passage", "content", "document"})
_MEMORY: dict[str, "RunTrace"] = {}
_MEMORY_LOCK = Lock()
_LANGFUSE_LOCK = Lock()
_langfuse_disabled = False
_DEFAULT_LANGFUSE_HOST = "https://cloud.langfuse.com"


class SpanKind(str, Enum):
    retrieve = "retrieve"
    rerank = "rerank"
    generate = "generate"
    abstain = "abstain"


class SpanStatus(str, Enum):
    ok = "ok"
    error = "error"


class ChunkRef(BaseModel):
    chunk_id: str
    doc_id: str
    text_ref: str
    score: float | None = None
    rank: int | None = None
    # Display metadata only. text_ref stays pointer-only; no chunk body.
    title: str | None = None
    source: str | None = None
    product: str | None = None
    doc_type: str | None = None
    version: str | None = None
    license: str | None = None
    page: int | None = None
    section: str | None = None
    url: str | None = None

    @field_validator("text_ref")
    @classmethod
    def pointer_only(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("text_ref must be a non-empty pointer")
        if "\n" in text or len(text) > 256:
            raise ValueError("text_ref must not embed the chunk body")
        if not _TEXT_REF_RE.match(text):
            raise ValueError("text_ref must look like doc_id#chunk_id")
        return text


class CostEstimate(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embed_tokens: int = 0
    rerank_tokens: int = 0
    usd_estimate: float = 0.0

    @field_validator(
        "prompt_tokens", "completion_tokens", "embed_tokens", "rerank_tokens"
    )
    @classmethod
    def nonneg_int(cls, value: int) -> int:
        if value < 0:
            raise ValueError("token counts must be >= 0")
        return value

    @field_validator("usd_estimate")
    @classmethod
    def nonneg_usd(cls, value: float) -> float:
        if value < 0:
            raise ValueError("usd_estimate must be >= 0")
        return value


class Span(BaseModel):
    span_id: str
    parent_id: str | None = None
    kind: SpanKind
    started_at: datetime
    finished_at: datetime
    status: SpanStatus = SpanStatus.ok
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def time_order(self) -> Span:
        if self.finished_at < self.started_at:
            raise ValueError("span finished_at must be >= started_at")
        return self


class RunTrace(BaseModel):
    run_id: str
    query: str
    started_at: datetime
    finished_at: datetime
    spans: list[Span] = Field(default_factory=list)
    citations: list[ChunkRef] = Field(default_factory=list)
    abstained: bool = False
    cost: CostEstimate = Field(default_factory=CostEstimate)
    langfuse_trace_id: str | None = None
    rerank_skipped: bool = False
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    cost_method: str = ""

    @model_validator(mode="after")
    def time_order(self) -> RunTrace:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must be >= started_at")
        return self


class LangfusePoster(Protocol):
    def post(self, trace: RunTrace) -> str: ...


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_span_id(kind: SpanKind | str) -> str:
    label = kind.value if isinstance(kind, SpanKind) else kind
    return f"{label}-{uuid4().hex[:10]}"


def chunk_ref_for_hit(
    *,
    chunk_id: str,
    doc_id: str,
    score: float | None,
    rank: int | None,
    title: str | None = None,
    source: str | None = None,
    product: str | None = None,
    doc_type: str | None = None,
    version: str | None = None,
    license: str | None = None,
    page: int | None = None,
    section: str | None = None,
    url: str | None = None,
) -> ChunkRef:
    return ChunkRef(
        chunk_id=chunk_id,
        doc_id=doc_id,
        text_ref=f"{doc_id}#{chunk_id}",
        score=score,
        rank=rank,
        title=title,
        source=source,
        product=product,
        doc_type=doc_type,
        version=version,
        license=license,
        page=page,
        section=section,
        url=url,
    )


def refs_from_hits(hits: list[Any]) -> list[ChunkRef]:
    refs: list[ChunkRef] = []
    for index, hit in enumerate(hits, start=1):
        refs.append(
            chunk_ref_for_hit(
                chunk_id=str(getattr(hit, "chunk_id", "")),
                doc_id=str(getattr(hit, "doc_id", "")),
                score=getattr(hit, "score", None),
                rank=getattr(hit, "rank", index),
                title=getattr(hit, "title", None),
                source=getattr(hit, "source", None),
                product=getattr(hit, "product", None),
                doc_type=getattr(hit, "doc_type", None),
                version=getattr(hit, "version", None),
                license=getattr(hit, "license", None),
                page=getattr(hit, "page", None),
                section=getattr(hit, "section", None),
                url=getattr(hit, "url", None),
            )
        )
    return refs


def validate_run_trace(trace: RunTrace) -> None:
    """Contract B tree + no corpus dump in citations or span attributes."""
    retrieve = [span for span in trace.spans if span.kind == SpanKind.retrieve]
    rerank = [span for span in trace.spans if span.kind == SpanKind.rerank]
    generate = [span for span in trace.spans if span.kind == SpanKind.generate]
    abstain = [span for span in trace.spans if span.kind == SpanKind.abstain]
    if len(retrieve) != 1:
        raise ValueError("RunTrace must contain exactly one retrieve span")
    if retrieve[0].parent_id is not None:
        raise ValueError("retrieve parent_id must be null")
    if len(rerank) != 1:
        raise ValueError("RunTrace must contain exactly one rerank span")
    if rerank[0].parent_id != retrieve[0].span_id:
        raise ValueError("rerank must be a child of retrieve")
    if "rerank_skipped" not in rerank[0].attributes:
        raise ValueError("rerank attributes must include rerank_skipped")
    skipped = bool(rerank[0].attributes["rerank_skipped"])
    if skipped != trace.rerank_skipped:
        raise ValueError("RunTrace.rerank_skipped must match the rerank span")

    if trace.abstained:
        if generate:
            raise ValueError("abstained run must not have a generate span")
        if len(abstain) != 1:
            raise ValueError("abstained run must have exactly one abstain span")
        if abstain[0].parent_id != rerank[0].span_id:
            raise ValueError("abstain must be a child of rerank")
        if trace.citations:
            raise ValueError("abstained run must have empty citations")
    else:
        if abstain:
            raise ValueError("non-abstain run must not have an abstain span")
        if len(generate) != 1:
            raise ValueError("non-abstain run must have exactly one generate span")
        if generate[0].parent_id != rerank[0].span_id:
            raise ValueError("generate must be a child of rerank")

    for ref in trace.citations:
        _assert_pointer(ref)
    for span in trace.spans:
        _assert_no_corpus_dump(span.attributes)


def _assert_pointer(ref: ChunkRef) -> None:
    if ref.text_ref == ref.chunk_id or len(ref.text_ref) > 256:
        raise ValueError("text_ref must be a pointer, not a payload")


def _assert_no_corpus_dump(value: Any) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            if str(key).lower() in _BODY_KEYS and isinstance(inner, str) and len(inner) > 80:
                raise ValueError("span attributes must not dump chunk text")
            _assert_no_corpus_dump(inner)
        return
    if isinstance(value, list):
        for item in value:
            _assert_no_corpus_dump(item)


def resolve_trace_store_dir(settings: Any | None = None) -> Path:
    env = os.environ.get("TRACE_STORE_DIR", "").strip()
    if env:
        return Path(env)
    if settings is not None:
        raw = getattr(settings, "trace_store_dir", None)
        if raw:
            return Path(raw)
    return Path("/tmp/citebench-traces")


def clear_memory_store() -> None:
    with _MEMORY_LOCK:
        _MEMORY.clear()


def reset_langfuse_state() -> None:
    """Test helper: allow Langfuse again after a circuit-break."""
    global _langfuse_disabled
    with _LANGFUSE_LOCK:
        _langfuse_disabled = False


def _disable_langfuse(reason: str) -> None:
    global _langfuse_disabled
    with _LANGFUSE_LOCK:
        _langfuse_disabled = True
    log.warning("Langfuse disabled for this process; local RunTrace store only. %s", reason)


def _silence_langfuse_sdk() -> None:
    logging.getLogger("langfuse").setLevel(logging.CRITICAL)


def _langfuse_host(settings: Any | None) -> str:
    host = (
        _setting(settings, "langfuse_host")
        or os.environ.get("LANGFUSE_HOST", "")
        or os.environ.get("LANGFUSE_BASE_URL", "")
    ).strip()
    return host or _DEFAULT_LANGFUSE_HOST


def _langfuse_host_reachable(host: str, *, timeout: float = 1.5) -> bool:
    url = host.rstrip("/") + "/api/public/health"
    try:
        response = httpx.get(url, timeout=timeout)
    except httpx.HTTPError:
        return False
    return response.status_code < 500


def emit_trace(
    trace: RunTrace,
    *,
    settings: Any | None = None,
    poster: LangfusePoster | None = None,
) -> None:
    """Validate, persist locally, then post to Langfuse. Soft-fail Langfuse."""
    validate_run_trace(trace)
    _store_local(trace, settings)
    client = poster if poster is not None else _default_poster(settings)
    if client is None:
        return
    try:
        langfuse_id = client.post(trace)
    except Exception as exc:
        if poster is None:
            _disable_langfuse(f"emit failed: {exc}")
        else:
            log.warning("Langfuse emit failed; keeping local RunTrace %s: %s", trace.run_id, exc)
        return
    if langfuse_id:
        trace.langfuse_trace_id = str(langfuse_id)
        _store_local(trace, settings)


def list_traces(*, settings: Any | None = None) -> list[RunTrace]:
    store = resolve_trace_store_dir(settings)
    found: dict[str, RunTrace] = {}
    if store.is_dir():
        for path in store.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                item = RunTrace.model_validate(payload)
            except Exception as exc:
                log.warning("skip unreadable trace %s: %s", path, exc)
                continue
            found[item.run_id] = item
    with _MEMORY_LOCK:
        for run_id, item in _MEMORY.items():
            found.setdefault(run_id, item)
    traces = list(found.values())
    traces.sort(key=lambda item: item.started_at, reverse=True)
    return traces


def get_trace(run_id: str, *, settings: Any | None = None) -> RunTrace | None:
    """Look up by ``run_id``, or by ``langfuse_trace_id`` when that id is set."""
    key = (run_id or "").strip()
    if not key or not _TRACE_ID_RE.match(key):
        return None
    with _MEMORY_LOCK:
        cached = _MEMORY.get(key)
        if cached is not None:
            return cached
        for item in _MEMORY.values():
            if item.langfuse_trace_id == key:
                return item
    path = resolve_trace_store_dir(settings) / f"{key}.json"
    if path.is_file():
        try:
            return RunTrace.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            log.warning("failed to read trace %s: %s", key, exc)
            return None
    return _find_by_langfuse_id(key, settings)


def _find_by_langfuse_id(langfuse_id: str, settings: Any | None) -> RunTrace | None:
    store = resolve_trace_store_dir(settings)
    if not store.is_dir():
        return None
    for path in store.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            item = RunTrace.model_validate(payload)
        except Exception as exc:
            log.warning("skip unreadable trace %s: %s", path, exc)
            continue
        if item.langfuse_trace_id == langfuse_id:
            return item
    return None


def langfuse_configured(settings: Any | None = None) -> bool:
    public = _setting(settings, "langfuse_public_key") or os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret = _setting(settings, "langfuse_secret_key") or os.environ.get("LANGFUSE_SECRET_KEY", "")
    return bool(str(public).strip() and str(secret).strip())


def _store_local(trace: RunTrace, settings: Any | None) -> None:
    with _MEMORY_LOCK:
        _MEMORY[trace.run_id] = trace
    store = resolve_trace_store_dir(settings)
    try:
        store.mkdir(parents=True, exist_ok=True)
        path = store / f"{trace.run_id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(trace.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(path)
    except Exception as exc:
        log.warning("local trace persist failed for %s: %s", trace.run_id, exc)


def _setting(settings: Any | None, name: str) -> str:
    if settings is None:
        return ""
    return str(getattr(settings, name, "") or "")


def _default_poster(settings: Any | None) -> LangfusePoster | None:
    if _langfuse_disabled or not langfuse_configured(settings):
        return None
    host = _langfuse_host(settings)
    if not _langfuse_host_reachable(host):
        _disable_langfuse(f"host unreachable: {host}")
        return None
    try:
        _silence_langfuse_sdk()
        poster = SdkLangfusePoster(settings)
        if not poster.auth_ok():
            _disable_langfuse(f"auth failed for {host}")
            return None
        return poster
    except Exception as exc:
        _disable_langfuse(f"client init failed: {exc}")
        return None


class SdkLangfusePoster:
    """Langfuse SDK adapter. v2 `trace()`/`span()` or v3 observations."""

    def __init__(self, settings: Any | None) -> None:
        from langfuse import Langfuse

        public = _setting(settings, "langfuse_public_key") or os.environ.get(
            "LANGFUSE_PUBLIC_KEY", ""
        )
        secret = _setting(settings, "langfuse_secret_key") or os.environ.get(
            "LANGFUSE_SECRET_KEY", ""
        )
        host = (
            _setting(settings, "langfuse_host")
            or os.environ.get("LANGFUSE_HOST", "")
            or os.environ.get("LANGFUSE_BASE_URL", "")
        )
        kwargs: dict[str, Any] = {
            "public_key": public.strip(),
            "secret_key": secret.strip(),
        }
        if host.strip():
            kwargs["host"] = host.strip()
        self._client = Langfuse(**kwargs)

    def auth_ok(self) -> bool:
        check = getattr(self._client, "auth_check", None)
        if not callable(check):
            return True
        try:
            return bool(check())
        except Exception:
            return False

    def post(self, trace: RunTrace) -> str:
        if hasattr(self._client, "trace"):
            return self._post_v2(trace)
        return self._post_v3(trace)

    def _metadata(self, trace: RunTrace) -> dict[str, Any]:
        return {
            "run_id": trace.run_id,
            "cost": trace.cost.model_dump(),
            "cost_method": trace.cost_method,
            "rerank_skipped": trace.rerank_skipped,
            "abstained": trace.abstained,
            "model": trace.model,
            "tokens_in": trace.tokens_in,
            "tokens_out": trace.tokens_out,
            "latency_ms": trace.latency_ms,
        }

    def _citations_out(self, trace: RunTrace) -> dict[str, Any]:
        return {
            "citations": [ref.text_ref for ref in trace.citations],
            "abstained": trace.abstained,
        }

    def _post_v2(self, trace: RunTrace) -> str:
        root = self._client.trace(
            name=TRACE_NAME,
            input=trace.query,
            metadata=self._metadata(trace),
            output=self._citations_out(trace),
        )
        by_id: dict[str, Any] = {}
        for span in _walk_spans(trace.spans):
            parent = by_id.get(span.parent_id) if span.parent_id else root
            created = parent.span(
                name=span.kind.value,
                start_time=span.started_at,
                end_time=span.finished_at,
                metadata=span.attributes,
                status_message=span.status.value,
                level="ERROR" if span.status == SpanStatus.error else "DEFAULT",
            )
            by_id[span.span_id] = created
        score = getattr(self._client, "score", None)
        if callable(score):
            score(
                trace_id=root.id,
                name="rerank_skipped",
                value=1 if trace.rerank_skipped else 0,
            )
        flush = getattr(self._client, "flush", None)
        if callable(flush):
            flush()
        return str(root.id)

    def _post_v3(self, trace: RunTrace) -> str:
        client = self._client
        start = getattr(client, "start_as_current_observation", None)
        if not callable(start):
            raise RuntimeError("Langfuse client has no trace() or start_as_current_observation()")
        with start(
            as_type="span",
            name=TRACE_NAME,
            input=trace.query,
            metadata=self._metadata(trace),
        ) as root:
            update_trace = getattr(root, "update_trace", None)
            if callable(update_trace):
                update_trace(
                    name=TRACE_NAME,
                    input=trace.query,
                    metadata=self._metadata(trace),
                    output=self._citations_out(trace),
                )
            self._post_v3_children(start, trace.spans, parent_id=None)
            root.update(output=self._citations_out(trace))
            trace_id = str(
                getattr(root, "trace_id", None)
                or getattr(root, "id", None)
                or getattr(client, "get_current_trace_id", lambda: "")()
                or ""
            )
        create_score = getattr(client, "create_score", None) or getattr(client, "score", None)
        if callable(create_score) and trace_id:
            create_score(
                name="rerank_skipped",
                value=1 if trace.rerank_skipped else 0,
                trace_id=trace_id,
            )
        flush = getattr(client, "flush", None)
        if callable(flush):
            flush()
        if not trace_id:
            raise RuntimeError("Langfuse v3 post returned no trace id")
        return trace_id

    def _post_v3_children(
        self,
        start: Any,
        spans: list[Span],
        *,
        parent_id: str | None,
    ) -> None:
        for span in spans:
            if span.parent_id != parent_id:
                continue
            as_type = "generation" if span.kind == SpanKind.generate else "span"
            with start(
                as_type=as_type,
                name=span.kind.value,
                metadata=span.attributes,
            ) as child:
                child.update(
                    metadata=span.attributes,
                    level="ERROR" if span.status == SpanStatus.error else "DEFAULT",
                )
                self._post_v3_children(start, spans, parent_id=span.span_id)


def _walk_spans(spans: list[Span]) -> list[Span]:
    """Parents before children so v2 nesting can attach to the created parent."""
    by_parent: dict[str | None, list[Span]] = {}
    for span in spans:
        by_parent.setdefault(span.parent_id, []).append(span)
    ordered: list[Span] = []

    def _visit(parent_id: str | None) -> None:
        for span in by_parent.get(parent_id, []):
            ordered.append(span)
            _visit(span.span_id)

    _visit(None)
    return ordered
