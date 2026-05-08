---
phase: 13-per-parameter-description-optimization
verified: 2026-05-08T00:00:00Z
status: human_needed
score: 3/3 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: null
  previous_score: null
  gaps_closed: []
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Live --dry-run smoke against a real hermes-agent checkout"
    expected: "Exit 0; stdout includes param_predictors_discovered=<positive int>; tools_in_scope > 0; no Python tracebacks"
    why_human: "Wave 0 unit tests stub HERMES_AGENT_REPO via _load_tool_descriptions monkeypatch. The live integration path (config.hermes_agent_path discovery → tool_loader.discover_tool_files → tool_loader.extract_tool_descriptions) is exercised only by humans with HERMES_AGENT_REPO set."
  - test: "Decide whether the 4 REVIEW BLOCKER findings (BL-01 through BL-04) are addressed in Phase 13 hardening or deferred to Phase 14 hygiene"
    expected: "Either (a) commit 4 fixes against evolve_tool_params.py + v1_baseline_gate.py + cost_tracker.py + test_evolve_tool_params_cli.py, OR (b) explicitly accept the deferral and document in Phase 14 backlog"
    why_human: "User's task framing said the BLOCKERs 'don't auto-fail goal achievement' — but they do affect (a) cost-cap audit-trail correctness (BL-01), (b) FAILED_<ts>/ triage usability (BL-02), (c) test-coverage honesty for D-15a (BL-03), and (d) error-resilience of holdout scoring (BL-04). The disposition (fix-now vs defer) is a project-management call, not a verification call."
  - test: "End-to-end GEPA run on the real hermes-agent dataset to verify the per-param optimization actually improves metrics — not just compiles"
    expected: "metrics.json shows evolved_score >= baseline_score (or improvement < 0 with v1_gate_passed=true), cost_usd_spent > 0 and < cost_usd_cap, param_consistency_failures == 0 on a clean run"
    why_human: "Requires LLM API key + 60-300s wallclock + API spend. Cannot be automated in verifier."
  - test: "Inspect the BL-01 surfaced cost_usd_spent value on a successful run"
    expected: "metrics.json cost_usd_spent reflects actual API spend (>0.10 USD typical); not 0.0"
    why_human: "BL-01 mechanism: tracker.poll() invoked AFTER `with tracker:` block exits → reads stale spent_usd. The only ways to confirm impact (vs. theoretical risk) are: (a) live run, or (b) targeted unit test that polls post-exit. Neither is in the current test suite. Verifier cannot synthesize."
---

# Phase 13: Per-Parameter Description Optimization Verification Report

**Phase Goal:** Extend tool description optimization to individual parameter descriptions, not just top-level
**Requirement IDs:** TOOL-V2-02
**Verified:** 2026-05-08T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ToolModule exposes per-parameter descriptions as independently optimizable parameters | VERIFIED | `evolution/tools/tool_module.py:48-84` introduces `_ToolParamBundle(dspy.Module)` wrapping `param_predictors: dict[str, dspy.Predict]`; live smoke `tm.named_predictors()` yields 3 `tools['<tool>'].param_predictors['<param>']` entries for a 3-param fixture. D-04 hierarchical naming preserved. Tests `test_named_parameters_discovery`, `test_key_hierarchy_preserved`, `test_empty_param_registered` GREEN. |
| 2 | GEPA can mutate individual param descriptions while tool-level description stays frozen | VERIFIED | `evolution/tools/tool_module.py:89-127` — `_frozen_tool_desc: dict[str, str]` is the **only** carrier of tool-level text; `_format_available_tools` reads from this dict, never from a Predict. Smoke confirms 0 entries containing `_frozen_tool_desc` in `named_predictors()` output. Test `test_tool_description_frozen` GREEN. GEPA's `dspy.Predict.signature.instructions` mutation surface targets only `param_predictors[*].signature.instructions`. |
| 3 | Constraint checks enforce max_param_desc_size (200 chars) per parameter | VERIFIED | `evolution/core/config.py:54` defines `max_param_desc_size: int = 200`. `evolution/tools/evolve_tool_params.py:799` invokes `validator._check_size(ptext, "param_description")` for every param of every evolved tool inside the constraint chain (step 11a). `tests/tools/test_param_size_gate.py::test_param_desc_201_chars_rejected` and `::test_param_desc_200_chars_accepted` both GREEN. Live smoke: 201 chars → `passed=False, message="Size exceeded: 201/200 chars (1 over)"`; 200 chars → `passed=True`. |

