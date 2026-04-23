# Architecture Research — v2.0 Milestone

**Domain:** DSPy-based optimization pipeline extension — per-param tools, SessionDB mining, think-augmented selection, dashboard, joint prompt optimization, drift detection, benchmark gating, code evolution
**Researched:** 2026-04-23
**Confidence:** HIGH (built directly on validated v1 codebase; integration points verified by reading actual source)

> **v1 baseline:** Original v1 architecture research is at git commit before 2026-04-23. v1 directory layout (`evolution/core/` + `evolution/{skills,tools,prompts}/`) is preserved unchanged.

---

## 1. Executive Summary

v2.0 extends v1 along four orthogonal axes:

1. **Depth** — per-param descriptions, joint sections, think-augmented selection
2. **Data** — SessionDB as real-world data source feeding both tool and prompt pipelines
3. **Gates** — drift detection, TBLite benchmark validators
4. **Reach** — code evolution beyond text artifacts (AGPL-isolated)

**Architectural principle:** v1's "Module-per-domain with Shared Core" pattern is preserved. v2 adds:
- 3 new top-level packages: `evolution/sessiondb/`, `evolution/dashboard/`, `evolution/benchmarks/`, `evolution/code/`
- 2 new files in `evolution/tools/`: `per_param_module.py`, `think_module.py`
- 2 new files in `evolution/prompts/`: `joint_module.py`, `drift_detector.py`

**Critical AGPL boundary:** `darwinian-evolver` (or substitute, see STACK.md research) MUST be isolated in `evolution/code/`, imported lazily, exposed only through a thin facade.

---

## 2. Directory Layout Diff (v1 → v2)

```
evolution/
├── core/                                 # UNCHANGED layer; minor extensions
│   ├── config.py                         # MODIFY: +6-8 fields (drift threshold, dashboard path, sessiondb path, etc.)
│   ├── constraints.py                    # MODIFY: register artifact_type "param_description" + "prompt_drift" + "tblite_benchmark"
│   ├── dataset_builder.py                # UNCHANGED
│   ├── external_importers.py             # MODIFY: fix Claude Code session path bug (history.jsonl → projects/*.jsonl)
│   └── fitness.py                        # UNCHANGED
│
├── skills/                               # UNCHANGED (Phase 1 frozen)
│
├── tools/                                # EXTEND (no restructure)
│   ├── tool_loader.py                    # MODIFY: helper extract_param_descriptions()
│   ├── tool_module.py                    # MODIFY: register per-param Predict siblings (Phase 13)
│   ├── tool_dataset_builder.py           # MODIFY: accept extra_examples list (sessiondb)
│   ├── per_param_module.py               # NEW (Phase 13)
│   ├── think_module.py                   # NEW (Phase 15) — IF retained; see Features research warning
│   ├── evolve_tool_descriptions.py       # MODIFY: +--per-param, +--use-sessiondb, +--think flags
│
├── prompts/                              # EXTEND (no restructure)
│   ├── prompt_module.py                  # UNCHANGED (round-robin stays)
│   ├── prompt_dataset_builder.py         # MODIFY: accept extra_examples
│   ├── joint_module.py                   # NEW (Phase 17) — all-sections-active variant
│   ├── drift_detector.py                 # NEW (Phase 18) — embedding/style comparator (constraint-style)
│   ├── evolve_prompt_sections.py         # MODIFY: +--joint, +--use-sessiondb, +--benchmark, +--drift-threshold flags
│
├── sessiondb/                            # NEW PACKAGE (Phase 14 + 19, shared infrastructure)
│   ├── reader.py                         # SQLite reader for hermes-agent SessionDB schema (~/.hermes/state.db)
│   ├── tool_miner.py                     # Phase 14: extracts misselection patterns
│   ├── behavior_miner.py                 # Phase 19: extracts section→behavior mappings
│   ├── filters.py                        # Three-layer PII sanitization (regex + NER + entropy heuristic)
│
├── benchmarks/                           # NEW PACKAGE (Phase 20)
│   ├── tblite_runner.py                  # Subprocess wrapper around hermes-agent/environments/benchmarks/tblite/tblite_env
│   ├── benchmark_gate.py                 # Constraint-style validator with regression threshold
│
├── dashboard/                            # NEW PACKAGE (Phase 16)
│   ├── metrics_store.py                  # Append-only JSON ledger per artifact_type
│   ├── renderer.py                       # Rich Live Table + optional HTML output
│
└── code/                                 # NEW PACKAGE (Phase 21) — AGPL/license isolation zone
    ├── __init__.py                       # IMPORT GUARD: raise ImportError if evolver missing
    ├── code_target_loader.py             # CodeTarget descriptor (curated initial target)
    ├── code_fitness.py                   # pytest pass + lint score + size penalty
    ├── evolve_code.py                    # CLI entry; subprocess isolation per Phase 21 prereq
    └── LICENSING.md                      # license boundary documentation

# Top-level:
evolution.yaml                            # MODIFY: +sessiondb, +dashboard, +benchmark, +drift, +darwinian sections
```

