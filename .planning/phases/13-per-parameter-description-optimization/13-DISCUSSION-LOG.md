# Phase 13: Per-Parameter Description Optimization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-07
**Phase:** 13-per-parameter-description-optimization
**Areas discussed:** 模块暴露方式, CLI 形态, Phase 13 范围切分, 评估数据与指标

---

## 模块结构（暴露方式）

| Option | Description | Selected |
|--------|-------------|----------|
| 每 param 一个 Predict（推荐） | 二维字典 tool→param→Predict，GEPA 通过 named_parameters() 发现每 param | ✓ |
| 每 tool 一个 Predict（bundle） | Signature.instructions 内嵌所有 params；内部解析回文本 | |
| 扁平 + 导航字典 | 保留 tool_predictors（冻结）+ 并列 param_predictors | |

**User's choice:** 每 param 一个 Predict
**Notes:** 与 Phase 3 D-04 模式一致，最细粒度，便于 GEPA 独立变异。

## 冻结机制

| Option | Description | Selected |
|--------|-------------|----------|
| 物理隔离（推荐） | tool-level desc 不作为 Predict 暴露，只读字符串 | ✓ |
| API 标记 frozen | 注册但通过 dspy.Predict.freeze 或自定义排除 | |

**User's choice:** 物理隔离
**Notes:** 与成功标准 2 对齐；GEPA 物理上无法触碰 tool-level。

## 参数筛选

| Option | Description | Selected |
|--------|-------------|----------|
| 全部参数 | 所有 param 都注册，包括空描述（GEPA 可从零生成） | ✓ |
| 仅非空 | 只给 description 非空的 param 注册 Predict | |
| CLI 指定子集 | 通过 --tools 或显式子集挑选 | |

**User's choice:** 全部参数
**Notes:** 空描述走 size/factual/consistency 约束，跳过 growth 检查。

## 命名与存储

| Option | Description | Selected |
|--------|-------------|----------|
| 两维字典（推荐） | self.param_predictors[tool_name][param_name] | ✓ |
| 扁平字符串 | self.param_{tool}_{name}_desc 拼接命名 | |

**User's choice:** 两维字典
**Notes:** 避免 tool/param 名冲突；get_evolved_descriptions() 易回溯。

---

## CLI 入口形态

| Option | Description | Selected |
|--------|-------------|----------|
| 新立独立入口（推荐） | evolution/tools/evolve_tool_params.py，原 Phase 5 CLI 不变 | ✓ |
| 原 CLI 加 --target 开关 | evolve_tool_descriptions --target params/top-level/joint | |
| 抽 core 共享 | evolve_tools_core() 重构，两个 CLI 都调用 | |

**User's choice:** 新立独立入口
**Notes:** 两条管道独立调试，边界清晰，向后兼容。

## 级联 / 向后兼容

| Option | Description | Selected |
|--------|-------------|----------|
| 完全分管（推荐） | 不在 Phase 5 CLI 加 --with-params；各自独立 | ✓ |
| 追加 --with-params 级联 | 运行 top-level 后自动跟 param-only 第二轮 | |

**User's choice:** 完全分管

## CLI 开关清单

| Option | Description | Selected |
|--------|-------------|----------|
| --tools 子集筛选 | 逗号分隔工具名，便于小范围验证 | ✓ |
| --max-cost-usd / --reflection-model | 响应 CONCERNS M8 成本失控 | ✓ |
| --baseline-run 指向 Phase 5 输出 | v1 回归门数据源 | ✓ |
| --param-group-size cap | Pitfall 1 #3 分组优化；留作 knob | ✓ |

**User's choice:** 四个都要

---

## Phase 13 Scope 切分

| Option | Description | Selected |
|--------|-------------|----------|
| joint fitness + param cap | PITFALLS #1/#3 + CONCERNS M3 行为约束 | ✓ |
| param_consistency 约束 | LLM 整 tool 批检，Pitfall 1 #2 | ✓ |
| per-tool rate 持久化 | metrics.json 记两份 dict，CONCERNS M3 | ✓ |
| 成本上限闸 | max_cost_usd + 超限 abort，CONCERNS M8 | ✓ |

**User's choice:** 四项全部落地 Phase 13

## v1 baseline 回归门强度

| Option | Description | Selected |
|--------|-------------|----------|
| 硬门：v2 须追平或超过 v1（推荐） | per-param holdout < baseline - 0.02 → FAIL | ✓ |
| 警告 | 记录但不 abort | |
| 推到 Phase 14 | Phase 14 SessionDB 重构 dataset 后再做 | |

