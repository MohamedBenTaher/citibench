import main as main_mod  # noqa: F401  # TestClient target; app wiring now lives in routes
from citebench_api import routes as routes
def test_cors_origins_keeps_localhost_when_compose_leaves_tokens(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:${WEB_PORT:-3000},https://demo.example",
    )
    monkeypatch.setenv("WEB_PORT", "3100")

    origins = routes._cors_origins()
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins
    assert "http://localhost:3100" in origins
    assert "https://demo.example" in origins
    assert all("${" not in origin for origin in origins)


def test_cors_origins_always_allow_gotenberg_fallback_port() -> None:
    origins = routes._cors_origins()
    assert "http://localhost:3100" in origins
    assert "http://127.0.0.1:3100" in origins


def test_health_allows_localhost_origin() -> None:
    from fastapi.testclient import TestClient

    response = TestClient(main_mod.app).get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_allows_credentials_so_edge_auth_cookies_survive() -> None:
    """The browser drops cookies on a cross-origin call unless the response opts in.

    Production puts an edge auth gate (Cloudflare Access) in front of the API on
    its own hostname. The UI fetch therefore sets credentials="include", which the
    browser only honours when the preflight/response carries this header.
    """
    from fastapi.testclient import TestClient

    response = TestClient(main_mod.app).get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_never_pairs_wildcard_with_credentials() -> None:
    """A wildcard origin plus credentials is forbidden by the CORS spec."""
    assert "*" not in routes._cors_origins()
