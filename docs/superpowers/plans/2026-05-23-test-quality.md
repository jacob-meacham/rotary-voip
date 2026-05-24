# Test Quality Strengthening Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen the assertions on five tests that exercise real code paths but verify them too weakly to catch regressions, per the follow-up table in `docs/superpowers/plans/2026-05-23-test-cleanup.md`.

**Architecture:** Each task rewrites one test in-place. The principle, from `agent-instructions/coding/constitution/general.md` §12 "Testing": *"Tests must prove behavior, not existence."* Where a test currently asserts `assertNotNull` / `len(x) == N` / `isinstance(x, dict)` as its terminal check, replace with field-value verification — for persistence tests, round-trip through the public read API; for callback tests, assert call count *and* payload; for serialization tests, parse the output and assert structural fields.

**Tech Stack:** pytest, `Database.get_call()` for DB round-trips, `json.loads()` for JSON parse checks, `unittest.mock` was considered but the existing callback tests use plain lists which work fine — kept that idiom.

---

## Scope notes

**Out of scope: renaming `test_integration_e2e.py`.** The first staff-review pass flagged the name as misleading because the tests use `MockGPIO + InMemorySIPClient`. On a second look, those are the *production* GPIO mock and the production in-memory SIP client — they're the real components, exercised through `CallManager`'s real wiring. That is integration, just with hardware/network seams swapped for in-process equivalents. No rename. (If someone later stands up a real loopback SIP container, they can add a `test_integration_real_sip.py` alongside; the existing file stays.)

**Out of scope: `test_base_event::endswith("Z")` and similar.** These weren't called out by name in the cleanup-plan's follow-up table and there are diminishing returns on bikeshed-strength assertions for trivial Pydantic field-getters.

---

## File Structure

No files created. Edits only:

| File | Tests rewritten | Notes |
|---|---|---|
| `tests/test_database.py` | `test_init_creates_tables` | Round-trip `add_call` → `get_call`, assert all persisted fields |
| `tests/test_config_manager.py` | `test_to_dict` | Compare round-tripped values against seeded config |
| `tests/test_websocket.py` | `test_event_json_serialization` | Parse JSON, assert structural fields |
| `tests/test_sip_client.py` | `test_on_incoming_call_callback`, `test_on_call_answered_callback_outgoing`, `test_on_call_answered_callback_incoming`, `test_on_call_ended_callback`, `test_multiple_callbacks` | Use `unittest.mock.Mock` for the callback; assert `call_count == 1` and call_args, then drop the list-collector idiom |
| `tests/test_gpio.py` | `test_mock_gpio_thread_safety` | Assert final pin state is one of the two valid writer terminal states; keep the no-errors check as a *prefix* assertion, not the terminal one |

---

## Pre-flight

### Task 0: Baseline

**Files:** none modified.

- [ ] **Step 0.1: Confirm working tree state**

Run: `git status --short`
Expected: empty (the working tree was cleared at the end of the previous session). If anything is modified, stop and ask before continuing — this plan assumes a clean baseline.

- [ ] **Step 0.2: Confirm baseline test suite is green**

Run: `uv run pytest -q`
Expected: `279 passed`. If it's anything else, stop — the baseline drifted and this plan's "drop count by exactly N" verifications won't be meaningful.

---

## Phase 1 — Persistence round-trip

### Task 1: Rewrite `test_init_creates_tables` to verify the round-trip, not just the insert

**Files:** Modify `tests/test_database.py:82-91`

- [ ] **Step 1.1: Verify the current test passes**

Run: `uv run pytest tests/test_database.py::TestDatabase::test_init_creates_tables -v`
Expected: PASS.

- [ ] **Step 1.2: Replace the test body**

Edit `tests/test_database.py`. Replace lines 82–91:

```python
    def test_init_creates_tables(self, temp_db: Database) -> None:
        """Test that init_db creates the required tables."""
        # Just verify we can add a call without error
        call = CallLog(
            timestamp=datetime.utcnow(),
            direction="outbound",
            status="completed",
        )
        call_id = temp_db.add_call(call)
        assert call_id > 0
```

