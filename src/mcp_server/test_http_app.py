"""Tests for the streamable-HTTP transport entrypoint.

Skipped automatically when the HTTP extras (uvicorn/starlette/httpx) are not
installed, so stdio-only environments do not fail.
"""
from __future__ import annotations

import importlib

import pytest

pytest.importorskip("starlette")
pytest.importorskip("httpx")

from starlette.routing import Mount, Route
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BORSDATA_API_KEY", "test_key")


def _fresh_module():
    import mcp_server.http_app as mod

    return importlib.reload(mod)


def test_build_app_exposes_health_and_mcp_routes() -> None:
    """Criterion 2: build_app() succeeds and exposes /health and /mcp."""
    mod = _fresh_module()
    app = mod.build_app()

    paths = set()
    for route in app.routes:
        if isinstance(route, (Route, Mount)):
            paths.add(route.path)

    assert "/health" in paths
    assert "/mcp" in paths


def test_health_endpoint_returns_ok() -> None:
    """Criterion 3: GET /health returns 200 with body 'ok'."""
    mod = _fresh_module()
    app = mod.build_app()

    with TestClient(app) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.text == "ok"


def test_auth_off_does_not_block_mcp_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 6: with MCP_AUTH_TOKEN unset, the auth gate does not 401."""
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    mod = _fresh_module()
    app = mod.build_app()

    with TestClient(app) as client:
        # A malformed MCP request is still served by the session manager; the
        # important assertion is that our auth gate did not return 401.
        resp = client.get("/mcp/")

    assert resp.status_code != 401


def test_auth_on_rejects_missing_and_wrong_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 5: with MCP_AUTH_TOKEN set, missing/wrong token returns 401."""
    monkeypatch.setenv("MCP_AUTH_TOKEN", "s3cret")
    mod = _fresh_module()
    app = mod.build_app()

    with TestClient(app) as client:
        no_auth = client.get("/mcp/")
        bad_auth = client.get("/mcp/", headers={"Authorization": "Bearer wrong"})
        good_auth = client.get("/mcp/", headers={"Authorization": "Bearer s3cret"})

    assert no_auth.status_code == 401
    assert bad_auth.status_code == 401
    # Correct token clears the auth gate; the session manager handles the rest
    # (and will return its own non-401 status for a malformed MCP request).
    assert good_auth.status_code != 401
