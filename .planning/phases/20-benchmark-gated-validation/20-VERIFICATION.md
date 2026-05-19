---
phase: 20-benchmark-gated-validation
verified: 2026-05-19T14:35:36Z
status: human_needed
score: 19/20 must-haves verified (code-level); 1 must-have requires live calibration deferred to user
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Live TBLite calibration run (Plan 20-05, Wave 4)"
    expected: |
      `python -m evolution.benchmarks.build_tblite_calibration --runs 3 --benchmark-max-cost 50.0`
      produces `datasets/prompts/tblite_anchor.json` with:
        - anchor_per_tier covering all 4 tiers (easy/medium/hard/extreme) each with n>=3, numeric mean+stdev
        - hermes_agent_commit matching `git rev-parse HEAD` of the hermes-agent checkout
        - dataset_revision_hash either real HF sha OR documented `unknown_v1.0` fail-open
        - tblite_estimated_cost_per_task_usd measured (likely 0.3-0.6)
        - calibration_timestamp / calibration_model / tblite_runner_version populated
      Plus `datasets/prompts/tblite_stratified_subset.json` updated with REAL TBLite task names
      replacing the Wave-1 `tblite-easy-01..tblite-extreme-03` placeholders; `_meta.placeholder`
      flipped to false.
      Then re-run `python -m evolution.prompts.evolve_prompt_sections --benchmark=tblite ...`
      end-to-end against the hermes-agent checkout to confirm step 10.5 actually executes
      TBLite subprocess + Risk_Score gating instead of fail-closing at the anchor-existence check.
    why_human: |
      Plan 20-05 was explicitly deferred at user direction. Live calibration requires:
        - OPENROUTER_API_KEY + MODAL_TOKEN_ID env vars (not available in this session)
        - Clean hermes-agent tree
        - ~$36 API budget approved by the user
        - 1-3 hour wall clock for 3 runs × 30 tasks
      The codebase is set up to fail-closed when the anchor file is missing (Plan 06
      anchor-existence pre-check at evolve_prompt_sections.py:1123-1129 raises click.ClickException
      with the recovery command). This is the correct behavior — but the runtime gating path
      itself has not been exercised end-to-end against a real hermes-agent subprocess.
  - test: "Multi-section overlay fix (CR-01) regression test"
    expected: |
      Add a regression test exercising N>=2 evolved sections through `TBLiteBenchmarkGate._run_overlay`
      to lock in the CR-01 fix (commit 416b8f3). The fix is in place and the change is correct
      (chain edits through overlay_path), but the test suite as committed still uses single-section
      `_FakeSection` fixtures (per REVIEW.md CR-01 fix instructions). Without a regression test the
      bug could silently re-emerge in a future refactor.
    why_human: |
      The fix is correct by inspection (overlay_path serves as both source and dest in the
      loop, threading edits cumulatively). But REVIEW.md CR-01 closing instructions explicitly
      asked for an N>=2-section regression test that was not added in the follow-up commits.
      Verifying that the fix actually preserves multi-section content end-to-end requires
      either (a) a live hermes-agent overlay run (covered by the previous human test) or
      (b) a unit test with two `_FakeSection` instances exercising different line_ranges.
---

# Phase 20: Benchmark-Gated Validation — Verification Report

**Phase Goal:** Use TBLite as optional hard regression gate after optimization
**Verified:** 2026-05-19T14:35:36Z
**Status:** human_needed
**Re-verification:** No (initial verification)

## Executive Summary

All code-level must-haves are present, tested, and verifiably wired. Phase 20's 5 executed plans (01, 02, 03, 04, 06) deliver the complete TBLite benchmark gate surface area:

- 4 new `EvolutionConfig` benchmark fields with full YAML/env/CLI override chain
- `TBLiteRunner` subprocess wrapper (Async Stream Pipe + State Monitor, daemon threads, heartbeat hang detection, samples.jsonl parser, T-20-05 task-name whitelist)
- `TBLiteBenchmarkGate` with Risk_Score algorithm, Virtual Prompt Overlay (snapshot/replace/restore), content-addressed cache, pre-flight checks (D-10/D-14)
- `build_tblite_calibration` CLI with Pre-flight Watermark check, HuggingFace dataset_revision_hash fail-open, multi-run aggregation
- `evolve_prompt_sections --benchmark={none,tblite,tblite-full}` integration via step 10.5 with FAILED_<ts>/ reject path and side-by-side `tblite_report.json` on both accept and reject
- All 4 REVIEW.md CR-class defects (CR-01..CR-04) closed by post-review commits
- 695 tests pass; 9 TestBenchmarkGate integration tests pass; 48 tests/benchmarks/ all pass

