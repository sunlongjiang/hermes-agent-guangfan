---
phase: 16-per-tool-regression-dashboard
reviewed: 2026-05-14T00:00:00Z
depth: standard
files_reviewed: 24
files_reviewed_list:
  - evolution/tools/regression_dashboard.py
  - evolution/tools/tool_metric.py
  - evolution/tools/tool_dataset.py
  - evolution/tools/evolve_tool_params.py
  - evolution/tools/evolve_tool_descriptions.py
  - evolution/tools/evolve_tool_reasoning.py
  - tests/tools/test_regression_dashboard.py
  - tests/tools/test_persist_raw_predictions.py
  - tests/tools/test_tool_dataset.py
  - tests/tools/test_evolve_tool_params_cli.py
  - tests/tools/test_evolve_tool_descriptions.py
  - tests/tools/test_evolve_tool_reasoning.py
  - .gitignore
  - tests/fixtures/dashboard_runs/desc_old/metrics.json
  - tests/fixtures/dashboard_runs/json_corrupt/metrics.json
  - tests/fixtures/dashboard_runs/params_complete/metrics.json
  - tests/fixtures/dashboard_runs/params_complete_v2/metrics.json
  - tests/fixtures/dashboard_runs/params_multi_regress/metrics.json
  - tests/fixtures/dashboard_runs/params_no_raw/metrics.json
  - tests/fixtures/dashboard_runs/reasoning_complete/ab_comparison.json
  - tests/fixtures/dashboard_runs/reasoning_complete/metrics.json
  - tests/fixtures/dashboard_runs/reasoning_old/metrics.json
  - tests/fixtures/dashboard_runs/reasoning_with_secret/ab_comparison.json
  - tests/fixtures/dashboard_runs/reasoning_with_secret/metrics.json
findings:
  critical: 3
  warning: 7
  info: 6
  total: 16
status: issues_found
---

# Phase 16: Code Review Report

**Reviewed:** 2026-05-14T00:00:00Z
**Depth:** standard
**Files Reviewed:** 24
**Status:** issues_found

## Summary

Phase 16 delivers a standalone Rich-CLI regression dashboard
(`regression_dashboard.py`, ~788 LoC) and wires `raw_predictions` /
`per_tool_*_rates` persistence into three `evolve_tool_*` CLIs. The code is
generally well-structured and the test suite is broad, but adversarial review
surfaced three blocker-level defects:

1. **`--runs` flag is broken in production.** `_scan_runs` treats every
   `--runs` value as a *root* and globs `<value>/*/metrics.json`, but the
   docstring and `--help` text both document `--runs` as a *run directory*.
   Every test patches `_scan_runs`, so this is never exercised — the flag
   silently finds zero runs against the documented input shape.
2. **`--runs` and `--baseline-run` have inconsistent path semantics** —
   `--baseline-run <dir>` reads `<dir>/metrics.json` directly, while
   `--runs <dir>` globs one level deeper. Same conceptual input, two
   incompatible interpretations.
3. **`evolve_tool_reasoning` mixes two different scoring metrics into one
   gate.** `th_*_full` now comes from `_score_with_predictions` (raw,
   case-sensitive, tool-only match) while `th_*_ambig` still comes from
   `_safe_score` → `joint_tool_param_metric` (normalized, tool+param
   composite). `ThinkABGate.check()` compares both — apples vs oranges.

Warnings cluster around silent re-reads, deprecated `datetime.utcnow()`,
inconsistent local-vs-UTC time handling, and FAILED-dir metrics that omit the
new persistence keys.

## Critical Issues

### CR-01: `--runs` flag silently finds zero runs against documented input

