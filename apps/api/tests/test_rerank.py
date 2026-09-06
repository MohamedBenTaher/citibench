from retrieve import FusedChunk

import rerank


def test_flashrank_loader_uses_minilm_and_cache_dir(monkeypatch, tmp_path) -> None:
    created: dict[str, object] = {}

    class FakeRanker:
        def __init__(self, model_name, cache_dir=None, **kwargs):
            created["model_name"] = model_name
            created["cache_dir"] = cache_dir

        def rerank(self, request):
            return [{"id": 0, "score": 0.42}]

    class FakeRequest:
        def __init__(self, query, passages):
            self.query = query
            self.passages = passages

    monkeypatch.setattr(rerank, "Ranker", FakeRanker)
    monkeypatch.setattr(rerank, "RerankRequest", FakeRequest)
    monkeypatch.setenv("FLASHRANK_CACHE_DIR", str(tmp_path))
    rerank.reset_ranker_cache()
    scores = rerank.flashrank_rerank(
        "how does the kube-scheduler place pods onto nodes",
        [FusedChunk(chunk_id="k8s-pods:0", doc_id="k8s-pods", text="A Pod")],
    )
    assert created["model_name"] == "ms-marco-MiniLM-L-12-v2"
    assert created["cache_dir"] == str(tmp_path)
    assert scores == [0.42]
    rerank.reset_ranker_cache()
