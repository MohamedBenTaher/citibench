from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from main import maybe_warmup, should_skip_model_warmup
from settings import load_settings


def test_warmup_skipped_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CITEBENCH_SKIP_MODEL_WARMUP", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert should_skip_model_warmup() is True

    embed = MagicMock()
    rerank = MagicMock()
    monkeypatch.setattr("main.warmup_local_embed", embed)
    monkeypatch.setattr("main.warmup_ranker", rerank)
    maybe_warmup(load_settings())
    embed.assert_not_called()
    rerank.assert_not_called()


def test_maybe_warmup_calls_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CITEBENCH_SKIP_MODEL_WARMUP", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert should_skip_model_warmup() is False

    embed = MagicMock()
    rerank = MagicMock()
    monkeypatch.setattr("main.warmup_local_embed", embed)
    monkeypatch.setattr("main.warmup_ranker", rerank)
    settings = load_settings()
    maybe_warmup(settings)
    maybe_warmup(settings)
    assert embed.call_count == 2
    assert rerank.call_count == 2
    rerank.assert_called_with(settings.rerank_model)
