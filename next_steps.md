# Staff Engineer Code Review: rotary-voip

Overall grade: **B+ / 3.4 GPA** — solid engineering for a hobby project, with thoughtful abstractions and unusually-good test infrastructure, but suffering from a hypertrophied `CallManager` and pervasive defensive exception handling that hides bugs.

---

## Status as of 2026-05-23

| # | Item | Status |
|---|---|---|
| 1 | `CallManager` doing too much + CallLogger coupling | ✅ Fixed in `1a2daf0` |
| 2 | Pervasive `except Exception` swallow-and-log | ⚠️ Partial (`call_manager.py` + parts of `pyvoip_client.py` done; `audio_handler.py` and several other `pyvoip_client.py` instances still broad) |
| 3 | Race in `PyVoIPClient._call_state_monitor` | ✅ Fixed in `2823fa0` |
| 4 | 0-duration `call_ended` event | ✅ Fixed in `1a2daf0` |
| 5 | `send_audio_file` 100-line method + `elapsed` overshoot | ❌ Untouched |
| 6 | `MockGPIO.set_input` indentation bug | ⚠️ Cosmetic-only (blank line removed in `46bc63a`; actual indentation still wrong — debug log still gated by `if callback_to_call`) |
| 7 | `@app.on_event` deprecation → lifespan | ✅ Fixed in `adf8f5b` |
| 8 | Config save endpoint write-and-reload | ❌ Untouched |
| 9a | `audio_handler.py` backcompat aliases | ✅ Fixed in `bc63a3b` |
| 9b | `config_manager.py` ConfigError import mid-module | ✅ Fixed in `46bc63a` |
| 9c | `_normalize_phone_number` NANP-only | ❌ Untouched |
| 9d | `_extract_caller_id` hasattr duck-typing | ✅ Fixed in `2823fa0` (narrowed to `AttributeError` + warn) |
| 9e | `network_monitor` TCP-to-53 probe semantic | ⚠️ Documented in `46bc63a`; probe itself unchanged |
| 9f | `time.sleep(0.15)` flakiness in integration fixture | ❌ Untouched |

**Priority list status:** 1, 3, 4, 5 (lifespan), 6 (the `_on_off_hook` half) done; #2 partial; send_audio_file half of #6 pending.

### Also addressed this session (not in original review)
- Eight worthless tests deleted per constitution §12 (`98b9a31`–`665da00`).
- Five weak tests strengthened with field-value assertions (`b8b1dfc`–`84a635a`).
- Pre-existing CI failure resolved (slowapi/Starlette typing mismatch, `e538f0d`).
- Battery scope removed from docs + handset-element BOM (`ae40052`).

### Queued for next plan
- **Finish-auth plan** (`docs/superpowers/plans/2026-05-23-finish-auth.md`) — wires `require_auth` to every protected router, adds WS auth, fixes login timing/blocking/session-fixation, conditional `secure` cookie, integration tests, bootstrap UX. Addresses the #1 critical from my opening staff review (admin interface had zero enforcement).

---

## What's good

**Abstraction boundaries are clean and intentional.** `SIPClient` ABC with `InMemorySIPClient`/`PyVoIPClient` (sip_client.py:27), `GPIO` ABC with `MockGPIO`/`RealGPIO` (gpio_abstraction.py:36), and constructor DI throughout `CallManager` (call_manager.py:55-66) means the system is testable without hardware or network. The integration tests in `tests/test_integration_e2e.py` validate the whole stack with mocks — the kind of seam most embedded projects miss.

**`audio/pyvoip_patches.py` is the highlight of the codebase.** It explains *why* the patches exist (μ-law → 8-bit linear loses 5 bits of dynamic range, biases samples toward -1), names the symptom users would see (the 0x7F peak), and the patch itself is small and surgical. `audio_handler.py:_setup_resamplers` correctly prefers polyphase FIR for integer ratios over `audioop.ratecv` for non-integer — that's real signal-processing literacy.

**State machine is explicit.** `PhoneState` is small (8 values), `_transition_to` is the single mutator, and transitions are logged. Good shape.

**Thread discipline is mostly right.** Locks are held narrowly, callbacks are deliberately invoked outside locks (e.g. dial_reader.py:142-144, hook_monitor.py:185), and the connection-per-operation SQLite pattern in `database.py:_connection` is the correct choice for multi-thread access.

**Config preserves comments via ruamel.yaml round-trip + atomic write** (config_manager.py:297-333). Most projects botch this; this one didn't.

## What's wrong

### ✅ 1. `CallManager` is doing too much (call_manager.py, 665 lines) — FIXED (`1a2daf0`)

