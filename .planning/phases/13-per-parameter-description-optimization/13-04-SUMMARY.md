---
phase: 13
plan: "04"
subsystem: tools
tags: [constraint, llm-judge, fail-closed, polarity-inversion, param-consistency, wave-2]
dependency_graph:
  requires:
    - 13-01-SUMMARY (Wave 0 RED tests — tests/tools/test_param_consistency.py)
    - 13-02-SUMMARY (per-param ToolModule structure — supplies evolved_tools.params[*].description)
  provides:
    - ParamConsistencyChecker (D-11) — per-tool batch LLM consistency gate
    - Fail-closed polarity-inverted Signature pattern (is_consistent, not has_conflicts)
  affects:
    - 13-08-PLAN (evolve_tool_params CLI): wires check_all() into reject-whole-run gate
tech_stack:
  added: []
  patterns:
    - Polarity-inverted boolean Signature field (is_consistent) so _parse_bool's
      conservative 'unknown -> False' default fails CLOSED (reject on ambiguity)
    - Deterministic JSON encoding of evolved_param_descriptions
      (ensure_ascii=False, sort_keys=True) for stable log/replay comparison
    - try/except wrapping dspy.ChainOfThought call — any LM/parse exception
      returns ConstraintResult(passed=False) (fail-closed)
    - Sibling-class co-location with ToolFactualChecker (shared _parse_bool helper)
key_files:
  created: []
  modified:
    - evolution/tools/tool_constraints.py (+161 lines; ParamConsistencyChecker class appended)
decisions:
  - "Kept check() kwargs frozen_desc/param_descs (as specified by Wave 0 tests in 13-01) instead of plan-specified frozen_tool_description/evolved_param_descriptions — tests are the binding contract. Internally the Signature still uses the longer descriptive field names (frozen_tool_description, evolved_param_descriptions) because those appear in the LLM prompt."
  - "Polarity inversion confirmed (Pitfall 5): Signature output is `is_consistent: bool` (NOT `has_conflicts`). This makes _parse_bool's conservative default — unknown text returns False — automatically produce passed=False (reject) on ambiguous LLM output. Verified by smoke test: _parse_bool('maybe') is False, _parse_bool(None) is False."
  - "check_all() signature is (evolved_tools, frozen_tool_descs: dict) — different from ToolFactualChecker.check_all(original_tools, evolved_tools) because the frozen tool-level descriptions here come from ToolModule._frozen_tool_desc (not from a list of 'original' ToolDescription objects). Caller (13-08) supplies this dict."
  - "Local `import json as _json` inside check() to avoid touching module-level imports (which are minimal — only dspy + EvolutionConfig + ConstraintResult)."
metrics:
  duration_minutes: 15
  completed_date: "2026-05-07"
---

# Phase 13 Plan 04: ParamConsistencyChecker Summary

**One-liner:** Implemented D-11 — per-tool batch LLM consistency checker with inverted-polarity Signature (`is_consistent`, not `has_conflicts`) so `_parse_bool`'s conservative "unknown → False" default fails CLOSED on ambiguous output.

## What Was Built

Appended `ParamConsistencyChecker` class after the existing `ToolFactualChecker` in `evolution/tools/tool_constraints.py`. The new class mirrors the ToolFactualChecker structure (inner `dspy.Signature` + `dspy.ChainOfThought` + `check()` + `check_all()` methods + shared `_parse_bool` helper) while implementing Pitfall 5's polarity inversion:

- **`ConsistencySignature`**: Inputs `tool_name`, `frozen_tool_description`, `evolved_param_descriptions` (JSON string). Outputs `is_consistent: bool` + `explanation: str`.
- **`check(tool_name, frozen_desc, param_descs)`**: Runs one LLM call per tool inside `dspy.context(lm=...)`. Returns `ConstraintResult(constraint_name="param_consistency", ...)`. Fail-closed on any exception or ambiguous bool.
- **`check_all(evolved_tools, frozen_tool_descs)`**: Iterates `ToolDescription` list; builds `{param_name: description}` dict from `.params`; calls `check()` per tool; returns list of `ConstraintResult`.

## Key Implementation Points

1. **Polarity inversion verified**: `grep "has_conflicts" evolution/tools/tool_constraints.py` returns nothing from ParamConsistencyChecker (only the original `has_false_claims` in ToolFactualChecker). Signature uses `is_consistent: bool` → `_parse_bool('maybe') = False` → `passed = False` (reject).

2. **Test kwargs match Wave 0 contract**: Wave 0 RED tests use `checker.check(tool_name=..., frozen_desc=..., param_descs=...)`. The implementation matches exactly — this is different from the plan's proposed `frozen_tool_description=`/`evolved_param_descriptions=` kwargs, but tests are the binding contract.

3. **JSON serialization deterministic**: `json.dumps(param_descs, ensure_ascii=False, sort_keys=True)` so CJK characters render correctly and cross-run comparison is stable.

4. **Exception-wrapped call**: `try/except Exception` around `self.checker(...)` — any DSPy/network/parse error returns `ConstraintResult(passed=False, ...)` with exception message in `details`. Matches ToolFactualChecker's conservative pattern but makes it explicit.

