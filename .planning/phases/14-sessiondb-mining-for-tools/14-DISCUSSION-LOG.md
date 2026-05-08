# Phase 14: SessionDB Mining for Tools - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-08
**Phase:** 14-sessiondb-mining-for-tools
**Areas discussed:** 误选信号定义, 架构与 CLI, 加权机制实现, 隐私护栏与表面漂移

---

## 误选信号定义

### Q1: 选哪些信号源作为 misselection 标签？

| Option | Description | Selected |
|--------|-------------|----------|
| 只用 B (报错重试) | 机械可提取硬信号；50-150 例；不需要 LLM | |
| B + C (硬信号 + oracle 分歧) | 加 ToolModule 重打分 + LLM 二判 | |
| **B + A + C (三路叠加)** | 加用户纠正信号；ToolSelectionExample 加 misselection_signal 字段 | ✓ |
| A+B+C+D 全选 | 还加多工具串联失败启发式 | |

**User's choice:** B + A + C 三路叠加
**Notes:** 不要 D（多工具串联失败）—— 噪声大。三路 union 时同 example 信号合并。

### Q2: 三路信号怎么记录到 ToolSelectionExample 上？

| Option | Description | Selected |
|--------|-------------|----------|
| **添加 misselection_signals: list[str] 字段** | 取值 {error_retry, user_correction, oracle_disagreement}；多路 union | ✓ |
| 复用 source 字段 | session:error_retry / session:user_correction / session:oracle 三选一；多路命中按优先级取 | |
| 三路各出一例 | 同 task 重复出 3 例；schema 不动；可能造成 train/holdout 泄漏 | |

**User's choice:** 添加信号字段
**Notes:** 字段值集合明确，多源 union 不重复产例。

### Q3: 对三路信号、correct_tool 如何产出？

| Option | Description | Selected |
|--------|-------------|----------|
| 启发式推导 + LLM 二判 | B 用 exit_code、A 用关键词、C 用 ToolModule 预测 + LLM 终审 | |
| B 成功代理为唯一 ground truth | A 和 C 候选丢人工 review 队列 | |
| **全部 LLM judge 决定** | 不依赖 exit_code/启发式；三路都送 GPT-4.1 judge | ✓ |

**User's choice:** 全部 LLM judge 决定
**Notes:** 由 judge 终审 correct_tool；session 中原选错的工具自动入 confuser_tools。

---

## 架构与 CLI

### Q4: Session 挖矿逻辑该怎么组织？

| Option | Description | Selected |
|--------|-------------|----------|
| **新独立 miner 模块 + 新 CLI + flag** | session_miner.py + mine_tool_sessions.py 新 CLI + evolve_* CLI 加 --session-source | ✓ |
| 扩展 ToolDatasetBuilder | 单 builder 内部完成 session 挖矿；evolve_* 加 --include-sessions flag | |
| 仅交付挖矿，不介入训练 CLI | Phase 14 范围最紧；用户手工合并 | |

**User's choice:** 新独立 miner 模块 + 新 CLI + flag
**Notes:** 三件套独立产物，便于 Phase 19 复用框架。

### Q5: evolve_* CLI 传入 --session-source 后的语义？

| Option | Description | Selected |
|--------|-------------|----------|
| session-only 互斥 | 给 --session-source 则只用 session JSONL；不给则走合成 | |
| **默认 union 混合** | 给则 session+合成混合；session 例子按信号源加权复制 | ✓ |
| 三档位 flag (merge/replace/holdout) | 灵活但权限面变广 | |

**User's choice:** 默认 union 混合
**Notes:** Phase 14 集成 ToolDatasetBuilder「作为额外数据源」原话被完整覆盖。

---

## 加权机制实现

### Q6: 「misselection 加权」如何落到训练集上？

| Option | Description | Selected |
|--------|-------------|----------|
| **例子复制 (默认 3x/3x/2x)** | error_retry=3x、user_correction=3x、oracle_disagreement=2x；schema/metric 不动；CLI 加 --misselection-multiplier | ✓ |
| 加 weight 字段 + metric 乘权 | ToolSelectionExample 加 weight；tool_selection_metric 和 joint metric 都改 | |
| 仅依靠 difficulty + confuser_tools | 不做主动加权；依赖 hard 例子稀缺自然加权 | |

**User's choice:** 例子复制 (默认 3x/3x/2x)
**Notes:** 多源命中取 max（不累乘）；schema 简单。

### Q7: session examples 怎么拆分 + 复制范围？

