# Roadmap: Hermes Agent Self-Evolution Phase 2 & 3

## Overview

Extend GEPA optimization from skill evolution (Phase 1, complete) to tool descriptions (Phases 2-6) and system prompts (Phases 7-11). Tool descriptions come first because they have binary measurable outcomes and validate the GEPA standalone pattern. System prompts follow, leveraging the proven pattern for fuzzier behavioral evaluation. Each phase delivers a testable, independent component that builds toward the full optimization pipeline.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Skill Evolution** - Already implemented (baseline pipeline)
- [ ] **Phase 2: Tool Loading** - Extract and write tool descriptions from hermes-agent
- [ ] **Phase 3: Tool Module** - DSPy-optimizable module wrapping all tool descriptions
- [ ] **Phase 4: Tool Dataset & Evaluation** - Synthetic dataset and binary tool selection metric
- [ ] **Phase 5: Tool Constraints & CLI** - Factual accuracy checks, size limits, and CLI entry point
- [ ] **Phase 6: Tool Pipeline Tests** - Unit tests for all tool description components
- [ ] **Phase 7: Prompt Loading** - Extract and write prompt sections from prompt_builder.py
- [ ] **Phase 8: Prompt Module** - Per-section DSPy-optimizable module with context passthrough
- [ ] **Phase 9: Prompt Evaluation** - Behavioral evaluator and 60-80 scenario test suite
- [ ] **Phase 10: Prompt Constraints & CLI** - Growth limits, role preservation, and CLI entry point
- [ ] **Phase 11: Prompt Pipeline Tests** - Unit tests for all prompt section components

## Phase Details

### Phase 1: Skill Evolution
**Goal**: Baseline GEPA optimization pipeline for skill files (already complete)
**Depends on**: Nothing
**Requirements**: (Phase 1 requirements already validated)
**Success Criteria** (what must be TRUE):
  1. Skill files can be optimized through GEPA pipeline
  2. Core infrastructure (dataset_builder, fitness, constraints) works end-to-end
**Plans**: Complete

### Phase 2: Tool Loading
**Goal**: Pipeline can reliably extract tool descriptions from hermes-agent and write evolved versions back without breaking schema structure
**Depends on**: Phase 1 (reuses core infrastructure)
**Requirements**: TOOL-01, TOOL-02
**Success Criteria** (what must be TRUE):
  1. Running the loader extracts all tool descriptions from hermes-agent's tools/*.py files
  2. Writing evolved descriptions back preserves param names, types, and required fields exactly
  3. Round-trip test passes: extract -> modify description text -> write back -> extract again yields the modification
**Plans:** 2 plans

Plans:
- [x] 02-01-PLAN.md — 数据类定义和工具描述提取（4 种格式 + 集成测试）
- [x] 02-02-PLAN.md — Format-preserving 写回和 round-trip 验证

### Phase 3: Tool Module
**Goal**: All tool descriptions are wrapped as a single GEPA-optimizable unit where only description text evolves
**Depends on**: Phase 2
**Requirements**: TOOL-03, TOOL-04
**Success Criteria** (what must be TRUE):
  1. All tool descriptions are exposed as optimizable parameters in one DSPy/GEPA module
  2. Schema structure (param names, types, required) is frozen and cannot be modified by optimization
  3. Module can receive updated description text and produce valid tool definitions
**Plans:** 1 plan

Plans:
- [x] 03-01-PLAN.md — TDD: ToolModule DSPy 模块（per-tool Predict + selector + schema 冻结 + 测试）

### Phase 4: Tool Dataset & Evaluation
**Goal**: Binary tool selection metric and synthetic dataset enable measuring whether evolved descriptions improve agent tool selection
**Depends on**: Phase 3
**Requirements**: TOOL-05, TOOL-06, TOOL-07, TOOL-08
**Success Criteria** (what must be TRUE):
  1. Given a task and available tools, the metric returns 0 or 1 for correct/incorrect tool selection
  2. Synthetic dataset contains 200-400 (task, correct_tool, correct_params) triples with difficulty levels
  3. Dataset includes confuser tasks where 2+ tools overlap but one is clearly better
  4. Cross-tool evaluation rejects candidates where any single tool's selection rate drops >2%
**Plans:** 2 plans

