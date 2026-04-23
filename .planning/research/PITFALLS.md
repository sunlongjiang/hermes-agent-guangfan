# Pitfalls Research — v2.0 Milestone

**Domain:** Extending v1 GEPA optimization pipeline (skills + tools + prompts) with per-param optimization, SessionDB mining, think-augmented selection, joint-section optimization, drift detection, benchmark gating, and Darwinian code evolution
**Researched:** 2026-04-23
**Confidence:** MEDIUM-HIGH (DSPy GEPA pitfalls verified against existing v1 code + commit 262402a evidence; AGPL/PII/benchmark/drift pitfalls based on engineering practice)

> Companion to v1 PITFALLS.md (preserved domain-level pitfalls). This document focuses on **regression risk on v1** and **integration risk** introduced by adding v2 features (Phase 13–22) on top of the stable 329-test v1 baseline.

---

## Critical Pitfalls

### Pitfall 1: Per-Parameter Optimization (Phase 13) Destroys Cross-Parameter Coherence

**What goes wrong:**
Phase 13 exposes per-parameter descriptions as independently optimizable parameters. GEPA, given an isolated metric for one parameter at a time, optimizes that param at the expense of the surrounding tool description and sibling parameters. The tool description ends up self-contradictory: e.g. `path` param description says "absolute paths only" while `cwd` param says "relative paths supported," even though the tool implementation requires consistent semantics. Combinatorial explosion: a tool with 8 params × N candidates per param = N^8 design space, blowing through the budget.

**Why it happens:**
- v1 ToolModule treats each tool's full description as a single parameter (Phase 3 design). Phase 13 changes the optimization unit to per-param, which breaks the implicit "one mutation, one fitness signal" coupling.
- GEPA's reflective analysis sees one param's selection-accuracy delta but has no signal for "did the param descriptions stay consistent with each other and with the top-level description?"
- Existing `tool_selection_metric` is binary at tool level — it cannot distinguish "right tool, wrong param framing" from "right tool, coherent param framing."

**Consequences:**
- Tool-level selection accuracy stays flat or improves, but `parameter_correctness` (rate at which agent invokes tool with valid args) regresses silently.
- v1 holdout passes; users hit runtime tool errors because evolved param descriptions misled the agent into wrong arg shapes.
- Optimization budget overruns 3–10× because GEPA explores combinatorially with no convergence signal.

**Warning signs (early symptoms):**
- Per-param metric improves but composite `parameter_correctness` drops on holdout.
- Evolved param descriptions for the same tool contradict each other on substrings (path vs relative, required vs optional framing).
- GEPA rollouts per iteration grow super-linearly with param count.
- `max_metric_calls` budget exhausted before Pareto front stabilizes.

**Prevention strategy (concrete mechanism):**
1. **Joint param fitness, not isolated.** The Phase 13 metric MUST score the full tool (top-level + all params together). Mutate one param per GEPA candidate but evaluate the whole tool's selection + invocation correctness.
2. **Add a `param_consistency` constraint** to `ConstraintValidator`: an LLM check that scans all params + top-level description and rejects candidates with self-contradictions. Reject before fitness scoring.
3. **Cap design space per tool:** if `len(params) > 5`, optimize params in fixed groups (e.g., 3 at a time, frozen others) rather than truly independent. Document the cap in Phase 13 plan.
4. **Per-param size hard limit (200 chars)** stays enforced from v1 — do not relax for "more room to express constraints."
5. **Regression gate against v1 baseline:** before accepting Phase 13 output, re-run v1 Phase 5 holdout (top-level-only optimization). v2 must match or beat v1.

**Phase plan should address explicitly:** **Phase 13** plan must include (a) joint-tool fitness function design, (b) param_consistency LLM constraint spec, (c) param-count cap policy, (d) v1-baseline regression gate as explicit acceptance criterion.

**Confidence:** HIGH

---

### Pitfall 2: SessionDB Mining (Phase 14 + Phase 19) Leaks PII / API Keys / Proprietary Code into Datasets

**What goes wrong:**
Real session transcripts from `~/.hermes/sessions/`, `~/.claude/history.jsonl`, and `~/.copilot/session-state/` contain user PII (emails, names, internal hostnames), API keys outside common patterns, proprietary code, and customer business data. v1's `SECRET_PATTERNS` regex in `external_importers.py` catches obvious tokens (`sk-...`, `ghp_...`) but not: internal URLs, employee names, customer identifiers, proprietary algorithm fragments, OAuth bearer tokens with non-standard prefixes, AWS account IDs, JWTs without standard headers. Mined examples become training data, then leak verbatim into evolved tool descriptions or prompt sections (Dropbox case study confirmed verbatim copying happens).

**Why it happens:**
- v1's secret detection is regex-only and pattern-shallow — it was designed for skill mining where the surface area was small.
- Phase 14 + 19 dramatically scale up the mining surface (every tool selection event, every behavioral example).
- Synthetic data generation (`SyntheticDatasetBuilder`) and GEPA reflection both echo training examples back into prompts. If the training set contains PII, the *evolved artifact* contains PII, and that artifact gets committed to git via the v2.0 PR loop (Phase 22).
- Session files aggregate multiple users' contexts on shared devices.

**Consequences:**
- PII leaks into committed `output/` artifacts and git history (irreversible).
- API keys mined from sessions get echoed into evolved descriptions, causing key revocation events when CI logs are scraped.
- GDPR / SOC2 compliance violations if hermes-agent users include EU customers.
- Loss of trust if a user discovers their session data shaped a published prompt.

**Warning signs (early symptoms):**
- Evolved artifacts contain proper nouns, email addresses, internal hostnames, or customer-specific terms.
- Test datasets contain identifiable user/project names.
- LLM judge feedback references specific users or projects.
- Mined dataset diff shows token-like strings (40+ chars of base64 entropy).