**Score:** 3/3 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `evolution/tools/tool_module.py` | Per-param ToolModule sub-Module structure | VERIFIED | 233 LoC. Contains `_ToolParamBundle`, `ToolSelectionWithParamsSignature`, `ToolModule.tools[name].param_predictors[pname]`, `_frozen_tool_desc`, `forward()` returning Prediction(selected_tool, selected_params), `get_evolved_descriptions()` round-trip. |
| `evolution/tools/tool_metric.py` | joint_tool_param_metric + feedback variant + persist_per_tool_rates | VERIFIED | 478 LoC. Phase 5 `tool_selection_metric` + `CrossToolRegressionChecker` preserved. Phase 13 adds `_NORMALIZATION_RULE = "strip_plus_coerce"` (matches 13-01 inspection output), `_coerce_scalar`, `_normalize_param_value`, `_parse_selected_params_json`, `_param_match_score`, `joint_tool_param_metric`, `joint_tool_param_metric_with_feedback` (returns `dspy.Prediction`, not bare dict — B2 fix), `persist_per_tool_rates`. |
| `evolution/tools/tool_constraints.py` | ParamConsistencyChecker w/ inverted polarity | VERIFIED | 308 LoC. `ToolFactualChecker` preserved unchanged. New `ParamConsistencyChecker` with `is_consistent: bool` OutputField (D-11 polarity inversion); fail-closed via `_parse_bool` returning False on ambiguous input; per-tool batch via `check_all(evolved_tools, frozen_tool_descs)`. |
| `evolution/core/cost_tracker.py` | CostTracker context manager | VERIFIED | 323 LoC. `CostTracker.__enter__` warns on `dspy.settings.track_usage=False` (W4); `poll()` accumulates real UsageTracker output + injected usage; `exceeded()` strict > comparison; `write_aborted_json` supports both `extra=` and kwargs forms. `CostBudgetExceeded` exception class. `estimate_cost_usd` helper using `litellm.cost_per_token` with hand-rolled fallback. |
| `evolution/tools/v1_baseline_gate.py` | V1BaselineGate + dual-source baseline | VERIFIED | 322 LoC. `compute_v1_baseline` resolves historical (`metrics.json` evolved_score, type+range guarded) → inline (joint_tool_param_metric on holdout) → 'missing'. `check_v1_baseline_gate` returns `ConstraintResult` (D-14: `passed=False` when evolved < baseline - tolerance). `V1BaselineGate.check()` merges baseline_info + gate metrics into a single dict for CLI. No `write_back` import (scope guard). |
| `evolution/tools/evolve_tool_params.py` | End-to-end Click CLI | VERIFIED | 991 LoC. 14 Click flags (verified via `--help`); pipeline: discover → filter → ToolModule → load dataset → configure LM (track_usage=True) → GEPA compile inside CostTracker w/ `_CostStopper(stop_callbacks)` adapter → constraint chain (size→non_empty→factual→ParamConsistencyChecker) → holdout dual-pair eval (D-18) → CrossToolRegressionChecker + persist_per_tool_rates → V1BaselineGate → metrics.json/evolved_descriptions.json/diff.txt. Loud GEPA failure default (D-15a); MIPROv2 fallback opt-in via `--allow-miprov2-fallback`. NO `write_back` references. |
| `evolution/core/config.py` | EvolutionConfig with max_cost_usd + reflection_model | VERIFIED | New fields: `max_cost_usd: float = 20.0` (line 59), `reflection_model: Optional[str] = None` (line 45). Layered resolution: defaults → YAML → `EVOLUTION_MAX_COST_USD`/`EVOLUTION_REFLECTION_MODEL` env → CLI overrides. Existing 24 config tests + 5 new (Phase 13) tests all GREEN. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `ToolModule.__init__` | `_ToolParamBundle` | `dspy.Module` recursion via `named_parameters()` | WIRED | `tool_module.py:117-124` instantiates one `_ToolParamBundle` per tool; smoke confirms named_predictors lists per-param entries. |
| `ToolModule.forward` | `_frozen_tool_desc[name]` | `_format_available_tools` reads from frozen dict | WIRED | `tool_module.py:147-158` reads tool-level text from `self._frozen_tool_desc[name]`, not from any Predict — confirms physical isolation. |
| `joint_tool_param_metric` | `json.loads(prediction.selected_params)` | `_parse_selected_params_json` try/except → None on malformed | WIRED | `tool_metric.py:273-298` wraps `json.loads` in try/except (json.JSONDecodeError, TypeError, ValueError); malformed → None → `_param_match_score` returns 0.0. |
| `joint_tool_param_metric_with_feedback` | `dspy.Prediction(score=..., feedback=...)` | direct construction | WIRED | `tool_metric.py:436` returns `dspy.Prediction(score=float(score), feedback=" ".join(fb_parts))`. B2 attribute-access contract verified. |
| `ParamConsistencyChecker.check` | `_parse_bool(result.is_consistent)` | conservative bool parsing fail-closed | WIRED | `tool_constraints.py:266` uses `_parse_bool` on `is_consistent` output. Polarity inversion verified — ambiguous → False → passed=False. |
| `evolve_tool_params.evolve` | `CostTracker(max_usd=config.max_cost_usd)` | `with tracker:` wraps GEPA compile | PARTIAL | `evolve_tool_params.py:681-712` correctly enters CostTracker around `optimizer.compile`. **WARNING (BL-01):** `tracker.poll()` is called at lines 746, 774, 919 — all AFTER `with tracker:` exits. `CostTracker.__exit__` clears `self._tracker = None`; subsequent `poll()` reads from `_injected_usage` (empty in production) and falls back to the previously-cached `spent_usd` from in-block stop_callback polls. If the stop_callback never polls (e.g., budget never approached), `cost_usd_spent` in metrics.json may report 0.0. |
| `evolve_tool_params.evolve` | `joint_tool_param_metric_with_feedback` (training) + `joint_tool_param_metric` (holdout) | two-metric split | WIRED | `evolve_tool_params.py:694` (feedback for GEPA), `_evaluate_holdout` line 327 (bare for scoring). Pitfall 7 mitigation in place. |
| `evolve_tool_params.evolve` | `ParamConsistencyChecker.check_all` | constraint chain step 11c | WIRED | `evolve_tool_params.py:829-833` invokes per-tool batch with `frozen_tool_descs=baseline_module._frozen_tool_desc`. Failures counted into `metrics["param_consistency_failures"]`. |
| `evolve_tool_params.evolve` | `V1BaselineGate.check` | step 14, after holdout eval | WIRED | `evolve_tool_params.py:892-914` resolves baseline (historical/inline/missing), runs `gate.check()`, branches to FAILED_<ts>/ on failure. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `evolve_tool_params.evolve` (success path) | `metrics["per_tool_baseline_rates"]`, `metrics["per_tool_evolved_rates"]` | `CrossToolRegressionChecker.compute_per_tool_rates(holdout_pairs)` | Yes — derived from real holdout predictions | FLOWING |
| `evolve_tool_params.evolve` | `metrics["param_predictors_discovered"]` | `len(list(baseline_module.named_predictors()))` | Yes — counts actual Predict objects | FLOWING |
| `evolve_tool_params.evolve` | `metrics["evolved_score"]` | `_evaluate_holdout(optimized_module, holdout, lm)` mean joint metric | Yes — real LM calls + scoring | FLOWING |
| `evolve_tool_params.evolve` | `metrics["cost_usd_spent"]` | `tracker.poll()` AFTER `with tracker:` exits | UNCERTAIN — see BL-01 | STATIC (potentially) |
| `evolve_tool_params.evolve` | `metrics["v1_baseline_holdout"]` + `v1_baseline_source` | `V1BaselineGate.resolve` reading historical metrics.json or inline scoring | Yes | FLOWING |
| `evolve_tool_params.evolve` (FAILED path) | `constraint_failures[]` tool field | `getattr(r, "constraint_name", "factual_accuracy")` | No — produces "factual_accuracy" string instead of tool name | HOLLOW_FIELD (BL-02) |
| `evolve_tool_params.evolve` (FAILED path) | `constraint_failures[]` tool field for consistency failures | hardcoded `None` | No — tool name available in `r.message` but not extracted | HOLLOW_FIELD (BL-02) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full pytest suite | `.venv/bin/python -m pytest tests/ -q` | 385 passed, 1 xfailed (W5 deferred), 3 RuntimeWarnings (intentional W4 track_usage warnings) | PASS |
| CLI help shows all 14 flags | `python -m evolution.tools.evolve_tool_params --help` | Exit 0; --iterations, --eval-source, --hermes-repo, --dry-run, --model, --api-base, --tools, --max-cost-usd, --reflection-model, --param-group-size, --baseline-run, --allow-miprov2-fallback, --component-selector, --auto, --help all present | PASS |
| ToolModule per-param discovery | Live import + smoke construction | 3 per-param `tools['<tool>'].param_predictors['<param>']` entries discovered for 3-param fixture | PASS |
| Tool-level description frozen | Smoke check `_frozen_tool_desc` membership in named_predictors | 0 frozen-desc entries; isinstance dict[str,str] confirmed | PASS |
| 200-char param size enforcement | `ConstraintValidator._check_size('a'*201, 'param_description')` | passed=False, message="Size exceeded: 201/200 chars (1 over)" | PASS |
| 200-char param size acceptance | `ConstraintValidator._check_size('a'*200, 'param_description')` | passed=True | PASS |
| GEPA loud-fail default behavior | Wave 0 test patches GEPA.compile to raise; default flag | Test passes — but via empty-tools shortcut (BL-03), not actual GEPA code path | PARTIAL |
| MIPROv2 opt-in fallback | Wave 0 test second invocation with `--allow-miprov2-fallback` | metrics.json `optimizer_used="miprov2"` after fallback | PASS |
| Live --dry-run integration | Requires HERMES_AGENT_REPO; not run in verifier | Skipped — routed to human verification | SKIP |
| Live GEPA run with real LM | Requires API key + spend | Skipped — routed to human verification | SKIP |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TOOL-V2-02 | 13-01 through 13-08 (all 8 plans) | Per-parameter description optimization (not just top-level) | SATISFIED | All 3 ROADMAP Success Criteria verified above. ToolModule exposes per-param Predicts (SC1), tool-level frozen (SC2), 200-char size gate enforced (SC3). REQUIREMENTS.md mapping `TOOL-V2-02 | Phase 13 | Complete` is consistent with verified evidence. |