Plans:
- [x] 04-01-PLAN.md — ToolSelectionExample/Dataset 数据类 + ToolDatasetBuilder 两步合成生成
- [x] 04-02-PLAN.md — tool_selection_metric 二值指标 + CrossToolRegressionChecker 回归检测

### Phase 5: Tool Constraints & CLI
**Goal**: Evolved tool descriptions are validated for factual accuracy and size limits, and the full pipeline is runnable via CLI
**Depends on**: Phase 4
**Requirements**: TOOL-09, TOOL-10, TOOL-11
**Success Criteria** (what must be TRUE):
  1. LLM-based factual accuracy check catches descriptions that claim false capabilities
  2. Size constraints reject descriptions >500 chars and parameter descriptions >200 chars
  3. `python -m evolution.tools.evolve_tool_descriptions` runs end-to-end with --iterations, --eval-source, --hermes-repo, --dry-run options
  4. Dry-run mode shows proposed changes without writing files
**Plans:** 2 plans

Plans:
- [ ] 05-01-PLAN.md — ToolFactualChecker 事实准确性检查器 + size constraint 复用验证
- [ ] 05-02-PLAN.md — evolve_tool_descriptions CLI 端到端管道

### Phase 6: Tool Pipeline Tests
**Goal**: Unit tests verify each tool pipeline component works correctly in isolation and together
**Depends on**: Phase 5
**Requirements**: TEST-01
**Success Criteria** (what must be TRUE):
  1. Tests cover tool loader (extraction and write-back)
  2. Tests cover tool module (parameter freezing, description exposure)
  3. Tests cover tool selection metric (correct scoring for known cases)
  4. Tests cover cross-tool evaluation (regression detection)
  5. All tests pass in CI
**Plans**: TBD

### Phase 7: Prompt Loading
**Goal**: Pipeline can extract the 5 evolvable prompt sections from prompt_builder.py and write evolved versions back
**Depends on**: Phase 2 (parallel development possible, shares loader pattern)
**Requirements**: PMPT-01, PMPT-02
**Success Criteria** (what must be TRUE):
  1. Loader extracts all 5 sections: DEFAULT_AGENT_IDENTITY, MEMORY_GUIDANCE, SESSION_SEARCH_GUIDANCE, SKILLS_GUIDANCE, PLATFORM_HINTS
  2. Writing evolved sections back preserves surrounding Python code structure
  3. Round-trip test passes: extract -> modify section text -> write back -> extract again yields the modification
**Plans:** 1 plan

Plans:
- [ ] 07-01-PLAN.md — PromptSection dataclass, AST extraction, format-preserving write-back, round-trip tests

### Phase 8: Prompt Module
**Goal**: Each prompt section is wrapped as a DSPy-optimizable module with frozen context from other sections
**Depends on**: Phase 7
**Requirements**: PMPT-03, PMPT-04
**Success Criteria** (what must be TRUE):
  1. Each of the 5 prompt sections is exposed as an independently optimizable parameter
  2. When optimizing one section, the other 4 sections are passed through as frozen context
  3. Module supports round-robin optimization (optimize one section at a time across iterations)
**Plans:** 1 plan

Plans:
- [ ] 08-01-PLAN.md — TDD: PromptModule DSPy 模块（per-section Predict + frozen context + round-robin + 测试）

### Phase 9: Prompt Evaluation
**Goal**: Behavioral evaluator with scenario-based tests measures whether evolved prompt sections produce correct agent behavior
**Depends on**: Phase 8
**Requirements**: PMPT-05, PMPT-06, PMPT-07
**Success Criteria** (what must be TRUE):
  1. Behavioral evaluator checks whether agent exhibits expected behavior for each scenario
  2. Test suite contains 60-80 scenarios across 5 sections (10-20 per section, scaled by importance)
  3. Per-section scoring produces structured actionable feedback that GEPA's reflective analysis can consume
**Plans:** 2 plans

Plans:
- [ ] 09-01-PLAN.md — TDD: PromptBehavioralExample/Dataset 数据类 + PromptDatasetBuilder 按重要性加权场景生成
- [ ] 09-02-PLAN.md — TDD: PromptBehavioralMetric callable class（LLMJudge 评分 + 快速启发式 + feedback 传播）

