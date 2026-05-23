# Test Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete every test in `tests/` that does not prove production behavior, using the engineering constitution at `agent-instructions/coding/constitution/general.md` §12 as the standard.

**Architecture:** Each task targets a single test file, removes the worthless tests, prunes the now-unused imports, runs the suite to confirm nothing else relied on them, and commits. Conservative deletion only — tests that exercise real code but assert weakly are flagged for a *follow-up* rewrite plan, not deleted here.

**Tech Stack:** pytest, uv, ruff (not yet installed — current project still uses black/mypy/pylint via `check.sh`; tooling migration is out of scope for this plan).

---

## Constitution clauses driving deletion

From `agent-instructions/coding/constitution/general.md` §12 "Testing":

> **"Tests must prove behavior, not existence. `assertNotNull` / `isNotEmpty` are banned as terminal assertions on success-path values — they may precede deeper checks, never replace them."**
>
> **"Code called only by tests is dead. Delete the code and its tests. Tests exist to verify production behavior."**

Each deletion in this plan is justified by one of:

| Code | Justification |
|---|---|
| **TAUT** | Tautology: asserts a module constant equals its own literal value. Cannot fail unless the constant is renamed, and even then a rename would also rename the test. |
| **EXC** | Exception-existence test: constructs an exception class and asserts `str(e) == "..."` or `isinstance(e, Base)`. Tests Python's exception inheritance, not our code. |
| **TERM** | Banned terminal assertion: `len(x) == N` or `x is not None` is the *only* check on a success-path value, with no field verification. |
| **DUP** | Behavior already proven by a stronger test in the same file. |
| **PRIV** | Asserts against private state (`store._sessions[id]`, `_state`) rather than the public method that exposes that state — by construction the assertion mirrors the setup. |

A test that hits multiple clauses (e.g., TERM + PRIV) gets deleted, full stop. A test that is TERM-only but exercises a real branch is kept and flagged for the follow-up rewrite plan.

---

## File Structure

No files created. Deletions only:

| File | Tests deleted | Justification codes |
|---|---|---|
| `tests/test_audio_handler.py` | `TestAudioFormatConstants::test_sample_rate`, `test_frame_size`, `TestAudioErrors::test_audio_error_base`, `test_audio_device_not_found_error` | TAUT, EXC |
| `tests/test_gpio.py` | `test_pin_constants` | TAUT |
| `tests/test_auth.py` | `TestSessionStore::test_create_session`, `test_create_session_stores_user_id` | TERM+PRIV, DUP+PRIV |
| `tests/test_websocket.py` | `TestConnectionManager::test_connection_count_property` | TERM |

Total: **7 test functions across 4 files.**

---

## Pre-flight

### Task 0: Baseline

**Files:** none modified.

- [ ] **Step 0.1: Confirm working tree state**

Run: `git status --short`
Expected: the repo is in the middle of unrelated work (multiple `M` lines from a prior commit on audio resampling). **Do not stage or commit those files in this plan.** Each task will explicitly `git add` only the test file it touched.

- [ ] **Step 0.2: Confirm baseline test suite is green**

Run: `uv run pytest -q`
Expected: all tests pass (or skipped). If anything fails before you start, stop and report — you must not delete tests against a broken baseline.

- [ ] **Step 0.3: Capture baseline coverage of the modules under test**

Run: `uv run pytest --cov=src/rotary_phone --cov-report=term tests/test_audio_handler.py tests/test_gpio.py tests/test_auth.py tests/test_websocket.py 2>&1 | tail -30`

Record the coverage percentages for `audio_handler.py`, `gpio_abstraction.py`, `web/auth.py`, `web/websocket/manager.py`, `web/websocket/events.py`. After Task 4 you'll re-run and confirm none of these dropped — a drop would mean a deleted test was the *only* caller of some production path, and you need to add a real test for that path before merging.

---

## Phase 1 — Tautology and exception-existence deletions

### Task 1: Delete tautology + exception-existence tests in `test_audio_handler.py`

**Files:** Modify `tests/test_audio_handler.py`

- [ ] **Step 1.1: Verify the target tests are still what the plan describes**

Run: `uv run pytest tests/test_audio_handler.py::TestAudioFormatConstants -v && uv run pytest "tests/test_audio_handler.py::TestAudioErrors::test_audio_error_base" "tests/test_audio_handler.py::TestAudioErrors::test_audio_device_not_found_error" -v`
Expected: all four tests PASS. If any are already gone or refactored, stop and re-read the file before continuing.

