"""Integration tests proving every protected route enforces auth.

Hits each router's primary endpoints with and without a session cookie
and asserts the right status code. The point isn't to test the routes'
business logic — it's to prove the auth wiring is correct and stays
correct as routes are added.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import bcrypt
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from rotary_phone.config import ConfigManager
from rotary_phone.database.database import Database
from rotary_phone.database.models import User
from rotary_phone.web.app import create_app


# Pairs of (method, path) covering at least one endpoint per protected router.
# Adding a new endpoint? Add a pair here so the auth wiring is verified.
PROTECTED_ENDPOINTS: list[tuple[str, str]] = [
    ("GET", "/api/sounds"),  # sounds_router
    ("GET", "/api/settings/timing"),  # settings_router
    ("GET", "/api/logs"),  # logs_router
    ("GET", "/api/calls"),  # calls_router
    ("GET", "/api/allowlist"),  # allowlist_router
    ("GET", "/api/speed-dial"),  # speed_dial_router
    ("GET", "/api/network/status"),  # network_router
]


@pytest.fixture(scope="module")
def _app(tmp_path_factory):
    """Build a real FastAPI app over a temp DB with one seeded user.

    Scoped to the module so the DB and in-memory session store are shared
    across tests (avoiding re-hitting the rate-limited /api/auth/login more
    than once per module run).
    """
    tmp_path = tmp_path_factory.mktemp("route_auth")
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    db.init_db()

    password_hash = bcrypt.hashpw(b"test-password", bcrypt.gensalt()).decode("utf-8")
    db.add_user(User(username="alice", password_hash=password_hash, created_at=datetime.now(UTC)))

    # Minimal in-memory config. Read tests/test_web_speed_dial.py for the
    # established YAML shape; this needs the same sections.
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "sip:\n"
        "  server: ''\n"
        "  username: ''\n"
        "  password: ''\n"
        "  port: 5060\n"
        "timing:\n"
        "  inter_digit_timeout: 2.0\n"
        "  ring_duration: 2.0\n"
        "  ring_pause: 4.0\n"
        "audio: {}\n"
        "speed_dial: {}\n"
        "allowlist:\n"
        "  - '*'\n"
        "web:\n"
        "  enabled: true\n"
        "  host: '0.0.0.0'\n"
        "  port: 0\n"
    )
    config = ConfigManager(user_config_path=str(config_path))

    call_manager = MagicMock()

    return create_app(
        call_manager=call_manager,
        config_manager=config,
        config_path=str(config_path),
        database=db,
    )


@pytest.fixture
def app_client(_app):
    """Fresh TestClient for each test — no leftover cookies between tests."""
    return TestClient(_app)


@pytest.fixture(scope="module")
def authed_cookie(_app) -> dict[str, str]:
    """Log in as the seeded user once per module and return the cookie jar.

    Uses its own short-lived TestClient so the login cookie isn't stored
    in the shared app_client and doesn't bleed into other tests.
    """
    with TestClient(_app) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "test-password"},
        )
        assert response.status_code == 200, response.text
        return {"session_id": response.cookies["session_id"]}


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_protected_route_returns_401_without_cookie(
    app_client: TestClient, method: str, path: str
) -> None:
    response = app_client.request(method, path)
    assert (
        response.status_code == 401
    ), f"{method} {path} expected 401, got {response.status_code}: {response.text}"
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_protected_route_accepts_valid_cookie(
    app_client: TestClient, authed_cookie: dict[str, str], method: str, path: str
) -> None:
    response = app_client.request(method, path, cookies=authed_cookie)
    # We don't care about the business response shape — only that the
    # auth gate let the request through. Any non-401 is a pass.
    assert (
        response.status_code != 401
    ), f"{method} {path} unexpectedly returned 401 with valid cookie"


def test_auth_routes_are_open(app_client: TestClient) -> None:
    """The auth router itself must NOT require auth — login can't require login."""
    response = app_client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False}


def test_websocket_rejects_unauthenticated_connection(app_client: TestClient) -> None:
    """Per Phase 3: /ws closes with code 4401 when no valid session cookie."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with app_client.websocket_connect("/ws"):
            pass

    assert exc_info.value.code == 4401


def test_websocket_accepts_authenticated_connection(
    app_client: TestClient, authed_cookie: dict[str, str]
) -> None:
    """With a valid session cookie, the WS handshake succeeds."""
    with app_client.websocket_connect("/ws", cookies=authed_cookie) as ws:
        ws.close()
