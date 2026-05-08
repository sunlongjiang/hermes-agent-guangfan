# Phase 14: SessionDB Mining for Tools - Context

**Gathered:** 2026-05-08
**Status:** Ready for planning

<domain>
## Phase Boundary

从 hermes-agent 真实会话转录（`~/.hermes/sessions/*.json`）中**自动挖矿** misselection 模式作为高价值 tool selection 训练样本。覆盖 TOOL-V2-01。**Phase 14 仅产出 + 注入数据**，不引入新 metric/optimizer，不触及 hermes-agent 写回路径，与 Phase 13 per-param 优化正交。

落地三件事：
1. SessionMiner 三路信号（错误重试 / 用户纠正 / oracle 分歧）→ LLM judge → ToolSelectionExample[]
2. 新 CLI `mine_tool_sessions.py` 一次离线挖矿，输出 JSONL
3. evolve_tool_descriptions / evolve_tool_params 加 `--session-source` flag union 合成数据集，misselection 例子按信号源加权复制（仅复制到 train 切分）

不引入新依赖，复用 DSPy/Click/Rich 栈。

</domain>

<decisions>
## Implementation Decisions

### D1 误选信号定义

- **D-01:** 三路信号叠加：**B (error_retry)** + **A (user_correction)** + **C (oracle_disagreement)**。三路均产出 candidate（task, available_tools, originally_used_tool, downstream_context）四元组送 LLM judge，judge 决定最终 `correct_tool`；session 中**原选错的工具入 `confuser_tools`**。不要 D（多工具串联失败）信号——噪声大、定义模糊。
- **D-02:** ToolSelectionExample 新增字段 `misselection_signals: list[str]`，取值集合 `{"error_retry", "user_correction", "oracle_disagreement"}`。同一 (normalized task hash, correct_tool) 被多路命中时 union 信号集合，不去重多产 example。新字段默认 `field(default_factory=list)`，向后兼容历史 Phase 4 数据集（旧例 signals=[]）。
- **D-03:** **所有** correct_tool 由 LLM judge 决定，不依赖 exit_code 启发式或预测置信度。Judge 输入：(task_description, full_tool_schemas, originally_used_tool, post-call session context including tool result + 后续 user/assistant turns)；输出：(verdict ∈ {confirm_misselection, false_positive}, correct_tool ∈ available_tools, rationale)。
- **D-04:** 三路信号的 candidate 抽取规则：
  - **B (error_retry):** assistant turn N 触发 tool_use；下一 `tool` 消息含 `error` 或 `exit_code != 0`；turn N+M 内同一 task chunk（user 消息切分边界内）改用不同工具完成。
  - **A (user_correction):** user 紧随 assistant tool_use 后发出 correction-like 消息；判定借助一份正则关键词列表 + LLM 二判（关键词列表预热召回，LLM 终审）。关键词种子见 specifics。
  - **C (oracle_disagreement):** 用 Phase 5/13 已产出的最佳 ToolModule（最近一次成功 evolve 输出）在 (task, original available_tools) 上重打分；若 ToolModule 预测工具 ≠ session 实际使用工具，标为 candidate。所有 candidate（含 verdict=false_positive）一并送 LLM judge；只有 confirm_misselection 才进数据集。
- **D-05:** Judge 输出 `verdict=false_positive` 的 candidate 不丢弃——写入 mining 报告 metrics.json 字段 `judge_false_positives_by_signal: dict[str, int]`，便于审计 LLM judge 噪声。

### D2 架构与 CLI

