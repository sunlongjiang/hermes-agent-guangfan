# Phase 21: Darwinian Code Evolution - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 21-darwinian-code-evolution
**Areas discussed:** 进化引擎选型, 目标组件选型, 适应度函数形状, 许可证 & 安全脚手架范围

---

## Pre-decided (from research / PROJECT.md / PITFALLS, not re-asked)

- output 到 `output/code/` — 不自动 merge (PROJECT.md Out-of-Scope)
- pytest pass = 二进制主门 (PITFALLS / FEATURES anti-feature 警告)
- 硬 exclude `evolution/` 自身 (recursive self-evolution anti-feature)
- 架构 lives in `evolution/code/` (stub 已存在)
- 复用 v1 pipeline pattern (load → dataset → optimize → constrain → eval → save)

---

## Area 1: 进化引擎选型

| Option | Description | Selected |
|--------|-------------|----------|
| openevolve 适配 (推荐) | openevolve>=0.2.27 Apache-2.0, single-import-surface adapter, ~150-300 LOC. AGPL 边界永久消解。 | ✓ |
| Roll-your-own DSPy+GEPA | 复用 GEPA reflection 模式,零新依赖,~400-600 LOC,但自管 population/archive/diversity。 | |
| darwinian-evolver subprocess | 仅当能拿到 AGPL 包时,subprocess + .venv-agpl + CI lint gate。最重路径。 | |

**User's choice:** openevolve 适配
**Follow-up — LLM 路径如何摆:**

| Option | Description | Selected |
|--------|-------------|----------|
| openevolve 原生 client + 复用 evolution.yaml 配置值 | adapter 读 EvolutionConfig.optimizer_model/api_base/api_key 实例化 openevolve 原生 client。联运身划一。 | ✓ |
| openevolve 独立配置 (不共享) | 走自己的 env, 文档说明两套。零胶水,适合 PoC,但两套配置文档要维护。 | |
| 先干一点 — planner 实际读 openevolve API 后决 | CONTEXT 记 Claude's Discretion,默认偏复用。 | |

**User's choice:** openevolve 原生 client + 复用 evolution.yaml 配置值
**Notes:** Phase 21 LLM 调用配置值统一,但客户端实例不走 dspy.LM。Risk anchor 记入:openevolve 若不接受 base_url override 需 shim,planner Task 1 spike 验证。

---

## Area 2: 目标组件选型

候选候选清单 (按 pytest 覆盖 + 行数 + 安全敏感度三个维度):

| File | Lines | Tests | Type |
|------|-------|-------|------|
| tools/ansi_strip.py | 44 | 30 | 纯算法 (regex+CSI/SGR strip) |
| tools/binary_extensions.py | 42 | 0 (无专属) | 准则表 |
| agent/retry_utils.py | 57 | 9 | 重试策略 |
| agent/redact.py | 181 | 43 | **安全敏感 — FEATURES 警告** |
| agent/model_metadata.py | 1001 | 75 | metadata table |

| Option | Description | Selected |
|--------|-------------|----------|
| tools/ansi_strip.py (推荐) | 44 行纯算法 (CSI/SGR 转义去除), 30 pytest, 零安全敏感路径。理想 PoC。 | ✓ |
| agent/retry_utils.py | 57 行策略代码, 9 tests (覆盖偏薄)。可能从进化中获益但信号弱。 | |
| agent/redact.py | 181 行, 43 tests 覆盖准饱。⚠ 安全敏感 (PII/凭证脱敏),FEATURES 明说不行。 | |

**User's choice:** tools/ansi_strip.py
**Follow-up — Holdout 怎么切:**

| Option | Description | Selected |
|--------|-------------|----------|
| 20/10 随机划分 (seed 固定) | 30 测试随机抽 20 train / 10 holdout。零额外测试,变异可能远跳出 train 分布。 | |
| 20/10 分层切 + 手补 5-10 个 edge case | 按 CSI/SGR/OSC 三类分层 + 手补长输入 / Unicode 边界 / 嵌套转义等 edge case 进 holdout。+10-20 LOC,holdout 信号稳。 | ✓ |
| 30/0 + 另写独立小型 property-based holdout | 30 全进 train,另写 hypothesis property-based 或 fuzzing。隔离最干净,需拼写 5-10 fuzzing 输入。 | |

**User's choice:** 20/10 分层切 + 手补 5-10 个 edge case
**Notes:** holdout edge case 测试写在 evolution 仓 (`tests/code/test_ansi_strip_holdout.py`),不入 hermes-agent。

---

## Area 3: 适应度函数形状

