"""Ingest keeps last-good chunks; text_ref matches citation pointers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from citebench_api.ingest.pipeline import IngestBusy, WipeDisabled, format_text_ref, run_ingest
from test_generate import make_settings


def test_format_text_ref_matches_citation_shape() -> None:
    assert format_text_ref("k8s-pods", "k8s-pods:0") == "k8s-pods#k8s-pods:0"


def test_record_failure_marks_without_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    from citebench_api.ingest.manifest import ManifestDoc
    import citebench_api.ingest.pipeline as pipeline_mod

    marked: list[str] = []
    monkeypatch.setattr(
        pipeline_mod,
        "replace_document",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("replace_document")),
    )
    monkeypatch.setattr(
        pipeline_mod,
        "mark_document_failed",
        lambda _conn, **kwargs: marked.append(str(kwargs["doc_id"])),
    )

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(pipeline_mod, "connect", lambda _url: _Conn())
    doc = ManifestDoc(
        id="k8s-pods",
        title="Pods",
        source_url="https://example.invalid/pods",
        version_or_snapshot="v1",
        license="CC-BY",
    )
    pipeline_mod._record_failure(
        make_settings(),
        doc,
        datetime.now(timezone.utc),
        RuntimeError("snap failed"),
    )
    assert marked == ["k8s-pods"]


def test_ingest_busy_without_database() -> None:
    import citebench_api.ingest.pipeline as pipeline_mod

    assert pipeline_mod._INGEST_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(IngestBusy):
            run_ingest(make_settings())
    finally:
        pipeline_mod._INGEST_LOCK.release()


def test_wipe_disabled_by_default() -> None:
    with pytest.raises(WipeDisabled):
        run_ingest(make_settings(allow_wipe=False), wipe=True)