**User's choice:** 硬门

## param-group-size cap 默认

| Option | Description | Selected |
|--------|-------------|----------|
| --param-group-size=3（研究推荐） | 严格上限 3，>5 时分组 | |
| 宽些 = 5 | 8+ 参数才触发 | |
| 无 cap（仅靠成本限制） | 依赖 max_cost_usd + max_metric_calls 双重约束 | ✓ |

**User's choice:** 无 cap（只用成本限制）
**Notes:** D-15 记录 rationale — 成本门限存在时过度 cap 压缩探索空间；cap 留作可选 CLI knob。

## 成本上限策略

| Option | Description | Selected |
|--------|-------------|----------|
| 默认 20 USD + abort（推荐） | 匹配 CLAUDE.md 成本声明 | ✓ |
| 默认 50 USD | 容忍 Phase 13 fan-out | |
| 仅追踪不 abort | 记 metrics 但不中断 | |

**User's choice:** 20 USD + abort

## param_consistency 粒度

| Option | Description | Selected |
|--------|-------------|----------|
| 整 tool 批检（推荐） | 一 LLM 调用传 top-level + 全部 params 一次性判定 | ✓ |
| Pairwise | 两两比对，O(n²) 调用 | |
| 仅 regex 推迟 LLM | 空描述 / 关键词污染 / 长度异常正则 | |

**User's choice:** 整 tool 批检

---

## 评估指标

| Option | Description | Selected |
|--------|-------------|----------|
| 复用 tool_selection_metric | 仅打 tool 名，param 不评 | |
| joint（tool + param）（推荐） | metric = 0.5 * tool + 0.5 * param_match | ✓ |
| param-only | 仅打 param，tool 当 given | |

**User's choice:** joint（tool+param）

## param 打分算法

| Option | Description | Selected |
|--------|-------------|----------|
| exact-match（推荐） | dict 逐对 key/value 比较，确定性 | ✓ |
| LLM judge | 语义宽容但变差高且贵 | |
| key-level F1 | 只看 key 覆盖，忽略 value | |

**User's choice:** exact-match

## joint 权重

| Option | Description | Selected |
|--------|-------------|----------|
| 均分 50/50（推荐） | 0.5 * tool + 0.5 * param | ✓ |
| tool 优先 70/30 | 保 tool 选择 | |
| 乘积门 | tool 错 → 0；最严 | |

**User's choice:** 50/50

## 数据集策略

| Option | Description | Selected |
|--------|-------------|----------|
| 复用 Phase 4 数据集（推荐） | datasets/tools/ 已含 correct_params | ✓ |
| 新建 param-focused | 新 ToolParamDatasetBuilder + 混淆场景 | |
| 维原状 + 添加 50-100 场景 | 折衷 | |

**User's choice:** 复用 Phase 4

## forward() 扩展

| Option | Description | Selected |
|--------|-------------|----------|
| selector 同时输出 tool + params（推荐） | 单次调用返回两字段，selected_params JSON 编码 | ✓ |
| two-pass tool → params | 先选 tool 再按选中 tool 的 param_predictors 逐个生成 | |
| forward 不变 + judge | 只改 metric 层，用 LLM judge 对比 | |

**User's choice:** selector 一次性输出两字段

---

## Claude's Discretion

- ToolSelectionWithParamsSignature 的字段 desc 文本与 JSON 编码约定（允许 `{}`）
- cost_tracker 的 token→USD 换算表
- ParamConsistencyChecker 的 Signature / system prompt 具体文本
- ABORTED / FAILED 目录布局细节（参考 Phase 5）
- evolve_tool_params 的 Rich 表格展示

## Deferred Ideas

- Joint optimization（tool + param 同轮进化）→ Phase 17
- Per-tool distribution dashboard（p25 gate, CONCERNS M3 + Pitfall 10）→ Phase 16
- SessionDB-driven param scenario augmentation → Phase 14
- Think-augmented param selection → Phase 15
- 写回 dry-run / git 干净校验 / deploy_mode → Phase 22（CONCERNS M6）
- JSONL 单行鲁棒加载（CONCERNS M7）→ 独立 hygiene fix
- LLM 输出解析强化 typed OutputField（CONCERNS M4）→ 独立
- `_format_paren_concat` Unicode / nested quote 鲁棒性（CONCERNS L1）→ Phase 13 写回放大时需补