- **D-06:** **新建** `evolution/tools/session_miner.py`，提供 `SessionToolMiner` 类。结构对齐 `ToolDatasetBuilder`：构造接 `EvolutionConfig`，方法 `mine(sessions_dir: Path, current_tools: list[ToolDescription]) -> list[ToolSelectionExample]`。三路 signal extractor 为内部私有方法（`_extract_error_retry`, `_extract_user_correction`, `_extract_oracle_disagreement`）。LLM judge 用内部 inner Signature 类（`ConfirmMisselection`），与 `ToolFactualChecker`/`ParamConsistencyChecker` 风格一致。
- **D-07:** **新建** CLI 入口 `evolution/tools/mine_tool_sessions.py`（Click + Rich）。复用 Phase 5 既有 flags：`--hermes-repo` / `--model` / `--api-base` / `--dry-run`。新增 flags：
  - `--sessions-dir <path>` 默认 `~/.hermes/sessions`
  - `--output <dir>` 默认 `datasets/tools/sessions/<YYYYMMDD_HHMMSS>/`
  - `--limit <int>` 0=全部
  - `--i-have-consent` **必填** boolean flag（缺则 abort，见 D-13）
  - `--signals` 逗号分隔子集 `error_retry,user_correction,oracle_disagreement`，默认全部
  - `--baseline-module <output-dir>` 指向已有 evolve 产物用作 oracle（C 信号）；缺省时跳过 C
  - `--judge-model` 默认 `openai/gpt-4.1`，可覆盖
- **D-08:** 输出目录结构：
  ```
  datasets/tools/sessions/<YYYYMMDD_HHMMSS>/
  ├── train.jsonl / val.jsonl / holdout.jsonl  # 70/15/15 拆分（D-11）
  ├── metrics.json                              # 信号统计、judge 调用数、surface drift
  └── miner_log.jsonl                           # 每条 candidate→verdict 的审计行
  ```
  CLI 末尾 Rich table 总结：原始 candidate / judge 通过 / 各 signal 命中数 / dropped surface drift / final example 数。
- **D-09:** evolve_tool_descriptions / evolve_tool_params 新增**完全相同**的 flag：`--session-source <path>`。指向 `datasets/tools/sessions/<timestamp>/` 目录。**默认行为：union**——session-source 三个 split 与 ToolDatasetBuilder 合成数据集对应 split union 合并，去重见 D-11。不传时一切走原行为，不触发挖矿。
- **D-10:** **不**扩展 `HermesSessionImporter`。session_miner 直接读 session JSON，原因：tool_calls 抽取语义与现有 user/assistant text 抽取差异大，复用反而牵涉双向接口压力。两个数据通道独立。

### D3 加权机制实现

- **D-11:** **样本复制策略**——不改 metric、不改 ToolSelectionExample 之外的 schema。SessionToolMiner 在 dataset 输出阶段按 `misselection_signals` 决定复制次数：
  - `error_retry` 命中：3x
  - `user_correction` 命中：3x
  - `oracle_disagreement` 命中：2x
  - 多源命中取 max（不累乘）
  - 复制**仅在 train 切分**发生；val/holdout 保留 1 份
- **D-12:** mine_tool_sessions CLI flag `--misselection-multiplier "error_retry=3,user_correction=3,oracle=2"`（key=value 格式覆盖默认）。GEPA 通过均匀采样自动消化加权。
- **D-13:** 数据集拆分：**按规范化 task hash 去重**——hash = `sha256(strip + lower + collapse_whitespace(task_description))[:16]`。同 hash 仅出现在一个切分，由 hash 模 100 划入 train(<70) / val(<85) / holdout(else)，保证可重现且无切分泄漏。复制发生在去重落桶**之后**，仅 train 切分内复制。session-only holdout 子集**不**抽取（与 Phase 13 D-14 v1 baseline 硬门理念一致——holdout 来源单一保证可比对）。
- **D-14:** evolve_* CLI 在 union 合成 + session 数据集时，先各自 hash 去重，再两路 union；同 hash 例子 session 优先（误选信号在 misselection_signals 字段保留）。最终 train/val/holdout 跨数据源 hash 去重。

### D4 隐私护栏 + 表面漂移

- **D-15:** **SECRET_PATTERNS 扩展（Layer 1）**——在 `evolution/core/external_importers.py` 的 `SECRET_PATTERNS` 增量加：
  - JWT 正则 `r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"`
  - AWS-secret 邻近模式 `r"(?:aws[_-]?(?:access|secret)|AKIA)[\s\S]{0,40}[A-Za-z0-9/+=]{32,}"`
  - Shannon 熵启发式：在 `_contains_secret(text)` 内对 ≥24 char 连续 base64-like token (`[A-Za-z0-9_/+=-]+`) 计算 Shannon 熵 > 4.0 即标记。新增辅助 `_shannon_entropy(s: str) -> float`。归因 `.planning/codebase/CONCERNS.md` §M5 + folded todo `2026-05-07-expand-secret-patterns.md`。
