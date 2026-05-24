# Finish Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the existing-but-unwired authentication subsystem from "paper door" to "real door" — wire `require_auth` to every protected route, harden the known weaknesses (login timing attack, blocking bcrypt, no session rotation, missing WS auth, wrong `WWW-Authenticate` header, non-conditional `secure` cookie flag), and add the route-coverage tests that prove every endpoint actually enforces auth.

**Architecture:** Seven small commits, each leaving the tree green:
1. Refactor `require_auth` from factory pattern to a proper FastAPI dependency that pulls `auth_manager` off `request.app.state`.
2. Apply `dependencies=[Depends(require_auth)]` at every protected `app.include_router(...)` call.
3. Add cookie-session auth to the `/ws` WebSocket endpoint.
4. Harden `AuthManager.login()`: equalize timing (always run bcrypt), move bcrypt to a thread, rotate session ID on login.
5. Make the `secure` cookie attribute conditional on SSL configuration.
6. Add integration tests proving each protected route returns 401 without cookie and works with one.
7. Bootstrap UX: loud startup warning when `count_users() == 0`, plus README + CLAUDE.md instructions.

**Tech Stack:** FastAPI, `bcrypt`, `slowapi` (already installed). No new dependencies.

---

## Constitution clauses invoked

`agent-instructions/coding/constitution/general.md`:
- §11 "Every endpoint enforces auth. No exceptions." — currently zero routes enforce; we fix this.
- §12 "Every public function has at least one test. Every error path has a test. Every tenant/ownership boundary has an isolation test." — we add route-level 401 tests.
- §6 "Never swallow exceptions" — the existing `try/except Exception: return False` in `verify_password` is overbroad; cleanup is a side effect of the login refactor.

`agent-instructions/coding/constitution/python.md`:
- "Async routes by default. Sync routes block the event loop." — `bcrypt.checkpw` is the violation; we move it to `asyncio.to_thread`.

---

## Surface area (from prior survey)

Protected routers in `src/rotary_phone/web/app.py` (around lines 188-195):
1. `sounds_router`
2. `settings_router`
3. `logs_router`
4. `calls_router`
5. `allowlist_router`
6. `speed_dial_router`
7. `network_router`

Plus the `/ws` WebSocket endpoint (around app.py:202).

Auth router (`auth_router`) stays unauthenticated — login can't require login.

---

## File Structure

Files **modified**:
- `src/rotary_phone/web/auth.py` — refactor `require_auth`, harden `login()`, add `_DUMMY_HASH`.
- `src/rotary_phone/web/routes/auth.py` — `await auth_manager.login(...)`, pass current session for rotation, conditional `secure=` on cookie.
- `src/rotary_phone/web/app.py` — `dependencies=[Depends(require_auth)]` on 7 router includes; auth check in `websocket_endpoint`.
- `src/rotary_phone/main.py` — startup warning when `count_users() == 0`.
- `tests/test_auth.py` — update `TestRequireAuth` to the new dependency signature; add timing-equalization + session-rotation tests for `login()`.
- `README.md`, `CLAUDE.md` — bootstrap docs.

Files **created**:
- `tests/test_route_auth.py` — integration tests proving 401 + 200 on every protected route, plus WS auth.

---

## Pre-flight

### Task 0: Baseline

- [ ] **Step 0.1:** `git status --short` → expect empty.
- [ ] **Step 0.2:** `uv run pytest -q | tail -3` → expect `279 passed`.
- [ ] **Step 0.3:** `./check.sh 2>&1 | tail -3` → expect `✅ All checks passed!`.

---

## Phase 1 — Refactor `require_auth` to a real FastAPI dependency

### Task 1: Make `require_auth` a top-level async dependency

**Why:** The current factory pattern (`require_auth(auth_manager) -> dependency_fn`) can't be used with `Depends(require_auth)` because `app.state.auth_manager` doesn't exist at handler-definition time. Pull it off `request.app.state` at request time instead.

**Files:**
- Modify: `src/rotary_phone/web/auth.py:185-218`
- Modify: `tests/test_auth.py` — `TestRequireAuth` class (3 tests)

- [ ] **Step 1.1:** Replace the `require_auth` factory

In `src/rotary_phone/web/auth.py`, delete lines 184-218 (the comment header + factory function) and replace with:

```python
async def require_auth(
    request: Request,
    session_id: Optional[str] = Cookie(None, alias="session_id"),
) -> User:
    """FastAPI dependency: returns the current User or raises 401.

    Pulls AuthManager off request.app.state so routes can use
    Depends(require_auth) directly without a factory closure.
    """
    auth_manager: AuthManager = request.app.state.auth_manager
    user = auth_manager.get_current_user(session_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
```

Add `from fastapi import Request` to the imports at the top (the existing import line is `from fastapi import Cookie, HTTPException, status` — extend it). Drop the unused `status` import (we hard-code 401 now) and the unused `Callable`, `Coroutine`, `Any` from `typing`.

Removed: the misleading `WWW-Authenticate: Bearer` header (this is cookie auth, not Bearer tokens).

- [ ] **Step 1.2:** Update `TestRequireAuth` in `tests/test_auth.py`

The existing 3 tests call `require_auth(auth_manager)` as a factory. Now `require_auth` IS the dependency. Tests need to call it directly:

```python
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException


class TestRequireAuth:
    """Tests for the require_auth FastAPI dependency."""

    async def test_returns_user_for_valid_session(self, test_user) -> None:
        request = MagicMock()
        request.app.state.auth_manager.get_current_user.return_value = test_user

        result = await require_auth(request=request, session_id="valid-session-id")

        assert result is test_user
        request.app.state.auth_manager.get_current_user.assert_called_once_with("valid-session-id")

    async def test_raises_401_when_no_cookie(self) -> None:
        request = MagicMock()
        request.app.state.auth_manager.get_current_user.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request=request, session_id=None)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Not authenticated"

    async def test_raises_401_when_session_invalid(self) -> None:
        request = MagicMock()
        request.app.state.auth_manager.get_current_user.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request=request, session_id="expired-or-fake")

        assert exc_info.value.status_code == 401
```

