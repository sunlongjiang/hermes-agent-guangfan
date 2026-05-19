---
phase: 20-benchmark-gated-validation
reviewed: 2026-05-19T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - datasets/prompts/tblite_stratified_subset.json
  - evolution/benchmarks/__init__.py
  - evolution/benchmarks/benchmark_gate.py
  - evolution/benchmarks/build_tblite_calibration.py
  - evolution/benchmarks/tblite_runner.py
  - evolution/prompts/evolve_prompt_sections.py
  - tests/benchmarks/__init__.py
  - tests/benchmarks/test_benchmark_gate.py
  - tests/benchmarks/test_build_tblite_calibration.py
  - tests/benchmarks/test_tblite_runner.py
  - tests/prompts/test_evolve_prompt_sections_cli.py
findings:
  critical: 4
  warning: 9
  info: 5
  total: 18
status: issues_found
---

# Phase 20: Code Review Report

**Reviewed:** 2026-05-19
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

The Phase 20 benchmark-gate code is structurally well-organized (TBLiteRunner subprocess wrapper, TBLiteBenchmarkGate validator, calibration CLI) and the test suite is broad. However, the review uncovered four BLOCKER-class defects that will manifest on the very first real run:

1. The Virtual Prompt Overlay silently discards all-but-one evolved sections when multiple sections are evolved (multi-section is the default code path).
2. The gate calls `TBLiteRunner.run(task_filter=...)` with raw subset items, which under the new W-7 schema are `dict` objects — the runner's `_validate_task_filter` will reject them with `ValueError`. Production use is broken; tests pass only because their fixtures still use the legacy flat-string schema.
3. Both pre-flight git checks ignore `subprocess.run().returncode`, so a non-zero git exit with empty stdout silently passes (or worse, produces a misleading "stale anchor" diagnostic).
4. `compute_artifact_hash` accepts items shaped as either dict or PromptSection but the dict path requires `["section_id"]` / `["text"]` — `KeyError` on slightly malformed cache lookups.

The remaining findings are mostly quality (oversized monolithic `evolve()` function, weak whitelist regex that admits `..`/`/`, head-of-tail slicing, missing returncode checks).

## Critical Issues

### CR-01: Multi-section overlay silently drops all but the last evolved section

**File:** `evolution/benchmarks/benchmark_gate.py:325-344`
**Issue:** `_run_overlay` repeatedly calls `write_back_section(self._target_path, sec, sec.text, dest=overlay_path)` inside the loop. Reading `prompt_loader.write_back_section` (`evolution/prompts/prompt_loader.py:175,200-201`), it ALWAYS reads its content from `prompt_builder_path` (i.e. `self._target_path`, the unmodified original) and ALWAYS writes the full file body to `output_path` (i.e. `dest=overlay_path`). Therefore each loop iteration completely overwrites the prior iteration's evolved section in `overlay_path`. After N evolved sections, only the section processed LAST appears in the overlay; the others are reverted to the original.

This is the default code path (multi-section optimization is what Phase 17 joint mode produces), so any real-world TBLite run that evolves more than one section will benchmark the original prompt with one section swapped — not the evolved prompt. Risk_Score will appear artificially low/normal, and the gate will accept regressions.

Tests do not catch this: `test_cache_miss_writes_result_only_on_accept` and `test_fs_boundary_cross_fs_uses_copy2_fallback` both use a single `_FakeSection`, so the bug is invisible.

**Fix:**
```python
# Option A: read+rewrite the overlay each iteration (chain the edits).
for sec in sorted_evolved:
    write_back_section(
        overlay_path,        # SOURCE = overlay (carries prior edits)
        sec,
        sec.text,
        dest=overlay_path,   # write back into overlay
    )

# Option B (preferred): apply all sections in memory, single write.
source_text = self._target_path.read_text()
lines = source_text.splitlines(keepends=True)
for sec in sorted_evolved:                       # bottom-up
    start, end = sec.line_range
    replacement = _format_section_replacement(sec, sec.text)
    lines = lines[:start - 1] + replacement.splitlines(keepends=True) + lines[end:]
overlay_path.write_text("".join(lines))
```
Either fix must be accompanied by a regression test that exercises N>=2 sections (e.g. `test_run_overlay_preserves_all_sections`).

### CR-02: Gate passes W-7 dict subset items to TBLiteRunner, which rejects them as unsafe