- **D-16:** **--i-have-consent flag（Layer 3）**——mine_tool_sessions CLI **必填** flag；缺省 raise SystemExit(1) 含明确错误消息。evolve_* CLI 通过 `--session-source` 加载已清洗 JSONL 时**不**需要此 flag（信任已审过的输出）。NER（Layer 2）和 LLM 数据集审计（Layer 4）**不**在本 phase 落地。
- **D-17:** **工具表面漂移**——session 引用工具名不在当前 hermes-agent `extract_tool_descriptions()` 结果时整例丢弃；CLI 末尾打印 `dropped_count` + `dropped_tool_distribution: dict[str, int]`；metrics.json 写入 `surface_drift_dropped: int` + `surface_drift_tools: list[str]`。**不**维护 alias 表、**不**保留漂移例做 audit（保持 Phase 14 范围紧）。
- **D-18:** **JSONL 容错读写（folded todo 子集）**——session_miner JSONL 输出和 evolve_* CLI 通过 `--session-source` 加载的 JSONL 读取路径，每行 `try/except json.JSONDecodeError` 跳过并 increment `skipped` 计数；skip 率 >5% Rich console warn。`EvalDataset.load` / `GoldenDatasetLoader.load` 不动（v2-STAB-01 独立清理）。归因 `.planning/codebase/CONCERNS.md` §M7 + folded todo `2026-05-07-jsonl-skip-bad-lines.md`（最小子集）。

### Claude's Discretion

- `ConfirmMisselection` Signature 的字段名、system prompt 文本、judge 输出 JSON 的精确 schema
- `_extract_user_correction` 关键词种子列表的具体词条（"不对/错了/应该用/用 X 替代/不是要/换一个" 等中英混合，参见 specifics 起点）和 LLM 二判 prompt
- mine_tool_sessions Rich 表展示细节（字段顺序、颜色、warning 阈值）
- session JSON 解析时遇到结构不规则消息（旧版本 hermes 格式）的容错策略
- judge LLM 调用的 batching/concurrency 上限（默认串行；如发现慢可加 ThreadPool）
- normalized task hash 的具体 collapse_whitespace 实现（推荐 `re.sub(r"\s+", " ", s).strip()`）
- `surface_drift_dropped` 报告的截断长度（dropped_tool_distribution 太长时截前 N 个）
- 多源命中加权采用 max 时的 tie-break 策略（默认 misselection_signals 列表保留全部源）

### Folded Todos

- **`.planning/todos/pending/2026-05-07-expand-secret-patterns.md`** — 见 D-15/D-16；Layer 1（JWT 正则 + AWS-secret 正则 + Shannon 熵）+ Layer 3（--i-have-consent flag）落地，Layer 2（NER）+ Layer 4（LLM 审计）延后。归因 CONCERNS M5。
- **`.planning/todos/pending/2026-05-07-jsonl-skip-bad-lines.md`** — 见 D-18；最小子集落地——仅 session_miner 输出 JSONL 和 evolve_* 通过 --session-source 加载 JSONL 路径加 try/except per line + skip 计数 + 5% 阈值 warn。EvalDataset/GoldenDatasetLoader 不动（v2-STAB-01 独立 hygiene）。归因 CONCERNS M7。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 研究与约束（必读）
- `.planning/codebase/CONCERNS.md` §M5 — Privacy/Secret Pattern Coverage Undersized for Phase 14；D-15/D-16 来源
- `.planning/codebase/CONCERNS.md` §M7 — JSONL Loaders Abort on First Bad Line；D-18 来源
- `.planning/codebase/CONCERNS.md` §M6 — Read-Only hermes-agent Not Enforced；本 phase 完全不写回，不影响但需提醒 planner 复查 read-only 边界
- `.planning/codebase/CONCERNS.md` §M4 — LLM 输出解析脆弱；D-03 LLM judge / D-04 user_correction LLM 二判增加调用，需鲁棒 JSON 解析
- `.planning/research/PITFALLS.md` §Pitfall 2 — Secret/PII Leakage in Mined Datasets（如存在；若仅在研究 SUMMARY 中也要查）
- `.planning/todos/pending/2026-05-07-expand-secret-patterns.md` — folded, 见 D-15/D-16
- `.planning/todos/pending/2026-05-07-jsonl-skip-bad-lines.md` — folded（最小子集），见 D-18
- `.planning/todos/pending/2026-05-07-enforce-readonly-hermes-agent.md` — reviewed not folded；Phase 14 是只读管线，本 phase 不实现 deploy_mode gate，留 Phase 22

