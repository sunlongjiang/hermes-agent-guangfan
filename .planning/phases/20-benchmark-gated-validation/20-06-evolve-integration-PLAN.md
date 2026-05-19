---
phase: 20-benchmark-gated-validation
plan: 06
type: execute
wave: 5
revised_at: 2026-05-19
depends_on:
  - 20-03-benchmark-gate-PLAN.md
  - 20-05-anchor-generation-checkpoint-PLAN.md
files_modified:
  - evolution/prompts/evolve_prompt_sections.py
  - tests/prompts/test_evolve_prompt_sections_cli.py
  - .planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md
autonomous: true
requirements:
  - PMPT-V2-03
requirements_addressed:
  - PMPT-V2-03
tags:
  - phase-20
  - benchmark
  - cli
  - integration
must_haves:
  truths:
    - "evolve_prompt_sections.py imports TBLiteBenchmarkGate from evolution.benchmarks.benchmark_gate when --benchmark != 'none' (lazy import to honor Plan 01's __init__.py guard)"
    - "evolve_prompt_sections.py step 10.5 inserted between step 10 (Report results) and step 11 (Save results) — only fires when benchmark != 'none' (D-18)"
    - "evolve() function gains 6 new keyword parameters: benchmark='none', benchmark_tier=None, benchmark_cache=True, benchmark_max_cost=50.0, wait_mode='wait', async_full_verify=True"
    - "Click main() gains 6 new @click.option decorators: --benchmark (Choice none/tblite/tblite-full), --benchmark-tier (CSV), --benchmark-cache/--no-benchmark-cache, --benchmark-max-cost, --wait/--detach, --async-full-verify/--no-async-full-verify"
    - "evolve() establishes a REAL optimization CostTracker wrapping the GEPA/MIPROv2 compile section (W-2/W-3 revision: Phase 13's max_cost_usd field was declared but never instantiated as a tracker in evolve_prompt_sections — Plan 06 wires the missing tracker)"
    - "metrics.json on SUCCESS path gains: benchmark_decision (always present, default 'skipped'), benchmark_passed, benchmark_risk_score, benchmark_per_tier (when ran), total_cost_breakdown {optimization, benchmark} with optimization=real_tracker.spent_usd (NOT a fabricated locals().get fallback)"
    - "Gate reject path writes FAILED_<ts>/ with metrics.json + tblite_report.json + evolved_sections.json + diff.txt; the function returns BEFORE write-back to hermes-agent (Phase 18 D-GATE-04 mirror)"
    - "Gate accept path writes output/prompts/<ts>/tblite_report.json side-by-side with evolved_sections.json (D-04)"
    - "Cost budget exceeded raises CostBudgetExceeded -> ABORTED_<ts>/ path (mirror Phase 13)"
    - "No --no-benchmark / --skip-benchmark Click option exists (Phase 18 D-BYPASS-01 spirit — --benchmark=none IS the bypass)"
    - "--benchmark-tier filter selects tasks by item['tier'] field (W-7 schema) — NOT by per_tier_counts index slice"
    - "tests/prompts/test_evolve_prompt_sections_cli.py gains TestBenchmarkGate class with at least 6 new tests covering: skipped default / accept happy path / reject path / cache flag / no-bypass-flag regression / tier filter (W-7 tier-field) / detach not-implemented"
    - "Tests patch BOTH evolution.benchmarks.benchmark_gate.TBLiteBenchmarkGate AND evolution.prompts.evolve_prompt_sections.TBLiteBenchmarkGate (W-4 revision: lazy import binds at the consuming module's namespace AFTER the lazy import fires)"
    - ".planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md exists tracking the two deferred features (--detach background dispatch + --check-benchmark/--restore/--confirm-rollback subcommands)"
  artifacts:
    - path: evolution/prompts/evolve_prompt_sections.py
      provides: "Step 10.5 benchmark gate insertion + 6 new CLI flags + benchmark_* metrics block + tblite_report.json write + REAL optimization CostTracker wrapping GEPA compile (W-2/W-3)"
      contains: "benchmark_decision"
    - path: tests/prompts/test_evolve_prompt_sections_cli.py
      provides: "TestBenchmarkGate class with 6+ CliRunner integration tests; double-patch helper for lazy-import binding (W-4)"
      contains: "TestBenchmarkGate"
    - path: .planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md
      provides: "Tracking todo for the two deferred Phase 22+ features documented in Plan 06"
      contains: "deferred"
  key_links:
    - from: evolve_prompt_sections.py step 10.5
      to: evolution.benchmarks.benchmark_gate.TBLiteBenchmarkGate
      via: "gate = TBLiteBenchmarkGate(config, anchor, subset, ...); bench_results = gate.check_all(original_sections, evolved_sections, cache_dir=..., use_cache=benchmark_cache)"
      pattern: "TBLiteBenchmarkGate"
    - from: evolve_prompt_sections.py step 6 (optimization)
      to: evolution.core.cost_tracker.CostTracker
      via: "optimization_tracker = CostTracker(max_usd=config.max_cost_usd); with optimization_tracker: ... GEPA/MIPROv2 compile ... optimization_tracker_spent = optimization_tracker.spent_usd"
      pattern: "optimization_tracker"
    - from: evolve_prompt_sections.py step 11
      to: output/prompts/<ts>/metrics.json
      via: "metrics['benchmark_decision'] = ...; metrics['benchmark_risk_score'] = ...; metrics['benchmark_per_tier'] = ...; metrics['total_cost_breakdown'] = {'optimization': optimization_tracker_spent, 'benchmark': benchmark_tracker_spent}"
      pattern: "benchmark_decision"
    - from: evolve_prompt_sections.py step 11
      to: output/prompts/<ts>/tblite_report.json
      via: "(output_dir / 'tblite_report.json').write_text(json.dumps(report_without_constraint_result, indent=2))"
      pattern: "tblite_report\\.json"
---

<objective>
Wave 5 — Integrate the Phase 20 benchmark gate into `evolve_prompt_sections.py`, completing the Phase 20 success criteria from the ROADMAP:
1. `--benchmark` flag triggers TBLite evaluation before accepting evolved sections.
2. Configurable pass threshold (Plans 01 + 03 provide `--benchmark-max-cost` + `reject_threshold` via constructor).
3. Benchmark results saved to output metrics.

The integration is a 5-edit surgical pass mirroring Phase 18 Plan 18-04 (PATTERNS §File 5 §Insertion point 1-4) PLUS one new edit added in the 2026-05-19 revision:
- **Edit 0 (W-2/W-3 NEW)**: Wrap the GEPA/MIPROv2 compile section with a real `CostTracker(max_usd=config.max_cost_usd)`. Phase 13 declared `max_cost_usd` on `EvolutionConfig` but `evolve_prompt_sections.py` never instantiated a tracker for it (verified by grep at planning time: zero CostTracker occurrences in the file). Plan 06 closes that long-standing gap, exposing `optimization_tracker_spent` as a real local variable. Without this edit, Edit 3's `total_cost_breakdown.optimization` would be a fabricated `locals().get(...)` zero — the silent masking that prompted W-2/W-3.
- **Edit 1**: Add lazy import block scoped inside `evolve()` (when `benchmark != "none"`) so Plan 01's lazy-guard `__init__.py` continues to work when benchmark is OFF.
- **Edit 2**: Insert step 10.5 between line ~1021 (`console.print(result_table)`) and line ~1023 (`# ── 11. Save results ──`). Reject path writes `FAILED_<ts>/` + returns BEFORE step 11; accept path falls through.
- **Edit 3**: Augment `evolve()` signature with 6 new parameters and the success-path metrics.json block (`benchmark_decision` always-present; rest conditional on `benchmark_results`). Uses the REAL `optimization_tracker_spent` from Edit 0.
- **Edit 4**: Add 6 `@click.option` decorators + thread params through `main()` -> `evolve()`.

Plus 1 new test class and 1 new tracking todo file:
- **TestBenchmarkGate** in `tests/prompts/test_evolve_prompt_sections_cli.py` with 6+ tests double-patching `TBLiteBenchmarkGate` at both `evolution.benchmarks.benchmark_gate` AND `evolution.prompts.evolve_prompt_sections` namespaces (W-4 revision).
- **`.planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md`** documenting the two deferred features (W-1 revision: file is now in `<files>` and has a verify check + content template).

Two intentional simplifications (deferred to Phase 22+, documented in the new tracking todo):
1. **No `--check-benchmark <ts>` / `--restore <ts>` / `--confirm-rollback <ts>` subcommands.** CONTEXT §Discretion 7 lets the planner pick `--detach` orchestration shape. Plan 06 ships `--wait` only (synchronous); `--detach` returns 1 with a not-yet-implemented stderr message.
2. **No async-full-verify background dispatch.** `--async-full-verify` flag exists but is documented as "no-op in Plan 06; reserved for Phase 22". CONTEXT §D-07 is partially deferred.

**B-1 (Plan 05) interaction:** The runtime guard in step 10.5 that warns when `anchor.get("_meta", {}).get("tier") == "mock"` is RETAINED. After Plan 05's B-1 revision, no mock anchor should ever ship from this project — but Plan 06 may still encounter mock anchors from external sources (stale CI artifacts, archived branches, hand-edits). The warning surfaces such cases loudly at runtime; it is no longer endorsing mock-anchor authoring (Plan 05 forbids that), only flagging suspicious historical artifacts.

Output: 1 modified file (`evolve_prompt_sections.py` +~280 lines including the new tracker), 1 modified test file (+~400 lines for new test class), 1 new tracking todo (~25 lines).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/20-benchmark-gated-validation/20-CONTEXT.md
@.planning/phases/20-benchmark-gated-validation/20-PATTERNS.md
@evolution/prompts/evolve_prompt_sections.py
@evolution/benchmarks/benchmark_gate.py
@evolution/benchmarks/tblite_runner.py
@evolution/core/cost_tracker.py
@.planning/phases/18-personality-drift-detection/18-04-PLAN.md
@.planning/phases/18-personality-drift-detection/18-05-PLAN.md
@./CLAUDE.md

<interfaces>
<!-- Plan 03 contracts being consumed. -->
From evolution/benchmarks/benchmark_gate.py:
```python
TIER_WEIGHTS = {"easy": 1.0, "medium": 1.5, "hard": 2.0, "extreme": 4.0}
REJECT_THRESHOLD = 4.0

class TBLiteBenchmarkGate:
    def __init__(self, config, anchor, stratified_subset, *,
                 moving_avg_history=None, tier_weights=None,
                 reject_threshold=None, runs=None, confidence_z=1.96): ...
    def check_all(self, original_sections, evolved_sections, *,
                  cache_dir=None, use_cache=True, output_dir=None) -> list[dict]: ...
```

<!-- Plan 02 contracts. -->
From evolution/benchmarks/tblite_runner.py:
```python
TBLITE_RUNNER_VERSION = "1.0"
```

