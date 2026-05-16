---
phase: 18-personality-drift-detection
plan: 03
subsystem: prompts
tags: [drift-detection, calibration, llm-judge, dspy, click, dashscope, openai]

requires:
  - phase: 18-personality-drift-detection
    provides: "DriftDetector class, DriftCalibrationBuilder, derive_thresholds (Wave 1 / Plan 18-02)"
provides:
  - "build_drift_calibration.py CLI orchestrating extract → generate → derive → persist"
  - "Per-side --eval-model / --eval-api-base / --eval-api-key flags decoupling detector from generator (RA5 enforcement at CLI level)"
  - "--reuse-jsonl flag for iterating on judge without regenerating examples"
  - "Diagnosed two compounding blockers on the live calibration path (documented for next attempt)"
affects: ["Plan 18-04 (drift-gate wiring) — BLOCKED on real drift_thresholds.json", "Plan 18-05 (CLI integration tests) — BLOCKED on Plan 18-04"]

tech-stack:
  added: []
  patterns:
    - "dataclasses.replace for per-side config divergence inside CLI orchestrators (avoid mutating shared EvolutionConfig fields)"
    - "Per-side LM endpoint heuristic gated on model-family prefix (gpt-/o1-/chatgpt- vs vendor-specific openai/<name>)"

key-files:
  created:
    - "evolution/prompts/build_drift_calibration.py"
  modified: []

key-decisions:
  - "Phase 18 paused at Plan 18-03 Task 2 — live calibration deferred until two blockers are resolved (zero-persona JSONL coverage + same-family bias)"
  - "Untracked Tier-3 JSONL (datasets/prompts/drift_calibration.jsonl) discarded — not committed because persona coverage is structurally absent"
  - "CLI Task 1 (build_drift_calibration.py) shipped + improved with per-side overrides — these land regardless of pause"

patterns-established:
  - "Two-config CLI pattern: shared EvolutionConfig.load() + dataclasses.replace clone with per-side mutations for generator vs detector"
  - "Banner-level RA5 violation detection: stdout shows generator + detector model+base on separate lines with explicit RA5 OK/VIOLATION tag"
  - "--reuse-jsonl as universal iteration accelerator for any 'expensive-data + cheap-compute' calibration pipeline"

requirements-completed: []
# PMPT-V2-02 remains OPEN. Plan 18-03 partially complete (Task 1 shipped; Task 2 paused).
# Plans 18-04 and 18-05 are still required to close PMPT-V2-02.

duration: ~75 min (including failed live-run diagnosis cycles)
completed: 2026-05-16
status: paused
---

# Plan 18-03 Summary

**build_drift_calibration CLI shipped + per-side override patch landed; live calibration paused due to zero-persona JSONL coverage and same-family bias.**

## Performance

- **Duration:** ~75 min (Task 1 + 3 failed live-run diagnosis cycles + deferral writeup)
- **Started:** 2026-05-15T13:54:00Z (~)
- **Completed:** 2026-05-16T02:55:00Z (~)
- **Tasks:** 1/2 (Task 1 ✓, Task 2 paused)
- **Files modified:** 1 (`evolution/prompts/build_drift_calibration.py`)

## Accomplishments

- **Task 1 shipped** — `evolution/prompts/build_drift_calibration.py` (292 LoC) orchestrating extract → generate → derive → persist with Rich F1 self-eval table and Tier 1/2/3 classification.
- **CLI improvement patch shipped** — Added `--reuse-jsonl`, `--eval-model`, `--eval-api-base`, `--eval-api-key` flags so the detector can run on a different model + backend from the generator without editing `evolution.yaml`. Banner now shows generator/detector on separate lines with an explicit `RA5 OK` / `RA5 VIOLATION` tag.
- **Diagnosed two compounding blockers** preventing live calibration from clearing Tier 1/2:
  1. Wave 1 generator omits `persona` from `DRIFT_TARGET_DIMS_PER_SECTION` → JSONL has zero persona-positive examples → persona F1 is structurally 0.0 regardless of judge.
  2. `evolution.yaml` configures `eval` and `judge` to the same DashScope model (`qwen-plus`) → same-family bias collapse (RA5 violation by config). qwen-max-as-judge improves marginally (macro 0.379 → 0.418) but stays in Tier 3.

