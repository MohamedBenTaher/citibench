import sys
from pathlib import Path

from manifest import parse_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_MANIFEST = REPO_ROOT / "corpus" / "MANIFEST.md"
REPO_V0_MANIFEST = REPO_ROOT / "corpus" / "v0" / "MANIFEST.md"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from crawl_manifest import allowed, slug_for  # noqa: E402


def test_big_freeze_has_minimum_size() -> None:
    docs = parse_manifest(REPO_MANIFEST)
    assert len(docs) >= 900
    ids = [doc.id for doc in docs]
    assert len(set(ids)) == len(ids)
    assert all(doc.source_url.startswith("https://") for doc in docs)
    assert all(doc.license.strip() for doc in docs)


def test_corpus_v0_manifest_has_fourteen_pinned_urls() -> None:
    docs = parse_manifest(REPO_V0_MANIFEST)
    assert len(docs) == 14
    ids = [doc.id for doc in docs]
    assert len(set(ids)) == 14
    assert all(doc.source_url.startswith("https://") for doc in docs)


def test_crawler_slug_and_prefix_helpers() -> None:
    assert slug_for("k8s", "https://kubernetes.io/docs/concepts/workloads/pods/") == (
        "k8s-docs-concepts-workloads-pods"
    )
    prefixes = ("https://kubernetes.io/docs/",)
    assert allowed("https://kubernetes.io/docs/concepts/pods/", prefixes)
    assert not allowed("https://kubernetes.io/blog/2024/", prefixes)


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


def test_manifest_reads_optional_metadata_columns(tmp_path: Path) -> None:
    path = tmp_path / "MANIFEST.md"
    path.write_text(
        """# test
| id | title | source_url | version_or_snapshot | license | pages | doc_type | product | source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| xv6-book | xv6 | https://example.invalid/book.pdf | 2026-09-10 | MIT | 0 | book | xv6 | pdos.csail.mit.edu |
""",
        encoding="utf-8",
    )
    docs = parse_manifest(path)
    assert len(docs) == 1
    assert docs[0].doc_type == "book"
    assert docs[0].product == "xv6"
    assert docs[0].source == "pdos.csail.mit.edu"


def test_manifest_v0_without_optional_columns_still_parses(tmp_path: Path) -> None:
    path = tmp_path / "MANIFEST.md"
    path.write_text(
        """# test
| id | title | source_url | version_or_snapshot | license | pages |
| --- | --- | --- | --- | --- | --- |
| k8s-pods | Pods | https://kubernetes.io/docs/concepts/workloads/pods/ | v0 | CC BY 4.0 | 1 |
""",
        encoding="utf-8",
    )
    docs = parse_manifest(path)
    assert docs[0].doc_type is None
    assert docs[0].product is None