- [ ] **Step 1.2: Delete `TestAudioFormatConstants` class and its two methods**

Edit `tests/test_audio_handler.py`. Remove the entire block currently at lines 268–277:

```python
class TestAudioFormatConstants:
    """Tests for audio format constants."""

    def test_sample_rate(self) -> None:
        """Test sample rate constant."""
        assert VOIP_SAMPLE_RATE == 8000

    def test_frame_size(self) -> None:
        """Test frame size constant."""
        assert VOIP_FRAME_SIZE == 160
```

Reason (TAUT): these assert a module constant equals its own literal value. If somebody changes `VOIP_SAMPLE_RATE` from 8000 to 16000 (a real, valid change), the test fails purely because the literal differs — the test catches the literal divergence, not a behavior regression. There is no production code that branches on this value being 8000 specifically; the constant is just read.

- [ ] **Step 1.3: Delete `test_audio_error_base` and `test_audio_device_not_found_error`**

Remove the two methods inside `TestAudioErrors` (currently lines 283–292):

```python
def test_audio_error_base(self) -> None:
    """Test AudioError base exception."""
    err = AudioError("test error")
    assert str(err) == "test error"

def test_audio_device_not_found_error(self) -> None:
    """Test AudioDeviceNotFoundError exception."""
    err = AudioDeviceNotFoundError("device not found")
    assert str(err) == "device not found"
    assert isinstance(err, AudioError)
```

**Keep** `test_pyaudio_import_error` (currently line 294) — it actually exercises `AudioHandler.start()` and proves it raises `AudioError` when pyaudio is missing. That's real behavior.

Reason (EXC): the deleted tests construct an exception and verify Python's built-in `Exception.__str__` and `isinstance` mechanics. They would still pass if `AudioError` and `AudioDeviceNotFoundError` were empty subclasses with no project-specific behavior — which they are. We are not testing our code; we are testing Python.

- [ ] **Step 1.4: Remove now-unused imports**

Check the top of `tests/test_audio_handler.py`. If `VOIP_SAMPLE_RATE` or `VOIP_FRAME_SIZE` is imported and no other test in the file references them, remove those names from the import. `AudioError` and `AudioDeviceNotFoundError` are still referenced by `test_pyaudio_import_error` — leave them.

Run: `grep -n "VOIP_SAMPLE_RATE\|VOIP_FRAME_SIZE" tests/test_audio_handler.py`
Expected: zero matches outside the import line. If matches remain, do not remove the imports.

- [ ] **Step 1.5: Run the affected test file**

Run: `uv run pytest tests/test_audio_handler.py -v`
Expected: every remaining test passes; collected-test count drops by exactly 4 versus the baseline.

- [ ] **Step 1.6: Run the full suite to catch any cross-file fallout**

Run: `uv run pytest -q`
Expected: all green. Anything that fails means a deleted test was the only caller of something that another test now needs — investigate before continuing.

- [ ] **Step 1.7: Commit**

```bash
git add tests/test_audio_handler.py
git commit -m "test(audio): delete tautology and exception-existence tests

Removed TestAudioFormatConstants (constants asserting their own
literal value) and two TestAudioErrors methods that only verified
Python's exception inheritance. See
docs/superpowers/plans/2026-05-23-test-cleanup.md."
```

---

### Task 2: Delete tautology test in `test_gpio.py`

**Files:** Modify `tests/test_gpio.py`

- [ ] **Step 2.1: Verify the target test**

Run: `uv run pytest tests/test_gpio.py::test_pin_constants -v`
Expected: PASS.

- [ ] **Step 2.2: Delete `test_pin_constants`**

Edit `tests/test_gpio.py`. Remove lines 18–23:

```python
def test_pin_constants() -> None:
    """Test that pin constants are defined."""
    assert HOOK == 17
    assert DIAL_PULSE == 27
    assert DIAL_ACTIVE == 22
    assert RINGER == 23
```

Reason (TAUT): the pin assignments are documented in `CLAUDE.md` and consumed by hardware modules — *if* a pin number changes intentionally, this test fails purely because the literal moved, not because behavior regressed. No production logic checks "pin 17 is the hook pin"; the constant is the contract.

- [ ] **Step 2.3: Check whether the now-unused imports can be pruned**

Run: `grep -n "HOOK\|DIAL_PULSE\|DIAL_ACTIVE\|RINGER" tests/test_gpio.py`
Expected: matches remain (other tests use HOOK and DIAL_PULSE). Do not remove the imports.