## Task Commits

1. **Task 1: Create build_drift_calibration.py** — `4251d72` (feat: Click CLI orchestrating extract → generate → derive → persist)
2. **CLI improvement: per-side override flags** — `23d67b1` (feat: --reuse-jsonl + per-side eval-model/api-base/api-key overrides)
3. **Task 2: Live calibration run** — PAUSED (no commit)

## Files Created/Modified

- `evolution/prompts/build_drift_calibration.py` — Click CLI with 11 flags, two-config pattern (generator config + detector config), Rich F1 self-eval table, Tier 1/2/3 classification with stdout color coding.

## Decisions Made

- **D-CAL-05 partial closure (Task 1 only):** CLI exists and is invocable. Live data assets (`datasets/prompts/drift_calibration.jsonl`, `drift_thresholds.json`) NOT yet materialized — explicit deferral, not a silent skip.
- **Untracked JSONL discarded:** The Tier-3 calibration JSONL (39 KB, 30 rows) was untracked because persona coverage is structurally absent. Keeping it on disk would risk a future "just commit what we have" shortcut that bakes in the design defect. Regenerate from scratch after blockers are resolved.
- **Two-config CLI pattern over EvolutionConfig.load() patching:** Instead of adding eval-model overrides to the shared config loader, the CLI clones config via `dataclasses.replace` for per-side mutations. Keeps `EvolutionConfig.load()` API stable.
- **Model-family prefix heuristic for OpenAI auto-routing:** Initial patch reset `api_base` to None for any `openai/` prefix, breaking DashScope-via-openai-adapter calls (qwen-max went to `api.openai.com` and 404'd). Tightened to only `^openai/(gpt-|o1-|chatgpt-)` for auto-routing — vendor-specific `openai/qwen-*` keeps the inherited DashScope base.

## Deviations from Plan

### Plan 18-03 Task 2 NOT completed (intentional pause)

The plan declared Task 2 as `checkpoint:human-action` requiring user-owned LLM credits + human spot-check ≥8/10. During execution, two technical blockers surfaced that prevent the live run from clearing Tier 1/2 even with successful credit + spot-check execution:

**Blocker 1: Zero persona examples in calibration JSONL (Wave 1 design defect)**
- `evolution/prompts/drift_calibration.py:141` hardcodes `DRIFT_TARGET_DIMS_PER_SECTION = ("tone", "formality", "vocabulary")` — persona deliberately omitted.
- Each section gets 3 drift variants (one per non-persona dim) + 3 no-drift = 6 variants × 5 sections = 30 examples.
- D-CAL-04 says `drift_dim ∈ {tone, formality, vocabulary, persona, none}`, and DriftDetector has 4 scoring OutputFields including persona. The calibration set fails to cover one of the four dims → F1 derivation for persona always yields 0 positives → F1 = 0.0.
- **Fix scope:** Wave 1 patch — extend generator to all 4 dims (e.g. 4 drift + 2 no-drift per section, still 6 variants × 5 sections = 30 total). This requires regenerating the JSONL.

**Blocker 2: Same-family bias even after RA5 separation**
- User's `evolution.yaml` configures `models.eval: openai/qwen-plus` AND `models.judge: openai/qwen-plus` — RA5's same-model-bias mitigation is defeated by config.
- Even after CLI patch decoupled the detector model (qwen-max via DashScope), macro F1 only rose 0.379 → 0.418 (still Tier 3, well below the 0.80 floor). Tone 0.60, formality 0.50, vocabulary 0.57.
- Tried OpenAI gpt-4.1-mini as judge (RA5-correct cross-family): blocked by **API quota** on the available `OPENAI_API_KEY` (HTTP 429 `insufficient_quota`).
- **Fix scope:** Provide a meaningfully different judge model — OpenAI w/ credits, Anthropic Claude, OpenRouter routed to non-qwen, or DashScope's `qwen-max-latest` if it shows materially different behavior.

### Security incident (informational, separately tracked)

During the environment check in Wave 2, the orchestrator's bash one-liner mis-used `${VAR:-NO}` semantics and printed the full `OPENAI_API_KEY` (sk-proj-…) to the terminal output. The user was advised to rotate the key. **Action item:** rotate the leaked key on platform.openai.com.

### Pre-existing housekeeping note (not from Phase 18)

stdout warning from `EvolutionConfig.load()`: `evolution.yaml contains a literal API key`. This is the Phase 12 known concern (todo: `2026-05-07-evolution-yaml-literal-key` if exists), not introduced by Phase 18.

## Issues Encountered

1. **First live run (seed=42, qwen-plus generator + qwen-plus detector):** Tier 3 FAIL, macro 0.379. Root cause: same-model bias collapse. Tier-3-blocked CLI ClickException prevented thresholds.json from being written.
2. **Second live run (--reuse-jsonl --eval-model openai/gpt-4.1-mini):** OpenAI quota exhausted, HTTP 429 `insufficient_quota`.
3. **Third live run (--reuse-jsonl --eval-model openai/qwen-max via DashScope):** First attempt routed to api.openai.com (CLI heuristic bug — auto-cleared api_base on `openai/` prefix), 404 NotFound. Patched heuristic to only auto-route OpenAI-hosted families (gpt-/o1-/chatgpt-). Retry succeeded against DashScope, Tier 3 FAIL persists, macro 0.418.

## User Setup Required

- **Rotate leaked `OPENAI_API_KEY`** — accidentally printed in terminal output during environment check.
- **Top up OpenAI credits OR provision a non-qwen judge** — required for resuming Plan 18-03 Task 2.
- **Set `HERMES_AGENT_REPO`** env var to be explicit (currently falls back to `~/.hermes/hermes-agent` which works but is implicit).

## Next Phase Readiness

**Phase 18 is NOT ready to advance.** Plans 18-04 (drift-gate wiring) and 18-05 (CLI integration tests) require `datasets/prompts/drift_thresholds.json` to exist with all 4 dims thresholded and a Tier 1/2 `_meta.f1_tier`. Until both blockers are resolved, Plans 18-04/18-05 cannot run.

**Resume protocol** (when ready):
1. Patch `evolution/prompts/drift_calibration.py:141` to include all 4 dims (e.g., 4 drift + 2 no-drift per section, OR extend total to 40 examples × 5 sections + adjust D-CAL-03).
2. Acquire access to a non-qwen judge family — OpenAI with credits, Anthropic Claude, OpenRouter routed to a non-qwen model, or similar.
3. Re-run: `python -m evolution.prompts.build_drift_calibration --seed 42 --eval-model <non-qwen-model> [--eval-api-base ...] [--eval-api-key ...]` (no `--reuse-jsonl` — fresh generation needed for persona coverage).
4. Spot-check 10/30 rows for plausibility (RA5 Mitigation 2).
5. Commit both artifacts: `git add datasets/prompts/drift_calibration.jsonl datasets/prompts/drift_thresholds.json && git commit`.
6. Resume Phase 18 with `/gsd-execute-phase 18` — Plans 18-01, 18-02, and Task 1 of 18-03 already have SUMMARY.md and will be skipped automatically; the orchestrator will pick up Task 2 of 18-03 and continue through Plans 18-04/18-05.

**Pending todo:** `.planning/todos/pending/2026-05-16-resume-phase-18-calibration.md` (created alongside this summary).

---
*Phase: 18-personality-drift-detection*
*Plan: 03 (Task 1 complete, Task 2 paused — deferred until calibration blockers resolved)*
*Status: paused*
*Updated: 2026-05-16*
