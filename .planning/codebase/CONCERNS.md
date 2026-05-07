# Codebase Concerns

**Analysis Date:** 2026-05-06
**Active Context:** v2.0 milestone — Phase 13 (per-parameter tool description optimization) is next.
**Cross-references:** `.planning/research/PITFALLS.md` (v2 pitfalls), v1 PITFALLS.md (domain-level baseline).

---

## Severity Legend

- **HIGH** — Will break a current pipeline run or cause silent quality regression / data loss / security incident.
- **MED** — Latent risk that becomes load-bearing at v2 dataset scale (Phase 13+) or under specific (but realistic) inputs.
- **LOW** — Smell / hygiene issue. No immediate harm, but compounds with other concerns.

---

## HIGH Severity

### H1. `evolve_skill.py` Uses Old GEPA API and 3-param Metric Signature — Silent MIPROv2 Fallback

- Files:
  - `evolution/skills/evolve_skill.py` lines 156-177 (uses `max_steps=iterations`, OLD GEPA API)
  - `evolution/core/fitness.py` lines 107-136 (`skill_fitness_metric(example, prediction, trace=None)` — 3 params)
- Why it matters:
  Commit `262402a` documents the GEPA fix as "5-param metric signature + reflection_lm" — but that fix landed only in `evolution/tools/evolve_tool_descriptions.py:184-190` and `evolution/prompts/evolve_prompt_sections.py:252-258`. The skill pipeline was left untouched. Today, `dspy.GEPA(metric=skill_fitness_metric, max_steps=iterations)` will:
    1. Reject `max_steps` (renamed to `max_metric_calls`), OR
    2. Reject 3-param metric (GEPA expects `(gold, pred, trace, pred_name, pred_trace)`), OR
    3. Refuse to run because `reflection_lm` is missing.
  Any of these triggers the `try/except` at line 167 → silently falls back to MIPROv2. Users believe GEPA's reflective optimization ran when it didn't. This is **Pitfall 12** from `.planning/research/PITFALLS.md` realized in current code, with **direct evidence in HEAD**.
- Suggested mitigation:
  - Rewrite `skill_fitness_metric` to 5-param signature `(example, prediction, trace=None, pred_name=None, pred_trace=None)`. Mirror the pattern in `evolution/tools/tool_metric.py` lines 18-45.
  - Replace `max_steps=iterations` with `max_metric_calls=iterations * 50` and add `reflection_lm=dspy.LM(config.optimizer_model, **config.get_lm_kwargs())`.
  - Convert silent fallback to **loud** — raise unless `--allow-miprov2-fallback` flag set (per Pitfall 12 prevention).
  - Add a unit test: `inspect.signature(skill_fitness_metric).parameters` length == 5.
- Tracked under: v2-STAB-02 / Phase 12 follow-up. Block v2 work until fixed.

### H2. `generate_report.py` Imports Undeclared `reportlab` Dependency

- Files:
  - `generate_report.py` lines 3-12 (imports `reportlab.lib`, `reportlab.platypus`, etc.)
  - `pyproject.toml` lines 17-32 (no `reportlab` in `[project.dependencies]` or `[project.optional-dependencies]`)
- Why it matters:
  Fresh `pip install -e .` produces an environment where `python generate_report.py` immediately raises `ModuleNotFoundError: No module named 'reportlab'`. CLAUDE.md / STACK research even calls out reportlab as "(not declared in pyproject.toml dependencies)." This breaks the documented Phase 1 validation report workflow.
- Suggested mitigation:
  - Add `[project.optional-dependencies] reports = ["reportlab>=4.0"]` to `pyproject.toml`. Document `pip install .[reports]` in README.
  - Or: move PDF generation to a Markdown report (no PDF dep) and delete the reportlab path entirely. Phase 1 report is one-shot and unlikely to be regenerated.
- Tracked under: v2-STAB-01 (dependency hygiene).

### H3. `evolve_skill.py` Bypasses Multi-Model Backend Config (`evolution.yaml` / EVOLUTION_API_*)

