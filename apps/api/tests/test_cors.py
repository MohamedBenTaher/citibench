from fastapi.testclient import TestClient


def test_cors_origins_keeps_localhost_when_compose_leaves_tokens(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:${WEB_PORT:-3000},https://demo.example",
    )
    monkeypatch.setenv("WEB_PORT", "3100")
    import main as main_mod

    origins = main_mod._cors_origins()
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins
    assert "http://localhost:3100" in origins
    assert "https://demo.example" in origins
    assert all("${" not in origin for origin in origins)


def test_cors_origins_always_allow_gotenberg_fallback_port() -> None:
    import main as main_mod

    origins = main_mod._cors_origins()
    assert "http://localhost:3100" in origins
    assert "http://127.0.0.1:3100" in origins


def test_health_allows_localhost_origin() -> None:
    from main import app

    response = TestClient(app).get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
