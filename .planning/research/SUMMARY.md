# Project Research Summary — v2.0 Milestone

**Project:** hermes-agent-self-evolution
**Domain:** DSPy/GEPA optimization-pipeline extension (Phase 13–22 on top of stable v1)
**Researched:** 2026-04-23
**Confidence:** MEDIUM-HIGH

> Companion files: [STACK.md], [FEATURES.md], [ARCHITECTURE.md], [PITFALLS.md]. This SUMMARY synthesises, does not restate.

---

## The Three Highest-Leverage Findings

### 1. Phase 21 architecture simplifies dramatically — `darwinian-evolver` does NOT exist on PyPI

`pip index versions darwinian-evolver` returns "No matching distribution" [STACK]. Closest live package: **`openevolve` 0.2.27 (Apache-2.0)**. Switching to `openevolve` **sidesteps the AGPL boundary entirely**:

- No subprocess isolation required
- No separate `.venv-agpl/` needed
- No CI grep-gate against accidental imports
- The "license isolation infrastructure" sub-phase that PITFALLS demanded becomes optional [PITFALLS]

**Action:** Roadmapper records "Phase 21 substrate = `openevolve`" as Key Decision. Drop `[darwinian]` extra from `pyproject.toml`; replace with `[code]`.

### 2. Phase 15 (Think-Augmented) is an anti-feature as currently scoped — DROP or REDEFINE

`ToolModule.selector` is **already** `dspy.ChainOfThought(ToolSelectionSignature)` at `tool_module.py:64` [FEATURES]. Adding "another reasoning step" is no-op or double-CoT that triples cost for noise-level gains [PITFALLS Pitfall 4].

Three options ranked:
- **A (recommended):** DROP entirely. Per-param descriptions (Phase 13) absorb most of what reasoning would compensate for.
- **B (re-scope):** Expose CoT rationale instruction as separately-optimisable component in GEPA `seed_candidate`.
- **C (re-scope):** A/B "evaluator parity" check.

**Action:** User decision required before Phase 15 can be planned.

### 3. ZERO net new runtime dependencies for Phases 13–20

Verified via filesystem inspection [STACK]:
- Phase 14/19 SessionDB → stdlib `sqlite3` against `~/.hermes/state.db` (FTS5 already present)
- Phase 16 dashboard → existing `rich.live.Live` + `rich.table.Table`
- Phase 18 drift → existing `LLMJudge` (NOT sentence-transformers — saves ~700MB PyTorch + GEPA-reflectable)
- Phase 20 TBLite → subprocess into `hermes-agent/environments/benchmarks/tblite/tblite_env.py`

Only Phase 21 adds a runtime dep (`openevolve`, optional extra). v2 is a software-architecture milestone, not a stack expansion.

---

## Recommended Phase Ordering (overrides current ROADMAP)

The original 13→14→15→16→17→18→19→20→21 violates two dependency constraints. Re-ordered:

