# Phase 17: Joint Section Optimization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-15
**Phase:** 17-joint-section-optimization
**Areas discussed:** Round-robin 共存策略, A/B baseline 与软门, CLI 形态 + iteration 预算, Output schema & metrics.json 字段

---

## Round-robin 共存策略

### Q1: Joint 上线后, round-robin 路径怎么处理?

| Option | Description | Selected |
|--------|-------------|----------|
| 保留 round-robin 为 fallback/--legacy(推荐) | joint 默认,round-robin 通过 --mode round-robin 或 --legacy 保留;复用同一 CLI;A/B 证明可复用 | ✓ |
| 直接删除 round-robin 路径 | PromptModule 仅保留 joint mode,set_active_section 改名或拆除;代价是 11 个测试用例同步改 | |
| Joint 独立为新 CLI | evolve_prompt_sections_joint.py 完全独立,各自维护 | |

**User's choice:** 保留 round-robin 为 fallback/--legacy
**Notes:** 倾向最低破坏面、保留 fallback 价值,避免 11 个测试用例回归。

### Q2: Joint 作为默认后,现有无 flag 调用怎么走?

| Option | Description | Selected |
|--------|-------------|----------|
| 静默切换到 joint(最简) | 不传 flag 就走 joint,所有现有脚本被隐式提升 | ✓ |
| 默认 joint + 启动时 stdout 提示 | 黄色 stdout 提示 "Using joint mode (default)" | |
| 默认 round-robin,joint 仅 --mode joint 启用 | joint opt-in,默认 round-robin | |

**User's choice:** 静默切换到 joint(最简)
**Notes:** 用户接受 "新默认仅在 README/docstring 标注" 的迁移成本。

### Q3: 现有的 `--section <id>` flag 怎么与 joint 默认共处?

| Option | Description | Selected |
|--------|-------------|----------|
| --section 隐含 round-robin 单点跑(推荐) | 传 --section 就走 round-robin 单段优化,不需 --mode | ✓ |
| --section 与 --mode joint 互斥,传了报错 | 显式互斥,exit 2 | |
| --section 走 joint 但 freeze 其他 section | 单参数 joint 等价于 round-robin 单点,语义重复 | |

**User's choice:** --section 隐含 round-robin 单点跑

### Q4: 选 mode 的 flag 语义怎么设计?

| Option | Description | Selected |
|--------|-------------|----------|
| --mode joint\|round-robin(默认 joint) | click.Choice 枚举,易扩展第 3 模式 | ✓ |
| --legacy / --joint(二选一 boolean) | 简单 boolean,未来扩第 3 模式难 | |

**User's choice:** --mode joint|round-robin(默认 joint)

---

## A/B baseline 与软门

### Q1: Joint 跑完后,怎么拿到 "同 dataset round-robin 得分" 作对比?

| Option | Description | Selected |
|--------|-------------|----------|
| Inline:joint 跑完后同一 CLI 再跑一遍 round-robin当 baseline(推荐) | LM 调用 ×2,但 apples-to-apples | ✓ |
| External:--baseline-run <ts> 读历史 round-robin output | 成本低但 dataset/微扣加变设后古提不可复现 | |
| 软验证:仅拿 holdout 绝对得分与历史最高分作软参考 | 不跑 baseline,成功标准 3 难证 | |

**User's choice:** Inline A/B
**Notes:** apples-to-apples 优先于成本。

### Q2: Inline A/B 跳出:joint < round-robin 时 CLI 怎么现?

| Option | Description | Selected |
|--------|-------------|----------|
| 软门: stdout 黄警告 + 两者都落盘(推荐) | metrics.json 双列,evolved_sections.json 仍写出 | ✓ |
| 硬门: joint < round-robin - eps 则 exit 2 不部署 | CI 硬限,但 LLM-judge 方差大易误杀 | |
| 表现中性:仅记录 metrics,不告警也不拦截 | 最轻,但 "证明" 软 | |

**User's choice:** 软门 + 双列落盘 + 黄警告

### Q3: epsilon 怎么定?

| Option | Description | Selected |
|--------|-------------|----------|
| joint_score ≥ roundrobin_score - 0.01 (1 pp 宽容) | 紧;LLM-judge 噪声本身在 1pp 量级 | ✓ |
| joint_score ≥ roundrobin_score - 0.02 (2 pp 宽容) | 与 Phase 13/16 工具 regression 警告齐 | |
| 参数化 --epsilon-pp 0.02(默认) | Click flag,运行时可调 | |

**User's choice:** 1pp 固定常量,不暴露为 flag
**Notes:** prompt 评分场景比工具评分更需要 "几乎相同" 的判定;以后扩 holdout 再考虑参数化。

### Q4: Round-robin baseline 跑 inline 时,iteration 预算能不能压缩避免成本翻倍?

| Option | Description | Selected |
|--------|-------------|----------|
| Baseline round-robin 跑全量 iterations(与现有一致) | 6× LM 调用但 A/B 对称 | ✓ |
| Baseline 仅跑 1 轮 round-robin(不优化) | Baseline 变成 "未优化 prompt holdout 得分",证明软 | |
| Baseline 用 --baseline-iterations 另给预算 | 默认与 --iterations 一致,可减半;多一个 flag | |