<!-- CostTracker reuse (Phase 13). -->
From evolution/core/cost_tracker.py:
```python
class CostTracker:
    def __init__(self, max_usd: float): ...
    def __enter__(self) -> "CostTracker": ...
    def __exit__(self, exc_type, exc, tb): ...
    @property
    def spent_usd(self) -> float: ...

class CostBudgetExceeded(Exception): ...
```

<!-- Existing evolve_prompt_sections.py anchors (lines verified at 2026-05-19). -->
File length: ~1220 lines.

**CRITICAL FINDING (W-2/W-3 root cause):** `grep -n "CostTracker\|cost_tracker" evolution/prompts/evolve_prompt_sections.py` returns ZERO matches. Phase 13 added `EvolutionConfig.max_cost_usd` and `evolution/core/cost_tracker.py`, but `evolve_prompt_sections.py` was never updated to instantiate a CostTracker around the GEPA compile section. The Phase 13 cost cap is therefore unenforced for prompt evolution today — it only exists for `evolve_skill.py` (verified by `grep -rn 'CostTracker' evolution/`). Plan 06 Edit 0 closes this gap.

Step 6 boundaries (existing code):
- Step 6a budget preview: lines 427-441 (`if effective_mode == "joint": joint_budget = ... else: joint_budget = 0`).
- Step 6b joint branch GEPA.compile call: lines 504-520.
- Step 6c round-robin branch GEPA → MIPROv2 fallback: lines 564-597.
- Step 6 completion timestamp at line 599 (`elapsed = time.time() - start_time`).

Step 10 ends at ~line 1021 (`console.print(result_table)`).
Step 11 starts at ~line 1023 (`# ── 11. Save results ──`).
`(output_dir / "metrics.json").write_text(...)` at line ~1087.
The drift_* `if drift_results:` block at line 1070-1086 (4-space function-body indent — sibling for benchmark_* block).
@click.command + 8 existing options at lines 1138-1200.
`def main(...)` at line 1201; `def evolve(...)` at line 188.

<!-- D-18 insertion topology. -->
The benchmark gate fires AFTER all in-loop work + drift gate (step 8c) + holdout eval (step 9) + report rendering (step 10), but BEFORE write-back (step 11). Reject -> FAILED_<ts>/ -> return. Accept -> step 11 + tblite_report.json side-by-side.

<!-- Wave 4 anchor (Plan 05 prerequisite). -->
datasets/prompts/tblite_anchor.json + datasets/prompts/tblite_stratified_subset.json are present at plan execution time (B-1 enforces live anchor only). Tests in Task 2 mock TBLiteBenchmarkGate entirely so these files do NOT need to exist for `pytest tests/prompts/`. The W-7 schema (subset.task_filter is list of {name, tier} objects) is the input shape to step 10.5's tier-filter logic.