### Phase 14 实现参考
- `evolution/core/external_importers.py` lines 78-80 — `SECRET_PATTERNS` 现有定义（D-15 扩展点）
- `evolution/core/external_importers.py` lines 78-80 — `_contains_secret()` 现有实现（D-15 加 `_shannon_entropy` 辅助）
- `evolution/core/external_importers.py` lines 334-416 — `HermesSessionImporter` 现有 user/assistant 抽取逻辑（D-10 不扩展，session_miner 单独读 session JSON 但可参考 SESSION_DIR 默认路径与 secret 过滤模式）
- `evolution/tools/tool_dataset.py` lines 33-71 — `ToolSelectionExample` 现有字段（D-02 加 misselection_signals 字段）
- `evolution/tools/tool_dataset.py` lines 74-148 — `ToolSelectionDataset` 现有 train/val/holdout JSONL 持久化与 from_dict 兼容性策略（向后兼容旧例靠 from_dict 已有的字段过滤）
- `evolution/tools/tool_dataset.py` lines 154-308 — `ToolDatasetBuilder`（D-06 SessionToolMiner 风格对齐）
- `evolution/tools/tool_loader.py` lines 1-200 — `ToolDescription` / `ToolParam` / `extract_tool_descriptions` 接口（D-17 工具表面对照）
- `evolution/tools/tool_module.py` — `ToolModule` 当前结构（C 信号 oracle 重打分入口）
- `evolution/tools/tool_constraints.py` — `ToolFactualChecker` 类结构（D-06 的 LLM judge 类对齐 inner Signature 风格）
- `evolution/tools/evolve_tool_descriptions.py` — Phase 5 完整 CLI 模板（D-07 mine CLI 复用 hermes-repo/model/api-base/dry-run flags）
- `evolution/tools/evolve_tool_params.py` — Phase 13 CLI 模板（D-09 加 --session-source flag 时对齐风格）
- `evolution/core/config.py` lines 11-65 — `EvolutionConfig`（无新字段，CLI flag 不下沉到 config）

### 项目规划文档
- `.planning/REQUIREMENTS.md` §TOOL-V2-01 — 需求定义
- `.planning/ROADMAP.md` §Phase 14 — 三条成功标准
- `.planning/PROJECT.md` §Constraints — 尺寸 / 依赖 / 只读约束
- `.planning/phases/13-per-parameter-description-optimization/13-CONTEXT.md` — Phase 13 D-15a (loud GEPA fail) / D-08 (--reflection-model + --max-cost-usd) / D-13 (cost cap) 的设计模式可参考；本 phase **不**触发 GEPA，但 LLM judge 调用预算约束遵循同一收口
- `.planning/phases/05-tool-constraints-cli/05-CONTEXT.md`（如存在） — Phase 5 CLI 与 metrics.json 结构参考
- `.planning/phases/04-tool-dataset-evaluation/04-CONTEXT.md`（如存在） — Phase 4 ToolSelectionExample 与 train/val/holdout 切分先例

### 外部框架
- DSPy 3.x `dspy.LM` / `dspy.Signature` / `dspy.ChainOfThought` — LLM judge 实现（同 ParamConsistencyChecker 风格）
- DSPy `Prediction` 对象 usage 字段 — 后续若加 cost cap 时复用 Phase 13 cost_tracker（本 phase 不强制启用）
- Python `hashlib.sha256` + `re` — task normalization hash（D-13）

