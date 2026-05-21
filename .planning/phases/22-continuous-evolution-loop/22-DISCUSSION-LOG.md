# Phase 22: Continuous Evolution Loop - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 22-continuous-evolution-loop
**Areas discussed:** Scheduler 调度底层, PR 创建机制与仓库拓扑, Loop 范围, 人审 gate 强制机制

---

## Pre-discussion — Todo Fold

| Option | Description | Selected |
|--------|-------------|----------|
| enforce-readonly-hermes-agent (deploy_mode gate) | Phase 20 明确建议推迟到 Phase 22 | ✓ |
| add-lockfile-dspy-pin | 可重现安装, 中高相关 | |
| expand-secret-patterns | PR 边界扩 SECRET, 中相关 | |
| 都不 fold | 保持 Phase 22 纯净 | |

**User's first response (contradictory)**: 同时选了三个具体 todo 和 "都不 fold" — 触发 clarification.

**User's clarified choice:** 仅 fold `enforce-readonly-hermes-agent`. 其他两个 todos 进 deferred ideas (留独立 hygiene phase).

---

## Scheduler 调度底层

### Q1 — 主 scheduler 底层

| Option | Description | Selected |
|--------|-------------|----------|
| GitHub Actions (cloud-native, 推荐) | 零本地依赖, ephemeral runner + per-job secret + native gh CLI + branch protection 原生集成 | ✓ |
| 本地 cron + Python entrypoint | 零云依赖但 host 必须存活 | |
| Python schedule lib (in-process daemon) | 进程内调度, crash 后丢调度 | |
| 多选 (GH Actions 主 + cron 本地补) | 双部署 artifact, 复杂度加倍 | |

**User's choice:** GitHub Actions
**Rationale:** INTEGRATIONS.md 当前零 CI/CD, Phase 22 是第一条 pipeline; GH Actions runner ephemeral + secret 管理 + branch protection 原生集成

### Q2 — 调度频率与触发方式

| Option | Description | Selected |
|--------|-------------|----------|
| Cron weekly + workflow_dispatch (推荐) | 每周一 UTC, 副 trigger workflow_dispatch 带 inputs | ✓ |
| Cron daily (多 CLI 交替) | 加快探索率但增加 PR 噪声 | |
| 仅 workflow_dispatch (手动) | 不满足 SC #1 "scheduled" | |

**User's choice:** Cron weekly + workflow_dispatch
**Rationale:** 频率低足够阅读 PR; manual trigger 支持 ad-hoc 调试

### Q3 — 是否还讨论 Scheduler?

| Option | Description | Selected |
|--------|-------------|----------|
| 下一个区域 (PR 创建与仓库拓扑) | Scheduler 决策已足够 | ✓ |
| 再问几个 Scheduler 问题 | 还有未明确点 | |

**User's choice:** 下一个区域

---

## PR 创建机制与仓库拓扑

### Q1 — PR target 仓

| Option | Description | Selected |
|--------|-------------|----------|
| hermes-agent (推荐) | evolved artifact 是 hermes-agent 的, PR 落到 hermes-agent | ✓ |
| evolution-self (audit 镜像) | 只仓存 metrics, 人手动复制过去 | |
| 双仓 (audit PR 本仓 + 实际 patch PR 在 hermes-agent) | 复杂度高但 audit trail 完整 | |

**User's choice:** hermes-agent
**Rationale:** SC #3 "human review before merge" 反应面集中到一个 reviewer 池, 避免 reviewer 分裂

### Q2 — PR 创建调用方式

| Option | Description | Selected |
|--------|-------------|----------|
| gh CLI subprocess (推荐) | 复用 PROJECT-level gh 现状, 零新依赖 | ✓ |
| PyGithub SDK | 加新依赖, token 管理 | |
| git push + curl GitHub REST API | 错误处理手写 | |

**User's choice:** gh CLI subprocess
**Rationale:** PROJECT.md 提到 'gh' CLI 已隐含使用; subprocess + restricted env 模式与 Phase 20 / Phase 21 同构

### Q3 — 分支命名 + checkout 拓扑

| Option | Description | Selected |
|--------|-------------|----------|
| evolution/auto-loop/<timestamp>/<artifact_kind> (推荐) | 全仓唯一名, timestamp 可跟踪, artifact_kind 可分桶 | ✓ |
| auto/<git-sha-of-output> (内容寻址) | 完全可重现但名字难读 | |
| fork-based PR (workflow 在 evolution-self bot fork 干活) | 隔离最强但设置复杂 | |

**User's choice:** evolution/auto-loop/<timestamp>/<artifact_kind>
**Rationale:** 与 evolve_* 输出 output/<kind>/<ts>/ 对齐, 调试友好

### Q4 — 是否还讨论 PR?

| Option | Description | Selected |
|--------|-------------|----------|
| 下一个区域 (Loop 范围) | PR 决策已足够 | ✓ |
| 再问 1-2 个 PR 问题 (标题/body 模板、secrets) | | |

**User's choice:** 下一个区域

---

## Loop 范围

### Q1 — 调度哪些 evolve_* CLI

| Option | Description | Selected |
|--------|-------------|----------|
| 全部 6 个 CLI 都调度 (推荐) | 完整 V2-LOOP-01 覆盖; yaml 中控制启停 | ✓ |
| 只调 evolve_code + evolve_prompt_sections (高价值 PoC) | Phase 21 新交付优先 | |
| 只调 evolve_code (最小 PoC) | 最小化 | |