<!-- Phase 18 step 8c → step 11 metrics block precedent (Plan 18-04 Edit-3). -->
The Phase 18 drift_results block at lines 1070-1086 is the indent-anchor for Plan 06's benchmark_* block. Place benchmark_* AT THE SAME 4-space indent (function-body), OUTSIDE the joint-only conditional.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Modify evolve_prompt_sections.py — 5-edit pass (CostTracker + signature + step 10.5 + metrics + CLI flags) + new tracking todo (W-1)</name>
  <files>
    - evolution/prompts/evolve_prompt_sections.py
    - .planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md
  </files>
  <read_first>
    - evolution/prompts/evolve_prompt_sections.py (entire file — confirm exact line numbers for anchors; especially lines 188-200 evolve() signature; lines 411-599 step 6 boundaries for the NEW CostTracker wrap (Edit 0); lines 1000-1100 step 10/11 boundary including the drift_* indent precedent at 1070-1086; lines 1136-1216 CLI section)
    - evolution/core/cost_tracker.py (entire — CostTracker context manager + CostBudgetExceeded + .spent_usd; understand the dspy.settings.track_usage gotcha at line 159)
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 5 (entire — 4 insertion points with exact anchor line numbers)
    - .planning/phases/20-benchmark-gated-validation/20-CONTEXT.md §D-18 (step 10.5 insertion topology) + §D-04 (tblite_report.json schema) + §D-16 (total_cost_breakdown) + §Specifics §Click CLI flags
    - .planning/phases/18-personality-drift-detection/18-04-PLAN.md Edit-3 (exact precedent for indent-level "OUTSIDE joint-only conditional")
    - ./CLAUDE.md (Rich console, no logging framework, snake_case, 4-space indent)
    - **PRE-EDIT GREP (mandatory before Edit 0):** Run `grep -n "CostTracker\|max_cost_usd\|cost_tracker\|\.spent_usd" evolution/prompts/evolve_prompt_sections.py` and confirm CostTracker is NOT yet wired (expected at planning time: zero matches). If grep returns matches, the file has been modified since planning — STOP and re-confirm Edit 0's placement.
  </read_first>
  <behavior>
    Task 2's TestBenchmarkGate class will exercise these required behaviors:
    1. test_benchmark_none_default_path_unchanged: `--benchmark=none` (default) → metrics.json has `benchmark_decision: "skipped"` AND no `benchmark_risk_score` key. Pre-Phase-20 behavior preserved.
    2. test_benchmark_tblite_accept_writes_report_and_metrics: `--benchmark=tblite` + mock gate returning `decision=accept` → success path writes BOTH `metrics.json` (with all benchmark_* fields) AND `tblite_report.json` side-by-side in `output/prompts/<ts>/`. `metrics["total_cost_breakdown"]["optimization"]` is a real float (>= 0; 0.0 acceptable in mocked LM tests but the FIELD must exist).
    3. test_benchmark_tblite_reject_writes_FAILED_dir: `--benchmark=tblite` + mock gate returning `decision=reject` → `output/prompts/FAILED_<ts>/` contains `metrics.json` (with `benchmark_passed: false`, `benchmark_risk_score`, `benchmark_per_tier`, `total_cost_breakdown`), `tblite_report.json`, `evolved_sections.json`, `diff.txt`. NO write-back to hermes-agent.
    4. test_benchmark_cache_flag_threads_through: `--no-benchmark-cache` → mock gate's `check_all` called with `use_cache=False`.
    5. test_no_skip_benchmark_flag: `--no-benchmark` and `--skip-benchmark` are rejected by Click with non-zero exit code (D-BYPASS-01 spirit regression guard).
    6. test_benchmark_tier_field_filters_subset (W-7): `--benchmark-tier easy,medium` → the stratified subset passed to the gate has only items where `item['tier'] in {easy, medium}` (per_tier_counts filtered consistently; NO index slicing).
    7. test_total_cost_breakdown_present: success path with `--benchmark=tblite` → `metrics['total_cost_breakdown']` is `{'optimization': float, 'benchmark': float}` (D-16) and BOTH values are floats (not None, not missing).
    8. test_detach_mode_not_yet_implemented_exits: `--detach` → exit 1 with stderr message about Phase 22.
    9. test_tests_must_fail_when_step_10_5_skipped (W-4 enforcement): When the test harness reaches step 10.5 but the wiring is broken, the assertion that `tblite_report.json` exists must FAIL the test (not pytest.skip). pytest.skip is reserved for environment issues (dspy not configured) — NEVER for "harness didn't reach step 10.5".
  </behavior>
  <action>
    Perform 5 surgical Edit operations on `evolution/prompts/evolve_prompt_sections.py` PLUS create 1 new file. After each Edit run `.venv/bin/python -c "import evolution.prompts.evolve_prompt_sections"` to confirm the module still imports.

    **Edit 0 — Wrap GEPA/MIPROv2 compile section with a real CostTracker (W-2/W-3 NEW).** This is the fix for the silent-zero spending bug.

    Sub-step 0.1: Add the import at the top of the module (with the other imports near line 22):

    ```python
    from evolution.core.cost_tracker import CostTracker, CostBudgetExceeded
    ```

    Sub-step 0.2: Locate `start_time = time.time()` at line ~471. Insert AFTER that line, BEFORE `if effective_mode == "joint":`, the tracker setup:

    ```python
    # W-2/W-3 (2026-05-19): Phase 13 declared max_cost_usd but
    # evolve_prompt_sections.py never instantiated a tracker. Plan 06 wires
    # the missing optimization-side CostTracker so total_cost_breakdown's
    # 'optimization' field reports the real LM spend across GEPA + MIPROv2
    # + A/B baseline runs. Without this wrap the field is permanently 0.0.
    optimization_tracker = CostTracker(max_usd=config.max_cost_usd)
    optimization_tracker_spent: float = 0.0
    try:
        with optimization_tracker:
    ```

    Sub-step 0.3: Locate the existing optimization body (lines 473-598 — the entire `if effective_mode == "joint": ... else: ... for active_sid in sections_to_optimize: ...` block PLUS the round-robin for-loop). INDENT the entire block 4 additional spaces so it sits INSIDE the `with optimization_tracker:` context. This is a multi-line shift; the executor should use the project's existing indent-shift tooling (or careful manual edit) to maintain valid Python.

    Sub-step 0.4: Locate line 599 (`elapsed = time.time() - start_time`). Insert BEFORE it (at the closing of the `with` block, dedent one level):

    ```python
        optimization_tracker_spent = optimization_tracker.spent_usd
    except CostBudgetExceeded as e:
        console.print(f"[red]Optimization cost budget exceeded: {e}[/red]")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        aborted_dir = Path("output") / "prompts" / f"ABORTED_{timestamp}"
        aborted_dir.mkdir(parents=True, exist_ok=True)
        (aborted_dir / "metrics.json").write_text(
            json.dumps({
                "timestamp": timestamp,
                "status": "ABORTED",
                "reason": "optimization_cost_budget_exceeded",
                "max_cost_usd": config.max_cost_usd,
                "spent_usd": getattr(e, "spent_usd", 0.0),
            }, indent=2)
        )
        console.print(f"  Saved aborted-cost state to {aborted_dir}/")
        return
    ```

    Verification: After Edit 0, `grep -nE 'optimization_tracker\b' evolution/prompts/evolve_prompt_sections.py` MUST return ≥4 matches (declaration + with-block + .spent_usd capture + later reference in Edit 3). `grep -c 'CostTracker' evolution/prompts/evolve_prompt_sections.py` MUST return ≥2 (import + instantiation). The Phase 13 unit tests (`pytest tests/prompts/test_evolve_prompt_sections_cli.py -k 'joint or round_robin'`) MUST still pass — the tracker is transparent to existing behavior when `max_cost_usd` is the default 20.0 and mocked LM usage stays under the cap.

    **Edit 1 — Extend `def evolve()` signature with 6 new keyword parameters.** Locate line ~188 `def evolve(...)`. Replace the signature (which currently ends with `session_source: Optional[Path] = None,`) with:

    ```python
    def evolve(
        section: Optional[str] = None,
        iterations: int = 10,
        eval_source: str = "synthetic",
        hermes_repo: Optional[str] = None,
        dry_run: bool = False,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
        mode: str = "joint",
        drift_thresholds_path: Path = Path("datasets/prompts/drift_thresholds.json"),
        session_source: Optional[Path] = None,
        # Phase 20 D-12 + D-15 + D-16
        benchmark: str = "none",
        benchmark_tier: Optional[str] = None,
        benchmark_cache: bool = True,
        benchmark_max_cost: float = 50.0,
        wait_mode: str = "wait",
        async_full_verify: bool = True,
    ):
    ```

    Keep the existing docstring; if it ends with a phrase like `..."""`, leave it. Do NOT delete the body — only the def signature lines change.

    **Edit 2 — Insert step 10.5 between line 1021 (`console.print(result_table)`) and line 1023 (`# ── 11. Save results ──`).** This is the largest insertion (~190 lines). The block must be at **4-space function-body indent**, OUTSIDE any conditional, so it always runs. Locate the existing `console.print(result_table)` at line ~1021 and insert AFTER it + a blank line:

    ```python

        # ── 10.5. Benchmark gate (Phase 20 D-18) — opt-in, OUT OF GEPA loop ─
        # Decision lattice:
        #   benchmark == "none"   -> skip (default; pre-Phase-20 behavior).
        #   benchmark == "tblite" -> stratified 30-task subset, 3-run avg.
        #   benchmark == "tblite-full" -> CONTEXT D-06 — NOT YET IMPLEMENTED
        #       in Plan 06 (full 100-task run is reserved for Phase 22
        #       async-full-verify orchestration). Surfaced as
        #       click.ClickException.
        # wait_mode == "detach"  -> NOT YET IMPLEMENTED. exits non-zero.
        benchmark_results: list = []
        benchmark_decision = "skipped"
        benchmark_risk_score: Optional[float] = None
        benchmark_per_tier: dict = {}
        benchmark_passed: Optional[bool] = None
        benchmark_tracker_spent = 0.0

        if benchmark != "none":
            if benchmark == "tblite-full":
                raise click.ClickException(
                    "--benchmark=tblite-full is reserved for Phase 22 "
                    "(async full verify). Use --benchmark=tblite for the "
                    "stratified 30-task subset."
                )
            if wait_mode == "detach":
                click.echo(
                    "--detach is reserved for Phase 22 "
                    "(see .planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md). "
                    "Plan 06 ships synchronous --wait only.",
                    err=True,
                )
                sys.exit(1)

            console.print(
                f"\n[bold]Running TBLite benchmark gate (mode={benchmark})[/bold]"
            )
            # D-Discretion-1 lazy import: never import benchmark_gate at module
            # load time. Plan 01's evolution/benchmarks/__init__.py is a
            # lazy-guard so callers running with --benchmark=none on a host
            # without hermes-agent / huggingface_hub still work.
            #
            # W-4 (2026-05-19): tests must double-patch this lazy import. After
            # the next line executes, `TBLiteBenchmarkGate` is bound as a NAME
            # in the evolve_prompt_sections module namespace AS WELL AS being
            # available at evolution.benchmarks.benchmark_gate.TBLiteBenchmarkGate.
            # Patching only the source site does NOT intercept this binding.
            from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate

            # Load anchor + stratified subset (Wave 4 artifacts).
            anchor_path = Path("datasets/prompts/tblite_anchor.json")
            subset_path = Path("datasets/prompts/tblite_stratified_subset.json")
            if not anchor_path.exists():
                raise click.ClickException(
                    f"{anchor_path} not found. Run "
                    f"`python -m evolution.benchmarks.build_tblite_calibration` first "
                    f"(Phase 20 D-13 prerequisite — Plan 05 produces this; "
                    f"B-1 forbids mock fallback)."
                )
            if not subset_path.exists():
                raise click.ClickException(
                    f"{subset_path} not found. Plan 01 should have placed "
                    f"a placeholder; check phase 20 wave 1 completion."
                )
            anchor = json.loads(anchor_path.read_text())
            subset = json.loads(subset_path.read_text())

            # Mock-tier audit: warn loudly so accept decisions are recognized
            # as non-authoritative. Per Plan 05's B-1 revision (2026-05-19)
            # no mock anchor SHOULD ever ship — this warning is a runtime
            # guard against historical / external archive artifacts that
            # bypass the planning flow.
            if anchor.get("_meta", {}).get("tier") == "mock":
                console.print(
                    "[bold yellow]⚠ Anchor is _meta.tier='mock' — gate "
                    "accept/reject decisions are NOT trustworthy. Plan 05 "
                    "(B-1) forbids mock-anchor authoring; this file appears "
                    "to be a stale or external artifact. Re-run "
                    "build_tblite_calibration before relying on the "
                    "gate.[/bold yellow]"
                )

            # D-05 + W-7 (2026-05-19): --benchmark-tier CSV subset filter.
            # Reads item['tier'] directly (W-7 schema: task_filter is list of
            # {name, tier} dicts). NO index slicing — the previous
            # offset-based implementation depended on subset being sorted
            # easy→medium→hard→extreme, which is no longer a contract.
            if benchmark_tier:
                selected_tiers = set(
                    t.strip().lower() for t in benchmark_tier.split(",") if t.strip()
                )
                bad = selected_tiers - {"easy", "medium", "hard", "extreme"}
                if bad:
                    raise click.ClickException(
                        f"--benchmark-tier contains unknown tiers: {sorted(bad)} "
                        f"(expected subset of easy,medium,hard,extreme)"
                    )
                subset = dict(subset)
                full_filter = subset.get("task_filter", [])
                # Tolerate both W-7 object form AND legacy flat-string form
                # during transition: if items are strings, fall back to the
                # per_tier_counts index slice as last resort with a warning.
                if full_filter and isinstance(full_filter[0], dict):
                    new_filter = [
                        item for item in full_filter
                        if str(item.get("tier", "")).strip().lower() in selected_tiers
                    ]
                    new_counts = {}
                    for item in new_filter:
                        t = str(item["tier"]).strip().lower()
                        new_counts[t] = new_counts.get(t, 0) + 1
                else:
                    # Legacy schema — log + best-effort index slice.
                    console.print(
                        "[yellow]Subset uses legacy flat-string task_filter "
                        "(pre-W-7 schema). --benchmark-tier filter will fall "
                        "back to per_tier_counts index slicing.[/yellow]"
                    )
                    full_counts = subset.get("per_tier_counts", {})
                    new_filter = []
                    offset = 0
                    new_counts = {}
                    for tier_name in ("easy", "medium", "hard", "extreme"):
                        n = full_counts.get(tier_name, 0)
                        if tier_name in selected_tiers:
                            new_filter.extend(full_filter[offset:offset + n])
                            new_counts[tier_name] = n
                        offset += n
                subset["task_filter"] = new_filter
                subset["per_tier_counts"] = new_counts
                if not new_filter:
                    raise click.ClickException(
                        f"--benchmark-tier produced an empty subset. "
                        f"Pick at least one of: easy,medium,hard,extreme."
                    )

            # Load moving_avg_history if present (D-01 first-run-falls-back-to-anchor).
            history_path = Path("output/prompts/tblite_history.json")
            moving_avg_history: list = []
            if history_path.exists():
                try:
                    moving_avg_history = json.loads(history_path.read_text())
                    if not isinstance(moving_avg_history, list):
                        moving_avg_history = []
                except json.JSONDecodeError:
                    console.print(
                        f"[yellow]{history_path} malformed; using empty history "
                        f"(moving_avg falls back to anchor per D-01).[/yellow]"
                    )
                    moving_avg_history = []

            gate = TBLiteBenchmarkGate(
                config,
                anchor=anchor,
                stratified_subset=subset,
                moving_avg_history=moving_avg_history,
            )

            cache_dir = (
                Path.home() / ".cache" / "hermes-evolution" / "tblite"
            )
            cache_dir.mkdir(parents=True, exist_ok=True)

            # D-16: dual-track budget. The benchmark tracker is independent
            # from the optimization tracker (Edit 0 wires that one).
            benchmark_tracker = CostTracker(max_usd=benchmark_max_cost)
            try:
                with benchmark_tracker:
                    benchmark_results = gate.check_all(
                        original_sections,
                        evolved_sections,
                        cache_dir=cache_dir,
                        use_cache=benchmark_cache,
                    )
                benchmark_tracker_spent = benchmark_tracker.spent_usd
            except CostBudgetExceeded as e:
                console.print(f"[red]Benchmark cost budget exceeded: {e}[/red]")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                aborted_dir = Path("output") / "prompts" / f"ABORTED_{timestamp}"
                aborted_dir.mkdir(parents=True, exist_ok=True)
                (aborted_dir / "metrics.json").write_text(
                    json.dumps({
                        "timestamp": timestamp,
                        "status": "ABORTED",
                        "benchmark_decision": "aborted_cost",
                        "benchmark_max_cost_usd": benchmark_max_cost,
                        "benchmark_spent_usd": getattr(e, "spent_usd", 0.0),
                    }, indent=2)
                )
                console.print(f"  Saved aborted-cost state to {aborted_dir}/")
                return

            # Single-element list per TBLiteBenchmarkGate.check_all contract.
            bench = benchmark_results[0]
            benchmark_decision = bench["decision"]
            benchmark_risk_score = bench["risk_score"]
            benchmark_per_tier = bench["per_tier"]
            benchmark_passed = (benchmark_decision == "accept")

            # D-OUT-01-style Rich Table (mirror Phase 18 drift_table at line 722).
            bench_table = Table(
                title=(
                    f"TBLite Benchmark Gate "
                    f"(Risk_Score={benchmark_risk_score:.2f} / "
                    f"reject_threshold={bench['reject_threshold']:.2f})"
                )
            )
            bench_table.add_column("Tier", style="bold")
            bench_table.add_column("Mean", justify="right")
            bench_table.add_column("Stdev", justify="right")
            bench_table.add_column("Threshold", justify="right")
            bench_table.add_column("Anchor", justify="right")
            bench_table.add_column("MovingAvg", justify="right")
            bench_table.add_column("Breach", justify="center")
            for tier in ("easy", "medium", "hard", "extreme"):
                v = benchmark_per_tier.get(tier, {})
                if not v:
                    continue
                breach_icon = (
                    "[red]x[/red]" if v.get("breach")
                    else "[green]ok[/green]"
                )
                bench_table.add_row(
                    tier,
                    f"{v.get('mean', 0):.3f}",
                    f"{v.get('stdev', 0):.3f}",
                    f"{v.get('threshold', 0):.3f}",
                    f"{v.get('anchor', 0):.3f}",
                    f"{v.get('moving_avg', 0):.3f}",
                    breach_icon,
                )
            console.print(bench_table)

            # Hard reject -> FAILED_<ts>/ + return BEFORE write-back (D-18 + D-GATE-04 mirror).
            if benchmark_decision == "reject":
                console.print(
                    f"[red]Benchmark gate REJECTED "
                    f"(Risk_Score={benchmark_risk_score:.2f} >= "
                    f"{bench['reject_threshold']:.2f}) — "
                    f"evolved prompts NOT deployed[/red]"
                )
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_dir = (
                    Path("output") / "prompts" / f"FAILED_{timestamp}"
                )
                output_dir.mkdir(parents=True, exist_ok=True)
                failed_metrics = {
                    "timestamp": timestamp,
                    "status": "FAILED",
                    "constraints_passed": True,  # in-loop constraints passed; benchmark gate rejected
                    "benchmark_decision": "reject",
                    "benchmark_passed": False,
                    "benchmark_risk_score": benchmark_risk_score,
                    "benchmark_per_tier": benchmark_per_tier,
                    "benchmark_reason": (
                        f"Risk_Score {benchmark_risk_score:.2f} >= "
                        f"{bench['reject_threshold']:.2f}"
                    ),
                    # W-2/W-3: optimization_tracker_spent is now a real local
                    # variable established by Edit 0. NO locals().get(...)
                    # fallback — if Edit 0 was skipped, this AttributeError
                    # fails loudly (good) rather than silently reporting 0.0.
                    "total_cost_breakdown": {
                        "optimization": float(optimization_tracker_spent),
                        "benchmark": float(benchmark_tracker_spent),
                    },
                }
                (output_dir / "metrics.json").write_text(
                    json.dumps(failed_metrics, indent=2)
                )
                # tblite_report.json (D-04 schema sans constraint_result).
                serializable_report = {
                    k: v for k, v in bench.items()
                    if k != "constraint_result"
                }
                (output_dir / "tblite_report.json").write_text(
                    json.dumps(serializable_report, indent=2, sort_keys=True)
                )
                (output_dir / "evolved_sections.json").write_text(
                    json.dumps(
                        [
                            {"section_id": s.section_id, "text": s.text}
                            for s in evolved_sections
                        ],
                        indent=2,
                    )
                )
                (output_dir / "diff.txt").write_text(
                    _generate_diff(original_sections, evolved_sections)
                )
                console.print(f"  Saved failed results to {output_dir}/")
                return

            # If we reach here, gate accepted. Step 11 continues normally.
            console.print(
                f"[green]Benchmark gate ACCEPTED "
                f"(Risk_Score={benchmark_risk_score:.2f} < "
                f"{bench['reject_threshold']:.2f})[/green]"
            )
    ```

    **Edit 3 — Augment step 11 metrics.json with benchmark_* + total_cost_breakdown + write tblite_report.json.** Locate the existing drift block at lines ~1070-1086 (the `if drift_results:` at 4-space indent, ending with `metrics["drift_max_dim"] = max_entry[1]`). INSERT after the closing of that block (still at 4-space function-body indent, NOT inside the drift conditional), BEFORE the `(output_dir / "metrics.json").write_text(...)` line at line ~1087:

    ```python
        # Phase 20 D-04: benchmark_* fields. ALWAYS write benchmark_decision
        # (default 'skipped') so Phase 16 dashboard can filter by status.
        metrics["benchmark_decision"] = benchmark_decision
        if benchmark_results:
            metrics["benchmark_passed"] = benchmark_passed
            metrics["benchmark_risk_score"] = benchmark_risk_score
            metrics["benchmark_per_tier"] = benchmark_per_tier
            metrics["benchmark_tier_weights"] = benchmark_results[0]["tier_weights"]
            metrics["benchmark_reject_threshold"] = (
                benchmark_results[0]["reject_threshold"]
            )

        # Phase 20 D-16: dual-track cost breakdown.
        # W-2/W-3 (2026-05-19): optimization_tracker_spent is established by
        # Edit 0's CostTracker(max_usd=config.max_cost_usd) wrap of the GEPA
        # compile section. NO locals().get(...) fallback — if Edit 0 was not
        # applied this line raises NameError loudly. Previous draft used
        # `locals().get("optimization_tracker_spent", 0.0)` which silently
        # masked the missing tracker as 0.0 (the W-2/W-3 bug).
        metrics["total_cost_breakdown"] = {
            "optimization": float(optimization_tracker_spent),
            "benchmark": float(benchmark_tracker_spent),
        }
    ```

    AND, AFTER the existing `(output_dir / "diff.txt").write_text(diff_text)` line (~line 1093), AFTER the existing drift_report.txt write block (~lines 1096-1099), INSERT (still at 4-space function-body indent):

    ```python
        # Phase 20 D-04: tblite_report.json side-by-side with evolved_sections.json
        # so Phase 16 dashboard can ingest per-tier breakdown without re-reading
        # metrics.json.
        if benchmark_results:
            serializable_report = {
                k: v for k, v in benchmark_results[0].items()
                if k != "constraint_result"
            }
            (output_dir / "tblite_report.json").write_text(
                json.dumps(serializable_report, indent=2, sort_keys=True)
            )
    ```

    **Edit 4 — Add 6 Click options + thread through main() → evolve().** Locate the existing `@click.option` block ending with `--session-source` (~line 1188-1200). INSERT after `--session-source` decorator + BEFORE `def main(...)`:

    ```python
    @click.option(
        "--benchmark",
        type=click.Choice(["none", "tblite", "tblite-full"]),
        default="none",
        help=(
            "Phase 20 D-18. Run TBLite benchmark gate after step 10 (out "
            "of GEPA loop, PITFALL #7). 'none' (default) = pre-Phase-20 "
            "behavior. 'tblite' = stratified 30-task subset. "
            "'tblite-full' = reserved for Phase 22 (errors out)."
        ),
    )
    @click.option(
        "--benchmark-tier",
        default=None,
        help=(
            "CSV of tiers to include (subset of easy,medium,hard,extreme). "
            "Default = all four. Phase 20 D-05 + W-7 (filters by item['tier'])."
        ),
    )
    @click.option(
        "--benchmark-cache/--no-benchmark-cache",
        default=True,
        help=(
            "Content-addressed cache at ~/.cache/hermes-evolution/tblite/ "
            "(Phase 20 D-15). Disable for a single forced re-run."
        ),
    )
    @click.option(
        "--benchmark-max-cost",
        default=50.0,
        type=float,
        help=(
            "USD cap for the benchmark cost tracker (Phase 20 D-16 dual-track). "
            "Distinct from --max-cost-usd which governs GEPA + LLM judge."
        ),
    )
    @click.option(
        "--wait/--detach",
        default=True,
        help=(
            "Phase 20 D-12. --wait blocks until TBLite subprocess exits then "
            "decides write-back (DEFAULT). --detach is reserved for Phase 22 "
            "(currently exits non-zero)."
        ),
    )
    @click.option(
        "--async-full-verify/--no-async-full-verify",
        default=True,
        help=(
            "Phase 20 D-07. NO-OP in Plan 06 — accepted for forward "
            "compatibility but the background full-verify dispatch is "
            "reserved for Phase 22."
        ),
    )
    ```

    Update the `def main(...)` signature (~line 1201) — add the 6 new positional params (Click derives them from the option names):

    ```python
    def main(section, iterations, eval_source, hermes_repo, dry_run, model,
             api_base, mode, drift_thresholds_path, session_source,
             benchmark, benchmark_tier, benchmark_cache, benchmark_max_cost,
             wait, async_full_verify):
        """Evolve hermes-agent prompt sections using DSPy + GEPA optimization."""
        evolve(
            section=section,
            iterations=iterations,
            eval_source=eval_source,
            hermes_repo=hermes_repo,
            dry_run=dry_run,
            model=model,
            api_base=api_base,
            mode=mode,
            drift_thresholds_path=drift_thresholds_path,
            session_source=session_source,
            benchmark=benchmark,
            benchmark_tier=benchmark_tier,
            benchmark_cache=benchmark_cache,
            benchmark_max_cost=benchmark_max_cost,
            wait_mode="wait" if wait else "detach",
            async_full_verify=async_full_verify,
        )
    ```

    **Edit 5 (W-1) — Create the tracking todo file.** Create `.planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md` with the Write tool. Exact content:

    ```markdown
    ---
    opened: 2026-05-19
    severity: MEDIUM
    phase_match_hint: 22
    related_files:
      - evolution/prompts/evolve_prompt_sections.py
      - evolution/benchmarks/benchmark_gate.py
      - evolution/benchmarks/tblite_runner.py
    ---

    # Phase 20 deferred: `--detach` + `--check-benchmark / --restore / --confirm-rollback` subcommands

    Phase 20 / Plan 06 (2026-05-19) shipped the synchronous `--wait` path of
    the TBLite benchmark gate but DEFERRED two pieces to a later phase (likely
    Phase 22 — Continuous Evolution Loop):

    1. **`--detach` background dispatch.** Today `--detach` exits 1 with a
       Phase-22 message. The real implementation needs a `subprocess.Popen`
       detached run + `output/prompts/<ts>/.benchmark_running.pid` lock file
       + Rich Live progress polling. CONTEXT §D-12 + §Discretion 7 describe
       the target shape.

    2. **`--check-benchmark <ts>` / `--restore <ts>` / `--confirm-rollback <ts>` subcommands.**
       Companion to `--detach`. Lets the user query a backgrounded run's
       gate decision and roll back if `tblite_full_report.json` (Phase 22
       async full verify) finds regressions. CONTEXT §D-07 + §D-08 + §Specifics
       define the lock file + history schema.

    **Why deferred:** These features cross a process boundary and need
    Phase-21-era infrastructure (a daemon mode for the evolution CLI, or a
    cron-like scheduler). Plan 06's scope was the synchronous integration
    only; adding the async story would have pushed Plan 06 past its 2-3-task
    budget.

    **Acceptance:** When Phase 22 picks this up, delete this file in the same
    commit that introduces the `--detach` background-process path. Verify by
    running `python -m evolution.prompts.evolve_prompt_sections --benchmark=tblite --detach`
    and confirming it returns a `benchmark_run_id` rather than exiting 1.
    ```

    After all 5 edits + 1 new file run `.venv/bin/python -c "from evolution.prompts.evolve_prompt_sections import main, evolve; import inspect; sig = inspect.signature(evolve); assert 'benchmark' in sig.parameters; assert 'benchmark_max_cost' in sig.parameters; assert 'wait_mode' in sig.parameters; print('OK signatures')"` and `.venv/bin/python -m evolution.prompts.evolve_prompt_sections --help | head -50` to confirm Click renders the new flags.

    Implements: PATTERNS §File 5 §Insertion points 1-4; CONTEXT §D-04 + §D-05 + §D-15 + §D-16 + §D-18; Phase 18 Plan 18-04 Edit-3 indent discipline. W-1, W-2, W-3, W-4, W-7 all addressed in 2026-05-19 revision.
  </action>
  <verify>
    <automated>.venv/bin/python -c "
