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