### Session 数据格式参考
- `~/.hermes/sessions/session_*.json` 实际样本（44 份样本观测）：每份含 `messages: list[{role, content, tool_calls?, name?, tool_call_id?}]` + 顶层 `tools: list[{type:"function", function:{name, description, parameters}}]`。`role` 取值 `user|assistant|tool|system`；assistant 可同时含 `content` 和 `tool_calls`；`tool` 消息 content 为字符串化结果（含 `error/exit_code` 字段时表示工具失败）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ToolSelectionExample.from_dict` 字段过滤（`tool_dataset.py:71`）——D-02 新增 `misselection_signals` 字段时旧例自动 default to []
- `ToolSelectionDataset.save/load`（`tool_dataset.py:90-128`）——D-08 输出复用同一 JSONL 持久化路径，仅 D-18 需在 load 处加 try/except
- `_contains_secret`（`external_importers.py:78-80`）——D-15 扩展点；同时 D-04 user_correction 抽取也要先过这层
- `ToolFactualChecker`（`tool_constraints.py`）——D-06 SessionToolMiner 内 LLM judge 类的结构样板（inner Signature + dspy.LM 调用 + JSON 解析）
- `EvolutionConfig.eval_model` / `judge_model`（`config.py`）——D-07 `--judge-model` 缺省值来源链路
- `extract_tool_descriptions(hermes_repo)`（`tool_loader.py`）——D-17 当前工具表面真实来源

### Established Patterns
- DSPy Module + inner Signature 类（Phase 1/3/13 统一）——LLM judge 风格
- Click CLI + Rich console + metrics.json 三件套（Phase 5/13 统一）——D-07 CLI 沿用
- FAILED_/ABORTED_ 输出目录约定（Phase 5/13）——挖矿失败时输出 `FAILED_<timestamp>/` 含 partial candidate（参考 Phase 13 D-13）
- ToolSelectionExample.source 字段标记 provenance（synthetic/golden）——session 例子取 `source="session"`
- 数据集 train/val/holdout JSONL 三件套（Phase 4 / Phase 13 复用 Phase 4 数据集）——D-13 沿用
- 多模型后端 layered config（evolution.yaml < env < CLI override，Phase 12）——`--judge-model` 走同一链路

### Integration Points
- mine_tool_sessions CLI → SessionToolMiner.mine() → 三路 signal extractor → LLM judge → ToolSelectionExample[] → train/val/holdout 拆分（hash mod 100）→ 复制（仅 train）→ 写 JSONL + metrics.json
- evolve_tool_descriptions / evolve_tool_params 启动时若 `--session-source <path>` 给定：load session JSONL（D-18 容错）→ ToolDatasetBuilder 合成 → 两路 hash 去重并 union（D-14）→ 进入既有 GEPA / 优化 → metric 路径不变
- LLM judge 调用链路同 `ToolFactualChecker`：单个 dspy.Predict 对象 + per-candidate 调用；不强制 cost_tracker 但 metrics.json 记录 `judge_calls: int`、`judge_false_positives_by_signal: dict[str, int]`
- session JSON tool_call schema 与 hermes-agent 当前 tools 表面对照在 SessionToolMiner.mine() 入口完成；不匹配整例丢弃 + drift 报告

</code_context>

<specifics>
## Specific Ideas

- `ConfirmMisselection` Signature 草稿（Claude's Discretion 内可微调）：
  - inputs: `task_description: str`, `available_tools_summary: str`（精简 name+description+param schema 列表）, `originally_used_tool: str`, `signal_source: str`, `downstream_context: str`（紧随 tool 调用后的 N 个消息摘要）
  - outputs: `verdict: str`（"confirm_misselection" | "false_positive"）, `correct_tool: str`, `rationale: str`
- `_extract_user_correction` 关键词种子（中英混合）：`不对|错了|不应该|应该用|应该是|用[X]|换一个|不是要|换工具|wrong tool|use [tool] instead|should have used|that's not right`。命中后 LLM 二判终审。
- 三路加权 multiplier 默认：`{"error_retry": 3, "user_correction": 3, "oracle_disagreement": 2}`；CLI override 格式 `--misselection-multiplier "error_retry=3,user_correction=3,oracle=2"`
- task hash normalization：`sha256(re.sub(r"\s+", " ", task_description.lower()).strip().encode())[:16]`（hex 前 16 位）
- session train/val/holdout 拆分：`bucket = int(hash[:8], 16) % 100`；< 70 → train，< 85 → val，else → holdout
- metrics.json 字段表（最小集）：
  - `total_candidates_by_signal: dict[str, int]`
  - `judge_confirmed_by_signal: dict[str, int]`
  - `judge_false_positives_by_signal: dict[str, int]`
  - `surface_drift_dropped: int`
  - `surface_drift_tools: list[str]`
  - `final_examples_by_split: {train, val, holdout}`
  - `final_train_after_duplication: int`
  - `multiplier_used: dict[str, int]`
  - `secret_filter_skipped: int`（_contains_secret 触发数）
  - `jsonl_skipped_lines: int`（D-18 每个 load 调用记录）
