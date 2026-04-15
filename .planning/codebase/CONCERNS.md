# Codebase Concerns

**Analysis Date:** 2026-04-15

## Tech Debt

**Empty Placeholder Modules:**
- Issue: Four package directories contain only empty `__init__.py` files, representing planned but unimplemented phases of the project (code evolution, monitoring, prompt optimization, tool evolution).
- Files: `evolution/code/__init__.py`, `evolution/monitor/__init__.py`, `evolution/prompts/__init__.py`, `evolution/tools/__init__.py`
- Impact: These are dead code that signals incomplete architecture. Any consumer importing from these packages gets nothing. The corresponding `datasets/tools/` and `datasets/skills/` directories are also empty.
- Fix approach: Either implement the planned modules or remove the empty packages until they are needed. Add a note in code or PLAN.md about which phases correspond to which packages.

**Naive YAML Frontmatter Parsing:**
- Issue: `load_skill()` and `_check_skill_structure()` parse YAML frontmatter using string splitting and `startswith()` checks rather than an actual YAML parser. This will break on multiline values, quoted strings with colons, comments, or nested YAML structures.
- Files: `evolution/skills/skill_module.py` (lines 33-47), `evolution/core/constraints.py` (lines 150-174)
- Impact: Skills with complex frontmatter (multiline descriptions, nested metadata) will be misparsed. The constraint validator could false-positive or false-negative on structural checks.
- Fix approach: Use `pyyaml` (already a dependency) to parse frontmatter properly: `yaml.safe_load(frontmatter_text)`.

**Keyword-Overlap Fitness Metric as Default:**
- Issue: `skill_fitness_metric()` in `evolution/core/fitness.py` uses a simplistic word-overlap heuristic as the DSPy metric function. This is explicitly noted as a "fast proxy" but is the default metric for all optimization runs. It cannot distinguish semantically correct from semantically wrong outputs that happen to share vocabulary.
- Files: `evolution/core/fitness.py` (lines 107-136)
- Impact: Optimization may reward keyword-stuffing rather than genuine quality improvement. The Phase 1 report acknowledges the +39.5% improvement was measured with this heuristic, making the result potentially inflated.
- Fix approach: Make `LLMJudge.score()` the default metric (it already exists), with the heuristic as an explicit `--fast-metric` fallback. Or implement a combined metric that uses the heuristic for speed during training and LLM-judge for validation.

**Hardcoded Model Strings:**
- Issue: Default model strings like `"openai/gpt-4.1"` and `"openai/gpt-4.1-mini"` are hardcoded in `EvolutionConfig` and CLI defaults. The CLI in `external_importers.py` defaults to `"openrouter/google/gemini-2.5-flash"`. These assume specific LiteLLM routing prefixes and model availability.
- Files: `evolution/core/config.py` (lines 21-23), `evolution/core/external_importers.py` (line 739), `evolution/skills/evolve_skill.py` (lines 302-303)
- Impact: If model names change or providers rotate endpoints, the tool breaks with opaque LiteLLM errors. Users on different providers must always override via CLI flags.
- Fix approach: Read model defaults from environment variables (e.g., `HERMES_OPTIMIZER_MODEL`) with the current values as fallbacks.

**No Determinism Controls for Dataset Generation:**
- Issue: `random.shuffle()` is used in `SyntheticDatasetBuilder.generate()`, `GoldenDatasetLoader.load()`, and `build_dataset_from_external()` without setting a seed. This means the same inputs produce different train/val/holdout splits on every run.
- Files: `evolution/core/dataset_builder.py` (lines 159, 193), `evolution/core/external_importers.py` (line 672)
- Impact: Optimization results are not reproducible. Two runs with identical inputs may optimize against different validation sets, making A/B comparisons unreliable.
- Fix approach: Accept an optional `seed` parameter in `EvolutionConfig` and call `random.seed(seed)` before shuffling, or use a dedicated `random.Random(seed)` instance.