| Option | Description | Selected |
|--------|-------------|----------|
| 纯 pytest + size penalty (推荐) | fitness = pytest_pass_rate + size penalty (>×1.2 罚 0.3 / >×1.5 reject)。零 LLM judge, 全 deterministic。 | |
| pytest + size + ruff (lint score) | 加 ruff check 转 0-1 score。零 LLM cost, 多一个 subprocess。 | ✓ |
| pytest + size + ruff + LLM nudge (0.1 权重) | 加 LLM-as-judge 看可读性 (≤0.1 权重避免 flaky)。多一跳 LLM cost / iter。 | |

**User's choice:** pytest + size + ruff (lint score)
**Notes:** PITFALLS 明确 LLM judge 在代码域 flaky;本期连 ≤0.1 nudge 也不开。ruff config 缺失退化风险记入 PLAN 注意事项 (planner 加最小 ruff.toml: select=[E,F,W], line-length=120)。

---

## Area 4: 许可证 & 安全脚手架范围

| Option | Description | Selected |
|--------|-------------|----------|
| LICENSE.md 在仓根 | PITFALLS Phase 21 前置, MIT/Apache-2.0 选定。不可逆,不能拖。 | ✓ |
| CI lint gate 禁止 evolver upstream 走出 adapter | pre-commit hook + pytest 校 `import openevolve` 只在 adapter 出现。营造单点 import 面架构习惯。 | ✓ |
| output/code-evolved/ + NOTICE.md (LLM 生成源记录) | 每次 evolve 同目录 NOTICE.md,Phase 22 自动 loop 时反向依赖。 | ✓ |
| Candidate 代码的评分沙箱 (subprocess+timeout) | candidate 评分走 subprocess + 30/120s timeout + restricted env (削减 API keys / PYTHONPATH)。 | ✓ |

**User's choice:** **全部 4 项都进本期**
**Follow-up — LICENSE 选哪个:**

| Option | Description | Selected |
|--------|-------------|----------|
| MIT (推荐) | 最宽松,与 openevolve (Apache-2.0) 与 DSPy (MIT) 完全兼容。 | ✓ |
| Apache-2.0 | 与 openevolve 完全对齐,多专利不告条款。 | |
| Claude's Discretion (planner 默认 MIT) | 留 planner 自决, 默认偏 MIT。 | |

**User's choice:** MIT
**Notes:** LICENSE 版权人 planner 用 git config user.name 默认填,但提交前 executor checkpoint 必须 AskUserQuestion 确认 (这是不可逆决策)。

---

## Claude's Discretion (留 planner / executor 决)

- openevolve 进化循环参数 (population_size / archive_size / mutation_temperature / max_generations) — planner 读 openevolve docs 给保守 PoC 默认
- `code_target_loader.find_target_tests` 的 AST 解析具体实现
- ruff_score / size_component 三段映射的精确分位 (D-12/D-13 允许 ±0.1)
- eval_dir 命名与清理时机 (TemporaryDirectory vs 手动 rmtree)
- openevolve native client 的具体 SDK (OpenAI / litellm / 内置 wrapper) — planner spike Task 1
- holdout 5-10 edge case 测试的具体内容
- `metrics.json` 字段命名前缀 (`code_*` 推荐)
- LICENSE 版权人具体值 (executor 确认)

---

## Deferred Ideas

- 多组件批量进化 / `--components a,b,c` / 跨组件 fitness
- LLM-as-judge code quality nudge (0.1 权重) — 留至 ruff+pytest 不够时新 phase
- Property-based / fuzzing holdout (Hypothesis / atheris)
- Modal / firejail / docker sandbox — subprocess + restricted_env + timeout 在 PoC 足够
- CodeMetric 抽象 + 多 evolver plugin 注册中心 — 第二个 evolver 出现时再抽
- evolved 代码自动 PR / 自动 merge — Phase 22 永久不入
- Recursive self-evolution — **永久** out-of-scope
- 安全敏感组件演化 (auth / sandbox / 凭证 / redact) — **永久** out-of-scope
- darwinian-evolver / AGPL 隔离基础设施 — openevolve 决策已 defuse,**永久** 不需建
- Cross-run 历史 metrics 持久化 — Phase 16 dashboard 扩展时再加 code_* 前缀分桶
- `--allow-fallback` 真实降级路径 (self-rolled DSPy+GEPA loop) — 本期占位 flag,不实做
- 多语言代码进化 (TypeScript / Rust / Go) — 需求触发再开 phase
- ROADMAP.md goal text 与 CONTEXT.md 替换说明同步 — 留 milestone cleanup phase