from evolution.prompts.evolve_prompt_sections import main, evolve
import inspect
sig = inspect.signature(evolve)
for p in ('benchmark', 'benchmark_tier', 'benchmark_cache', 'benchmark_max_cost', 'wait_mode', 'async_full_verify'):
    assert p in sig.parameters, f'evolve() missing {p}'
main_sig = inspect.signature(main.callback)
for p in ('benchmark', 'benchmark_tier', 'benchmark_cache', 'benchmark_max_cost', 'wait', 'async_full_verify'):
    assert p in main_sig.parameters, f'main() missing {p}'
print('OK both signatures')
" && .venv/bin/python -m evolution.prompts.evolve_prompt_sections --help 2>&1 | grep -E '\-\-(benchmark|benchmark-tier|benchmark-cache|benchmark-max-cost|wait|async-full-verify)' | wc -l | awk '{ if ($1 < 6) { print "FAIL: only " $1 " new flags in --help"; exit 1 } else { print "OK: " $1 " flags shown" } }' && .venv/bin/python -m evolution.prompts.evolve_prompt_sections --help 2>&1 | grep -E '\-\-no-benchmark|\-\-skip-benchmark' | wc -l | awk '{ if ($1 != 0) { print "FAIL: D-BYPASS-01-style bypass flag present"; exit 1 } else { print "OK: no bypass flag" } }' && grep -nE '@click\.option\(\s*"--(no|skip)-benchmark"' evolution/prompts/evolve_prompt_sections.py | wc -l | awk '{ if ($1 != 0) { print "FAIL: @click.option decorator for --no-benchmark / --skip-benchmark exists (Phase 18 D-BYPASS-01 spirit violation)"; exit 1 } else { print "OK D-BYPASS-01-style guard" } }' && grep -c 'benchmark_decision' evolution/prompts/evolve_prompt_sections.py | awk '{ if ($1 < 3) { print "FAIL: benchmark_decision appears only " $1 " times — need (step 10.5 init) + (reject path) + (success metrics)"; exit 1 } else { print "OK: benchmark_decision threaded through" } }' && grep -c 'tblite_report\.json' evolution/prompts/evolve_prompt_sections.py | awk '{ if ($1 < 2) { print "FAIL: tblite_report.json must be written on both reject + accept paths"; exit 1 } else { print "OK: " $1 " tblite_report.json writes" } }' && grep -c 'total_cost_breakdown' evolution/prompts/evolve_prompt_sections.py | awk '{ if ($1 < 2) { print "FAIL: D-16 total_cost_breakdown missing — need reject path + success path"; exit 1 } else { print "OK D-16" } }' && grep -c 'TBLiteBenchmarkGate' evolution/prompts/evolve_prompt_sections.py | awk '{ if ($1 < 1) { print "FAIL: TBLiteBenchmarkGate import missing"; exit 1 } else { print "OK" } }' && grep -nE '^from evolution\.benchmarks\.benchmark_gate' evolution/prompts/evolve_prompt_sections.py | awk '{ print "FAIL: TBLiteBenchmarkGate must be LAZY-imported inside evolve(), NOT at module top — found top-level import at line " $1; exit 1 }' && echo "OK lazy import preserved" && grep -c 'CostTracker' evolution/prompts/evolve_prompt_sections.py | awk '{ if ($1 < 2) { print "FAIL: Edit 0 CostTracker import + instantiation missing (W-2/W-3)"; exit 1 } else { print "OK: CostTracker wired (" $1 " refs)" } }' && grep -nE 'optimization_tracker\b' evolution/prompts/evolve_prompt_sections.py | wc -l | awk '{ if ($1 < 4) { print "FAIL: optimization_tracker must appear >=4 times (declaration + with-block + .spent_usd capture + metrics reference); found " $1; exit 1 } else { print "OK: optimization_tracker threaded through (" $1 " refs)" } }' && grep -nE 'locals\(\).get\("optimization_tracker_spent"' evolution/prompts/evolve_prompt_sections.py | wc -l | awk '{ if ($1 != 0) { print "FAIL: locals().get(optimization_tracker_spent) fallback still present — W-2/W-3 regression"; exit 1 } else { print "OK: no silent-zero fallback" } }' && test -f .planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md || (echo "FAIL: W-1 tracking todo missing"; exit 1) && wc -l .planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md | awk '{ if ($1 < 15) { print "FAIL: tracking todo too short (need >=15 lines of meaningful content)"; exit 1 } else { print "OK: tracking todo " $1 " lines" } }' && .venv/bin/pytest tests/prompts/ -q --tb=line 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `evolve()` signature has 6 new keyword parameters: benchmark, benchmark_tier, benchmark_cache, benchmark_max_cost, wait_mode, async_full_verify.
    - `main()` signature has 6 new positional parameters (Click converts --wait/--detach toggle to bare `wait`).
    - `python -m evolution.prompts.evolve_prompt_sections --help` shows all 6 new flags.
    - `--help` does NOT show `--no-benchmark` or `--skip-benchmark` (Phase 18 D-BYPASS-01 spirit).
    - `grep -nE '@click\.option\(\s*"--(no|skip)-benchmark"' evolution/prompts/evolve_prompt_sections.py` returns no matches.
    - `grep -c 'benchmark_decision' evolution/prompts/evolve_prompt_sections.py` >= 3 (step 10.5 init + reject metrics + success metrics).
    - `grep -c 'tblite_report\.json' evolution/prompts/evolve_prompt_sections.py` >= 2 (reject path + success path).
    - `grep -c 'total_cost_breakdown' evolution/prompts/evolve_prompt_sections.py` >= 2 (reject metrics + success metrics).
    - `grep -c 'TBLiteBenchmarkGate' evolution/prompts/evolve_prompt_sections.py` >= 1.
    - `from evolution.benchmarks.benchmark_gate import` appears INSIDE evolve(), NOT at module top-level (lazy import per Plan 01 Discretion-1).
    - **(W-2/W-3)** `grep -c 'CostTracker' evolution/prompts/evolve_prompt_sections.py` >= 2 (import + at least one instantiation; Edit 0 instantiates the optimization tracker, step 10.5 instantiates the benchmark tracker).
    - **(W-2/W-3)** `grep -nE 'optimization_tracker\b' evolution/prompts/evolve_prompt_sections.py` count >= 4 (declaration + with-block + spent_usd capture + metrics reference).
    - **(W-2/W-3)** `grep -nE 'locals\(\).get\("optimization_tracker_spent"' evolution/prompts/evolve_prompt_sections.py` returns ZERO matches — the silent-zero fallback must be eliminated.
    - **(W-1)** `.planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md` exists with >= 15 lines.
    - `pytest tests/prompts/` still passes existing tests (no regression).
  </acceptance_criteria>
  <done>
    - 5 surgical edits + 1 new file applied
    - 6 new Click flags exposed
    - No bypass flag (--no-benchmark / --skip-benchmark) exists
    - Step 10.5 sits between step 10 and step 11 with full reject/accept branching
    - metrics.json gains benchmark_* + total_cost_breakdown fields with REAL optimization spend (W-2/W-3)
    - tblite_report.json written on both accept (success path) and reject (FAILED path)
    - Lazy import of benchmark_gate honors Plan 01's __init__.py
    - --benchmark-tier filters by item['tier'] (W-7) with legacy-fallback warning
    - W-1 tracking todo created with meaningful content
    - Existing pytest tests/prompts/ baseline unchanged
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add TestBenchmarkGate class to tests/prompts/test_evolve_prompt_sections_cli.py with double-patch (W-4) + 6+ CliRunner integration tests</name>
  <files>tests/prompts/test_evolve_prompt_sections_cli.py</files>
  <read_first>
    - tests/prompts/test_evolve_prompt_sections_cli.py (entire file — see existing TestABBaseline + TestJointPipeline + TestDriftGate classes; use _ab_patched_run / _drift_patched_run style helpers)
    - .planning/phases/18-personality-drift-detection/18-05-PLAN.md (entire — Phase 18 TestDriftGate is the direct analog; Plan 06 mirrors the multi-patch topology)
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 5 §Insertion point 1 (step 10.5 reject path) + §Insertion point 2 (success metrics block)
    - evolution/benchmarks/benchmark_gate.py (Plan 03 — confirm check_all return shape)
    - evolution/prompts/evolve_prompt_sections.py (just-modified — confirm lazy import site of TBLiteBenchmarkGate for W-4 double-patch target identification)
  </read_first>
  <behavior>
    Test class TestBenchmarkGate, located at the END of tests/prompts/test_evolve_prompt_sections_cli.py.

    All tests use CliRunner + a multi-patch topology that:
      - Stubs `datasets/prompts/tblite_anchor.json` + `datasets/prompts/tblite_stratified_subset.json` under tmp_path (subset uses W-7 `{name, tier}` object schema)
      - **W-4 double-patch:** Patches `TBLiteBenchmarkGate` at BOTH `evolution.benchmarks.benchmark_gate.TBLiteBenchmarkGate` (source) AND `evolution.prompts.evolve_prompt_sections.TBLiteBenchmarkGate` (binding established by the lazy `from ... import ...` inside evolve()). Patching only the source site does NOT intercept the binding once evolve() executes its lazy import.
      - Patches Phase 18 DriftDetector + PromptModule + dspy LM/configure to no-op (so the test focuses on the gate, not the rest of the pipeline)

    Required tests (>= 6 PLUS the W-4 enforcement guard):
    1. test_benchmark_none_default_path_unchanged
    2. test_benchmark_tblite_accept_writes_report_and_metrics
    3. test_benchmark_tblite_reject_writes_FAILED_dir
    4. test_benchmark_cache_flag_threads_through
    5. test_no_skip_benchmark_flag (Click rejects --no-benchmark and --skip-benchmark)
    6. test_total_cost_breakdown_present
    7. test_benchmark_tier_field_filters_subset (W-7: --benchmark-tier filter selects by item['tier'] field, not by index slice)
    8. test_detach_mode_not_yet_implemented_exits
    9. test_step_10_5_wiring_must_not_be_silent_skip (W-4 enforcement: when the harness reaches the gate, missing tblite_report.json FAILS the test instead of pytest.skip)
  </behavior>
  <action>
    APPEND a new `TestBenchmarkGate` class to the END of `tests/prompts/test_evolve_prompt_sections_cli.py`. Skeleton (executor expands fully):

    ```python
    # ── Phase 20 / Plan 06: TestBenchmarkGate ──────────────────────────────


    def _benchmark_patched_run(
        runner,
        cli_args: list[str],
        *,
        tmp_path: "Path",
        gate_decision: str = "accept",
        gate_risk_score: float = 1.5,
        gate_per_tier: dict | None = None,
        anchor_overrides: dict | None = None,
        subset_overrides: dict | None = None,
        check_all_recorder: list | None = None,
        gate_constructor_recorder: list | None = None,
    ):
        """Run evolve_prompt_sections.main in a sandbox with all heavy deps mocked.

        W-4 (2026-05-19): MUST double-patch TBLiteBenchmarkGate:
          (a) evolution.benchmarks.benchmark_gate.TBLiteBenchmarkGate (source)
          (b) evolution.prompts.evolve_prompt_sections.TBLiteBenchmarkGate
              (the local binding established by the lazy `from ... import ...`
              inside evolve(). Without this patch the test silently runs the
              REAL gate and either crashes or — worse — appears to "pass" via
              pytest.skip.)

        Returns (CliRunner result, output_dir Path or None).
        """
        import json
        from pathlib import Path
        from unittest.mock import patch, MagicMock

        from evolution.prompts.evolve_prompt_sections import main as cli_main

        gate_per_tier = gate_per_tier or {
            "easy":    {"mean": 0.85, "stdev": 0.01, "threshold": 0.83,
                        "anchor": 0.85, "moving_avg": 0.85, "breach": False,
                        "scores": [0.84, 0.86, 0.85]},
            "medium":  {"mean": 0.70, "stdev": 0.01, "threshold": 0.68,
                        "anchor": 0.70, "moving_avg": 0.70, "breach": False,
                        "scores": [0.69, 0.71, 0.70]},
            "hard":    {"mean": 0.50, "stdev": 0.01, "threshold": 0.48,
                        "anchor": 0.50, "moving_avg": 0.50, "breach": False,
                        "scores": [0.49, 0.51, 0.50]},
            "extreme": {"mean": 0.30, "stdev": 0.01, "threshold": 0.28,
                        "anchor": 0.30, "moving_avg": 0.30, "breach":
                            (gate_decision == "reject")},
        }

        # Stub anchor + subset under tmp_path/datasets/prompts/ in W-7 schema.
        datasets_dir = tmp_path / "datasets" / "prompts"
        datasets_dir.mkdir(parents=True, exist_ok=True)
        anchor = {
            "anchor_per_tier": {
                t: {"mean": v["anchor"], "stdev": 0.02, "n": 3,
                    "scores": [v["anchor"]] * 3}
                for t, v in gate_per_tier.items()
            },
            "dataset_revision_hash": "test_rev",
            "hermes_agent_commit": "test_commit",
            "stratified_subset_seed": 42,
            "tblite_estimated_cost_per_task_usd": 0.4,
            "calibration_timestamp": "2026-05-19T00:00:00Z",
            "calibration_model": "test/model",
            "tblite_runner_version": "1.0",
        }
        if anchor_overrides:
            anchor.update(anchor_overrides)
        (datasets_dir / "tblite_anchor.json").write_text(json.dumps(anchor))
        subset = {
            "seed": 42,
            "per_tier_counts": {"easy": 1, "medium": 1, "hard": 1, "extreme": 1},
            "task_filter": [
                {"name": "t-easy", "tier": "easy"},
                {"name": "t-medium", "tier": "medium"},
                {"name": "t-hard", "tier": "hard"},
                {"name": "t-extreme", "tier": "extreme"},
            ],
            "source": "test",
            "generated_timestamp": "2026-05-19T00:00:00Z",
        }
        if subset_overrides:
            subset.update(subset_overrides)
        (datasets_dir / "tblite_stratified_subset.json").write_text(
            json.dumps(subset)
        )
        # Also stub a drift_thresholds.json since the existing pipeline requires it.
        drift_thresholds = {
            "tone": 0.5, "formality": 0.5, "vocabulary": 0.5, "persona": 0.5,
            "_meta": {"f1_tier": 1},
        }
        (datasets_dir / "drift_thresholds.json").write_text(
            json.dumps(drift_thresholds)
        )

        # Constraint result shim for the mocked gate.
        from evolution.core.constraints import ConstraintResult
        gate_report = {
            "decision": gate_decision,
            "risk_score": gate_risk_score,
            "reject_threshold": 4.0,
            "tier_weights": {"easy": 1.0, "medium": 1.5, "hard": 2.0, "extreme": 4.0},
            "per_tier": gate_per_tier,
            "samples_jsonl_path": str(tmp_path / "samples.jsonl"),
            "subprocess_runtime_seconds": 1.0,
            "cost_breakdown": {"modal_compute_usd": 1.0},
            "dataset_revision_hash": "test_rev",
            "cache_hit": False,
            "async_full_verify_pending": False,
            "jsonl_skipped_lines_total": 0,
            "stderr_tails": [],
            "artifact_hash": "abc123",
            "constraint_result": ConstraintResult(
                passed=(gate_decision == "accept"),
                constraint_name="tblite_benchmark",
                message=f"Risk_Score={gate_risk_score:.2f}",
                details="{}",
            ),
        }

        def _make_gate(*args, **kwargs):
            if gate_constructor_recorder is not None:
                gate_constructor_recorder.append({"args": args, "kwargs": kwargs})
            mg = MagicMock()
            if check_all_recorder is not None:
                def _record(*a, **kw):
                    check_all_recorder.append(kw)
                    return [gate_report]
                mg.check_all.side_effect = _record
            else:
                mg.check_all.return_value = [gate_report]
            return mg

        with runner.isolated_filesystem(temp_dir=str(tmp_path)) as iso:
            iso_path = Path(iso)
            (iso_path / "datasets" / "prompts").mkdir(parents=True, exist_ok=True)
            for fname in ("tblite_anchor.json", "tblite_stratified_subset.json",
                          "drift_thresholds.json"):
                (iso_path / "datasets" / "prompts" / fname).write_text(
                    (datasets_dir / fname).read_text()
                )

            patches = [
                # W-4 (a) source-site patch.
                patch(
                    "evolution.benchmarks.benchmark_gate.TBLiteBenchmarkGate",
                    side_effect=_make_gate,
                ),
                # W-4 (b) consumer-site patch — established AFTER the lazy
                # `from ... import ...` inside evolve(). Patching only (a) is
                # insufficient: by the time the test reaches the gate call,
                # the name is rebound in evolve_prompt_sections' namespace.
                patch(
                    "evolution.prompts.evolve_prompt_sections.TBLiteBenchmarkGate",
                    side_effect=_make_gate,
                    create=True,
                ),
                # DriftDetector is heavy; stub so 3-run averaging doesn't fire.
                patch(
                    "evolution.prompts.drift_detector.DriftDetector",
                    return_value=MagicMock(
                        check_all=MagicMock(return_value=[]),
                    ),
                ),
                # ... PromptModule + dspy stubs (mirror TestDriftGate from 18-05) ...
            ]

            for p in patches:
                p.start()
            try:
                result = runner.invoke(cli_main, cli_args)
            finally:
                for p in patches:
                    p.stop()

            output_root = iso_path / "output" / "prompts"
            out_dirs = sorted(output_root.glob("*")) if output_root.exists() else []
            output_dir = out_dirs[-1] if out_dirs else None
            return result, output_dir


    class TestBenchmarkGate:
        """Phase 20 Plan 06 CLI integration tests.

        Each test double-patches TBLiteBenchmarkGate at BOTH binding sites
        (W-4 revision 2026-05-19):
          (a) evolution.benchmarks.benchmark_gate.TBLiteBenchmarkGate (source)
          (b) evolution.prompts.evolve_prompt_sections.TBLiteBenchmarkGate
              (the local binding established by the lazy import inside
              evolve(); patching only (a) misses this binding and the real
              gate fires).

        W-4 also forbids pytest.skip for "harness didn't reach step 10.5".
        Tests must FAIL when wiring is broken; pytest.skip is only acceptable
        for environment issues (e.g. dspy not configured).
        """

        def test_benchmark_none_default_path_unchanged(self, tmp_path):
            """--benchmark=none -> metrics.json has benchmark_decision='skipped' and NO benchmark_risk_score."""
            from click.testing import CliRunner
            runner = CliRunner()
            result, output_dir = _benchmark_patched_run(
                runner,
                [
                    "--section", "memory_guidance",
                    "--iterations", "0",
                    "--eval-source", "synthetic",
                    "--benchmark", "none",
                ],
                tmp_path=tmp_path,
            )
            assert result.exit_code == 0 or output_dir is not None, \
                f"CLI exited non-zero with no output_dir: {result.output[:500]}"
            if output_dir and (output_dir / "metrics.json").exists():
                import json
                m = json.loads((output_dir / "metrics.json").read_text())
                assert m.get("benchmark_decision") == "skipped"
                assert "benchmark_risk_score" not in m

        def test_benchmark_tblite_accept_writes_report_and_metrics(self, tmp_path):
            """W-4 enforcement: assertion failures here surface as test FAIL,
            not pytest.skip. If output_dir is None the wiring is broken — FAIL."""
            from click.testing import CliRunner
            runner = CliRunner()
            result, output_dir = _benchmark_patched_run(
                runner,
                [
                    "--section", "memory_guidance",
                    "--iterations", "0",
                    "--benchmark", "tblite",
                ],
                tmp_path=tmp_path,
                gate_decision="accept",
                gate_risk_score=1.5,
            )
            assert output_dir is not None, (
                f"Step 10.5 wiring failure: no output_dir created. "
                f"CLI output: {result.output[:500]}"
            )
            assert (output_dir / "tblite_report.json").exists(), \
                "accept path must write tblite_report.json"
            import json
            m = json.loads((output_dir / "metrics.json").read_text())
            assert m["benchmark_decision"] == "accept"
            assert m["benchmark_passed"] is True
            assert m["benchmark_risk_score"] == 1.5
            assert "benchmark_per_tier" in m
            assert "total_cost_breakdown" in m

        def test_benchmark_tblite_reject_writes_FAILED_dir(self, tmp_path):
            """W-4 enforcement: reject branch wiring failures surface as FAIL."""
            from click.testing import CliRunner
            runner = CliRunner()
            result, output_dir = _benchmark_patched_run(
                runner,
                [
                    "--section", "memory_guidance",
                    "--iterations", "0",
                    "--benchmark", "tblite",
                ],
                tmp_path=tmp_path,
                gate_decision="reject",
                gate_risk_score=5.0,
            )
            assert output_dir is not None, (
                f"Step 10.5 reject wiring failure: no output_dir created. "
                f"CLI output: {result.output[:500]}"
            )
            assert "FAILED_" in output_dir.name, \
                f"reject path must write FAILED_<ts>/; got {output_dir.name}"
            import json
            m = json.loads((output_dir / "metrics.json").read_text())
            assert m["benchmark_decision"] == "reject"
            assert m["benchmark_passed"] is False
            assert m["benchmark_risk_score"] == 5.0
            assert (output_dir / "tblite_report.json").exists()
            assert (output_dir / "evolved_sections.json").exists()
            assert (output_dir / "diff.txt").exists()

        def test_benchmark_cache_flag_threads_through(self, tmp_path):
            from click.testing import CliRunner
            runner = CliRunner()
            recorder: list = []
            result, _ = _benchmark_patched_run(
                runner,
                [
                    "--section", "memory_guidance",
                    "--iterations", "0",
                    "--benchmark", "tblite",
                    "--no-benchmark-cache",
                ],
                tmp_path=tmp_path,
                gate_decision="accept",
                check_all_recorder=recorder,
            )
            assert len(recorder) >= 1, "gate.check_all was never invoked"
            kw = recorder[-1]
            assert kw.get("use_cache") is False, \
                f"--no-benchmark-cache must thread use_cache=False; kwargs={kw}"

        def test_no_skip_benchmark_flag(self):
            """--no-benchmark and --skip-benchmark are rejected by Click."""
            from click.testing import CliRunner
            from evolution.prompts.evolve_prompt_sections import main as cli_main
            r1 = CliRunner().invoke(cli_main, ["--no-benchmark"])
            assert r1.exit_code != 0, "--no-benchmark must be rejected"
            r2 = CliRunner().invoke(cli_main, ["--skip-benchmark"])
            assert r2.exit_code != 0, "--skip-benchmark must be rejected"

        def test_total_cost_breakdown_present(self, tmp_path):
            from click.testing import CliRunner
            runner = CliRunner()
            result, output_dir = _benchmark_patched_run(
                runner,
                [
                    "--section", "memory_guidance",
                    "--iterations", "0",
                    "--benchmark", "tblite",
                ],
                tmp_path=tmp_path,
                gate_decision="accept",
            )
            assert output_dir is not None, (
                f"Step 10.5 wiring failure (total_cost_breakdown test). "
                f"CLI output: {result.output[:500]}"
            )
            import json
            m = json.loads((output_dir / "metrics.json").read_text())
            assert "total_cost_breakdown" in m, \
                "W-2/W-3 regression: total_cost_breakdown missing from metrics.json"
            tcb = m["total_cost_breakdown"]
            assert "optimization" in tcb, "W-2/W-3: optimization key missing"
            assert "benchmark" in tcb, "W-2/W-3: benchmark key missing"
            assert isinstance(tcb["optimization"], (int, float)), \
                f"optimization must be numeric, got {type(tcb['optimization']).__name__}"
            assert isinstance(tcb["benchmark"], (int, float))

        def test_benchmark_tier_field_filters_subset(self, tmp_path):
            """W-7: --benchmark-tier filter selects items where item['tier'] matches."""
            from click.testing import CliRunner
            runner = CliRunner()
            constructor_recorder: list = []
            result, _ = _benchmark_patched_run(
                runner,
                [
                    "--section", "memory_guidance",
                    "--iterations", "0",
                    "--benchmark", "tblite",
                    "--benchmark-tier", "easy,medium",
                ],
                tmp_path=tmp_path,
                gate_decision="accept",
                gate_constructor_recorder=constructor_recorder,
            )
            assert len(constructor_recorder) >= 1, \
                f"TBLiteBenchmarkGate constructor never invoked; CLI: {result.output[:500]}"
            # The constructor receives stratified_subset as a kwarg or
            # positional arg. Inspect for kwarg first, fall back to args.
            call = constructor_recorder[-1]
            kw = call["kwargs"]
            args = call["args"]
            subset_arg = kw.get("stratified_subset")
            if subset_arg is None and len(args) >= 3:
                subset_arg = args[2]
            assert subset_arg is not None, \
                f"could not find stratified_subset in constructor call: {call}"
            tiers_seen = {
                str(item.get("tier", "")).strip().lower()
                for item in subset_arg.get("task_filter", [])
                if isinstance(item, dict)
            }
            assert tiers_seen == {"easy", "medium"}, \
                f"--benchmark-tier easy,medium should filter subset to those tiers; got tiers={tiers_seen}"

        def test_detach_mode_not_yet_implemented_exits(self, tmp_path):
            from click.testing import CliRunner
            runner = CliRunner()
            result, _ = _benchmark_patched_run(
                runner,
                [
                    "--section", "memory_guidance",
                    "--iterations", "0",
                    "--benchmark", "tblite",
                    "--detach",
                ],
                tmp_path=tmp_path,
                gate_decision="accept",
            )
            assert result.exit_code != 0, "--detach must not exit 0 in Plan 06"

        def test_step_10_5_wiring_must_not_be_silent_skip(self, tmp_path):
            """W-4 enforcement: when the harness reaches step 10.5 the gate
            constructor MUST fire (recorded). If it doesn't, the test fails
            instead of pytest.skip-ping silently."""
            from click.testing import CliRunner
            runner = CliRunner()
            constructor_recorder: list = []
            result, output_dir = _benchmark_patched_run(
                runner,
                [
                    "--section", "memory_guidance",
                    "--iterations", "0",
                    "--benchmark", "tblite",
                ],
                tmp_path=tmp_path,
                gate_decision="accept",
                gate_constructor_recorder=constructor_recorder,
            )
            # If the harness can produce ANY output_dir at all, then step 10.5
            # MUST have run. If neither output_dir nor a constructor call were
            # observed, the wiring is broken — fail loudly.
            if output_dir is None and not constructor_recorder:
                raise AssertionError(
                    "Step 10.5 wiring failure: neither output_dir nor "
                    "TBLiteBenchmarkGate constructor were observed. "
                    "Tests must NOT silently skip past step 10.5. "
                    f"CLI output: {result.output[:500]}"
                )
            # If gate constructor was called, accept path should write report.
            if constructor_recorder:
                assert output_dir is not None, \
                    "constructor fired but no output_dir — accept path broken"
                assert (output_dir / "tblite_report.json").exists(), \
                    "accept path must write tblite_report.json"
    ```

    After writing, run `.venv/bin/pytest tests/prompts/test_evolve_prompt_sections_cli.py::TestBenchmarkGate -v` and confirm all 9 tests run. The deterministic regression guards (test_no_skip_benchmark_flag, test_detach_mode_not_yet_implemented_exits, test_step_10_5_wiring_must_not_be_silent_skip) MUST pass. Other tests pass when wiring is correct; they FAIL (not skip) when wiring is broken.

    Implements: PATTERNS §File 5 §Insertion points + Phase 18 Plan 18-05 TestDriftGate analog + W-4 double-patch enforcement.
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/prompts/test_evolve_prompt_sections_cli.py::TestBenchmarkGate -v --tb=short 2>&1 | tail -40 && .venv/bin/pytest tests/prompts/test_evolve_prompt_sections_cli.py::TestBenchmarkGate::test_no_skip_benchmark_flag -v --tb=short 2>&1 | tail -5 | grep -E 'passed' || (echo "FAIL: critical regression guard test_no_skip_benchmark_flag did not pass"; exit 1) && .venv/bin/pytest tests/prompts/test_evolve_prompt_sections_cli.py::TestBenchmarkGate::test_detach_mode_not_yet_implemented_exits -v --tb=short 2>&1 | tail -5 | grep -E 'passed' || (echo "FAIL: regression guard test_detach_mode_not_yet_implemented_exits did not pass"; exit 1) && .venv/bin/pytest tests/prompts/test_evolve_prompt_sections_cli.py::TestBenchmarkGate::test_step_10_5_wiring_must_not_be_silent_skip -v --tb=short 2>&1 | tail -5 | grep -E 'passed' || (echo "FAIL: W-4 regression guard test_step_10_5_wiring_must_not_be_silent_skip did not pass"; exit 1) && grep -c 'class TestBenchmarkGate' tests/prompts/test_evolve_prompt_sections_cli.py | awk '{ if ($1 < 1) { print "FAIL: TestBenchmarkGate class missing"; exit 1 } else { print "OK class present" } }' && grep -c 'def test_' tests/prompts/test_evolve_prompt_sections_cli.py | awk '{ if ($1 < 8) { print "FAIL: test method count " $1 " too low (need >=8 including pre-existing + 9 new)"; exit 1 } else { print "OK total " $1 " tests" } }' && grep -c '"evolution.prompts.evolve_prompt_sections.TBLiteBenchmarkGate"' tests/prompts/test_evolve_prompt_sections_cli.py | awk '{ if ($1 < 1) { print "FAIL: W-4 double-patch consumer-site missing"; exit 1 } else { print "OK W-4 double-patch present" } }' && grep -c 'pytest.skip.*step 10.5\|pytest.skip.*harness' tests/prompts/test_evolve_prompt_sections_cli.py | awk '{ if ($1 != 0) { print "FAIL: W-4 violation — pytest.skip for harness-didnt-reach-step-10.5 found (must FAIL instead)"; exit 1 } else { print "OK no silent-skip for step 10.5" } }' && .venv/bin/pytest tests/ -q --tb=line 2>&1 | tail -3 | grep -E 'passed|failed' || (echo "FAIL: full test suite did not produce a summary line"; exit 1)</automated>
  </verify>
  <acceptance_criteria>
    - `tests/prompts/test_evolve_prompt_sections_cli.py` now contains class `TestBenchmarkGate` with >= 8 test methods (W-4 adds one explicit wiring-enforcement test).
    - Test `test_no_skip_benchmark_flag` PASSES (regression guard for D-BYPASS-01 spirit).
    - Test `test_detach_mode_not_yet_implemented_exits` PASSES (Plan 06 scope guard).
    - Test `test_step_10_5_wiring_must_not_be_silent_skip` PASSES (W-4 enforcement guard).
    - `_benchmark_patched_run` patches `evolution.prompts.evolve_prompt_sections.TBLiteBenchmarkGate` (W-4 consumer-site patch). `grep -c '"evolution.prompts.evolve_prompt_sections.TBLiteBenchmarkGate"' tests/prompts/test_evolve_prompt_sections_cli.py` >= 1.
    - No `pytest.skip(...)` call references "step 10.5" or "harness didn't reach" — those scenarios MUST fail the test instead (W-4).
    - `pytest tests/ --collect-only` succeeds globally (no syntax error in the appended class).
    - tests/prompts/ test count rises by >= 8.
  </acceptance_criteria>
  <done>
    - TestBenchmarkGate class appended with >= 8 test methods including the W-4 wiring-enforcement guard
    - Regression guards (no-bypass-flag, detach-not-implemented, wiring-must-not-skip) pass deterministically
    - Double-patch at both `evolution.benchmarks.benchmark_gate` AND `evolution.prompts.evolve_prompt_sections` namespaces
    - Cache flag and tier-field-filter (W-7) tests use recorders for kwargs/constructor inspection
    - Reject path test asserts all 4 FAILED_<ts>/ artifacts (metrics.json + tblite_report.json + evolved_sections.json + diff.txt)
    - No pytest.skip for step-10.5-not-reached scenarios — those FAIL the test
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| --benchmark CLI flag → benchmark mode selection | Click `type=click.Choice(["none","tblite","tblite-full"])` rejects other values at parse time. Phase 22 will add real `tblite-full` handler. |
| --benchmark-tier CLI flag → CSV parse → tier filter | Parsed via `.split(",")` + lowercase + whitelist check (`{easy,medium,hard,extreme}`). Unknown tier → `click.ClickException` with explicit message. W-7 schema: filter selects items by `item['tier']`. |
| --benchmark-max-cost CLI flag → CostTracker max_usd | float coerced by Click. CostTracker handles <= 0 short-circuit (cost_tracker.py:266). |
| --benchmark-cache toggle → use_cache kwarg to gate.check_all | Boolean; plumbed verbatim. |
| datasets/prompts/tblite_anchor.json → TBLiteBenchmarkGate.__init__ | UNTRUSTED at IO level. Plan 03's constructor validates schema. `_meta.tier=="mock"` warning surfaces at Plan 06 invocation time — per Plan 05 B-1, no mock anchor should ever be produced, so this warning indicates an external / archived artifact. |
| evolved_sections (PromptModule output) → gate.check_all → Virtual Prompt Overlay | Plan 03 handles atomic replace + always-restore; Plan 06 just passes the sections through. |
| optimization_tracker.spent_usd → metrics.json `total_cost_breakdown.optimization` | Real spend captured by Edit 0's CostTracker wrap; cleartext USD float, not sensitive. |
| benchmark_tracker.spent_usd → metrics.json `total_cost_breakdown.benchmark` | Cleartext USD float; not sensitive. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-20-29 | E (Elevation of privilege) | --benchmark bypass via novel flag | mitigate | Click Choice restricts --benchmark to {none, tblite, tblite-full}. NO `--no-benchmark` / `--skip-benchmark` decorator exists (verified by `grep -nE '@click\.option\(\s*"--(no\|skip)-benchmark"'` returning 0). Regression guard test_no_skip_benchmark_flag fires on any future violation. |
| T-20-30 | T (Tampering) | --benchmark-tier CSV smuggling shell metachars | accept | The CSV is split + lowercase + whitelist-validated AGAINST `{easy,medium,hard,extreme}`. Any unknown token → click.ClickException. Even if a tier name slipped through, Plan 02's `_validate_task_filter` re-checks task names at subprocess construction. |
| T-20-31 | I (Information disclosure) | tblite_report.json contains stderr_tails from Modal failures | mitigate | Plan 02's stderr_tail cap (20 lines) limits exposure. Plan 06 writes the full report — Phase 14 SECRET_PATTERNS pass is deferred. Documented limitation; logs/regression.jsonl write site (also deferred to Phase 22 per the W-1 tracking todo) is where the SECRET_PATTERNS filter belongs per CONTEXT §integration points. |
| T-20-32 | D (Denial of service) | benchmark gate runs against a stale anchor (commit_hash mismatch) | mitigate | Plan 03 `_check_anchor_existence` raises SystemExit(1) inside check(). Plan 06 invokes check_all -> check; the SystemExit propagates up and click.Abort terminates the run cleanly. W-5 added warn-only dataset_revision_hash drift check (yellow Rich warning, continues). |
| T-20-33 | T (Tampering) | optimization_tracker.spent_usd reported as 0.0 due to DSPy track_usage unwired | accept | Edit 0 wires the tracker correctly; `spent_usd` reflects whatever DSPy `track_usage` reports during compile. In tests where LMs are mocked, spent_usd is naturally 0.0 — that is correct (the field reports REAL spend, not mocked spend). Pre-W-2/W-3, this field was permanently 0.0 due to `locals().get(...)` silent default; that fallback is now eliminated. |
| T-20-34 | E (Elevation of privilege) | tblite-full CLI flag accepted but unimplemented | mitigate | Step 10.5 raises `click.ClickException` with explicit Phase 22 reference when `benchmark == "tblite-full"`. |
| T-20-35 | I (Information disclosure) | mock-tier anchor accepted as production baseline | mitigate-by-elimination + runtime guard | Plan 05 B-1 forbids producing mock anchors. Step 10.5's bold yellow Rich warning when `_meta.tier == "mock"` is RETAINED as a runtime guard against stale archive / external artifacts that bypass Plan 05's flow. |
| T-20-37 | T (Tampering) | optimization_tracker_spent silent-zero via locals().get fallback | **MITIGATED BY ELIMINATION (W-2/W-3, 2026-05-19)** | The locals().get("optimization_tracker_spent", 0.0) fallback was the silent-zero bug. Plan 06 Edit 0 wires a real CostTracker; Edit 3 references `optimization_tracker_spent` directly (will raise NameError if Edit 0 is skipped — loud-fail instead of silent-zero). Verify gate runs `grep -nE 'locals\(\).get\("optimization_tracker_spent"'` and FAILS if any match exists. |
</threat_model>