**User's choice:** 全部 6 个 CLI
**Rationale:** Phase 22 完整覆盖, 后续可裁剪是可逆扩展

### Q2 — 6 CLI 同一调度周期内的并行性

| Option | Description | Selected |
|--------|-------------|----------|
| 串行, 固定顺序, 上一个 fail 后续还跑 (推荐) | 避免 API rate-limit + 简化成本计算 + reviewer 分辨 | ✓ |
| GH Actions matrix 并行 (每 CLI 一 job) | 加快总时间但 PR×6 同时 | |
| 高/低风险分开调度 (复杂) | 多 cron 分桶 | |

**User's choice:** 串行
**Rationale:** API rate-limit + 简化总成本 + reviewer 体验

### Q3 — 总成本上限策略

| Option | Description | Selected |
|--------|-------------|----------|
| 每个 CLI 独立 max-cost (推荐) — evolution.yaml.loop.<cli>.max_cost_usd 配 | 复用 EvolutionConfig.max_cost_usd 语义; 用户在 yaml 调 sum | ✓ |
| Loop-级总上限 (例 $30/run) | 简化但某 CLI 烧穿后举 | |
| 动态推进 (剩余预算从 sum cap 减) | 代码复杂度加 | |

**User's choice:** 每个 CLI 独立 max-cost
**Rationale:** 复用现有 5-param Config load 链, 用户可调

### Q4 — 是否还讨论 Loop 范围?

| Option | Description | Selected |
|--------|-------------|----------|
| 下一个区域 (人审 gate) | Loop 范围已足够 | ✓ |
| 再问 history 持久化、失败重试 | | |

**User's choice:** 下一个区域

---

## 人审 gate 强制机制

### Q1 — gate 机械化方式

| Option | Description | Selected |
|--------|-------------|----------|
| GitHub branch protection + required reviewers (推荐) | 平台级硬强制, runbook 交付 setup steps | ✓ |
| PR label gate + auto-decline workflow (软强制) | 依赖 evolution 账号不 self-merge 约定 | |
| 仅约定 + NOTICE.md UNREVIEWED 纯文本信号 | 最轻但 SC #3 仅 weakly 满足 | |

**User's choice:** GitHub branch protection + required reviewers
**Rationale:** SC #3 "Human review required before merge (no auto-merge)" 需平台级机械化保证

### Q2 — Pre-merge status checks 组成

| Option | Description | Selected |
|--------|-------------|----------|
| 复用现有 holdout gates (推荐) | 每个 evolve_* CLI 已在 metrics.json 写 holdout_gate_passed; loop 仅 PR 通过的 | ✓ |
| 加 loop-级 cross-artifact gate (鲁棒但高 LOC) | 跑 hermes-agent 全集 test, 多 100-200 LOC | |
| 双层 (上游闭环 + loop 跨 artifact 检查) | 完整 | |

**User's choice:** 复用现有 holdout gates
**Rationale:** SC #2 由上游 CLI 闭环, cross-artifact gate 留 Phase 23+ deferred

### Q3 — deploy_mode gate (fold 进来的 enforce-readonly todo) 实现

| Option | Description | Selected |
|--------|-------------|----------|
| EvolutionConfig.deploy_mode + write_back_description guard (推荐) | Python 层 guard, raise PermissionError; GH Actions runner 设 deploy_mode=production | ✓ |
| 只在 evolve_code 加 guard (scope 最小) | 其他 5 CLI 仍会写回 hermes-agent | |
| OS 文件层 read-only mount (chmod -R a-w) | 超出 Python 范围 + Linux only | |

**User's choice:** EvolutionConfig.deploy_mode + write_back_description guard
**Rationale:** CONCERNS §M6 闭环, 不破坏 local dev 行为

### Q4 — 是否还讨论 人审 gate?

| Option | Description | Selected |
|--------|-------------|----------|
| I'm ready for context (推荐) | 4 区域均已决策 | ✓ |
| 探索额外灰区 (history persistence / secrets 部署 / alert / CLI 子集开关) | | |

**User's choice:** I'm ready for context

---

## Claude's Discretion

- GH Actions YAML 具体结构 (job 命名、step 划分、cache key、Python 版本)
- `gh pr create` 精确 flag 组合 (--draft / label spelling / body source)
- `evolution.yaml` `loop:` 段 schema 嵌套形式
- CODEOWNERS GitHub username (用户在 runbook 中自填)
- branch protection rules 精确 JSON (runbook 用 `gh api`)
- Loop history.json 字段 schema (与 Phase 20 tblite_history.json 对齐)
- 失败告警 (Phase 22 暂依赖 GH Actions 原生 email-on-failure)

## Deferred Ideas

- Loop-级 cross-artifact regression gate (Phase 23+)
- GH Actions matrix 并行调度
- evolution-self audit PR 镜像
- 每 CLI 独立 cron / 不同节奏
- Slack / issue 创建失败告警
- 动态根据 history 自动启停 CLI 的智能调度
- Reviewed-but-not-folded todos: add-lockfile-dspy-pin, expand-secret-patterns, centralize-lm-retry-handling, harden-llm-output-parsing, make-jsonl-loaders-skip-bad-lines, untitled