with this round-trip version:

```python
    def test_init_creates_tables_persists_call_round_trip(self, temp_db: Database) -> None:
        """init_db creates the schema such that add_call() persists every column
        and get_call() returns it intact. This is what 'the tables work' means.
        """
        timestamp = datetime.utcnow()
        call = CallLog(
            timestamp=timestamp,
            direction="outbound",
            status="completed",
            dialed_number="11",
            destination="+15551234567",
            speed_dial_code="11",
            duration_seconds=42,
            error_message=None,
        )

        call_id = temp_db.add_call(call)
        loaded = temp_db.get_call(call_id)

        assert loaded is not None
        assert loaded.id == call_id
        assert loaded.timestamp == timestamp
        assert loaded.direction == "outbound"
        assert loaded.status == "completed"
        assert loaded.dialed_number == "11"
        assert loaded.destination == "+15551234567"
        assert loaded.speed_dial_code == "11"
        assert loaded.duration_seconds == 42
        assert loaded.error_message is None
```

Reason: the original test's terminal assertion was `assert call_id > 0`. That fires on any successful INSERT, including one against a schema that's missing optional columns or has the wrong column order — both bugs SQLite would happily commit. The round-trip version verifies that every column is **persisted** *and* **read back** with the right value.

- [ ] **Step 1.3: Run the affected test file**

Run: `uv run pytest tests/test_database.py -v`
Expected: every test in the file passes; the renamed test shows up as `test_init_creates_tables_persists_call_round_trip PASSED`.

- [ ] **Step 1.4: Commit**

```bash
git add tests/test_database.py
git commit -m "$(cat <<'EOF'
test(database): strengthen init_creates_tables to round-trip a call

The original test asserted only that add_call() returned a positive
id, which fires on any successful INSERT — including one against a
schema with missing or reordered columns. Now also calls get_call()
and asserts every persisted field round-trips intact. Renamed to
test_init_creates_tables_persists_call_round_trip to reflect what's
being verified.

See docs/superpowers/plans/2026-05-23-test-quality.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Config round-trip

### Task 2: Rewrite `test_to_dict` to verify values, not just keys

**Files:** Modify `tests/test_config_manager.py:312-328`

- [ ] **Step 2.1: Verify the current test passes**

Run: `uv run pytest tests/test_config_manager.py::test_to_dict -v`
Expected: PASS.

- [ ] **Step 2.2: Replace the test body**

Edit `tests/test_config_manager.py`. Replace lines 312–328:

```python
def test_to_dict() -> None:
    """Test getting entire config as dictionary."""
    config_dict = get_minimal_valid_config()
    config_path = create_temp_config(config_dict)

    try:
        config = ConfigManager(user_config_path=config_path)

        config_dict_result = config.to_dict()
        assert isinstance(config_dict_result, dict)
        assert "sip" in config_dict_result
        assert "timing" in config_dict_result
        assert "audio" in config_dict_result
        assert "speed_dial" in config_dict_result
        assert "allowlist" in config_dict_result
    finally:
        Path(config_path).unlink()
```

with:

```python
def test_to_dict_round_trips_seeded_values() -> None:
    """to_dict() returns every section with the values the YAML actually
    contained — not just the section keys."""
    seeded = get_minimal_valid_config()
    seeded["sip"]["server"] = "sip.example.com"
    seeded["sip"]["username"] = "alice"
    seeded["speed_dial"] = {"11": "+15551234567"}
    seeded["allowlist"] = ["+15551234567"]
    seeded["timing"]["inter_digit_timeout"] = 3.5

    config_path = create_temp_config(seeded)

    try:
        result = ConfigManager(user_config_path=config_path).to_dict()

        assert result["sip"]["server"] == "sip.example.com"
        assert result["sip"]["username"] == "alice"
        assert result["sip"]["port"] == 5060
        assert result["timing"]["inter_digit_timeout"] == 3.5
        assert result["speed_dial"] == {"11": "+15551234567"}
        assert result["allowlist"] == ["+15551234567"]
    finally:
        Path(config_path).unlink()
