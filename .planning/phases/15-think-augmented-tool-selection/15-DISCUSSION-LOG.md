# Phase 15: Think-Augmented Tool Selection - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-09
**Phase:** 15-think-augmented-tool-selection
**Areas discussed:** Reasoning 模块结构, A/B 路由策略, CLI 入口形态, A/B 验收门 + ambiguous 子集定义

---

## Reasoning 模块结构

### Q1 — Reasoning 可优化参数如何暴露给 GEPA？
| Option | Description | Selected |
|--------|-------------|----------|
| A) 独立 Predict + selector InputField | reasoner 是一个独立 `dspy.Predict(ToolReasoningSignature)`，`reasoning` 作为 selector 的 InputField 传入 | ✓ |
| B) 两段链 sub-Module | reasoner 与 selector 用同一个 sub-Module 串起来 | |
| C) 复用现有 CoT instructions | 不新建 Predict，直接把 reasoning prompt 合并进 selector CoT | |

**User's choice:** A
**Notes:** 保持模块职责清晰，GEPA 只见一份新 instructions。

### Q2 — ToolReasoningSignature 输入输出字段？
| Option | Description | Selected |
|--------|-------------|----------|
| A) (task, tools)→reasoning；selector 保留完整 tools | reasoner 只产出 reasoning 文本，selector 仍看完整 tool 列表 | ✓ |
| B) reasoner 输出 reasoning + candidates | reasoner 预筛 candidate tools 交给 selector | |
| C) (task)→reasoning；selector 拿工具表 | reasoner 不见 tools，只读 task | |

**User's choice:** A
**Notes:** 避免 reasoner 把筛选责任揽走，P4 Pitfall 对齐。

### Q3 — Reasoning Predict 粒度
| Option | Description | Selected |
|--------|-------------|----------|
| A) 全局单 reasoner Predict | 全部 tool 共享一条 reasoning 模板 | ✓ |
| B) per-tool reasoner Predict | 每个 tool 独立 reasoner | |

**User's choice:** A

### Q4 — reasoning 长度 200-token cap 如何落地？
| Option | Description | Selected |
|--------|-------------|----------|
| A) max_tokens=200 硬截 + prompt 模板提示 | 双保险：LM config 硬截 + instructions 口头提示 | ✓ |
| B) 只用 prompt 提示 | 依赖 prompt 自觉 | |
| C) 硬截 + post-eval Checker 双保险 | 再加一个后校验 | |

**User's choice:** A
**Notes:** Constraint 链不需要额外 Checker。

---

## A/B 路由策略

### Q1 — think 调用的路由策略
| Option | Description | Selected |
|--------|-------------|----------|
| A) opt-in flag | think-mode 二选一 | ✓ |
| B) hybrid (运行时路由) | 根据任务特征动态选择 | |
| C) always-think | 永远启用 | |

**User's choice:** A

### Q2 — v1 baseline gate 的 A/B 对比两边
| Option | Description | Selected |
|--------|-------------|----------|
| A) think-off baseline vs think-on evolved | 对照是无 reasoning 的原 selector | ✓ |
| B) think-on default vs think-on evolved | 都带 reasoning 只比优化前后 | |
| C) 三者都跟 | 同时跟 think-off/think-on default/think-on evolved | |

**User's choice:** A

### Q3 — enable_reasoning 的 toggle 时机
| Option | Description | Selected |
|--------|-------------|----------|
| A) constructor arg + 静态分叉 | 两条 pipeline 分别构建两个 ToolModule 实例 | ✓ |
| B) runtime mutator | 常驻构造 reasoner，运行时决定是否调用 | |

**User's choice:** A

### Q4 — latency/token 采样 + 3 重门判决放哪
| Option | Description | Selected |
|--------|-------------|----------|
| A) 独立 think_metrics.py + ThinkABGate 类 | 不污染 fitness/metric 模块 | ✓ |
| B) cost 进 fitness 函数 | metric 里直接加 cost 项 | |
| C) inline 在 CLI | 判决逻辑写在 CLI 里 | |

**User's choice:** A

---

## CLI 入口形态

### Q1 — think-augmented CLI 入口放哪里
| Option | Description | Selected |
|--------|-------------|----------|
| A) 独立新 CLI | evolution/tools/evolve_tool_reasoning.py | ✓ |
| B) 在 evolve_tool_params.py 加 --enable-reasoning flag | 复用 Phase 13 CLI | |
| C) 抽共享 pipeline 模块 | think_ab_pipeline.py 公共 | |