### Phase 10: Prompt Constraints & CLI
**Goal**: Evolved prompt sections are validated for growth limits and role preservation, and the full pipeline is runnable via CLI
**Depends on**: Phase 9
**Requirements**: PMPT-08, PMPT-09, PMPT-10
**Success Criteria** (what must be TRUE):
  1. Growth constraint rejects evolved sections that exceed baseline by >20%
  2. LLM-based role preservation check confirms evolved text maintains its functional role
  3. `python -m evolution.prompts.evolve_prompt_sections` runs end-to-end with --section, --iterations, --hermes-repo, --dry-run options
  4. Dry-run mode shows proposed changes without writing files
**Plans:** 2 plans

Plans:
- [ ] 10-01-PLAN.md — PromptRoleChecker 角色保持检查器 + growth constraint 复用验证
- [ ] 10-02-PLAN.md — evolve_prompt_sections CLI 端到端管道

### Phase 11: Prompt Pipeline Tests
**Goal**: Unit tests verify each prompt pipeline component works correctly in isolation and together
**Depends on**: Phase 10
**Requirements**: TEST-02
**Success Criteria** (what must be TRUE):
  1. Tests cover prompt loader (extraction of all 5 sections and write-back)
  2. Tests cover prompt module (frozen context passthrough, per-section optimization)
  3. Tests cover behavioral evaluator (scoring known-good and known-bad scenarios)
  4. All tests pass in CI
**Plans**: Skipped (TDD satisfied)

---

## Milestone v2.0 — Stabilization, Enhancement & Expansion

**Priority order:** Stabilize v1 → Enhance tools/prompts → New capabilities

### Phase 12: v1 Stabilization
**Goal**: Fix bugs, update traceability, ensure both pipelines run end-to-end reliably
**Depends on**: Phase 10
**Requirements**: V2-STAB-01, V2-STAB-02
**Success Criteria** (what must be TRUE):
  1. REQUIREMENTS.md traceability table reflects all v1 phases as Complete
  2. PROJECT.md validated requirements section updated to match actual state
  3. Both `--dry-run` pipelines succeed on a fresh clone
  4. `python -m pytest tests/ -v` passes 329+ tests with zero failures
**Plans**: TBD

### Phase 13: Per-Parameter Description Optimization
**Goal**: Extend tool description optimization to individual parameter descriptions, not just top-level
**Depends on**: Phase 12
**Requirements**: TOOL-V2-02
**Success Criteria** (what must be TRUE):
  1. ToolModule exposes per-parameter descriptions as independently optimizable parameters
  2. GEPA can mutate individual param descriptions while tool-level description stays frozen
  3. Constraint checks enforce max_param_desc_size (200 chars) per parameter
**Plans:** 8/8 plans complete

Plans:
**Wave 1**
- [x] 13-01-PLAN.md — Wave 0 test scaffolding (8 RED test files + mock_lm_with_usage fixture) + correct_params type inspection script
- [x] 13-02-PLAN.md — ToolModule sub-Module-per-tool pattern + ToolSelectionWithParamsSignature (D-01/D-02/D-03/D-04/D-05/D-18)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 13-03-PLAN.md — joint_tool_param_metric + ScoreWithFeedback variant (D-10/D-17, Pitfalls 4+7)
- [x] 13-04-PLAN.md — ParamConsistencyChecker with fail-closed polarity inversion (D-11, Pitfall 5)
- [x] 13-05-PLAN.md — EvolutionConfig.max_cost_usd + reflection_model + cost_tracker module (D-08/D-13, folded-todo closure)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 13-06-PLAN.md — persist_per_tool_rates helper (D-12, folded-todo closure)
- [x] 13-07-PLAN.md — V1BaselineGate module with historical + inline fallback (D-14, Pitfall 8)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 13-08-PLAN.md — evolve_tool_params CLI end-to-end pipeline (D-06/D-07/D-08/D-15/D-15a, folded-todo closure)

### Phase 14: SessionDB Mining for Tools
**Goal**: Mine hermes-agent session transcripts for tool misselection patterns as high-value training data
**Depends on**: Phase 12
**Requirements**: TOOL-V2-01
**Success Criteria** (what must be TRUE):
  1. Importer extracts tool selection ground truth from session transcripts
  2. Misselection patterns weighted higher in training dataset
  3. Integration with existing ToolDatasetBuilder as additional data source
**Plans:** 6/6 plans complete