Read the existing `TestRequireAuth` (around `test_auth.py:265-302`) to see what the current tests look like, delete them all, and replace with the three above. Make sure each test method is marked `@pytest.mark.asyncio` if the test runner needs it (check whether the project uses pytest-asyncio's auto mode — `grep asyncio_mode pyproject.toml`).

- [ ] **Step 1.3:** Run the affected tests

```bash
uv run pytest tests/test_auth.py -v
```

Expected: all tests pass, including the rewritten `TestRequireAuth` (3 tests).

- [ ] **Step 1.4:** Full quality gate

```bash
./check.sh 2>&1 | tail -3
```

Expected: green.

- [ ] **Step 1.5:** Commit

```bash
git add src/rotary_phone/web/auth.py tests/test_auth.py
git commit -m "$(cat <<'EOF'
refactor(auth): make require_auth a real FastAPI dependency

The previous factory pattern (require_auth(auth_manager) -> dependency)
couldn't be used with Depends() because app.state.auth_manager isn't
available at handler-definition time. The factory was defined and
tested but never actually used in any route — that's why the admin
interface had no enforcement.

Now require_auth is a normal async dependency that pulls auth_manager
off request.app.state at request time. Routes can use
Depends(require_auth) directly. Wiring lands in the next commit.

Also dropped the misleading WWW-Authenticate: Bearer header on the
401 response (this is cookie auth, not Bearer tokens).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Wire `Depends(require_auth)` to all 7 routers

### Task 2: Protect every router at the include point

**Why:** Per-route decoration would be 7+ files × N routes; one line per router at the include point is cleaner and impossible to forget on a new route.

**Files:**
- Modify: `src/rotary_phone/web/app.py` — router-include block (around lines 188-195)

- [ ] **Step 2.1:** Add the dependency import and protected-include constant

In `src/rotary_phone/web/app.py`, add to imports (already imports `Depends`-friendly things; verify `from fastapi import Depends` or add it):

```python
from fastapi import Depends
```

(Likely already imported as part of the existing FastAPI import line — check.)

Add this import:

```python
from rotary_phone.web.auth import AuthManager, require_auth
```

(The existing line imports `AuthManager` only — extend it to include `require_auth`.)

Just above the router-include block (around line 187), add:

```python
# Every router except the auth router itself requires a valid session cookie.
# Adding the dependency here (rather than per-route) guarantees a new endpoint
# can't be accidentally exposed.
_protected = [Depends(require_auth)]
```

- [ ] **Step 2.2:** Update the include calls

Find the existing block around lines 188-195:

```python
    app.include_router(auth_router)
    app.include_router(sounds_router)
    app.include_router(settings_router)
    app.include_router(logs_router)
    app.include_router(calls_router)
    app.include_router(allowlist_router)
    app.include_router(speed_dial_router)
    app.include_router(network_router)
```

Replace with:

```python
    app.include_router(auth_router)  # NOT protected — login can't require login
    app.include_router(sounds_router, dependencies=_protected)
    app.include_router(settings_router, dependencies=_protected)
    app.include_router(logs_router, dependencies=_protected)
    app.include_router(calls_router, dependencies=_protected)
    app.include_router(allowlist_router, dependencies=_protected)
    app.include_router(speed_dial_router, dependencies=_protected)
    app.include_router(network_router, dependencies=_protected)
```

- [ ] **Step 2.3:** Run unit tests

```bash
uv run pytest -q 2>&1 | tail -5
```

Expected: existing tests still pass. The integration tests proving 401 land in Phase 6 — for now, no test broke means routes still work for authenticated requests (which the existing tests implicitly are, since the test fixtures don't simulate cookies).

**If anything fails:** the most likely cause is a test that hits a protected route through an in-process AsyncClient and now gets 401. Note the failing test; we'll either need to give it a fixture-mocked auth_manager or rewrite it. Report DONE_WITH_CONCERNS and we'll discuss before continuing.

- [ ] **Step 2.4:** Quick smoke test that 401s actually fire

```bash
uv run pytest -q 2>&1 | tail -3
./check.sh 2>&1 | tail -3
```

Both green.

- [ ] **Step 2.5:** Commit

```bash
git add src/rotary_phone/web/app.py
git commit -m "$(cat <<'EOF'
feat(web): enforce require_auth on every non-auth router

Seven include_router calls (sounds, settings, logs, calls, allowlist,
speed_dial, network) now declare dependencies=[Depends(require_auth)].
auth_router itself stays unauthenticated — login can't require login.

This closes the staff-review finding that "auth was scaffolded but
never enforced." Requests without a valid session cookie now get 401
on every admin endpoint. Integration tests proving this for every
route land in Phase 6.

The WebSocket /ws endpoint is still unauthenticated; that's the next
commit (cookie-session validation on WebSocket isn't expressible
through Depends).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3 — Authenticate the WebSocket

### Task 3: Add cookie-session validation to `/ws`

**Why:** WebSocket auth doesn't compose with `Depends(require_auth)` — there's no HTTP response to return 401 on. The pattern is: accept the connection, validate, then close with a specific WS close code if invalid.

**Files:**
- Modify: `src/rotary_phone/web/app.py` — `websocket_endpoint` (around line 202)

- [ ] **Step 3.1:** Replace the `websocket_endpoint` body

Find the existing handler (`@app.websocket("/ws")`) at around line 202. The current body opens the connection and reads messages. Update to validate first:

```python
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time updates. Requires a valid
        session cookie; otherwise rejects with WS close code 4401."""
        session_id = websocket.cookies.get("session_id")
        auth_manager: AuthManager = websocket.app.state.auth_manager
        if auth_manager.get_current_user(session_id) is None:
            await websocket.close(code=4401, reason="Not authenticated")
            return

        ws_manager: ConnectionManager = websocket.app.state.ws_manager
        await ws_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await ws_manager.disconnect(websocket)
        except Exception as e:
            logger.error("WebSocket error: %s", e)
            await ws_manager.disconnect(websocket)
```

Read the existing handler to see the exact current shape before replacing. The wrapping `try/except` block likely already exists; if so, preserve its semantics and only insert the auth-check prelude.

WS close code 4401 is in the application-private range (4000-4999). The pattern (close-with-4401-then-return) is conventional for "would have been 401 over HTTP."

- [ ] **Step 3.2:** Run tests

```bash
uv run pytest tests/test_websocket.py -v 2>&1 | tail -10
```

Expected: existing WS tests still pass. If any test connects without supplying a session_id and expects messages, it will now get a close immediately. Note any test that breaks; we'll wire fixtures in Phase 6 if so.

- [ ] **Step 3.3:** Full gate

```bash
./check.sh 2>&1 | tail -3
```

Green.

- [ ] **Step 3.4:** Commit

```bash
git add src/rotary_phone/web/app.py
git commit -m "$(cat <<'EOF'
feat(web): require valid session cookie for /ws WebSocket

Cookie-session auth doesn't compose with Depends() — there's no HTTP
response to return 401 on. Pattern: accept, validate, then close with
WS code 4401 if invalid. 4401 is in the application-private range
(4000-4999) and conventionally signals "would have been 401 over HTTP."

A WS test that proves unauth connections get rejected lands in Phase 6
alongside the route-level integration tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4 — Harden `login()`: timing, blocking, session rotation

### Task 4: Fix all three login bugs in one cohesive commit

**Why:** All three issues live in the same `AuthManager.login()` codepath and fixing one without the others would leave a still-broken function. Bundling.

**Files:**
- Modify: `src/rotary_phone/web/auth.py` — add `_DUMMY_HASH`, make `verify_password`/`login` async, equalize timing, rotate session
- Modify: `src/rotary_phone/web/routes/auth.py` — `await auth_manager.login(...)`, pass current session for rotation
- Modify: `tests/test_auth.py` — update `TestAuthManager.test_login_*` to be `async` and add new tests for the three fixes

- [ ] **Step 4.1:** Add `_DUMMY_HASH` module constant in `auth.py`

After the imports and before `class SessionStore`, add:

```python
# Pre-computed bcrypt hash used to equalize the timing of failed logins
# regardless of whether the username exists. Computed once at module load
# (~100ms one-time cost) so login() doesn't reveal user-existence via timing.
_DUMMY_HASH: Final[bytes] = bcrypt.hashpw(b"dummy", bcrypt.gensalt())
```

Add `from typing import Final` (or extend the existing `from typing` line). If `Final` is not yet imported anywhere in the project, that's fine — it's stdlib.

- [ ] **Step 4.2:** Rewrite `AuthManager.login` and remove `verify_password`

Replace the existing `verify_password` (lines ~110-124) and `login` (lines ~126-155) with this single async `login`:

```python
    async def login(
        self,
        username: str,
        password: str,
        current_session_id: Optional[str] = None,
    ) -> Optional[str]:
        """Authenticate user and create a new session.

        Always runs bcrypt — even when the username is unknown — so that
        timing doesn't reveal user existence. Runs bcrypt in a worker thread
        so the FastAPI event loop isn't blocked for ~100ms per attempt.

        If current_session_id is provided (i.e. the request already had a
        session cookie), that session is invalidated before the new one is
        minted — defends against session-fixation.
        """
        password_bytes = password.encode("utf-8")
        user = self.database.get_user_by_username(username)

        if user is None or user.id is None:
            # Run bcrypt anyway to keep the timing flat — prevents enumeration.
            await asyncio.to_thread(bcrypt.checkpw, password_bytes, _DUMMY_HASH)
            logger.warning("Login failed: user not found or has no id: %s", username)
            return None

        password_ok = await asyncio.to_thread(
            bcrypt.checkpw, password_bytes, user.password_hash.encode("utf-8")
        )
        if not password_ok:
            logger.warning("Login failed: invalid password for user: %s", username)
            return None

        # Rotate: invalidate any prior session before minting a new one.
        if current_session_id:
            self.sessions.delete_session(current_session_id)

        session_id = self.sessions.create_session(user.id)
        logger.info("User logged in: %s (user_id=%d)", username, user.id)
        return session_id
```

Add `import asyncio` to the top of the file.

`verify_password` is deleted because it was only called by `login`; if you find a stray reference elsewhere (`grep -rn verify_password src/ tests/`), inline it.

- [ ] **Step 4.3:** Update `routes/auth.py` to await login and pass current session

In `src/rotary_phone/web/routes/auth.py` around line 46, find:

```python
        session_id = auth_manager.login(username, password)
```

Replace with:

```python
        current_session_id = request.cookies.get("session_id")
        session_id = await auth_manager.login(username, password, current_session_id)
```

- [ ] **Step 4.4:** Update existing `TestAuthManager` tests to be async

Find every test in `tests/test_auth.py::TestAuthManager` that calls `auth_manager.login(...)`. Each must:
1. Have `async def test_…` instead of `def test_…`.
2. `await` the login call.
3. Be marked with `@pytest.mark.asyncio` if the project doesn't use `asyncio_mode = "auto"` (check `pyproject.toml`).

Also delete or update any test that directly calls `verify_password` (since the method is gone). Pure-helper tests of `bcrypt.checkpw` aren't useful — drop them.

- [ ] **Step 4.5:** Add the three new tests

In `tests/test_auth.py::TestAuthManager`, add:

```python
    async def test_login_runs_bcrypt_even_for_missing_user(self, mocker, temp_db) -> None:
        """Timing-attack guard: bcrypt.checkpw must be called regardless of
        whether the username exists, so an attacker can't enumerate users
        by measuring response times."""
        # Capture the synchronous bcrypt.checkpw that AuthManager.login wraps in to_thread.
        check_spy = mocker.spy(bcrypt, "checkpw")

        manager = AuthManager(temp_db)
        result = await manager.login("nobody-exists", "anything")

        assert result is None
        assert check_spy.call_count == 1, "bcrypt must run for unknown users too"

    async def test_login_rotates_session_when_cookie_present(
        self, temp_db, test_user
    ) -> None:
        """Calling login with a prior session_id invalidates it and mints a
        fresh one — defends against session fixation."""
        manager = AuthManager(temp_db)

        first = await manager.login(test_user.username, "test-password")
        assert first is not None
        assert manager.sessions.get_user_id(first) == test_user.id

        second = await manager.login(test_user.username, "test-password", current_session_id=first)

        assert second is not None
        assert second != first
        assert manager.sessions.get_user_id(first) is None, "old session must be invalidated"
        assert manager.sessions.get_user_id(second) == test_user.id

    async def test_login_does_not_block_event_loop(self, temp_db, test_user) -> None:
        """login() must run bcrypt in a worker thread so the event loop stays
        responsive. Use mocker to confirm asyncio.to_thread is invoked."""
        to_thread_spy = mocker.spy(asyncio, "to_thread")

        manager = AuthManager(temp_db)
        await manager.login(test_user.username, "test-password")

        # The first to_thread call should be for bcrypt.checkpw.
        assert to_thread_spy.call_count >= 1
```

`mocker` is `pytest-mock`'s fixture. If pytest-mock isn't installed, add it as a dev dep:

```bash
uv add --dev pytest-mock
```

Verify the existing `test_user` fixture's plaintext password is `"test-password"` (or whatever it actually uses) — adjust the test strings to match. Read `tests/test_auth.py:26-35` to confirm.

- [ ] **Step 4.6:** Run tests + check.sh

```bash
uv run pytest tests/test_auth.py -v 2>&1 | tail -15
./check.sh 2>&1 | tail -3
```

Both green. If pytest-asyncio complains about missing config, add to `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
asyncio_mode = "auto"
```

- [ ] **Step 4.7:** Commit

```bash
git add src/rotary_phone/web/auth.py src/rotary_phone/web/routes/auth.py tests/test_auth.py pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
fix(auth): equalize login timing, run bcrypt off the event loop, rotate session

Three fixes in the same code path:

- Timing-attack guard. login() previously returned immediately when
  the username wasn't found, taking microseconds; valid-username paths
  ran bcrypt (~100ms). An attacker could trivially distinguish the two
  and enumerate valid usernames. Now bcrypt runs in both branches,
  comparing the supplied password against a module-level dummy hash if
  the user doesn't exist.

- Blocking work on the event loop. bcrypt.checkpw is CPU-bound and
  takes ~100ms; calling it from an async route handler stalls the
  whole loop. Now wrapped in asyncio.to_thread.

- Session fixation. login() previously created a new session_id but
  left any prior session active. If a request already carried a
  session cookie, an attacker who knew it could keep using it after
  the real user logged in. Now login() accepts an optional
  current_session_id and invalidates it before minting the new one.

verify_password() was deleted (it was only called by login). Added
pytest-mock for the new spy-based tests.

Closes staff-review findings on login timing, blocking-on-event-loop,
and session-fixation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 5 — Conditional `secure` cookie

### Task 5: Set `secure=True` on the session cookie when SSL is configured

**Why:** A cookie without `secure=True` can be sent over plain HTTP; a passive observer on the LAN can grab it. But if the app is sometimes deployed on HTTP (no SSL config), forcing `secure=True` would mean the cookie is never set. Compromise: conditional on whether SSL certs are configured.

**Files:**
- Modify: `src/rotary_phone/web/routes/auth.py` — `login` handler cookie set

- [ ] **Step 5.1:** Make `secure` conditional on SSL config

In `src/rotary_phone/web/routes/auth.py` around line 52, find:

```python
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=3600,
            samesite="lax",
        )
```

Replace with:

```python
        # secure=True only when SSL is configured — otherwise the cookie
        # would never be set in HTTP-only LAN deployments.
        config_manager = request.app.state.config_manager
        use_secure = bool(
            config_manager.get("web.ssl_certfile") and config_manager.get("web.ssl_keyfile")
        )
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=use_secure,
        )
```

- [ ] **Step 5.2:** Verify `config_manager` is on `app.state`

```bash
grep -n "app.state.config_manager" src/rotary_phone/web/app.py
```

Expected: at least one match (the existing app wiring already stores it). If not, the install line is at around app.py:117 — add `app.state.config_manager = config_manager` if missing.

- [ ] **Step 5.3:** Tests + gate

```bash
uv run pytest tests/test_auth.py -v 2>&1 | tail -10
./check.sh 2>&1 | tail -3
```

Both green.

- [ ] **Step 5.4:** Commit

```bash
git add src/rotary_phone/web/routes/auth.py
git commit -m "$(cat <<'EOF'
fix(auth): set secure=True on session cookie when SSL is configured

A session cookie without secure=True is sent over plain HTTP, so a
passive LAN observer can capture it. Always forcing secure=True would
break HTTP-only LAN deployments (the cookie would never be set).

Compromise: condition secure= on whether web.ssl_certfile +
web.ssl_keyfile are configured. HTTPS deployments get the protection;
HTTP deployments keep working as they do today.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 6 — Integration tests for every protected route

### Task 6: Prove the wiring at the route level

**Why:** Phase 2 added one-line `dependencies=` to each include_router. Per constitution §12, every error path needs a test. We add a parametrized integration test that hits each protected endpoint without and with a session cookie, plus a WS test for Phase 3.

**Files:**
- Create: `tests/test_route_auth.py`

- [ ] **Step 6.1:** Write the test file

Create `tests/test_route_auth.py`:

```python
"""Integration tests proving every protected route enforces auth.

Hits each router's primary endpoints with and without a session cookie
and asserts the right status code. The point isn't to test the routes'
business logic — it's to prove the auth wiring is correct and stays
correct as routes are added.
"""

from __future__ import annotations

import bcrypt
import pytest
from fastapi.testclient import TestClient

from rotary_phone.config import ConfigManager
from rotary_phone.database.database import Database
from rotary_phone.database.models import User
from rotary_phone.web.app import create_app


# Pairs of (method, path) covering at least one endpoint per protected router.
# Adding a new endpoint? Add a pair here so the auth wiring is verified.
PROTECTED_ENDPOINTS: list[tuple[str, str]] = [
    ("GET", "/api/sounds"),
    ("GET", "/api/settings"),
    ("GET", "/api/logs"),
    ("GET", "/api/calls"),
    ("GET", "/api/allowlist"),
    ("GET", "/api/speed-dial"),
    ("GET", "/api/network"),
]


@pytest.fixture
def app_client(tmp_path):
    """Build a real FastAPI app over a temp DB with one seeded user."""
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    db.init_db()

    password_hash = bcrypt.hashpw(b"test-password", bcrypt.gensalt()).decode("utf-8")
    db.add_user(User(username="alice", password_hash=password_hash))

    # Minimal in-memory config — only needs whatever create_app reads.
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "sip: {server: '', username: '', password: ''}\n"
        "timing: {}\n"
        "audio: {}\n"
        "speed_dial: {}\n"
        "allowlist: []\n"
        "web: {enabled: true, host: 0.0.0.0, port: 0}\n"
    )
    config = ConfigManager(user_config_path=str(config_path))

    # CallManager is required by create_app. The simplest path is to use
    # a stand-in that satisfies the constructor — see the existing
    # test_websocket.py fixture for the pattern.
    from unittest.mock import MagicMock
    call_manager = MagicMock()

    app = create_app(
        call_manager=call_manager,
        config_manager=config,
        config_path=str(config_path),
        database=db,
    )
    return TestClient(app)