**File:** `evolution/benchmarks/benchmark_gate.py:556` (and `evolution/benchmarks/tblite_runner.py:134-151`)
**Issue:** `check()` calls

```python
run_result = self.runner.run(
    task_filter=list(self.stratified_subset["task_filter"]),
    output_dir=run_dir,
)
```

Under the W-7 schema (declared in `datasets/prompts/tblite_stratified_subset.json:43-50` and exercised in `tests/prompts/test_evolve_prompt_sections_cli.py:1255-1260`), `task_filter` is a `list[dict]` of `{name, tier}` objects. `TBLiteRunner._validate_task_filter` checks `isinstance(name, str)` (line 145) and raises `ValueError("Unsafe task name ...")` on dicts.

Only `build_tblite_calibration.main` (lines 322-332) extracts `item["name"]` before invoking the runner. The gate has no equivalent step. The gate constructor's docstring at line 104 even claims `task_filter` is `list[str]`, and the runtime schema assertion at line 150-153 says `"stratified_subset must have task_filter: list[str]"` — both contradict the actual W-7 schema.

Result: every production `--benchmark=tblite` run will crash with `ValueError("Unsafe task name {'name': 't-easy', ...}")` inside the gate. Tests pass because the test fixtures in `tests/benchmarks/test_benchmark_gate.py:52-59` and the legacy fallback at line 1167 use flat strings.

**Fix:**
```python
# evolution/benchmarks/benchmark_gate.py near line 556 (extract names like
# build_tblite_calibration.py:322-332 does):
raw_filter = self.stratified_subset["task_filter"]
task_names: list[str] = []
for item in raw_filter:
    if isinstance(item, dict) and "name" in item:
        task_names.append(item["name"])
    elif isinstance(item, str):
        task_names.append(item)
    else:
        raise TypeError(f"task_filter item has unexpected shape: {item!r}")
run_result = self.runner.run(task_filter=task_names, output_dir=run_dir)
```
Also tighten constructor validation to accept BOTH shapes and update the schema error message at line 150-153. Add a regression test that constructs a gate from the actual W-7 fixture and asserts no `ValueError` reaches the runner.

### CR-03: `_check_anchor_existence` and `_check_overlay_sanity` ignore subprocess returncode

**File:** `evolution/benchmarks/benchmark_gate.py:215-232` and `249-270`
**Issue:** Both git invocations:

```python
res = subprocess.run([...], cwd=..., capture_output=True, text=True, timeout=10)
# returncode never inspected
```

Behavior:
- `_check_overlay_sanity`: if `git status --porcelain` exits non-zero (broken repo, `.git/` corrupted, lock file, etc.) with empty stdout, the dirty-tree check silently passes. The function then proceeds to perform the overlay swap on an unknown-state hermes-agent — exactly the failure mode D-10 was added to prevent (CONCERNS §M6).
- `_check_anchor_existence`: if `git rev-parse HEAD` fails (e.g. detached HEAD with no commits, broken repo, wrong cwd), `current_commit` becomes `""`. Then `"" != anchor_commit` is True (anchor was just validated to contain a hermes_agent_commit), and the user gets a misleading "Anchor stale: anchor hermes_agent_commit=def45678 but current=<missing>" message. The fix instructions tell them to re-calibrate, which will hit the same git error and produce a worse anchor.

Note that the otherwise-equivalent helpers in `build_tblite_calibration.py:99-110` DO check `res.returncode != 0` — the bug is gate-specific.

**Fix:**
```python
# Apply to both call sites:
try:
    res = subprocess.run([...], cwd=..., capture_output=True, text=True, timeout=10)
except (subprocess.TimeoutExpired, FileNotFoundError) as e:
    console.print(f"[red]git status check failed: {type(e).__name__}: {e}[/red]")
    sys.exit(1)
if res.returncode != 0:
    console.print(
        f"[red]git command failed (exit={res.returncode}): "
        f"{res.stderr.strip() or '<no stderr>'}[/red]"
    )
    sys.exit(1)
# ... existing stdout-based logic ...
```

### CR-04: `compute_artifact_hash` raises KeyError on dict items missing required keys

**File:** `evolution/benchmarks/tblite_runner.py:412-425`
**Issue:** When `evolved_sections` items are dicts, the code uses bare subscription:

```python
elif isinstance(s, dict):
    normalized.append({
        "section_id": s["section_id"],
        "text": s["text"],
    })
```