- [ ] **Step 2.4: Run the affected test file**

Run: `uv run pytest tests/test_gpio.py -v`
Expected: every remaining test passes; collected-test count drops by exactly 1.

- [ ] **Step 2.5: Run the full suite**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 2.6: Commit**

```bash
git add tests/test_gpio.py
git commit -m "test(gpio): delete pin-constant tautology

test_pin_constants asserted pin numbers equal their own literal
values, which catches renames-by-tests rather than behavior
regressions. See
docs/superpowers/plans/2026-05-23-test-cleanup.md."
```

---

## Phase 2 — Banned-terminal and duplicate-coverage deletions

### Task 3: Delete weak terminal + private-state tests in `test_auth.py`

**Files:** Modify `tests/test_auth.py`

- [ ] **Step 3.1: Verify the target tests and the test that subsumes them**

Run: `uv run pytest "tests/test_auth.py::TestSessionStore::test_create_session" "tests/test_auth.py::TestSessionStore::test_create_session_stores_user_id" "tests/test_auth.py::TestSessionStore::test_get_user_id_valid_session" -v`
Expected: all three PASS. The third one (`test_get_user_id_valid_session`) covers the behavior — if it doesn't, stop and re-read the file before deleting.

- [ ] **Step 3.2: Delete `test_create_session` and `test_create_session_stores_user_id`**

Edit `tests/test_auth.py`. Remove the two methods currently at lines 53–68:

```python
def test_create_session(self) -> None:
    """Test creating a new session."""
    store = SessionStore()
    session_id = store.create_session(user_id=1)

    assert session_id is not None
    assert len(session_id) > 20  # Secure token should be long
    assert session_id in store._sessions

def test_create_session_stores_user_id(self) -> None:
    """Test that session stores correct user ID."""
    store = SessionStore()
    session_id = store.create_session(user_id=42)

    user_id, _ = store._sessions[session_id]
    assert user_id == 42
```

Reason for `test_create_session` (TERM + PRIV): the two checks `session_id is not None` and `len(session_id) > 20` are the constitution's banned terminal pattern. The third check `session_id in store._sessions` reaches into the private dict; the public behavior — "after create, the session resolves to the right user" — is already proven by `test_get_user_id_valid_session` immediately below.

Reason for `test_create_session_stores_user_id` (DUP + PRIV): destructures `store._sessions[session_id]` directly and asserts the user id matches the value just passed in. That's the same code path as `test_get_user_id_valid_session`, but expressed against private state instead of the public `get_user_id()` method. Strictly redundant and worse.

- [ ] **Step 3.3: Run the affected test file**

Run: `uv run pytest tests/test_auth.py -v`
Expected: every remaining test passes; collected-test count drops by exactly 2. `test_get_user_id_valid_session` and the other session tests still cover create→read→expire.

- [ ] **Step 3.4: Run the full suite**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 3.5: Commit**

```bash
git add tests/test_auth.py
git commit -m "test(auth): delete weak and duplicate session tests

test_create_session used the banned 'is not None' terminal
assertion and probed the private _sessions dict. The behavior is
already proven by test_get_user_id_valid_session. See
docs/superpowers/plans/2026-05-23-test-cleanup.md."
```

---

### Task 4: Delete banned-terminal test in `test_websocket.py`

**Files:** Modify `tests/test_websocket.py`

- [ ] **Step 4.1: Verify the target test**

Run: `uv run pytest "tests/test_websocket.py::TestConnectionManager::test_connection_count_property" -v`
Expected: PASS.

- [ ] **Step 4.2: Confirm `connect()` behavior is exercised elsewhere**

Run: `grep -n "manager.connect\|await manager.connect" tests/test_websocket.py`
Expected: at least one other test (in `TestConnectionManagerThreadSafety` or the broadcast tests) calls `manager.connect()` with assertions on broadcast behavior. If `connect()` has no other coverage, do **not** delete — escalate and add a behavioral test first.

- [ ] **Step 4.3: Delete `test_connection_count_property`**

Edit `tests/test_websocket.py`. Remove lines 294–308:

```python
def test_connection_count_property(self) -> None:
    """Test connection_count property."""
    manager = ConnectionManager()

    assert manager.connection_count == 0

    async def add_connections() -> None:
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await manager.connect(ws1)
        await manager.connect(ws2)

    asyncio.run(add_connections())

    assert manager.connection_count == 2
```