No orphaned requirements detected — REQUIREMENTS.md maps only TOOL-V2-02 to Phase 13 and all 8 plans declare it.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `evolution/tools/evolve_tool_params.py` | 774, 919 | `tracker.poll()` invoked AFTER `with tracker:` exits | WARNING (advisory) | BL-01: cost telemetry can report stale or 0.0 spent_usd in metrics.json on the success path. Does not break SC1/SC2/SC3 but compromises cost-cap audit trail (D-13) and downstream Phase 16 dashboard inputs. |
| `evolution/tools/evolve_tool_params.py` | 821, 839 | `constraint_failures` tool field set to `getattr(r, "constraint_name", "factual_accuracy")` and `None` instead of tool name | WARNING (advisory) | BL-02: every factual-accuracy failure logs as `tool="factual_accuracy"`, every consistency failure logs as `tool=None`. Downstream Phase 16 triage cannot identify which tool failed. Does not affect SC1/SC2/SC3. |
| `tests/tools/test_evolve_tool_params_cli.py` | 11-44 | `test_loud_gepa_failure_and_opt_in` patches `_load_tool_descriptions=[]` causing CLI to short-circuit before GEPA invocation | WARNING (advisory) | BL-03: D-15a loud-fail-vs-opt-in branching at evolve_tool_params.py:727-743 is **never exercised by the test that claims to test it**. Test passes via the empty-tools `return 1` path on line 614-628. Coverage claim in 13-08-SUMMARY.md is misleading; the actual D-15a behavior is unverified. |
| `evolution/tools/evolve_tool_params.py` | 323-326, `evolution/tools/v1_baseline_gate.py` | 170-175 | bare `except Exception` retry pattern in holdout scoring | WARNING (advisory) | BL-04: real LM errors (timeout, rate limit, malformed completion) are caught and silently retried with the same `task_description`, doubling LM cost on failure and re-raising the same error. Does not affect SC1/SC2/SC3 but degrades operational diagnostics. |
| `evolution/core/cost_tracker.py` | 130-131, 238-242 | `exceeded()` short-circuits on `max_usd <= 0` without polling, contradicting docstring claim "still polls" | WARNING (low) | WR-01: documentation drift. Operationally fine — disabled enforcement is rarely used. |
| `evolution/core/config.py` | 124-127, 147-150, 169-172 | Silent `pass` on `max_cost_usd` parse failure | WARNING (low) | WR-02: typo'd YAML or env var silently uses default. Users not informed. |
| `evolution/tools/evolve_tool_params.py` | 782-784 | metrics["tools_filter"] re-parses raw `--tools` string without filtering empties; `_filter_tools` uses cleaned list | WARNING (low) | WR-03: minor data-quality inconsistency in metrics.json. |
| `evolution/tools/v1_baseline_gate.py` | 137-144, 162-183 | `_NullCtx` + bare-except retry — failed inline baseline can return 0.0 silently making gate trivially pass | WARNING (low) | WR-09: degrades v1 gate safety guarantee silently. |