Plans:
**Wave 0**
- [x] 14-01-PLAN.md — 测试脚手架（9 测试文件 + 7 session fixture JSON）覆盖 28 测试函数 + Wave 0 缺口
**Wave 1** (并行: 02 + 03)
- [x] 14-02-PLAN.md — ToolSelectionExample.misselection_signals 字段 (D-02) + 旧 JSONL 向后兼容
- [x] 14-03-PLAN.md — Privacy gate v2: SECRET_PATTERNS + JWT/AWS 正则 + Shannon 熵 (D-15, T-14-02)
**Wave 2**
- [x] 14-04-PLAN.md — session_miner.py 核心: 3 extractor + ConfirmMisselection + hash bucket + dedup union + train duplication (D-01..D-13/D-17/D-18, T-14-01/T-14-03)
**Wave 3**
- [x] 14-05-PLAN.md — mine_tool_sessions.py CLI: 12 flags + consent gate + Rich Table summary + metrics.json (D-06..D-08/D-12/D-16, T-14-04)
**Wave 4** *(blocked on Wave 3 + manual checkpoint)*
- [x] 14-06-PLAN.md — evolve_tool_*.py --session-source flag (D-09/D-14) + 44-session real-data dry-run smoke + entropy threshold calibration

### Phase 15: Think-Augmented Tool Selection
**Goal**: Add optional reasoning-before-selection Predict to ToolModule (enable_reasoning opt-in), make it GEPA-optimizable, and validate via three-AND gate (full-regression 2pp + ambiguous +3pp + latency p95 ≤ 5s) in a new CLI with isolated output directory.
**Depends on**: Phase 13
**Requirements**: TOOL-V2-03
**Success Criteria** (what must be TRUE):
  1. ToolModule supports optional ChainOfThought reasoning before selection
  2. Reasoning step is optimizable by GEPA (prompt text is a parameter)
  3. A/B comparison shows improvement on ambiguous selection scenarios
**Plans:** 6/6 plans complete

Plans:
**Wave 0**
- [x] 15-01-PLAN.md — Wave 0 test scaffolding (test_think_metrics.py + test_evolve_tool_reasoning.py + test_dataset_ambiguous_size.py + conftest.py — 30+ RED stubs + ambiguous subset observation)

**Wave 1**
- [x] 15-02-PLAN.md — ToolModule.enable_reasoning + ToolReasoningSignature + forward 双路径 + reasoning InputField (D-01..D-07/D-17) + TestEnableReasoning 7 tests

**Wave 2** (并行: 02 + 03)
- [x] 15-03-PLAN.md — think_metrics.py: ThinkABGate 双 API + sample_latency_tokens + 4 模块级常量 + Pitfall 12 守门测试

**Wave 3** *(blocked on Wave 1 + Wave 2)*
- [x] 15-04-PLAN.md — evolve_tool_reasoning.py CLI: 16 步流水线 + 双 ToolModule + 双门并跑 (V1BaselineGate×2 + ThinkABGate×1) + 4 输出文件 + output/tools_reasoning/ 物理隔离

**Wave 4** *(blocked on Wave 3 + manual dry-run checkpoint)*
- [x] 15-05-PLAN.md — test_e2e_mock_pipeline smoke + optional __init__.py export + manual real dry-run checkpoint + VALIDATION.md approved sign-off (PARTIAL — Tasks 1-2 done; Tasks 3-4 blocked on Plan 15-06)

**Wave 5** *(gap closure for Plan 15-05 — to_dspy_examples bug spun out per user scope decision)*
- [x] 15-06-PLAN.md — Fix to_dspy_examples() missing confuser_tools / correct_params (D-13 ambiguous filter + Phase 13 joint metric param_match) + test_to_dspy_examples_supports_ambiguous_filter regression test + dry-run consistency verification

### Phase 16: Per-Tool Regression Dashboard
**Goal**: Track individual tool selection rates across optimization runs
**Depends on**: Phase 14
**Requirements**: TOOL-V2-04
**Success Criteria** (what must be TRUE):
  1. Metrics file records per-tool accuracy before and after optimization
  2. Rich console dashboard shows selection rate changes per tool
  3. Regression threshold configurable (default: 2pp drop triggers warning)
**Plans:** 7/6 plans complete

