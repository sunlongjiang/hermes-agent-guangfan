# Phase 5: Tool Constraints & CLI - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-16
**Phase:** 05-tool-constraints-cli
**Areas discussed:** 事实准确性检查, CLI 编排流程, 约束集成策略, 输出与保存格式

---

## 事实准确性检查

| Option | Description | Selected |
|--------|-------------|----------|
| 原始 vs 进化对比 | 把原始描述和进化后描述一起传给 LLM，问"进化后的描述是否声称了原始描述中不存在的能力？"。简单直接，和 Phase 1 的 LLM-as-judge 模式一致 | ✓ |
| 代码对照验证 | 传入原始描述 + 工具的实际代码/实现，让 LLM 判断进化后描述是否与实际实现一致。更强但需要读取工具源码 | |
| 双重验证 | 同时做两者：先对比原始描述，再对照代码。最强但 API 调用成本加倍 | |

**User's choice:** 原始 vs 进化对比
**Notes:** 无

| Option | Description | Selected |
|--------|-------------|----------|
| Pass/Fail 二值 | pass/fail 二值："新增了虚假能力"→ fail，否则 pass。和 Phase 4 的 tool_selection_metric 保持一致 | ✓ |
| 连续分数 | 返回 0-1 连续分数，表示事实准确程度。更细粒度但 constraint 通常是硬门禁 | |
| 三层级 | pass / warning / fail 三层，warning 记录但不拒绝。更灵活但增加复杂度 | |

**User's choice:** Pass/Fail 二值
**Notes:** 无

| Option | Description | Selected |
|--------|-------------|----------|
| 独立文件 | 新建 `ToolFactualChecker` 类，放在 evolution/tools/tool_constraints.py。和 tool_loader、tool_module 并列 | ✓ |
| 扩展 ConstraintValidator | 扩展现有 ConstraintValidator，添加 _check_factual_accuracy() 方法。集中管理但 constraints.py 会变大 | |

**User's choice:** 独立文件
**Notes:** 无

---

## CLI 编排流程

| Option | Description | Selected |
|--------|-------------|----------|
| 单文件 CLI+逻辑 | 像 evolve_skill.py 一样，一个 evolve_tool_descriptions.py 包含 CLI 入口 + evolve() 业务逻辑。最简单直接 | ✓ |
| CLI 与逻辑分离 | CLI 入口和编排逻辑分离到两个文件。更可测但增加复杂度 | |

**User's choice:** 单文件 CLI+逻辑
**Notes:** 无

| Option | Description | Selected |
|--------|-------------|----------|
| 复制 evolve_skill 流程 | loader → module → dataset(synthetic/load) → GEPA optimize → constraint validate → holdout evaluate → save。和 evolve_skill.py 完全一致 | ✓ |
| 分层优化 | 先 per-tool 优化，再联合优化。更精细但复杂度高 | |

**User's choice:** 复制 evolve_skill 流程
**Notes:** 无

| Option | Description | Selected |
|--------|-------------|----------|
| 标准四参数 | --iterations, --eval-source(synthetic/load), --hermes-repo, --dry-run。和 ROADMAP 要求完全一致 | ✓ |
| 扩展参数集 | 额外加 --dataset-path, --optimizer-model, --eval-model。和 evolve_skill.py 保持一致 | |

**User's choice:** 标准四参数
**Notes:** 无

---

## 约束集成策略

| Option | Description | Selected |
|--------|-------------|----------|
| 组合复用 | 复用现有 ConstraintValidator 的 size_limit + growth_limit + non_empty，加上新建的 ToolFactualChecker。CLI 中顺序调用两者 | ✓ |
| 统一封装 | 新建 ToolConstraintValidator 封装所有工具相关约束（包含 size + factual），提供单一入口 | |

**User's choice:** 组合复用
**Notes:** 无

| Option | Description | Selected |
|--------|-------------|----------|
| 优化后门禁 | GEPA 优化完成后、holdout 评估之前执行约束验证。和 Phase 1 的 post-optimization constraint gate 一致 | ✓ |
| 每迭代检查 | GEPA 每次迭代都检查。更严格但增加 API 成本 | |

**User's choice:** 优化后门禁
**Notes:** 无

---

## 输出与保存格式

| Option | Description | Selected |
|--------|-------------|----------|
| output/ 目录 | 进化结果保存到 output/tools/ 目录，不直接修改 hermes-agent。和 PROJECT.md "输出到 output/ 目录即可" 一致 | ✓ |
| 直接写回 | 默认写回 hermes-agent 的 tools/*.py，--dry-run 只展示不写入 | |

**User's choice:** output/ 目录
**Notes:** 无

| Option | Description | Selected |
|--------|-------------|----------|
| 描述 + 指标 + diff | 保存进化后的描述文本 + 评估指标 JSON（baseline vs evolved scores）+ before/after diff 文本。和 evolve_skill 的 output 模式一致 | ✓ |
| 仅描述文本 | 只保存进化后的描述文本。最简单 | |

**User's choice:** 描述 + 指标 + diff
**Notes:** 无

| Option | Description | Selected |
|--------|-------------|----------|
| 设置验证 + 预览 | 验证设置（能找到 hermes-agent、能加载工具、能生成/加载数据集）+ 展示将要优化的工具列表，不运行 GEPA | ✓ |
| 完整运行不保存 | 运行完整管道但最后不保存结果。更完整但仍然花费 API 调用 | |

**User's choice:** 设置验证 + 预览
**Notes:** 无

---

## Claude's Discretion

- `ToolFactualChecker` 内部的 DSPy Signature 设计
- LLM 输出的 JSON 解析策略
- diff 输出的具体格式
- 输出目录的子结构组织方式

## Deferred Ideas

None — discussion stayed within phase scope