It orchestrates hardware, runs a state machine, validates numbers, expands speed dial, drives the call logger, drives the audio handler, emits WebSocket events, and manages two separate timer types. The smell shows up most in `_on_off_hook` (call_manager.py:251) — *one method, one lock acquisition, two completely different responsibilities* (idle→dialing setup vs. ringing→answer). It should be split into `_handle_idle_pickup()` and `_handle_ringing_answer()`.

The coupling to `CallLogger` is the worst part: every state branch is sprinkled with `if self._call_logger:` followed by a specific logger method call (call_manager.py:271, 286, 310, 317, 332, 420, 429, 459, 488, 498, 528, 574, 649). You already have `_emit_event` (line 210) — `CallLogger` should subscribe to events the way the WebSocket does. Then `CallManager` doesn't know `CallLogger` exists.

### ⚠️ 2. Pervasive `except Exception` swallow-and-log antipattern — PARTIAL

`call_manager.py` narrowed in `1a2daf0` (SIPError/AudioError). `pyvoip_client._call_state_monitor` and `_get_caller_id` narrowed in `2823fa0`. **Remaining broad excepts:** `pyvoip_client.py:171, 178, 275, 290, 311, 475` and the whole of `audio_handler.py` (~10 instances). Finish in a future pass.

I count ~30 `except Exception as e: logger.error(...)` blocks in call_manager.py, pyvoip_client.py, and audio_handler.py that catch broadly and continue. Examples:

- ~~`call_manager.py:139, 169, 219, 282, 327, 335, 456, 539, 557, 645`~~ — done
- `pyvoip_client.py:171, 178, 254, 275, 290, 311, 374, 475` — 254 + 374 done; rest pending

This is the cardinal sin of error handling: it doesn't recover, doesn't surface, doesn't fail loud. Bugs hide in here. You have a real exception hierarchy in `exceptions.py` (SIPRegistrationError, SIPCallError, etc.) — *use it*. Narrow these catches, or remove them and let exceptions propagate to a single high-level handler that knows what to do with each type.

### ✅ 3. Race in `PyVoIPClient._call_state_monitor` (pyvoip_client.py:227) — FIXED (`2823fa0`)

The monitor thread reads `self._current_call` and `self._call_state` without the lock (line 229, 232, 233). Meanwhile `hangup()` (line 279) holds the lock to mutate them. Concrete failure mode: user hangs up just as the remote does — `hangup()` sets `_current_call = None` and fires `_on_call_ended`; the monitor sees `call_state == ENDED` on its next poll, sets state to REGISTERED again, and fires `_on_call_ended` *again*. The `CallManager._on_call_ended` is not idempotent (it'll try to stop audio that's already stopped, log a duplicate "call ended" event, etc.).

Fix: monitor thread should acquire `_lock` for each iteration, or transition the call object to None atomically with the "ended" detection.

### ✅ 4. Dead/lossy code in `_on_call_ended` (call_manager.py:577-580) — FIXED (`1a2daf0`)

```python
# Note: Call duration is tracked by the CallLogger, but we don't have
# access to it here since on_call_ended() clears it. The actual duration
# is stored in the database and can be retrieved from call logs.
call_duration = 0.0
```

You're emitting a WebSocket event with `duration: 0` and a comment apologizing for it. Either fetch the duration before clearing (swap the order of operations), or have `CallLogger.on_call_ended` return the finalized record. The current code is broken-by-design and the comment admits it.

### ❌ 5. `send_audio_file` does too much and has a sleep-loop bug (pyvoip_client.py:379-477) — PENDING

100-line method that reads WAV, downmixes, resamples, encodes μ-law, sends, then sleeps in 100ms increments to allow interruption. The increment logic is wrong:

```python
time.sleep(min(interval, duration - elapsed))
elapsed += interval  # ← should be the actual sleep duration
```

When the last sleep is shorter than `interval`, `elapsed` overshoots. Cosmetic in practice (loop exits anyway) but indicates the method wasn't carefully audited. Break it up: `_decode_wav_to_ulaw(path)` and `_send_with_interruption(data, stop_check)`.

### ⚠️ 6. Indentation bug in `MockGPIO.set_input` (gpio_abstraction.py:255-261) — COSMETIC-ONLY FIX

`46bc63a` removed a blank line inside the if-block but **the indentation is still wrong** — the debug log still only fires when a callback is registered.

```python
            self._last_values[pin] = value

    # Call callback outside of lock to avoid deadlock
    if callback_to_call is not None:
        callback_to_call(pin)

        logger.debug("Mock input: pin=%d, value=%d, triggered edge detect", pin, value)
```