@pytest.fixture
def authed_cookie(app_client) -> dict[str, str]:
    """Log in as the seeded user and return the cookie jar."""
    response = app_client.post(
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
    assert response.status_code == 401, f"{method} {path} expected 401, got {response.status_code}: {response.text}"
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_protected_route_accepts_valid_cookie(
    app_client: TestClient, authed_cookie: dict[str, str], method: str, path: str
) -> None:
    response = app_client.request(method, path, cookies=authed_cookie)
    # We don't care about the business response shape here — only that the
    # auth gate let the request through. Any non-401 is a pass.
    assert response.status_code != 401, f"{method} {path} unexpectedly returned 401 with valid cookie"


def test_auth_routes_are_open(app_client: TestClient) -> None:
    """The auth router itself must NOT require auth — login can't require login."""
    response = app_client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False}


def test_websocket_rejects_unauthenticated_connection(app_client: TestClient) -> None:
    """Per Phase 3: /ws closes with code 4401 when no valid session cookie."""
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with app_client.websocket_connect("/ws"):
            pass

    assert exc_info.value.code == 4401


def test_websocket_accepts_authenticated_connection(
    app_client: TestClient, authed_cookie: dict[str, str]
) -> None:
    """With a valid session cookie, the WS handshake succeeds."""
    with app_client.websocket_connect("/ws", cookies=authed_cookie) as ws:
        # Connection accepted — that's all we're verifying here.
        ws.close()