5. **Shared `_parse_bool`**: Reuses the existing module-level helper (lines 15-29) without modification. Same function serves both checkers; contrast with FactualCheck where `True` means "reject" (has_false_claims) vs. here where `True` means "accept" (is_consistent).

## Deviations from Plan

None structurally. Two minor kwarg naming adjustments, both driven by the Wave 0 test contract written in 13-01:

1. **`check()` kwargs**: Plan specified `frozen_tool_description=` / `evolved_param_descriptions=`. Wave 0 tests use `frozen_desc=` / `param_descs=`. I chose the test names because RED tests are the binding contract. The Signature's internal InputField names still use the longer descriptive versions (which surface in the LLM prompt), so the LLM-facing semantics are unchanged.

2. **`check_all()` second arg**: Plan specified `frozen_tool_descs: dict[str, str]`; tests use positional `frozen_descs` dict. Aligned with test usage (positional dict argument).

## Tests

**Wave 0 RED → GREEN (3 tests, all passing)**:
- `tests/tools/test_param_consistency.py::test_detects_conflicts` — mock `is_consistent=False` → passed=False with explanation in details
- `tests/tools/test_param_consistency.py::test_malformed_json_fallback` — mock `is_consistent="maybe ok?"` → `_parse_bool` returns False → passed=False (fail-closed)
- `tests/tools/test_param_consistency.py::test_whole_tool_rejection` — `check_all` over 2 ToolDescriptions where one produces `is_consistent=False` → list with ≥1 failed

**Non-regression (21 tests, all passing)**:
- `tests/tools/test_tool_constraints.py` — all ToolFactualChecker tests, `_parse_bool` branch tests, and size constraint reuse tests continue passing. Module imports intact.

Total: **24/24 tests green** (3 new + 21 existing).

## Acceptance Criteria (from plan)

| Criterion | Status |
|-----------|--------|
| `class ParamConsistencyChecker` appears at line after `ToolFactualChecker` | Line 152 (after 32) |
| `is_consistent` appears ≥3 times | 5 matches (Signature + OutputField decl + 3 usage sites) |
| `has_false_claims` still matches original | Preserved at line 60 |
| Import surface smoke: `ParamConsistencyChecker, ToolFactualChecker, _parse_bool` | `import OK` |
| `pytest tests/tools/test_param_consistency.py -x` exits 0 | PASS (3/3) |
| `pytest tests/tools/test_tool_constraints.py -x` exits 0 | PASS (21/21) |
| Fail-closed smoke: `_parse_bool('maybe') is False`, `_parse_bool(None) is False`, `_parse_bool(True) is True` | `fail-closed OK` |

## Threat Model Compliance

All 4 threats from plan `<threat_model>` mitigated:

- **T-13-11 (Prompt injection)**: Evolved param text is passed as a JSON InputField value (properly escaped via `json.dumps`). DSPy ChainOfThought field-level framing + future 200-char size cap (enforced upstream in 13-08) bound injection surface.
- **T-13-12 (Info disclosure)**: `explanation` text flows to `ConstraintResult.details` → `metrics.json`. No NEW disclosure (param descriptions already logged).
- **T-13-13 (DoS)**: Per-param size gate (`_check_size("param_description") <= 200 chars`) upstream of this checker. Tool param count schema-bounded.
- **T-13-14 (Repudiation / silent pass)**: **Primary mitigation.** Polarity inversion + conservative `_parse_bool` + explicit try/except ensures ANY failure mode (exception, ambiguous output, missing field) → `passed=False`. Verified by `test_malformed_json_fallback`.

## Operational Anomaly (for orchestrator awareness)

During commit, `cd` into the main repo path bypassed the worktree context and the initial commit `d9ff99b feat(13-04): implement ParamConsistencyChecker with inverted polarity` landed on `main` branch instead of `worktree-agent-aff3555ce977a9f12`. Per the `<destructive_git_prohibition>` rule (never self-recover from protected ref drift), I did NOT reset main. Instead I cherry-picked the same commit into the worktree branch as `f644b59` (identical content/message). The orchestrator's worktree-merge step will likely deduplicate via merge-base / patch-id; flagging here for awareness. The file changes and tests exist correctly on the worktree branch; no work was lost.

## Self-Check: PASSED

**Files:**
- FOUND: evolution/tools/tool_constraints.py (modified; 307 lines total; ParamConsistencyChecker at line 152)
- FOUND: .planning/phases/13-per-parameter-description-optimization/13-04-SUMMARY.md (this file)

**Commits:**
- FOUND: f644b59 feat(13-04): implement ParamConsistencyChecker with inverted polarity (on worktree-agent-aff3555ce977a9f12)
- ANOMALY: d9ff99b (duplicate commit on main; see Operational Anomaly above)

**Verification:**
- 24/24 tests passing (`pytest tests/tools/test_param_consistency.py tests/tools/test_tool_constraints.py`)
- Fail-closed smoke script passes
- Polarity inversion verified via `__annotations__` check