Reason (TERM): the only behavioral assertions are `count == 0` and `count == 2`. This is the constitution's banned `assertEquals(2, list.size)`-style terminal — it proves the integer property arithmetic works but does not verify that the *right* websockets are stored, that they will receive broadcasts, that disconnect decrements correctly, or anything else a consumer cares about. The connect/disconnect-then-broadcast tests elsewhere in the file cover the real behavior.

- [ ] **Step 4.4: Run the affected test file**

Run: `uv run pytest tests/test_websocket.py -v`
Expected: every remaining test passes; collected-test count drops by exactly 1.

- [ ] **Step 4.5: Run the full suite**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 4.6: Commit**

```bash
git add tests/test_websocket.py
git commit -m "test(websocket): delete connection-count tautology

test_connection_count_property only checked an integer count
with no field-level verification — the constitution's banned
terminal-assertion pattern. Real connect/broadcast behavior is
covered by the surrounding tests. See
docs/superpowers/plans/2026-05-23-test-cleanup.md."
```

---

## Phase 3 — Verification

### Task 5: Verify coverage did not drop on production modules

**Files:** none modified.

- [ ] **Step 5.1: Re-run targeted coverage**

Run: `uv run pytest --cov=src/rotary_phone --cov-report=term tests/test_audio_handler.py tests/test_gpio.py tests/test_auth.py tests/test_websocket.py 2>&1 | tail -30`

Compare to the Step 0.3 baseline. The line/branch coverage on `audio_handler.py`, `gpio_abstraction.py`, `pins.py`, `web/auth.py`, `web/websocket/manager.py`, and `web/websocket/events.py` must be **equal or higher** to what Task 0 recorded.

- [ ] **Step 5.2: If any coverage dropped, investigate before declaring done**

If a percentage went down, the deleted test was the sole caller of some branch. Two options:
1. The branch is genuinely uncovered behavior that needs a real test — write it, then re-run.
2. The branch is dead code (constitution §2). Open a follow-up issue and **stop** — do not silently accept the regression. Note it in `next_steps.md`.

If coverage held flat or rose, proceed.

- [ ] **Step 5.3: Run full quality gate**

Run: `./check.sh`
Expected: all checks pass. (The repo currently runs black + mypy + pylint + pytest. None of those should regress from deleting tests.)

- [ ] **Step 5.4: Confirm the four commits look right**

Run: `git log --oneline -n 4`
Expected: four commits, one per task, each touching exactly one test file. If any commit accidentally swept in the pre-existing modified files from the working tree, amend with `git reset --soft HEAD~1` and re-stage only the test file. (Do not amend if the commit was already pushed — but for local commits this is fine.)

---

## Follow-up — out of scope for this plan

These tests **exercise real branches** but assert too weakly. They are not deleted here; they need an assertion-strengthening pass in a separate plan.

| Test | Current weakness | Strengthening idea |
|---|---|---|
| `test_database.py::test_init_creates_tables` (line 82) | Only asserts `call_id > 0` | Query the row back and assert its fields match what was inserted |
| `test_config_manager.py::test_to_dict` (line 312) | Only asserts `isinstance(dict)` and key presence | Assert the round-tripped values equal the seeded config |
| `test_websocket.py::test_event_json_serialization` (line 116) | Substring matches on JSON text | Parse JSON and assert structural fields |
| `test_sip_client.py` callback tests (lines 239–330) | `len(events) == N` terminals | Assert event payload fields, ordering, and that the callback fired exactly once |
| `test_gpio.py::test_mock_gpio_thread_safety` (line 242) | Asserts only "no errors raised" | Assert final pin state is one of the two writers' last values |

The broader cleanup informed by the staff review (web auth wiring, callbacks-under-lock refactor, secrets-at-rest, ruff/pyright migration) lives in separate plans yet to be written.

---

## Self-Review

**Spec coverage:** the user asked to (a) write the plan down, (b) work through it, (c) remove tests that don't actually test anything, (d) use the constitution as guide. The plan covers all four — each deletion cites the specific constitution clause that condemns it, the deletions are bite-sized and reversible, and the verification step protects against accidentally dropping production coverage.

**Placeholder scan:** no TBDs, no "add appropriate handling" hand-waves. Every code block to delete is quoted verbatim from the current file. Every commit message is fully written.

**Type / signature consistency:** no new code is introduced, so no type drift to worry about.

**Conservatism check:** the plan deletes 7 tests, not the 15+ the audit flagged. The cut line was: "tests where the assertion was banned by constitution §12 *and* no other consideration suggests keeping them (e.g., they exercise a unique code path)." Anything weaker than that is in the follow-up table.