**Files added: ~17. Files modified: ~9. v1 tests: untouched.**

---

## 3. Per-Feature Integration Specs

### 3.1 Phase 13 — Per-Parameter Description Optimization

- **Lives in:** `evolution/tools/per_param_module.py`
- **Why new file:** ToolModule has 1 Predict per tool. Per-param needs nested (tool, param) Predicts. New file = v1 untouched, opt-in via CLI.
- **Reuses:** `ToolDescription.params` (already populated), `tool_selection_metric`, `ConstraintValidator._check_size("param_description")`
- **New:** `PerParamToolModule(ToolModule)` with `get_evolved_param_descriptions()`
- **Build dep:** Phase 12 only

### 3.2 Phase 14 — SessionDB Mining for Tools

- **Lives in:** `evolution/sessiondb/` (NEW package)
- **Why new package:** SessionDB sqlite is a different domain from JSONL session imports; bundling with `external_importers.py` (already 700+ lines) inflates a mixed module
- **Reuses:** `SECRET_PATTERNS`, `ToolSelectionExample`, `ToolDatasetBuilder.extra_examples`
- **New:** `SessionDBReader`, `ToolMisselectionMiner`
- **Data source:** `~/.hermes/state.db` (verified by Stack research; FTS5 + tool_calls columns)
- **Build dep:** Phase 12 (also fixes hidden v1 bug: Claude Code path migration)

### 3.3 Phase 15 — Think-Augmented Tool Selection

- **⚠️ Features research flagged as POTENTIAL ANTI-FEATURE:** `ToolModule.selector` is already `dspy.ChainOfThought` (`tool_module.py:64`). Original design is no-op or double-CoT.
- **Recommendation:** Drop OR redefine as "expose CoT rationale prompt as separately optimizable parameter"
- **If retained, lives in:** `evolution/tools/think_module.py`
- **Build dep:** Phase 13 (composes with per-param)

### 3.4 Phase 16 — Per-Tool Regression Dashboard

- **Lives in:** `evolution/dashboard/` (NEW package)
- **Why new package:** Cross-cutting (tools, prompts, code); persistence layer needs own home
- **Reuses:** `CrossToolRegressionChecker` (already produces per-tool deltas), Rich Live Table
- **New:** `MetricsStore` (append-only JSON ledger), `DashboardRenderer`
- **Complexity:** LOW (~100 LOC per Stack research)
- **Build dep:** Phase 14 (needs sessiondb-mined holdout for meaningful deltas)
- **Recommended order:** Phase 16 should land BEFORE Phase 17 to wire section dashboards immediately

### 3.5 Phase 17 — Joint Section Optimization

- **Lives in:** `evolution/prompts/joint_module.py` (NEW file, sibling of `prompt_module.py`)
- **Why new file:** v1 PromptModule is round-robin (set_active_section); joint is all-active simultaneously — different invariant. Mixing in one class invites stateful bugs.
- **Reuses:** `PromptSection`, `PromptBehavioralMetric`, `PromptRoleChecker`, `PromptDatasetBuilder`
- **New:** `JointPromptModule(dspy.Module)` with all section Predicts active
- **Failure-closed policy (per Pitfalls):** if joint loses to round-robin on holdout, publish negative result and keep round-robin default

### 3.6 Phase 18 — Personality Drift Detection

- **Lives in:** `evolution/prompts/drift_detector.py`
- **Why in prompts/:** Prompt-domain specific (baseline comparison, tone analysis); mirrors `PromptRoleChecker` placement
- **Reuses:** `ConstraintResult`, `LLMJudge` (LLM-as-judge over sentence-transformers — zero new deps, GEPA-reflectable)
- **New:** `PromptDriftDetector` returning ConstraintResult
- **Calibration-first (per Pitfalls):** must build labeled set (15 real drift / 15 false drift) BEFORE writing detector, tune threshold via F1
- **Build dep:** Phase 17 (joint mutations are highest drift risk)
- **Order swap (per Features research):** 18 → 17 (drift detector must exist before joint optimization can be safely run)

