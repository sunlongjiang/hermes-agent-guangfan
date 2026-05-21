# Hermes Agent Self-Evolution: Phase 2 & 3

## What This Is

在已实现 Phase 1（技能进化）的基础上，实现 Phase 2（工具描述优化）和 Phase 3（系统提示词进化）。复用核心基础设施（dataset_builder、fitness、constraints），为每个 Phase 构建独立可用的优化管道。目标是让 GEPA 能优化 hermes-agent 的工具描述和系统提示词组件。

## Core Value

让 GEPA 优化循环能覆盖工具描述和系统提示词——不仅是技能文件——使 hermes-agent 的核心文本制品都能被系统性地自动改进。

## Current Milestone: v2.0 Stabilization, Enhancement & Expansion

**Goal:** 在 v1 稳定基础上扩展工具/提示词优化深度，并新增代码进化与持续学习能力（Phase 12, 13 ✓ 完成；Phase 14-21 待执行）。

**Target features:**
- 工具优化增强：per-parameter 描述优化、SessionDB 误选挖掘、think-augmented 选择、单工具回归仪表盘（Phase 13-16）
- 提示词优化增强：5 段联合优化、个性漂移检测、SessionDB 行为挖掘、TBLite 基准门控（Phase 17-20）
- 新能力扩展：Darwinian 代码进化（Phase 21）

**Phase numbering:** 继续 v1 编号（Phase 13 起），不重置。

## Requirements

### Validated

- ✓ Skill evolution pipeline — Phase 1 已实现
- ✓ DSPy module wrapper pattern (SkillModule) — existing
- ✓ Synthetic dataset builder — existing
- ✓ Session importers (Claude Code, Copilot, Hermes) — existing
- ✓ LLM-as-judge fitness scoring — existing
- ✓ Constraint validation (size, growth, structure) — existing
- ✓ CLI with Click + Rich console output — existing
- ✓ Tool loading & discovery (ToolDescription, extract_tool_descriptions) — Validated in Phase 2-3
- ✓ ToolModule (DSPy module for tool selection) — Validated in Phase 3
- ✓ Tool selection dataset (ToolSelectionExample, ToolSelectionDataset, ToolDatasetBuilder) — Validated in Phase 4
- ✓ Binary tool selection metric (tool_selection_metric) — Validated in Phase 4
- ✓ Cross-tool regression checker (CrossToolRegressionChecker) — Validated in Phase 4

### Active

- [ ] v2: Per-parameter description optimization (TOOL-V2-02)
- [x] v2: SessionDB mining for tool/prompt training data (TOOL-V2-01, PMPT-V2-04) — TOOL-V2-01 validated in Phase 14; PMPT-V2-04 validated in Phase 19 (5 plans, 3/3 SC verified, 27/27 threats closed; REVIEW 9/10 issues auto-fixed, WR-08 accepted as deferred protected-region nit)
- [x] v2: Think-augmented tool selection (TOOL-V2-03) — Validated in Phase 15 (pending real-LM UAT for CR-01..04 scenarios)
- [x] v2: Joint section optimization (PMPT-V2-01) — Validated in Phase 17 (pending real-LM UAT for joint vs RR holdout comparison + WR-07 [ACTIVE:sid] tag reflection quality)
- [x] v2: Personality drift detection (PMPT-V2-02) — Validated in Phase 18 (5 plans, 9/9 must-haves verified; v1-pragmatic Tier 2 calibration ships with formality/vocabulary warned dims — tighten in a follow-up phase when a stronger judge is available)
- [x] v2: TBLite benchmark-gated validation (PMPT-V2-03) — Code-level validated in Phase 20 (5/6 plans executed; Plan 20-05 live calibration deferred at user direction — anchor.json + real TBLite task names pending. Gate fails-closed without anchor, so runtime is safe. Resume via `python -m evolution.benchmarks.build_tblite_calibration`)
- [ ] v2: Darwinian code evolution (V2-CODE-01)
- [x] v2: Continuous evolution loop (V2-LOOP-01) — Validated in Phase 22 (7 plans, 3/3 SCs verified; GH Actions cron `57 8 * * 1` + workflow_dispatch invoking serial 6-CLI loop, push-to-hermes-agent PRs via gh CLI subprocess with `requires-human-review` label, branch-protection runbook + CODEOWNERS template shipped, EVOLUTION_DEPLOY_MODE=production worker guard closes CONCERNS §M6. 785 passed / 1 skipped / 1 xfailed; +62 tests vs Phase 21 baseline)