**File:** `evolution/tools/regression_dashboard.py:54-60`, `588-589`, `624-627`
**Issue:** `_scan_runs` globs `root.glob("*/metrics.json")` — i.e. it treats
each `--runs` value as a *parent root* containing run subdirectories. But the
module docstring (line 11: `--runs path/to/run1`) and the `--help` text
(line 589: `"Run directory (repeatable; appends to default roots)"`) both
document `--runs` as pointing at an individual *run directory* that contains
`metrics.json` directly. Passing `--runs output/tools/20260512_103000` (a real
run dir) makes `_scan_runs` look for `output/tools/20260512_103000/*/metrics.json`
and find nothing. Every test in `test_regression_dashboard.py` patches
`_scan_runs` (`return_value=[...]`), so the real glob is never exercised — the
bug is fully masked by the test suite.
**Fix:** Decide on one semantic and make code + docs agree. If `--runs` is a
run directory, scan it explicitly:
```python
def _scan_runs(roots: tuple[Path, ...], explicit_runs: tuple[Path, ...] = ()) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if root.exists():
            found.extend(root.glob("*/metrics.json"))
    for run_dir in explicit_runs:
        mp = Path(run_dir) / "metrics.json"
        if mp.exists():
            found.append(mp)
    return sorted(set(found), key=lambda p: p.stat().st_mtime)
```
and call it as `_scan_runs(DEFAULT_ROOTS, tuple(Path(r) for r in runs))`. Add a
test that does NOT patch `_scan_runs` so the glob/explicit-path logic is
actually covered.

### CR-02: `--runs` vs `--baseline-run` path semantics are inconsistent

**File:** `evolution/tools/regression_dashboard.py:624-627` vs `675-676`
**Issue:** `--baseline-run` / `--evolved-run` are consumed as
`_load_run(Path(baseline_run) / "metrics.json")` (line 675-676) — the value is
a run directory whose `metrics.json` is read directly. But `--runs` values are
appended to `roots` and passed to `_scan_runs`, which globs `*/metrics.json`
one level *below* them (see CR-01). A user who learns "`--baseline-run` takes a
run directory" will reasonably assume `--runs` does too, and get zero results
with no error. This is a latent correctness/usability defect that produces
silently wrong output (empty LATEST/TREND, "No runs found" exit 2).
**Fix:** Unify the semantics — both flags should accept a run directory and
both should resolve `<dir>/metrics.json`. See CR-01 fix; apply the same
explicit-run handling so `--runs` and `--baseline-run` interpret their
arguments identically.

### CR-03: `evolve_tool_reasoning` feeds two incompatible metrics into one A/B gate

**File:** `evolution/tools/evolve_tool_reasoning.py:469-473`, `492-505`
**Issue:** After the Phase 16 wiring change, `th_off_full` / `th_on_full` are
produced by `_score_with_predictions` (line 470-471), which scores with a raw
`correct == selected` comparison — **case-sensitive, no `.strip().lower()`
normalization, tool-name only** (line 676). Meanwhile `th_off_ambig` /
`th_on_ambig` still come from `_safe_score` → `_score_module_on_holdout` →
`joint_tool_param_metric` (line 472-473), which is **normalized
(`strip().lower()`) and a 0.5 tool + 0.5 param composite**
(`tool_metric.py:353-362`). Both pairs are then handed to the *same*
`ThinkABGate.check()` (line 498-505): the full-regression gate compares
`th_on_full` vs `th_off_full` (metric A) while the ambiguous-improvement gate
compares `th_on_ambig` vs `th_off_ambig` (metric B). A model whose only change
is parameter quality, or whose tool names differ only in case, will move one
metric and not the other — making the gate's pass/fail decision incoherent.
The pre-Phase-16 code used `_safe_score` for `th_*_full` too, so this is a
regression introduced by this phase.
**Fix:** Make `_score_with_predictions` use the same scoring function as the
rest of the pipeline. Either compute `score` via `joint_tool_param_metric`
inside the loop, or normalize the comparison to match
`tool_selection_metric` semantics:
```python
correct_n = correct.strip().lower()
selected_n = selected.strip().lower()
total += 1.0 if correct_n == selected_n else 0.0
```
and confirm with the Phase 15 gate authors which metric (`joint_tool_param`
vs tool-only) is the contractually-correct one for `th_*_full`, then use it
consistently for both full and ambiguous scores.

