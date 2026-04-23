# Feature Research — v2.0 Milestone

**Domain:** v2 enhancements to an existing DSPy/GEPA-based pipeline that optimizes tool descriptions and system-prompt sections for hermes-agent. v1 (Phases 1-12) is complete and validated; v2 adds 9 new phases (13-21).
**Researched:** 2026-04-23
**Confidence:** MEDIUM (architecturally HIGH because v1 patterns are concrete; behavioral/benchmark items are MEDIUM because no live web search was available — see "Source Notes" below)

> **Source Notes.** Web search and fetch were denied during this research run. All ecosystem citations below are carried forward from the v1 research (FEATURES.md, SUMMARY.md, PITFALLS.md), which were collected with full web access on 2026-04-15. New v2-specific claims are grounded in the actual codebase under `evolution/` and the orchestrator-supplied milestone context. Items needing fresh web validation are flagged with **[VERIFY]**.

---

## v2 Scope at a Glance

Nine candidate features mapped to phases 13-21. Two big themes:
1. **Depth on existing artifacts** — make tool/prompt optimization more granular, more targeted, more guarded (Phases 13-20).
2. **Width into new artifact types** — extend evolution beyond text into code (Phase 21).

| Phase | Feature ID | Name | Category | Complexity |
|------|-----------|------|----------|-----------|
| 13 | TOOL-V2-02 | Per-parameter description optimization | **Table stakes** | LOW-MED |
| 14 | TOOL-V2-01 | SessionDB mining for tools | **Differentiator** | MED |
| 15 | TOOL-V2-03 | Think-augmented tool selection | **Anti-feature** (as currently scoped) | MED-HIGH |
| 16 | TOOL-V2-04 | Per-tool regression dashboard | **Table stakes** | LOW |
| 17 | PMPT-V2-01 | Joint section optimization | **Differentiator** | MED |
| 18 | PMPT-V2-02 | Personality drift detection | **Table stakes** | MED |
| 19 | PMPT-V2-04 | SessionDB behavioral mining for prompts | **Differentiator** | MED |
| 20 | PMPT-V2-03 | Benchmark-gated validation (TBLite) | **Differentiator** (gate, not loop) | MED-HIGH |
| 21 | V2-CODE-01 | Darwinian code evolution | **Differentiator with anti-feature risk** | HIGH |

---

## Feature Landscape

### Table Stakes — v2 Cannot Ship Without These

Without these, v2 either contradicts its own positioning ("safer optimization") or leaves obvious gaps that v1 already implied.

#### TOOL-V2-02 / Phase 13 — Per-Parameter Description Optimization

**Behavior table.**

| Input | Expected Output |
|-------|-----------------|
| `evolve_tool_descriptions --granularity=param` over 8 tools × 5 params each | 40 independently-optimizable text components, each ≤200 chars; param names/types/required flags untouched |
| Param description previously "the file" (12 chars) | Optimized to "absolute path to the source file; relative paths resolved against cwd" (~75 chars), still ≤200 |
| Top-level description constraint already satisfied | Param-level constraint check (200 chars) gates each candidate independently |

**Why table stakes for v2.** v1 FEATURES.md already named this as a v2 must: *"parameter descriptions ... improves parameter correctness, not just tool selection."* Selection accuracy plateaus once descriptions are good; param accuracy (right tool, wrong arg) becomes the dominant remaining failure mode.

**User-facing behavior.** Two new flags on `evolve_tool_descriptions`:
- `--granularity=tool|param|both` (default: `tool` for backward compatibility)
- Output report shows per-param accuracy delta in addition to per-tool selection rate.

**Reference implementations / patterns.**
1. **GEPA `seed_candidate` dict pattern** (v1 SUMMARY.md, HIGH confidence) — multiple text components keyed by ID, exactly the shape needed: keys become `f"{tool_name}.{param_name}"`. **[VERIFY]** that DSPy's `dspy.GEPA` wrapper exposes the same multi-component surface; the v1 stack uses `dspy.GEPA` not standalone `gepa.optimize()`.
2. **Existing `ToolModule.tool_predictors` dict** (`evolution/tools/tool_module.py:48`) — already a per-tool dict. Extend to nested dict `{tool: {param: Predict}}`, or flat dict with composite keys. The `params: list[ToolParam]` are already loaded with separate `description` fields (`evolution/tools/tool_loader.py:37`).
3. **MPO section-local gradients** (v1 source: arxiv 2601.04055) — analogous principle: optimize structured text component-by-component with local feedback rather than as a monolith.

**Dependency on v1 code.**
- `evolution/tools/tool_loader.py` — `ToolParam.description` field already exists; no loader change needed.
- `evolution/tools/tool_module.py` — extend `__init__` to wrap each param desc in its own `Predict`; extend `forward()` to inject param descs into the `available_tools` rendering; extend `get_evolved_descriptions()` to read back per-param edits.
- `evolution/tools/tool_constraints.py` — add `MAX_PARAM_DESC_SIZE = 200` constraint (already declared in PROJECT.md, just wire it).
- `evolution/tools/tool_dataset.py` — add a "param-correctness" subscore that distinguishes wrong-tool from right-tool-wrong-args.