- mine_tool_sessions dry-run 行为：跳过 LLM judge，按规则枚举 candidate 后打印分布表（不消耗 API 配额），便于先估 judge 调用量
- D-04 B 信号识别 "tool 报错"：tool 消息 content 是 JSON-encoded string；用 `json.loads(content)` 后查 `error` 字段或 `exit_code != 0`；解析失败也算成功（保守）
- LLM judge 调用预算粗估：44 sessions × 平均 ~20 candidate/session × ~2k token/call × $5/1M tokens ≈ $9；可 by 配置 `--judge-model openai/gpt-4.1-mini` 降到 ~$1.5

</specifics>

<deferred>
## Deferred Ideas

- **Phase 19 SessionDB Behavioral Mining for Prompts** — 同样三路信号但用于 prompt section（角色一致性 / memory 引用模式）；本 phase 决策可作模板，但 Phase 19 数据切片粒度不同，session_miner 不强制抽公共基类——等 Phase 19 真正落地时再决定是否提取 base class
- **Phase 16 Per-Tool Regression Dashboard** — session 例子可能让 per-tool 分布更倾斜（read_file 437 / search_files 170 / terminal 104）；Phase 16 dashboard 视角下 session 加权后的工具不均衡需要专门可视化
- **Phase 15 Think-Augmented Tool Selection** — session 中 assistant 的 reasoning text（pre-tool_call 的 content）可作为 think augmentation 的训练样本；Phase 14 不抽取该字段，留 Phase 15
- **Layer 2 NER（spacy/Presidio 可选依赖）** — 隐私护栏的 PII 检测增强；本 phase 不引入新依赖，留 v2-STAB 或独立 hygiene phase
- **Layer 4 LLM 数据集审计步骤** — 挖矿后整体审 PII/secret；本 phase 仅落 L1+L3
- **--session-mode replace|holdout** — 三档位 flag 行为；本 phase 仅做 union 默认；replace/holdout 模式留待真实需求出现
- **`misselection_weight: float` 字段 + metric 乘权** — 比复制更精细的加权机制；本 phase 选样本复制（D-11）以保 metric/schema 兼容；若样本复制后训练效果不佳再演进
- **多工具串联失败 (D 信号)** — 启发式噪声大；后续若 misselection 召回率不够再考虑
- **session-only holdout 子集 + `session_holdout_score` 指标** — 评估 hermes-agent 真实分布上的表现；与 Phase 13 v1 baseline 硬门理念冲突，留 Phase 19+ 重审

### Reviewed Todos (not folded)

- **`.planning/todos/pending/2026-05-07-enforce-readonly-hermes-agent.md`** — Phase 14 是只读挖矿管线，**完全不调用** `write_back_description` 或 prompt section 写回，因此 deploy_mode gate 在本 phase 上无落地点。留 Phase 22 持续进化循环或独立 hygiene phase 集中实施。

</deferred>

---

*Phase: 14-sessiondb-mining-for-tools*
*Context gathered: 2026-05-08*
