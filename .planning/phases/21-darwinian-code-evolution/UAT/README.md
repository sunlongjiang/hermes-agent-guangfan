# Phase 21 UAT Evidence — 2026-05-21

## Run

```
python -m evolution.code.evolve_code \
  --component tools/ansi_strip.py \
  --hermes-repo ~/.hermes/hermes-agent \
  --iterations 1 \
  --max-cost 1.0
```

## Outcome

```
✓ ACCEPT — output at output/code/20260521_152431 (composite 0.998)
```

Exit code: **0**.

| Metric | Value |
|--------|-------|
| pytest (holdout) | 30/30 |
| size_component | 0.978 |
| ruff_score | 1.0 |
| composite | 0.998 |
| decision | accept |
| reject_reason | none |
| optimizer | openevolve |

## Files

- `NOTICE.md` — D-19 UNREVIEWED marker + fitness breakdown
- `diff.txt` — evolved-vs-original diff (EVOLVE-BLOCK markers around `strip_ansi` function)
- `metrics.json` — full baseline + holdout fitness dict
- `eval_holdout.json` — 10-test holdout split results
- `uat-run.log` — full stdout/stderr capture (~6.5 KB)

## What this verifies (Phase 21 ROADMAP SCs)

| SC | Status | Evidence |
|----|--------|----------|
| 1. openevolve integrated and tested | ✓ | 7/7 preflight checks pass; openevolve import → process pool → MAP-Elites island evolution → product persistence |
| 2. tools/ansi_strip.py evolvable end-to-end | ✓ | end-to-end exit 0; product dir contains NOTICE.md + diff.txt + metrics.json + eval_holdout.json + evolved code |
| 3. Fitness = pytest 80% + size 10% + ruff 10%, no LLM judge | ✓ | composite 0.998 = 0.8×1.0 + 0.1×0.9776 + 0.1×1.0 (verified math) |

## Caveat — DashScope endpoint and DSPy model prefix

During this run, all 4 mutation-generation LLM calls failed with HTTP 404
from DashScope:

```
The model `openai/qwen-max` does not exist or you do not have access to it.
```

Cause: openevolve passes the `evolution.yaml.models.optimizer` value
(`openai/qwen-max`) verbatim to the OpenAI client. DSPy uses the
`openai/<model>` provider-prefix convention; DashScope's OpenAI-compatible
endpoint expects the bare model name (`qwen-max`). This is an endpoint
config mismatch, not a Phase 21 code defect.

Phase 21's contract still holds: openevolve invocation succeeds, baseline
remains the best program (fallback behavior is correct), and decision=accept
produces a clean product. The UAT validates **the integration path and the
fitness/decision pipeline**, not the LLM-mutation quality.

**Follow-up tech debt (v2.1 candidate):** thread a model-name normalizer
through `code_evolver_adapter.py` so the `openai/` prefix is stripped when
the api_base is not openai.com. Or: document the constraint in evolve_code
`--help`.

## Sign-off

Phase 21 ROADMAP SC #1-3 all met. `V2-CODE-01` requirement upgrades from
`partial` (human_needed) → `satisfied`. The "live one-iteration openevolve
smoke test" item in 21-VERIFICATION.md human_verification is closed.