### 3.7 Phase 19 — SessionDB Behavioral Mining for Prompts

- **Lives in:** `evolution/sessiondb/behavior_miner.py` (same package as Phase 14)
- **Why same package:** Both read same SessionDB via shared `SessionDBReader`
- **Reuses:** `SessionDBReader`, `PromptBehavioralExample`, `PromptDatasetBuilder.extra_examples`
- **New:** `PromptBehaviorMiner` with section heuristics
- **Build dep:** Phase 14 (shared reader)

### 3.8 Phase 20 — TBLite Benchmark-Gated Validation

- **Lives in:** `evolution/benchmarks/` (NEW package)
- **Why new package:** Benchmarks are extensible domain (TBLite today, others later); heavyweight runs need own runner abstraction
- **Reuses:** `ConstraintResult`, existing subprocess pattern
- **TBLite location:** `hermes-agent/environments/benchmarks/tblite/tblite_env.py` (already exists; subprocess wrapper)
- **New:** `TBLiteRunner`, `TBLiteRegressionGate`, `BenchmarkResult`
- **Anti-pattern guard (per Features):** opt-in only, fast subset, NOT per-iteration in GEPA loop
- **Build dep:** Phase 18 (drift cheap-filters before expensive benchmark)
- **Variance pre-calibration:** small-sample experiment to set "median-of-3 + 3pp band" parameters

### 3.9 Phase 21 — Code Evolution (license-isolated)

- **Lives in:** `evolution/code/` (NEW top-level package)
- **🔴 BLOCKER from Stack research:** `darwinian-evolver` does NOT exist on PyPI. Substitute candidate: `openevolve` (Apache-2.0, sidesteps AGPL entirely)
- **Prerequisite phase (per Pitfalls):** establish license isolation infrastructure (LICENSING.md + subprocess wrapper + isolated venv + CI lint) BEFORE any evolution code
- **Isolation layers:**
  1. Optional dep declaration (`[project.optional-dependencies] code-evolution`)
  2. Single import surface (only `evolution/code/code_evolver_adapter.py` imports upstream)
  3. Lazy imports (function-scope, not module-scope)
  4. Subprocess option (strongest; recommend if upstream is AGPL)
  5. License manifest in `evolution/code/LICENSING.md`
  6. CI grep gate (test fails if upstream import outside adapter)
- **Hard exclusion:** `evolution/code/` MUST NOT evolve `evolution/` (no recursive self-evolution per Features research)
- **Reuses:** Pipeline pattern (load → dataset → optimize → constrain → eval → save), pytest as primary code fitness gate
- **New:** `CodeTarget`, `code_fitness_metric`, `code_evolver_adapter` (the single import point)

### 3.10 Phase 22 — Continuous Evolution Loop (deferred — out of v2 strict scope)

- **Lives in:** `evolution/loop/` (NEW package)
- **Default mode:** dry-run (no auto-PR per Pitfalls + PROJECT.md Out-of-Scope)
- **Build dep:** all above

---

## 4. Reused vs New Abstractions

| Need | Source | Status |
|------|--------|--------|
| Config | `EvolutionConfig` | EXTEND (+8 fields) |
| Constraints framework | `ConstraintValidator`, `ConstraintResult` | REUSE (extend artifact_type dispatch) |
| Tool dataset | `ToolDatasetBuilder` | EXTEND (+`extra_examples` arg) |
| Prompt dataset | `PromptDatasetBuilder` | EXTEND (+`extra_examples` arg) |
| LLM judge | `LLMJudge` | REUSE (drift detector) |
| Tool selection metric | `tool_selection_metric` | REUSE (works for per-param + think) |
| Behavioral metric | `PromptBehavioralMetric` | REUSE (works for joint) |
| Cross-tool regression | `CrossToolRegressionChecker` | REUSE (feeds dashboard) |
| Tool module | `ToolModule` | SUBCLASS for per-param + think |
| Prompt module | `PromptModule` | SIBLING new class for joint |
| Per-param Predicts | `PerParamToolModule` | NEW |
| SessionDB read | `SessionDBReader` | NEW |
| Tool misselection | `ToolMisselectionMiner` | NEW |
| Behavior mining | `PromptBehaviorMiner` | NEW |
| Drift detection | `PromptDriftDetector` | NEW |
| Benchmark runner | `TBLiteRunner` | NEW |
| Benchmark gate | `TBLiteRegressionGate` | NEW |
| Metrics store | `MetricsStore` | NEW |
| Dashboard render | `DashboardRenderer` | NEW |
| Code target | `CodeTarget` | NEW |
| Code evolver facade | `code_evolver_adapter` | NEW (license isolation point) |