## Warnings

### WR-01: `datetime.utcnow()` is deprecated and emits a runtime warning

**File:** `evolution/tools/regression_dashboard.py:563`
**Issue:** `datetime.utcnow()` is deprecated since Python 3.12 and scheduled
for removal; on the project's Python 3.13/3.14 runtime it emits a
`DeprecationWarning` (confirmed at review time). The CLAUDE.md stack pins
Python >=3.10 with a 3.13 venv, so this will warn on every dashboard run.
**Fix:**
```python
"generated_at": datetime.now(timezone.utc).isoformat(),
```
(import `timezone` from `datetime`; the trailing `+ "Z"` becomes redundant
since `isoformat()` on an aware datetime already includes the offset, or use
`.strftime("%Y-%m-%dT%H:%M:%SZ")` on the UTC value).

### WR-02: TREND `--trend-days` cutoff mixes local time with mtime, and `generated_at` uses UTC

**File:** `evolution/tools/regression_dashboard.py:703-707` vs `563`
**Issue:** The `--trend-days` window computes `cutoff = datetime.now().timestamp() - ...`
(local-time wall clock) and compares against `Path(...).stat().st_mtime`
(epoch seconds — fine), but `_write_dashboard_json` stamps `generated_at` with
`datetime.utcnow()`. The dashboard therefore reports a UTC `generated_at`
while its own day-window math runs on local time. In non-UTC timezones a run
created "today" can fall just outside or inside the window inconsistently with
the reported timestamp. Low blast radius but a genuine correctness smell.
**Fix:** Use one clock everywhere. `datetime.now().timestamp()` and
`st_mtime` are both epoch-based and already consistent — keep that for the
window — and switch `generated_at` to the same basis (local `datetime.now()`
isoformat, or convert both to UTC). Pick one and document it.

### WR-03: `_load_run` is called 2-3× per run path — silent redundant disk reads

**File:** `evolution/tools/regression_dashboard.py:640-658`, `691-698`, `675-676`
**Issue:** `main()` loads every scanned run once in the classification loop
(line 641), then `_load_run` is invoked *again* for every path in the TREND
`valid_runs` loop (line 692), and again for DIFF runs (line 675-676). For the
`json_corrupt` fixture this means re-parsing a known-bad file multiple times;
for large `raw_predictions` payloads it re-reads and re-`json.loads()` the
whole file. Beyond wasted I/O, the two passes can *disagree* if a file changes
mid-run (TOCTOU), and the classification pass's `dropped[]` reasons are not
reused by the TREND pass. Not a crash, but a maintainability/correctness
hazard.
**Fix:** Load each run exactly once into a `dict[Path, dict]` cache (or build
`usable_runs` / `valid_runs` from the single classification pass) and have
DIFF/TREND consume the cached records.

### WR-04: FAILED-dir `metrics.json` omits `raw_predictions` / `per_tool_*_rates`

**File:** `evolution/tools/evolve_tool_descriptions.py:368-381`
**Issue:** In `evolve_tool_descriptions.evolve()`, `raw_preds` and the per-tool
rate dicts are computed (lines 338-366) but `persist_per_tool_rates` /
`persist_raw_predictions` are only applied at line 405-406 — *after* the
regression-fail early `return` at line 381. A `REGRESSION_FAILED` run therefore
writes a metrics.json with only `timestamp/status/baseline_score/evolved_score/
regressed_tools`. The dashboard's `_load_run` then drops it for "missing
per_tool_*_rates" — so a regressed run, which is exactly the case the
regression dashboard exists to surface, is invisible to the dashboard.
**Fix:** Move the `persist_per_tool_rates` / `persist_raw_predictions` calls
before the regression-result branch so the FAILED metrics.json carries the
per-tool data, mirroring `evolve_tool_params.py:1018-1029` which correctly
persists before its `_write_failed_dir` call.

