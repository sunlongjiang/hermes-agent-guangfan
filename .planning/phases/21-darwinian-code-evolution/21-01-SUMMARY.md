---
phase: 21-darwinian-code-evolution
plan: "01"
subsystem: infrastructure-bootstrap
tags:
  - phase-21
  - infrastructure
  - license
  - pyproject
  - pre-commit
  - bootstrap
dependency_graph:
  requires:
    - .gitignore (CONCERNS H4: output/ already ignored — pre-execution verified)
    - pyproject.toml (existing [project.optional-dependencies] section)
  provides:
    - LICENSE (MIT, D-17 irreversible)
    - pyproject.toml [code] extra (openevolve>=0.2.27)
    - pyproject.toml [dev] extra (ruff added)
    - pyproject.toml [tool.ruff] config (line-length=120, select=["E","F","W"])
    - .pre-commit-config.yaml (openevolve-single-import-surface hook — D-18 first layer)
  affects:
    - evolution/code/code_evolver_adapter.py (Wave 1, Plan 21-04: hook gates this file as the sole openevolve import surface)
    - evolution/code/ (Wave 1+: pip install .[code] resolves the openevolve dependency for all Plan 21 code-evolution work)
tech_stack:
  added:
    - "openevolve>=0.2.27 (Apache-2.0, declared via [code] extra)"
    - "ruff (linter, declared via [dev] extra + [tool.ruff] config block)"
    - "pre-commit (declared via .pre-commit-config.yaml; install separately as needed)"
  patterns:
    - "Optional extras for opt-in heavy deps ([code] mirrors prior [darwinian] slot)"
    - "Local pre-commit hook with grep gate + bash exit-code semantics (zero external repos)"
    - "MIT LICENSE at repo root (canonical OSS layout)"
key_files:
  created:
    - LICENSE
    - .pre-commit-config.yaml
  modified:
    - pyproject.toml
decisions:
  - "D-01/D-02 physically landed: [code] extra replaces [darwinian]; AGPL boundary permanently closed (openevolve is sole evolutionary code search lib for Phase 21)"
  - "D-13 physically landed: [dev] extra adds ruff + [tool.ruff] minimal config (line-length=120, select=E/F/W)"
  - "D-17 physically landed: MIT LICENSE with `Copyright (c) 2026 Longjiang Sun` — copyright holder confirmed via pre-resolved checkpoint (user explicitly chose English transliteration over Chinese name `龙江 孙` from git config); year 2026 confirmed"
  - "D-18 first layer physically landed: .pre-commit-config.yaml openevolve-single-import-surface local hook; passes vacuously today (no openevolve imports exist yet) — Plan 21-04 will create code_evolver_adapter.py, the only file the hook permits to import openevolve"
metrics:
  duration: "~3 min"
  completed: "2026-05-20"
  tasks_completed: 3
  tasks_total: 3
  files_created: 2
  files_modified: 1
---

# Phase 21 Plan 01: Infrastructure Bootstrap Summary

Phase 21 base infrastructure: replaced the broken `[darwinian]` extra (pointing to a non-existent PyPI package) with a working `[code]` extra (`openevolve>=0.2.27`), added ruff as a [dev] extra with a minimal `[tool.ruff]` config (D-13), introduced the repo's first `.pre-commit-config.yaml` containing a local grep-based hook that pins `import openevolve` / `from openevolve` to a single file (D-18 first layer), and committed a standard MIT LICENSE with copyright `2026 Longjiang Sun` (D-17 irreversible — checkpoint pre-resolved by user via orchestrator).

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Replace [darwinian] extra with [code] (openevolve) + add ruff to [dev] + add [tool.ruff] config | 678bf53 | pyproject.toml |
| 2 | Create .pre-commit-config.yaml with openevolve-single-import-surface local hook | 6352603 | .pre-commit-config.yaml |
| 3 | Create MIT LICENSE with `Copyright (c) 2026 Longjiang Sun` (checkpoint pre-resolved) | 468cf40 | LICENSE |

## Diff Stats

| File | Lines Added | Lines Removed |
|------|-------------|---------------|
| pyproject.toml | +7 | -2 |
| .pre-commit-config.yaml | +9 | 0 (new file) |
| LICENSE | +21 | 0 (new file) |

## Verification Results

All 6 verification commands from PLAN `<verification>` block pass:

| # | Check | Result |
|---|-------|--------|
| 1 | `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"` | TOML OK |
| 2 | `code` extra contains `openevolve>=0.2.27` AND `darwinian` extra absent | extras OK |
| 3 | `[tool.ruff]` has `line-length=120` AND `"E"` in `select` | ruff config OK |
| 4 | `grep "openevolve-single-import-surface" .pre-commit-config.yaml` | hook OK (1 line) |
| 5 | `grep "MIT License" LICENSE` | LICENSE OK (1 line) |
| 6 | `grep "^output/" .gitignore` | gitignore OK (1 line, pre-existing) |

Additional `<done>` criteria validated per task:

| Task | Criterion | Result |
|------|-----------|--------|
| 1 | `grep -c "openevolve>=0.2.27" pyproject.toml ≥ 1` | 1 ✓ |
| 1 | `grep -c "darwinian" pyproject.toml = 0` | 0 ✓ |
| 1 | `grep -c "ruff" pyproject.toml ≥ 2` (dev extra + [tool.ruff]) | 2 ✓ |
| 2 | `grep -c "always_run: true"` = 1 | 1 ✓ |
| 2 | `grep -c "pass_filenames: false"` = 1 | 1 ✓ |
| 2 | `grep -c "code_evolver_adapter.py"` = 1 | 1 ✓ |
| 2 | manual hook execution passes (no openevolve imports yet → grep empty → exit 0) | PASS ✓ |
| 3 | `grep -c "MIT License" LICENSE` = 1 | 1 ✓ |
| 3 | `Copyright (c) 2026 Longjiang Sun` present verbatim | PRESENT ✓ |

## Threat Surface Confirmation

Plan-level `<threat_model>` mitigations status:

| Threat ID | Plan 21-01 responsibility | Status |
|-----------|---------------------------|--------|
| T-21-IMPORT (Tampering, code_evolver_adapter.py / CI gate) | Plan 21-01 is the FIRST of the dual-defense layers (D-18) | ✓ Landed via `.pre-commit-config.yaml` openevolve-single-import-surface hook |
| T-21-SUPPLY (Tampering, openevolve dep) | Accept disposition: pinned `openevolve>=0.2.27` in [code] extra | ✓ Pinned (lockfile remains a deferred todo per existing repo state) |

The remaining mitigations (T-21-SECRET, T-21-RECURSE, T-21-DOS, T-21-LEAK, T-21-UNREVIEWED) belong to later plans in Phase 21 and are out of scope for Plan 01.

## Decisions Made

1. **Copyright holder: `Longjiang Sun`** — User pre-resolved the D-17 checkpoint via the orchestrator. They explicitly chose the English transliteration over the Chinese form `龙江 孙` (the value currently in `git config user.name`). Year `2026` confirmed correct. LICENSE is now in git history and considered formal.

2. **Hook entry quoting preserved verbatim from CONTEXT.md D-18** — The grep alternation `^import openevolve\|^from openevolve` is wrapped in `bash -c '...'`. The single-quotes around the bash body keep the backslash-pipe literal so grep itself sees the `\|` alternation (basic regex). No portability concerns on macOS/Linux.

3. **Hook passes vacuously today** — `evolution/code/code_evolver_adapter.py` does not yet exist (Plan 21-04). The hook's `grep -v code_evolver_adapter.py` is the eventual exclusion; today there are zero matches before the `grep -v`, so the pipeline yields empty output and `exit 0`. This is the intended baseline behavior.

4. **Backed out plan typo silently** — The `<output>` block of PLAN.md ends with `</output>` instead of e.g. a closing `</tasks_summary>` tag. Treated as a non-issue (semantically clear) — no plan edit attempted.

## Deviations from Plan

None — all three tasks executed exactly as specified by `<action>` blocks. No Rule 1/2/3/4 deviations triggered. No CLAUDE.md rules violated. No untracked files generated beyond the three committed artifacts.

## Known Stubs

None. All three artifacts are final-shape for their purpose at Plan 01 boundary:

- `LICENSE` is a complete, standard MIT text with finalized copyright.
- `pyproject.toml` `[code]` extra contains the pinned final dep version.
- `.pre-commit-config.yaml` hook entry is the final form per D-18; its `grep -v code_evolver_adapter.py` clause references a file Plan 21-04 will create, which is intentional forward-reference (the hook enforces the future invariant; it passes vacuously now, will gate real matches later).

## Self-Check: PASSED

- `LICENSE`: FOUND ✓
- `.pre-commit-config.yaml`: FOUND ✓
- `pyproject.toml` (modified): FOUND ✓
- Commit 678bf53 (task 1): FOUND ✓
- Commit 6352603 (task 2): FOUND ✓
- Commit 468cf40 (task 3): FOUND ✓