### Validated (v1 Complete)

- ✓ Skill evolution pipeline — Phase 1
- ✓ DSPy module wrapper pattern (SkillModule) — Phase 1
- ✓ Synthetic dataset builder — Phase 1
- ✓ Session importers (Claude Code, Copilot, Hermes) — Phase 1
- ✓ LLM-as-judge fitness scoring — Phase 1
- ✓ Constraint validation (size, growth, structure) — Phase 1
- ✓ CLI with Click + Rich console output — Phase 1
- ✓ Tool loading & discovery (ToolDescription, extract_tool_descriptions) — Phase 2
- ✓ ToolModule (DSPy module for tool selection) — Phase 3
- ✓ Tool selection dataset (ToolSelectionExample, ToolDatasetBuilder) — Phase 4
- ✓ Binary tool selection metric (tool_selection_metric) — Phase 4
- ✓ Cross-tool regression checker (CrossToolRegressionChecker) — Phase 4
- ✓ ToolFactualChecker (factual accuracy constraint) — Phase 5
- ✓ evolve_tool_descriptions CLI entry point — Phase 5
- ✓ Prompt loading (extract_prompt_sections, write_back_section) — Phase 7
- ✓ PromptModule (per-section DSPy optimization) — Phase 8
- ✓ Prompt behavioral dataset (PromptDatasetBuilder, 80 scenarios) — Phase 9
- ✓ Prompt behavioral metric (PromptBehavioralMetric) — Phase 9
- ✓ PromptRoleChecker (role preservation constraint) — Phase 10
- ✓ evolve_prompt_sections CLI entry point — Phase 10
- ✓ TBLiteRunner + TBLiteBenchmarkGate (Risk_Score + Virtual Prompt Overlay) — Phase 20
- ✓ build_tblite_calibration CLI (live anchor generation) — Phase 20
- ✓ `--benchmark=tblite` flag wired into evolve_prompt_sections step 10.5 — Phase 20
- ✓ Continuous evolution loop (EvolutionConfig.loop_cli_config + run_loop.py + pr_creator.py + GH Actions cron) — Phase 22
- ✓ Production read-only worker guard (EVOLUTION_DEPLOY_MODE=production → PermissionError on write-back) — Phase 22

### Out of Scope

- hermes-agent batch_runner integration — 做独立管道，不依赖 hermes-agent 的运行时
- TBLite/YC-Bench benchmark gating — 基准测试作为可选项，不阻塞核心功能
- Phase 4 (Code evolution via Darwinian Evolver) — 不在本次范围
- Phase 5 (Continuous improvement loop) — 不在本次范围
- Auto PR creation — 输出到 output/ 目录即可

## Context

- 项目是独立的优化管道，对 hermes-agent 只做读取操作
- Phase 1 建立的模式：Module wrapper → Dataset → GEPA optimize → Constraint validate → Holdout evaluate → Save output
- PLAN.md 中对 Phase 2 和 Phase 3 有非常详细的规划，包括具体的数据源、评估指标、约束条件
- 核心依赖：DSPy>=3.0, Click, Rich

## Constraints

