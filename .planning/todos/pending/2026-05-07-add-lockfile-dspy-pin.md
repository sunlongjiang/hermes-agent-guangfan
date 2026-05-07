---
created: 2026-05-07T07:53:18Z
title: Add lockfile for reproducible installs (DSPy pin)
area: tooling
files:
  - pyproject.toml:17-23
---

## Problem

No lockfile exists (no `requirements.txt`, `poetry.lock`, `uv.lock`, `Pipfile.lock`, `pdm.lock`). Only minimum-version constraints in `pyproject.toml`. Every fresh clone gets the latest matching `dspy` and may break in new ways.

Evidence: commit `262a02a` ("fix: GEPA compatibility — 5-param metric signature + reflection_lm") is direct proof a DSPy upgrade silently broke the metric contract. v2.0 work (Phases 13–22) plans 200–400-example datasets; a DSPy upgrade landing mid-phase would invalidate in-flight runs ($30-100 sunk cost per run per v2 research Pitfall 4).

`darwinian-evolver` is also unversioned in `[optional-dependencies.darwinian]`; AGPL contamination risk (Pitfall 3) amplified if a future version changes import surface.

## Solution

- Generate a lockfile via `pip-compile` (pyproject-build-pinned) or migrate to `uv` (`uv lock`). Pin DSPy to a tested patch range (e.g. `dspy>=3.0.0,<3.2.0`).
- Add a `make freeze` and CI job that asserts `pip-compile --check` matches the lockfile.
- Document the verified DSPy patch version in README's "Verified Compatibility" section.

**Priority:** MED. Tracked under v2-STAB-01. Source: `.planning/codebase/CONCERNS.md` M1.
