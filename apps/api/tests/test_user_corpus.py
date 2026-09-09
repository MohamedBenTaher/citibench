from pathlib import Path

import httpx
import pytest

from chunking import chunk_text_dynamic
from fetch_guard import UnsafeSource, assert_fetchable_https
from snapshot import SnapshotError, snapshot_url_streamed


def test_fetch_guard_rejects_loopback() -> None:
    with pytest.raises(UnsafeSource):
        assert_fetchable_https("https://127.0.0.1/docs")
    with pytest.raises(UnsafeSource):
        assert_fetchable_https("http://example.com/docs")


def test_chunk_text_dynamic_splits_headings() -> None:
    text = "# One\n" + ("alpha " * 40) + "\n# Two\n" + ("bravo " * 40)
    chunks = chunk_text_dynamic(text, chunk_size=32, chunk_overlap=4)
    assert len(chunks) >= 2
    assert any("One" in c.text for c in chunks)
    assert any("Two" in c.text for c in chunks)


def test_snapshot_stream_respects_max_bytes(tmp_path: Path) -> None:
    body = b"<html>" + (b"x" * 200) + b"</html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(SnapshotError, match="max bytes"):
        snapshot_url_streamed(
            doc_id="user-test",
            source_url="https://example.com/page",
            raw_root=tmp_path,
            client=client,
            max_bytes=50,
        )