```

Reason: the original test asserted that the result was a dict containing certain keys, which is the constitution's banned existence-check pattern (`isinstance` + key membership). The rewrite seeds non-default values into each section and verifies they survive load+`to_dict`. If a future refactor drops the `sip.port` default, drops a section, or silently coerces the speed-dial dict to something else, this test now catches it.

- [ ] **Step 2.3: Run the affected test file**

Run: `uv run pytest tests/test_config_manager.py -v`
Expected: every test passes; `test_to_dict_round_trips_seeded_values` shows up where the old `test_to_dict` was.

- [ ] **Step 2.4: Commit**

```bash
git add tests/test_config_manager.py
git commit -m "$(cat <<'EOF'
test(config): strengthen to_dict to verify seeded values round-trip

The original test_to_dict asserted only isinstance(dict) and section
key presence — the constitution's banned existence pattern. Now seeds
non-default values into each section and asserts they survive load +
to_dict() unchanged. Renamed to test_to_dict_round_trips_seeded_values.

See docs/superpowers/plans/2026-05-23-test-quality.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3 — Structural JSON parse

### Task 3: Rewrite `test_event_json_serialization` to parse JSON, not substring-match

**Files:** Modify `tests/test_websocket.py:116-124`

- [ ] **Step 3.1: Verify the current test passes**

Run: `uv run pytest "tests/test_websocket.py::TestWebSocketEvents::test_event_json_serialization" -v`
Expected: PASS.

- [ ] **Step 3.2: Add `json` import if missing**

Run: `grep -n "^import json\|^from json" tests/test_websocket.py`
Expected: no matches yet. If matches exist, skip step 3.3.

- [ ] **Step 3.3: Add `import json` near the top of the file**

Edit `tests/test_websocket.py`. Find the line `import asyncio` (line 3) and insert below it:

```python
import json
```

Final result around lines 3–4:

```python
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
```

- [ ] **Step 3.4: Replace the test body**

Edit `tests/test_websocket.py`. Replace lines 116–124:

```python
    def test_event_json_serialization(self) -> None:
        """Test that events can be serialized to JSON."""
        event = CallStartedEvent(direction="outbound", number="123")

        json_str = event.model_dump_json()

        assert "call_started" in json_str
        assert "outbound" in json_str
        assert "123" in json_str
```

with:

```python
    def test_event_json_serialization_round_trip(self) -> None:
        """model_dump_json() emits a JSON object with the expected structural
        keys and values — not a free-form string we happen to substring-match.
        """
        event = CallStartedEvent(direction="outbound", number="+15551234567")

        parsed = json.loads(event.model_dump_json())

        assert parsed["type"] == "call_started"
        assert parsed["data"]["direction"] == "outbound"
        assert parsed["data"]["number"] == "+15551234567"
        assert parsed["timestamp"].endswith("Z")
```

Reason: substring matching on JSON text passes for a serializer that emits `{"type": "blah blah call_started blah outbound 123"}` — anything containing those tokens. The parse-then-assert form fails fast if the field layout changes, which is the actual contract the WebSocket consumer depends on.

- [ ] **Step 3.5: Run the affected test file**

Run: `uv run pytest tests/test_websocket.py -v`
Expected: every test passes; renamed test shows up as `test_event_json_serialization_round_trip PASSED`.

- [ ] **Step 3.6: Commit**