| Option | Description | Selected |
|--------|-------------|----------|
| **task hash 去重 + 复制仅限 train** | 70/15/15 拆；同 hash 仅在一个切分；复制只在 train 内 | ✓ |
| session 全进 train，val/holdout 依旧 | 低泄漏但失去 session 真实分布的评估能力 | |
| 抽 10% 为 session-only holdout | metrics 拆记录 hybrid_holdout_score 和 session_holdout_score | |

**User's choice:** task hash 去重 + 复制仅限 train
**Notes:** hash 模 100 划桶（< 70 train, < 85 val, else holdout），可重现且无泄漏。

---

## 隐私护栏与表面漂移

### Q8: expand-secret-patterns 在 Phase 14 里谁复责、做多深？

| Option | Description | Selected |
|--------|-------------|----------|
| **L1 + L3 (正则+熵+consent)** | JWT/AWS 正则 + Shannon 熵阈值 + --i-have-consent flag；不引 NER | ✓ |
| L1 + L3 + L4 (加 LLM 数据集审计) | 多一道 LLM 整体审计；成本小、防御层完整 | |
| 仅最小改动 (JWT + consent) | 接受 Phase 14 blocker 最小解除；后续独立 hygiene phase | |

**User's choice:** L1 + L3
**Notes:** Layer 2 (NER) / Layer 4 (LLM 审计) 延后；Layer 1 包括 JWT 正则 + AWS 正则 + Shannon 熵 >4.0 over 24+ char tokens。

### Q9: 源 session 引用了现不存在的工具名怎么处理？

| Option | Description | Selected |
|--------|-------------|----------|
| **不匹配则丢弃 + 送报告** | 整例 skip；CLI 末尾打印 dropped_count + dropped_tool_distribution；metrics.json 写 surface_drift_dropped | ✓ |
| alias 表 + 丢弃 fallback | 维护 evolution/tools/tool_aliases.yaml；引入手动维护负担 | |
| 保留 + 打漂移标 | session 保留并标 surface_drift: bool；fitness metric 可选跳过 | |

**User's choice:** 不匹配则丢弃 + 送报告
**Notes:** 不维护 alias 表；保 phase 范围紧。

### Q10: 剩下 2 个 pending todos 怎么处理？

| Option | Description | Selected |
|--------|-------------|----------|
| **最小折入方案** | jsonl-skip-bad-lines 仅折 session_miner JSONL 读写 + --session-source 加载路径；EvalDataset/GoldenDatasetLoader 不动；enforce-readonly review 不折 | ✓ |
| jsonl 全范围折入 | EvalDataset.load 和 GoldenDatasetLoader.load 都加 skip 逻辑 + 警告 | |
| 不折入其他两个 | jsonl-skip-bad-lines 留给 v2-STAB-01；enforce-readonly 留给 Phase 22 | |

**User's choice:** 最小折入方案
**Notes:** enforce-readonly-hermes-agent 不折——Phase 14 完全只读，无 write_back 路径。

---

## Claude's Discretion

- ConfirmMisselection Signature 字段名 / system prompt 文本 / judge 输出 JSON schema
- _extract_user_correction 关键词种子的具体词条 + LLM 二判 prompt
- mine_tool_sessions Rich 表展示细节（字段顺序、颜色、warning 阈值）
- session JSON 解析时遇到结构不规则消息（旧版本 hermes 格式）的容错
- judge LLM 调用的 batching/concurrency 上限
- normalized task hash 的具体 collapse_whitespace 实现
- surface_drift_dropped 报告的截断长度
- 多源命中加权 max 时的 tie-break 策略

## Deferred Ideas

- Phase 19 SessionDB Behavioral Mining for Prompts — 三路信号模板可参考但不强制抽 base class
- Phase 16 Per-Tool Regression Dashboard — session 加权后工具不均衡需要专门可视化
- Phase 15 Think-Augmented Tool Selection — session 中 assistant pre-tool_call reasoning text 留 Phase 15
- Layer 2 NER（spacy/Presidio 可选依赖）— v2-STAB 或独立 hygiene phase
- Layer 4 LLM 数据集审计步骤 — 本 phase 仅落 L1+L3
- --session-mode replace|holdout — 三档位 flag 行为；本 phase 仅做 union
- misselection_weight: float 字段 + metric 乘权 — 比复制更精细，效果不佳再演进
- 多工具串联失败 (D 信号) — 启发式噪声大，召回不够再考虑
- session-only holdout 子集 + session_holdout_score — 留 Phase 19+ 重审
- enforce-readonly-hermes-agent (reviewed not folded) — Phase 22 持续进化循环或独立 hygiene
