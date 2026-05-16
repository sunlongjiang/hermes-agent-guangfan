# Phase 19: SessionDB Behavioral Mining for Prompts - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning

<domain>
## Phase Boundary

从 hermes-agent 真实会话转录（`~/.hermes/sessions/*.json`，45 份样本）中**自动挖矿** prompt section 行为信号 → 生成 `PromptBehavioralExample[]` 增强 PromptDatasetBuilder 合成数据集。覆盖 PMPT-V2-04，是 Phase 14 SessionDB Mining for Tools 的 prompt 侧镜像。

落地三件事：
1. SessionPromptMiner 四路信号（user_correction / section_specific_failure / oracle_disagreement / persona_drift）→ LLM judge → PromptBehavioralExample[]
2. 新 CLI `mine_prompt_sessions.py` 一次离线挖矿，输出 JSONL
3. evolve_prompt_sections 加 `--session-source` flag union 合成数据集；session 例子按信号源加权复制（仅复制到 train 切分）

**Phase 19 仅产出 + 注入行为评估数据**，不引入新 metric/optimizer，不触及 hermes-agent 写回路径。Phase 18 DriftDetector / DriftCalibrationBuilder 不在本 phase scope（除了在 persona_drift 信号路径中作为只读 judge 复用），漂移检测是独立约束层。

不引入新依赖，复用 DSPy/Click/Rich 栈。

</domain>

<decisions>
## Implementation Decisions

### D1 挖矿信号定义

- **D-01:** 四路信号叠加：**user_correction + section_specific_failure + oracle_disagreement + persona_drift**。四路均产出 candidate（task_description, available_sections_context, originally_observed_behavior, downstream_context）送 LLM judge；judge 决定最终 verdict + section_id + expected_behavior + difficulty + rationale；session 中触发 misbehavior 的 section_id 进入 example。**比 Phase 14（3 路）多一路 persona_drift**，因为 prompt 侧"错误"更软，需要更多信号源覆盖。
- **D-02:** PromptBehavioralExample 新增字段 `mining_signals: list[str]`，取值集合 `{"user_correction", "section_specific_failure", "oracle_disagreement", "persona_drift"}`。同一 (normalized task hash, section_id) 被多路命中时 union 信号集合，不去重多产 example。新字段默认 `field(default_factory=list)`，向后兼容历史 Phase 9 数据集（旧例 signals=[]）；`from_dict` 已过滤 unknown keys (prompt_dataset.py:66) 故无需额外迁移。`source` 字段枚举值扩展允许 `"session"`（追加 synthetic/golden 之后）。
- **D-03:** **所有** verdict + section_id + expected_behavior + difficulty 由 LLM judge 一次性输出。`ConfirmBehavioralExample` Signature 与 Phase 14 `ConfirmMisselection` 风格一致；输入：(task_description, candidate_signal_source, originally_observed_behavior, all_5_section_texts, downstream_context)；输出：(verdict ∈ {confirm_example, false_positive}, section_id ∈ {5选1 + platform_hints.<key>}, expected_behavior: str, difficulty ∈ {easy,medium,hard}, rationale: str)。单 LLM call 完成三件事（verdict + section_id + expected_behavior + difficulty）以控成本。
- **D-04:** 四路信号的 candidate 抽取规则：
  - **user_correction:** 任意 user turn 紧随 assistant turn 后发出 correction-like 消息；判定借助关键词列表 + LLM 二判（关键词列表预热召回，LLM 终审）。关键词种子见 specifics（中英混合 + prompt 专属风格词）。
  - **section_specific_failure:** 每个 section 独立启发式 extractor（per-section pattern proposers）：
    - `memory_guidance`: user 表达 "I already told you / 你忘了 / repeat question" 类语句
    - `skills_guidance`: user 提到 "use /<skill>" / "should use <skill>" 而 assistant 未调用；或 assistant 调用 skill 后 user 否认相关性
    - `session_search_guidance`: user 重复问相同问题，agent 未触发 session 搜索
    - `default_agent_identity`: user 反馈 "too formal / too verbose / be more concise / don't apologize"
    - `platform_hints.<key>`: 平台 token（'on macOS / Linux 下 / Windows 则'）后 user 提示错误
  - **oracle_disagreement:** 用最近一次成功 evolve_prompt_sections 产出的 PromptModule（扫 `output/prompts/<ts>/evolved_sections.json`，不区分 joint/round-robin mode）在 (user_message, original_5_sections) 上重打分；LLM 对比 oracle 预测 vs session 实际 assistant 行为，差异显著标为 candidate（非严格相等，因为 prompt 输出是 free-text）。`--baseline-module <output-dir>` flag 可手动覆盖，缺省时自动扫最近产出；缺失任何成功产出时 oracle 信号自动 disabled（warn + 继续其他三路）。
  - **persona_drift:** 复用 Phase 18 `DriftDetector` (drift_detector.py)，对同一会话早期（前 1/3 assistant turns）vs 晚期（后 1/3 assistant turns）pairwise 调用；若 persona_score / tone_score 高于 thresholds.json 则会话进入 candidate 池。**复用 Phase 18 资产，不重造轮子**；额外 LLM judge 调用量增加约 1.5x。
