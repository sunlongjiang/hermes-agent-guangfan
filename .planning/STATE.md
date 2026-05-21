---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: — Stabilization, Enhancement & Expansion
status: planning
stopped_at: Phase 22 context gathered
last_updated: "2026-05-21T03:46:40.646Z"
last_activity: 2026-05-20
progress:
  total_phases: 11
  completed_phases: 8
  total_plans: 53
  completed_plans: 53
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-23)

**Core value:** 让 GEPA 优化循环能覆盖工具描述和系统提示词，使 hermes-agent 的核心文本制品都能被系统性地自动改进
**Current focus:** Phase 21 — darwinian-code-evolution

## Current Position

Phase: 22
Plan: Not started
Status: Ready to plan
Last activity: 2026-05-20

Progress: [█████████░] 87%

## Milestone v2.0 Phase Map

| Phase | Name | Status |
|-------|------|--------|
| 12 | v1 Stabilization | ✓ Complete |
| 13 | Per-Parameter Description Optimization | Next |
| 14 | SessionDB Mining for Tools | Pending |
| 15 | Think-Augmented Tool Selection | Pending |
| 16 | Per-Tool Regression Dashboard | Pending |
| 17 | Joint Section Optimization | Pending |
| 18 | Personality Drift Detection | Pending |
| 19 | SessionDB Behavioral Mining for Prompts | Pending |
| 20 | Benchmark-Gated Validation | Pending |
| 21 | Darwinian Code Evolution | Pending |

## Accumulated Context

### Decisions (v1)