**`generate_report.py` is a 500-Line Hardcoded PDF:**
- Issue: The entire Phase 1 validation report is a single Python file with hardcoded strings, table data, and ReportLab styling. It generates a fixed report rather than being parameterized from actual metrics.
- Files: `generate_report.py` (504 lines)
- Impact: Cannot generate reports for future phases or different skills without rewriting the file. The hardcoded metrics (0.408 -> 0.569) are baked in, not read from `metrics.json`.
- Fix approach: Either remove this file (it has served its purpose) or refactor into a template-based report generator that reads from `output/<skill>/<timestamp>/metrics.json`.

## Known Bugs

**GEPA Fallback May Silently Change Optimization Strategy:**
- Symptoms: If `dspy.GEPA` raises any exception (not just "not available"), the code catches it with a bare `except Exception` and silently falls back to `MIPROv2`. This includes genuine configuration errors, API failures, or bugs.
- Files: `evolution/skills/evolve_skill.py` (lines 156-177)
- Trigger: Any exception during `dspy.GEPA()` instantiation or `optimizer.compile()`.
- Workaround: None. The user sees a yellow warning but the optimization continues with a fundamentally different algorithm that may produce worse results.

**`_check_skill_structure` Checks First 500 Chars Only:**
- Symptoms: The constraint validator only searches the first 500 characters for `name:` and `description:` fields. A skill with a long preamble before frontmatter, or frontmatter fields appearing after 500 chars, would fail validation incorrectly.
- Files: `evolution/core/constraints.py` (lines 152-154)
- Trigger: Skill files with large frontmatter blocks where `description:` appears after char 500.
- Workaround: Keep frontmatter compact (which is already best practice).

**`evolve_skill.py` Uses `judge_model=eval_model` Override:**
- Symptoms: The `evolve()` function sets `judge_model=eval_model` on line 53, overriding the config default. This means dataset generation uses the cheaper eval model instead of the intended stronger judge model, potentially producing lower-quality synthetic datasets.
- Files: `evolution/skills/evolve_skill.py` (line 53)
- Trigger: Every run via `evolve_skill.py` CLI.
- Workaround: Pass a separate `--judge-model` flag (not currently exposed in CLI).

## Security Considerations

**subprocess.run Without Shell=False Verification:**
- Risk: `ConstraintValidator.run_test_suite()` runs `subprocess.run(["python", "-m", "pytest", ...])` with a user-provided `hermes_repo` path as `cwd`. While `shell=False` is the default (safe), the `cwd` parameter comes from `config.hermes_agent_path` which can be set via environment variable or CLI argument.
- Files: `evolution/core/constraints.py` (lines 58-63)
- Current mitigation: The path is validated to exist in `get_hermes_agent_path()`.
- Recommendations: Validate that `cwd` is actually a git repository and contains expected files before running subprocess commands.

**Session History Files May Contain Sensitive Data:**
- Risk: The external importers read user session history from `~/.claude/history.jsonl`, `~/.copilot/session-state/`, and `~/.hermes/sessions/`. These may contain sensitive business information, proprietary code, or personal data beyond just API keys.
- Files: `evolution/core/external_importers.py` (lines 157-416)
- Current mitigation: Secret detection via regex patterns (`SECRET_PATTERNS`). Task inputs are capped at 2000 chars.
- Recommendations: Add a consent/confirmation prompt before reading session history. Consider adding content classification beyond just secret detection (e.g., PII detection). Document that generated datasets should be treated as potentially sensitive.

**No Rate Limiting on LLM API Calls:**
- Risk: The `RelevanceFilter.filter_and_score()` loop makes one LLM call per candidate message with no rate limiting or retry logic. With 150 candidates (max_examples * 3), this could hit API rate limits.
- Files: `evolution/core/external_importers.py` (lines 498-531)
- Current mitigation: None.
- Recommendations: Add exponential backoff retry logic, or batch calls where possible.

## Performance Bottlenecks