- **D-05:** Judge 输出 `verdict=false_positive` 的 candidate 不丢弃——写入 mining 报告 metrics.json 字段 `judge_false_positives_by_signal: dict[str, int]`，便于审计 LLM judge 噪声（Phase 14 D-05 对称）。

### D2 Section 归因拓扑

- **D-06:** SessionPromptMiner 内部为 4 路 signal 各起一个 per-section 启发式 candidate proposer（共 5 sections × 4 signals = 20 proposer 矩阵）。所有 proposer 命中的 candidate 一律送 LLM judge 终审 section_id 与 verdict。**candidate proposer 仅负责"召回"，section_id 由 LLM 判定**。这避免硬编码 section→pattern 的 1:1 绑定，但比"全靠 LLM 全局判"经济。
- **D-07:** 一个 candidate 仅产出**一个 section_id**（LLM judge 输出 section_id ∈ {default_agent_identity, memory_guidance, session_search_guidance, skills_guidance, platform_hints.<9 keys>}，单选）。如果一个 candidate 在多个 section proposer 中命中，拆成多条 examples（相同 task_hash + 不同 section_id）。schema 保持 `section_id: str` 不变（PromptBehavioralExample / PromptDatasetBuilder / PromptModule 全链路无 schema 改动）。
- **D-08:** PLATFORM_HINTS section_id 形如 `platform_hints.<key>`（key ∈ {macos, linux, windows, ...}），与 Phase 7 抽取一致（Phase 7 把 PLATFORM_HINTS dict 按 key 展开为 9 个独立 section）。LLM judge prompt 中必须包含 "if the misbehavior is platform-specific, output section_id as 'platform_hints.<platform_token>'" 指引；platform_token 从 candidate 上下文中提取。
- **D-09:** Section_id surface drift：session 推出的 section_id 不在当前 hermes-agent `extract_prompt_sections()` 产出里时**整例丢弃**（与 Phase 14 D-17 同策略）。`metrics.json` 写入 `surface_drift_dropped: int` + `surface_drift_sections: list[str]`；CLI 末尾打印 `dropped_count` + `dropped_section_distribution: dict[str, int]`。**不**维护 alias 表、**不**保留漂移例做 audit。

### D3 样本 schema 与生成路径

- **D-10:** PromptBehavioralExample 字段：`section_id` (str) + `user_message` (str) + `expected_behavior` (str) + `difficulty` (str, easy/medium/hard) + `source` (str, 扩展枚举 synthetic/golden/session) + `mining_signals: list[str]` (新增, 默认 `[]`)。**不**额外加 session_path / turn_idx / verdict_rationale 字段（PII 风险 + schema 简洁性）。
- **D-11:** **expected_behavior 由 LLM judge ConfirmBehavioralExample Signature 一并输出**（从 user correction 文本 + downstream context 提炼成可评测的 rubric）。**不**用 verbatim correction 作为 expected_behavior（rarely 是合格 rubric 格式，例如 "no don't apologize" 不可评估）。**不**采用两阶段 LLM call（成本翻倍且 confirm vs synthesize 解耦没必要）。
- **D-12:** difficulty 由 LLM judge 同时输出（与 verdict/section_id/expected_behavior 共享一次 LLM call），符合 Phase 9 PromptDatasetBuilder 已有的 difficulty 赋值惯例。Signature 的 difficulty OutputField 显式约束为 `easy|medium|hard` 字面值。
- **D-13:** **样本复制策略**——不改 metric、不改 PromptBehavioralExample 之外的 schema。SessionPromptMiner 在 dataset 输出阶段按 `mining_signals` 决定复制次数（mirror Phase 14 D-11）：
  - `user_correction`：3x
  - `section_specific_failure`：3x
  - `oracle_disagreement`：2x
  - `persona_drift`：2x
  - 多源命中取 max（不累乘）
  - 复制**仅在 train 切分**发生；val/holdout 保留 1 份