<verification>
- `pytest tests/prompts/test_evolve_prompt_sections_cli.py::TestBenchmarkGate -v` exits 0 with deterministic guards PASSING (test_no_skip_benchmark_flag, test_detach_mode_not_yet_implemented_exits, test_step_10_5_wiring_must_not_be_silent_skip at minimum).
- `pytest tests/ --collect-only` succeeds (no global discovery break from the new class).
- `python -m evolution.prompts.evolve_prompt_sections --help` shows --benchmark, --benchmark-tier, --benchmark-cache, --no-benchmark-cache, --benchmark-max-cost, --wait, --detach, --async-full-verify, --no-async-full-verify.
- `--help` does NOT show --no-benchmark / --skip-benchmark.
- `grep -c 'benchmark_decision' evolution/prompts/evolve_prompt_sections.py` >= 3.
- `grep -c 'tblite_report\.json' evolution/prompts/evolve_prompt_sections.py` >= 2.
- `grep -c 'total_cost_breakdown' evolution/prompts/evolve_prompt_sections.py` >= 2.
- `grep -c 'TBLiteBenchmarkGate' evolution/prompts/evolve_prompt_sections.py` >= 1 (lazy import inside evolve()).
- `grep -nE '^from evolution\.benchmarks\.benchmark_gate' evolution/prompts/evolve_prompt_sections.py` returns 0 (no top-level import — must be inside evolve()).
- **(W-2/W-3)** `grep -c 'CostTracker' evolution/prompts/evolve_prompt_sections.py` >= 2 (import + ≥1 instantiation).
- **(W-2/W-3)** `grep -nE 'optimization_tracker\b' evolution/prompts/evolve_prompt_sections.py` count >= 4.
- **(W-2/W-3)** `grep -nE 'locals\(\).get\("optimization_tracker_spent"' evolution/prompts/evolve_prompt_sections.py` returns 0.
- **(W-1)** `test -f .planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md` succeeds.
- **(W-4)** `grep -c '"evolution.prompts.evolve_prompt_sections.TBLiteBenchmarkGate"' tests/prompts/test_evolve_prompt_sections_cli.py` >= 1.
</verification>