```bash
git add tests/test_websocket.py
git commit -m "$(cat <<'EOF'
test(websocket): parse JSON instead of substring-matching it

test_event_json_serialization checked that the JSON output contained
the substrings 'call_started', 'outbound', and '123'. That passes for
any serializer that includes those tokens anywhere in any field.
Replaced with json.loads() + structural field assertions, which is
the actual contract the WebSocket consumer relies on.

See docs/superpowers/plans/2026-05-23-test-quality.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4 — Callback fidelity

### Task 4: Rewrite SIP callback tests to assert call count *and* payload

**Files:** Modify `tests/test_sip_client.py:239-330`

- [ ] **Step 4.1: Verify the current tests pass**

Run: `uv run pytest tests/test_sip_client.py::test_on_incoming_call_callback tests/test_sip_client.py::test_on_call_answered_callback_outgoing tests/test_sip_client.py::test_on_call_answered_callback_incoming tests/test_sip_client.py::test_on_call_ended_callback tests/test_sip_client.py::test_multiple_callbacks -v`
Expected: all five PASS.

- [ ] **Step 4.2: Verify `Mock` import is available**

Run: `grep -n "from unittest.mock\|from unittest import mock" tests/test_sip_client.py`
Expected: at least one match. If none, add `from unittest.mock import Mock, call` at the top of the file's imports. If there's already a `from unittest.mock import ...` line, add `Mock, call` to it.

- [ ] **Step 4.3: Replace the five callback tests**

Edit `tests/test_sip_client.py`. Replace lines 239–330 (the five callback tests) with:

```python
def test_on_incoming_call_callback_fires_once_with_caller_id() -> None:
    """simulate_incoming_call invokes on_incoming_call exactly once with the
    caller id passed in."""
    on_incoming = Mock()
    client = InMemorySIPClient(on_incoming_call=on_incoming)
    client.register("sip:user@example.com", "user", "password")

    client.simulate_incoming_call("5559876543")

    on_incoming.assert_called_once_with("5559876543")


def test_on_call_answered_fires_once_for_outgoing_call() -> None:
    """make_call invokes on_call_answered exactly once (the in-memory client
    auto-answers); the callback is invoked with no arguments."""
    on_answered = Mock()
    client = InMemorySIPClient(on_call_answered=on_answered)
    client.register("sip:user@example.com", "user", "password")

    client.make_call("5551234567")

    on_answered.assert_called_once_with()


def test_on_call_answered_fires_once_for_inbound_answer() -> None:
    """answer_call on a ringing inbound call invokes on_call_answered exactly
    once, with no arguments."""
    on_answered = Mock()
    client = InMemorySIPClient(on_call_answered=on_answered)
    client.register("sip:user@example.com", "user", "password")
    client.simulate_incoming_call("5559876543")

    client.answer_call()

    on_answered.assert_called_once_with()


def test_on_call_ended_fires_once_with_no_args_after_hangup() -> None:
    """hangup() invokes on_call_ended exactly once with no arguments."""
    on_ended = Mock()
    client = InMemorySIPClient(on_call_ended=on_ended)
    client.register("sip:user@example.com", "user", "password")
    client.make_call("5551234567")

    client.hangup()

    on_ended.assert_called_once_with()


def test_callbacks_fire_in_order_incoming_then_answered_then_ended() -> None:
    """A full incoming-call lifecycle invokes the callbacks in the documented
    order: on_incoming_call(caller_id) -> on_call_answered() -> on_call_ended().
    """
    on_incoming = Mock()
    on_answered = Mock()
    on_ended = Mock()
    parent = Mock()
    parent.attach_mock(on_incoming, "incoming")
    parent.attach_mock(on_answered, "answered")
    parent.attach_mock(on_ended, "ended")

    client = InMemorySIPClient(
        on_incoming_call=on_incoming,
        on_call_answered=on_answered,
        on_call_ended=on_ended,
    )
    client.register("sip:user@example.com", "user", "password")

    client.simulate_incoming_call("5559876543")
    client.answer_call()
    client.hangup()

    assert parent.mock_calls == [
        call.incoming("5559876543"),
        call.answered(),
        call.ended(),
    ]
```

Reason:

- The original tests appended a sentinel into a list inside the callback and asserted `len(...) == N`. That fires for any code that mutates the list — including the callback being invoked twice (which would actually be a bug), or the test itself appending in setup. `Mock.assert_called_once_with` proves *the SIPClient itself called the callback exactly once with the right argument*.
- The "multiple callbacks" test asserted `events[N] == (...)` — but the tuple-tagging idiom meant a test would also pass if the callbacks fired in the wrong order *and* with the wrong arguments, as long as the tagging happened to line up. The `parent.mock_calls` pattern verifies *interleaved order across mocks*, which is the actual contract.

- [ ] **Step 4.4: Run the affected test file**

Run: `uv run pytest tests/test_sip_client.py -v`
Expected: every test in the file passes; the five renamed tests show up where the old ones were.

- [ ] **Step 4.5: Commit**

```bash
git add tests/test_sip_client.py
git commit -m "$(cat <<'EOF'
test(sip): assert callback fired once + payload, not len of a list