**Prevention strategy (concrete mechanism):**
1. **Three-layer sanitization pipeline** before any mined data hits disk:
   - Layer 1: Expand regex pattern list (add JWT regex `eyJ[a-zA-Z0-9_-]{20,}`, AWS pattern `AKIA[0-9A-Z]{16}`, OAuth bearer `Bearer [a-zA-Z0-9._-]{20,}`, hex tokens `[a-f0-9]{32,}`).
   - Layer 2: NER-based PII redaction (Microsoft Presidio or `spacy`'s default NER for PERSON, ORG, EMAIL, PHONE, IP, GPE entities). New optional dep, isolated to `evolution.core.privacy`.
   - Layer 3: Entropy heuristic — reject any token >24 chars with Shannon entropy >4.0.
2. **Allowlist-based extraction:** only extract structured fields needed for the metric (e.g. `tool_name`, `task_description_summary`), never raw user message bodies. Have an LLM produce a *paraphrased* task description instead of using the original verbatim.
3. **Opt-in consent prompt** with explicit list of files to be scanned, before any read happens (CLI must show counts + sample paths and require `--i-have-consent` flag).
4. **Sanitization audit** runs against any mined dataset before GEPA sees it: an LLM check "does this dataset contain any PII, secrets, or proprietary data?" — block on YES.
5. **No verbatim copy constraint** (already noted in v1 PITFALLS Pitfall 3) gets *enforced* as a `ConstraintValidator` check for v2: reject any evolved artifact containing 8+ contiguous tokens from a training example.
6. **Dataset retention policy:** mined datasets stored under `datasets/private/`, gitignored, with a 30-day TTL.

**Phase plan should address explicitly:** **Phase 14 plan** must include sanitization pipeline design + consent UX. **Phase 19 plan** must reference Phase 14's pipeline and add the no-verbatim-copy constraint to `PromptModule` evolution. **Phase 22 plan** (continuous loop) must block PR creation if sanitization audit fails.

**Confidence:** HIGH (PII-in-LLM-training-data is a documented and litigated failure mode; v1 secret-detection limits are visible in code)

---

### Pitfall 3: AGPL Contamination from `darwinian-evolver` (Phase 21)

**What goes wrong:**
`darwinian-evolver` is AGPL v3 (declared in CLAUDE.md). AGPL's network-use clause means: any software that *links to* AGPL code, or *interacts with it as a combined work*, must itself be AGPL when distributed or made available over a network. If Phase 21 imports `darwinian_evolver` directly inside `evolution/code/`, the entire `evolution/` package arguably becomes AGPL-encumbered — including v1 components (skill / tool / prompt evolution), which would be re-licensed by accident. If hermes-agent is later distributed under another license, the contamination propagates.

**Why it happens:**
- `pip install .[darwinian]` installs as a same-process Python dependency. Direct `import` is the canonical "linking" trigger for AGPL.
- Developers default to "just import it" rather than building a process boundary.
- AGPL §13 (network interaction) extends contamination to SaaS / API-served code paths — meaning if `evolution/` is later wrapped behind an HTTP service (e.g., a self-evolution dashboard from Phase 16), the AGPL obligation triggers.
- "Optional dependency" in pyproject.toml does NOT shield the using code — once you import it, you're combined.

**Consequences:**
- Project license becomes effectively AGPL — incompatible with proprietary or permissively-licensed downstream use.
- v1 components (skill/tool/prompt evolution, currently un-licensed or permissive) get re-licensed by linkage.
- Distribution of `output/` artifacts may also become subject to AGPL share-alike if they contain code generated by AGPL evolver.
- Legal review required before any release; potentially blocks merging to hermes-agent.

**Warning signs (early symptoms):**
- `import darwinian_evolver` (or similar) appearing in any module outside `evolution/code/`.
- v1 modules (`evolution/core/`, `evolution/skills/`, `evolution/tools/`, `evolution/prompts/`) acquiring imports from `evolution/code/`.
- Test files that exercise both v1 and Phase 21 code in the same process.
- pyproject.toml moving `darwinian-evolver` from `[project.optional-dependencies.darwinian]` to base `[project.dependencies]`.
- Code generated by darwinian-evolver checked in without separate AGPL license header.

**Prevention strategy (concrete mechanism):**
1. **Process boundary, not import boundary.** Phase 21 invokes `darwinian-evolver` ONLY via `subprocess.run(["python", "-m", "darwinian_evolver", ...])` from a thin wrapper in `evolution/code/darwinian_runner.py`. No direct `import darwinian_evolver` anywhere.
2. **Separate venv for AGPL deps.** Install `darwinian-evolver` into `.venv-agpl/` (isolated venv), invoked with `subprocess.run(["{repo}/.venv-agpl/bin/python", ...])`. Add a Makefile target `make agpl-venv`.
3. **License header in `evolution/code/`:** every file in this directory carries an AGPL v3 header. Other directories carry the project's chosen license (TBD; recommend MIT or Apache-2.0 explicit declaration in LICENSE before Phase 21 starts).
4. **CI lint check:** add a pre-commit hook + CI job that fails if `darwinian_evolver` appears in any `import` line outside `evolution/code/darwinian_runner.py`. Use `grep -r "import darwinian" evolution/ --exclude-dir=code` as the gate.
5. **Output isolation:** evolved code from darwinian-evolver written to `output/code-evolved/` with prominent NOTICE.md explaining the AGPL provenance. Do NOT auto-merge into hermes-agent without human license review.
6. **Add LICENSE.md** at repo root declaring the project's license BEFORE Phase 21 — once contamination happens, retroactive re-licensing is impossible.

**Phase plan should address explicitly:** **Phase 21 plan** must specify the subprocess-only invocation pattern, the isolated venv setup, the CI lint check, and the LICENSE.md prerequisite. The plan's first task (before any code) is "establish license isolation infrastructure."

**Confidence:** HIGH (AGPL §13 contamination is well-documented in OSS legal literature)

---

### Pitfall 4: Think-Augmented Selection (Phase 15) Inflates Latency / Cost Without Accuracy Gain

**What goes wrong:**
Phase 15 adds a ChainOfThought reasoning step before tool selection. Tokens per selection grow 3–10× (reasoning typically 200–800 tokens vs. ~50 for direct selection). Optimization cost spikes proportionally because GEPA evaluates each candidate against the full dataset. Worse, the reasoning step *appears* to improve selection by encouraging the model to articulate decisions — but research on chain-of-thought shows that reasoning can be confabulated post-hoc, with the actual selection driven by the same surface heuristics. Net result: 3× cost for a noise-level accuracy bump that disappears on holdout.

**Why it happens:**
- "More reasoning = better answers" is a common but unsupported assumption for narrow classification tasks like tool selection.
- DSPy's `ChainOfThought` wrapper makes the change a one-liner — easy to add, hard to evaluate the cost honestly.
- v1 tool_selection_metric measures `is_correct` per call but doesn't track tokens, latency, or cost — so the regression is invisible in the existing metric.
- GEPA's `max_metric_calls=iterations * 50` budget translates to 5–10× more API tokens with reasoning enabled, but the budget knob is unchanged.

**Consequences:**
- Optimization runs go from `$2-10` (v1 baseline) to `$30-100` per Phase 15 run — silently breaking the project's "$2-10 per run" cost claim.
- Production latency for tool selection grows 3–10× — direct user impact in hermes-agent.
- Apparent gains on training set don't replicate on holdout (overfitting to confabulated reasoning patterns).
- Prompt cache invalidation: reasoning prompts vary per query, so cache hit rate drops.

**Warning signs (early symptoms):**
- Token usage per GEPA iteration jumps 3–10× vs. Phase 13 baseline.
- Holdout-vs-training accuracy gap widens.
- A/B test on ambiguous tasks shows accuracy delta within noise (<2pp) despite 3×+ cost.
- Wall-clock time per optimization run exceeds 2× v1 baseline.

**Prevention strategy (concrete mechanism):**
1. **Mandatory cost & latency tracking:** Phase 15 metric MUST emit `tokens_per_selection` and `latency_ms` alongside `is_correct`. Cost is part of the fitness function (penalize selections >2× baseline tokens).
2. **A/B holdout gate:** Phase 15 acceptance criterion = "+5pp accuracy on ambiguous-tasks subset on holdout, AND ≤2× latency, AND ≤3× tokens." Reject if any constraint fails. No "well it improved on training set" pass.
3. **Reasoning length cap:** add a constraint that the reasoning step prompt template caps output at 200 tokens. Forces concise reasoning, prevents runaway.
4. **Direct vs. think A/B by default:** Phase 15 keeps the v1 direct-selection module as the fallback, switches to think-augmented only when classified as `ambiguous` by a cheap classifier. Hybrid routing avoids paying the cost on the 80% easy cases.
5. **Hard budget cap:** new `EvolutionConfig.max_cost_usd` per run. Optimization halts when exceeded.

**Phase plan should address explicitly:** **Phase 15 plan** must list cost/latency tracking as a Phase 15 *deliverable* (not optional), specify the A/B holdout acceptance criterion explicitly, and document the hybrid routing fallback.

**Confidence:** MEDIUM-HIGH (CoT confabulation is documented in 2024-2025 reasoning literature; cost projection is a direct calculation)

---

### Pitfall 5: Joint Section Optimization (Phase 17) Has One Bad Section Drag Others Down

**What goes wrong:**
Phase 17 mutates all 5 prompt sections (DEFAULT_AGENT_IDENTITY, MEMORY_GUIDANCE, SESSION_SEARCH_GUIDANCE, SKILLS_GUIDANCE, PLATFORM_HINTS) simultaneously instead of round-robin (v1 Phase 8 design). GEPA candidates that mutate 5 sections at once produce 32 (2^5) interaction patterns. A bad change in one section can drag down the joint score even when the other 4 are improvements — and GEPA's reflective analysis can't easily attribute which section caused the regression. Optimization stalls or oscillates. v1 Phase 8 round-robin worked precisely because it isolated the change source.

**Why it happens:**
- "Joint optimization" sounds more powerful than round-robin, but it sacrifices attribution.
- DSPy GEPA's reflection_lm (per commit 262402a) reads the failure trace and proposes mutations — with 5 simultaneously-changed sections, attribution becomes a 5-way credit-assignment problem the reflection LM is poorly suited to solve.
- v1 PromptModule and round-robin loop are working. The "joint" path is a re-architecture, not an addition.
- Cross-section interactions (e.g., MEMORY_GUIDANCE telling agent to check memory + SESSION_SEARCH_GUIDANCE telling it to search sessions) compound or conflict in ways the metric can't decompose.

**Consequences:**
- Joint optimization scores worse than round-robin on holdout — Phase 17 is a regression vs. v1.
- Wasted optimization budget on Pareto candidates that are strictly dominated.
- "Best joint" output may have one regressed section that gets rolled to production because the aggregate looks fine.
- v1 Phase 10 `evolve_prompt_sections` CLI users see worse results than before if Phase 17 becomes the default.

**Warning signs (early symptoms):**
- Joint-mode holdout score < v1 round-robin holdout score on the same dataset.
- GEPA's Pareto front has many candidates clustered near baseline (no clear winner).
- Per-section scores after joint optimization show 1 section regressed >5pp while others improved.
- GEPA reflection_lm feedback comments like "unclear which change caused the regression."

**Prevention strategy (concrete mechanism):**
1. **Per-section regression gate within joint mode:** any candidate where ANY single section's per-section behavioral score drops >3pp vs. baseline is rejected, even if joint score improved. Reuse `PromptBehavioralMetric` per-section scoring.
2. **Round-robin remains the default;** joint mode is `--mode=joint` opt-in flag. v1 users get v1 behavior unchanged.
3. **A/B holdout acceptance criterion:** Phase 17 accepted only if joint mode beats round-robin by ≥3pp on holdout AND no per-section regression. Otherwise document "joint experiment failed, round-robin retained" and close the phase.
4. **Section-attributed feedback:** modify the metric to emit per-section deltas in the `feedback` field so reflection_lm has attribution signal. Without this, GEPA is blind on joint-mode failures.
5. **Cap simultaneous mutations:** even in joint mode, GEPA candidates limited to mutating 2 sections per generation (configurable), not all 5. Reduces interaction surface from 32 patterns to 10.

**Phase plan should address explicitly:** **Phase 17 plan** must specify (a) per-section regression gate is non-optional, (b) round-robin remains default, (c) "Phase 17 fails closed" — if joint mode doesn't beat round-robin, ship the negative result and close the phase rather than forcing a positive narrative.

**Confidence:** HIGH (credit assignment in joint optimization is well-known; v1 round-robin is the proven baseline)

---

### Pitfall 6: Personality Drift Detection (Phase 18) Calibrated Wrong Blocks Valid Improvements

**What goes wrong:**
Phase 18 adds a `DriftDetector` constraint that rejects evolved sections with tone/personality drift exceeding a threshold. Calibration is hard: too tight and every meaningful improvement is rejected (the whole point of evolution is to change behavior); too loose and the constraint is ceremonial — evolved prompts drift to "Helpful AI assistant" generic tone. Initial threshold is invariably wrong, and false-positive blocks frustrate users who then disable the gate, defeating its purpose. The drift score itself is LLM-as-judge, so it inherits the v1 PITFALLS #2 instability problem.

**Why it happens:**
- "Drift" is a fuzzy, multi-dimensional concept (tone, formality, persona traits, vocabulary). Collapsing to a single threshold is an approximation that always leaks.
- LLM-judged drift scores have ±0.15 noise — threshold-on-noisy-signal yields high false-positive rate.
- v1 PromptRoleChecker (Phase 10) already exists and works for *role* preservation. Adding personality detection on top doubles the LLM-judge cost AND adds another noisy signal.
- Default thresholds tend to be set by a single calibration run on a small sample, not validated against a held-out drift-true / drift-false dataset.

**Consequences:**
- Phase 18 either blocks 80% of evolved candidates (false positives, optimization stalls) or accepts everything (false negatives, drift not actually prevented).
- Users disable the gate via config or CLI flag, defeating the safety mechanism.
- Optimization cost rises because each candidate now requires an extra LLM call for drift scoring.
- "Drift detected" alerts become noise; real drift slips through alongside false alarms.

**Warning signs (early symptoms):**
- Phase 18 rejects >30% of candidates that pass v1 constraints (calibration too tight).
- OR Phase 18 rejects <2% of candidates, including obviously-drifted candidates from synthetic test (calibration too loose).
- Drift score variance on identical input >0.10 (judge too noisy for the threshold).
- Users add `--no-drift-check` flag in real usage.

**Prevention strategy (concrete mechanism):**
1. **Build a drift-labeled calibration set BEFORE setting threshold.** 30 paired (original, evolved) examples where 15 are "true drift" (synthetically rewritten in different tone) and 15 are "no drift" (rephrased preserving tone). Set threshold to maximize F1 on this labeled set, not on intuition.
2. **Drift score must be pairwise** (`DriftDetector(original, evolved) -> float`), NOT pointwise. Pairwise comparison is more reliable than absolute scoring (v1 PITFALLS #2).
3. **3-run averaging:** drift score = mean of 3 LLM-judge runs. Reject only if mean - 1·stdev > threshold (conservative — prefer false negatives over false positives during calibration).
4. **Multi-dimensional drift, not scalar:** report drift as a vector (tone, formality, vocabulary, persona). Threshold each dimension separately. Single dimension exceeded = warning; 2+ dimensions exceeded = reject. Surfaces "what kind of drift" to the user.
5. **Reuse v1 PromptRoleChecker pattern:** make DriftDetector follow the same interface (LLM judge + JSON output + parsed fields) so test infrastructure is shared.
6. **Threshold revisit cadence:** quarterly recalibration with newly collected drift examples from production; threshold tuning is an ongoing maintenance task, not a one-shot.

**Phase plan should address explicitly:** **Phase 18 plan** must include (a) drift-labeled calibration set construction as Task 1 (before any DriftDetector code), (b) F1-optimized threshold derivation, (c) pairwise (not pointwise) score design, (d) multi-dimensional output schema, (e) explicit "no `--no-drift-check` bypass flag" decision rationale.

**Confidence:** HIGH (LLM-judge calibration is well-documented; v1 PromptRoleChecker is the proven analog)

---

### Pitfall 7: TBLite Benchmark Gating (Phase 20) Becomes a Flaky Wall, Wastes Budget

**What goes wrong:**
Phase 20 gates evolved sections on TBLite benchmark — if benchmark fails, candidate rejected. But TBLite is slow (PROJECT.md notes 2-6 hours, $50-200) and often flaky (LLM-driven benchmarks have run-to-run variance). Gating on flaky benchmarks means: (a) good candidates rejected by transient noise, (b) bad candidates accepted because they passed the noisy gate, (c) GEPA optimization budget wasted re-evaluating candidates that were rejected by flakiness rather than real regression. Worse, GEPA's reflection_lm gets misleading "passed/failed" signals, optimizing toward gaming the benchmark rather than genuine quality.

**Why it happens:**
- LLM-as-judge benchmarks (and TBLite is one) have inherent run-to-run variance — 2-5pp on small subsets.
- "Pass = score ≥ X" thresholding on a noisy score is a binary view of a continuous noisy signal.
- A 2-6 hour gate per candidate × 20-100 GEPA candidates = full optimization run measured in weeks.
- If the gate is wired into GEPA's metric loop (not as a final acceptance check), every candidate triggers it.
- "Optional --benchmark flag" in plan implies TBD wiring decisions that may default to wrong placement.

**Consequences:**
- Optimization runs become unaffordable ($1000+, multi-day) — Phase 20 effectively unusable.
- OR users skip the gate (`--no-benchmark`), making Phase 20 ceremonial.
- GEPA over-fits to benchmark idiosyncrasies (specific phrasing in benchmark tasks).
- False rejections discourage real improvements; false passes ship real regressions.
- Project's "$2-10 per run" claim broken further than Phase 15 already does.

**Warning signs (early symptoms):**
- Same candidate evaluated twice gives different pass/fail.
- Optimization budget exhausted while Pareto front still moving.
- Acceptance rate <20% with apparently-good candidates failing.
- User reports "I keep re-running and getting different results."
- GEPA optimization wall-clock > 24 hours per run.

**Prevention strategy (concrete mechanism):**
1. **Benchmark is a FINAL gate, NOT in the GEPA loop.** GEPA optimizes against `PromptBehavioralMetric` (cheap, fast). After GEPA produces top-K candidates, run TBLite ONCE per top-K candidate. Reject only if TBLite regression > 3pp vs. baseline.
2. **Multi-run averaging on the gate.** Run TBLite 3× per candidate, take median. Pass iff median ≥ baseline - 3pp (allow 3pp regression band for noise).
3. **Subset benchmark for fast iteration.** TBLite has tiers; use a 10-min subset for inner-loop sanity (catches obvious regressions), full suite only for final candidate.
4. **Hard cost cap.** `EvolutionConfig.max_cost_usd` (introduced for Phase 15) applies here too. Halt if benchmark spend exceeds threshold.
5. **Cache results per (artifact_hash, benchmark_version).** Same evolved artifact never benchmarked twice. Cache survives across optimization runs.
6. **Default OFF.** `--benchmark` is opt-in for v2. Default behavior unchanged from v1.

**Phase plan should address explicitly:** **Phase 20 plan** must specify (a) "outside GEPA loop, final-only" as architectural decision, (b) median-of-3 noise mitigation, (c) artifact-hash caching, (d) opt-in default, (e) cost cap integration.

**Confidence:** HIGH (noisy gate problems are well-understood in CI/CD and ML evaluation literature)

---

## Moderate Pitfalls

### Pitfall 8: SessionDB Format Drift Across hermes-agent Versions

**What goes wrong:**
Phase 14 + 19 importers parse session JSON from `~/.hermes/sessions/`. hermes-agent's session schema evolves over time (new event types, renamed fields, nested structure changes). Importers written against today's schema silently miss new event types after a hermes-agent upgrade — mining yields fewer / biased examples without raising errors.

**Why it happens:**
- v1 Hermes session importer reads files defensively (skips on errors per CONCERNS.md), so schema drift presents as "fewer results" not "failure."
- No schema version pinning: importer doesn't check hermes-agent's session schema version.
- hermes-agent is read-only from this repo's perspective; schema changes there are not tracked here.

**Prevention strategy:**
- Importers MUST read and assert a `session_schema_version` field if hermes-agent provides one (file an issue against hermes-agent if missing). Hard fail (not silent skip) on unknown major version.
- Add a "session import audit" CLI subcommand that reports counts by event type — surfaces silent drops.
- CI integration test that runs the importer against a checked-in fixture (representative session JSON), so schema parsing changes are caught.

**Phase plan should address explicitly:** **Phase 14 plan** must include the schema version assertion + audit CLI as deliverables.

**Confidence:** MEDIUM-HIGH

---

### Pitfall 9: SessionDB Mining Biased Toward Failures Only

**What goes wrong:**
"Mine misselection patterns as high-value training data" (TOOL-V2-01) — sounds great, but if Phase 14 only mines failures, the dataset distribution becomes failure-skewed. GEPA optimizes for "fix the failures" without verifying "successes still succeed." Tool descriptions evolve to handle pathological tasks at the cost of common-case selection accuracy.

**Why it happens:**
- "High-value" is interpreted as "rare and educational" (failures), not "representative" (success + failure mix).
- v1 Phase 4 datasets are synthetic-balanced. Mixing in pure failures shifts class distribution.
- GEPA's reflection_lm sees only failures, so its mutations target failure recovery at the expense of success preservation.

**Prevention strategy:**
- Mined dataset MUST include both successes (positive examples) and failures (negative examples), with documented class balance (suggest 70/30 success/failure for representativeness).
- Track per-class fitness (success accuracy, failure-recovery accuracy) separately. Reject candidates that improve one but regress the other.
- Document the mining target distribution in Phase 14 plan; deviation requires explicit justification.

**Phase plan should address explicitly:** **Phase 14 plan** must specify success:failure ratio + per-class metric tracking.

**Confidence:** MEDIUM

---

### Pitfall 10: Per-Tool Regression Dashboard (Phase 16) Stores Misleading Averages

**What goes wrong:**
Phase 16 dashboards "selection rate per tool." Aggregate average hides distribution shifts: tool X improves on tasks A,B,C but regresses on D — average looks fine, but D-tasks now silently fail. Naively shipping the average-improved evolved tool degrades real-world UX.

**Why it happens:**
- Dashboards default to means/medians, not distributions.
- "2pp threshold" (per ROADMAP Phase 16) is on the aggregate, not per-task-segment.
- v1 CrossToolRegressionChecker exists at the per-tool level — Phase 16 must extend, not replace.

**Prevention strategy:**
- Dashboard reports distribution (min, p25, median, p75, max per-tool selection rate) AND aggregate. Surface tools with high variance.
- Regression gate operates on the WORST-decile, not the mean. "No tool's selection rate drops >2pp at p25" is a stronger gate than "no tool's mean drops >2pp."
- Add per-task-segment breakdown (e.g., by difficulty, by tool count in candidate pool) to dashboard output.
- Storage budget: cap metrics history at 90 days or 1000 runs per tool. Otherwise dashboard storage grows unboundedly.

**Phase plan should address explicitly:** **Phase 16 plan** must specify distribution-aware metrics, p25-based regression gate, retention policy.

**Confidence:** MEDIUM

---

### Pitfall 11: GEPA Reflection_LM Cost Underestimated

**What goes wrong:**
Per commit 262402a, GEPA was fixed by passing `reflection_lm=optimizer_model`. The reflection LM is invoked on every failed evaluation to propose mutations. With v2's larger datasets (Phase 14 mining → 200-400 examples) and joint optimization (Phase 17 → 5 sections at once), reflection_lm calls scale super-linearly. Hidden cost: reflection model is `optimizer_model` (gpt-4.1, expensive), not `eval_model` (gpt-4.1-mini).

**Why it happens:**
- `reflection_lm=optimizer_model` is a recent compatibility fix; cost implications not yet measured at v2 scale.
- v1 datasets are small (20 examples) so reflection_lm cost was rounding error.
- Documentation/CLI doesn't expose reflection_lm token usage separately; users see total spend, not the breakdown.

**Prevention strategy:**
- Add token accounting: log reflection_lm vs eval_model vs optimizer_model token consumption separately in `metrics.json`.
- Allow `EvolutionConfig.reflection_model` to differ from `optimizer_model` — let users use a cheaper reflection model when budget-constrained.
- Set `max_metric_calls` defaults conservatively for v2 phases (currently `iterations * 50` — re-evaluate at v2 dataset sizes).
- Document expected cost ranges per v2 phase in plan files (Phase 13: $X, Phase 17: $Y, etc.) BEFORE running, then compare to actuals as acceptance signal.

**Phase plan should address explicitly:** **Phase 13, 15, 17, 19, 20** plans each must include a "Cost projection" section listing expected $/run and the basis for the estimate.

**Confidence:** MEDIUM-HIGH (cost dynamics inferred from GEPA architecture; commit 262402a confirms reflection_lm wiring)

---

### Pitfall 12: GEPA 5-Param Metric Signature Drift on New Phases

**What goes wrong:**
Per commit 262402a, GEPA requires metric signature `(gold, pred, trace, pred_name, pred_trace)` — 5 params, not the older 2-param `(gold, pred)`. Phase 13–22 each introduce new metrics (per-param metric, joint-section metric, etc.). If any new metric reverts to 2-param style (because copy-pasted from v1 Phase 1 era code, or DSPy docs example), GEPA silently falls back to MIPROv2 (per evolve_skill.py fallback path) — losing GEPA's reflective benefit.

**Why it happens:**
- Old DSPy examples and Stack Overflow answers use 2-param signature.
- The fallback path in `evolve_skill.py` catches the exception and continues, so the failure is silent — yellow warning, then proceeds.
- Phase plans don't enforce signature checking.
- Type system can't enforce DSPy callable signature.

**Prevention strategy:**
- Add a DSPy-version-aware unit test for every new metric: import the metric, assert signature has 5 positional params (use `inspect.signature`).
- Convert the silent fallback to LOUD: the GEPA-to-MIPROv2 fallback in v2 should fail-fast (raise) unless `--allow-miprov2-fallback` flag set. Silent fallback hid the bug originally.
- Document the canonical metric signature in `evolution/core/fitness.py` module docstring as the reference implementation.

**Phase plan should address explicitly:** **Phase 13, 15, 17, 19, 20** plans must reference the 5-param signature as a Test-First requirement (TDD). Add to Phase 12 follow-up: turn off silent MIPROv2 fallback or make it loud.

**Confidence:** HIGH (commit 262402a is direct evidence of this pitfall already happening once)

---

### Pitfall 13: Continuous Loop (Phase 22) Without Idempotency Checks

**What goes wrong:**
Phase 22 schedules optimization runs, validates, and creates PRs. Without idempotency checks: scheduler retries on failure, creates duplicate PRs; concurrent runs race on the same artifact; PR creation logic bugs spam the hermes-agent repo with N PRs per skill. "Human review required" is the stated safety net, but spamming reviewers is also a failure mode.

**Why it happens:**
- v1 has no scheduler. Phase 22 is the first entry into "automated, repeated, multi-tenant" execution.
- No PR-creation logic exists yet — naive implementation calls `gh pr create` without checking existing open PRs.
- Concurrency model unspecified.

**Prevention strategy:**
- PR creation requires a "PR for this artifact already exists" check via `gh pr list --search`. Update existing PR rather than creating new.
- Mutex / lock file per artifact to prevent concurrent runs on the same target.
- Idempotency key in metrics output: `{artifact_hash}-{config_hash}-{dataset_hash}` → if same key already produced, skip.
- Rate limit PR creation: ≤1 PR per skill/tool/section per 7 days, configurable.
- "Dry-run by default" — Phase 22 ships in dry-run mode initially; enable PR creation only after manual confirmation that pipeline is safe.

**Phase plan should address explicitly:** **Phase 22 plan** must specify idempotency strategy, concurrency model, PR rate limit, and dry-run-default policy.

**Confidence:** MEDIUM-HIGH

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Reuse v1 `tool_selection_metric` for Phase 13 per-param | Skip metric design work | Per-param has different fitness shape; v1 metric blind to param-level signal | Never — Phase 13 needs its own metric |
| Default `reflection_lm` to `optimizer_model` (current state) | Works without configuration | 5–10× hidden cost at v2 dataset scale | Acceptable for v1 dataset sizes; revisit at Phase 13+ |
| Direct `import darwinian_evolver` in `evolution/code/` | Faster prototyping | AGPL contamination, irreversible without git history surgery | Never — subprocess only |
| Skip session import format-version assertion | Less code | Silent dataset shrinkage on hermes-agent upgrade | Never — assert + audit required |
| Calibrate drift threshold by intuition | Skip building labeled set | High false-positive rate, users disable gate | Never — labeled calibration set is mandatory |
| Run TBLite gate inside GEPA loop | Simpler architecture | Optimization runs measured in weeks, $1000+ | Never — final-gate-only |
| 2-param metric signature (DSPy old style) | Easier copy-paste from old docs | Silent MIPROv2 fallback, lose GEPA benefit | Never — assert signature in tests |
| Mine only failure cases for SessionDB | "High value" appearance | Distribution skew, success regressions | Never — must include success cases |
| Joint optimization without per-section gate | Higher reported scores | Hides per-section regressions | Never — per-section gate non-optional |
| Auto-merge PRs from continuous loop | Faster delivery | Bad evolved artifacts ship silently | Never — explicit human review per PROJECT.md Out of Scope |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| DSPy GEPA constructor | Pass 2-param metric → silent MIPROv2 fallback | Pass 5-param metric `(gold, pred, trace, pred_name, pred_trace)` + assert signature in test |
| DSPy GEPA constructor | Omit `reflection_lm` → GEPA refuses to run | Always pass `reflection_lm=dspy.LM(config.optimizer_model, ...)` (per commit 262402a pattern) |
| DSPy GEPA budget | Set `max_steps` (old API) | Use `max_metric_calls` per v2 baseline |
| `darwinian-evolver` | `import darwinian_evolver` in non-isolated module | Subprocess via isolated venv only |
| hermes-agent session files | Assume schema is stable across versions | Read & assert `session_schema_version`, fail loud on unknown major |
| TBLite benchmark | Wire into GEPA inner loop as metric | Call ONCE on top-K candidates as final gate, with median-of-3 noise mitigation |
| Mined session datasets | Treat as freely shareable | Treat as private (gitignored, retention TTL, sanitization audit) |
| `EvolutionConfig` extension | Add v2 fields directly to v1 dataclass | Use composition / subclass to keep v1 contract stable for the 329-test baseline |
| GEPA reflection_lm | Reuse `eval_model` (cheaper) | reflection_lm is reasoning-quality-sensitive; use `optimizer_model` BUT log token usage separately |
| Continuous loop PRs | Each scheduled run creates new PR | Update existing PR by artifact hash; rate-limit per artifact |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Phase 13 combinatorial param explosion | Optimization budget exhausted before Pareto stable | Cap params optimized per generation (3-of-N), document cap | Tools with >5 params |
| Phase 15 reasoning token blow-up | 3-10× cost vs. v1 baseline | Hybrid routing (think only on ambiguous), 200-token reasoning cap | All tools, all queries |
| Phase 17 joint mutation interaction | GEPA stalls, Pareto front clusters near baseline | Cap simultaneous mutations to 2 sections, per-section regression gate | 5+ sections optimized jointly |
| Phase 20 TBLite-in-loop | Optimization runs measured in days/weeks | Final-gate-only architecture, artifact-hash caching | Any GEPA run with benchmark gating in inner loop |
| Phase 22 metric storage bloat | `output/metrics/` directory grows unboundedly | Retention policy: 90-day or 1000-run cap per artifact | After ~6 months of continuous loop |
| reflection_lm cost at scale | Total optimization spend 5-10× v1 baseline | Log reflection_lm tokens separately; allow cheaper reflection_model | Phase 14+ datasets (200+ examples) |
| Synchronous LLM scoring (carryover from v1 CONCERNS) | Wall-clock dominates | Async via `dspy.asyncify` or batching | Datasets >100 examples |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Mine session data without consent prompt | Privacy violation, GDPR/SOC2 issues | Explicit `--i-have-consent` flag with file-list preview |
| Rely on regex-only secret detection for session mining | API keys leak into datasets and committed artifacts | 3-layer pipeline: regex + NER + entropy heuristic |
| Commit mined datasets to git | Irreversible PII leak in git history | Datasets under `datasets/private/` (gitignored) with TTL |
| AGPL contamination via direct import | License obligations propagate to v1 components | Subprocess + isolated venv + CI lint check |
| Auto-PR mined-data-trained artifacts | Verbatim PII echoes into hermes-agent codebase | No-verbatim-copy constraint enforced before PR creation |
| Run evolved code from darwinian-evolver in hermes-agent runtime | Code execution of unreviewed LLM-generated code | Output to `output/code-evolved/`, NOTICE.md, mandatory human review |
| `subprocess.run(cwd=hermes_repo)` without validation (carryover from v1) | Path traversal / wrong-repo execution | Validate cwd is git repo + contains expected files |
| Continuous loop creates PRs at unbounded rate | Reviewer DoS, accidental bad-PR merge | Rate limit + dry-run-default + idempotency check |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Drift detector false positives (Pitfall 6) | Users disable gate via flag | F1-calibrated threshold; multi-dimensional output explains "what kind of drift" |
| Phase 16 dashboard shows only averages | Users miss tail regressions | Show distribution (min/p25/median/p75/max) per tool |
| Silent MIPROv2 fallback (commit 262402a context) | Users think GEPA ran when it didn't | Loud fallback with explicit `--allow-miprov2-fallback` opt-in |
| Phase 15 cost spike unexplained | Users surprised by bill | Cost projection in CLI output before run starts; halt at `max_cost_usd` |
| TBLite gate failure says "rejected" with no detail | Users can't tell flake vs. real regression | Output median-of-3 scores + variance; suggest re-run if variance high |
| Session import doesn't show what was filtered | Users distrust mining | Audit CLI subcommand showing per-stage drop counts |

---

## "Looks Done But Isn't" Checklist

- [ ] **Phase 13 per-param optimization:** Often missing → param consistency constraint. Verify: synthetic test with intentionally inconsistent param descriptions gets rejected by `ConstraintValidator`.
- [ ] **Phase 14 SessionDB mining:** Often missing → entropy-based secret detection (regex + NER alone leak high-entropy non-pattern tokens). Verify: planted JWT/AWS-key fixtures in test session caught.
- [ ] **Phase 14/19 mining:** Often missing → opt-in consent flag. Verify: running CLI without `--i-have-consent` aborts with clear message.
- [ ] **Phase 15 think-augmented:** Often missing → cost/latency tracking in metric. Verify: `metrics.json` includes `tokens_per_selection`, `latency_ms`.
- [ ] **Phase 17 joint mode:** Often missing → per-section regression gate. Verify: synthetic candidate where 1 section regresses 5pp gets rejected even when joint score improves.
- [ ] **Phase 18 drift detector:** Often missing → labeled calibration set. Verify: F1-on-labeled-set documented in plan + threshold derivation reproducible.
- [ ] **Phase 20 benchmark gating:** Often missing → outside-GEPA-loop architecture. Verify: GEPA runs with `--benchmark` only call TBLite on top-K candidates, not per generation.
- [ ] **Phase 21 darwinian:** Often missing → CI lint check forbidding `import darwinian_evolver` outside `evolution/code/darwinian_runner.py`. Verify: lint added to pre-commit + CI; deliberate violation in test branch fails CI.
- [ ] **Phase 21 darwinian:** Often missing → LICENSE.md at repo root. Verify: LICENSE file present BEFORE Phase 21 work begins.
- [ ] **Phase 22 continuous loop:** Often missing → idempotency check (artifact_hash). Verify: running scheduler twice on unchanged artifact creates 0 new PRs.
- [ ] **All v2 phases:** Often missing → 5-param GEPA metric signature test. Verify: per-phase metric module has `test_metric_signature` asserting `inspect.signature` returns 5 positional params.
- [ ] **All v2 phases:** Often missing → reflection_lm cost logging. Verify: `metrics.json` has `reflection_lm_tokens` separate from `eval_model_tokens`.
- [ ] **All v2 phases:** Often missing → v1 baseline regression gate. Verify: every v2 phase plan has explicit "v1 holdout score not regressed" acceptance criterion.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Pitfall 1 (per-param incoherence shipped) | LOW | Revert to v1 top-level optimization, drop the evolved per-param outputs, add param_consistency constraint, re-optimize |
| Pitfall 2 (PII leaked to git) | HIGH | git history rewrite (filter-branch / BFG), rotate any leaked credentials, notify affected users, post-mortem; if PII committed to public PR, may require taking the PR down + reaching out to GitHub support |
| Pitfall 3 (AGPL contamination) | HIGH | Audit imports, rip out direct `import darwinian_evolver`, retroactive LICENSE clarification, notify any downstream users; if redistributed under non-AGPL terms, may need legal counsel |
| Pitfall 4 (Phase 15 cost spike in production) | LOW | Disable Phase 15 (revert to v1 direct selection), keep think-augmented as opt-in only, add hybrid routing as fix |
| Pitfall 5 (Phase 17 ships regressions) | MEDIUM | Revert to v1 round-robin (Phase 8); per-section diff to identify which section regressed; re-optimize that section in isolation |
| Pitfall 6 (drift detector miscalibrated) | LOW | Adjust threshold using F1-optimization on labeled set; previously-rejected candidates re-evaluated with new threshold |
| Pitfall 7 (TBLite-gated runs unaffordable) | MEDIUM | Move TBLite out of GEPA loop, refund-from-cache previously-computed scores, document new architecture |
| Pitfall 8 (session schema drift undetected) | MEDIUM | Audit count comparison vs. previous run reveals drop; update parser; re-run mining |
| Pitfall 11 (reflection_lm cost surprise) | LOW | Switch to cheaper reflection_model; truncate `max_metric_calls`; document cost projection retroactively |
| Pitfall 12 (silent MIPROv2 fallback) | LOW | Add metric signature test; fix fallback to be loud; re-run optimization with proper GEPA |
| Pitfall 13 (PR spam from continuous loop) | LOW | Disable scheduler; manually close duplicate PRs via `gh pr close`; add idempotency check before re-enabling |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Per-param incoherence | Phase 13 | param_consistency constraint test passes; v1 baseline regression gate in plan |
| 2. SessionDB PII leakage | Phase 14 (primary), Phase 19 (reuse), Phase 22 (PR gate) | Sanitization pipeline integration test with planted secrets/PII |
| 3. AGPL contamination | Phase 21 (architectural) + LICENSE.md prerequisite | CI lint check in repo + LICENSE.md present before Phase 21 starts |
| 4. Think-augmented cost/latency | Phase 15 | `metrics.json` includes token + latency tracking; A/B holdout acceptance criterion in plan |
| 5. Joint section credit-assignment | Phase 17 | Per-section regression gate test; round-robin remains default |
| 6. Drift detector calibration | Phase 18 | Labeled calibration set in plan; F1-derived threshold; pairwise scoring |
| 7. TBLite gate flakiness | Phase 20 | Outside-GEPA-loop architecture; median-of-3; artifact-hash caching |
| 8. Session schema drift | Phase 14 | Schema version assertion + audit CLI in plan |
| 9. Failure-only mining bias | Phase 14 | Documented success:failure ratio; per-class metric tracking |
| 10. Dashboard misleading averages | Phase 16 | Distribution (p25/median/p75) reported; p25-based regression gate |
| 11. reflection_lm cost | Phase 13, 15, 17, 19, 20 | Per-phase cost projection in plan; reflection_lm token logging |
| 12. 5-param metric signature drift | Phase 13, 15, 17, 19, 20 | Per-phase metric signature unit test; loud (not silent) MIPROv2 fallback |
| 13. Continuous loop idempotency | Phase 22 | Idempotency-key check; PR rate limit; dry-run default |

**Cross-phase prevention** (no single phase owns):
- v1 regression gate: every v2 phase plan must include "v1 holdout score not regressed" as acceptance criterion (recheck via existing 329-test suite + v1 dry-run).
- 5-param metric signature: enforce as universal TDD pattern across all v2 metrics.
- Cost projection: every v2 phase plan must include $/run estimate before implementation.

---

## Sources

- v1 PITFALLS.md (preserved domain-level pitfalls — companion to this document)
- `.planning/codebase/CONCERNS.md` — v1 codebase tech debt audit (e.g., session sensitive data, secret regex limits, naive YAML parsing, GEPA fallback hidden behavior)
- `.planning/codebase/ARCHITECTURE.md` — v1 layer architecture (constraint, fitness, module, orchestration)
- `.planning/ROADMAP.md` — v2 milestone Phase 12-22 specifications
- `.planning/REQUIREMENTS.md` — v2 requirement definitions (TOOL-V2-*, PMPT-V2-*, V2-CODE-*, V2-LOOP-*)
- Commit `262402a` (`fix: GEPA compatibility — 5-param metric signature + reflection_lm`) — direct evidence of GEPA signature pitfall (Pitfall 12) and reflection_lm wiring
- Commit `cdc2f4a` (`feat: add multi-model backend support via evolution.yaml`) — multi-model config infrastructure used in cost-projection prevention
- DSPy GEPA documentation patterns observed in `evolution/tools/evolve_tool_descriptions.py` and `evolution/prompts/evolve_prompt_sections.py`
- AGPL §13 network-use clause (engineering practice, OSS legal literature) — basis for Pitfall 3 prevention
- CLAUDE.md project constraints — `darwinian-evolver` AGPL declaration; max sizes for tool descriptions / prompts
- Dropbox Dash DSPy case study (verbatim copy failure mode) — referenced via v1 PITFALLS Pitfall 3, applies to Phase 14/19 mining
- LLM-as-Judge instability survey (referenced in v1 PITFALLS Pitfall 2) — basis for Pitfall 6 (drift) and Pitfall 7 (benchmark) noise mitigation

---

*Pitfalls research for: v2.0 milestone (Phases 13-22)*
*Researched: 2026-04-23*
*Companion to v1 PITFALLS.md (domain-level baseline)*