**Dependency on other v2 phases.** None. Phase 13 should ship before Phase 15 (think-augmented), because per-param descriptions reduce ambiguity and may eliminate much of what reasoning would otherwise compensate for.

**Sharp scope boundary.**
- ✅ Optimize the text of `description` fields inside `params: list[ToolParam]`.
- ✅ Per-param size constraint enforcement.
- ✅ Per-param accuracy reporting.
- ❌ **NOT** adding new params, removing params, reordering, retyping, changing `required`, adding/removing enums.
- ❌ **NOT** rewriting the top-level `ToolDescription.description` jointly in this phase (that's existing v1 behavior, kept independent).

**Complexity:** LOW-MED. Mostly a fan-out of an already-working pattern; metric gets one new subscore.

---

#### TOOL-V2-04 / Phase 16 — Per-Tool Regression Dashboard

**Behavior table.**

| Input | Expected Output |
|-------|-----------------|
| Optimization run completes with global accuracy +3pp | Dashboard shows per-tool delta; if any tool drops >2pp, run is **flagged** (not failed) and dashboard highlights it red |
| `--regression-threshold=0.05` flag passed | Threshold becomes 5pp instead of default 2pp |
| `output/tools/<run-id>/per_tool_metrics.json` written | Machine-readable file with `{tool_name: {baseline_rate, evolved_rate, delta, sample_count}}` for downstream tooling |

**Why table stakes.** v1 already ships `CrossToolRegressionChecker` (`evolution/tools/tool_metric.py:72`) which computes per-tool rates internally — but it only emits a pass/fail boolean, not a visible dashboard. PITFALLS.md ranks "cross-tool interference" as Pitfall #1; without a visible per-tool view, regressions caused by joint optimization (Phase 13's per-param fan-out makes this worse) are undetectable in practice. This is the *minimum trust surface* for v2.

**User-facing behavior.**
- Rich console table at end of run: tool, baseline rate, evolved rate, Δ, sample count, status (✓ / ⚠ / ✗).
- JSON metrics file written next to existing `metrics.json`.
- Default threshold 2pp is a warn, configurable via `--regression-threshold`.
- Hard-fail threshold (default 5pp) **rejects** the candidate (mirrors existing constraint pattern).

**Reference implementations / patterns.**
1. **Existing `CrossToolRegressionChecker`** — already computes the data; this phase exposes it.
2. **DSPy run `metrics.json` convention** (v1 codebase, `output/skills/<run-id>/metrics.json`) — same JSON shape, just per-tool-keyed.
3. **Rich `Table` patterns already used in `evolve_skill.py`** (CLAUDE.md: "Tables via `rich.table.Table`") — copy idiom verbatim.

**Dependency on v1 code.**
- Reads from `CrossToolRegressionChecker.compute_per_tool_rates()` (already exists).
- Writes to existing `output/tools/<run-id>/` directory layout.

**Dependency on other v2 phases.** Should land **before or alongside** Phase 13, because Phase 13's per-param granularity multiplies the surface where description-stealing can occur. If Phase 13 ships first, regressions could land in production-ready output without anyone seeing them.

**Recommendation:** Re-order to Phase 13 → Phase 16 → Phase 14 → Phase 15.

**Sharp scope boundary.**
- ✅ Per-tool selection rate tracking and visualization.
- ✅ Configurable threshold; warn vs hard-fail tiers.
- ✅ JSON output for downstream tooling.
- ❌ **NOT** historical comparison across runs (that's Phase 22 / continuous loop territory).
- ❌ **NOT** a Web UI; Rich console + JSON is sufficient.
- ❌ **NOT** real-time monitoring during the optimization loop (post-run only; otherwise it slows GEPA reflection).

**Complexity:** LOW. Pure presentation + configuration on top of existing data.

---

#### PMPT-V2-02 / Phase 18 — Personality / Tone Drift Detection

**Behavior table.**

| Input | Expected Output |
|-------|-----------------|
| Baseline `DEFAULT_AGENT_IDENTITY` (300 chars), evolved variant (350 chars) | Drift report scored on dimensions: directness, formality, verbosity, helpfulness, honesty (0-1 each); composite drift score |
| Drift score >0.15 on any dimension | Constraint check returns `passed=False`, candidate rejected |
| `--drift-threshold=0.20` flag | Tolerance widened to 20% per dimension |

**Why table stakes for v2.** Phase 17 introduces joint multi-section optimization, which *increases* blast radius — multiple sections move at once, so personality drift becomes more likely. Without an automated gate, the only way to catch drift is human review of every output (defeats the point of v2 enhancements). v1 FEATURES.md already named this as expected v2 work.

**User-facing behavior.**
- Runs after constraint validation, before final acceptance.
- Probe set: 10-20 generic agent-like tasks (not section-specific) executed against baseline-prompt and evolved-prompt agents.
- LLM-as-judge scores each pair on five dimensions; produces both a per-dimension delta and a composite.
- Drift report saved to `output/prompts/<run-id>/drift_report.json`.
- Rejection emits a Rich panel: "Personality drift detected: directness -0.18 (was: 0.85, now: 0.67)".

**Reference implementations / patterns.**
1. **v1 `LLMJudge` pattern** (`evolution/core/fitness.py:34`) — DSPy `Signature` with rubric. New `DriftCheckSignature` follows same shape, just outputs five floats instead of one composite. HIGH confidence (proven pattern).
2. **v1 `PromptRoleChecker`** (`evolution/prompts/prompt_constraints.py:32`) — same constraint-style integration: returns `ConstraintResult`, gates acceptance. HIGH confidence.
3. **LLM-as-a-Judge survey** (v1 source: arxiv 2411.15594) — recommends binary checks over float scores when possible. Apply: convert per-dimension score to a binary `drifted_significantly: bool` plus magnitude, rather than relying on raw floats. **MEDIUM confidence** without re-fetch.

**Dependency on v1 code.**
- `evolution/core/fitness.py` — reuse `LLMJudge` infrastructure; add `PersonalityDriftJudge` parallel class.
- `evolution/prompts/prompt_constraints.py` — register `PersonalityDriftChecker` alongside `PromptRoleChecker`.
- A small probe-set fixture (10-20 generic tasks) — new file `evolution/prompts/drift_probes.json` or similar.

**Dependency on other v2 phases.** **Must precede or co-ship with Phase 17** (joint section optimization). Joint optimization without drift detection is reckless.

**Sharp scope boundary.**
- ✅ Five named dimensions (directness, formality, verbosity, helpfulness, honesty) — committed in advance.
- ✅ Constraint-style gating (pass/fail with thresholds).
- ✅ Both per-dimension and composite scoring.
- ❌ **NOT** open-ended "vibe check" with arbitrary LLM rubrics — that's PromptRoleChecker's job.
- ❌ **NOT** comparing against historical drift baselines (Phase 22 territory).
- ❌ **NOT** explaining *why* drift occurred (just detecting + flagging).

**Complexity:** MED. Probe set design + judge calibration are the real work; integration is mechanical.

---

### Differentiators — Set v2 Apart

These are not strictly required for v2 to "make sense", but they unlock genuinely new capability that competing optimization stacks lack.

#### TOOL-V2-01 / Phase 14 — SessionDB Mining for Tool Misselection

**Behavior table.**

| Input | Expected Output |
|-------|-----------------|
| `evolve_tool_descriptions --eval-source=sessiondb` | Imports tool_call entries from hermes-agent SessionDB, identifies misselections, builds dataset |
| Misselection found: agent picked `terminal(grep)` when `search_files` was clearly better | Becomes a high-weight training example with `expected_tool=search_files`, `weight=2.0` |
| Session contained user correction ("no, use search instead") | Becomes a hard-negative example, doubly weighted |
| Mixed with synthetic data | Final dataset is configurable mix; default 70% synthetic + 30% mined |

**Value proposition.** Real misselections beat synthetic confusers. Synthetic confusers are designed by an LLM that already knows which tool *should* win; real misselections come from cases where the agent itself was confused. Higher signal per example.

**User-facing behavior.**
- New CLI flag `--eval-source={synthetic,sessiondb,mixed}`.
- New CLI flag `--sessiondb-path` (env fallback `HERMES_SESSION_DB`).
- Mining log printed: "Imported 142 tool calls; identified 23 misselections; rejected 6 ambiguous".
- Misselections cached to `datasets/tools/sessiondb_misselections.jsonl` so re-runs skip the mining step.

**Reference implementations / patterns.**
1. **v1 `HermesSessionImporter`** (`evolution/core/external_importers.py:334`) — already reads SessionDB. Extend with a `extract_tool_calls()` static method.
2. **v1 `RelevanceFilter`** (`evolution/core/external_importers.py:422`) — already uses LLM-as-judge to score message relevance. Mirror as `MisselectionFilter`: given (task_context, tool_used, tool_args, outcome), score whether the choice was optimal. MEDIUM confidence (pattern is identical, calibration is new).
3. **ToolACE-style data synthesis** (v1 source: arxiv 2409.00920v2) — confirms that real-world misselection data outperforms synthetic data for tool optimization. **MEDIUM confidence** without re-fetch.

**Dependency on v1 code.**
- `evolution/core/external_importers.py` — extend `HermesSessionImporter` or add `SessionToolMiner` peer class.
- `evolution/tools/tool_dataset.py` — add `from_sessiondb()` constructor; integrate weighting into `ToolDatasetBuilder`.
- `evolution/tools/tool_metric.py` — support example weighting in metric computation.

**Dependency on other v2 phases.** Independent. Could ship in parallel with Phase 13. Soft dependency on Phase 16: if the dashboard exists, you can compare per-tool rates between synthetic-only and mixed-source runs to validate that mining actually helps.

**Sharp scope boundary.**
- ✅ Read-only mining from SessionDB (HERMES_AGENT_REPO is read-only, per CLAUDE.md).
- ✅ Misselection detection via LLM-as-judge.
- ✅ Weighted integration into existing dataset builder.
- ❌ **NOT** writing back to SessionDB.
- ❌ **NOT** privacy/PII scrubbing beyond what v1 secret detection (`SECRET_PATTERNS`) already does — assume SessionDB is already clean per project policy.
- ❌ **NOT** active learning loops; mining is offline/batch.

**Complexity:** MED. The mining logic is straightforward; calibrating "what counts as a misselection?" is the real work.

---

#### PMPT-V2-04 / Phase 19 — SessionDB Behavioral Mining for Prompts

**Behavior table.**

| Input | Expected Output |
|-------|-----------------|
| `evolve_prompt_sections --eval-source=mixed --section=MEMORY_GUIDANCE` | Synthetic scenarios + mined real cases where memory should/shouldn't have been used |
| User corrections like "you already know this" | Mined as positive examples for MEMORY_GUIDANCE (agent failed to recall) |
| User corrections like "no, search the project first" | Mined as positive examples for SESSION_SEARCH_GUIDANCE |
| Verbose-response complaints from session | Mined as targeted scenarios for IDENTITY section |

**Value proposition.** v1's 80 synthetic behavioral scenarios are good but generic. Real session corrections show the *exact* failure modes that matter to actual users. Each mined scenario maps to a specific section, making the data per-section actionable.

**User-facing behavior.** Same `--eval-source` flag as Phase 14, but for prompts. New mining log entries per section.

**Reference implementations / patterns.**
1. **v1 `HermesSessionImporter`** + **`RelevanceFilter`** — same shape as Phase 14, different output (behavioral examples instead of tool selections).
2. **v1 `PromptDatasetBuilder`** (`evolution/prompts/prompt_dataset.py:154`) — already supports per-section dataset construction. Extend to accept mined examples as additional input.
3. **LangSmith / phoenix-style "annotate from traces"** patterns — common across agent observability stacks. **LOW confidence** without re-fetch — but the conceptual pattern is sound and mirrors Phase 14 exactly.

**Dependency on v1 code.** Same surface as Phase 14, but in `evolution/prompts/`.

**Dependency on other v2 phases.** Independent. Symmetric with Phase 14.

**Sharp scope boundary.**
- ✅ Section-tagged mining (which section's behavior failed?).
- ✅ Integration with PromptDatasetBuilder.
- ❌ **NOT** automatic section-classifier (human heuristics + LLM-as-judge for assignment, not learned classifier).
- ❌ **NOT** mining behaviors that aren't tied to one of the 5 evolvable sections (e.g., raw tool-use behavior — that's Phase 14's job).

**Complexity:** MED. Same difficulty as Phase 14, with extra complexity in the section-attribution step (which prompt section *should* have prevented this failure?).

---

#### PMPT-V2-01 / Phase 17 — Joint Section Optimization

**Behavior table.**

| Input | Expected Output |
|-------|-----------------|
| `evolve_prompt_sections --mode=joint` | All 5 sections become simultaneously discoverable as `dspy.Predict` instances; GEPA `component_selector="all"` mode (or equivalent in `dspy.GEPA`) optimizes across all of them |
| Joint run completes | Holdout score compared against round-robin baseline; jointly-optimized variant accepted only if score ≥ round-robin |
| Section A's edit conflicts with Section B's edit on a holdout scenario | Drift detector (Phase 18) catches it; constraint validators (existing) gate it |

**Value proposition.** v1 PromptModule explicitly freezes 4 sections while optimizing 1, with round-robin scheduling. This misses cross-section interactions — e.g., improving MEMORY_GUIDANCE might enable a tighter PLATFORM_HINTS, which the round-robin pass can't discover in one cycle. Joint optimization captures these.

**User-facing behavior.**
- New CLI flag `--mode={round_robin,joint}` (default: `round_robin` for backward compatibility).
- Joint mode is more expensive (estimated 2-3× cost per iteration); flag in console output.
- Output report compares joint vs round-robin metrics if both have been run for the same baseline.

**Reference implementations / patterns.**
1. **GEPA `component_selector="all"`** (v1 source: GEPA standalone API blog 2026) — directly supports this mode. **MEDIUM confidence** that `dspy.GEPA` (the wrapper actually used in v1) exposes the same knob; **[VERIFY]** in DSPy 3.0 changelog or via Context7.
2. **v1 `ToolModule` already does joint optimization** (`evolution/tools/tool_module.py:48`) — all `tool_predictors` are simultaneously discoverable. Phase 17 brings PromptModule to parity.
3. **MPO paper** (arxiv 2601.04055) — recommends per-section first, *then* joint pass. Aligns with this phase ordering.

**Dependency on v1 code.**
- `evolution/prompts/prompt_module.py` — major refactor: replace single-active-section pattern with all-active-as-predictors pattern. Keep round-robin mode for backward compatibility.
- `evolution/prompts/evolve_prompt_sections.py` — add `--mode` flag and orchestration branch.

**Dependency on other v2 phases.** **Must depend on Phase 18** (drift detection). Joint optimization without drift detection is high-risk because all 5 sections move at once.

**Recommendation:** Re-order to Phase 18 → Phase 17 (or co-ship), not the current 17 → 18.

**Sharp scope boundary.**
- ✅ All 5 sections optimizable simultaneously.
- ✅ Mode flag preserves round-robin as default.
- ✅ Comparison report against round-robin baseline.
- ❌ **NOT** changing the 5 sections themselves (still: DEFAULT_AGENT_IDENTITY, MEMORY_GUIDANCE, SESSION_SEARCH_GUIDANCE, SKILLS_GUIDANCE, PLATFORM_HINTS).
- ❌ **NOT** auto-discovering new evolvable sections.
- ❌ **NOT** removing growth/role/drift constraints (they apply per-section even in joint mode).

**Complexity:** MED. Conceptually simple; the v1 PromptModule's "frozen by exclusion" design needs to be unwound carefully so DSPy's `named_parameters()` discovers all 5.

---

#### PMPT-V2-03 / Phase 20 — Benchmark-Gated Validation (TBLite)

**Behavior table.**

| Input | Expected Output |
|-------|-----------------|
| `evolve_prompt_sections --benchmark=tblite` | After all in-loop validators pass, evolved variant is run against TBLite "fast subset" (~20 tasks, ~20 min) |
| TBLite score regresses by ≥ threshold | Variant rejected; report saved with per-task TBLite breakdown |
| TBLite score improves or holds | Variant accepted; benchmark report saved alongside metrics |
| `--benchmark` not passed | Phase 20 is a no-op (default: skip benchmark for cost reasons) |

**Value proposition.** Behavioral synthetic scenarios (v1 PromptDatasetBuilder) and drift detection (Phase 18) are necessary but not sufficient — a prompt could pass both yet still regress on real benchmark tasks the synthetic suite doesn't cover. TBLite as a final gate provides a model-graded reality check.

**Why differentiator (not table stakes).** Marked **Out of Scope** in PROJECT.md and REQUIREMENTS.md as "TBLite/YC-Bench per-iteration gating — every 2-6 hours + $50-200 each." This phase is the *bounded* version: not per-iteration, not full benchmark — only a fast subset, only on the final candidate(s), only when explicitly opted in. That bounded form is what makes it ship-able for v2.

**User-facing behavior.**
- Opt-in via `--benchmark={tblite,tblite-fast,none}` (default: `none`).
- Cost warning printed before benchmark starts: "TBLite-fast estimated cost: $5-15, ~20 minutes".
- Benchmark report saved to `output/prompts/<run-id>/tblite_report.json`.

**Reference implementations / patterns.**
1. **TBLite (Terminal Bench Lite)** — referenced throughout v1 PROJECT.md. **[VERIFY]** the existence and exact name; v1 sources didn't link it directly.
2. **Existing constraint pattern** — `ConstraintValidator.validate_all()` returns list of `ConstraintResult`. Add a `BenchmarkConstraint` that runs only on opted-in candidates.
3. **DSPy hold-out evaluation pattern** (v1 codebase) — same shape: run module against held-out examples, score, gate.

**Dependency on v1 code.**
- `evolution/core/constraints.py` — add benchmark gate (or new module `evolution/core/benchmark_gate.py` per v1 SUMMARY mention).
- `evolution/prompts/evolve_prompt_sections.py` — orchestrate benchmark step; honor opt-in flag.
- External: TBLite must be installable / runnable from this pipeline. **[VERIFY]** integration story.

**Dependency on other v2 phases.** Should follow Phase 18 (drift detection) — benchmark is the *last* gate, after constraints and drift. Independent of Phase 17 mechanically but more valuable when combined with joint optimization (catches joint-mode side effects).

**Sharp scope boundary.**
- ✅ Opt-in only; `none` is default.
- ✅ Fast subset only (~20 tasks, ~20 min).
- ✅ Final-candidate gate, not per-iteration.
- ❌ **NOT** YC-Bench, full TerminalBench2, or any benchmark with multi-hour runtime (PROJECT.md Out-of-Scope).
- ❌ **NOT** in-loop fitness signal (would slow GEPA iteration to a crawl).
- ❌ **NOT** auto-merge based on benchmark pass (still requires human review per CLAUDE.md / PROJECT.md).

**Complexity:** MED-HIGH. The integration with TBLite is the unknown; the gate logic itself is straightforward.

---

#### V2-CODE-01 / Phase 21 — Darwinian Code Evolution

**Behavior table.**

| Input | Expected Output |
|-------|-----------------|
| `evolve_code --component=tool_registry --tests=tests/integration/test_registry.py` | At least one hermes-agent code component is evolved; fitness = pytest pass rate + code-quality metrics |
| Test failure on holdout | Variant rejected (binary gate, not LLM-as-judge) |
| `pip install .[darwinian]` already done (per CLAUDE.md) | darwinian-evolver wired into the pipeline |

**Value proposition.** Extends self-evolution beyond text artifacts to code. This is the project's stated v2 stretch goal and the most visible "new capability" addition.

**Why differentiator with anti-feature risk.** Massive scope per phase (one full new evolution surface), brings AGPL v3 license obligations (CLAUDE.md notes `darwinian-evolver` is AGPL v3 — this affects how the pipeline can be deployed/licensed downstream), and code evolution has fundamentally different risk profile than text evolution (text bugs degrade quality; code bugs cause crashes). The phase is justified, but its scope **must** be tightly constrained.

**User-facing behavior.**
- New CLI: `python -m evolution.code.evolve_code --component=<name> --tests=<path> --iterations=N`.
- Fitness function combines: pytest pass rate (binary, must be 100%), code-quality scores (pylint/ruff if available — keep minimal), file-size delta (penalize bloat).
- Output: evolved file written to `output/code/<run-id>/<component>.py` plus diff report.
- Like all v1 pipelines: NEVER auto-merges; human review required (CLAUDE.md).

**Reference implementations / patterns.**
1. **darwinian-evolver itself** — already a dependency per CLAUDE.md; check its README for canonical usage. **[VERIFY]** API surface.
2. **Existing `evolution/code/` package stub** (per `ls evolution/`) — the directory exists, suggesting some scaffolding may already be present.
3. **AlphaEvolve / FunSearch-style evolutionary code search** — established in 2024-2025 literature. **LOW confidence** without re-fetch. Same conceptual pattern: candidates generated by LLM, scored by tests, top-K kept, mutated.

**Dependency on v1 code.**
- `evolution/code/` (package stub exists) — populate with `code_module.py`, `code_metric.py`, `code_constraints.py`, `evolve_code.py`.
- `evolution/core/constraints.py` — add code-specific constraints (file size delta, must-pass-tests).
- New constraint: **license attribution** — emit notice that AGPL v3 dependency is used; document how this affects downstream usage.

**Dependency on other v2 phases.** Listed in roadmap as depending on Phase 16 + Phase 20 (i.e., after the regression dashboard and benchmark gate are in place). **Concur with that ordering** — code evolution needs the strongest possible safety net before it ships.

**Sharp scope boundary.**
- ✅ ONE code component evolvable (success criterion is "at least one"; do not over-deliver).
- ✅ Fitness combines tests + minimal code quality.
- ✅ Hard binary test gate (no flaky-test allowance).
- ✅ Read-only against hermes-agent (writes only to `output/`, per project constraints).
- ❌ **NOT** evolving security-critical components (auth, sandbox, eval).
- ❌ **NOT** evolving the optimization pipeline itself (no recursive self-evolution).
- ❌ **NOT** broad refactoring agents (this is small targeted edits, not "rewrite this module").
- ❌ **NOT** auto-applying changes without test pass.

**Complexity:** HIGH. Single biggest new feature; new package, new metric design, new external dependency surface, license implications.

---

### Anti-Features — Tempting But Wrong (As Currently Scoped)

#### TOOL-V2-03 / Phase 15 — Think-Augmented Tool Selection (as currently described)

**Why it's flagged as anti-feature.** The roadmap describes this as "ChainOfThought before selection; measure if reasoning step improves accuracy." Two problems:

1. **`ToolModule.selector` is already `dspy.ChainOfThought(ToolSelectionSignature)`** — see `evolution/tools/tool_module.py:64`. CoT-before-selection already happens. There is no missing capability to add.

2. **The actual value would be optimizing the CoT rationale prompt as a parameter, not adding CoT.** That's a different, more bounded feature: expose the `ChainOfThought`'s `rationale` field's instruction text as a GEPA-optimizable component.

**Why it sounds attractive.** "Think before you act" is intuitively appealing and there's 2025 literature (Think-Augmented Function Calling, arxiv 2601.18282 — cited in v1 FEATURES.md, MEDIUM confidence) suggesting reasoning improves tool selection.

**Why it's actually problematic as currently scoped.**
- Implementation would either be a no-op (CoT is already there) or would add a *second* reasoning step before the existing CoT — which doubles latency and cost without clear benefit.
- v1 FEATURES.md already noted: *"this changes agent behavior, not just descriptions — may be out of scope for Phase 2 if we're only evolving text."* The same concern applies for v2: hermes-agent's actual runtime tool-selection path is independent of this pipeline; making the *evaluator* think harder doesn't change the *agent's* runtime behavior.
- Risk of overfitting: a more powerful evaluator can find descriptions that pass eval but don't help the actual (less powerful) runtime selector.

**What to do instead — three options, in order of preference.**

**Option A (recommended): Drop Phase 15.** Per-param descriptions (Phase 13) already address most of the ambiguity that a reasoning step would compensate for. Save the iteration budget.

**Option B (re-scope): "Optimize the reasoning prompt itself."** Expose the CoT rationale prompt as a separately optimizable text component (one new key in the GEPA `seed_candidate` dict). Bounded, low-risk, follows the same per-component pattern as Phases 13 & 17.

**Option C (re-scope): "Evaluator/runtime parity check."** Instead of adding a reasoning step, add an A/B comparison that runs each evolved description against both the v1 selector (no reasoning) and a stronger reasoning selector. Use *agreement* between them as a robustness signal — descriptions that work only with the stronger reasoner are penalized.

**Behavior table (for Option B if pursued).**

| Input | Expected Output |
|-------|-----------------|
| `evolve_tool_descriptions --optimize-rationale` | The instruction text inside `ToolModule.selector`'s ChainOfThought signature is added to the GEPA optimization set |
| Optimization completes | Evolved rationale prompt + evolved tool descriptions both reported |

**Complexity if pursued (Option B):** MED. Mostly DSPy plumbing.
**Complexity if pursued as originally scoped:** MED-HIGH and likely net-negative.

**Recommendation:** Defer to v2.1 or drop. If kept in v2, restrict to Option B with a conservative cost cap.

---

### Anti-Feature Risks Hidden Inside Other Features

These are not standalone phases but sub-scopes that v2 could accidentally absorb. Calling them out so the scoping conversation is explicit.

| Hidden Anti-Feature | Phase It Could Sneak Into | Why Avoid | Better Alternative |
|---|---|---|---|
| Cross-run historical drift tracking ("compare to last 5 runs") | Phase 16 (dashboard) | Requires persistent metrics store, conflicts with v1's "no persistent state between runs" architecture (CLAUDE.md). | Defer to Phase 22 / continuous loop where persistence is justified. |
| Auto-PR creation from optimization output | Any phase | PROJECT.md Out-of-Scope: "Auto PR creation — output to `output/` directory only". | Stays as-is: human creates PR from `output/`. |
| Real-time per-iteration TBLite fitness | Phase 20 | $50-200 + 2-6h per run; explicitly Out-of-Scope. | Final-candidate fast subset only (the scoped form). |
| Recursive self-evolution (evolve the evolver) | Phase 21 | Massive blast radius, no safety net possible. | Hard-exclude `evolution/` from Phase 21's component list. |
| Evolving SessionDB schema or hermes-agent runtime code | Phases 14, 19, 21 | Project constraint: hermes-agent is read-only. | Mining/reading only; outputs to `output/`. |
| Auto-merge if benchmark passes | Phase 20 | PROJECT.md Out-of-Scope: "Auto-merge without human review". | Benchmark report informs reviewer; reviewer decides. |
| LLM-graded fitness on code evolution | Phase 21 | Code is binary correct/incorrect; LLM-as-judge invites flaky scoring. | Pytest pass rate as primary gate; LLM only for code-quality nudges. |

---

## Feature Dependencies

```
Phase 12 (v1 stabilization, COMPLETE) ──┐
                                          │
                      ┌───────────────────┼──────────────────────┐
                      │                   │                      │
                      ▼                   ▼                      ▼
              Phase 13 (per-param)  Phase 17 (joint sec.)  Phase 14 (sessdb tools)
                      │                   ▲                      │
                      │                   │                      │
                      ▼                   │                      ▼
              Phase 16 (dashboard) ──────┐│              Phase 19 (sessdb prompts)
                      │                  ││                      │
                      │           ┌──────┘│                      │
                      │           │       │                      │
                      ▼           │       │                      │
              Phase 15 (think)    │       │                      │
              [defer / re-scope]  │       │                      │
                                  │       │                      │
                            Phase 18 (drift detection)           │
                                  │                              │
                                  ▼                              │
                            Phase 20 (TBLite gate) ◀─────────────┘
                                  │
                                  ▼
                            Phase 21 (code evolution)
                            [HIGH risk; needs all gates]
```

### Dependency Notes

**Strict prerequisites.**
- **Phase 13 → Phase 16**: Per-param granularity multiplies the surface where description-stealing can occur. Dashboard must exist before per-param ships, or *recommend* re-ordering so they ship together.
- **Phase 18 → Phase 17**: Joint section optimization moves all 5 sections at once — drift detection is the only automated guardrail. Roadmap currently has 17 → 18; **recommend swap or co-ship**.
- **Phase 21 → all gating phases (16, 18, 20)**: Code evolution has the highest blast radius; needs every safety net.

**Independent / parallel-shippable.**
- Phase 14 (sessdb tools) ⊥ Phase 19 (sessdb prompts) — symmetric, share no code.
- Phase 13 (per-param) ⊥ Phase 14 (sessdb tools) — different surfaces of the tool pipeline.
- Phase 17 (joint sec.) ⊥ Phase 19 (sessdb prompts) — different surfaces of the prompt pipeline.

**Conflicts / careful combinations.**
- **Phase 13 + Phase 17 simultaneously**: Multiplies the optimization surface enormously. Should not be the *first* combined run; ship them sequentially with separate validation runs first.
- **Phase 21 + Phase 22 (continuous loop, out of v2)**: Code evolution + automation = high risk. Phase 22 is correctly outside v2.

---

## v2 MVP Definition

### Ship in v2 (Recommended Cut)

**Strict v2 minimum (re-ordered for safety):**

1. **Phase 13** — Per-parameter description optimization (low complexity, high value, table stakes)
2. **Phase 16** — Per-tool regression dashboard (low complexity, prerequisite trust surface for Phase 13)
3. **Phase 18** — Personality drift detection (medium complexity, prerequisite trust surface for Phase 17)
4. **Phase 17** — Joint section optimization (medium complexity, real differentiator once gated by 18)
5. **Phase 14** — SessionDB mining for tools (medium complexity, real-data differentiator)
6. **Phase 19** — SessionDB behavioral mining for prompts (medium complexity, real-data differentiator)
7. **Phase 20** — Benchmark-gated validation (medium-high complexity, opt-in only)
8. **Phase 21** — Darwinian code evolution (high complexity, capstone new capability)

### Defer or Re-scope

- **Phase 15** — Think-augmented tool selection: defer or re-scope to "optimize rationale prompt" (Option B above). Current scoping is an anti-feature.

### Out of v2 Entirely

- Phase 22 (continuous evolution loop) — already correctly outside v2.
- Cross-run historical metrics persistence.
- Auto-PR / auto-merge.
- Per-iteration TBLite fitness.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---|---|---|---|
| Phase 13: Per-param desc | HIGH (param accuracy is largest remaining error class) | LOW-MED | **P1** |
| Phase 16: Per-tool dashboard | HIGH (trust surface; required for Phase 13's safety) | LOW | **P1** |
| Phase 18: Drift detection | HIGH (gates Phase 17; protects personality) | MED | **P1** |
| Phase 17: Joint section opt | MED-HIGH (catches cross-section interactions) | MED | **P2** |
| Phase 14: SessionDB tools | MED-HIGH (real-world data > synthetic) | MED | **P2** |
| Phase 19: SessionDB prompts | MED-HIGH (real-world data > synthetic) | MED | **P2** |
| Phase 20: TBLite gate | MED (opt-in; cost-bounded) | MED-HIGH | **P2** |
| Phase 21: Code evolution | MED (capstone; separate user base) | HIGH | **P3** |
| Phase 15: Think-augmented (as scoped) | LOW (CoT already present) | MED-HIGH | **P3 / drop** |

---

## Competitor / Reference Stack Comparison

Carried forward from v1 research. **[VERIFY]** indicates needs fresh check.

| Capability | DSPy ecosystem (2026) | GEPA paper (ICLR 2026) | LangChain / LangSmith | Our v2 approach |
|---|---|---|---|---|
| Multi-component text optimization | `dspy.GEPA` + standalone `gepa.optimize()` with `seed_candidate` dict (HIGH confidence from v1) | Native; reflective per-component feedback | Limited; mostly per-prompt | GEPA via `dspy.GEPA`; per-tool, per-param, per-section components |
| Per-tool regression detection | Custom (no built-in) | Not addressed in paper | Built-in eval comparison via LangSmith **[VERIFY]** | `CrossToolRegressionChecker` + Phase 16 dashboard |
| Personality drift detection | Not built-in | Not addressed | Custom evaluators in LangSmith **[VERIFY]** | `PersonalityDriftJudge` (constraint-style) |
| Real-data mining from sessions | Not built-in (DSPy `Example` pattern is BYO data) | Not addressed | Built-in via LangSmith trace replay **[VERIFY]** | `HermesSessionImporter` extensions (Phases 14/19) |
| Code evolution | Not built-in | Not in scope | Not in scope | darwinian-evolver (Phase 21) |
| Joint section/component opt | `component_selector="all"` (HIGH from v1) | Native (paper) | Not directly applicable | Phase 17 |

---

## Sources

### Primary (HIGH confidence — carried from v1, verified at the time)

- [DSPy GEPA Overview](https://dspy.ai/api/optimizers/GEPA/overview/) — `component_selector` modes (Phases 13, 17)
- [GEPA Paper (ICLR 2026 Oral)](https://arxiv.org/abs/2507.19457) — multi-component reflective optimization (Phases 13, 17)
- [GEPA Standalone API Blog](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/) — `seed_candidate` dict pattern (Phase 13)

### Secondary (MEDIUM confidence — carried from v1)

- [ACL 2025: A Joint Optimization Framework for Tool Utilization](https://github.com/Bingo-W/ToolOptimization) — cross-tool regression prevention (Phases 13, 16)
- [Modular Prompt Optimization (MPO)](https://arxiv.org/abs/2601.04055) — section-local then joint pattern (Phase 17)
- [LLM-as-a-Judge Survey](https://arxiv.org/abs/2411.15594) — binary checks > float scores (Phase 18)
- [ToolACE (ICLR 2025)](https://arxiv.org/html/2409.00920v2) — tool-call data synthesis & mining (Phases 14, 19)
- [Microsoft: Tool-Space Interference](https://www.microsoft.com/en-us/research/blog/tool-space-interference-in-the-mcp-era-designing-for-agent-compatibility-at-scale/) — cross-tool interference (Phase 16)

### Tertiary (LOW confidence — carried from v1, needs re-verification)

- [Think-Augmented Function Calling](https://arxiv.org/html/2601.18282) — relevant to Phase 15; the citation is the v1 source for the original idea but does not validate the specific implementation proposed in the v2 roadmap.
- TBLite (Terminal Bench Lite) — referenced in v1 PROJECT.md without external citation. **[VERIFY]** existence and integration story.
- darwinian-evolver — installed via `pip install .[darwinian]` per CLAUDE.md; AGPL v3. **[VERIFY]** API surface and license implications for Phase 21.

### Internal (HIGH confidence — codebase grounding, current 2026-04-23)

- `evolution/tools/tool_module.py` — confirms `ChainOfThought` selector already present (Phase 15 anti-feature evidence)
- `evolution/tools/tool_loader.py` — confirms `ToolParam.description` field exists (Phase 13 feasibility)
- `evolution/prompts/prompt_module.py` — confirms single-active-section design (Phase 17 refactor surface)
- `evolution/tools/tool_metric.py` — confirms `CrossToolRegressionChecker` already computes per-tool rates (Phase 16 minimal-build)
- `evolution/core/external_importers.py` — confirms `HermesSessionImporter` + `RelevanceFilter` patterns (Phases 14, 19 reuse path)
- `evolution/core/fitness.py` — confirms `LLMJudge` rubric pattern (Phase 18 reuse path)
- `evolution/code/` directory exists per `ls evolution/` — confirms Phase 21 has a stub package waiting

---
*Feature research for: hermes-agent-self-evolution v2.0 milestone*
*Researched: 2026-04-23*
*Note: Web search/fetch denied during this run; all external citations carried forward from v1 research (2026-04-15) and grounded against current codebase. **[VERIFY]** items flagged where re-validation is recommended before phase planning.*