- **D-14:** mine_prompt_sessions CLI flag `--behavioral-multiplier "user_correction=3,section_specific_failure=3,oracle_disagreement=2,persona_drift=2"`（key=value 格式覆盖默认，Phase 14 D-12 对称；naming 用 `--behavioral-multiplier` 而非 `--misselection-multiplier` 以贴合 prompt 域语义）。
- **D-15:** 数据集拆分：**按规范化 task hash 去重**——hash = `sha256(strip + lower + collapse_whitespace(user_message))[:16]`。同 hash 仅出现在一个切分，由 hash 模 100 划入 train(<70) / val(<85) / holdout(else)，保证可重现且无切分泄漏。复制发生在去重落桶**之后**，仅 train 切分内复制。session-only holdout 子集**不**抽取（与 Phase 14 D-13 同理由——holdout 来源单一保证可比对）。
- **D-16:** evolve_prompt_sections.py 在 union 合成 + session 数据集时，先各自 hash 去重，再两路 union；同 hash 例子 session 优先（mining_signals 字段保留）。最终 train/val/holdout 跨数据源 hash 去重。Phase 14 D-14 对称。

### D4 CLI 入口与注入路径

- **D-17:** **新建** CLI 入口 `evolution/prompts/mine_prompt_sessions.py`（Click + Rich），高度对称 `mine_tool_sessions.py`（13 个 flag）。复用 Phase 5/10 既有 flags：`--hermes-repo` / `--model` / `--api-base` / `--dry-run`。新增 flags：
  - `--sessions-dir <path>` 默认 `~/.hermes/sessions`
  - `--output <dir>` 默认 `datasets/prompts/sessions/<YYYYMMDD_HHMMSS>/`
  - `--limit <int>` 0=全部
  - `--i-have-consent` **必填** boolean flag（缺则 abort，Phase 14 D-16 同策略）
  - `--signals` 逗号分隔子集 `user_correction,section_specific_failure,oracle_disagreement,persona_drift`，默认全部
  - `--baseline-module <output-dir>` 指向已有 evolve_prompt_sections 产物用作 oracle（oracle_disagreement 信号），缺省自动扫最近产出；扫不到则该信号 disabled
  - `--judge-model` 默认 `openai/gpt-4.1`，可覆盖
  - `--behavioral-multiplier "<key=value,...>"` 覆盖 D-13 默认 multipliers
  - `--drift-thresholds-path <path>` 默认 `datasets/prompts/drift_thresholds.json`（Phase 18 D-BYPASS-02 对称），供 persona_drift 信号读取 thresholds
- **D-18:** **新建** `evolution/prompts/session_prompt_miner.py`，提供 `SessionPromptMiner` 类。结构对齐 `SessionToolMiner`：构造接 `EvolutionConfig`，方法 `mine(sessions_dir: Path, current_sections: list[PromptSection]) -> list[PromptBehavioralExample]`。四路 signal extractor 为内部私有方法（`_extract_user_correction`, `_extract_section_specific_failure`, `_extract_oracle_disagreement`, `_extract_persona_drift`）。LLM judge 用内部 inner Signature 类（`ConfirmBehavioralExample`），与 `ConfirmMisselection`/`PromptRoleChecker`/`DriftDetector` 风格一致。persona_drift extractor 通过 `from evolution.prompts.drift_detector import DriftDetector` 复用 Phase 18 资产。
- **D-19:** **不**扩展 `HermesSessionImporter`（同 Phase 14 D-10 理由）。session_prompt_miner 直接读 session JSON。
- **D-20:** 输出目录结构（与 Phase 14 高对称）：
  ```
  datasets/prompts/sessions/<YYYYMMDD_HHMMSS>/
  ├── train.jsonl / val.jsonl / holdout.jsonl  # 70/15/15 拆分（D-15）
  ├── metrics.json                              # 信号统计、judge 调用数、surface drift、persona_drift 通过率
  └── miner_log.jsonl                           # 每条 candidate→verdict 的审计行
  ```
  CLI 末尾 Rich table 总结：原始 candidate / judge 通过 / 各 signal 命中数 / dropped surface drift / final example 数。`datasets/**/*.jsonl` 默认在 `.gitignore` 不 track；calibration set 是例外（Phase 18 D-CAL-02），session-mined dataset **不** track（与 Phase 14 同行为）。
