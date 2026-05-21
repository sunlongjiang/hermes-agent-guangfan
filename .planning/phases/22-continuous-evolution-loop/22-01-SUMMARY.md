---
phase: 22-continuous-evolution-loop
plan: 01
status: complete
completed: 2026-05-21
key-files:
  created:
    - tests/test_deploy_mode_gate.py
  modified:
    - evolution/core/config.py
    - evolution/tools/tool_loader.py
    - evolution/prompts/prompt_loader.py
---

# Plan 22-01 Summary — deploy_mode gate (D-11 / CONCERNS §M6)

## Outcome

`EVOLUTION_DEPLOY_MODE=production` now hard-fails any in-place write back to
hermes-agent before file I/O happens. Phase 22 production CI (D-11) can rely on
the worker-level defense even if a downstream evolve_* CLI accidentally calls a
write-back. Phase 1-21 callers see zero behavior change because env var defaults
unset and `EvolutionConfig().deploy_mode` defaults `None`.

## Where the guards live

| File | Lines | Behavior |
|------|-------|----------|
| `evolution/core/config.py` | 47-51 | `deploy_mode: Optional[str] = None` dataclass field |
| `evolution/core/config.py` | 208-210 | yaml-load branch (`_expand_env` honored) |
| `evolution/core/config.py` | 283-286 | `EVOLUTION_DEPLOY_MODE` env-var override |
| `evolution/core/config.py` | 372-374 | CLI override (highest priority) |
| `evolution/tools/tool_loader.py` | 541-550 | `write_back_description` raises `PermissionError` before any read |
| `evolution/prompts/prompt_loader.py` | 175-185 | `write_back_section(dest=None)` raises; `dest != None` (Phase 20 Overlay) stays open |
| `tests/test_deploy_mode_gate.py` | 1-71 | 6-test coverage matrix |

## Decision: env-var-direct-read in loaders

The plan called for re-reading `EVOLUTION_DEPLOY_MODE` directly inside both
`write_back_description` and `write_back_section` rather than threading
`EvolutionConfig` through the loader signature. Rationale: adding a Config
parameter would ripple through every Phase 2-21 call site; the env-var read is
a 4-line zero-coupling check that matches CONTEXT.md D-11 intent verbatim
("workflow yaml 设 env: EVOLUTION_DEPLOY_MODE: production").

## Phase 20 Overlay compatibility

`write_back_section` only raises when `dest is None` (in-place write to
hermes-agent). When Phase 20's Virtual Prompt Overlay passes
`dest=~/.hermes/tmp/benchmark_<ts>/...`, the guard is skipped because that path
is never inside hermes-agent's source tree. Test
`test_production_allows_write_back_section_with_dest` regression-locks this.

## Verification

- 6/6 `tests/test_deploy_mode_gate.py` PASS
- Full suite: **729 passed, 2 skipped, 1 xfailed, 40 warnings in 53.45s** (no regression vs Phase 21 baseline of 723 passed; +6 deploy-mode tests, same skipped/xfailed counts)
- `grep -c "EVOLUTION_DEPLOY_MODE" evolution/core/config.py evolution/tools/tool_loader.py evolution/prompts/prompt_loader.py` = 1 each
- `grep -c "PermissionError" evolution/tools/tool_loader.py evolution/prompts/prompt_loader.py` = 1 each
- All 7 plan acceptance-criteria checks pass

## Commits

- `25f877d` test(22-01): add failing tests for D-11 deploy_mode gate (RED — 6 stubs)
- `adb565b` feat(22-01): implement D-11 deploy_mode gate (3-layer load + PermissionError guards) (GREEN)

## Unblocks

- 22-02 (Wave 2): `evolution.yaml loop:` schema extends `EvolutionConfig.deploy_mode` pattern; shares `_expand_env` yaml-load helper
- 22-05 (Wave 4): GH Actions workflow yaml sets `EVOLUTION_DEPLOY_MODE=production` knowing the guard now exists

## Self-Check: PASSED

All 7 plan acceptance-criteria checks pass. 6 unit tests pass. Zero regressions in 729-test suite.
