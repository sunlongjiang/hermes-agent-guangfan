---
created: 2026-05-16T02:55:00Z
title: Resume Phase 18 calibration (paused at Plan 18-03 Task 2)
area: prompts / drift-detection
resolves_phase: 18
files:
  - evolution/prompts/drift_calibration.py:141
  - evolution.yaml
  - datasets/prompts/drift_calibration.jsonl
  - datasets/prompts/drift_thresholds.json
---

## Problem

Phase 18 (Personality Drift Detection) is paused at Plan 18-03 Task 2 — the live LLM-driven calibration run could not clear Tier 1/2 due to two compounding blockers documented in `.planning/phases/18-personality-drift-detection/18-03-SUMMARY.md`:

1. **Zero persona coverage (Wave 1 design defect):** `DriftCalibrationBuilder.DRIFT_TARGET_DIMS_PER_SECTION` hardcodes 3 dims (tone/formality/vocabulary), so the generated JSONL has no persona-positive examples → persona F1 is structurally 0.0 regardless of judge.
2. **Same-family bias collapse (RA5 violation by config):** `evolution.yaml` sets `eval` and `judge` to the same DashScope model (`qwen-plus`). qwen-max as detector marginally helps (macro 0.379 → 0.418, still Tier 3). OpenAI gpt-4.1-mini judge is RA5-correct but currently blocked by API quota.

Plans 18-04 (drift-gate wiring) and 18-05 (CLI integration tests) are blocked on real `datasets/prompts/drift_thresholds.json`.

## Solution

1. **Patch the generator (Wave 1)** to cover all 4 dims. Two options:
   - Change `DRIFT_TARGET_DIMS_PER_SECTION` to all 4 dims AND rebalance the no-drift count: e.g., 4 drift + 2 no-drift per section × 5 sections = 30 examples (preserves D-CAL-03 count, splits drift 20/30 + no-drift 10/30). Update tests accordingly.
   - OR keep the 3 drift + 3 no-drift pattern per section but rotate which 3 dims are sampled across sections, so persona gets coverage from some sections. Less symmetric but preserves the 15/15 drift split.
2. **Provision a non-qwen judge** for the detector side. Top up OpenAI credits and use `--eval-model openai/gpt-4.1-mini`, or wire a different provider (Anthropic Claude, OpenRouter routed to a non-qwen model).
3. **Re-run** with full generation (no `--reuse-jsonl` — persona coverage must come from a fresh generator pass):
   ```bash
   python -m evolution.prompts.build_drift_calibration --seed 42 \
     --eval-model openai/gpt-4.1-mini \
     # OR: --eval-model anthropic/claude-haiku-4-5 --eval-api-base https://api.anthropic.com/v1 --eval-api-key $ANTHROPIC_API_KEY
   ```
4. **Spot-check ≥ 8/10** rows for plausibility (RA5 Mitigation 2) before committing.
5. **Commit** `datasets/prompts/drift_calibration.jsonl` + `datasets/prompts/drift_thresholds.json` (`.gitignore` exception from Plan 18-01 already allows this).
6. **Resume:** `/gsd-execute-phase 18` — Plans 18-01, 18-02, and Task 1 of 18-03 are SUMMARY-marked and will be skipped; Task 2 of 18-03 + Plans 18-04 / 18-05 will run.

**Priority:** MED — blocks Phase 18 completion (PMPT-V2-02). Does not block downstream phases (19-22 depend on Phase 17 or Phase 16, not 18).

**Cost estimate when resumed:** $0.50–2 generator (qwen-plus on DashScope) + $0.05–0.20 detector (gpt-4.1-mini for ~60 calls).

**Related artifacts:**
- Plan: `.planning/phases/18-personality-drift-detection/18-03-PLAN.md`
- Summary (paused): `.planning/phases/18-personality-drift-detection/18-03-SUMMARY.md`
- CLI module: `evolution/prompts/build_drift_calibration.py` (already supports `--eval-model` / `--eval-api-base` / `--eval-api-key`)
- Generator defect: `evolution/prompts/drift_calibration.py:141`