**Sequential LLM Scoring in RelevanceFilter:**
- Problem: `RelevanceFilter.filter_and_score()` scores candidates one-by-one in a synchronous loop, making up to `max_examples * 3` sequential LLM API calls.
- Files: `evolution/core/external_importers.py` (lines 491-531)
- Cause: No async/concurrent execution. Each call waits for the previous to complete.
- Improvement path: Use `asyncio` with `dspy.asyncify` or batch multiple scoring requests. DSPy supports async evaluation — leverage it for 5-10x throughput improvement.

**Copilot Session Files Can Be 100MB+:**
- Problem: The docstring notes Copilot event files can be 100MB+, and the code streams line-by-line (good), but it loads ALL session directories and processes them sequentially with no caching.
- Files: `evolution/core/external_importers.py` (lines 238-257)
- Cause: No incremental processing or caching of previously-scanned sessions.
- Improvement path: Track a "last processed" timestamp and only scan new sessions. Cache extracted messages to avoid re-parsing large files.

**Holdout Evaluation Runs Both Baseline and Evolved Sequentially:**
- Problem: In `evolve_skill.py` lines 214-224, holdout evaluation runs baseline and evolved predictions sequentially for each example, doubling the evaluation time.
- Files: `evolution/skills/evolve_skill.py` (lines 214-224)
- Cause: Synchronous loop with no parallelism.
- Improvement path: Run baseline and evolved predictions in parallel, or pre-compute baseline scores before optimization since they don't change.

## Fragile Areas

**DSPy Version Compatibility:**
- Files: `evolution/skills/evolve_skill.py` (lines 156-177), `evolution/core/fitness.py`, `evolution/core/dataset_builder.py`
- Why fragile: The code depends on `dspy>=3.0.0` but uses specific APIs like `dspy.GEPA`, `dspy.MIPROv2`, `dspy.ChainOfThought`, `dspy.context()`, and `dspy.LM()`. DSPy is rapidly evolving and has had breaking API changes between minor versions. The GEPA fallback to MIPROv2 is already evidence of version instability.
- Safe modification: Pin DSPy to a specific minor version in `pyproject.toml` (e.g., `dspy>=3.0.0,<3.1.0`). Add a DSPy version check at startup.
- Test coverage: No tests exercise the DSPy integration directly; all DSPy calls are mocked in tests.

**Skill File Format Assumptions:**
- Files: `evolution/skills/skill_module.py` (lines 15-55), `evolution/core/constraints.py` (lines 150-174)
- Why fragile: The skill loader assumes a very specific format: `---` YAML frontmatter delimiters, `name:` and `description:` as top-level keys, markdown body after the second `---`. Any deviation (e.g., TOML frontmatter, different delimiters) breaks silently.
- Safe modification: Validate format explicitly and raise clear errors on unexpected formats.
- Test coverage: Basic happy-path tests exist in `tests/skills/test_skill_module.py`, but edge cases (no frontmatter, malformed YAML, extra `---` in body) are not tested.

**LLM Output Parsing:**
- Files: `evolution/core/dataset_builder.py` (lines 136-145), `evolution/core/external_importers.py` (lines 546-600), `evolution/core/fitness.py` (lines 139-146)
- Why fragile: Three separate parsers handle LLM outputs: JSON array extraction in `SyntheticDatasetBuilder`, balanced-brace JSON extraction in `_parse_scoring_json`, and score float parsing in `_parse_score`. Each has different fallback strategies. LLM output format changes (e.g., markdown wrapping, additional explanation text) can break any of these.
- Safe modification: Consolidate into a single robust JSON extraction utility. Consider using DSPy's typed output features if available.
- Test coverage: `_parse_scoring_json` is well-tested. `_parse_score` and the dataset builder's JSON extraction have no direct tests.

## Scaling Limits

**In-Memory Dataset Processing:**
- Current capacity: Datasets up to ~10K examples fit comfortably in memory.
- Limit: Very large session histories (millions of messages across tools) would cause memory pressure since all messages are collected into a list before filtering.
- Scaling path: Use generator/iterator patterns instead of collecting all messages into lists. Process in streaming fashion.