**User's choice:** Baseline 跑全量

---

## CLI 形态 + iteration 预算

### Q1: joint mode 下 `--iterations N` 的语义怎么定?

| Option | Description | Selected |
|--------|-------------|----------|
| joint N 次总体;baseline 仍 5N(推荐) | joint 是 1 次优化过程,N 轮 GEPA reflection;baseline 是 5 次独立优化,各 N 轮 | ✓ |
| joint 5N 次(总 LM 调用对齐 round-robin) | A/B 公平,但 GEPA 在 5 参数下是否需 5× 轮次需研究 | |
| 参数化 --joint-iterations 单独(默认与 iterations 一致) | 明确但多一个 flag | |

**User's choice:** joint N 总体;baseline 5N

### Q2: GEPA 的 `max_metric_calls` 怎么推出 N 轮?

| Option | Description | Selected |
|--------|-------------|----------|
| joint: iterations × 50 × 5(与参数数量成正比) | 5 参数需要更多 budget 收敛多参数空间 | ✓ |
| joint: iterations × 50(与单 section round-robin 一致) | budget 不变,可能不足 | |
| 不预设,交 researcher 查 DSPy 文档后决 | 弹性 | |

**User's choice:** iterations × 50 × 5 起点
**Notes:** Researcher 若查到更精确公式可微调,本期定 ×5 起点。

### Q3: CLI 启动时要不要打预算预估?

| Option | Description | Selected |
|--------|-------------|----------|
| stdout 启动时打预算预估行(推荐) | 显式列 joint 与 baseline 预算 + 总 LM 调用估算 | ✓ |
| 仅文档说明,CLI 静默 | 不打 stdout,docstring 标注 | |
| 加 --dry-budget flag 单独查 | 多一个 flag | |

**User's choice:** stdout 预估行

---

## Output schema & metrics.json 字段

### Q1: joint run 输出目录走哪?

| Option | Description | Selected |
|--------|-------------|----------|
| 同一目录 output/prompts/<ts>/＋mode 字段(推荐) | 共用现有目录,通过 metrics.json mode 分桶 | ✓ |
| 独立目录 output/prompts_joint/ | 完全隔离,dashboard 扫两个 root | |
| 默认同目录 + --output-dir override | 提供 override,默认共用 | |

**User's choice:** 同一目录 + mode 字段

### Q2: metrics.json 上 A/B 双列字段怎么命名?

| Option | Description | Selected |
|--------|-------------|----------|
| joint_score + roundrobin_baseline_score + mode + epsilon_pp(推荐) | 显式双 score + mode 字段 + epsilon 常量落盘 | ✓ |
| baseline_score(现有) + joint_score,roundrobin baseline 隐藏 | 不破坏 baseline_score 含义,但 A/B 关系难提取 | |
| 平铺:joint/roundrobin/baseline_unoptimized + improvement | 三点齐全但 metrics 膨胀 | |

**User's choice:** joint_score + roundrobin_baseline_score + mode + epsilon_pp

### Q3: per-section diff 怎么呈现?

| Option | Description | Selected |
|--------|-------------|----------|
| 现有 diff.txt 不动,_generate_diff 已动态处理 multi-section(推荐) | 零代码改动,joint mode 下 5 section diff 自然拼接 | ✓ |
| 拆 diff_<section_id>.txt 多文件 | 输出与 round-robin 不一致 | |
| diff.txt 不动 + sections.json metadata | 多一个 artifact 留 dashboard 用 | |

**User's choice:** diff.txt 沿用,零改动

### Q4: Phase 16 仪表盘对 prompt run 接入要不要在 Phase 17 预留 schema?

| Option | Description | Selected |
|--------|-------------|----------|
| 仅保证 metrics.json 可被未来 dashboard 扩展读取(推荐) | mode + joint_score + roundrobin_baseline_score 已足够 | ✓ |
| 提前落 per_section growth_pct 数组备未来用 | YAGNI | |
| 本 phase 同时扩 regression_dashboard.py 走 prompt root | scope 拓宽,留给 PMPT-V2 后期 phase | |

**User's choice:** 仅字段命名友好,不接入

---

## Claude's Discretion

- joint mode 下 `PromptModule` 状态机的具体设计(哨兵 / flag / 子类)
- joint mode 下 `forward()` 的具体实现(concat into one Predict / 5 parallel Predicts)
- A/B baseline run 在 `output/prompts/<ts>/` 内的存储位置(共用文件 + 前缀 / `baseline/` 子目录)
- 软门 stdout 警告的精确文案、颜色规则

## Deferred Ideas

- per-section growth_pct / delta_score 数组进 metrics.json(YAGNI)
- dashboard 接入 prompt run(Phase 22+)
- `--joint-iterations N` 单独 flag(YAGNI)
- A/B 硬门 + exit code(holdout 扩到 ≥50 例后再考虑)
- `hybrid` mode(joint warmup → round-robin fine-tune)
- Cross section 联动检查(Phase 18 personality drift detection 方向)