A dict missing `section_id` or `text` raises an uncaught `KeyError` instead of the consistent `TypeError` raised on the else branch. Worse, any external caller passing `{"id": "...", "text": "..."}` or `{"section_id": "...", "body": "..."}` will hit this from inside the gate's `check()` (line 511-516), aborting the whole benchmark run with a stack trace that points at the cache code rather than at the malformed input.

The corresponding test `test_cache_key_deterministic` (line 232-245) only passes well-formed dicts.

**Fix:**
```python
elif isinstance(s, dict):
    if "section_id" not in s or "text" not in s:
        raise TypeError(
            f"evolved_sections dict missing required keys "
            f"'section_id' and/or 'text': got keys={sorted(s.keys())}"
        )
    normalized.append({"section_id": s["section_id"], "text": s["text"]})
```

## Warnings

### WR-01: `_TASK_NAME_RE` whitelist admits `..` and `/` — defeats T-20-05 mitigation

**File:** `evolution/benchmarks/tblite_runner.py:61`
**Issue:** `_TASK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-./]{0,127}$")` allows `.` and `/` after the first character. Strings like `tblite/../../etc/passwd`, `t./../escape`, `a/../../b` all pass validation. The module docstring (line 23-25) advertises this as the security boundary for T-20-05 ("task names follow the [a-zA-Z0-9_-]+ pattern"), but the implementation is much looser.

While the runner only joins these into a CSV passed to `--env.task_filter`, downstream consumers in hermes-agent's tblite_env.py may interpret the value as a path or pass it to a shell. The mitigation should match the documentation.

**Fix:**
```python
# Strict version matching the docstring claim:
_TASK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,127}$")
# OR if dotted/slashed names are required, explicitly reject path traversal:
_TASK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-./]{0,127}$")
def _validate_task_filter(task_filter):
    ...
    for name in task_filter:
        if not isinstance(name, str) or not _TASK_NAME_RE.match(name) or ".." in name:
            raise ValueError(...)
```
Update the docstring to reflect what the regex actually enforces.

### WR-02: Misleading "stderr tail" — actually takes head of the tail

**File:** `evolution/benchmarks/build_tblite_calibration.py:397`
**Issue:** `f"stderr tail: {run_result.stderr_tail[:5]}"` — `stderr_tail` is already the LAST 20 stderr lines (set in `tblite_runner.py:321` as `stderr_buf[-20:]`). Slicing `[:5]` returns the FIRST 5 of those 20, which is the OLDEST stderr output — exactly the opposite of what an operator wants when diagnosing a TBLite failure ("show me the most recent error messages"). The variable name "tail" is contradicted by the slice.

**Fix:**
```python
f"stderr tail: {run_result.stderr_tail[-5:]}"
```

### WR-03: Schema validation message contradicts the W-7 schema

**File:** `evolution/benchmarks/benchmark_gate.py:150-153`
**Issue:** The validation message says `"stratified_subset must have task_filter: list[str]"` but the documented and current schema (see `datasets/prompts/tblite_stratified_subset.json:43-50` `_meta.schema_note`) is `list[{name, tier}]`. The docstring at line 103-104 also says `list[str]`. Any operator who hits this error and follows the message will produce a file the gate cannot consume.

**Fix:** update the message and docstring to read `list[{name, tier}] or list[str]` (legacy), and validate inner item shape during construction. See CR-02 fix.

### WR-04: Empty-tier silent zero-anchoring masks data quality issues

**File:** `evolution/benchmarks/build_tblite_calibration.py:169-170` and `145-171`
**Issue:** `_one_run_per_tier_pass_rate` returns `0.0` for any tier whose `by_tier[t]` list is empty (no tasks, all `infra_fail`, or category mis-spelled). Calibration then writes `anchor_per_tier[tier]["mean"] = 0.0`. The gate later computes `threshold = max(0.0, 0.0) - 1.96 * stdev`, which is always negative — so candidate pass rates can never breach an empty tier. A user who mis-configures `per_tier_counts` (e.g. mistyped `medium` -> `mediun`) gets a passing gate with no warning that an entire tier silently disappeared.