```

The exact response shape for protected endpoints (the 200/400/etc. when authed) is router-specific; the test only asserts "not 401" because what's being tested is the gate, not the handler.

- [ ] **Step 6.2:** Verify `httpx` (which FastAPI's TestClient uses) is installed

```bash
grep -E "httpx" pyproject.toml
```

The project already has `httpx>=0.28.1` in `[dependency-groups].dev`. Good.

- [ ] **Step 6.3:** Run the new tests + full gate

```bash
uv run pytest tests/test_route_auth.py -v 2>&1 | tail -25
./check.sh 2>&1 | tail -3
```

Both green. If any of the parametrized 200 assertions fails with a non-401-but-also-not-200 response (e.g., 500 because the mock CallManager raises), inspect: that's a routing bug masked by the previous lack of auth. Either fix the handler or use a more realistic CallManager stand-in.

- [ ] **Step 6.4:** Commit

```bash
git add tests/test_route_auth.py
git commit -m "$(cat <<'EOF'
test(web): prove every protected route enforces auth

Parametrized over the 7 protected routers: each endpoint is hit
without a session cookie (expect 401) and with a valid cookie (expect
not-401). Also verifies the auth router itself stays open, and that
the /ws WebSocket rejects unauthenticated handshakes with code 4401
and accepts authenticated ones.