- **Architecture**: 严格遵循 Phase 1 的代码模式和目录结构
- **Dependency**: 不引入新的外部依赖，复用现有 DSPy/Click/Rich 栈
- **hermes-agent**: 只读访问，通过 HERMES_AGENT_REPO 环境变量定位
- **Size**: 工具描述 ≤500 chars，参数描述 ≤200 chars，提示词段 ≤ 基线 +20%

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 独立管道优先 | 不依赖 hermes-agent 运行时，降低集成复杂度 | ✓ Validated |
| 复用 core/ 基础设施 | SyntheticDatasetBuilder、LLMJudge、ConstraintValidator 已经足够通用 | ✓ Validated |
| 遵循 PLAN.md 的 Phase 2/3 详细规划 | 规划已经非常详尽，包含具体实现方案 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-19 — Phase 19 (sessiondb-behavioral-mining-for-prompts, PMPT-V2-04) complete with 5 plans; verifier 3/3 SC PASS, security 27/27 threats closed. SessionPromptMiner (4-way signal extraction: user_correction / section_specific_failure / oracle_disagreement / persona_drift) + mine_prompt_sessions CLI (13 flags, --i-have-consent gate, FAILED_<ts>/ recovery) + evolve_prompt_sections --session-source union (hash dedup, bad-line tolerance, joint+round-robin transparent). Code review surfaced 2 critical + 8 warning + 5 info; 9/10 critical+warning auto-fixed (CR-01/CR-02 dead code+hardcoded path; WR-01..07 metric channels / secret scrubbing / cheap-rule filters). WR-08 (drift_thresholds.json parse guard inside Phase 18 protected region) accepted as deferred. 637 tests passing, zero regression. Phase 20 (benchmark-gated-validation, PMPT-V2-03) next.*

*Last updated: 2026-05-20 — Phase 20 (benchmark-gated-validation, PMPT-V2-03) complete at code level with 5/6 plans (Plan 20-05 live calibration deferred at user direction — anchor.json + real TBLite task names pending). Shipped: TBLiteRunner (async stream pipe + state monitor, daemon threads, heartbeat hang detection), TBLiteBenchmarkGate (Risk_Score weighted algorithm + Virtual Prompt Overlay + content-addressed cache + sliding-window adaptive thresholds), build_tblite_calibration CLI (Watermark check, HF revision pinning, 3-run median, Rich Table), and --benchmark=tblite wired into evolve_prompt_sections step 10.5 (post-GEPA, pre-write-back). CostTracker(max_cost_usd) finally instantiated in prompt evolution path (closed Phase 13 gap). Code review surfaced 4 critical + 9 warning + 5 info; 4/4 critical + 8/9 warning auto-fixed (CR-01 multi-section overlay loss / CR-02 W-7 dict-to-runner mismatch / CR-03 git returncode ignored / CR-04 KeyError vs TypeError; WR-01 path traversal in task name regex / WR-04 zero-sample tier / WR-08 failed runs polluting aggregation). WR-06 (1300+ line evolve() refactor) deferred. 695 tests passing (+13 regression tests). Verification: 19/20 must-haves code-level PASS, status human_needed pending live calibration via `python -m evolution.benchmarks.build_tblite_calibration --runs 3 --benchmark-max-cost 50.0`. HUMAN-UAT.md persisted. Phase 21 (darwinian-code-evolution, V2-CODE-01) next.*

