import hashlib

import httpx
import pytest

from snapshot import SnapshotError, snapshot_url


def test_snapshot_writes_bytes_and_sha256(tmp_path) -> None:
    body = b"<html><main>Pods</main></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = snapshot_url(
        doc_id="k8s-pods",
        source_url="https://kubernetes.io/docs/concepts/workloads/pods/",
        raw_root=tmp_path,
        client=client,
    )
    digest = hashlib.sha256(body).hexdigest()
    assert result.sha256 == digest
    assert (tmp_path / "k8s-pods" / "page.html").read_bytes() == body
    assert (tmp_path / "k8s-pods" / "sha256").read_text(encoding="utf-8").strip() == digest
    assert '"sha256"' in (tmp_path / "k8s-pods" / "meta.json").read_text(encoding="utf-8")


def test_snapshot_http_error_is_visible(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="nope")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(SnapshotError, match="HTTP 503"):
        snapshot_url(
            doc_id="az-monitor",
            source_url="https://learn.microsoft.com/en-us/azure/azure-monitor/overview",
            raw_root=tmp_path,
            client=client,
        )
