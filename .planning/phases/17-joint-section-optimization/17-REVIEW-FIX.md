---
phase: 17-joint-section-optimization
fixed_at: 2026-05-15T08:55:00Z
review_path: .planning/phases/17-joint-section-optimization/17-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 17: Code Review Fix Report

**Fixed at:** 2026-05-15T08:55:00Z
**Source review:** .planning/phases/17-joint-section-optimization/17-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (2 BLOCKER + 7 WARNING; 4 INFO out of scope)
- Fixed: 9
- Skipped: 0
- Full test suite after all fixes: 513 passed, 1 skipped, 1 xfailed (zero regression vs Phase 17 landing baseline)

## Fixed Issues

### CR-01: A/B baseline branch mirrors main RR GEPA->MIPROv2 fallback

**Files modified:** `evolution/prompts/evolve_prompt_sections.py`
**Commit:** 604163c
**Applied fix:** Wrapped the A/B baseline's `dspy.GEPA(...).compile(...)` block in the same nested `try / except → MIPROv2 fallback → except → skip` structure used by the main round-robin branch (lines ~405-438). Without this, a transient GEPA failure (dspy version skew, network hiccup, rate limit) leaves the A/B baseline UNoptimized while joint optimization succeeds, turning the soft-gate comparison from "joint vs round-robin" into "joint vs raw text" and producing false-positive soft-gate triggers. This restores D-AB-04 "1:1 strict comparability". (Decision: chose review's option A — give A/B the same fallback as main RR — rather than option B (strip MIPROv2 from main RR). Option A preserves the existing main-path behavior unchanged; option B would have widened blast radius into Phase 8 legacy semantics.)

### CR-02: epsilon_pp unit consistency — store as percentage points

**Files modified:** `evolution/prompts/evolve_prompt_sections.py`, `tests/prompts/test_evolve_prompt_sections_cli.py`
**Commit:** c03d790
**Applied fix:** Changed `EPSILON_PP = 0.01` (score-space) to `EPSILON_PP = 1.0` (true percentage points), then divided by 100 at the internal score-space comparison site. Added a module-top docstring documenting the `_pp`-suffix convention. Updated the warning text format string from `EPSILON_PP * 100` to `EPSILON_PP` directly. Test assertion at `test_evolve_prompt_sections_cli.py:494` updated to `metrics["epsilon_pp"] == 1.0`. Sibling field `joint_vs_roundrobin_delta_pp` was already in pp, so the two `_pp` fields are now unit-consistent and can be safely compared without 100x rescaling.

### WR-01: Hoist baseline set_active_section out of holdout loop

**Files modified:** `evolution/prompts/evolve_prompt_sections.py`
**Commit:** bca385a
**Applied fix:** Replaced the per-example `for sid in baseline_module._section_ids: set_active_section(sid); break` pattern with a one-time pre-loop activation: `if holdout_examples and baseline_module._section_ids: baseline_module.set_active_section(baseline_module._section_ids[0])`. The empty-holdout guard preserves existing test expectations on `set_active_section.call_count` (which assume zero activations when holdout is empty in the CLI mock tests). Pitfall 1 fix already guarantees `_build_frozen_context` includes all sections regardless of which is active, so per-iteration reactivation was redundant.

### WR-02: Correct prompt_module docstring named_parameters -> named_predictors

**Files modified:** `evolution/prompts/prompt_module.py`
**Commit:** 5aa3b57
**Applied fix:** Updated module-top docstring, `PromptModule` class docstring, and `named_predictors` override docstring to reference `named_predictors()` (the method GEPA actually introspects) instead of `named_parameters()`. Added explicit note that frozen sections are `dict[str, str]` — plain strings, neither `dspy.Parameter` nor `dspy.Predict` — so they are invisible to BOTH discovery APIs by default with no override needed.

### WR-03: Remove dead num_predictors assignment in round-robin branch

**Files modified:** `evolution/prompts/evolve_prompt_sections.py`
**Commit:** 5647505
**Applied fix:** Removed `num_predictors = len(module._section_ids)` from the round-robin else-branch (it was never read on this path) and added a comment noting num_predictors is a joint-mode-only quantity.

### WR-04: Remove unused Panel and get_hermes_agent_path imports

**Files modified:** `evolution/prompts/evolve_prompt_sections.py`
**Commit:** 0b4bf84
**Applied fix:** Removed `from rich.panel import Panel` and dropped `get_hermes_agent_path` from `from evolution.core.config import EvolutionConfig, get_hermes_agent_path`. Neither was referenced anywhere in the file.

### WR-05: Snapshot section ids before loops that rebind the module

**Files modified:** `evolution/prompts/evolve_prompt_sections.py`
**Commit:** f7baf71
**Applied fix:** Two sites:
1. Main round-robin: `sections_to_optimize = list(module._section_ids)` instead of bare attribute reference, decoupling iteration from `module = optimizer.compile(...)` rebind semantics.
2. A/B baseline: introduced `ab_section_ids = list(ab_baseline_module._section_ids)` snapshot before `for ab_sid in ab_section_ids:`.

The IDs themselves are stable, so this is defensive — but it makes the invariant explicit and survives any future change in dspy.GEPA.compile's return contract (mutate-in-place vs deep-copy).

### WR-06: Document soft-gate strict-less-than + round scores for FP stability

**Files modified:** `evolution/prompts/evolve_prompt_sections.py`
**Commit:** 17e46f6
**Applied fix:** (1) Added comment explaining that `<` (strict less-than) is deliberate — a regression of exactly -EPSILON_PP is treated as within tolerance per Plan 17-03 soft-gate semantics ("warn when joint regresses by MORE THAN 1pp"). (2) Round both `evolved_score` and `roundrobin_baseline_score` to 4 decimal places before the gate comparison. 1e-4 is two orders of magnitude smaller than EPSILON_PP/100 = 0.01, so 4dp preserves semantic resolution while smoothing the IEEE-754 last-bit noise (e.g. `0.60 - 0.59 == 0.010000000000000009`).

### WR-07: Tag active section with [ACTIVE:sid]: to disambiguate selector view (requires human verification)

**Files modified:** `evolution/prompts/prompt_module.py`, `tests/prompts/test_prompt_module.py`
**Commit:** e5ac45d
**Applied fix:** Implemented review's option A (minimal change): in `_build_frozen_context`, tag the round-robin active section as `[ACTIVE:{sid}]:` instead of plain `[{sid}]:`. Joint mode keeps plain `[{sid}]:` for every section (all are jointly active, so no single one is "the" active). Frozen sections keep plain `[{sid}]:`. Tests updated:
- `test_frozen_context_includes_active`: assert `[ACTIVE:memory_guidance]:` in context AND plain `[memory_guidance]:` NOT in context (guards against tag duplication).
- `test_forward_in_round_robin_includes_active_text`: same tag swap.
- Joint-mode test `test_forward_in_joint_mode_uses_all_section_texts`: unchanged (joint mode does not tag).

**Why this needs human verification:** This changes the prompt string actually fed to the selector LLM, which affects GEPA reflection quality and downstream agent behavior. The review's option B (architectural refactor — add an explicit `active_section_text` input field to the selector signature) is a more thorough disambiguation but exceeds fixer scope. Option A is the minimal-change disambiguation; whether it materially improves GEPA's reflection signal needs an end-to-end run against a real eval set, not a unit test.

---

_Fixed: 2026-05-15T08:55:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