**Fix:** Detect zero-sample tiers and either fail the calibration with an actionable error, or persist `n=0` and have the gate skip that tier with a warning rather than silently anchor at zero.
```python
# In build_tblite_calibration.py around line 412-424:
for tier in TIERS:
    scores = [run.get(tier, 0.0) for run in per_run_per_tier]
    n_observed = sum(
        len([t for t in r.per_task
             if not t.get("infra_fail") and str(t.get("category","")).lower() == tier])
        for r in per_run_per_tier_full  # original results, not just per-tier rate
    )
    if n_observed == 0:
        raise click.ClickException(
            f"Tier {tier!r} produced 0 valid samples across {n_runs} runs — "
            f"check per_tier_counts and task names in stratified_subset.json"
        )
```

### WR-05: `check()` does not check git status before the snapshot/replace cycle when cache hits

**File:** `evolution/benchmarks/benchmark_gate.py:510-529`
**Issue:** Pre-flight checks (`_check_anchor_existence` and `_check_overlay_sanity`) are intentionally skipped on cache hits. That is reasonable for the overlay sanity check (no overlay happens), but it means a cached "accept" decision can be returned for an anchor whose `hermes_agent_commit` no longer matches the current HEAD — exactly the staleness condition D-14 was added to detect. The cache key includes the dataset_revision_hash but NOT the hermes_agent_commit. So if a user re-checks-out hermes-agent at a different commit, the gate returns a cached accept that was computed against a different prompt baseline.

**Fix:** Either include `hermes_agent_commit` in the cache key, or run `_check_anchor_existence` BEFORE the cache lookup so stale anchors abort regardless of cache state.

### WR-06: `evolve()` function is 1300+ lines — unmaintainable, untestable in isolation

**File:** `evolution/prompts/evolve_prompt_sections.py:189-1503`
**Issue:** The single `evolve()` function spans ~1314 lines and 11 numbered steps with deeply nested conditionals (joint vs round-robin × benchmark vs no-benchmark × drift accept/warn/reject × tier filter object vs string × cache hit/miss × cost-budget exceeded). Cyclomatic complexity is well into the dozens. New features (Phase 22 async-full-verify referenced in line 1083-1088) will further inflate it. Reading the file requires scrolling through 100+ comment markers (W-1 through W-7, D-AB-01 through D-15, etc.) that document partial revisions.

This makes review difficult (this finding alone took most of the review budget), and Plan 21+ will be hard to land without regressions in untested combinations.

**Fix:** Extract phase-shaped helpers: `_run_drift_gate(...)`, `_run_benchmark_gate(...)`, `_persist_success(...)`, `_persist_failed(...)`, `_run_optimization(...)`, `_run_ab_baseline(...)`. Each helper takes a small dataclass holding the shared state. Target: `evolve()` becomes a 100-200 line orchestrator. This is mechanical and low-risk if done with the existing test suite as a regression baseline.

### WR-07: `--accept-stale-anchor` flag has misleading name

**File:** `evolution/benchmarks/build_tblite_calibration.py:227-236, 279-285`
**Issue:** The flag name says "stale-anchor" but its actual effect is "skip the dirty-tree guard" — it has nothing to do with anchor staleness. The output anchor still records the current `git HEAD`, so users may think the flag affects the recorded commit, when it only suppresses a pre-flight check. The help text says "Allow writing the anchor even if hermes-agent has uncommitted changes" but the flag is consumed only by `if not accept_stale_anchor: _check_hermes_clean(...)`.

**Fix:** Rename to `--allow-dirty-tree` (or `--unsafe-skip-clean-check`) and update help text. Existing test `test_accept_stale_anchor_bypasses_git_check` needs renaming alongside.

### WR-08: `run_status_any_error` only flags non-`ok` runs; partial-data scenarios merge silently

**File:** `evolution/benchmarks/benchmark_gate.py:553-581`
**Issue:** When `run_result.status != "ok"` (line 568), the code marks `run_status_any_error = True` but STILL appends the partial `_one_run_per_tier_pass_rate(run_result)` to `per_run_per_tier`. The aggregation at line 576-577 then computes a mean across mixed real + partial-failed runs. The decision override at line 580 flips accept→reject, but operators who see "decision=reject" plus per-tier numbers near the threshold will likely re-investigate rather than recognize "this is a subprocess error, not a quality regression."

Also, with `runs=3` and one hang_timeout, the candidate stdev jumps artificially (3 runs at e.g. `[0.85, 0.85, 0.0]` gives stdev ≈ 0.49), which widens the breach band and could mask a real regression on retry.

