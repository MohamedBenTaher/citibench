from __future__ import annotations

import pytest

from trace import clear_memory_store


@pytest.fixture(autouse=True)
def isolate_trace_store(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRACE_STORE_DIR", str(tmp_path / "traces"))
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    clear_memory_store()
    yield
    clear_memory_store()
