import socket

from db import (
    database_unavailable_detail,
    is_database_error,
    resolve_database_url,
    rewrite_database_url_host,
)


def test_rewrite_preserves_user_password_port_and_db() -> None:
    rewritten = rewrite_database_url_host(
        "postgresql://citebench:citebench@db:5432/citebench",
        "127.0.0.1",
    )
    assert rewritten == "postgresql://citebench:citebench@127.0.0.1:5432/citebench"


def test_resolve_keeps_resolvable_compose_host(monkeypatch) -> None:
    def fake_getaddrinfo(host: str, _port: object, *args: object, **kwargs: object):
        if host == "db":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.18.0.2", 0))]
        raise OSError(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    url = "postgresql://citebench:citebench@db:5432/citebench"
    assert resolve_database_url(url) == url


def test_resolve_rewrites_unresolvable_docker_host(monkeypatch) -> None:
    def fake_getaddrinfo(host: str, _port: object, *args: object, **kwargs: object):
        if host in {"127.0.0.1", "localhost"}:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        raise OSError(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    resolved = resolve_database_url("postgresql://citebench:citebench@db:5432/citebench")
    assert resolved == "postgresql://citebench:citebench@127.0.0.1:5432/citebench"


def test_resolve_does_not_rewrite_unrelated_unresolvable_host(monkeypatch) -> None:
    def fake_getaddrinfo(_host: str, _port: object, *args: object, **kwargs: object):
        raise OSError(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    url = "postgresql://citebench:citebench@prod.internal:5432/citebench"
    assert resolve_database_url(url) == url


def test_database_unavailable_detail_names_host() -> None:
    exc = OSError(-2, "Name or service not known")
    detail = database_unavailable_detail(
        exc,
        "postgresql://citebench:citebench@db:5432/citebench",
    )
    assert "could not resolve host 'db'" in detail
    assert "127.0.0.1" in detail
    assert "Name or service not known" in detail


def test_is_database_error_matches_dns() -> None:
    assert is_database_error(OSError(-2, "Name or service not known"))
    assert not is_database_error(ValueError("bad chunk"))


def test_insert_chunks_writes_metadata_columns() -> None:
    import db

    captured: list[str] = []

    class _Cursor:
        def execute(self, sql: str, params: object) -> None:
            captured.append(sql)

        def __enter__(self):
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

    class _Conn:
        def cursor(self) -> _Cursor:
            return _Cursor()

    db.insert_chunks(
        _Conn(),
        [
            {
                "id": "k8s-pods:0",
                "doc_id": "k8s-pods",
                "chunk_index": 0,
                "page": 1,
                "section": "A",
                "section_path": "A",
                "url": "https://example.invalid/pods",
                "text": "body",
                "text_ref": "k8s-pods#k8s-pods:0",
                "token_count": 1,
                "embedding": [0.0, 0.0],
            }
        ],
    )
    assert captured
    sql = captured[0]
    for column in ("section", "section_path", "url"):
        assert column in sql


def test_list_documents_parameterizes_filters() -> None:
    import db

    captured: list[tuple[str, object]] = []

    class _Res:
        def __init__(self, rows: list[dict]) -> None:
            self._rows = rows

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return self._rows

    class _Conn:
        def execute(self, sql: str, params: object = None) -> _Res:
            captured.append((sql, params))
            if sql.strip().startswith("SELECT COUNT(*)"):
                return _Res([{"n": 1}])
            return _Res(
                [
                    {
                        "id": "d",
                        "title": "t",
                        "source_url": "u",
                        "product": "Kubernetes",
                        "doc_type": "guide",
                        "source": "s",
                        "origin": "freeze",
                        "license": "MIT",
                        "status": "ok",
                        "error": None,
                        "page_count": 1,
                        "indexed_at": None,
                        "version": "v",
                        "chunk_count": 3,
                    }
                ]
            )

    result = db.list_documents(
        _Conn(), query="pods", product="Kubernetes", limit=5, offset=10
    )
    assert result["total"] == 1
    assert result["documents"][0]["chunk_count"] == 3
    sql, params = captured[-1]
    assert "%s" in sql
    assert "pods" not in sql  # values are bound, never interpolated
    assert params[-2:] == [5, 10]


def test_clean_topic_and_phrase_question() -> None:
    import db

    assert db.clean_topic("Kubernetes", "Pods / Kubernetes") == "Pods"
    assert (
        db.clean_topic(
            "PostgreSQL", "PostgreSQL: Documentation: 18: 13.4. Data Consistency Checks"
        )
        == "Data Consistency Checks"
    )
    assert (
        db.clean_topic("FastAPI", "Additional Responses in OpenAPI - FastAPI")
        == "Additional Responses in OpenAPI"
    )
    assert (
        db.clean_topic(
            "Azure", "What is AKS? - Azure Kubernetes Service / Microsoft Learn"
        )
        == "What is AKS?"
    )
    assert db.phrase_question("Kubernetes", "Pods") == "What is Pods in Kubernetes?"
    assert db.phrase_question("Kubernetes", "Configure a Pod").startswith("How do I configure")
    assert db.phrase_question("xv6", "anything") == "What does the xv6 book cover?"


def test_corpus_suggestions_are_derived_from_documents() -> None:
    import db

    rows = [
        {"id": "k8s-deploy", "title": "Deployments / Kubernetes", "product": "Kubernetes", "doc_type": "concept"},
        {"id": "k8s-ctrl", "title": "Controllers / Kubernetes", "product": "Kubernetes", "doc_type": "concept"},
        {"id": "pg-wal", "title": "PostgreSQL: Documentation: 18: 28. WAL", "product": "PostgreSQL", "doc_type": "manual"},
    ]

    class _Result:
        def fetchall(self):
            return rows

    class _Conn:
        def execute(self, _sql: str, _params: object = None) -> _Result:
            return _Result()

    suggestions = db.corpus_suggestions(_Conn(), 3)["suggestions"]
    questions = [item["question"] for item in suggestions]
    assert any("Deployments" in question for question in questions)
    assert any(question.startswith("Compare") for question in questions)
    assert all(item["question"] for item in suggestions)