**Severity classification rationale:** All 4 BLOCKER findings from `13-REVIEW.md` are categorized here as WARNING (advisory) per the user's framing in this verification request: "they don't auto-fail goal achievement, since they're advisory; flag them as risks for review." None of them prevent SC1/SC2/SC3 from being verified. They are real defects that will affect operational quality (cost telemetry accuracy, FAILED triage, test honesty, error resilience) but not the phase goal.

### Phase 13 → later-phase deferrals (informational)

The following items were explicitly deferred to later phases and are NOT gaps:

- `--param-group-size` is a visible NO-OP knob — deferred to Phase 14 per CONTEXT D-15
- W5 poll-side empty-usage detection — scaffolded as `xfail` in `tests/core/test_cost_tracker.py::test_poll_side_empty_usage_warning` for later closure
- Per-tool dashboard / distribution visualization — Phase 16 (TOOL-V2-04)
- Joint top-level + per-param simultaneous optimization — Phase 17
- Write-back to hermes-agent — Phase 22 (continuous evolution loop)
- SessionDB-driven param scenario augmentation — Phase 14

### Human Verification Required

See `human_verification` block in frontmatter. Four items routed to human:

1. **Live --dry-run smoke against real hermes-agent**: Requires `HERMES_AGENT_REPO` set; verifies the integration path between config discovery, `tool_loader.discover_tool_files`, `tool_loader.extract_tool_descriptions`, and ToolModule construction.