The previous tests appended sentinels into a list inside the callback
and asserted len(events) == N. That passes for double-fire bugs as
long as the count happens to match, and the tuple-tagging idiom in
test_multiple_callbacks can't distinguish wrong ordering from right
ordering if the tags happen to line up.

Replaced with Mock-based callbacks using assert_called_once_with()
and, for the ordering test, parent.attach_mock + mock_calls to
verify interleaved order across the three callback objects.

See docs/superpowers/plans/2026-05-23-test-quality.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 5 — Concurrency final-state assertion

### Task 5: Strengthen `test_mock_gpio_thread_safety` to verify the final pin state

**Files:** Modify `tests/test_gpio.py:234-264`

- [ ] **Step 5.1: Verify the current test passes**

Run: `uv run pytest tests/test_gpio.py::test_mock_gpio_thread_safety -v`
Expected: PASS.

- [ ] **Step 5.2: Replace the test body**

Edit `tests/test_gpio.py`. Replace lines 234–264 (the whole function):

```python
def test_mock_gpio_thread_safety() -> None:
    """Test that GPIO operations are thread-safe."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(HOOK, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    errors = []

    def reader() -> None:
        try:
            for _ in range(100):
                gpio.input(HOOK)
        except Exception as e:
            errors.append(e)

    def writer() -> None:
        try:
            for i in range(100):
                gpio.set_input(HOOK, i % 2)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=reader) for _ in range(5)]
    threads.extend([threading.Thread(target=writer) for _ in range(5)])

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
```

with:

```python
def test_mock_gpio_thread_safety_leaves_pin_in_consistent_state() -> None:
    """Under concurrent reads and writes, MockGPIO must (a) never raise from
    either side and (b) leave the pin in one of the values writers actually
    wrote. A torn read returning some garbage int (or None) would mean the
    internal dict was being mutated mid-read without locking."""
    gpio = MockGPIO()
    gpio.setmode(GPIO.BCM)
    gpio.setup(HOOK, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    errors: list[Exception] = []
    observed_reads: list[int] = []

    def reader() -> None:
        try:
            for _ in range(100):
                observed_reads.append(gpio.input(HOOK))
        except Exception as e:  # noqa: BLE001 — capturing for test assertion
            errors.append(e)

    def writer() -> None:
        try:
            for i in range(100):
                gpio.set_input(HOOK, i % 2)
        except Exception as e:  # noqa: BLE001 — capturing for test assertion
            errors.append(e)

    threads = [threading.Thread(target=reader) for _ in range(5)]
    threads.extend([threading.Thread(target=writer) for _ in range(5)])
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # No exceptions on either side
    assert errors == [], f"thread errors: {errors!r}"
    # Every read returned one of the two values a writer could have written
    assert set(observed_reads) <= {0, 1}, f"saw unexpected reads: {set(observed_reads)}"
    # The final pin value matches the last write (writers' last iteration is i=99 -> 1)
    assert gpio.input(HOOK) == 1
```

Reason: the original test only asserted "no exceptions raised," which passes for any implementation that returns `None`, returns stale-pointer garbage, or silently corrupts the pin dict — as long as it doesn't *raise*. The strengthened version verifies that every observed read was a value a writer could legitimately have written (catches torn reads / wrong-type returns) and that the final pin state is the writers' last-iteration value (catches lost writes).

- [ ] **Step 5.3: Run the affected test file**

Run: `uv run pytest tests/test_gpio.py -v`
Expected: every test passes; renamed test shows up in place of the old one. **Caveat:** the final-write assertion (`gpio.input(HOOK) == 1`) assumes writers' last iteration is `i=99 → i%2 == 1`. If this proves to be racy in practice (e.g., the scheduler interleaves writer threads such that thread A's last write of `1` is overwritten by thread B's earlier write of `0`), drop step 5.3's final assertion and replace it with `assert gpio.input(HOOK) in {0, 1}`. Run the test ten times if needed to confirm stability before committing — see step 5.4.