PROTECTED_ENDPOINTS is a flat list at the top of the file — adding a
new router means adding one line. This is the safety net that catches
"oops, forgot to mark it protected" regressions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 7 — Bootstrap UX + docs

### Task 7: Warn loudly when no users exist, document `manage_users.py`

**Why:** With auth wired, a fresh deployment with `count_users() == 0` is unusable — nobody can log in. Pi-Zero deployers won't remember a CLI command they ran once a year ago. Loud warning + README/CLAUDE.md instructions.

**Files:**
- Modify: `src/rotary_phone/main.py` — startup check
- Modify: `README.md` — bootstrap section
- Modify: `CLAUDE.md` — operations section

- [ ] **Step 7.1:** Add the startup warning

In `src/rotary_phone/main.py`, find where the database is initialized (likely in the init flow near the top of `main()` or in a helper). After `database.init_db()` is called, add:

```python
        if database.count_users() == 0:
            logger.warning("=" * 60)
            logger.warning("NO USERS IN DATABASE — web admin is unreachable.")
            logger.warning("Create one with: uv run python -m scripts.manage_users add <username>")
            logger.warning("=" * 60)
```

Wrap this in a try/except so a database error doesn't kill startup — `count_users()` should always work after `init_db()`, but defense-in-depth on a one-line check is cheap.

