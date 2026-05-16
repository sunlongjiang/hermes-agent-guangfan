# Phase 19: SessionDB Behavioral Mining for Prompts - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-16
**Phase:** 19-sessiondb-behavioral-mining-for-prompts
**Areas discussed:** Signal Definition, Section Attribution, Sample Schema & expected_behavior, CLI Entry & Wiring

---

## Signal Definition

### Q1: Which mining signals to extract?

| Option | Description | Selected |
|--------|-------------|----------|
| user_correction | 用户对 agent 风格/方法/persona 明确反馈；最高信号强度，复用 Phase 14 D-04 关键词 + LLM 二判 | ✓ |
| section_specific_failure | 每个 section 独立启发式（memory: 'I already told you' / skills: 未调用 / search: 重复问题等） | ✓ |
| oracle_disagreement | 最近一次成功 evolve_prompt_sections 产物作为 oracle，重打分对比 | ✓ |
| persona_drift（进阶） | session 中 agent tone/persona 随轮崩坏；与 Phase 18 DriftDetector 互补但数据层 | ✓ |

**User's choice:** 全部 4 路
**Notes:** 比 Phase 14（3 路）多一路 persona_drift，因为 prompt 侧"错误"更软需要更多信号源覆盖。

### Q2: How to implement persona_drift?

| Option | Description | Selected |
|--------|-------------|----------|
| 复用 DriftDetector | 抽 session 早期 vs 晚期 assistant turn 做 pairwise；不重复造轮子 | ✓ |
| 启发式 + LLM 二判 | 'sorry' 频率、中/英文语言切换、礼仪表达突变 | |
| 同时两路 OR 合并 | 启发式提候选 + DriftDetector 终审 | |

**User's choice:** 复用 DriftDetector
**Notes:** Phase 18 资产直接复用；额外 LLM judge 调用量 +1.5x 可接受。

### Q3: Train duplication multipliers?

| Option | Description | Selected |
|--------|-------------|----------|
| 镜像 Phase 14 | user_correction=3, section_specific_failure=3, oracle_disagreement=2, persona_drift=2 | ✓ |
| 用户信号卷得更高 | user_correction=4, 其他不变 | |
| 平权（3x 全部） | 所有路径同权 | |
| 交给你 | Claude 拍板 | |

**User's choice:** 镜像 Phase 14
**Notes:** 多源命中取 max，与 Phase 14 D-11 一致。

### Q4: Oracle source for oracle_disagreement?

| Option | Description | Selected |
|--------|-------------|----------|
| 最近一次成功产出 | 扫 output/prompts/ 下最近的 evolved_sections.json；--baseline-module flag 覆盖 | ✓ |
| Joint mode 产出优先 | 优先找 joint，退化到 round-robin | |
| 可选不跑 oracle | 默认不启用 oracle 信号，--baseline-module 是启动条件 | |

**User's choice:** 最近一次成功产出
**Notes:** 不区分 mode；缺失任何成功产出时 oracle 信号自动 disabled。

### Q5: user_correction keyword seeds?

| Option | Description | Selected |
|--------|-------------|----------|
| 复用 Phase 14 D-04 + 拓展风格词 | 中英混合 + prompt 专属：'too verbose / 太长了 / be more concise / don't apologize' 等 | ✓ |
| 只用 LLM，不预热关键词 | 成本 4-10x 但避免关键词种子偏见 | |
| 交给你 | 默认走选项 1，planner 在 Plan 拍板列表 | |

**User's choice:** 复用 Phase 14 D-04 定义 + 拓展风格词
**Notes:** 命中后 LLM 二判终审。

---

## Section Attribution

### Q1: How does SessionPromptMiner decide section_id?

| Option | Description | Selected |
|--------|-------------|----------|
| per-section extractor + LLM 二判 | 5 sections × 4 signals = 20 proposer 矩阵；启发式召回，LLM 终审 | ✓ |
| 全局候选 → LLM 全部拍板 | 信号 extractor 不绑 section；LLM 输入 5 section text 完全决定 | |
| 启发式后备 + LLM 主决 | LLM 主路径判断；启发式仅作为预过滤器限制 LLM 调用量 | |

**User's choice:** per-section extractor + LLM 二判
**Notes:** candidate proposer 仅"召回"，section_id 由 LLM 判定；避免硬编码 section→pattern 1:1 绑定。