- Files:
  - `evolution/skills/evolve_skill.py` line 49 (uses raw `EvolutionConfig(...)` constructor)
  - `evolution/skills/evolve_skill.py` line 141 (`lm = dspy.LM(eval_model)` — no `**config.get_lm_kwargs()`)
  - Compare to `evolution/tools/evolve_tool_descriptions.py` line 92 (uses `EvolutionConfig.load(...)`) and line 174 (passes `**config.get_lm_kwargs()`).
  - `evolution/prompts/evolve_prompt_sections.py` lines 100 / 208 — same correct pattern as tools.
- Why it matters:
  The Phase 12 multi-model backend (commit `cdc2f4a`) added `evolution.yaml`, `EVOLUTION_API_BASE`, `EVOLUTION_API_KEY`, `EVOLUTION_MODEL`, and CLI `--model` / `--api-base` overrides. Tool and prompt CLIs honor all three layers. The skill CLI honors only `--optimizer-model` and `--eval-model` flags — it ignores YAML, env vars, and never injects `api_base` / `api_key` into `dspy.LM`. Users who configured Qwen / OpenRouter / local-vLLM via `evolution.yaml` will get an OpenAI default when running `evolve_skill.py` and may pay an unexpected bill or hit unauthenticated errors.
- Suggested mitigation:
  - Replace `EvolutionConfig(iterations=..., optimizer_model=..., ...)` with `EvolutionConfig.load(iterations=iterations, model=optimizer_model or eval_model, hermes_repo=hermes_repo, ...)`.
  - Add `--model` / `--api-base` Click options to match the other two CLIs (lines 400-407 of `evolve_tool_descriptions.py` is the canonical pattern).
  - Pass `**config.get_lm_kwargs()` everywhere `dspy.LM(...)` is called (currently line 141, 75 inside `LLMJudge.score()`).
- Tracked under: v2-STAB-02 (verify all three evolve_* CLIs honor backend override).

### H4. `output/` Directory NOT in `.gitignore` — Risk of Committing Generated Artifacts (and Embedded Mined Data)

- Files:
  - `.gitignore` (no `output/` rule; covers `__pycache__/`, `.venv/`, `evolution.yaml`, `datasets/**/*.jsonl`, `snapshots/`, but NOT `output/`).
  - `output/` actually exists at repo root with `prompts/`, `skills/`, `tools/` subdirs.
- Why it matters:
  - Each `evolve_*` run writes `metrics.json`, `evolved_*.json`, `diff.txt`, `baseline_*` files to timestamped `output/<phase>/<timestamp>/`. Without ignore, `git add -A` (or accidental `git add output/`) pulls them in.
  - When Phase 14 SessionDB mining lands (`.planning/research/PITFALLS.md` Pitfall 2), evolved artifacts may contain verbatim mined PII / API keys. Committing them is **irreversible** (git history rewrite required for recovery).
  - The repo already tolerated `output/` showing up in `git status` without a tracking gate.
- Suggested mitigation:
  - Add `output/` to `.gitignore` immediately. Optionally `!output/.gitkeep` to preserve the directory.
  - Add a retention policy: cap to last N runs per artifact type or 30-day TTL via a `evolution/cli/clean_output.py` utility.
  - Once Phase 14 is in-flight, also gitignore `datasets/private/` per Pitfall 2 prevention plan.
- Tracked under: v2-STAB-01 (must precede Phase 14 mining work).

### H5. `evolution.yaml` Contains Real API Key — Gitignored But Plaintext on Disk

- Files:
  - `evolution.yaml` (gitignored — "User config (contains API keys)").
  - `evolution.example.yaml` (template — safe).
- Why it matters:
  The current working `evolution.yaml` contains a live API key for DashScope (Qwen). It is correctly gitignored, but:
    - Plaintext-on-disk credentials at the repo root are a known leak vector when developers share screenshots, copy directories, or run `tar`/`zip` of the workspace for backup or AI tooling uploads.
    - There is no validation gate that asserts `evolution.yaml` ≠ tracked-in-git. A future developer might `git add -f evolution.yaml`.
    - The file is read by `EvolutionConfig.load()` in `evolution/core/config.py` lines 73-88; nothing logs WHICH file the key came from, so a reviewer reading `metrics.json` cannot tell if the bill went to a personal or shared key.