Plans:
**Wave 0**
- [x] 16-00-PLAN.md — raw_predictions schema + persist_raw_predictions helper + to_dspy_examples 加 difficulty + 三 CLI 接线 (D-12)
**Wave 1** *(blocked on Wave 0)*
- [x] 16-01-PLAN.md — Dashboard CLI 骨架 + LATEST 区 (per-tool 表 12 列 + 频次柱图 + sample<3 退化 n/a) (D-09 / D-16 / D-11)
**Wave 2** *(blocked on Wave 1)*
- [x] 16-02-PLAN.md — DIFF 区 (--baseline-run + --evolved-run) + TREND 区 (--trend-window/--trend-days mutex + sparkline) (D-05 / D-06 / D-10)
**Wave 3** *(blocked on Wave 2)*
- [x] 16-03-PLAN.md — ABStudy 区 (三类计数 + top-3 + secret redact) + 跨 CLI source 启发判定 + 三类 fallback + warning 不影响 exit code (D-07 / D-08 / D-13 / D-15)
**Wave 4** *(blocked on Wave 3)*
- [x] 16-04-PLAN.md — dashboard.json schema 收口 (8 顶层字段) + E2E 集成测试 + .gitignore 卫生 (D-04 / D-17)
**Wave 5** *(gap closure — verifier 4/6 → 6/6)*
- [x] 16-05-PLAN.md — CR-01/CR-02 (--runs 语义统一) + CR-03 (reasoning joint metric 一致性) + WR-04 (FAILED 分支 persist 顺序反转) + datetime/timezone/IN-02 hygiene

### Phase 17: Joint Section Optimization
**Goal**: 让 GEPA 把 hermes-agent prompt 的全部 section (实测 13 个) 视为一组参数同时优化,取代当前的 round-robin。CLI 默认 `--mode joint` 调用 DSPy GEPA `component_selector="all"` 单次 compile,joint 跑完 holdout 评估后 inline 跑 round-robin A/B baseline (fresh PromptModule + 同 dataset/metric/holdout),软门 1pp 比较 + 双方都落盘 (shared-prefix output layout)。
**Depends on**: Phase 12
**Requirements**: PMPT-V2-01
**Success Criteria** (what must be TRUE):
  1. PromptModule supports all-sections-active mode (all Predicts discoverable)
  2. GEPA can mutate multiple sections in one pass
  3. Joint optimization produces equal or better scores than round-robin on holdout
**Plans:** 3/3 plans complete

Plans:
**Wave 1**
- [x] 17-01-PLAN.md — PromptModule joint mode 状态机扩展 (set_joint_mode + JOINT_SENTINEL + forward 三态 + Pitfall 1 修复 + selector freeze) + TestJointMode 测试

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 17-02-PLAN.md — CLI --mode flag + joint pipeline 分支 + num_predictors-dynamic budget + stdout 预算预估 + TestJointPipeline/TestDryRun 测试

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 17-03-PLAN.md — inline A/B baseline + 软门 [yellow] 警告 + metrics.json 4 新字段 + shared-prefix baseline 副本文件 + TestABBaseline 测试

### Phase 18: Personality Drift Detection
**Goal**: Detect tone/personality changes between original and evolved prompt sections
**Depends on**: Phase 17
**Requirements**: PMPT-V2-02
**Success Criteria** (what must be TRUE):
  1. DriftDetector compares original vs evolved text on tone, formality, personality dimensions
  2. Constraint gate rejects evolved sections with drift score exceeding threshold
  3. Drift report included in optimization output
**Plans:** 5/5 plans complete

Plans:
**Wave 0**
- [x] 18-01-PLAN.md — Wave 0 RED test scaffolds (test_drift_detector.py 10 tests + test_drift_calibration.py 4 tests + conftest fixtures + mini fixture JSONL + .gitignore exception)

**Wave 1** *(blocked on Wave 0 completion)*
- [x] 18-02-PLAN.md — DriftDetector class (temperature=0.7/cache=False + typed float OutputFields + 3-run averaging + severity ladder) + DriftCalibrationBuilder + derive_thresholds (pure stdlib F1 scan, no sklearn)

**Wave 2** *(blocked on Wave 1 completion — checkpoint:human-action)*
- [x] 18-03-PLAN.md — build_drift_calibration CLI + live calibration run + human spot-check >= 8/10 + commit datasets/prompts/drift_{calibration.jsonl,thresholds.json} to git (D-CAL-02/05, RA5/RA6 Tier gating)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 18-04-PLAN.md — evolve_prompt_sections.py step 8c DriftDetector wiring + drift_* metrics fields + drift_report.txt + Rich Table + --drift-thresholds-path Click flag + D-BYPASS-01 absence

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 18-05-PLAN.md — TestDriftGate CLI integration tests (5 tests covering D-OUT-02 / D-BYPASS-01..02 regression / D-GATE-03 soft warn / D-GATE-04 hard reject + FAILED_<ts>/ artifacts)