- **D-21:** evolve_prompt_sections.py 新增 flag：`--session-source <path>`。指向 `datasets/prompts/sessions/<timestamp>/` 目录。**默认行为：union**——session-source 三个 split 与 PromptDatasetBuilder 合成数据集对应 split union 合并，去重见 D-16。不传时一切走原行为，不触发挖矿。**Joint mode（Phase 17）与 round-robin mode 都自动消费 session-source**，无需额外 flag。
- **D-22:** **不**为 Phase 18 `build_drift_calibration.py` 加 `--session-source` flag。Calibration set 的用途是 label 原始 vs 漂移 pair 用于 F1 derive；session-mined 例是 section 行为场景，语义不同。强插会扰乱 thresholds derivation。如果未来需要 session-grounded calibration，独立 phase 推进。

### D5 隐私护栏 + 缓解（继承 Phase 14）

- **D-23:** **复用** Phase 14 D-15 已在 `evolution/core/external_importers.py` 落地的 `SECRET_PATTERNS`（JWT 正则 + AWS-secret 邻近模式 + Shannon 熵 ≥ 4.0）+ `_contains_secret(text)` + `_shannon_entropy(s)`。session_prompt_miner 读 user/assistant 文本时一律走 `_contains_secret` 过滤；命中则整条 candidate 丢弃 + `metrics.json.secret_filter_skipped: int` 递增。
- **D-24:** **复用** Phase 14 D-18 已建立的 JSONL `try/except` per-line skip 模式。session_prompt_miner 输出 JSONL 与 evolve_prompt_sections 通过 `--session-source` 加载的 JSONL，每行 `try/except json.JSONDecodeError` 跳过并递增 `metrics.json.jsonl_skipped_lines`；skip 率 >5% Rich console warn。**不**重写 `PromptBehavioralDataset.load`（v2-STAB-01 独立清理范围）。
- **D-25:** `--i-have-consent` 必填 gate（Phase 14 D-16 对称）：mine_prompt_sessions CLI 缺该 flag → `raise SystemExit(1)` + 明确错误消息引用 `~/.hermes/sessions/` 数据来源 + 用户审计期望。evolve_prompt_sections 通过 `--session-source` 加载已清洗 JSONL 时**不**需要此 flag（信任已审过的输出）。NER（Layer 2）和 LLM 数据集审计（Layer 4）**不**在本 phase 落地。

### Claude's Discretion

- `ConfirmBehavioralExample` Signature 的字段名、system prompt 文本、judge 输出 JSON 的精确 schema
- 4 路 per-section heuristic candidate proposer 的具体关键词列表与正则（specifics 给起点；planner 在 PLAN 中固化）
- `mine_prompt_sessions` Rich 表展示细节（字段顺序、颜色、warning 阈值）
- session JSON 解析时遇到结构不规则消息（旧版本 hermes 格式）的容错策略
- judge LLM 调用的 batching/concurrency 上限（默认串行；persona_drift 1.5x 调用量后如发现慢可加 ThreadPool）
- normalized task hash 的具体 collapse_whitespace 实现（推荐 `re.sub(r"\s+", " ", s).strip()`）
- `surface_drift_dropped` 报告的截断长度（dropped_section_distribution 太长时截前 N 个）
- 多源命中加权采用 max 时的 tie-break 策略（默认 mining_signals 列表保留全部源）
- DriftDetector 在 persona_drift extractor 中的调用参数（早期 vs 晚期 turn 窗口大小、最小 turn 数门槛）
- `--session-source` 加载时 PromptDatasetBuilder synthetic 集与 session 集的 train hash collision 报告格式

### Folded Todos

- **`.planning/todos/pending/2026-05-07-expand-secret-patterns.md`** — Phase 14 已落地 Layer 1（JWT/AWS/Shannon 熵）+ Layer 3（--i-have-consent），Phase 19 复用同一基础设施，**无新落地需求**（仅引用与启用）。
- **`.planning/todos/pending/2026-05-07-jsonl-skip-bad-lines.md`** — Phase 14 已落地最小子集（session_miner 输出 + evolve_* --session-source 加载路径 try/except per line + 5% warn），Phase 19 复用同一模式扩展到 mine_prompt_sessions 输出 + evolve_prompt_sections --session-source 加载。**无新落地需求**。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 直接前置 CONTEXT（最重要 —— Phase 19 是 Phase 14 的 prompt 镜像）
- `.planning/phases/14-sessiondb-mining-for-tools/14-CONTEXT.md` — **Phase 14 全部 18 个决策几乎都有 prompt 侧对称物**；D-01..D-18 是 Phase 19 D-01..D-25 的直接来源
- `.planning/phases/14-sessiondb-mining-for-tools/14-RESEARCH.md`（如存在） — Phase 14 研究的隐私护栏 / oracle disagreement / 加权策略均直接适用
- `.planning/phases/14-sessiondb-mining-for-tools/14-PATTERNS.md`（如存在） — session_miner.py / mine_tool_sessions.py 文件结构模板
- `.planning/phases/18-personality-drift-detection/18-CONTEXT.md` — `DriftDetector` 复用入口；persona_drift extractor 调用方需理解 D-CAL-* / D-OUT-* / D-BYPASS-* 已建约束
- `.planning/phases/09-prompt-evaluation/09-CONTEXT.md` — PromptBehavioralExample / PromptDatasetBuilder / PromptBehavioralMetric 数据结构与训练循环来源
- `.planning/phases/07-prompt-loading/07-CONTEXT.md`（如存在） — `extract_prompt_sections` PLATFORM_HINTS 按 key 展开的拓扑；D-08 / D-09 surface drift 判定基础
- `.planning/phases/17-joint-section-optimization/17-CONTEXT.md` — joint vs round-robin pipeline 拓扑；D-21 union 行为需兼容两条 pipeline

