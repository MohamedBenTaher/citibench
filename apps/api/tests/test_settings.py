from pathlib import Path

import pytest

from citebench_api.config import GROQ_KEY_HELP, Settings, _repo_root, load_settings, require_groq_key


def test_require_groq_key_fails_clearly() -> None:
    settings = Settings(
        provider="groq",
        embed_model="nomic-embed-text-v1.5",
        embed_dimensions=768,
        embed_api_base="https://api.groq.com/openai/v1",
        embed_document_prefix="search_document: ",
        chunk_size=512,
        chunk_overlap=64,
        tokenizer="cl100k_base",
        database_url="postgresql://citebench:citebench@127.0.0.1:5432/citebench",
        corpus_dir=Path("."),
        manifest_path=Path("MANIFEST.md"),
        groq_api_key="",
    )
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        require_groq_key(settings)
    assert "console.groq.com/keys" in GROQ_KEY_HELP
    assert "second embed provider" in GROQ_KEY_HELP
    assert "second chat provider" in GROQ_KEY_HELP
    # Import-time repo-root walk must not assume a deep path (Compose image is /app).
    assert _repo_root() is None or (_repo_root() / "config.yaml").exists()


def test_load_settings_binds_groq_chat_model() -> None:
    settings = load_settings()
    assert settings.provider == "groq"
    assert settings.chat_model == "openai/gpt-oss-20b"
    assert settings.abstain_min_score == 0.12
    assert settings.chat_prompt_usd_per_1m == 0.075
    assert settings.chat_completion_usd_per_1m == 0.30
    assert settings.embed_backend == "local"


def test_manifest_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = tmp_path / "MANIFEST.md"
    manifest.write_text("# empty\n", encoding="utf-8")
    monkeypatch.setenv("CITEBENCH_MANIFEST", str(manifest))
    assert load_settings().manifest_path == manifest


def test_snapshot_only_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CITEBENCH_SNAPSHOT_ONLY", "1")
    assert load_settings().snapshot_only is True
    monkeypatch.delenv("CITEBENCH_SNAPSHOT_ONLY", raising=False)
    assert load_settings().snapshot_only is False