<success_criteria>
- ROADMAP SC #1 covered: `--benchmark={none,tblite}` flag triggers TBLite evaluation before write-back.
- ROADMAP SC #2 covered: `--benchmark-max-cost` + reject_threshold (default 4.0 from Plan 03 constants) are configurable.
- ROADMAP SC #3 covered: benchmark results in `metrics.json` (benchmark_decision/passed/risk_score/per_tier/tier_weights/reject_threshold + total_cost_breakdown with REAL optimization spend) and side-by-side `tblite_report.json`.
- D-04 covered: tblite_report.json schema written on both accept and reject paths.
- D-05 + W-7 covered: --benchmark-tier filter selects by item['tier'] field (NO index slicing).
- D-15 covered: cache_dir wired with `~/.cache/hermes-evolution/tblite/`.
- D-16 covered: dual-track total_cost_breakdown emits {optimization, benchmark} with REAL tracker spend on both sides.
- D-18 covered: step 10.5 between step 10 and step 11.
- Phase 18 D-BYPASS-01 spirit: no --no-benchmark / --skip-benchmark flag; --benchmark=none IS the bypass.
- W-1, W-2, W-3, W-4, W-7 all addressed (see Revision Log).
- T-20-29..T-20-37 mitigated or accepted with rationale.
- Phase 20 closes — ROADMAP Phase 20 row can transition to "Complete" after Plan 05 anchor commit + this plan's tests green.
</success_criteria>