### 研究与约束
- `.planning/codebase/CONCERNS.md` §M5 — Privacy/Secret Pattern Coverage；D-23 来源（Phase 14 已落地，Phase 19 复用）
- `.planning/codebase/CONCERNS.md` §M7 — JSONL Loaders Abort on First Bad Line；D-24 来源（Phase 14 已落地最小子集，Phase 19 扩展到 prompt 路径）
- `.planning/codebase/CONCERNS.md` §M6 — Read-Only hermes-agent Not Enforced；Phase 19 是只读管线，与 Phase 14 一致
- `.planning/codebase/CONCERNS.md` §M4 — LLM 输出解析脆弱；D-03 ConfirmBehavioralExample 一次 LLM call 输出 5 个字段，需 typed OutputField（DSPy 3.x）或鲁棒 JSON fallback
- `.planning/research/PITFALLS.md` §Pitfall 2 (Secret/PII Leakage) — 适用于 prompt session 文本
- `.planning/todos/pending/2026-05-07-expand-secret-patterns.md` — folded（Phase 14 已落地，Phase 19 复用）
- `.planning/todos/pending/2026-05-07-jsonl-skip-bad-lines.md` — folded（Phase 14 已落地最小子集，Phase 19 扩展）

### Phase 19 实现锚点（planner / executor 必读）
- `evolution/tools/session_miner.py` — **直接模板**；SessionPromptMiner 镜像其全部结构（构造 + mine() + 4 个 _extract_* + _judge_candidate + _load_session + ConfirmXxx inner Signature）
- `evolution/tools/mine_tool_sessions.py` — **直接模板**；mine_prompt_sessions.py 镜像其全部 13 个 Click option + Rich Table summary + metrics.json schema 风格
- `evolution/prompts/drift_detector.py` — persona_drift extractor 复用入口（D-04 / D-18）
- `evolution/prompts/prompt_dataset.py` lines 33-66 — `PromptBehavioralExample` 当前字段（D-02 加 mining_signals + source 扩展）；`from_dict` 已过滤 unknown keys 保证向后兼容
- `evolution/prompts/prompt_dataset.py` lines 69-? — `PromptBehavioralDataset` train/val/holdout JSONL 持久化与 `to_dspy_examples` 转换
- `evolution/prompts/prompt_dataset.py` — `PromptDatasetBuilder` 风格（SessionPromptMiner 类结构对齐）
- `evolution/prompts/prompt_loader.py` — `extract_prompt_sections` 返回的 `PromptSection` 列表（D-09 surface drift 真实来源；PLATFORM_HINTS 按 key 展开 9 个 sub-section）
- `evolution/prompts/prompt_constraints.py` — `PromptRoleChecker` LLM-as-judge 风格（ConfirmBehavioralExample Signature 设计参考）
- `evolution/prompts/evolve_prompt_sections.py` — Phase 10/17/18 完整 CLI 模板（D-21 加 `--session-source` flag 时对齐风格；step 8c 已有 DriftDetector wiring）
- `evolution/prompts/build_drift_calibration.py` — Phase 18 calibration CLI（D-22 不动；本 phase 不为 calibration 加 --session-source）
- `evolution/core/external_importers.py` lines 47-119 — `SECRET_PATTERNS` + `_shannon_entropy` + `_contains_secret`（D-23 直接复用，无修改）
- `evolution/core/config.py` lines 11-65 — `EvolutionConfig`（无新字段；CLI flag 不下沉到 config）