### Q2: Multi-section attribution?

| Option | Description | Selected |
|--------|-------------|----------|
| 仅一个 section_id | LLM 5 选 1；多源命中拆多条 examples（同 task_hash + 不同 section_id） | ✓ |
| section_ids: list[str] | 改 schema 为 multi-section；破坏 PromptDatasetBuilder/PromptModule 链 | |
| PLATFORM_HINTS 下钻到 platform key | section_id 仍 string + 额外 platform_key 字段 | |

**User's choice:** 仅一个 section_id
**Notes:** 保持 schema 简洁；多 section 命中拆分为多条 examples。

### Q3: PLATFORM_HINTS granularity?

| Option | Description | Selected |
|--------|-------------|----------|
| section_id = 'platform_hints.<key>' | 与 Phase 7 抽取一致（9 个 sub-section） | ✓ |
| 'platform_hints' 不下钻 | 单一 section 参数，低设计负荷但丢粒度 | |
| 跳过 PLATFORM_HINTS | 本 phase 不挖 platform 信号 | |

**User's choice:** section_id = 'platform_hints.<key>'
**Notes:** LLM judge prompt 需识别平台 token 并输出对应 key。

### Q4: Section_id surface drift handling?

| Option | Description | Selected |
|--------|-------------|----------|
| 整例丢弃 + metrics.json | Phase 14 D-17 同策略；dropped_count + surface_drift_sections 入 metrics | ✓ |
| alias 表 + fuzzy match | 维护 `{'old_name': 'new_name'}` alias；误匹配风险 | |
| Phase 19 不考虑（hard fail） | section drift → CLI exit 1 | |

**User's choice:** 整例丢弃 + metrics.json
**Notes:** 与 Phase 14 D-17 完全对称。

---

## Sample Schema & expected_behavior

### Q1: New fields for session-origin examples?

| Option | Description | Selected |
|--------|-------------|----------|
| mining_signals + source='session' | 加 `mining_signals: list[str]` 字段（默认 []）+ source 枚举扩展 | ✓ |
| + session_path + turn_idx | 额外加完整溯源；PII 风险（session 路径含用户名） | |
| + platform_key + verdict_rationale | 加更多结构化字段；schema 变动最多 | |

**User's choice:** mining_signals + source='session'
**Notes:** from_dict 已过滤 unknown keys，向后兼容历史 Phase 9 数据集。

### Q2: How to generate expected_behavior?

| Option | Description | Selected |
|--------|-------------|----------|
| LLM judge 一起输出 | ConfirmBehavioralExample Signature 一次输出 verdict + section_id + expected_behavior + difficulty + rationale | ✓ |
| Verbatim correction 文本 | 用 user 修正原文作为 expected_behavior；rarely 是合格 rubric 格式 | |
| 两阶段 | Stage 1: verdict+section_id；Stage 2: expected_behavior（仅 confirm 时） | |

**User's choice:** LLM judge 一起输出
**Notes:** 最经济（1 次 LLM 调用完成三件事）。

### Q3: How to assign difficulty?

| Option | Description | Selected |
|--------|-------------|----------|
| LLM judge 同时输出 | difficulty 字段与 verdict/section_id/expected_behavior 共享一次 LLM call | ✓ |
| 默认 'hard' | session-mined 例都是 synthetic 漏挨的场景；简单偷懒但高偏见 | |
| 启发式赋值 | 1 信号=medium, 2+ 信号=hard, oracle_only=easy | |

**User's choice:** LLM judge 同时输出
**Notes:** Signature OutputField 显式约束为 easy/medium/hard 字面值。

### Q4: Duplication mechanics?

| Option | Description | Selected |
|--------|-------------|----------|
| 镜像 Phase 14 D-13 | hash mod 100 拆分（70/15/15）后仅 train 复制；val/holdout 保 1 份；多信号取 max | ✓ |
| 复制 train + per-section quota cap | 额外为每 section 设 upper cap（默认 30） | |
| 不复制，仅联合去重 | session 例子作为额外样本源 union 进 PromptDatasetBuilder 产出集 | |

**User's choice:** 镜像 Phase 14 D-13
**Notes:** Phase 14 D-14 近邻 hash 去重 + session 优先策略同样适用。

---

## CLI Entry & Wiring

