# Phase 18: Personality Drift Detection - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-15
**Phase:** 18-personality-drift-detection
**Areas discussed:** 门禁机制 (gate), 阈值校准 (calibration), 评分稳健度 (3-run averaging), 报告输出 (drift report)

---

## 已由 Phase 17 + research 锁定(未重新讨论)

下列决策在 discuss 启动前已由 ROADMAP + REQUIREMENTS + `.planning/research/PITFALLS.md` §Pitfall 6 锁定,本次 discussion 不重复:

- Detection 方式:LLM-as-judge,pairwise(`DriftDetector(original, evolved) -> per-dim scores`),仿 `PromptRoleChecker` 接口
- Dimensions:tone / formality / vocabulary / persona 四维向量(per PITFALL #6 prevention #4)
- 没有 `--no-drift-check` bypass flag(per PITFALL #6 prevention)
- 集成位置:`evolution/prompts/prompt_constraints.py` 同模式(由 planner 决定新文件 vs 扩展);在 `evolve_prompt_sections.py` step 8b 之后、step 9 (holdout) 之前
- Reference baseline:对比 evolved vs original (untouched hermes-agent 段落)

---

## 1. 门禁机制 (Gate type)

| Option | Description | Selected |
|--------|-------------|----------|
| 阶梯门 (1 dim 警告 / 2+ dim reject) | research 推荐的混合门;1 dim 超 = stdout 警告 + 仍 deploy;2+ dim 超 = constraint FAILED 不 deploy。与 Phase 17 A/B 软门语义互补,与 ROADMAP success criteria 2 "reject… exceeding threshold" 对齐(2+ dim 是 operational 的 "exceeding") | ✓ |
| 全硬门 (任 1 dim 超即 reject) | 顺应 v1 PromptRoleChecker all-or-nothing 风格,最简;风险:research 警告未校准前会误杀 30%+ 候选 → 优化停滞 | |
| 全软门 (只警告 + 落盘,不 reject) | 与 Phase 17 A/B 软门一致;风险:ROADMAP success criteria 2 明说 "Constraint gate rejects" 不满足,verify-phase 难通过 | |
| 阶梯门 + per-section dim 个数可调 | 默认 1/2,但 DEFAULT_AGENT_IDENTITY 可配为 "任 1 超即 reject";YAGNI 风险 | |

**User's choice:** 阶梯门 (1 dim 警告 / 2+ dim reject)
**Notes:** 与 Phase 17 D-AB-02 软门语义对齐;ROADMAP success criteria 2 "reject… exceeding threshold" 在 operational 层面解读为 2+ dim 超才算真正的 exceeding。

---

## 2. 阈值校准 (Calibration set)

| Option | Description | Selected |
|--------|-------------|----------|
| Synthetic LLM 生成 (复用 PromptDatasetBuilder 模式) | 新增 `drift_calibration.py:DriftCalibrationBuilder` + DSPy Signature,生成 15 真漂移 + 15 无漂移 = 30 对。成本低、可复现。风险:同源偏误,需人工 spot-check 缓解 | ✓ |
| 手写 (用户提供 30 例 YAML) | 质量最高、可复现;~2-3 小时人工输入成本 | |
| Hybrid:LLM 生成 + 人工 review | 全面但多一道工序 | |
| 本期不做 calibration,先用保守阈值占位 (0.6/dim) | 跳过 calibration 直接写死阈值;风险:research 把 calibration 列为 Task 1,跳过会踩坑 | |

**User's choice:** Synthetic LLM 生成(复用 PromptDatasetBuilder 模式)
**Notes:** 同源偏误风险在 CONTEXT.md `code_context > Risk Anchors` 已显式标注 — planner 在 PLAN.md 必须明确人工 spot-check 步骤(抽 10 例由用户 review,不通过则重生成)。Calibration set 落盘到 `datasets/prompts/drift_calibration.jsonl` 并 git 跟踪(`.gitignore` 加 exception 行)。

---

## 3. 评分稳健度 (3-run averaging)

| Option | Description | Selected |
|--------|-------------|----------|
| 只在 final constraint gate 3-run | GEPA 内循环 / A/B baseline 不触发 DriftDetector;只在 step 8c gate 跑 3 次 × 5 段 × 4 维 = 60 次/run。成本可控 ($0.5-2 额外) | ✓ |
| 只 1-run,接受噪声 | 最便宜;研究警告 ±0.15 噪声 → F1 会差 | |
| 所有调用 3-run 完整平均 | 最稳健;若 GEPA 内循环触发 drift judge 会 ×3 爆炸($30-100/run) — 现设计中 DriftDetector 只在 gate 一次,本质等价于选项 1 | |
| Calibration 期 3-run / 生产期 1-run | 阈值严锁但运行期有 ±0.15 噪声;门会不稳 | |

**User's choice:** 只在 final constraint gate 3-run
**Notes:** 决策规则 `mean - 1·stdev > threshold[dim]`(保守、偏 false negative);joint mode 5 段 × 4 维 × 3 次 = 60 次/run 在可控范围;round-robin 单段优化也走完整 4 维 3-run。

---

## 4. 报告输出 (Drift report)

| Option | Description | Selected |
|--------|-------------|----------|
| Rich table + metrics.json `drift_per_dim` + drift_report.txt | (a) stdout Rich 表格 (b) metrics.json 新增结构化字段 (c) 单独 drift_report.txt 人类可读。Phase 17 metrics.json schema 全保留。最完整 | ✓ |
| 仅 metrics.json + Rich 表格,不写独立文件 | metrics.json 体积变胖;少一个文件资产 | |
| 仅 stdout + metrics.json 布尔字段 | 最简化;丢失 dim-级分数,未来 dashboard 难重现 | |
| Rich + metrics.json + drift_report.json (结构化) | 结构化便于机器消费;暂时不需要 — txt 已足够 review | |

**User's choice:** Rich table + metrics.json `drift_per_dim` + drift_report.txt
**Notes:** metrics.json 新增字段全部以 `drift_*` 前缀,不冲突 Phase 17 字段(`mode`、`joint_score`、`roundrobin_baseline_score`、`epsilon_pp`、`joint_vs_roundrobin_delta_pp`)。drift_report.txt 在成功 / FAILED 两条路径都写盘,便于事后排查。

---

## Claude's Discretion (用户未拍板,留给 planner / researcher 决策)

- DriftDetector 类放在 `evolution/prompts/drift_detector.py` 还是扩展 `prompt_constraints.py` — planner 决,约束是必须沿用 `check_all` 接口
- `DriftCalibrationBuilder` 的 CLI 入口形式(独立 `python -m evolution.prompts.build_drift_calibration` vs 作为 `evolve_prompt_sections.py --build-calibration` 子模式)
- 30 例 calibration set 的 LLM 生成 prompt 具体措辞(planner 写 DSPy Signature 时撰写)
- F1 derivation 算法实现(暴力扫描 [0.1, 0.9] step 0.05 vs sklearn `precision_recall_curve`)
- DriftDetector 在 evolve_prompt_sections.py 的精确插入位置 / 与 role check 的代码组织
- 软警告 / 硬 reject 的 Rich 颜色微调与 emoji 使用
- `dspy.OutputField(type=float)` 在当前 DSPy 3.x 版本是否可用 — researcher 验证后回写 PLAN

## Deferred Ideas(本期不做,见 CONTEXT.md `<deferred>`)

- Embedding-based 相似度作为额外信号
- per-section 阈值 / 阶梯定制
- 运行期阈值在线调节 / online learning
- DriftDetector 接入 GEPA 优化内循环作为 secondary fitness signal(Goodhart 风险)
- 在 A/B baseline run 上跑 drift 检查
- drift_report.json(结构化镜像)
- Quarterly 自动重新 calibration 调度

## Reviewed Todos (not folded)

cross_reference_todos 找到 6 个 score ≥ 0.2 的 todo,均未折叠:
- `2026-05-07-enforce-readonly-hermes-agent.md` (score 0.4) — 本期不写回 hermes-agent
- `2026-05-07-harden-llm-output-parsing.md` (score 0.4) — 已作为 Risk Anchor 在 CONTEXT.md code_context 中标注,不进主线 scope
- `2026-05-07-add-lockfile-dspy-pin.md` (score 0.2)
- `2026-05-07-expand-secret-patterns.md` (score 0.2)