**Single-Threaded Optimization:**
- Current capacity: One skill at a time, one optimization run.
- Limit: No support for parallel skill evolution or distributed evaluation.
- Scaling path: Add a job queue or use multiprocessing for independent skill optimizations.

## Dependencies at Risk

**DSPy (>=3.0.0):**
- Risk: Rapidly evolving library with frequent breaking changes. The `>=3.0.0` lower bound with no upper bound means any future DSPy release could break the codebase.
- Impact: Core optimization loop, fitness evaluation, dataset generation all depend on DSPy.
- Migration plan: Pin to a tested version range. Add integration tests that actually call DSPy (with a cheap/local model) to catch breakage early.

**ReportLab (unlisted dependency):**
- Risk: `generate_report.py` imports `reportlab` but it is not listed in `pyproject.toml` dependencies. Running this script in a fresh environment fails with ImportError.
- Impact: Report generation fails unless manually installed.
- Migration plan: Either add `reportlab` to optional dependencies (`[project.optional-dependencies] report = ["reportlab>=4.0"]`) or remove the script.

## Missing Critical Features

**No CLI Entry Point Registration:**
- Problem: The `pyproject.toml` does not define `[project.scripts]` or `[project.entry-points]`. Users must invoke tools via `python -m evolution.skills.evolve_skill` rather than a clean CLI command.
- Blocks: User-friendly invocation and integration into CI/CD pipelines.

**No PR Creation Automation:**
- Problem: `EvolutionConfig.create_pr = True` is defined but never used. The `evolve_skill.py` pipeline saves evolved skills to local `output/` directory but never creates a PR against hermes-agent.
- Blocks: The stated goal of automated PR-based deployment of evolved skills.

**No Logging Framework:**
- Problem: All output goes through `rich.console.Console.print()`. There is no structured logging, no log levels, no file output. Debugging failed optimization runs requires re-running with manual print statements.
- Blocks: Production use, CI/CD integration, debugging of failed runs.

**No Configuration File Support:**
- Problem: All configuration is via CLI flags or hardcoded defaults. There is no support for a config file (e.g., `evolution.yaml`) to persist preferred settings per project.
- Blocks: Repeatable runs without long CLI commands.

## Test Coverage Gaps

**No Tests for `evolve_skill.py`:**
- What's not tested: The entire main orchestration pipeline including skill loading + dataset generation + optimization + constraint validation + holdout evaluation + output saving.
- Files: `evolution/skills/evolve_skill.py` (323 lines, 0 tests)
- Risk: The most critical file in the project has zero test coverage. Any refactoring could break the end-to-end flow undetected.
- Priority: High

**No Tests for `fitness.py` LLMJudge:**
- What's not tested: `LLMJudge.score()` method, `FitnessScore.composite` calculation, `_parse_score()` edge cases.
- Files: `evolution/core/fitness.py` (146 lines, 0 tests)
- Risk: The fitness scoring logic drives all optimization decisions. Bugs here silently degrade all evolution runs.
- Priority: High

**No Tests for `dataset_builder.py` SyntheticDatasetBuilder:**
- What's not tested: `SyntheticDatasetBuilder.generate()`, `EvalDataset.save()`/`load()` roundtrip, `EvalDataset.to_dspy_examples()`, `GoldenDatasetLoader.load()` auto-split logic.
- Files: `evolution/core/dataset_builder.py` (201 lines, 0 tests)
- Risk: Dataset generation and serialization bugs could produce invalid training data, causing silent optimization failures.
- Priority: Medium

**No Integration Tests:**
- What's not tested: No test exercises a real (even minimal) DSPy optimization loop. All DSPy interactions are mocked.
- Files: All `evolution/` modules
- Risk: API compatibility issues with DSPy are only discovered at runtime. The GEPA-to-MIPROv2 fallback was likely discovered this way.
- Priority: Medium

---

*Concerns audit: 2026-04-15*