**Fix:** Skip failed runs from `per_run_per_tier` AND `samples_paths` aggregation. Add a `failed_runs: int` field to the report. If `failed_runs >= runs / 2`, force `decision = "reject"` with reason "insufficient successful runs."

### WR-09: `evolve_prompt_sections.py` re-formats `optimization_tracker_spent` cost twice with identical comments

**File:** `evolution/prompts/evolve_prompt_sections.py:1314-1321, 1434-1444`
**Issue:** Two large comment blocks (~10 lines each) repeat the same justification for using `optimization_tracker_spent` rather than `locals().get(...)`. The FAILED path at line 1318-1321 and the success path at line 1441-1444 produce identical `total_cost_breakdown` dicts; this is a copy-paste pattern that will drift the next time a third cost source is added.

**Fix:** Extract a tiny helper:
```python
def _cost_breakdown(opt_spent: float, bench_spent: float) -> dict[str, float]:
    return {"optimization": float(opt_spent), "benchmark": float(bench_spent)}
```
Call from both paths.

## Info

### IN-01: Missing returncode check in `_git_head` falls through to empty-string check elsewhere

**File:** `evolution/benchmarks/build_tblite_calibration.py:98-110`
**Issue:** `_git_head` does inspect `res.returncode != 0` (good), but the function still relies on its caller to interpret `""` as a failure. The caller at line 286-291 does check this. Acceptable, but adding a debug `console.print` showing the stderr on returncode != 0 would aid diagnostics.

**Fix:**
```python
if res.returncode != 0:
    console.print(f"[yellow]git rev-parse exit={res.returncode}: {res.stderr.strip()}[/yellow]")
    return ""
```

### IN-02: `_parse_samples_jsonl` opens file without explicit encoding

**File:** `evolution/benchmarks/tblite_runner.py:354`
**Issue:** `with open(jsonl_path) as f:` uses platform default encoding. TBLite is documented as Python tooling that emits UTF-8 JSON, but on Windows hosts with cp1252 default, non-ASCII text in error messages or task names could raise `UnicodeDecodeError`.

**Fix:** `with open(jsonl_path, encoding="utf-8") as f:`

### IN-03: `lazy import inside `_run_overlay` re-imports on every call

**File:** `evolution/benchmarks/benchmark_gate.py:314`
**Issue:** `from evolution.prompts.prompt_loader import write_back_section` lives inside `_run_overlay`. Python caches the import, so the cost is negligible, but the comment chain at lines 1-15 of `evolution/benchmarks/__init__.py` already explains the lazy-import strategy at module level. The mid-function import would be cleaner moved to module top, gated by a `TYPE_CHECKING` block if necessary, since `prompt_loader` does not transitively import hermes-agent or huggingface_hub.

**Fix:** Move to module-top imports unless a circular import is documented.

### IN-04: `_meta.placeholder=true` warning in stratified subset only fires when calibration is run — not when gate runs

**File:** `datasets/prompts/tblite_stratified_subset.json:43-50` (consumer: `evolution/prompts/evolve_prompt_sections.py:1108-1136`)
**Issue:** The placeholder subset committed under `_meta.placeholder=true` flags itself as wave-1 not-yet-finalized. Calibration warns the user (line 338-345). But the BenchmarkGate consumer at evolve_prompt_sections.py only warns when `anchor._meta.tier == "mock"` (line 1128-1136), not when `subset._meta.placeholder == True`. A user who ships before Plan 05 replaces the placeholder names will get a successful gate run against fake task names.

**Fix:** Add a parallel warning around line 1121 of `evolve_prompt_sections.py`:
```python
if subset.get("_meta", {}).get("placeholder"):
    console.print("[bold yellow]⚠ Stratified subset is placeholder ...[/bold yellow]")
```

### IN-05: `subprocess.run` cwd cast to str is unnecessary on Python 3.10+

**File:** `evolution/benchmarks/benchmark_gate.py:217, 251`; `evolution/benchmarks/build_tblite_calibration.py:101, 125`
**Issue:** `cwd=str(self.config.hermes_agent_path)` — subprocess.run accepts `Path` objects directly since 3.6. The `str(...)` cast is a no-op style relic.

**Fix:** Drop the `str(...)` wrappers (minor cleanup, not strictly necessary).

---

_Reviewed: 2026-05-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