2. **Disposition of the 4 REVIEW BLOCKER findings (BL-01 through BL-04)**: User must decide fix-now vs defer-to-Phase-14. Verifier flagged them as advisory per the task framing but recommends the user read `13-REVIEW.md` and pick a path forward before next phase begins. BL-01 is the most urgent (silent metrics corruption); BL-03 is a test-honesty issue (claimed coverage doesn't exist).

3. **Real GEPA optimization run on hermes-agent**: Verifies the per-param optimization actually improves `evolved_score` vs. `baseline_score` — not just compiles. Requires LLM API spend ($1-10).

4. **Inspect cost_usd_spent value on a real run** (BL-01 confirmation): Confirms whether the post-exit `tracker.poll()` actually returns 0.0 in production (theoretical) or just stale-but-nonzero (less severe).

### Gaps Summary

**No gaps blocking goal achievement.** All three ROADMAP Success Criteria are verified by direct evidence in code + GREEN unit tests + live smoke. TOOL-V2-02 traces cleanly through the implementation. The CLI `python -m evolution.tools.evolve_tool_params` is a functioning entry point with all 14 declared flags. 385 unit tests pass + 1 deliberately xfail (W5).

**Risks flagged for human review** (advisory, not goal-blocking):

- **BL-01**: cost telemetry reads stale/zero spend on success path → metrics.json `cost_usd_spent` may underreport actual API spend. Affects audit trail (D-13) and Phase 16 dashboard inputs but not SC1/SC2/SC3.
- **BL-02**: constraint-failure records lose tool identity (always "factual_accuracy" or None) → FAILED_<ts>/metrics.json triage degraded. Phase 16 dashboard cannot identify which tool failed.
- **BL-03**: Wave 0 test `test_loud_gepa_failure_and_opt_in` claims to test D-15a loud-fail-vs-opt-in branching but actually exercises the empty-tools shortcut → D-15a behavior is unverified despite test PASS. Coverage gap, not behavior gap.
- **BL-04**: bare `except Exception` retry in holdout scoring + v1_baseline_gate scoring → real LM errors are silently retried with identical input, doubling cost on failure, then re-raised uncaught. Operational hardening issue.

These 4 issues are flagged in `13-REVIEW.md` and should be resolved before Phase 14 begins to prevent compound risk in continuous-evolution scenarios. The user's task framing accepted them as "Phase 14 hygiene" candidates — the verifier surfaces them for explicit disposition rather than silently passing.

---

_Verified: 2026-05-08_
_Verifier: Claude (gsd-verifier)_
