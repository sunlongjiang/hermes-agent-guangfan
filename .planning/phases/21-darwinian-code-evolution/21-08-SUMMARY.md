---
phase: 21-darwinian-code-evolution
plan: "08"
subsystem: testing
tags: [holdout, edge-case, strip-ansi, hermes-agent, d-07]

requires:
  - phase: 21-02
    provides: "tests/code/ package skeleton"
provides:
  - "tests/code/test_ansi_strip_holdout.py — 10 edge case tests for strip_ansi"
  - "Module-level pytest.skip when HERMES_AGENT_REPO unreachable (CI-safe)"
affects: [21-07-cli-orchestrator]  # consumed by D-15 holdout gate at runtime

tech-stack:
  added: []
  patterns:
    - "sys.path.insert at module top — no conftest dependency"
    - "Module-level pytest.skip allow_module_level=True for missing dependency"

key-files:
  created:
    - tests/code/test_ansi_strip_holdout.py
  modified: []

key-decisions:
  - "Module-level skip when hermes-agent not reachable — preserves CI green"
  - "Truncated CSI test asserts only 'no crash + str out' — behaviour is implementation-defined"
  - "C1 control char test (\\x80\\x81\\x82) asserts result == '' because regex strips [\\x80-\\x9f]"
  - "CRLF test asserts CRLF survives — newlines are NOT inside escape body"

patterns-established:
  - "Holdout test file living in evolution repo (NOT hermes-agent) per CONTEXT §Out of Scope"
  - "PYTHONPATH wired at file top via sys.path.insert(0, hermes_repo) — runtime import without conftest"

requirements-completed: [V2-CODE-01]

duration: ~5min (orchestrator inline write — agent fully blocked)
completed: 2026-05-20
---

# Phase 21 Plan 08: ansi_strip Holdout Edge Case Tests Summary

**10 edge case holdout tests for strip_ansi() living in the evolution repo (D-15 holdout gate consumes these at runtime; D-07 EDGE_CASE_HOLDOUT_TESTS 1:1 mapping). Module-level skip on missing hermes-agent keeps CI green.**

## Performance

- **Duration:** ~5 min (orchestrator inline write — Wave 2 executor agent fully sandbox-blocked)
- **Tasks:** 1 (test file)
- **Files modified:** 1 created

## Accomplishments

10 edge case tests, mapped 1:1 to CONTEXT.md §D-07:

1. `test_empty_string` — `strip_ansi("")` returns `""`
2. `test_single_char` — `strip_ansi("a")` returns `"a"` (fast-path)
3. `test_extreme_long_input_10k_chars` — 10 000-char input with embedded SGR; ESC fully stripped, text fragments survive
4. `test_unicode_boundary_in_escape` — `"\x1b[42m中文\x1b[0m"` → `"中文"`
5. `test_nested_escape_sequences` — `"\x1b[1m\x1b[31mbold_red\x1b[0m\x1b[0m"` → `"bold_red"`
6. `test_overlapping_escapes` — `"\x1b[31m\x1b[32mtext\x1b[0m"` → `"text"`
7. `test_truncated_csi_at_eof` — `"hello\x1b[31"` returns a str, no crash (implementation-defined residue)
8. `test_unknown_osc_command` — `"\x1b]99;unknown-payload\x07text"` → `"text"`
9. `test_mixed_invalid_bytes` — `"\x80\x81\x82"` (C1 controls) → `""` (regex strips [\\x80-\\x9f])
10. `test_crlf_inside_escape` — `"\x1b[0m\r\ntext"` → `"\r\ntext"`

Wired via `sys.path.insert(0, str(_hermes_repo))` at module top — no conftest dependency. Module-level pytest.skip with `allow_module_level=True` when `~/.hermes/hermes-agent/tools/ansi_strip.py` not present.

## Task Commits

1. **Task 1: tests/code/test_ansi_strip_holdout.py** — `753a729` (test)

Plan metadata commit (this SUMMARY.md) follows via orchestrator commit.

## Files Created/Modified

- `tests/code/test_ansi_strip_holdout.py` — 129 lines. 10 test functions + sys.path wiring + module-skip guard.

## Decisions Made

- **Truncated CSI test asserts isinstance + no-crash only.** strip_ansi's regex falls back through Fp/Fe/Fs single-byte alternative for `"\x1b["`; the resulting residue is implementation-defined and shouldn't be pinned by a holdout test (would block legitimate refactors).
- **C1 control test expects empty result.** The regex's last alternative `[\x80-\x9f]` strips every C1 byte; `"\x80\x81\x82"` → `""`. Verified against the real `tools/ansi_strip.py` source before writing.
- **OSC test uses BEL terminator** (`\x07`) — the regex supports both BEL and `\x1b\\` ST; BEL is the more common form and matches CONTEXT.md §D-07.

## Deviations from Plan

None.

## Issues Encountered

- **Executor agent sandbox lockout — 100% blocked.** Wave 2 agent for 21-08 hit denied Write/Bash on every attempt; could not even create `tests/code/__init__.py` (which was already in place from Plan 21-02, but worktree HEAD drifted). Agent reported the issue and surfaced a complete test design in its final report. Orchestrator wrote the test file directly on main using that design, validated against the real strip_ansi implementation at `~/.hermes/hermes-agent/tools/ansi_strip.py`.

## Verification Output

- `pytest tests/code/test_ansi_strip_holdout.py -v`: 10 passed in 0.13s
- `pytest tests/code/`: 28 passed in 4.21s (cumulative)
- `grep "from tools.ansi_strip import strip_ansi" tests/code/test_ansi_strip_holdout.py`: 1
- `grep "test_empty_string\|test_extreme_long_input\|test_unicode_boundary\|test_truncated_csi\|test_unknown_osc\|test_crlf_inside" tests/code/test_ansi_strip_holdout.py`: 6 (covers 10-edge-case mandatory subset per plan done-criteria)

## Self-Check: PASSED

- tests/code/test_ansi_strip_holdout.py exists (129 lines)
- Commit 753a729 (test) on main
- All 10 tests pass against real strip_ansi
- All plan success criteria PASS

## Threat Surface

- T-21-UNREVIEWED — these tests act as a regression safety net inside the D-15 holdout gate, ensuring evolved candidates that break edge cases get rejected before reaching `output/code/<ts>/`.

---
*Phase: 21-darwinian-code-evolution*
*Completed: 2026-05-20*