**The single deferred item is Plan 20-05 (live anchor calibration):** `datasets/prompts/tblite_anchor.json` does not exist on disk. This is a runtime-level prerequisite for `--benchmark=tblite` to actually execute (instead of fail-closing at the anchor-existence pre-check). The deferral is **documented in STATE.md** as a tracked user-initiated decision, not an undiscovered gap. PMPT-V2-03 is IMPLEMENTED but NOT YET VALIDATED at runtime.

## Goal Achievement

### Observable Truths (from ROADMAP Success Criteria + Plan must_haves)

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1   | Optional `--benchmark` flag triggers TBLite evaluation before accepting evolved sections (ROADMAP SC #1) | VERIFIED | `evolve_prompt_sections.py:1590` adds `--benchmark` Click flag with choices `[none|tblite|tblite-full]`; `--help` confirms it; integration at step 10.5 (lines 1118-1366) instantiates `TBLiteBenchmarkGate` and calls `check_all(...)` before write-back; reject path at line 1305-1366 writes FAILED_<ts>/ and returns BEFORE step 11 (write-back) |
| 2   | Configurable pass threshold (default: no regression on core capabilities) (ROADMAP SC #2) | VERIFIED | `TIER_WEIGHTS = {easy:1.0, medium:1.5, hard:2.0, extreme:4.0}` (benchmark_gate.py:62); `REJECT_THRESHOLD = 4.0` (line 68); both can be overridden via TBLiteBenchmarkGate constructor (`tier_weights=`/`reject_threshold=` kwargs at line 128); `--benchmark-max-cost` CLI flag also configurable; per-tier breach test uses 1.96σ confidence band (`CONFIDENCE_Z = 1.96`) |
| 3   | Benchmark results saved to output metrics (ROADMAP SC #3) | VERIFIED | `evolve_prompt_sections.py:1439` writes `metrics["benchmark_decision"]` always; lines 1441-1444 conditionally write `benchmark_passed`/`benchmark_risk_score`/`benchmark_per_tier`; `tblite_report.json` written side-by-side at lines 1347 (reject) AND 1485 (accept); `total_cost_breakdown` includes both optimization and benchmark tracker spend (line 1335, real CostTracker via Edit-0 W-2/W-3) |
| 4   | 4 new EvolutionConfig benchmark fields with YAML/env/CLI override chain | VERIFIED | config.py:75-93 declares all 4 fields (benchmark_max_cost_usd=50.0, tblite_estimated_cost_per_task_usd=0.4, benchmark_runs=3, benchmark_heartbeat_seconds=60); YAML at lines 158-200; env at lines 235-272 (EVOLUTION_BENCHMARK_MAX_COST_USD etc.); CLI overrides at lines 315-340; all 4-block pattern |
| 5   | TBLiteRunner subprocess wrapper streams output (NOT blocking subprocess.run) | VERIFIED | tblite_runner.py:253 uses `subprocess.Popen(args, cwd=..., stdout=PIPE, stderr=PIPE, text=True, bufsize=1)`; zero occurrences of `subprocess.run` in the file; 2 daemon threads at lines 267, 272 pump stdout/stderr into queue.Queue |
| 6   | Heartbeat-based hang detection (queue.Empty → hang_count → SIGTERM) | VERIFIED | tblite_runner.py:293,322 catch queue.Empty; heartbeat clamped via `max(1, int(hb_raw))` at constructor (T-20-04 mitigation); test_heartbeat_timeout_triggers_hang covers it |
| 7   | samples.jsonl parser with per-line try/except + infra_fail flagging | VERIFIED | tblite_runner.py:352-390 implements per-line JSONDecodeError skip; D-24 mirror; infra_fail flag set on rows with non-empty `error` field (Risk Anchor 3) |
| 8   | compute_artifact_hash() returns 16-char hex (D-15 cache key) | VERIFIED | tblite_runner.py:393-447; uses sha256(canonical_json + dataset_revision_hash + seed_bytes + TBLITE_RUNNER_VERSION).hexdigest()[:16]; TBLITE_RUNNER_VERSION = "1.0" at line 51 |
| 9   | Task_filter whitelist regex prevents shell injection (T-20-05) | VERIFIED | tblite_runner.py:61 defines `_TASK_NAME_RE`; WR-01 fix (commit 5a0a37a) tightened pattern + added `..` path traversal block; `_validate_task_filter` at line 140 |
| 10  | TBLiteBenchmarkGate Risk_Score algorithm (tier-weighted breach sum) | VERIFIED | benchmark_gate.py:62-74 declares constants; `_compute_risk_score`/breach logic at gate.check(); rejects when risk_score >= REJECT_THRESHOLD; per-tier breach uses `mean(candidate) < max(anchor_mean, moving_avg) - 1.96 * candidate_stdev` (Adaptive Sliding Window D-01) |
| 11  | Virtual Prompt Overlay: snapshot → atomic replace → ALWAYS restore | VERIFIED | benchmark_gate.py:345-410 `_run_overlay` snapshots target, copies to overlay_path, applies sections bottom-up (CR-01 fix: chains through overlay_path), atomic os.replace OR shutil.copy2 fallback (cross-fs); `_restore_overlay` at line 412 + try/finally at line 561 (1 occurrence, D-09 mandate) |
| 12  | Pre-flight checks: _check_anchor_existence + _check_overlay_sanity (D-10/D-14) | VERIFIED | benchmark_gate.py:264-311 (anchor) + 202-262 (overlay); both inspect git returncode (CR-03 fix, commit 1fbc0c4); both raise sys.exit(1) on dirty tree or stale anchor; 8 occurrences of sys.exit(1) total in file |
| 13  | Content-addressed cache (D-15) — cache hit short-circuits subprocess | VERIFIED | benchmark_gate.py:564-568 calls compute_artifact_hash; cache write only on accept (decision policy from SUMMARY); WR-05 fix (commit 9bd5cbe) moved anchor freshness check BEFORE cache lookup; test_cache_hit_short_circuits_subprocess covers it |
| 14  | write_back_section accepts optional dest= parameter for overlay staging | VERIFIED | prompt_loader.py:142-148 signature has `*, dest: "Path \| None" = None`; docstring updated to document SOURCE vs dest semantics |
| 15  | build_tblite_calibration CLI is runnable + has 8 documented flags | VERIFIED | `python -m evolution.benchmarks.build_tblite_calibration --help` shows all flags: --hermes-repo, --seed, --runs, --output-json, --benchmark-max-cost, --model, --api-base, --allow-dirty-tree (--accept-stale-anchor alias, WR-07); module main at line 242 |
| 16  | Pre-flight Watermark check (D-17): estimated × 3 must fit budget | VERIFIED | build_tblite_calibration.py:356-371; raises ClickException when watermark > budget BEFORE subprocess starts; test_pre_flight_watermark_blocks_when_insufficient_budget passes |
| 17  | HuggingFace dataset_revision_hash with fail-open fallback (D-15 + RA5) | VERIFIED | build_tblite_calibration.py:68-87 wraps HfApi() in try/except, falls back to `unknown_v{TBLITE_RUNNER_VERSION}` on ANY exception; test_huggingface_fallback_on_api_error confirms |
| 18  | Anchor JSON has full D-CAL-01 schema (all 8 top-level keys + per-tier mean/stdev/n) | VERIFIED (by test) | build_tblite_calibration.py:492-499 builds anchor dict with anchor_per_tier, calibration_timestamp, dataset_revision_hash, hermes_agent_commit, stratified_subset_seed, tblite_estimated_cost_per_task_usd, tblite_runner_version; test_anchor_json_schema_complete asserts all keys exist |
| 19  | 6 new CLI flags on evolve_prompt_sections | VERIFIED | --help confirms all 6 flags exist: --benchmark, --benchmark-tier, --benchmark-cache/--no-benchmark-cache, --benchmark-max-cost, --wait/--detach, --async-full-verify/--no-async-full-verify; click.option decorators at lines 1590, 1601, 1609, 1617, 1626, 1635 |
| 20  | datasets/prompts/tblite_anchor.json exists with live calibration data (Plan 05 Wave 4) | NOT VERIFIED (deferred) | File does not exist on disk. STATE.md "Phase 20 — Wave 4 Deferred" documents explicit user choice to defer. `evolve_prompt_sections.py:1123-1129` correctly fail-closes with click.ClickException pointing to recovery command. Code is wired up; live execution is the deferral. |

**Code-level score:** 19/19 verified
**Runtime-level score:** 0/1 verified (deferred to human)

### Required Artifacts

| Artifact | Expected    | Status | Details |
| -------- | ----------- | ------ | ------- |
| `evolution/core/config.py` | 4 new fields + YAML/env/CLI override chain | VERIFIED | grep confirms 15+ benchmark_max_cost_usd occurrences across 4-block pattern |
| `evolution/benchmarks/__init__.py` | Docstring-only lazy-import guard | VERIFIED | 15 lines, docstring confirms D-Discretion-1 lazy-import-guard pattern; no eager submodule imports |
| `evolution/benchmarks/tblite_runner.py` | TBLiteRunner + TBLiteRunResult + compute_artifact_hash + TBLITE_RUNNER_VERSION (>= 180 lines) | VERIFIED | 448 lines; all symbols present; daemon=True ×2; queue.Empty ×3; subprocess.Popen ×4; subprocess.run ×0 |
| `evolution/benchmarks/benchmark_gate.py` | TBLiteBenchmarkGate + Risk_Score + Virtual Overlay + Pre-flight + cache (>= 350 lines) | VERIFIED | 737 lines; class TBLiteBenchmarkGate at line 95; TIER_WEIGHTS + REJECT_THRESHOLD + CONFIDENCE_Z all module-level; os.replace ×4; shutil.copy2 ×6; finally ×1; sys.exit(1) ×8 |
| `evolution/benchmarks/build_tblite_calibration.py` | Click CLI producing tblite_anchor.json (>= 300 lines) | VERIFIED | 525 lines; 8 @click.option decorators; main() at line 242 |
| `evolution/prompts/prompt_loader.py` | write_back_section accepts optional dest= parameter | VERIFIED | signature at lines 142-148; docstring updated |
| `evolution/prompts/evolve_prompt_sections.py` | Step 10.5 + 6 CLI flags + benchmark_* metrics + real optimization CostTracker | VERIFIED | optimization_tracker (line 501); step 10.5 (lines 1078-1366); 6 click flags (lines 1590-1640); benchmark_decision metrics (line 1439); tblite_report.json writes at 1347 AND 1485 |
| `datasets/prompts/tblite_stratified_subset.json` | 30-task W-7 schema with per_tier_counts (easy:12, medium:8, hard:7, extreme:3) | VERIFIED | All 30 items have {name, tier} dict shape; tier counts verified; _meta.schema_version=2; _meta.placeholder=true (correct — Wave 4 will overwrite) |
| `datasets/prompts/tblite_anchor.json` | Live anchor with anchor_per_tier across 4 tiers (Plan 05 Wave 4) | MISSING (deferred) | Not on disk; STATE.md documents user-initiated deferral; runtime fail-closed behavior is correct |
| `.gitignore` | tblite_anchor.json + tblite_stratified_subset.json exceptions + logs/ ignore | VERIFIED | Lines 27, 28, 48 confirm all three rules present |
| `tests/benchmarks/test_tblite_runner.py` | 7+ tests covering Popen/streams/heartbeat/samples/jsonl-skip/infra-fail/hash | VERIFIED | 9 tests pass in 12s |
| `tests/benchmarks/test_benchmark_gate.py` | 12+ tests covering Risk_Score/anchor/overlay/cache/fs-boundary | VERIFIED | 18+ tests pass in <6s |
| `tests/benchmarks/test_build_tblite_calibration.py` | 6+ CliRunner tests covering schema/seed/HF/git-block/Watermark/cost | VERIFIED | 8 tests pass in 6s |
| `tests/prompts/test_evolve_prompt_sections_cli.py::TestBenchmarkGate` | 6+ CLI integration tests with W-4 double-patch | VERIFIED | 9 tests pass in 0.5s |
| `.planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md` | Tracking todo for deferred --detach + subcommands | VERIFIED | File exists; tracks 2 Phase 22 deferrals |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| config.py | evolution.yaml | data.get('benchmark_max_cost_usd') | WIRED | lines 158-200 all 4 keys |
| config.py | env vars | EVOLUTION_BENCHMARK_* | WIRED | lines 235-272 |
| config.py | CLI overrides | overrides.get('benchmark_*') | WIRED | lines 315-340 |
| tblite_runner.py | subprocess.Popen | streaming subprocess with cwd=hermes_agent_path, text=True, bufsize=1 | WIRED | line 253 |
| tblite_runner.py | daemon threads | threading.Thread(target=_pump_stream, ..., daemon=True) | WIRED | lines 267, 272 |
| tblite_runner.py | queue.Queue | q.get(timeout=heartbeat_seconds) → queue.Empty → hang_count | WIRED | lines 293, 322 |
| tblite_runner.py | hashlib.sha256 | compute_artifact_hash 16-char hex | WIRED | line 443 |
| benchmark_gate.py | TBLiteRunner | self.runner.run(task_filter=task_names, output_dir=...) | WIRED | line 624; CR-02 fix extracts dict→name |
| benchmark_gate.py | prompt_builder.py overlay | os.replace + shutil.copy2 fallback | WIRED | lines 401-408 |
| benchmark_gate.py | write_back_section(dest=) | overlay-path chain (CR-01 fix) | WIRED | line 385 |
| benchmark_gate.py | cache_dir/<hash>/result.json | compute_artifact_hash → cache file | WIRED | line 564 |
| benchmark_gate.py | tblite_history.json | moving_avg history | WIRED | (per Plan 03 must_have) |
| build_tblite_calibration.py | TBLiteRunner | task_names = [item['name'] for ...] (W-7) | WIRED | lines 327-337 |
| build_tblite_calibration.py | CostTracker | tracker = CostTracker(max_usd=budget) | WIRED | lines 44, 382 |
| build_tblite_calibration.py | huggingface_hub.HfApi | _hf_dataset_revision with try/except fail-open | WIRED | lines 68-87 |
| build_tblite_calibration.py | datasets/prompts/tblite_anchor.json | output_json.write_text | WIRED (code present, file not produced; Plan 05 deferred) |
| evolve_prompt_sections.py step 10.5 | TBLiteBenchmarkGate | lazy import + gate.check_all(...) | WIRED | lines 1118, 1222, 1263 |
| evolve_prompt_sections.py step 6 | CostTracker (optimization) | wraps GEPA/MIPROv2 compile | WIRED | lines 501, 504, 631 (Edit-0 W-2/W-3 fix) |
| evolve_prompt_sections.py step 11 | metrics.json benchmark_* fields | metrics['benchmark_decision'] = ... | WIRED | lines 1439-1444 |
| evolve_prompt_sections.py step 11 | output/prompts/<ts>/tblite_report.json | (output_dir / 'tblite_report.json').write_text(...) | WIRED | lines 1347 (reject), 1485 (accept) |
| evolve_prompt_sections.py anchor-existence pre-check | datasets/prompts/tblite_anchor.json | raise click.ClickException if missing | WIRED (correctly fail-closes when file absent) | lines 1123-1129 |

### Data-Flow Trace (Level 4)

Phase 20 produces CLI artifacts (no JSX/component rendering). Level 4 trace focuses on the data path: anchor JSON → gate → metrics.json/tblite_report.json output.

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| metrics.json `benchmark_decision` | `benchmark_decision` local | gate.check_all() at line 1263 | YES when anchor exists; `"skipped"` default otherwise | FLOWING (with deferral) |
| metrics.json `benchmark_per_tier` | `benchmark_per_tier` local | gate.check_all() at line 1267 | YES per-tier dict from real TBLite subprocess output (or test mock) | FLOWING |
| tblite_report.json | `tblite_report_payload` local | gate.check_all() at line 1265 | YES — includes anchor_per_tier/candidate_per_tier/risk_score/breach_map | FLOWING |
| FAILED_<ts>/ + ABORTED_<ts>/ paths | output_dir variants | step 10.5 reject path lines 1305-1366 | YES — writes 4 artifacts before returning | FLOWING |
| datasets/prompts/tblite_anchor.json (produced by build_tblite_calibration) | `anchor` dict | live TBLite subprocess + statistics aggregation | DEFERRED — Plan 05 not executed; live calibration requires user-side resources | DISCONNECTED (deferred, not broken) |

**Note:** The single DISCONNECTED data flow (anchor file production) is the documented user deferral, not a hidden gap. Fail-closed behavior at the anchor-existence pre-check is correct: gate cannot operate without live calibration data per D-13 ("no mock fallback").

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Benchmark module imports without hermes-agent reachable | `python -c "from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate, TIER_WEIGHTS, REJECT_THRESHOLD, CONFIDENCE_Z"` | All constants accessible | PASS |
| Runner module exposes expected symbols | `python -c "from evolution.benchmarks.tblite_runner import TBLiteRunner, TBLITE_RUNNER_VERSION, compute_artifact_hash, TBLiteRunResult"` | TBLITE_RUNNER_VERSION = "1.0" | PASS |
| Calibration CLI is runnable with --help | `python -m evolution.benchmarks.build_tblite_calibration --help` | 8 flags shown; "Build TBLite anchor + persist datasets/prompts/tblite_anchor.json" | PASS |
| evolve CLI exposes 6 new benchmark flags | `python -m evolution.prompts.evolve_prompt_sections --help \| grep -E "\-\-benchmark\|\-\-wait\|\-\-detach\|\-\-async-full-verify"` | All 6 flags visible | PASS |
| Phase 20 unit tests pass | `pytest tests/benchmarks/ -q` | 48 passed in 18s | PASS |
| Phase 20 CLI integration tests pass | `pytest tests/prompts/test_evolve_prompt_sections_cli.py::TestBenchmarkGate -q` | 9 passed in 0.5s | PASS |
| Full project test suite passes | `pytest tests/ -q` | 695 passed, 1 skipped, 1 xfailed in 47.5s | PASS |
| Anchor file presence check | `test -f datasets/prompts/tblite_anchor.json` | NOT FOUND | EXPECTED (Plan 05 deferred) |
| Step 10.5 fail-closes when anchor missing | (verified by code reading at lines 1123-1129) | click.ClickException raised with recovery command | PASS (code level) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| PMPT-V2-03 | Plans 20-01 through 20-06 | Benchmark-gated validation (TBLite as hard regression gate) | IMPLEMENTED but NOT RUNTIME-VALIDATED | All code-level integration present (CLI flag at evolve_prompt_sections.py:1590; gate algorithm at benchmark_gate.py; runner at tblite_runner.py; calibration CLI at build_tblite_calibration.py; evolve integration at evolve_prompt_sections.py step 10.5). Requires live calibration (Plan 05 deferred at user direction). REQUIREMENTS.md currently marks status="Pending" — should be marked "Complete (pending runtime calibration)" or similar nuance once anchor is produced. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| evolution/benchmarks/build_tblite_calibration.py | 315, 343-349 | "placeholder" mentions | INFO | Intentional — first match is in ClickException message asking user to run Plan 01; second is the Wave-1 placeholder warning when subset has `_meta.placeholder=true`. Both are correct runtime guards, not stubs. |
| datasets/prompts/tblite_stratified_subset.json | (data) | task_filter contains `tblite-easy-01..tblite-extreme-03` placeholder names | INFO | Documented in Plan 05 as the deliverable being deferred. Wave 4 calibration replaces these with real HF task names. Not a hidden stub — `_meta.placeholder=true` and the calibration CLI emits a yellow warning when it encounters this marker. |

No blocker anti-patterns identified. The placeholder values are correctly flagged at runtime by the calibration CLI's `_meta.placeholder` warning at lines 343-349.

### Code Review (REVIEW.md) Closure Status

REVIEW.md identified 4 CRITICAL + 9 WARNING + 5 INFO findings (18 total). Subsequent commits closed:

| Finding | Severity | Commit | Status |
| ------- | -------- | ------ | ------ |
| CR-01: Multi-section overlay silently drops sections | CRITICAL | 416b8f3 | CLOSED (chain through overlay_path) |
| CR-02: Gate passes W-7 dict to runner, runner rejects | CRITICAL | c1b8af7 | CLOSED (extract task_names list) |
| CR-03: Pre-flight git checks ignore returncode | CRITICAL | 1fbc0c4 | CLOSED (inspect returncode + sys.exit(1)) |
| CR-04: compute_artifact_hash KeyError on malformed dicts | CRITICAL | a1b4b91 | CLOSED (raise TypeError with clear message) |
| WR-01: Task name regex admits `..` and `/` | WARNING | 5a0a37a | CLOSED (tighten regex + reject `..`) |
| WR-02: "stderr tail" takes head of tail | WARNING | 99d27a8 | CLOSED |
| WR-04: Empty-tier silent zero-anchoring | WARNING | c269015 | CLOSED |
| WR-05: Cache hits skip git status check | WARNING | 9bd5cbe | CLOSED |
| WR-07: --accept-stale-anchor misleading name | WARNING | 9e93c3d | CLOSED (renamed to --allow-dirty-tree) |
| WR-08: run_status_any_error keeps partial data | WARNING | f8ac957 | CLOSED |
| WR-09: Duplicated cost-breakdown blocks | WARNING | ee020dd | CLOSED (extract _cost_breakdown helper) |
| WR-03 | WARNING | (not seen in log) | OPEN — schema validation msg |
| WR-06 | WARNING | (not seen in log) | OPEN — evolve() monolith 1300+ lines |
| IN-01..IN-05 | INFO | (not seen in log) | OPEN — minor improvements (acceptable) |

All 4 critical findings are closed. WR-06 (monolithic evolve()) is a quality concern, not a goal-blocker; carrying it to a Phase 22+ refactor todo would be appropriate. WR-03 is a docstring/error-message clarity issue, also non-blocking.

### Deferred Items

Items not yet met but explicitly addressed in this phase via user-initiated deferral. Per STATE.md "Phase 20 — Wave 4 Deferred":

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | datasets/prompts/tblite_anchor.json with live calibration data | Plan 20-05 (deferred at user direction 2026-05-19) | STATE.md: "Plan 20-05 (anchor generation checkpoint) was SKIPPED at user request"; recovery command documented: `python -m evolution.benchmarks.build_tblite_calibration --runs 3 --benchmark-max-cost 50.0` |
| 2 | Replacement of placeholder task names in stratified_subset.json with real TBLite HF task names | Plan 20-05 Wave 4 (deferred) | Same as above; Wave 4 (build_tblite_calibration) overwrites task_filter[].name |

### Human Verification Required

See frontmatter `human_verification` section for the two items needing live execution:

1. **Live TBLite calibration run (Plan 20-05)** — Run `build_tblite_calibration` against the hermes-agent checkout with real Modal + OpenRouter credentials, then re-run `evolve_prompt_sections --benchmark=tblite` end-to-end to confirm the gating path actually executes the subprocess + Risk_Score evaluation (rather than fail-closing at the anchor-existence pre-check).

2. **Multi-section overlay regression test (CR-01)** — The fix is correct by inspection but lacks an N>=2-section regression test. Either add a unit test with two `_FakeSection` fixtures exercising different line_ranges, or accept it as covered by the live calibration run.

### Gaps Summary

No code-level gaps. The phase delivers the full benchmark-gate surface area per PMPT-V2-03 and ROADMAP success criteria #1, #2, #3. All 4 CRITICAL findings from the post-execution code review (CR-01..CR-04) were closed by follow-up commits, and 6 of 9 WARNINGs were also closed. The remaining 3 WARNINGs (WR-03 docstring clarity, WR-06 evolve() monolith, and INFO-level items) are quality-of-life concerns suitable for tracking-todo capture rather than gate-blockers.

The single deferred deliverable (live anchor calibration) is:
- Explicitly documented as a user-initiated deferral in STATE.md
- Correctly fail-closed at runtime (evolve_prompt_sections.py:1123-1129 raises click.ClickException with recovery command)
- Recoverable via a single CLI invocation (`python -m evolution.benchmarks.build_tblite_calibration --runs 3 --benchmark-max-cost 50.0`) when user supplies credentials + budget

The phase goal "use TBLite as optional hard regression gate after optimization" is **structurally achieved** — the gate is implemented, integrated, tested, and gated behind the missing anchor (correct fail-closed behavior). It is **not yet runtime-validated** end-to-end because Plan 05 was deferred.

---

_Verified: 2026-05-19T14:35:36Z_
_Verifier: Claude (gsd-verifier, Opus 4.7 1M)_