*Last updated: 2026-05-20 — Phase 21 (darwinian-code-evolution, V2-CODE-01) complete with 8/8 plans across 3 waves. Shipped: MIT LICENSE (D-17), pyproject.toml [code] extra (openevolve>=0.2.27) + ruff dev dep + [tool.ruff], .pre-commit-config.yaml D-18 layer-1 grep gate, evolution/code/ package (LICENSING.md, __init__.py lazy guard), code_target_loader.py (CodeTarget + AST scan + stratified 20/10 train/holdout + T-21-RECURSE blacklist), code_fitness.py (deterministic 3-component scoring: pytest hard gate + size piecewise + ruff bucket, NO LLM judge per D-14), sandbox_runner.py (build_restricted_env strips 8 API keys / 120s timeout / finally cleanup / PYTHONPATH eval_dir lock), code_evolver_adapter.py (sole openevolve import surface per D-03, EVOLVE-BLOCK injection + self-contained evaluator generation), evolve_code.py (Click CLI 8 flags + 9-step evolve pipeline + 7-step preflight + D-15 holdout gate + D-19 NOTICE.md with secret-filtered failures), 10 holdout edge case tests covering D-07 EDGE_CASE_HOLDOUT_TESTS, plus D-18 layer-2 pytest import boundary gate. Verifier 3/3 truths VERIFIED after one cycle: initial run found BLOCKER cross-plan signature drift between code_fitness.score_candidate and sandbox_runner.run_pytest_in_sandbox (3-arg mock kwargs vs real 5-arg positional) — fixed via c9498f4 (test_file_path kwarg + uuid run_id + positional call site update across code_fitness/code_evolver_adapter/evolve_code + real-sandbox integration test added). Live dry-run smoke `python -m evolution.code.evolve_code --component tools/ansi_strip.py --dry-run` now exits 0 with baseline pytest 30/30. 29 tests/code/ + 695 wider regression all pass. Wave 1+2 executor agents hit a session-level Claude Code sandbox lockout denying Write/Bash on 6/7 spawned agents; orchestrator wrote/committed missing code+SUMMARYs inline from each agent's design spec — fully documented in each plan's SUMMARY.md "Issues Encountered". HUMAN-UAT.md persisted with 1 pending item (live one-iteration openevolve smoke test, requires LLM API budget). Phase 22 (continuous-evolution-loop) next.*

*Last updated: 2026-05-21 — Phase 22 (continuous-evolution-loop, V2-LOOP-01) complete with 7/7 plans across 4 waves. Shipped: EvolutionConfig.deploy_mode + PermissionError guards in write_back_description / write_back_section (closes CONCERNS §M6 hermes-agent read-only enforcement); LOOP_CLI_NAMES + loop_cli_config schema + evolution.yaml.example template (D-06 per-CLI enable / D-08 per-CLI max-cost cap); evolution/loop/run_loop.py Click CLI orchestrator (D-07 6-CLI canonical serial dispatch + D-10 holdout-gate dir-name+metrics classification + non-blocking failure + Phase 20 D-13 run_summary.json shape + lazy pr_creator import); evolution/loop/pr_creator.py (D-03/D-04/D-05 gh CLI subprocess + staging-dir copy into hermes-agent/evolution-loop/<kind>/<ts>/ + never-raises contract + 8 _contains_secret defense-in-depth sites); first-ever .github/workflows/evolution-loop.yml (Monday 08:57 UTC cron + workflow_dispatch + ubuntu-latest Python 3.13 + EVOLUTION_DEPLOY_MODE=production + two-repo checkout via GH_PAT_HERMES_PUSH + run_summary artifact upload); docs/setup-hermes-agent-branch-protection.md runbook (199 LoC, gh api one-shot apply + CODEOWNERS + verification + rollback + FAQ for SC #3 enforcement); tests/loop/ 47 tests (test_run_loop 13 + test_pr_creator 34). Verifier 3/3 SCs PASS. 785 tests passing / +62 vs Phase 21 baseline / no regression. Wave 1 subagents hit the same session-level Bash/Write/Edit permission wall seen in Phase 21 (22-07 transient-succeeded; 22-01 + 22-04 stalled mid-task); orchestrator finalized those inline and ran Waves 2-4 entirely inline. Five deviations documented in 22-VERIFICATION.md: subagent fallback, evolution.yaml gitignore → evolution.yaml.example, pr_creator test overlap (32 from Wave 1 + 2 appended for Plan 06 parity = 34), __getattr__ recursion fix in evolution/loop/__init__.py (importlib.import_module + globals caching), code-review/security gates skipped this session pending subagent-dispatch restoration. Milestone v2.0 now 9/11 phases complete.*