### Phase 19: SessionDB Behavioral Mining for Prompts
**Goal**: Mine session transcripts for behavioral patterns to generate targeted test scenarios
**Depends on**: Phase 12
**Requirements**: PMPT-V2-04
**Success Criteria** (what must be TRUE):
  1. Importer extracts behavioral examples from real sessions (what section guided which behavior)
  2. Mined examples augment synthetic dataset with real-world scenarios
  3. Integration with PromptDatasetBuilder as additional data source
**Plans:** 5/5 plans complete

Plans:
**Wave 1**
- [x] 19-01-dataset-schema-extension-PLAN.md — PromptBehavioralExample.mining_signals 字段 + hash-bucket split 辅助 (D-02 / D-10 / D-15)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 19-02-session-prompt-miner-PLAN.md — SessionPromptMiner 核心 (4 路 extractor + ConfirmBehavioralExample 单 call 5 字段 + DriftDetector 1-run 复用 + split_and_duplicate) (D-01..D-15 / D-18 / D-23 / D-24)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 19-03-mine-prompt-sessions-cli-PLAN.md — mine_prompt_sessions CLI (13 flags + --i-have-consent gate + Rich Table + 5 文件输出 + FAILED 路径) (D-04 / D-14 / D-17 / D-20 / D-25)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 19-04-evolve-prompt-sections-integration-PLAN.md — evolve_prompt_sections --session-source union (D-16 hash dedup + joint/round-robin dual-mode + D-22 不动 build_drift_calibration) (D-13 / D-14 / D-16 / D-21 / D-22 / D-24)

**Wave 5** *(blocked on Wave 2 + Wave 3 + Wave 4 completion)*
- [x] 19-05-integration-tests-PLAN.md — SessionPromptMiner unit tests + mine_prompt_sessions CLI tests + --session-source 集成测试 + 4 个 fixtures + step 8c / build_drift_calibration regression guard

### Phase 20: Benchmark-Gated Validation
**Goal**: Use TBLite as optional hard regression gate after optimization
**Depends on**: Phase 18
**Requirements**: PMPT-V2-03
**Success Criteria** (what must be TRUE):
  1. Optional `--benchmark` flag triggers TBLite evaluation before accepting evolved sections
  2. Configurable pass threshold (default: no regression on core capabilities)
  3. Benchmark results saved to output metrics
**Plans:** 5/6 plans complete

Plans:
**Wave 1**
- [x] 20-01-config-scaffolding-PLAN.md — EvolutionConfig 4 新字段 + evolution/benchmarks/ 包脚手架 + tblite_stratified_subset.json 占位 + .gitignore 例外 (D-03 / D-08 / D-11 / D-16 / D-17 / D-CAL-02)

**Wave 2** *(blocked on Wave 1)* — Plans 02 + 03 并行
- [x] 20-02-tblite-runner-PLAN.md — TBLiteRunner Async Stream Pipe + State Monitor + samples.jsonl 解析 + compute_artifact_hash + 9 单元测试 (D-11 / D-15 / T-20-05)
- [x] 20-03-benchmark-gate-PLAN.md — TBLiteBenchmarkGate Risk_Score 算法 + Virtual Prompt Overlay + Pre-flight (D-10/D-14) + 内容寻址 cache + prompt_loader.write_back_section dest= 扩展 + 14+ 单元测试 (D-01..D-04 / D-09 / D-10 / D-14 / D-15)

**Wave 3** *(blocked on Wave 2)*
- [x] 20-04-build-calibration-cli-PLAN.md — build_tblite_calibration CLI (8 flags + CostTracker enforcement + Pre-flight Watermark + HuggingFace dataset_revision_hash 失败开放) + 6 CliRunner 测试 (D-13 / D-15 / D-16 / D-17)

**Wave 4** *(BLOCKING — checkpoint:decision + checkpoint:human-action)*
- [ ] 20-05-anchor-generation-checkpoint-PLAN.md — Path A 实跑 calibration (~$36, 30-90 min) OR Path B mock anchor + 跟踪 todo;datasets/prompts/tblite_anchor.json + 真实 task names 落入 tblite_stratified_subset.json (D-CAL-05)