- [ ] **Step 5.4: Run the test 10 times to confirm stability**

Run: `uv run pytest tests/test_gpio.py::test_mock_gpio_thread_safety_leaves_pin_in_consistent_state --count=10 2>&1 | tail -3` if `pytest-repeat` is installed; otherwise:

```bash
for i in 1 2 3 4 5 6 7 8 9 10; do uv run pytest "tests/test_gpio.py::test_mock_gpio_thread_safety_leaves_pin_in_consistent_state" -q 2>&1 | tail -1; done
```

Expected: all 10 runs pass. If even one fails on the final-state assertion, fall back to `assert gpio.input(HOOK) in {0, 1}` per the caveat in step 5.3, then re-run.

- [ ] **Step 5.5: Commit**

```bash
git add tests/test_gpio.py
git commit -m "$(cat <<'EOF'
test(gpio): assert thread-safety leaves pin in a consistent value

The previous test only asserted no exceptions were raised, which
passes for any implementation that silently returns None, returns
torn-read garbage, or corrupts the internal pin dict — anything that
doesn't actively raise. Now also asserts every observed read was 0
or 1 (catches type errors and torn reads) and that the final pin
value is what the writers last wrote.

See docs/superpowers/plans/2026-05-23-test-quality.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 6 — Verification

### Task 6: Confirm coverage is preserved and full gate is green

**Files:** none modified.

- [ ] **Step 6.1: Full suite**

Run: `uv run pytest -q`
Expected: `279 passed` (same count as baseline — we're rewriting, not adding or removing).

- [ ] **Step 6.2: Full quality gate**

Run: `./check.sh`
Expected: `✅ All checks passed!`

- [ ] **Step 6.3: Spot-check coverage on the touched modules**

Run: `uv run pytest --cov=src/rotary_phone --cov-report=term tests/test_database.py tests/test_config_manager.py tests/test_websocket.py tests/test_sip_client.py tests/test_gpio.py 2>&1 | grep -E "database\.py|config_manager\.py|websocket/events|in_memory_client|gpio_abstraction|TOTAL"`

Expected: line coverage on `database/database.py`, `config/config_manager.py`, `web/websocket/events.py`, `sip/in_memory_client.py`, and `hardware/gpio_abstraction.py` is **equal or higher** than the pre-rewrite baseline (the rewrites assert *more* of each module's behavior, so coverage should only go up, never down). If any number drops, investigate — a drop means a removed assertion was the only exerciser of some branch.

- [ ] **Step 6.4: Inspect the commit list**

Run: `git log --oneline -n 6`
Expected: five `test(...)` commits (one per phase), plus the most recent doc commit (`docs: add staff review and the test-cleanup plan`) underneath them. Each touched exactly one test file.

---

## Self-Review

**Spec coverage:** the user asked for the "test quality cluster" and the cleanup plan named exactly five candidates plus the rename question. Five candidates → five tasks; the rename is explicitly addressed and explicitly declined (with reasoning). Covered.

**Placeholder scan:** every Edit block contains the literal current code and the literal replacement. Every `Run:` line has an exact command and exact expected output. The only conditional in the plan is in step 5.3's caveat about the thread-safety final-state assertion, with a concrete fallback assertion ready to go — that's the right shape for a known-racy test (state what to try, state the fallback if it doesn't hold).

**Type/identifier consistency:** `CallLog`, `add_call`, `get_call`, `to_dict`, `model_dump_json`, `assert_called_once_with`, `parent.mock_calls`, `Mock`, `call`, `MockGPIO.input`, `MockGPIO.set_input` — all match the actual signatures in the codebase (verified by reading the source before writing the plan).

**One small adjustment from a fresh read:** the original `test_to_dict` does not assert on `database`, `logging`, or `web` sections even though `get_minimal_valid_config()` includes them. The rewrite intentionally keeps the same section-level surface (`sip`, `timing`, `speed_dial`, `allowlist`) and adds value-level assertions to that surface — not expanding scope. Good.
