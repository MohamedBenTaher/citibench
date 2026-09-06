from pathlib import Path

from manifest import parse_manifest

REPO_MANIFEST = Path(__file__).resolve().parents[3] / "corpus" / "MANIFEST.md"


def test_frozen_manifest_has_exactly_fourteen_pinned_urls() -> None:
    docs = parse_manifest(REPO_MANIFEST)
    assert len(docs) == 14
    ids = [doc.id for doc in docs]
    assert len(set(ids)) == 14
    assert all(doc.source_url.startswith("https://") for doc in docs)
    assert {doc.id for doc in docs} == {
        "k8s-deployments",
        "k8s-pods",
        "k8s-services",
        "k8s-configmaps",
        "k8s-secrets",
        "k8s-ingress",
        "k8s-scheduler",
        "k8s-storage",
        "az-aks-intro",
        "az-aks-concepts",
        "az-aks-network",
        "az-blob-overview",
        "az-identity",
        "az-monitor",
    }


def test_parse_manifest_reads_table(tmp_path: Path) -> None:
    path = tmp_path / "MANIFEST.md"
    path.write_text(
        """# test
| id | title | source_url | version_or_snapshot | license | pages |
| --- | --- | --- | --- | --- | --- |
| k8s-pods | Pods | https://kubernetes.io/docs/concepts/workloads/pods/ | snap | CC BY 4.0 | TBD |
""",
        encoding="utf-8",
    )
    docs = parse_manifest(path)
    assert len(docs) == 1
    assert docs[0].id == "k8s-pods"