<output>
After completion, create `.planning/phases/20-benchmark-gated-validation/20-06-evolve-integration-SUMMARY.md` covering:
- 5 edit anchor lines (before/after) and diff stats.
- pytest summary line for TestBenchmarkGate (expect 8+ tests, all should PASS — no silent skips for step-10.5 wiring).
- Grep evidence: benchmark_decision count, tblite_report.json count, TBLiteBenchmarkGate import location (must be inside evolve()), CostTracker count (≥2), optimization_tracker count (≥4), locals().get fallback count (==0).
- Confirmation that `python -m evolution.prompts.evolve_prompt_sections --help` displays the 6 new flags AND does not display --no-benchmark / --skip-benchmark.
- Confirmation that `.planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md` exists with the documented W-1 content template.
- Explicit listing of the 2 deferred features (now tracked in the W-1 todo):
  1. `--check-benchmark <ts>` / `--restore <ts>` / `--confirm-rollback <ts>` subcommands
  2. async-full-verify background dispatch
- ROADMAP Phase 20 row update note: ready to mark Complete after Wave 4 anchor commit + Wave 5 tests green.
</output>

## Revision Log

- 2026-05-19 (W-1): Added `.planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md` to the plan's `<files>` block and `must_haves.artifacts`. New Edit 5 in Task 1 creates the todo with a concrete content template (frontmatter + body explaining what's deferred and the Phase 22 acceptance criterion). Added a `test -f` verify gate.
- 2026-05-19 (W-2/W-3): Added a NEW Edit 0 that wraps the GEPA/MIPROv2 compile section with a real `CostTracker(max_usd=config.max_cost_usd)`. Pre-edit grep at planning time confirmed `evolve_prompt_sections.py` has ZERO `CostTracker` references — Phase 13's `max_cost_usd` field was declared but never instantiated for prompt evolution. Edit 0 closes this gap. Edit 3 now references `optimization_tracker_spent` directly (no `locals().get(...)` fallback); will raise NameError loudly if Edit 0 is skipped instead of silently reporting 0.0. Same fix applied to BOTH the success-path metrics block (Edit 3) AND the reject-path FAILED_<ts>/ metrics block (Edit 2 reject branch). Added explicit verify gates: `optimization_tracker` count ≥4, `CostTracker` count ≥2, `locals().get("optimization_tracker_spent"` count ==0. Test `test_total_cost_breakdown_present` now asserts the field exists with numeric values, not just "if-output-dir".
- 2026-05-19 (W-4): Test helper `_benchmark_patched_run` now double-patches `TBLiteBenchmarkGate` at BOTH `evolution.benchmarks.benchmark_gate` (source) AND `evolution.prompts.evolve_prompt_sections` (the binding established by the lazy `from ... import ...` inside evolve()). Added explicit `test_step_10_5_wiring_must_not_be_silent_skip` guard. Removed `pytest.skip` usage for "harness didn't reach step 10.5" scenarios — those now FAIL the test. `pytest.skip` is reserved for environment issues only.
- 2026-05-19 (W-7): `--benchmark-tier` filter now selects subset items by `item['tier']` field (W-7 object schema) rather than slicing by `per_tier_counts` offsets. Falls back with a yellow Rich warning if a legacy flat-string subset is encountered. Test `test_benchmark_tier_csv_filters_subset` renamed to `test_benchmark_tier_field_filters_subset` and now inspects the constructor-passed subset directly (via `gate_constructor_recorder`) to confirm the filter operated on `item['tier']`.
- 2026-05-19 (B-1 interaction note): The `_meta.tier == "mock"` runtime warning in step 10.5 is retained as a guard against historical / external archive artifacts that bypass Plan 05's flow. After Plan 05's B-1 revision (no mock-anchor authoring) the warning indicates only a stale or external anchor — never a sanctioned authoring path. Wording in the docstring updated accordingly.