- Suggested mitigation:
  - Document in README that `evolution.yaml` MUST set `api_key` to an env-var reference (e.g. `api_key: "${DASHSCOPE_KEY}"`) and add expansion logic to `EvolutionConfig.load()`.
  - Add a pre-commit hook (or `make precommit-check`) that fails if `evolution.yaml` is staged.
  - Rotate the current key out-of-band and replace with env-var reference. (Not part of code work — operational task.)
- Tracked under: v2-STAB-01 (security hygiene before any v2 phase).

---

## MED Severity

### M1. No Lockfile — DSPy 3.x Breaking Change Already Bit the Project Once

- Files:
  - `pyproject.toml` lines 17-23 (only minimum-version constraints: `dspy>=3.0.0`, `openai>=1.0.0`, etc.)
  - No `requirements.txt`, `poetry.lock`, `uv.lock`, `Pipfile.lock`, or `pdm.lock` in repo root.
- Why it matters:
  - Commit `262402a` ("fix: GEPA compatibility — 5-param metric signature + reflection_lm") is direct evidence: a DSPy upgrade silently broke the metric contract. Without a lockfile, every fresh clone gets the latest matching `dspy` and may break in new ways.
  - v2.0 work (Phases 13–22) plans 200–400-example datasets and joint-section optimization. A DSPy upgrade landing mid-phase would invalidate in-flight optimization runs ($30-100 sunk cost per run per Pitfall 4).
  - `darwinian-evolver` is unversioned in `[optional-dependencies.darwinian]`; AGPL contamination risk (Pitfall 3) is amplified if a future version changes its import surface.
- Suggested mitigation:
  - Generate a lockfile via `pip-compile` (pyproject-build-pinned) or migrate to `uv` (`uv lock`). Pin DSPy to a tested patch range (e.g. `dspy>=3.0.0,<3.2.0`).
  - Add a `make freeze` and CI job that asserts `pip-compile --check` matches the lockfile.
  - Document the verified DSPy patch version in README's "Verified Compatibility" section.
- Tracked under: v2-STAB-01.

### M2. GEPA Fallback Is Silent — Hides Future Breakage Behind a Yellow Print

- Files:
  - `evolution/skills/evolve_skill.py` lines 167-177
  - `evolution/tools/evolve_tool_descriptions.py` lines 196-206
  - `evolution/prompts/evolve_prompt_sections.py` lines 264-284
- Why it matters:
  - All three pipelines wrap `dspy.GEPA(...)` in `try/except Exception` and fall back to `dspy.MIPROv2`. The exception message is printed in yellow and execution continues. MIPROv2 has different semantics (no reflective trace, no `reflection_lm`), so the resulting evolved artifact is qualitatively different but indistinguishable in `metrics.json` (which records `optimizer_model` but not the actually-used optimizer name).
  - The fix from commit `262402a` was *itself* a reaction to a silent fallback. Future DSPy upgrades will fall into the same trap.
  - Per Pitfall 12 prevention strategy: "Convert the silent fallback to LOUD — fail-fast unless `--allow-miprov2-fallback` flag set."
- Suggested mitigation:
  - Add `--allow-miprov2-fallback` flag (default off). Without it, re-raise the exception with a clear message including the original GEPA error.
  - Record `optimizer_used: "gepa"|"miprov2"` in `metrics.json` so post-hoc audits can detect silent fallbacks in past runs.
  - Add a per-pipeline metric-signature unit test (per Pitfall 12: `inspect.signature(metric).parameters` == 5).
- Tracked under: Phase 12 follow-up + Phase 13 prerequisite.

### M3. Cross-Tool Regression Gate Is Pass/Fail Only — No Per-Tool Persistence for Phase 13 Fan-Out