### 项目规划文档
- `.planning/REQUIREMENTS.md` §PMPT-V2-04 — 需求定义
- `.planning/ROADMAP.md` §Phase 19 — 三条成功标准
- `.planning/PROJECT.md` §Constraints — 尺寸 / 依赖 / 只读约束

### 外部框架
- DSPy 3.x `dspy.LM` / `dspy.Signature` / `dspy.ChainOfThought` — LLM judge 实现（同 ConfirmMisselection 风格）
- DSPy `dspy.OutputField(type=str)` / typed OutputField — ConfirmBehavioralExample Signature 5 个输出字段
- Python `hashlib.sha256` + `re` — task normalization hash（D-15）

### Session 数据格式参考
- `~/.hermes/sessions/session_*.json` 实际样本（45 份样本观测）：每份含 `messages: list[{role, content, tool_calls?, name?, tool_call_id?}]` + 顶层 `tools: list[{type:"function", function:{name, description, parameters}}]`。`role` 取值 `user|assistant|tool|system`；assistant 可同时含 `content` 和 `tool_calls`；user/assistant 文本走 SECRET_PATTERNS 过滤后进入 candidate 池。Prompt 侧 session 信号不依赖 tool_call 结构，主要利用 user/assistant 文本对话流。

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PromptBehavioralExample.from_dict` 字段过滤（`prompt_dataset.py:66`）——D-02 新增 `mining_signals` 字段时旧例自动 default to []，无 schema 迁移
- `PromptBehavioralDataset.save/load` (`prompt_dataset.py`)——D-20 输出复用同一 JSONL 持久化路径
- `_contains_secret` (`external_importers.py:108`)——D-23 复用，user/assistant 文本过滤
- `SECRET_PATTERNS` + `_shannon_entropy` (`external_importers.py:47, 82`)——Phase 14 已扩展，覆盖 JWT/AWS/熵；Phase 19 直接受益
- `SessionToolMiner` (`evolution/tools/session_miner.py`)——SessionPromptMiner 直接模板
- `mine_tool_sessions.py` Click 接口 (`evolution/tools/mine_tool_sessions.py`)——mine_prompt_sessions.py 直接模板
- `DriftDetector` (`evolution/prompts/drift_detector.py`)——persona_drift extractor 复用入口
- `PromptSection` + `extract_prompt_sections` (`prompt_loader.py`)——section_id surface drift 真实来源
- `PromptRoleChecker` (`prompt_constraints.py`)——LLM-as-judge inner Signature 风格模板
- `EvolutionConfig.judge_model` / `eval_model` (`config.py`)——D-17 `--judge-model` 缺省值来源链路

### Established Patterns
- DSPy Module + inner Signature 类（Phase 1/3/13/14/18 统一）——ConfirmBehavioralExample 风格
- Click CLI + Rich console + metrics.json 三件套（Phase 5/13/14/17 统一）——D-17 / D-20 CLI 沿用
- FAILED_/ABORTED_ 输出目录约定（Phase 5/13/14/18）——挖矿失败时输出 `FAILED_<timestamp>/` 含 partial candidate
- PromptBehavioralExample.source 字段标记 provenance（synthetic/golden）——session 例子取 `source="session"`，枚举扩展
- 数据集 train/val/holdout JSONL 三件套（Phase 9 / Phase 14 复用）——D-15 沿用
- 多模型后端 layered config（evolution.yaml < env < CLI override，Phase 12）——`--judge-model` 走同一链路
- Hash mod 100 拆分 + sample copy 仅 train 切分（Phase 14 D-11/D-13）——D-13 / D-15 沿用
- 复用既有 LLM-as-judge constraint（Phase 18 DriftDetector 在 Phase 19 作为信号 extractor 而非约束）——persona_drift 复用范式

### Integration Points
- mine_prompt_sessions CLI → SessionPromptMiner.mine() → 4 路 signal extractor（含 DriftDetector 调用）→ LLM judge → PromptBehavioralExample[] → train/val/holdout 拆分（hash mod 100）→ 复制（仅 train）→ 写 JSONL + metrics.json
- evolve_prompt_sections 启动时若 `--session-source <path>` 给定：load session JSONL（D-24 容错）→ PromptDatasetBuilder 合成 → 两路 hash 去重并 union（D-16）→ 进入既有 GEPA / 优化 → metric 路径不变 → 兼容 Phase 17 joint mode 与 round-robin mode
- LLM judge 调用链路同 `ConfirmMisselection`：单个 dspy.Predict 对象 + per-candidate 调用；不强制 cost_tracker 但 metrics.json 记录 `judge_calls: int`、`judge_false_positives_by_signal: dict[str, int]`
- DriftDetector 在 persona_drift extractor 中作为只读 dependency：读 thresholds.json + 调用 check_all() pairwise → 比较 score 与 thresholds[dim] → score > threshold 进 candidate；不写回 thresholds 或修改 calibration
- session JSON section_id 与 hermes-agent 当前 prompt sections 对照在 SessionPromptMiner.mine() 入口完成；不匹配整例丢弃 + drift 报告

### Risk Anchors (Pre-execution)
- **ConfirmBehavioralExample Signature 一次输出 5 字段**——CONCERNS §M4 LLM 输出解析脆弱；planner 必须确认 `dspy.OutputField(type=str)` 在 DSPy 3.x 可用，或回退到 typed JSON parse helper
- **DriftDetector 在 persona_drift 调用链中的版本兼容性**——若 Phase 18 DriftDetector 接口改变，Phase 19 调用方需同步更新；planner 应在 PLAN 中标注 `DriftDetector.check` API contract 锚点
- **LLM judge 调用预算**：45 sessions × 平均 ~30 candidate/session × ~3k token/call × $5/1M tokens ≈ $20；persona_drift +1.5x ≈ $30；可用 `--judge-model openai/gpt-4.1-mini` 降到 ~$5
- **Synthetic + session 数据集 train 集大小膨胀**：Phase 9 合成 80 例（40 train），Phase 19 session 若产 100+ examples 经 3x duplication train 可达 250+；planner 应监控 GEPA 训练时长是否超预算
- **Oracle source 缺失时 fallback 路径**：D-04 oracle_disagreement 在 `output/prompts/` 空时 silent disable + warn；planner 应在 PLAN 中明确"oracle_disabled" metrics.json 字段记录

</code_context>

<specifics>
## Specific Ideas

- `ConfirmBehavioralExample` Signature 草稿（Claude's Discretion 内可微调）：
  - inputs: `user_message: str`, `available_sections_summary: str`（5 个 section 文本摘要 + platform_hints 9 个 key 列表）, `originally_observed_behavior: str`（紧随 user 的 assistant turn 摘要）, `signal_source: str`, `downstream_context: str`（后续 user/assistant turn 摘要 N=3）
  - outputs: `verdict: str`（"confirm_example" | "false_positive"）, `section_id: str`（5 选 1 或 `platform_hints.<key>`）, `expected_behavior: str`（rubric 形式：1-3 句话描述 agent 应当如何行为）, `difficulty: str`（"easy" | "medium" | "hard"）, `rationale: str`
- `_extract_user_correction` 关键词种子（中英混合，Phase 14 D-04 拓展 + prompt 专属风格词）：`不对|错了|不应该|应该用|应该是|换一个|不是要|wrong|don't|stop|too verbose|太长了|be more concise|don't apologize|不要道歉|stop saying|use simpler language|in Chinese|in English`。命中后 LLM 二判终审。
- `_extract_section_specific_failure` per-section 关键词种子（草稿）：
  - `memory_guidance`: `I already told you|你忘了|repeat question|我已经说过|forget that|don't remember|你之前|recall what`
  - `skills_guidance`: `use /<skill>|should use [a-z-]+ skill|skill not found|you didn't use the [a-z-]+ skill|该用|没用 skill`
  - `session_search_guidance`: `already asked|asked before|let me restate|same question|相同问题`
  - `default_agent_identity`: `too formal|too casual|stop being|act more|don't be so|别那么`
  - `platform_hints.<key>`: 平台 token 后跟 user 反馈错误（`on macOS|Linux下|Windows则` + correction 词）