The debug log is inside the `if callback_to_call is not None` block — so it only logs when a callback fires, not on every input change. Either the log is misplaced or the indentation is. Reading the message ("Mock input… triggered edge detect"), the intent looks like the log should be unconditional with a different message, or this log should be at the call site. Minor, but exactly the kind of thing the test suite won't catch.

### ✅ 7. FastAPI deprecation: `@app.on_event` (app.py:159, 175) — FIXED (`adf8f5b`)

`on_event` was deprecated in FastAPI 0.93. You're on `>=0.109.0`. Switch to a `lifespan` context manager — it's not just lint, it's also the only way to do proper async setup/teardown ordering.

### ❌ 8. Config validation by writing-and-reloading (app.py:273-291) — PENDING

The save endpoint writes the new YAML to a temp file, instantiates a *whole* `ConfigManager` from it to validate, then writes the real file. You already have `ConfigManager.update_config()` (config_manager.py:267) that validates in-memory — use it. Bonus: the current path leaks the tmp file on validation failure between line 277 and the `finally` (the `ConfigManager` constructor raises before reaching the `try`).

### 9. Small cuts

- ✅ `audio_handler.py:32-34` — `SAMPLE_RATE`/`FRAME_SIZE` "backward compatibility aliases" for symbols that have never been public. CLAUDE.md says don't add backcompat shims; delete. **FIXED (`bc63a3b`)**
- ✅ `config_manager.py:18` — `from rotary_phone.exceptions import ConfigError` is mid-module, post-`logger`. Move to the top import block. **FIXED (`46bc63a`)**
- ❌ `ConfigManager._normalize_phone_number` (config_manager.py:193) — handles only NANP. The allowlist will silently mis-match international formats. Document or generalize. **PENDING**
- ✅ `pyvoip_client._extract_caller_id` (line 355) — `hasattr` duck-typing against a third-party SIP library. If pyVoIP renames `.request.headers`, you silently return "Unknown" forever. Catch a specific `AttributeError` and warn loudly. **FIXED (`2823fa0`)**
- ⚠️ `network_monitor.check_connectivity` opens a TCP socket to `8.8.8.8:53` — DNS doesn't normally accept TCP. Works (Google DNS does answer TCP) but the semantic is "can I reach a thing on the internet," not "is DNS working." Comment or pick a more honest probe. **`46bc63a` added a comment; probe itself unchanged.**
- ❌ Tests use `time.sleep(0.15)` to wait for registration in the `phone_system` fixture (test_integration_e2e.py:86) — flaky on slow CI. Wait on a condition. **PENDING**

## Quality scorecard

| Dimension | Grade | Notes |
|---|---|---|
| Architecture | B+ | Clean abstractions, but `CallManager` is a god-object and `CallLogger` coupling is heavy. |
| Correctness | B | Mostly right, but the SIP monitor race and the 0-duration event are real bugs. |
| Error handling | C | Defensive `except Exception` everywhere; defined exception hierarchy goes mostly unused. |
| Threading | B+ | Locks held narrowly, callbacks outside locks — good discipline marred by the monitor-thread race. |
| Testability | A- | DI + mock SIP + mock GPIO gives a real integration test. Rare and valuable. |
| Documentation | A- | Docstrings are useful, not ceremonial. `pyvoip_patches.py` is exemplary. |
| Elegance | B | The μ-law work shines; the `CallManager` event-emission code drags it down. |

## What I'd do next, in order

1. ✅ Refactor `CallLogger` to subscribe to events via `_emit_event` — strip ~50 lines of `if self._call_logger:` from `CallManager`. **DONE (`1a2daf0`)**
2. ⚠️ Audit every `except Exception` and either narrow it (use the existing exception hierarchy) or delete it. **PARTIAL — CallManager + parts of PyVoIPClient done; audio_handler.py and rest of PyVoIPClient pending.**
3. ✅ Fix the `_call_state_monitor` lock race in `PyVoIPClient`. **DONE (`2823fa0`)**
4. ✅ Fix the 0-duration `call_ended` event — read duration before clearing. **DONE (`1a2daf0`)**
5. ✅ Switch FastAPI to lifespan; drop `on_event`. **DONE (`adf8f5b`)**
6. ⚠️ Split `_on_off_hook` and `send_audio_file` into single-responsibility helpers. **PARTIAL — `_on_off_hook` split in `1a2daf0`; `send_audio_file` pending (#5).**

This is good code — better than most hobby-scale projects ever reach. The flaws are the kind you only catch once it's worth catching.