- [ ] **Step 7.2:** Update README.md

Find the existing setup section. Add a subsection (or append to setup):

```markdown
### First-run user setup

The web admin requires a login. Create your first user before starting
the service:

    uv run python -m scripts.manage_users add admin

You'll be prompted for a password. Repeat with different usernames to
add more users.

Forgot your password? Delete the user and add it again — passwords
can't be recovered, only reset.
```

- [ ] **Step 7.3:** Update CLAUDE.md operations section

Add to the "Common Development Tasks" or "Development Commands" section:

```markdown
### Managing web admin users

    uv run python -m scripts.manage_users add <username>
    uv run python -m scripts.manage_users list
    uv run python -m scripts.manage_users delete <username>

Users are stored in the SQLite database alongside call logs. Passwords
are bcrypt-hashed. The app refuses to be useful with zero users — a
loud startup warning fires if `count_users() == 0`.
```

- [ ] **Step 7.4:** Tests + gate

```bash
./check.sh 2>&1 | tail -3
```

Green. No new tests needed for documentation changes; the startup warning is best verified by running the app, but a unit test on `main` would mean refactoring it for testability — out of scope.

- [ ] **Step 7.5:** Commit

```bash
git add src/rotary_phone/main.py README.md CLAUDE.md
git commit -m "$(cat <<'EOF'
feat(ops): warn loudly when no users exist + document bootstrap

With auth wired, a fresh deployment with count_users()==0 is
unreachable through the web admin. main.py now logs a big WARNING
block at startup with the exact command to run, and README +
CLAUDE.md document the manage_users.py CLI.

This is the only UX change needed; the existing CLI handles add /
list / delete and bcrypt-hashes passwords at the right point.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 8 — Final verification + plan commit

### Task 8: Plan-file commit + final gate + final review

**Files:**
- Add: this plan file

- [ ] **Step 8.1:** Full gate

```bash
./check.sh
```

Expected: `✅ All checks passed!`.

- [ ] **Step 8.2:** Coverage spot-check

```bash
uv run pytest --cov=src/rotary_phone --cov-report=term -q 2>&1 | grep -E "auth\.py|app\.py|TOTAL"
```

Expected: `web/auth.py` coverage **higher** than baseline (we added tests). `web/app.py` slight change but acceptable. TOTAL same or up.

- [ ] **Step 8.3:** Commit the plan

```bash
git add docs/superpowers/plans/2026-05-23-finish-auth.md
git commit -m "$(cat <<'EOF'
docs: add the finish-auth plan

