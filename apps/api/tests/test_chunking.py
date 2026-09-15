from citebench_api.retrieval.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    chunk_text,
    chunk_text_dynamic,
    encoding_for,
)


def test_chunk_windows_are_512_with_64_overlap() -> None:
    enc = encoding_for()
    text = " ".join(f"tok{i}" for i in range(800))
    chunks = chunk_text(text)
    assert chunks
    assert all(chunk.token_count <= DEFAULT_CHUNK_SIZE for chunk in chunks)
    assert chunks[0].token_count == DEFAULT_CHUNK_SIZE
    stride = DEFAULT_CHUNK_SIZE - DEFAULT_CHUNK_OVERLAP
    token_ids = enc.encode(text)
    for left, right in zip(chunks, chunks[1:], strict=False):
        assert right.start_token - left.start_token == stride
        left_tail = token_ids[left.start_token + left.token_count - DEFAULT_CHUNK_OVERLAP : left.start_token + left.token_count]
        right_head = token_ids[right.start_token : right.start_token + DEFAULT_CHUNK_OVERLAP]
        assert left_tail == right_head


def test_chunking_is_stable_across_calls() -> None:
    text = "Kubernetes Deployments manage ReplicaSets.\n" * 200
    first = [chunk.text for chunk in chunk_text(text)]
    second = [chunk.text for chunk in chunk_text(text)]
    assert first == second
    assert first


def test_short_document_is_single_chunk() -> None:
    chunks = chunk_text("one short passage")
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].start_token == 0


def test_dynamic_chunking_sets_heading_section_path() -> None:
    text = "# A\nintro text\n## B\ndetails here\n# C\nclosing"
    chunks = chunk_text_dynamic(text)
    sections = [chunk.section for chunk in chunks]
    assert "A" in sections
    assert "A > B" in sections


def test_page_marker_becomes_section_without_heading() -> None:
    text = "[page 1]\nalpha\n[page 2]\nbeta"
    chunks = chunk_text_dynamic(text)
    assert [chunk.section for chunk in chunks] == ["page 1", "page 2"]