- 四路加权 multiplier 默认：`{"user_correction": 3, "section_specific_failure": 3, "oracle_disagreement": 2, "persona_drift": 2}`；CLI override 格式 `--behavioral-multiplier "user_correction=3,section_specific_failure=3,oracle_disagreement=2,persona_drift=2"`
- task hash normalization：`sha256(re.sub(r"\s+", " ", user_message.lower()).strip().encode())[:16]`（hex 前 16 位）
- session train/val/holdout 拆分：`bucket = int(hash[:8], 16) % 100`；< 70 → train，< 85 → val，else → holdout
- metrics.json 字段表（最小集，前缀 mining_/judge_/surface_drift_/session_）：
  - `total_candidates_by_signal: dict[str, int]`
  - `judge_confirmed_by_signal: dict[str, int]`
  - `judge_false_positives_by_signal: dict[str, int]`
  - `surface_drift_dropped: int`
  - `surface_drift_sections: list[str]`
  - `final_examples_by_split: {train, val, holdout}`
  - `final_train_after_duplication: int`
  - `mining_multiplier_used: dict[str, int]`
  - `secret_filter_skipped: int`（_contains_secret 触发数）
  - `jsonl_skipped_lines: int`（D-24 每个 load 调用记录）
  - `persona_drift_thresholds_used: dict[str, float]`（从 thresholds.json 读取的副本）
  - `oracle_baseline_path: Optional[str]`（解析到的 baseline-module 路径，缺失时 None + disabled）
  - `judge_calls: int`
  - `judge_model: str`
