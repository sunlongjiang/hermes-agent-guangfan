---
phase: 13
plan: 03
type: execute
status: complete
requirements:
  - TOOL-V2-02
files_created: []
files_modified:
  - evolution/tools/tool_metric.py
tests_added:
  - tests/tools/test_joint_metric.py (Wave 0 — already added by 13-01; now GREEN)
---

## What was built

Extended `evolution/tools/tool_metric.py` with two Phase 13 metrics, four private helpers, and an updated module docstring. Existing `tool_selection_metric` and `CrossToolRegressionChecker` remain untouched (Phase 5 backwards compatibility).

Public surface added:
- `joint_tool_param_metric(example, prediction, trace=None, pred_name=None, pred_trace=None) -> float` — the D-10/D-17 acceptance and holdout metric. Returns `0.5 * tool_match + 0.5 * param_match` where both are exact-match (tool after strip+lower, params after strip_plus_coerce dict comparison). GEPA 5-param signature contract satisfied.
- `joint_tool_param_metric_with_feedback(example, prediction, trace=None, pred_name=None, pred_trace=None) -> dspy.Prediction` — the GEPA reflection_lm variant. Returns `dspy.Prediction(score=float, feedback=str)`. Delegates score to the bare metric; feedback string names wrong tool / invalid JSON / missing, extra, and wrong-value param keys (without echoing the full correct_params dict).

Private helpers added:
- `_coerce_scalar(v)` — tries bool → int → float in that order on stripped strings; preserves PEP 285 bool-before-int ordering.
- `_normalize_param_value(v)` — recursive normalization across dict/list; dispatches on `_NORMALIZATION_RULE`.
- `_parse_selected_params_json(raw)` — try/except json.loads; returns None on malformed input (T-13-08 DoS mitigation — no crash, no partial credit).
- `_param_match_score(predicted, correct)` — 1.0 iff same keys AND all normalized values equal, else 0.0.

Normalization policy — `_NORMALIZATION_RULE = "strip_plus_coerce"` (evidence: `13-correct-params-type-inspection.txt` reports 6 value types — str=363, int=26, list=19, bool=15, dict=7, float=3 — so coercion is the right default against stringified LLM outputs). W3 constant-vs-inspection match verified: both values are the literal string `strip_plus_coerce`.

## Tests

- `tests/tools/test_joint_metric.py` — 4/4 GREEN (Wave 0 RED → GREEN)
  - `test_exact_match_cases` (tool+params match → 1.0, one mismatch → 0.5, both → 0.0)
  - `test_5_param_signature` (GEPA `inspect.signature().bind(None,None,None,None,None)` succeeds)
  - `test_json_decode_error_handling` (malformed `selected_params` → param_match=0.0, no exception)
  - `test_feedback_metric_shape` (dspy.Prediction with `.score: float` + `.feedback: str`)
- `tests/tools/test_tool_metric.py` — 17/17 still pass (no regression in Phase 5 path).

Total: 21/21 pass (`.venv/bin/python -m pytest tests/tools/test_joint_metric.py tests/tools/test_tool_metric.py`).

## Acceptance criteria

- [x] Two new top-level functions with verified GEPA 5-param signature
- [x] Feedback variant returns `dspy.Prediction` (attribute-safe) — NOT a bare dict (grep for `return {"score":` returns 0 matches)
- [x] Wave 0 RED tests green; Phase 5 tests untouched
- [x] `_NORMALIZATION_RULE` matches 13-01 recorded recommendation (W3 guard)
- [x] Invalid JSON → param_match = 0.0 (no partial credit)
- [x] Feedback string does not echo full correct_params dict (T-13-09 mitigation)

## Commits

- `37a2d7b` — feat(13-03): add joint_tool_param_metric + ScoreWithFeedback variant
- (this SUMMARY commit) — docs(13-03): complete joint metric plan

## Recovery note

The executor agent stalled on the stream watchdog after committing `37a2d7b` and printing "工作树干净。现在创建 SUMMARY.md。" but before writing this file. The orchestrator recovered by inspecting the worktree, re-running the test suite (21/21 green), and authoring SUMMARY.md from the feat commit content + plan contract. No feat work was lost; no changes beyond this SUMMARY commit were added during recovery.

## Self-Check: PASSED