| Order | Phase | Why this slot | Source |
|-------|-------|---------------|--------|
| 0 | **Phase 12.5** (NEW INSERT) — v2 shared infrastructure | 5-param sig validator, loud GEPA→MIPROv2 fallback, per-phase cost projection, v1 regression harness, Claude Code path bug fix | [PITFALLS, STACK] |
| 1 | Phase 13 — per-param descriptions | Foundational artifact change; needs dashboard right after | [FEATURES] |
| 2 | Phase 16 — per-tool dashboard | **Move up** — must precede joint optimization risk; surfaces Phase 13 cross-param regressions | [FEATURES, PITFALLS #1, #10] |
| 3 | Phase 14 — SessionDB tool mining | Independent of 13; can ship parallel | [ARCHITECTURE Wave A] |
| 4 | Phase 19 — SessionDB prompt behavioural mining | Reuses `SessionDBReader` from 14 | [ARCHITECTURE] |
| 5 | Phase 18 — drift detection | **Move before 17** — joint section opt without drift gate is reckless | [FEATURES, PITFALLS #5/#6] |
| 6 | Phase 17 — joint section optimisation | Now safe; round-robin remains default; `--mode=joint` opt-in; fails-closed | [PITFALLS #5] |
| 7 | Phase 20 — TBLite benchmark gate | Cheap drift filter precedes expensive benchmark; final-gate-only | [PITFALLS #7] |
| 8 | Phase 15 — think-augmented (DEFER OR REDEFINE) | Re-evaluate after 13 lands | [FEATURES anti-feature] |
| 9 | Phase 21 — code evolution (`openevolve`) | Needs 16 (visibility) + 20 (final gate) as safety net | [ARCHITECTURE Wave E] |
| 10 | Phase 22 — continuous loop | Defer past v2 if scope tight; dry-run-default if shipped | [PITFALLS #13] |

**Waves:**
- Wave A (parallel): 12.5 first; then 13 + 14 in parallel
- Wave B: 16 (after 14), 19 (after 14)
- Wave C (sequential, gated): 18 → 17 → 20
- Wave D (decide first): 15
- Wave E (heavy/license): 21
- Wave F (orchestration, optional): 22

---

## Cross-Cutting Decisions the User MUST Make Before Planning Phase 13

Roadmapper should surface these as Key Decisions (not embed silently in plans):

1. **Phase 21 substrate** — confirm `openevolve` (Apache-2.0) replaces `darwinian-evolver`. Permanently retires AGPL boundary problem. [STACK §"Phase 21 BLOCKER"]
2. **Phase 15 disposition** — DROP / re-scope to Option B (rationale prompt) / re-scope to Option C (parity check). [FEATURES anti-feature]
3. **Insert Phase 12.5 mini-phase?** — recommended yes. Packages 4 shared v2 prerequisites. [PITFALLS #11/#12, ARCHITECTURE §5]
4. **Claude Code importer fix scope** — patch as part of 12.5 / Phase 14, OR insert Phase 12.x maintenance entry. Existing `ClaudeCodeImporter` silently broken today (path moved to `~/.claude/projects/<encoded-cwd>/<sid>.jsonl`). [STACK]
5. **PII / secrets policy for SessionDB mining (Phase 14 + 19)** — three-layer sanitisation (regex + NER + entropy) mandatory per PITFALLS #2. May add Microsoft Presidio or spacy as optional dep. Approve `evolution.core.privacy` package + `--i-have-consent` CLI gate + `datasets/private/` gitignored. [PITFALLS #2]
6. **SessionDB `mode=ro` access pattern** — open via `sqlite3.connect(..., uri=True)` with `mode=ro` for WAL safety. [STACK]
7. **Phase 17 fails-closed policy** — if joint < round-robin on holdout, ship negative result + keep round-robin default. [PITFALLS #5]

---

## Key Findings by Research File

### Stack [STACK]
- v1 stack sufficient; v2 adds at most 1 runtime dep (`openevolve`, optional)
- Rejected: `sqlalchemy`, `pandas`, `textual`, `sentence-transformers`, `mlflow/wandb`
- Hermes `state.db` schema verified: `sessions(system_prompt, ...)` + `messages(tool_calls, tool_name, ...)` + FTS5
- TBLite internal to hermes-agent — no PyPI dep, just subprocess
- `pyproject.toml` patches: add `[reporting]` for ReportLab, add `[code]=openevolve`, REMOVE `[darwinian]`

### Features [FEATURES]
- Table stakes (3): Phase 13 per-param, Phase 16 dashboard, Phase 18 drift
- Differentiators (5): 14, 17, 19, 20, 21
- Anti-feature (1): 15 as currently scoped
- Hidden anti-features to NOT absorb: live web UI for dashboard, in-loop TBLite, recursive self-evolution in 21, auto-merge in 22

### Architecture [ARCHITECTURE]
- v1 layout preserved; 4 NEW packages: `sessiondb/`, `dashboard/`, `benchmarks/`, `code/`
- 2 new files in `tools/` (`per_param_module.py`, optionally `think_module.py`)
- 2 new files in `prompts/` (`joint_module.py`, `drift_detector.py`)
- ~17 files added, ~9 modified, v1 tests UNTOUCHED
- `evolution.yaml` gains 5 sections (sessiondb / dashboard / drift / benchmark / code_evolution)
- 8 v1 abstractions REUSED, 4 EXTENDED, 11 NEW — two-thirds of v2 ships by composing existing primitives

### Pitfalls [PITFALLS]
Top 7 critical pitfalls + concrete prevention each phase plan must encode:
1. **Phase 13 cross-param coherence** — joint-tool fitness, `param_consistency` LLM constraint, param-count cap, v1 regression gate
2. **Phase 14/19 PII leakage** — three-layer sanitisation, allowlist extraction, `--i-have-consent`, no-verbatim-copy, TTL
3. **Phase 21 AGPL contamination** — DEFUSED if `openevolve` chosen; else subprocess + isolated venv + CI grep-gate
4. **Phase 15 cost blow-up** — drop or hybrid-routing + reasoning-length cap + cost in fitness
5. **Phase 17 joint-mode credit assignment** — per-section regression gate, round-robin default, fails-closed
6. **Phase 18 drift calibration** — labelled set BEFORE detector, F1-tuned threshold, pairwise (not pointwise), median-of-3
7. **Phase 20 TBLite flakiness** — final-gate-only (NOT in GEPA loop), median-of-3, artifact-hash cache, opt-in default

Plus moderate pitfalls 8-13 (schema drift, success/failure balance, dashboard distribution metrics, reflection_lm cost, 5-param signature, continuous-loop idempotency).

---

## Calibration-First Phases

Two phases must invert "code then calibrate" order:
- **Phase 18 (drift detector):** 30 paired examples (15 true-drift, 15 false-drift) as Task 1; threshold by F1-maximisation, NOT intuition
- **Phase 20 (TBLite gate):** small-sample variance experiment to calibrate "median-of-3 + 3pp band" before any candidate hits the gate

These belong as *first* tasks of their phase plans.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All claims verified by direct filesystem inspection or PyPI lookup. `openevolve` API surface MEDIUM (no live README fetch) |
| Features | MEDIUM | Architecturally HIGH; behavioural / benchmark items MEDIUM (no live web search) |
| Architecture | HIGH | Built directly on v1 codebase; integration points verified by reading source |
| Pitfalls | MEDIUM-HIGH | DSPy GEPA pitfalls verified against commit 262402a; AGPL/PII/benchmark/drift advice based on engineering practice |

**Overall:** MEDIUM-HIGH

### Gaps to Address During Phase Planning
- `openevolve` API surface and GEPA-style reflection compatibility — verify on first Phase 21 plan iteration
- Hermes `state.db` schema stability — only one snapshot observed; Phase 14 plan must include `schema_version` assertion
- TBLite per-run variance — needs small-sample experiment in Phase 20 plan Task 1
- DSPy 3.x `dspy.GEPA` `component_selector` — [VERIFY] whether wrapper exposes same multi-component surface as standalone `gepa.optimize()`
- Whether commit cdc2f4a's per-component model overrides plumb through to `evolve_*` CLIs — verify in Phase 12.5

---

## Sources

### Primary (HIGH confidence — direct verification)
- Live filesystem: `~/.hermes/state.db` schema, `~/.claude/projects/<encoded-cwd>/<sid>.jsonl` format, `hermes-agent/environments/benchmarks/tblite/tblite_env.py`
- v1 codebase: `evolution/tools/tool_module.py:64` (CoT already present), `evolution/core/external_importers.py` (Claude Code path bug), `evolution/core/fitness.py` (LLMJudge), `pyproject.toml`
- Git history: commit 262402a (5-param GEPA + reflection_lm), cdc2f4a (per-component model override)
- PyPI: `darwinian-evolver` (NOT FOUND), `openevolve 0.2.27`, `darwinian 0.0.5.4`, `sentence-transformers 5.4.1`, `plotly 6.7.0`, `sqlalchemy 2.0.49`

### Secondary (MEDIUM — v1 research carry-forward)
- v1 PITFALLS.md / FEATURES.md / SUMMARY.md (collected 2026-04-15 with full web access)
- DSPy 3.0 documentation as embedded in v1 codebase usage

### Tertiary (LOW — needs validation)
- `openevolve` exact API shape
- Hermes `state.db` long-term schema stability
- 2024-25 papers cited in FEATURES marked **[VERIFY]** (ToolACE, MPO, Think-Augmented Function Calling)

---
*Synthesised: 2026-04-23 — ready for v2 roadmap revision once 7 Cross-Cutting Decisions resolved*