- Roadmap: Tool descriptions (Phase 2-6) before system prompts (Phase 7-11) per research findings
- Roadmap: Fine granularity -- 10 focused phases for 23 requirements
- [Phase 02]: AST + positional replacement for format-preserving write-back
- [Phase 06]: Skipped -- TEST-01 already satisfied by 107 tests created during Phase 2-5 TDD
- [Phase 07]: AST 解析 prompt_builder.py 提取 5 段落，PLATFORM_HINTS 按 key 展开
- [Phase 08]: PromptModule 用动态 Predict 移动实现 per-section 隔离
- [Phase 09]: LLM 合成 80 场景，按重要性加权，复用 FitnessScore
- [Phase 10]: PromptRoleChecker + evolve_prompt_sections CLI 端到端管道
- [Phase 11]: Skipped -- TEST-02 already satisfied by 83 tests created during Phase 7-10 TDD
- [Phase 12]: GEPA 5-param metric signature + reflection_lm wired; multi-model backend via evolution.yaml
- [Phase 12 post-audit 2026-05-07]: Codebase map refresh surfaced 5 HIGH + 9 MED concerns. All 5 HIGH fixed (commits 7500abc `output/` gitignore, 5ed6dbb skill GEPA 5-param, 4887a02 skill CLI honors evolution.yaml, 05cc00d env-var references + pre-commit guard). 9 MED concerns parked as `.planning/todos/pending/*.md` for future pickup.
- [Phase 13 discuss 2026-05-07]: Gray areas resolved across module structure (two-dim param_predictors, physically isolated tool-level desc), CLI shape (new `evolve_tool_params` entry, existing CLI untouched), scope (joint fitness + param_consistency + per-tool persistence + cost cap all in-scope; v1 baseline hard regression gate; no default param-group cap), eval (reuse Phase 4 dataset, joint 50/50 exact-match, selector outputs tool+params together). Folded todos: loud-gepa-fallback, persist-per-tool-regression-rates, max-cost-usd-and-reflection-model.
- [Phase 13-07 2026-05-08]: V1 baseline hard-gate landed in `evolution/tools/v1_baseline_gate.py` — `check_v1_baseline_gate` returns `ConstraintResult` (per Wave 0 contract); `compute_v1_baseline` resolves baseline source as historical (Phase 5 metrics.json:evolved_score, type-safe loader rejects bool/string/OOR/malformed) → inline (rerun joint metric on baseline ToolModule + holdout) → missing (degraded). `V1BaselineGate` facade for 13-08 CLI metrics.json shape. Plan-vs-test signature conflict resolved by honoring tests as canonical source; `evolve_tool_params.py` shell module re-exports the gate symbols (13-08 will replace shell with full Click CLI, exports preserved). Wave 0 RED tests now GREEN.
- [Phase 13-08 2026-05-08]: evolve_tool_params CLI end-to-end pipeline landed at `evolution/tools/evolve_tool_params.py` (991 LoC; 14 flags). Wires all Wave 1-3 atomic components into a single user entry point: discover → ToolModule (13-02) → joint metric+feedback (13-03) → ParamConsistencyChecker (13-04) → CostTracker w/ _CostStopper StopperProtocol adapter (13-05) → persist_per_tool_rates (13-06) → V1BaselineGate (13-07). Loud-by-default GEPA failure (D-15a closure); `--allow-miprov2-fallback` opt-in records `optimizer_used: 'miprov2'` in metrics.json. FAILED_<ts>/ + ABORTED_<ts>/ + success output topology. Hard scope guard verified (`grep -c 'write_back'` = 0). Wave 0 RED tests GREEN; full suite 385 passed + 1 xfailed. Phase 13 = **8/8 plans complete**.
- [Phase 18-01 2026-05-15]: Wave 0 RED scaffolds — 14 failing pytest scaffolds (10 in tests/prompts/test_drift_detector.py + 4 in tests/prompts/test_drift_calibration.py) plus first-ever tests/prompts/conftest.py (mock_drift_lm, dummy_thresholds, drift_calibration_mini_path fixtures) and 6-row deterministic mini calibration fixture. .gitignore now exempts datasets/prompts/drift_calibration.jsonl + drift_thresholds.json per D-CAL-02. Lazy module imports inside test helpers let pytest --collect-only succeed before Wave 1/3 production code exists; tests fail at run time with ModuleNotFoundError as intended. tests/prompts/ test count rose from 97 to 111 with zero regression. Commits: 97f8c08, bba021c, c00ad1f.
- [Phase 18-02 2026-05-15]: Wave 1 — DriftDetector + DriftCalibrationBuilder + derive_thresholds shipped (drift_detector.py 258 LoC + drift_calibration.py 271 LoC). DriftDetector uses typed-float DSPy Signature with try/except ValidationError -> 0.0 fallback (NOT 0.5) per RA1/M4 prevention. LM constructed in __init__ with temperature=0.7 + cache=False (RA2/Pitfall A — closes the 'stdev=0 collapses conservative decision' failure mode). check() does 3-run averaging with mean-stdev > threshold conservative rule (D-ROB-02); severity ladder: 0 dims=pass, 1=warn (still deploys), 2+=reject. DriftCalibrationBuilder uses config.judge_model (NOT eval_model) at temperature=0.9 for RA5 model differentiation. derive_thresholds pure-stdlib F1 brute scan over [0.10,0.90] step 0.05 — zero sklearn/numpy/scipy imports (RA3, verified by two-layer source-grep + sys.modules guard). All 13 Wave 0 RED tests turn GREEN; tests/prompts/ 97->110 passed; repo 514->527 passed. Commits: 32324aa, 4821678.
- [Phase 18-03 2026-05-16] COMPLETE: `build_drift_calibration.py` CLI shipped (~400 LoC, 14 flags) + Wave 1 generator fix for persona coverage (commit c7c334f) + v1-pragmatic tier-target flags (commits 91b2007, 49cc32d) + live calibration artifacts (commit 15b9c4c). Final stack: qwen-plus generator (DashScope) + gpt-5.5 detector (api1.mygod.buzz reseller), Tier 2 borderline pass under v1-pragmatic targets (target_self=0.60 / per_dim_floor=0.35 / macro_floor=0.50). Per-dim F1: tone 0.60 ✓, formality 0.42 WARN, vocabulary 0.40 WARN, persona 0.73 ✓, macro 0.54. 10/10 human spot-check passed on the JSONL — data quality is high; the relaxed targets reflect the available judge's discrimination ceiling, not a data problem. `_meta` audit block records preset/targets/models/endpoint/seed/tier for re-derivation tracking. `datasets/prompts/{drift_calibration.jsonl, drift_thresholds.json}` git-tracked via `.gitignore` exception from Plan 18-01. **Security incidents:** two API keys (`OPENAI_API_KEY` sk-proj-…, reseller sk-b43e…dae1) leaked to terminal during execution; user advised to rotate. **Tech debt:** v1-pragmatic gate is permissive (formality/vocabulary warned dims won't catch subtle drift) — future calibration with a stronger judge can tighten back toward research-strict (0.85/0.70/0.80). See `.planning/phases/18-personality-drift-detection/18-03-SUMMARY.md`.
- [Phase 18-04 2026-05-16] COMPLETE: Wave 3 — DriftDetector wired into evolve_prompt_sections.py constraint gate via 5 surgical edits (commit b20f83b). Edit-1 import; Edit-2 step 8c gate (3-run severity ladder pass/warn/reject + Rich Table titled "Drift Detection (per-section x per-dim, 3-run averaged)" + drift_report.txt buffer + extended FAILED path); Edit-3 success metrics drift_per_dim/drift_thresholds/drift_exceeded_dims/drift_passed/drift_max_section/drift_max_dim at 4-space function-body indent OUTSIDE the joint-only conditional (D-ROB-04 mechanically — both joint AND round-robin pipelines emit drift_* fields); Edit-4 success-path drift_report.txt write parallel with diff.txt; Edit-5 --drift-thresholds-path Click flag (default datasets/prompts/drift_thresholds.json, click.Path(exists=True, path_type=Path)) threaded through main() → evolve(). D-BYPASS-01 enforced via decorator-anchored grep `@click\.option\(\s*"--(no|skip)-drift-check"` returning 0 — Click rejects --no-drift-check at parse time with exit 2. Rule-3 deviation: TestABBaseline._ab_patched_run patched to stub drift_thresholds.json under tmp_path + mock DriftDetector to no-op so three sandboxed A/B baseline tests continue passing. TestJointPipeline needed no change — its existing dspy.LM mock causes Wave 1's typed-float ValidationError fallback to fire (all dims → 0.0 → severity=pass). tests/prompts/: 110 passed (baseline retained); tests/: 527 passed, 1 skipped, 1 xfailed (Wave 1 repo baseline retained); Wave 1 drift unit tests: 13 passed. Plan 18-05 (Wave 5 CLI integration tests) UNBLOCKED. See `.planning/phases/18-personality-drift-detection/18-04-SUMMARY.md`.
- [Phase 18-05 2026-05-16] COMPLETE: Wave 4 — 6 CLI integration tests appended to tests/prompts/test_evolve_prompt_sections_cli.py::TestDriftGate (commit b04b108, +526 LoC). Coverage: D-OUT-02 joint mode (`test_metrics_json_has_drift_fields`), D-OUT-02 + D-ROB-04 round-robin (`test_round_robin_metrics_json_has_drift_fields` — regression guard for Plan 18-04 Edit-3 indent placement; fires with explicit "D-ROB-04 REGRESSION" message if drift_* block is ever nested inside the joint-only conditional), D-BYPASS-02 custom thresholds path verbatim propagation (`test_drift_thresholds_path_flag`), D-BYPASS-01 bypass-flag absence (`test_no_skip_drift_flag` — both --no-drift-check and --skip-drift-check rejected by Click at parse time with exit_code != 0), D-GATE-03 soft warn keeps exit 0 + evolved_sections.json (`test_one_dim_drift_warns_but_deploys`), D-GATE-04 hard reject + D-OUT-03 FAILED dir artifacts (`test_two_dim_drift_rejects_and_writes_failed_dir` — asserts FAILED_<ts>/ contains drift_report.txt + evolved_sections.json + diff.txt + metrics.json drift_passed=false). Multi-patch topology mirrors TestABBaseline._ab_patched_run: tmp_path stub thresholds + DriftDetector mock + PromptModule spy factory + dspy LM/configure/context/GEPA mocks. All 6 tests PASS in 0.44s. tests/prompts/ 110 → 116 passed (1 skipped retained); tests/ 527 → 533 passed (1 skipped, 1 xfailed retained). Zero regression. Phase 18 verify gate fully covered: SC#1 (4-dim DriftDetector) → Wave 1 unit tests; SC#2 (constraint gate rejects on multi-dim drift) → `test_two_dim_drift_rejects_and_writes_failed_dir`; SC#3 (drift report in output) → `test_metrics_json_has_drift_fields` + round-robin variant + reject path. Phase 18 = **5/5 plans complete**, ready for verification. See `.planning/phases/18-personality-drift-detection/18-05-SUMMARY.md`.
- [Phase 21-01 2026-05-20] COMPLETE: Infrastructure bootstrap — 3 atomic commits (678bf53 pyproject.toml; 6352603 .pre-commit-config.yaml; 468cf40 LICENSE) close D-02 / D-13 / D-17 / D-18 (layer 1). pyproject.toml: removed [darwinian]=[darwinian-evolver] (PyPI 404), added [code]=[openevolve>=0.2.27] (Apache-2.0 sole evolutionary code search lib; AGPL boundary permanently closed), added "ruff" to [dev] extra + [tool.ruff] line-length=120 select=["E","F","W"]. .pre-commit-config.yaml (first ever in repo): local hook `openevolve-single-import-surface` greps `^import openevolve` / `^from openevolve` in evolution/**.py and rejects any match NOT in evolution/code/code_evolver_adapter.py; always_run=true, pass_filenames=false. Passes vacuously today (no openevolve imports yet) — Plan 21-04 creates code_evolver_adapter.py. T-21-IMPORT first defense layer landed; Plan 06 pytest gate = second layer. LICENSE: standard MIT text with `Copyright (c) 2026 Longjiang Sun` — D-17 irreversible. Checkpoint pre-resolved via orchestrator: user explicitly chose English transliteration "Longjiang Sun" over Chinese git config name "龙江 孙"; year 2026 confirmed. All 6 PLAN <verification> commands PASS (TOML syntax + extras shape + ruff config + hook id + MIT header + output/ gitignore). 9 task-level <done> criteria PASS. Zero deviations. Self-Check PASSED (3 files + 3 commits all found). See `.planning/phases/21-darwinian-code-evolution/21-01-SUMMARY.md`.

### Test Coverage (v2 baseline after 2026-05-07 fixes)

- Tool tests: 107 (tests/tools/)
- Prompt tests: 83 (tests/prompts/)
- Core tests: 139 + 24 new config tests (tests/)
- Skill tests: 7 (tests/skills/)
- **Total: 353 tests, all passing** (329 baseline + 24 config-layer gates)

### Pending Todos

9 MED-severity concerns parked as structured todos. Query with `node $HOME/.claude/get-shit-done/bin/gsd-tools.cjs list-todos`. Surfaced automatically by `todo match-phase` during future `/gsd-discuss-phase` runs. Phase 13 matches (score ≥ 0.6): persist-per-tool-regression-rates, max-cost-usd-and-reflection-model, loud-gepa-fallback. Phase 14 matches (score ≥ 0.6): expand-secret-patterns, enforce-readonly-hermes-agent, jsonl-skip-bad-lines, max-cost-usd-and-reflection-model, persist-per-tool-regression-rates.

## Session Continuity

Last session: 2026-05-21T03:46:40.628Z
Stopped at: Phase 22 context gathered
Next: Phase 18 ready for verification (`/gsd-verify-phase 18`). All 6 CLI integration tests + 13 Wave 1 unit tests + Wave 3 integration tests via TestABBaseline cover the full success-criteria matrix (SC#1 → Wave 1 unit tests; SC#2 → test_two_dim_drift_rejects_and_writes_failed_dir; SC#3 → test_metrics_json_has_drift_fields + round-robin variant + reject path).

## Phase 20 — Wave 4 Deferred

**Plan 20-05 (anchor generation checkpoint) was SKIPPED at user request (2026-05-19).**

The plan is BLOCKING and requires:

- OPENROUTER_API_KEY + MODAL_TOKEN_ID env vars
- Clean hermes-agent tree
- ~$36 budget

Until `datasets/prompts/tblite_anchor.json` exists, `TBLiteBenchmarkGate._check_anchor_existence` raises `SystemExit(1)` — Plan 06 CLI integration is wired up but `--benchmark=tblite` at runtime won't work.

**To resume:** `python -m evolution.benchmarks.build_tblite_calibration --runs 3 --benchmark-max-cost 50.0` then commit the JSON files.