**Wave 5** *(blocked on Wave 4)*
- [x] 20-06-evolve-integration-PLAN.md — evolve_prompt_sections.py step 10.5 插入 + 6 新 Click flags + benchmark_* metrics + total_cost_breakdown + tblite_report.json 落盘 + TestBenchmarkGate 6+ CLI 集成测试 (D-04 / D-05 / D-15 / D-16 / D-18 / D-BYPASS-01 精神)

### Phase 21: Darwinian Code Evolution
**Goal**: Integrate darwinian-evolver for code-level evolution of hermes-agent components
**Note**: CONTEXT.md substituted openevolve (Apache-2.0) for darwinian-evolver (not on PyPI); goal intent preserved.
**Depends on**: Phase 16, Phase 20
**Requirements**: V2-CODE-01
**Success Criteria** (what must be TRUE):
  1. openevolve (Apache-2.0, >=0.2.27) integrated and tested as code evolution substrate
  2. At least one code component (tools/ansi_strip.py) evolvable end-to-end
  3. Fitness function: pytest binary gate (80%) + size penalty (10%) + ruff lint (10%), no LLM judge
**Plans**: 8 plans

**Wave 0** *(infrastructure — blocking)*
- [x] 21-01-PLAN.md — LICENSE (MIT, D-17 not-reversible checkpoint) + pyproject.toml [code] extra (openevolve>=0.2.27) + .pre-commit-config.yaml CI lint gate (D-18 layer-1)

**Wave 1** *(parallel — depends on Wave 0)*
- [ ] 21-02-PLAN.md — evolution/code/ package skeleton: __init__.py lazy guard + LICENSING.md + tests/code/__init__.py + output/code/.gitkeep (D-21)
- [ ] 21-03-PLAN.md — code_target_loader.py: CodeTarget dataclass + find_target (D-06/D-08 evolution/ path reject) + find_target_tests AST scan + stratify_tests 20/10 split; 4 unit tests (T-21-RECURSE)
- [ ] 21-04-PLAN.md — code_fitness.py: CodeFitness dataclass + score_candidate (D-11/D-12/D-13/D-14 no-LLM); 6 unit tests (pytest pass/fail × size × ruff)
- [ ] 21-05-PLAN.md — sandbox_runner.py: build_restricted_env (API key strip, D-20/T-21-SECRET) + run_pytest_in_sandbox (timeout 120s, eval_dir cleanup); 4 unit tests
- [ ] 21-06-PLAN.md — code_evolver_adapter.py (唯一 import openevolve 文件, D-03) + tests/code/test_import_boundary.py (D-18 layer-2 pytest gate)

**Wave 2** *(depends on Wave 1)*
- [ ] 21-07-PLAN.md — evolve_code.py Click CLI (--component/--iterations/--dry-run/--max-cost, EvolutionConfig.load 5-param, NOTICE.md D-19) + tests/code/test_evolve_code_cli.py (3 E2E dry-run tests)
- [ ] 21-08-PLAN.md — tests/code/test_ansi_strip_holdout.py: 9-10 edge case holdout tests (D-07: 超长/Unicode/嵌套/截断CSI/OSC/无效字节/CRLF)

### Phase 22: Continuous Evolution Loop
**Goal**: Automated pipeline that periodically runs optimization, validates, and creates PRs
**Depends on**: Phase 21
**Requirements**: V2-LOOP-01
**Success Criteria** (what must be TRUE):
  1. Scheduler runs optimization on configurable interval
  2. Results validated against regression gates before PR creation
  3. Human review required before merge (no auto-merge)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Skill Evolution | - | Complete | Pre-existing |
| 2. Tool Loading | 2/2 | Complete | - |
| 3. Tool Module | 0/1 | Planned | - |
| 4. Tool Dataset & Evaluation | 0/2 | Planned | - |
| 5. Tool Constraints & CLI | 0/2 | Planned | - |
| 6. Tool Pipeline Tests | 0/TBD | Not started | - |
| 7. Prompt Loading | 0/1 | Planned | - |
| 8. Prompt Module | 0/1 | Planned | - |
| 9. Prompt Evaluation | 0/2 | Planned | - |
| 10. Prompt Constraints & CLI | 0/2 | Planned | - |
| 11. Prompt Pipeline Tests | 0/TBD | Not started | - |