### WR-05: DIFF region renders `None` source label when run source is undetectable

**File:** `evolution/tools/regression_dashboard.py:677-683`, `330-333`
**Issue:** The DIFF guard (lines 677-682) only checks that `metrics` and
`per_tool_evolved_rates` are present — it does not require `source` to be
non-None. `_render_diff` then interpolates `baseline_run['source']` /
`evolved_run['source']` straight into the table title (line 331-332), so a run
whose source `_detect_source` could not classify renders a literal
`DIFF region [None vs None]: ...` heading. Cosmetic, but it ships malformed
output instead of failing or labelling clearly.
**Fix:** Either reject DIFF runs with `source is None` (consistent with how
the classification pass drops them from LATEST/TREND), or coerce in
`_render_diff`: `baseline_run['source'] or '?'`.

### WR-06: `_render_frequency_bars` can emit a blank-named bar from empty `correct_tool`

**File:** `evolution/tools/regression_dashboard.py:210`, `277-294`
**Issue:** `sample_counts = Counter(rec.get("correct_tool", "") for rec in raw_preds)`
(line 210) will produce an empty-string key if any `raw_predictions` record is
missing/blank `correct_tool`. `persist_raw_predictions` coerces missing
`correct_tool` to `""` (`tool_metric.py:510`), so this is reachable from real
data. `_render_frequency_bars` then prints a row like `"" + bar + count` — a
ghost bar with no label. The same empty key also pollutes `sample_counts.get(tool)`
lookups in `_render_latest`.
**Fix:** Filter empties before counting:
`Counter(t for t in (rec.get("correct_tool", "") for rec in raw_preds) if t)`,
and skip empty keys in the frequency-bar loop.

### WR-07: `_score_with_predictions` swallows all per-example AND batch-level exceptions silently

**File:** `evolution/tools/evolve_tool_reasoning.py:660-681`
**Issue:** The inner `except Exception: continue` (line 665-666) drops any
per-example failure with no logging, and the outer `except Exception: return
0.0, tool_pairs, raw_preds` (line 680-681) swallows a batch-level failure
(e.g. `dspy.context` setup error) and returns a partial/empty result as if it
were a real 0.0 score. Compare `evolve_tool_params._evaluate_holdout`
(lines 388-398) which at least prints a yellow `console.print` for skipped
examples. Here a fully-broken holdout pass produces `score=0.0` indistinguishable
from a genuinely 0%-accurate model, and that 0.0 then feeds the V1 gate and
ThinkABGate — silently failing the run for the wrong reason.
**Fix:** Log skipped examples (`console.print` yellow, as `_evaluate_holdout`
does) and, for the outer handler, either re-raise or emit a loud warning and
set a sentinel so the caller can distinguish "scoring crashed" from "model
scored 0.0". Counting skipped examples in the returned tuple would let the
caller gate on it.

## Info

### IN-01: `_load_run` `loaded is None` branches are dead code

**File:** `evolution/tools/regression_dashboard.py:642`, `645`
**Issue:** `_load_run` always returns a dict (parse-error path returns a dict
with `metrics: None`, `_drop_reason` set — lines 71-72; it never returns
`None`). The `loaded is None` checks at lines 642 and the `if loaded else
"load failed"` fallback at 645 are therefore unreachable.
**Fix:** Drop the `is None` checks, or change `_load_run`'s contract to
actually return `None` on hard failure (the docstring at line 63 says
"or None on parse error" — the code disagrees with its own docstring).

### IN-02: `tests/fixtures/dashboard_runs/json_corrupt/` is never referenced by any test