**User's choice:** A
**Notes:** 避免 Phase 13 CLI 承担 A/B 职责。

### Q2 — CLI 里跑几个 baseline 门
| Option | Description | Selected |
|--------|-------------|----------|
| A) 双门 V1BaselineGate + ThinkABGate | V1 管全集不回归，ThinkAB 管 A/B + latency | ✓ |
| B) 单门 只看 ThinkAB | 不跟 v1 | |
| C) 省掉 think-off 只比 v1 | think-on 直接 vs v1 | |

**User's choice:** A

### Q3 — 成功 run 的输出物
| Option | Description | Selected |
|--------|-------------|----------|
| A) 独立 output/tools_reasoning/ + 完整 metrics/prompt/diff/ab_comparison | 与 Phase 13 物理隔离 | ✓ |
| B) 复用 output/tools/ 加后缀 | 文件混放易混淆 | |
| C) 独立目录但不写 descriptions | 只写 reasoning_prompt | |

**User's choice:** A

### Q4 — 新 CLI 暴露哪些参数
| Option | Description | Selected |
|--------|-------------|----------|
| A) 四个新 flag + 复用 P13 通用 flags | --reasoning-tokens-cap/--ab-tolerance-pp/--latency-budget-sec/--ambiguous-only + --eval-source 等 | ✓ |
| B) 极简 2 flag | 只暴露 reasoning cap + tolerance | |
| C) 全 config 无 CLI flag | 一切走 EvolutionConfig | |

**User's choice:** A

---

## A/B 验收门 + ambiguous 子集定义

### Q1 — ambiguous 子集如何定义
| Option | Description | Selected |
|--------|-------------|----------|
| A) 模糊多候选 (≥ 3 合法工具) | 复用 ToolSelectionExample.confuser_tools 字段 | ✓ |
| B) 启发式关键词/长度规则 | 关键词"好像/也许/or"或任务长度判定 | |
| C) LLM judge 整批打标 ambiguous | 一次性 judge pass | |

**User's choice:** A
**Notes:** 已有字段，零新代码；与 Phase 14 mining 兼容。

### Q2 — ThinkABGate 三重门组合
| Option | Description | Selected |
|--------|-------------|----------|
| A) 三重 AND：全集不回归 + ambiguous +3pp + latency p95≤5s | 同时防偏、防延迟、证价值 | ✓ |
| B) 只抗 ambiguous 子集门 | 其它只警告 | |
| C) 两重门 + latency 观察 | latency 不拦截 | |

**User's choice:** A

### Q3 — 三重门阈值放哪里
| Option | Description | Selected |
|--------|-------------|----------|
| A) 硬编码默认 + CLI 覆盖 | think_metrics.py 常量，CLI flag 覆写 | ✓ |
| B) 进 EvolutionConfig | 走 config 文件层 | |
| C) 推迟到 PLAN 阶段 | Wave 0 RED 时再定 | |

**User's choice:** A

### Q4 — ambiguous 子集太小（<5 例）怎么处理
| Option | Description | Selected |
|--------|-------------|----------|
| A) skip 并标记 | ambiguous_gate_skipped=true；run 仍 PASS | ✓ |
| B) 硬要求 ≥ 5 | 小样本直接 FAILED | |
| C) 宽容 tolerance | 子集 <5 时放宽阈值到 ±5pp | |

**User's choice:** A

---

## Claude's Discretion

- Wave 数量、RED 测试分片顺序（`ThinkABGate` 单测先 vs `ToolModule.enable_reasoning` 构造先）由 planner 决定。
- `ab_comparison.json` 的具体字段名由 planner pin 死（参考命名：`task_id` / `correct_tool` / `selected_off` / `selected_on` / `reasoning_on`）。
- `think_metrics.py` 是否同时暴露类 API + 函数 API（参考 `v1_baseline_gate.py` 惯例）。

## Deferred Ideas

- Hybrid 运行时路由 → 未来 phase。
- per-tool reasoner → 等 Phase 16 dashboard 出数据后评估。
- ab_comparison.json 的错例分析 CLI / skill → Phase 16 延展。
- sessiondb 新增人工 ambiguous 标签 → 不做。
- Bayesian 显著性检验门 → 当前用固定 pp 阈值。