The plan that drove Phases 1-7: refactor require_auth, wire it to
every protected router, add WS auth, harden login (timing /
blocking / session fixation), conditional secure cookie, integration
tests, and bootstrap warning + docs. Kept on disk as the record of
scope and rationale.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 8.4:** Inspect the commit list

```bash
git log --oneline -n 9
```

Expected: 8 commits from this plan (Phases 1-7 commits + the plan commit), all on `main`.

---

## Self-Review

**Spec coverage:** the user said "fix it up." That includes wiring (Phase 2), WS coverage (Phase 3), and the three login bugs the staff review and I called out (Phase 4). Bonus phases: refactoring `require_auth` so wiring is even possible (Phase 1), conditional `secure` cookie because the user runs both HTTP and HTTPS modes (Phase 5), integration tests proving the wiring (Phase 6), bootstrap UX so the wiring doesn't lock them out of their own device (Phase 7). I think Phase 5 and Phase 7 might be more than the user explicitly asked for — flag at execution time and offer to drop if scope is creeping.

**Placeholder scan:** every step has either exact code or specific instructions. The closest things to placeholders are step 3.1 ("Read the existing handler... preserve its semantics") and step 7.1 ("find where the database is initialized") — both are because I can't quote code I haven't read in context. Both include the exact replacement structure.

**Coupling:** Phase 4 is the most complex (one commit, three behavior changes, async-conversion ripple). If it grows beyond ~150 lines of diff, split into 4a (timing) / 4b (asyncify) / 4c (rotation). I'm betting on bundling because all three change the same function and would otherwise require three separate test-fixture updates.

**Ordering verified:** 1 (refactor) → 2 (wire) → 3 (WS) → 4 (harden) → 5 (secure cookie) → 6 (tests) → 7 (docs) → 8 (final). Tests in Phase 6 prove the wiring from Phase 2 + Phase 3; you could move Phase 6 earlier but that means writing tests against the wiring-not-yet-applied. Wire first, prove second, harden the still-working flow, then test what was hardened.

**Bootstrap concern:** Phase 7's warning fires only if `count_users() == 0`. After Phase 7 lands, **the user must run `manage_users.py add` before the next deployment** or they'll lock themselves out. Flag at execution time.