- Files:
  - `evolution/tools/tool_metric.py` lines 72-187 (`CrossToolRegressionChecker`)
  - `evolution/tools/evolve_tool_descriptions.py` lines 308-327 (only consumes `passed` / `regressed_tools`)
  - `evolution/tools/evolve_tool_descriptions.py` lines 365-378 (`metrics.json` schema — no per-tool field)
- Why it matters:
  - Today's check reports per-tool delta in a Rich table at run-time, but `metrics.json` records only aggregate `baseline_score` / `evolved_score`. There is no persistent per-tool record across runs.
  - Phase 13 fans out optimization to per-parameter (~50 tools × 3 avg params = ~150 optimizable units). Description theft (Pitfall 1: "tool X improved by stealing semantics from tool Y") becomes geometrically more likely.
  - Pitfall 10 from v2 research: dashboard must report **distribution** (min/p25/median/p75/max) and operate the regression gate on **p25**, not the mean.
- Suggested mitigation:
  - Persist per-tool rates to `metrics.json` (`per_tool_baseline_rates`, `per_tool_evolved_rates`).
  - Add a `param_consistency` LLM check in `ConstraintValidator` (Pitfall 1 prevention): scan all params + top-level for self-contradictions before fitness scoring.
  - Cap optimization fan-out: `if len(params) > 5`, optimize 3 params at a time with rest frozen (Pitfall 1 prevention #3).
- Tracked under: Phase 13 plan must include this as an explicit acceptance criterion (this is also planned as Phase 16, but Phase 13 cannot ship without at least the persistence piece).

### M4. LLM-Output Parsing Is Brittle — Silent Score Degradation on Format Drift

- Files:
  - `evolution/core/external_importers.py` lines 546-600 (`_parse_scoring_json` — try/except + brace-counting fallback)
  - `evolution/core/dataset_builder.py` lines 137-145 (try/except + regex extraction fallback)
  - `evolution/core/fitness.py` lines 139-146 (`_parse_score` — clamps to `[0, 1]`, defaults to **0.5** on parse failure)
- Why it matters:
  - When upstream LLMs change their output format (e.g. adding leading "```json" fences, restructuring schema), parse failure silently degrades quality:
    - `_parse_score` returning 0.5 on failure means a model that breaks JSON output gets a middling score instead of 0 — GEPA's reflective trace gets misleading signal.
    - `_parse_scoring_json` returns `None` on failure → the importer just increments `errors` counter and continues. Error rate is reported but not used to halt or trigger re-run.
  - At v2 dataset scale (Phase 14: 200-400 examples), a 30% silent parse-failure rate is plausible and would drag GEPA toward arbitrary directions.
  - Pitfall 11: reflection_lm cost is super-linear at v2 scale; wasting it on parse-failure-induced noise is doubly expensive.
- Suggested mitigation:
  - Use `dspy.OutputField(desc=..., type=float)` typed outputs in DSPy 3.x where supported, replacing manual parse logic.
  - Add an error-rate threshold: if `errors / total > 0.2`, halt and emit a clear "LLM output format may have drifted, re-run with verbose mode" message instead of silently completing.
  - Replace 0.5 default in `_parse_score` with **0.0** + log to `metrics.json["parse_failures"]`. Misses that produce 0 are visible; misses that produce 0.5 are invisible.
- Tracked under: Phase 13 (new metric design) and Phase 14 (mining at scale).

### M5. `SECRET_PATTERNS` Coverage Is Regex-Only and Pattern-Shallow

- Files:
  - `evolution/core/external_importers.py` lines 45-70 (`SECRET_PATTERNS`)
  - Used by `_contains_secret()` line 78-80 — called in 3 importers.
- Why it matters:
  - Current patterns: `sk-ant-api`, `sk-or-v1-`, `sk-\S{20,}`, `ghp_`, `ghu_`, `xoxb-`, `xapp-`, `ntn_`, `AKIA[0-9A-Z]{16}`, `Bearer\s+\S{20,}`, RSA private key headers, plus exact env-var-name strings (`ANTHROPIC_API_KEY`, etc.) and `password=`/`secret=`/`token=` assignments.
  - Gaps confirmed against Pitfall 2 prevention strategy:
    - **JWT regex missing**: no `eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+` pattern — `Bearer\s+\S{20,}` only catches JWTs preceded by literal `Bearer `.
    - **OAuth bearer with non-standard prefix** not caught.
    - **Internal hostnames, employee names, customer IDs** (PII per Pitfall 2) not detected at all.
    - **Generic high-entropy tokens** (32+ char base64) not detected.
    - **NER-based PII** (PERSON, ORG, EMAIL, PHONE, IP) requires `spacy`/Presidio — not in deps.
  - Phase 14 SessionDB mining (TOOL-V2-01) drastically expands the surface. Today's gate is sufficient for skill mining (small surface) but undersized for v2.
- Suggested mitigation:
  - Add the JWT pattern, AWS-secret pattern (`[a-zA-Z0-9/+=]{40}` adjacent to `aws`), and entropy heuristic (Shannon entropy > 4.0 over 24+ char tokens) per Pitfall 2 prevention #1.
  - Layer 2 (NER): introduce `evolution/core/privacy.py` with optional `spacy` / Presidio dependency. Gate behind `[project.optional-dependencies].privacy`.
  - Layer 3: add the `--i-have-consent` flag to importers per Pitfall 2 #3 (BEFORE any read).
  - Add a sanitization audit step (per Pitfall 2 #4) — LLM check "does this dataset contain PII or secrets?"
- Tracked under: Phase 14 plan must include all three sanitization layers.

### M6. `hermes-agent` Repo Is Not Read-Only-Enforced — Write-Back Functions Exist

- Files:
  - `evolution/core/config.py` lines 120-145 (`get_hermes_agent_path` — discovery only, no read-only assertion).
  - `evolution/tools/tool_loader.py` line 578 (`file_path.write_text(source)` in `write_back_description`).
  - `evolution/prompts/prompt_loader.py` line 182 (`prompt_builder_path.write_text(...)` in section write-back).
- Why it matters:
  - The architecture doc and CLAUDE.md both state hermes-agent is "read-only" — but the code path **can** write to it via `write_back_description` and the prompt loader's section replacement. These are intentional Phase 13/22 hooks (auto-PR loop), but they are not gated by an explicit "deploy mode" flag.
  - A typo, a stray script, or a future Phase 22 idempotency bug (Pitfall 13) could clobber `hermes-agent/tools/*.py` or `hermes-agent/agent/prompt_builder.py` before review.
  - There is no `dry_run` parameter on `write_back_description` — it always writes.
  - The `hermes-agent` path is resolved without verifying it's a git repo or that the working tree is clean.
- Suggested mitigation:
  - Add a `EvolutionConfig.deploy_mode: bool = False` flag. `write_back_description` and section write-back must assert `config.deploy_mode is True` or raise.
  - Validate that `hermes_agent_path / ".git"` exists and `git status --porcelain` is clean before any write-back. Refuse to write to a dirty tree.
  - Add a `--dry-run-write` flag that prints the diff but does not call `.write_text()`.
- Tracked under: Phase 13 write-back integration; Phase 22 continuous loop hardening.

### M7. JSONL Loaders Abort on Single Bad Line — No Skip-and-Continue

- Files:
  - `evolution/core/dataset_builder.py` lines 62-75 (`EvalDataset.load`) — line `examples.append(EvalExample.from_dict(json.loads(line)))` will raise on first malformed line.
  - `evolution/core/dataset_builder.py` lines 186-190 (`GoldenDatasetLoader.load`) — same pattern.
  - Compare to `evolution/core/external_importers.py` lines 185-188 — the importer DOES catch `json.JSONDecodeError` per-line and continue. Inconsistent within the same module family.
- Why it matters:
  - Dataset files are written by `EvalDataset.save()` (lines 54-60 — atomic-per-file but no per-line validation). A power-loss / disk-full event during write produces a truncated last line that aborts all future loads of that split.
  - User-provided `golden.jsonl` files (TIER 1 golden datasets) often have hand-edited last lines. One typo permanently breaks load.
  - Auto-importers from session data (Phase 14) will produce 100s of MB of JSONL — partial writes are realistic.
- Suggested mitigation:
  - Wrap per-line `json.loads(line)` in `try/except json.JSONDecodeError` and increment a `skipped` counter.
  - Log skip count (warn if > 5% of lines).
  - Add `EvalDataset.load_strict()` for the cases where strict validation is desired (CI test fixtures).
- Tracked under: v2-STAB-01 (low-risk hygiene fix).

### M8. Phase 13 Per-Param Fan-Out Multiplies Optimization Cost — No Budget Cap

- Files:
  - `evolution/core/config.py` lines 11-49 (no `max_cost_usd` field).
  - `evolution/tools/evolve_tool_descriptions.py` line 188 (`max_metric_calls=iterations * 50` — fixed multiplier).
  - Phase 13 will introduce per-parameter optimization (per `.planning/research/PITFALLS.md` Pitfall 1).
- Why it matters:
  - Today: ~50 tools × 1 description each = 50 optimizable units. `max_metric_calls=iterations * 50` is acceptable (≈$2-10 per run per CLAUDE.md).
  - Phase 13: ~50 tools × 3 avg params + 50 top-level = ~200 units. Naively reusing `iterations * 50` gives 4× the GEPA budget — and **per-param** GEPA candidates each invoke `reflection_lm` (Pitfall 11 — at the expensive `optimizer_model`). Total cost projection: $30-100 per run, breaking the documented $2-10 cost claim.
  - Combinatorial explosion (Pitfall 1): a tool with 8 params × N candidates = N⁸ design space.
  - No `max_cost_usd` halt mechanism exists today — runs continue until `max_metric_calls` exhausted regardless of token spend.
- Suggested mitigation:
  - Add `EvolutionConfig.max_cost_usd: float = 20.0` field. Track token usage per LLM call (DSPy 3.x emits usage in result objects), abort optimization when threshold crossed.
  - Add `reflection_model: Optional[str] = None` field — when set, use cheaper model for reflection (Pitfall 11 prevention).
  - For Phase 13: cap params optimized per generation to 3 (frozen others) when `len(params) > 5` (Pitfall 1 prevention #3).
  - Per-phase cost projection in plan files (Pitfall 11).
- Tracked under: Phase 13 plan must include cost projection and `max_cost_usd` integration.

### M9. No Rate-Limit / Retry Handling at LLM Call Sites

- Files:
  - `evolution/core/fitness.py` lines 75-83 (raw `dspy.LM(...)` + `with dspy.context(lm=lm): self.judge(...)`)
  - `evolution/core/external_importers.py` lines 493-530 (loop calling `self.scorer(...)` per candidate, only catches generic `Exception`)
  - `evolution/core/dataset_builder.py` lines 126-133 (single `self.generator(...)` call)
- Why it matters:
  - Code relies entirely on DSPy/LiteLLM defaults for rate-limit handling. DSPy 3.x has improved this, but there is no explicit `dspy.LM(..., max_retries=...)` or backoff_strategy configuration.
  - At Phase 14 scale (200-400 examples × N relevance-scoring + judge-scoring calls), a single 429 burst from the upstream API will cascade — no graceful degradation.
  - When Pitfall 11 plays out (reflection_lm cost spike), rate-limit hits become more likely as the optimizer sustains high QPS.
- Suggested mitigation:
  - Centralize LM creation in `evolution/core/config.py`: add `EvolutionConfig.create_lm(model_name)` that injects `max_retries`, `temperature`, and `**get_lm_kwargs()`. Replace all bare `dspy.LM(...)` calls.
  - Add exponential backoff wrapper around `RelevanceFilter.filter_and_score` per-candidate loop.
  - Document recommended rate-limit headroom in README ("Use a key with ≥600 req/min for full eval-dataset runs").
- Tracked under: Phase 14 readiness (high-volume mining).

---

## LOW Severity

### L1. `_format_paren_concat` Edge Cases — Unicode and Internal Quotes

- Files:
  - `evolution/tools/tool_loader.py` lines 737-771 (`_format_paren_concat`)
  - `evolution/tools/tool_loader.py` lines 706-734 (`_format_description` — escape logic for triple-quote / single-line / paren-concat)
- Why it matters:
  - Current escape logic: `text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')`. This is correct for ASCII but:
    - **Triple-quote format** (line 728-729): only escapes literal `"""` substrings. A description containing `\"\"\"` (already-escaped triple-quote) becomes `\\"""` after the second pass — produces malformed Python.
    - **Paren-concat** word-split logic (lines 753-765) splits at spaces. A long URL or hash without spaces produces a single line >70 chars (line 752 condition fails), then the inner else branch may produce empty strings or split mid-word.
    - Unicode in descriptions (CJK text, emoji) interacts with the 70-char `len()` check by codepoint, not by visual width — formatting may look ugly but is correct semantically. Not a bug, but a UX nit at Phase 13 fan-out.
  - Phase 13 per-parameter write-back exercises this code path 3-5× more than Phase 3 top-level-only.
- Suggested mitigation:
  - Use `ast.unparse()` or `black`/`ruff format` to round-trip the modified Python, ensuring valid syntax after write-back. Can be a `[project.optional-dependencies].dev` add.
  - Add a fuzz test that feeds unicode + nested-quote + URL strings to `write_back_description` and asserts the result file parses with `ast.parse()`.
- Tracked under: Phase 13 (write-back integration testing).

### L2. No Consolidated End-to-End Integration Test

- Files:
  - `tests/` directory — 15 test files covering unit-level concerns (constraints, importers, modules, metrics, datasets, loaders).
  - Phase 6 / Phase 11 marked "Skipped — TDD satisfied".
  - `tests/tools/test_tool_loader.py` line 583 has the only integration-style guard: `@pytest.mark.skipif(not HERMES_AVAILABLE, ...)`.
- Why it matters:
  - There is **no** single test that runs `evolve_skill.py` / `evolve_tool_descriptions.py` / `evolve_prompt_sections.py` end-to-end with a mock LLM. This means H1 (the silent MIPROv2 fallback) was not caught by tests.
  - v2-STAB-02 verifies dry-run only — full optimization integration is unverified. A regression in `dspy.GEPA` API would be caught only at runtime by the next user.
  - "Tests pass" is a misleading green signal — they assert unit contracts, not pipeline contracts.
- Suggested mitigation:
  - Add `tests/integration/test_pipeline_smoke.py` per phase, using `dspy.Mock` or a stubbed LM (`dspy.LM("mock", ...)`) that returns canned responses. Assert: GEPA path actually invoked (not MIPROv2 fallback), `metrics.json` contains expected fields, output files written.
  - CI: run the full suite + smoke tests on every PR.
- Tracked under: Phase 12 follow-up + v2-STAB-03.

### L3. Output Directory Has No Retention Policy

- Files:
  - `evolution/skills/evolve_skill.py` line 257 (`output_dir = Path("output") / skill_name / timestamp`)
  - `evolution/tools/evolve_tool_descriptions.py` line 352 (`output_dir = Path("output") / "tools" / timestamp`)
  - `evolution/prompts/evolve_prompt_sections.py` line 416 (`output_dir = Path("output") / "prompts" / timestamp`)
- Why it matters:
  - Each run creates a new timestamped subdirectory. No code deletes old runs.
  - Per-run footprint is small (~10-50 KB of JSON + diff text), but at Phase 22 continuous-loop scale (Pitfall 13: scheduled runs) the directory grows unboundedly.
  - Once H4 (gitignore) is fixed, this is a disk hygiene issue rather than a security issue, but still worth fixing before automation lands.
- Suggested mitigation:
  - Add `evolution/cli/clean_output.py` with `--keep-last N` and `--older-than DAYS` options.
  - Default policy: keep last 10 runs per artifact type. Document in README.
- Tracked under: Phase 22 (continuous loop) prerequisite.

### L4. `extract_tool_descriptions` Uses Regex on Python Source — Not AST

- Files:
  - `evolution/tools/tool_loader.py` lines 158-213 (regex-based schema discovery via `_SCHEMA_VAR_PATTERN`)
  - `evolution/tools/tool_loader.py` lines 401-431 (regex-based name + description extraction with manual `_find_matching_bracket`)
  - Note: `import ast` is in the file (line 12) but only used for `ast.literal_eval` on extracted snippets, not for parsing the schema dicts directly.
- Why it matters:
  - Regex-based parsing is brittle to:
    - Schema dicts assigned via tuple unpacking (`X_SCHEMA, Y_SCHEMA = (...)`)
    - F-strings or `.format()` calls in description fields (rare but possible)
    - Nested dict comprehensions (currently uncommon but legal Python)
  - hermes-agent format drift (Pitfall 8 from v2 research) at the schema level would silently drop tools from optimization.
  - Today this works because hermes-agent uses simple `XXX_SCHEMA = {...}` constants. Pitfall 8 concerns session JSON, but the same drift risk applies to tool source files.
- Suggested mitigation:
  - Replace regex schema discovery with `ast.parse(source)` + walking `ast.Assign` nodes whose target name matches `_SCHEMA(_S)?$`. Preserve the existing `desc_format` / `raw_source` fields for write-back.
  - This is a refactor, not a bug fix; can be deferred until Phase 13 fan-out forces more parsing edge cases.
- Tracked under: Phase 13 plan (consider as scope decision).

### L5. `EvolutionConfig` Mixes Read-Time Discovery with Run-Time Mutability

- Files:
  - `evolution/core/config.py` lines 14-17 (`hermes_agent_path: Path = field(default_factory=lambda: get_hermes_agent_path())`)
- Why it matters:
  - `get_hermes_agent_path()` raises `FileNotFoundError` if hermes-agent is missing — this happens at `EvolutionConfig()` construction time, even when the caller doesn't need the path (e.g. unit tests, dry-run validation).
  - Tests must monkey-patch `get_hermes_agent_path` or supply `HERMES_AGENT_REPO` env var to construct any config.
- Suggested mitigation:
  - Make `hermes_agent_path` lazily-resolved: `def __post_init__(self): if self._hermes_agent_path is None: ...`.
  - Or accept `hermes_agent_path: Optional[Path] = None` and resolve only when first read.
- Tracked under: low-priority refactor; may surface during Phase 13 plan if config-shape needs to change.

### L6. `DATABASE_URL` in Secret Patterns — False-Positive Risk in Skill Files

- Files:
  - `evolution/core/external_importers.py` line 64 (`DATABASE_URL` exact-match in `SECRET_PATTERNS`)
- Why it matters:
  - Skill files legitimately mention `DATABASE_URL` as a configuration concept (e.g. a database tutorial skill). Today, any session message mentioning "set the DATABASE_URL env var" is silently dropped from training data even though no actual secret value was leaked.
  - Same applies to other env-var-name patterns: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `SLACK_BOT_TOKEN`, `GITHUB_TOKEN`, `AWS_SECRET_ACCESS_KEY` — all biased away from infrastructure topics.
- Suggested mitigation:
  - Tighten the pattern: `DATABASE_URL\s*[=:]\s*\S+` (require an actual assignment) instead of bare `DATABASE_URL`.
  - Apply the same fix to all other env-var-name patterns.
- Tracked under: Phase 14 (sanitization expansion) — fold into M5 mitigation.

---

## Cross-Cutting: v1-Baseline Regression Gate

Per Pitfall research "Cross-phase prevention" section: every v2 phase plan must include "v1 holdout score not regressed" as an explicit acceptance criterion. **This is not a single concern — it's a process gate that must be enforced in every Phase 13–22 plan.**

- Today: no infrastructure exists to run the v1 holdout against an evolved v2 artifact and compare scores.
- Mitigation: add `evolution/cli/regression_gate.py` that loads the v1 holdout from `datasets/skills/<name>/holdout.jsonl`, scores it against both baseline and evolved artifacts, and emits PASS/FAIL based on `evolved_score >= baseline_score - 0.03`.
- Tracked under: Phase 13 must build this gate; Phases 14–22 must invoke it.

---

*Concerns audit: 2026-05-06*
