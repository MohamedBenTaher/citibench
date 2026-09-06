import pytest

from embed import EmbedError, _vectors_from_payload


def test_vectors_from_payload_enforces_768d() -> None:
    payload = {
        "data": [
            {"index": 1, "embedding": [0.0] * 768},
            {"index": 0, "embedding": [1.0] * 768},
        ]
    }
    vectors = _vectors_from_payload(payload, 768, 2)
    assert vectors[0][0] == 1.0
    assert vectors[1][0] == 0.0
    assert len(vectors[0]) == 768


def test_vectors_from_payload_rejects_wrong_dimension() -> None:
    payload = {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}
    with pytest.raises(EmbedError, match="768"):
        _vectors_from_payload(payload, 768, 1)