**File:** `tests/fixtures/dashboard_runs/json_corrupt/metrics.json`
**Issue:** The corrupt-JSON fixture was added in this phase but no test in
`test_regression_dashboard.py` loads it. `test_e2e_dashboard_json_schema` uses
5 explicit fixture paths, none of which is `json_corrupt`. The JSON-parse-error
drop path (`_load_run` lines 71-72) thus has no functional coverage.
**Fix:** Add a test that scans `json_corrupt` and asserts it appears in
`dropped_runs[]` with a `json parse error` reason, or remove the unused
fixture.

### IN-03: Test docstrings/comments contradict the fixture data they exercise

**File:** `tests/tools/test_regression_dashboard.py:51-53`, `74`, `367`
**Issue:** `test_status_color_coding` and `test_warning_threshold_no_exit`
repeatedly describe `params_complete`'s `browser_navigate` row as
"delta=-5pp", but the fixture has `per_tool_baseline_rates.browser_navigate =
0.60` and `per_tool_evolved_rates.browser_navigate = 0.50` → actual delta is
**-10pp**. The assertions still pass (they only require `<= -2.0`), but the
misleading comments will send a future maintainer to debug a non-bug.
**Fix:** Update the comments to say `-10pp`, or adjust the fixture to actually
be `-5pp` if that was the intent.

### IN-04: `_quintiles` over `seg_rates` mislabels columns as min/p25/median/p75/max

**File:** `evolution/tools/regression_dashboard.py:146-186`
**Issue:** `_segment_distribution` computes one accuracy rate *per segment*
(line 180-181) and then runs `_quintiles` over that short list of segment
rates (line 185). With `--segment difficulty` there are at most 3 segments, so
the "p25/median/p75" columns are quintiles of 3 numbers — statistically
meaningless and not what a reader expects from a "distribution" column. The
TREND legend explains the cross-run semantics (line 419-424) but LATEST has no
such caveat.
**Fix:** Either compute the distribution over per-example outcomes within each
tool (a real spread), or rename the LATEST columns / add a legend clarifying
they are per-segment rates, not a percentile distribution of samples.

### IN-05: `_detect_source` step 2 comment claims params detection is unreachable for reasoning, but only by ordering luck

**File:** `evolution/tools/regression_dashboard.py:86-108`
**Issue:** The docstring says `param_predictors_discovered` is "NOT used for
reasoning even though reasoning shares — step 1 catches first". This is true
only because every reasoning `metrics.json` happens to contain
`think_ab_gate`. A reasoning run that failed before the gate was assembled
(see `evolve_tool_reasoning.py:435-447`, the `GEPA_FAILED` metrics dict has no
`think_ab_gate`) but still wrote `param_predictors_discovered` would be
misclassified as `params`. Low likelihood (FAILED dirs are not scanned for
LATEST), but the comment overstates the guarantee.
**Fix:** Add the directory-name check (`tools_reasoning`) *before* the
`param_predictors_discovered` check, or note the assumption explicitly.

### IN-06: `evolve_tool_descriptions.evolve()` still uses bare `sys.exit(1)` instead of the exit-code-return pattern

**File:** `evolution/tools/evolve_tool_descriptions.py:152`, `160`, `199`,
`205`, `327-329`, `379-381`
**Issue:** `evolve_tool_params.py` and `evolve_tool_reasoning.py` were
refactored to a `_evolve_impl() -> int` + `sys.exit(int(exit_code))` pattern
for testability, but `evolve_tool_descriptions.evolve()` still calls
`sys.exit(1)` directly mid-function and `return`s on soft failures. This
inconsistency makes the three sibling CLIs harder to test uniformly and means
`evolve_tool_descriptions` failure modes can't be unit-tested without catching
`SystemExit`. Not a Phase 16 regression (pre-existing), but the phase touched
this file and left the inconsistency.
**Fix:** Out of scope for a pure dashboard phase, but worth a follow-up todo:
align `evolve_tool_descriptions` with the `_evolve_impl` exit-code pattern.

---

_Reviewed: 2026-05-14T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