### Q1: Mining CLI naming & structure?

| Option | Description | Selected |
|--------|-------------|----------|
| mine_prompt_sessions.py（高对称） | 高对称 mine_tool_sessions.py 13 个 flag；datasets/prompts/sessions/<ts>/ | ✓ |
| mine_prompt_behaviors.py + 变量重命名 | 名称更精确但与 Phase 14 命名不对称 | |
| evolve_prompt_sessions.py 子命令 | 不动独立 CLI，作为 evolve_prompt_sections 的 mine 子命令 | |

**User's choice:** mine_prompt_sessions.py
**Notes:** evolution/prompts/mine_prompt_sessions.py；CLI flag 集复用 mine_tool_sessions.py + 加 --drift-thresholds-path（D-04 persona_drift 复用 Phase 18 thresholds）。

### Q2: --session-source default behavior and multi-section wiring?

| Option | Description | Selected |
|--------|-------------|----------|
| Union + 两模式均消费 | Phase 14 D-09 同策略；joint 与 round-robin 都自动 union session-source | ✓ |
| Union，仅 joint mode 启用 | 仅 joint mode 走 session union；round-robin 保留现有行为 | |
| Per-section --session-source | 每个 section 独立 flag；过度粒度 | |

**User's choice:** Union + 两模式均消费
**Notes:** session 3 splits 与 PromptDatasetBuilder 合成 splits 对应 union，hash 去重 session 优先。

### Q3: Phase 18 build_drift_calibration.py also add --session-source?

| Option | Description | Selected |
|--------|-------------|----------|
| 不加 | session-mined 例是 section 行为场景；与 calibration 的 label 原始 vs 漂移 pair 语义不同；强插扰乱 F1 derive | ✓ |
| 加，session 例作为 'no-drift' 变体参与 calibration | 增加多样性但混淆 ground-truth label | |
| 加，但只为 build_drift_calibration --augment-from-session | 独立 opt-in flag，默认不启用 | |

**User's choice:** 不加
**Notes:** 如果未来需要 session-grounded calibration，独立 phase 推进。

### Q4: Output directory & metrics.json field naming?

| Option | Description | Selected |
|--------|-------------|----------|
| datasets/prompts/sessions/<ts>/（高对称） | 镜像 Phase 14；datasets/**/*.jsonl 默认 .gitignore 不 track | ✓ |
| output/prompts/sessions/<ts>/ | 与 Phase 17/18 output/ 同根；表示 run-time artifact | |
| datasets/prompts/sessions/ + tracked-in-git 与 ignored 双表现 | 同选项 1，session-mined dataset 不 track；calibration 是例外 | |

**User's choice:** datasets/prompts/sessions/<ts>/（高对称）
**Notes:** 与 Phase 14 datasets/tools/sessions/<ts>/ 完全对称。

---

## Claude's Discretion

- ConfirmBehavioralExample Signature 字段名、system prompt 文本、JSON 输出 schema
- 4 路 per-section heuristic candidate proposer 关键词列表与正则（specifics 给起点，planner 在 PLAN 中固化）
- mine_prompt_sessions Rich 表展示细节（字段顺序、颜色、warning 阈值）
- session JSON 旧版结构容错策略
- judge LLM batching/concurrency 上限（默认串行）
- normalized task hash 的 collapse_whitespace 实现
- surface_drift_dropped 报告截断长度
- 多源命中加权 max 时的 tie-break 策略
- DriftDetector 在 persona_drift extractor 中调用参数（早/晚期 turn 窗口、min_turns 门槛）
- --session-source 加载时 synthetic vs session 训练集 hash collision 报告格式

## Deferred Ideas

- session-only holdout 子集 + session_holdout_score 指标
- behavioral_weight: float 字段 + metric 乘权
- 多 section 同时归因 schema（section_ids: list[str]）
- session-grounded calibration set 增强 Phase 18 DriftDetector
- Per-section quota cap 防止过采样
- --session-mode replace|holdout 三档位 flag
- Phase 16 dashboard 加 prompt session-source 维度
- NER (Layer 2 PII) 隐私护栏
- LLM 数据集审计（Layer 4）
- Two-stage LLM call（verdict + section_id 分开，expected_behavior 单独）
- persona_drift extractor 用 3-run averaging
- mine_prompt_sessions 增量挖矿模式