- mine_prompt_sessions dry-run 行为：跳过 LLM judge，按规则枚举 candidate 后打印分布表（不消耗 API 配额），便于先估 judge 调用量
- LLM judge 调用预算粗估：45 sessions × 平均 ~30 candidate/session × ~3k token/call × $5/1M tokens ≈ $20；persona_drift +1.5x ≈ $30；`--judge-model openai/gpt-4.1-mini` 降到 ~$5
- DriftDetector 在 persona_drift extractor 调用：取 session 前 1/3 assistant turn 拼接为 "original_text"、后 1/3 拼接为 "evolved_text"，对每维 1-run（非 3-run，避免 candidate 数膨胀；3-run 留给 Phase 18 final gate）；min_turns=6（少于 6 turn 跳过 persona_drift 信号）

</specifics>

<deferred>
## Deferred Ideas

- **session-only holdout 子集 + `session_holdout_score` 指标** — 评估 hermes-agent 真实分布上的表现；与 Phase 14 D-13 / Phase 13 v1 baseline 硬门理念冲突，留 Phase 19+ 重审
- **`behavioral_weight: float` 字段 + metric 乘权** — 比复制更精细的加权机制；本 phase 选样本复制（D-13）以保 metric/schema 兼容；若样本复制后训练效果不佳再演进
- **多 section 同时归因（section_ids: list[str]）schema 改造** — 本期单选 section_id 拆多条；如果 session 出现大量 cross-section binding，重审
- **session-grounded calibration set 增强 Phase 18 DriftDetector thresholds** — 独立 phase；Phase 19 不动 calibration 路径
- **Per-section quota cap 防止 platform_hints 某一 platform_key 过采样** — 本期不做；如果 metrics 显示某 section_id 占 train 50%+ 再加 cap
- **`--session-mode replace|holdout` 三档位 flag** — 本 phase 仅做 union 默认（D-21）；replace/holdout 模式留待真实需求出现
- **Phase 16 dashboard 加 prompt session-source 维度** — 本期 mining metrics 用 `mining_*` 前缀便于未来 dashboard 接入按前缀分桶；具体接入留 Phase 16 v3
- **NER (Layer 2 PII)** — 隐私护栏增强；本 phase 不引入新依赖，留 v2-STAB 或独立 hygiene phase
- **LLM 数据集审计（Layer 4）** — 挖矿后整体审 PII/secret；本 phase 仅落 L1+L3
- **Two-stage LLM call（verdict + section_id 分开，expected_behavior 单独）** — 本期单 call 5 字段；如果 LLM 输出质量差再拆
- **persona_drift extractor 用 3-run averaging（Phase 18 final gate 同策略）** — 本期 1-run（candidate 召回阶段，过滤压力低）；如果误报率高再升级
- **mine_prompt_sessions 增量挖矿模式（仅处理新 session 文件）** — 本期全量；如果 sessions 数达 100+ 增量挖矿值得加

### Reviewed Todos (not folded)

- **`.planning/todos/pending/2026-05-07-enforce-readonly-hermes-agent.md`** — Phase 19 是只读挖矿管线，**完全不调用** prompt section 写回，因此 deploy_mode gate 在本 phase 上无落地点。留 Phase 22 持续进化循环或独立 hygiene phase。
- **`.planning/todos/pending/2026-05-07-add-lockfile-dspy-pin.md`** — 依赖锁定，不在本期 scope（v2-STAB-01 范围）
- **`.planning/todos/pending/2026-05-07-centralize-lm-retry-handling.md`** — LLM 重试集中化，与本 phase LLM judge 调用模式无强相关；如果实施后 mine_prompt_sessions 长跑遇到限流再单独评估
- **`.planning/todos/pending/2026-05-07-harden-llm-output-parsing.md`** — LLM 输出解析鲁棒性，CONCERNS §M4；planner 在实现 ConfirmBehavioralExample Signature 时可参考但非本 phase 主线 scope

</deferred>

---

*Phase: 19-sessiondb-behavioral-mining-for-prompts*
*Context gathered: 2026-05-16*