**Net: ~4 extensions, ~8 reuses, ~11 new abstractions.** Two-thirds of v2 ships by composing existing primitives.

---

## 5. Build Order — Dependency-Driven

```
Phase 12 (DONE: stabilization baseline)
      │
      ├── Phase 12.5 [INSERT?] v2 shared infrastructure
      │   (5-param sig validator, loud fallback, cost projection, v1 regression harness)
      │
      ├── Phase 13 (per-param tools)        ──┐
      │                                       ├── Wave A: parallelizable
      ├── Phase 14 (sessiondb tools)        ──┤   no shared files
      │                                       │
      ├── Phase 17 (joint prompt) [HOLD]    ──┘   (hold until 18 lands)
      │
      ├── Phase 19 (sessiondb prompt behavior) ── shares SessionDBReader from 14
      │
      ↓
Phase 16 (dashboard) ── after Phase 14 (real data); BEFORE 17/21 to wire metrics
      │
      ↓
Phase 18 (drift detection) ── must precede 17 (per Features research re-order)
      │
      ↓
Phase 17 (joint section)   ── now safe with drift detector in place
      │
      ↓
Phase 20 (TBLite gate) ── after 18 (cheap drift filter precedes expensive benchmark)
      │
      ↓
Phase 15 (think-augmented) [DEFER OR REDEFINE] ── anti-feature per Features research
      │
      ↓
Phase 21 (code evolution) ── after dashboard + benchmark; license isolation prereq
      │
      ↓
Phase 22 (continuous loop) ── deferred to vNext if scope tight
```

**Recommended waves:**
- **Wave A (parallel, low risk):** 13, 14
- **Wave B:** 16 (after 14), 19 (after 14)
- **Wave C (sequential, gated):** 18 → 17 → 20
- **Wave D (decide first):** 15 (drop or redefine)
- **Wave E (heavy/license):** 21
- **Wave F (orchestration):** 22 deferred

---

## 6. AGPL/License Isolation for Phase 21

**Threat:** Linking propagation under copyleft licenses (AGPL especially) could pull entire `evolution` codebase under that license if upstream is imported at top of any always-loaded module.

**Mitigation layers (5):**

1. **Optional dep:** `pip install .[code-evolution]` opt-in
2. **Single import surface:** Only `evolution/code/code_evolver_adapter.py` imports upstream
3. **Lazy imports:** Function-scope, not module-top
4. **Subprocess option:** Spawn upstream as subprocess with JSON-over-stdio (recommend if upstream is AGPL)
5. **License manifest:** `evolution/code/LICENSING.md` documents the boundary

**CI gate:** pytest fails if `import <upstream>` appears outside `code_evolver_adapter.py`.

**License path resolution (per Stack research):** `darwinian-evolver` doesn't resolve on PyPI. If `openevolve` (Apache-2.0) is chosen as substitute, layers 4 (subprocess) becomes optional rather than required.

---

## 7. Config Extension (`evolution.yaml` v2 additions)

```yaml
sessiondb:
  path: "~/.hermes/state.db"
  enable_tool_mining: true
  enable_behavior_mining: true
  min_correction_confidence: 0.7

dashboard:
  output_dir: "./output/dashboard"
  history_retention: 50
  render_html: false

drift:
  enabled: true
  threshold: 0.3
  dimensions: ["tone", "formality", "personality"]

benchmark:
  tblite_subset: "fast"  # avoid full per-iteration runs
  cache_baseline: true
  regression_threshold: 0.02

code_evolution:
  enabled: false        # opt-in (license boundary)
  upstream: "openevolve"
  fitness_weights:
    pytest_pass: 0.7
    lint_score: 0.15
    size_penalty: 0.15
```

---

## 8. Open Questions for Planners

- Hermes SessionDB `schema_version` field — Phase 14 plan must check + fail loudly on mismatch
- Code evolution upstream choice — `openevolve` (Apache-2.0, simpler) vs other options
- TBLite per-run variance — Phase 20 needs small-sample calibration before deployment
- 3-model config separation in evolution.yaml (commit cdc2f4a) — verify per-component override works
- Phase 12 stabilization commits already include cost-projection logging? if not, add to Phase 12.5 mini-phase

---

## 9. Files Read

- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/research/ARCHITECTURE.md` (v1)
- `evolution/core/config.py`
- `evolution/tools/tool_module.py`
- `evolution/prompts/prompt_module.py`
- `pyproject.toml`
