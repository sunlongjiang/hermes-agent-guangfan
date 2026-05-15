# Phase 17: Joint Section Optimization - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

让 GEPA 把 hermes-agent prompt 的 5 个 section 视为一组参数**同时**优化,取代当前的 round-robin(逐段循环)。覆盖 ROADMAP §Phase 17 / PMPT-V2-01 — 三条 Success Criteria(PromptModule 支持 all-sections-active 模式、GEPA 单次 pass 可 mutate 多 section、joint 在 holdout 上 ≥ round-robin)。

**In scope:**
- 改造 `evolution/prompts/prompt_module.py`,新增 joint mode:全部 5 个 section 的 `Predict` 实例同时挂在 `section_predictors` 上,对 DSPy `named_parameters()` 可见。Round-robin 通过 `set_active_section()` 的现有路径继续工作。
- 改造 `evolution/prompts/evolve_prompt_sections.py`:
  - 新增 `--mode joint|round-robin` flag(Click.Choice,默认 `joint`);`--section <id>` 隐含 round-robin 单点优化(用户可不传 `--mode`)。
  - joint pipeline:不按 section_id filter dataset,GEPA 看完整 train/val,单次 `optimizer.compile()` 调用,`max_metric_calls = iterations * 50 * 5`。
  - **Inline A/B baseline**:joint 跑完 holdout 评估后,在同一 CLI 内再跑一遍 round-robin(全量 N 轮 × 5 section)作为 baseline,两者在同一 holdout 上打分。
  - 启动时 stdout 打预算预估行,显式列 joint(`iterations × 50 × 5`)与 round-robin baseline(`iterations × 50 × 5 = 5×500 calls/section`)总 LM 调用数。
- 软门 A/B:`joint_score ≥ roundrobin_score - epsilon`(epsilon 默认 0.01 = 1pp),不满足时 stdout 黄警告 + 两者都落盘;不 exit 2,不阻断 constraint validation 与 evolved_sections.json 写盘。
- metrics.json schema 扩展:新增 `mode: joint|round-robin`、`joint_score`、`roundrobin_baseline_score`、`epsilon_pp` 四字段;保留现有 `baseline_score`(= 未优化的原始 prompt 在 holdout 上的得分,与 round-robin baseline 不同)、`evolved_score`、`improvement` 等字段。
- diff.txt 复用现有 `_generate_diff()`(已通过 section_id 遍历,自然支持 multi-section 输出),零代码改动。
- 测试:
  - `test_prompt_module.py` 新增 joint mode 单测(`set_joint_mode(True)` 后 `named_parameters()` 含全部 5 个 Predict)。
  - `test_evolve_prompt_sections_cli.py` 新增 `--mode joint`(默认走通)、`--mode round-robin`(legacy 路径)、`--section <id>` 自动 round-robin、joint < round-robin - epsilon 触发软警告四类集成测试(用轻量 fake GEPA mock,避免真 LM 调用)。

**Out of scope:**
- 删除 round-robin 实现 — `set_active_section()` 与 round-robin pipeline 全部保留,通过 `--mode round-robin` 触达(11 个现有测试用例零回归)。
- Round-robin 默认调用警告/deprecation 提示 — 静默切换,文档侧标注新默认即可。
- 接入 Phase 16 regression_dashboard.py — 仅保证 metrics.json 字段可被未来 dashboard 读取(`mode` 字段足以分桶 joint/round-robin),不修改 `regression_dashboard.py`。
- per-section diff 拆文件 — 单 diff.txt 含全部 section 的 unified diff 维持现状。
- joint-only iteration budget flag(如 `--joint-iterations`) — 用户用 `--iterations N` 同时控制 joint 与 round-robin baseline。
- 跨 section 联动验证(如 "section A 长度增长抑制 section B 风格漂移") — Phase 18 (Personality Drift Detection) 与本期完全解耦,本期仅做 GEPA 多参数优化。
- joint mode 在 `--dry-run` 中的 budget breakdown ASCII 表(stdout 预算预估行已足够,不做额外 dry-budget flag)。

</domain>

<decisions>
## Implementation Decisions

### Round-robin 共存策略
- **D-RR-01:** 保留 round-robin 实现为 `--mode round-robin` 显式 fallback。`PromptModule.set_active_section()` 不动,所有现有调用(`evolve_prompt_sections.py` 内的 for-loop)走 round-robin 分支不变。Rationale:joint 出问题时有 fallback;A/B baseline 需复用 round-robin 实现;11 个现有测试用例零改写。
- **D-RR-02:** Joint 是 CLI 默认 mode,**静默切换**,不打 deprecation 警告。Rationale:对内部脚本/文档的现有 `python -m evolution.prompts.evolve_prompt_sections` 调用隐式提升到 joint;新默认在 README 与 docstring 中标注即可。
- **D-RR-03:** `--section <section_id>` flag **隐含** round-robin 单点优化路径,用户不需要同时传 `--mode round-robin`。Rationale:贴合 "我只想调某一段" 的 mental model;joint 在单参数场景退化为 GEPA 单点,语义重复且 budget 浪费;`--section X` 与 `--mode joint` 同时存在时按 round-robin 单点处理,不报错。
- **D-RR-04:** `--mode` 用 `click.Choice(["joint", "round-robin"])`,默认 `joint`。Rationale:未来加第 3 种模式(如 `hybrid`)零成本扩展;比 `--legacy` boolean 更可读。

### A/B baseline 与软门
- **D-AB-01:** 采用 **inline A/B**:joint 跑完 holdout 评估后,同一 CLI 进程内再跑一次完整 round-robin(`for sid in section_ids: set_active_section(sid); GEPA.compile(...)`),用相同 dataset、相同 metric、相同 holdout 打分。Rationale:apples-to-apples;`--baseline-run <ts>` 外部对比依赖 schema 稳定性,且历史 round-robin 输出可能是不同 dataset 跑出的,误差大;ROADMAP 成功标准 3 直接要求 joint ≥ round-robin,必须同条件对比。
- **D-AB-02:** 软门:joint_score < roundrobin_score - epsilon 时,stdout 打黄警告(`[yellow]Joint score (X.XXX) below round-robin baseline (Y.YYY) by Zpp — review before deploying[/yellow]`),但**两者都落盘**,**不 exit 2**,**不阻断 constraint validation 与 evolved_sections.json 写出**。Rationale:与 Phase 16 dashboard `--warning-threshold-pp` 模型一致;LLM-as-judge 评分本身有方差,硬门容易误杀;运维方能通过 metrics.json 自查后决定是否回滚。
- **D-AB-03:** Epsilon 默认 **0.01 (1pp)**,固定常量不暴露为 flag。Rationale:与 Phase 13/16 的 2pp 工具回归警告比 1pp 更紧 — 这里是 prompt 评分的 LLM-judge 方差最大场景,1pp 是 "几乎相同" 而不是 "等价";若 holdout 扩到 ≥50 例后想调紧,后续 phase 可改成参数化(本期不预设 flag,YAGNI)。
- **D-AB-04:** Round-robin baseline 跑全量 `iterations × 5` 调用(与 `--mode round-robin` 单跑等价),不做 budget 压缩。Rationale:压缩 baseline 会让 A/B 不对称 — "joint 充分优化 vs round-robin 半成品" 不是有效证明;成本上 LM 调用 6× 单 phase 但只发生在 joint mode 默认运行,可接受。

### CLI 与 iteration 预算
- **D-IT-01:** joint mode 下 `--iterations N` 是 **GEPA 总轮数**(优化器对 5 参数一同 reflection 的 N 个 pass);round-robin baseline 仍是 N 次/section × 5 section。Rationale:GEPA 把多参数当一组优化,N 轮 reflection 是优化器层面的语义;round-robin 是 5 个独立优化进程,N 是每个进程的 reflection 次数;两者 LM 总调用之比 1:5 是本身 GEPA 的语义差。
- **D-IT-02:** joint 的 GEPA `max_metric_calls = iterations × 50 × 5`(乘 5 因 5 个参数)。Rationale:DSPy GEPA 对单参数推荐 `iterations × 50`(现有 round-robin per-section 用法);多参数需要按参数数量线性放大 budget,保证 reflection LM 有足够 step 收敛多参数空间;若 researcher 在 DSPy GEPA 文档中查到更精确公式可微调,本期定为 `× 5` 起点。
- **D-IT-03:** CLI 启动时 stdout 打预算预估行,格式:
  ```
  Joint optimization:        iterations=10, max_metric_calls=2500
  Round-robin A/B baseline:  iterations=10/section × 5 sections, max_metric_calls=500/section
  Total est. LM calls:       ~5000 (joint) + ~2500 (baseline) = ~7500
  ```
  Rationale:用户能在跑下去之前判断成本与时间;与 Phase 5/13 现有的 "Configuring optimizer" stdout 块风格一致。

### Output schema & metrics.json
- **D-OUT-01:** joint run 与 round-robin run 共用 `output/prompts/<YYYYMMDD_HHMMSS>/` 目录格式,**不另起 `output/prompts_joint/`**。区分通过 metrics.json `mode` 字段。Rationale:未来 Phase 16 dashboard 扩 prompt 方向时只扫一个 root;消费方按 `mode` 字段分桶即可;符合 Phase 16 D-04 "default 落 CWD + flag override" 的就近原则。
- **D-OUT-02:** metrics.json 新增字段(joint mode 下):
  - `mode: "joint"` 或 `"round-robin"`(必填,所有 run)
  - `joint_score: float`(仅 joint mode 写)
  - `roundrobin_baseline_score: float`(仅 joint mode 写,来自 inline A/B 的 round-robin run)
  - `epsilon_pp: 0.01`(joint mode 软门常量,落盘便于复现)
  - 保留现有字段:`baseline_score`(未优化的原始 prompt holdout 得分)、`evolved_score`(本 mode 演化后 holdout 得分,joint mode 下 = `joint_score`)、`improvement`(`evolved - baseline`)、`iterations`、`eval_model` 等不变
  Rationale:`joint_score` 与 `roundrobin_baseline_score` 显式双列,A/B 关系一目了然;`baseline_score` 沿用现有命名以避免破坏现存 metrics.json 消费者(若有)。
- **D-OUT-03:** diff.txt 沿用现有 `_generate_diff()`,多 section 的 unified diff 自然拼接成单文件。零代码改动。Rationale:`_generate_diff` 已通过 `section_id` 遍历输出,joint mode 下多 section 同变是预期表现;拆文件改动会让 round-robin / joint 输出不一致。
- **D-OUT-04:** **不**修改 `evolution/tools/regression_dashboard.py`,**不**为 prompt run 接入仪表盘。仅保证 metrics.json 字段命名(`mode`、`joint_score`、`roundrobin_baseline_score`)对未来 dashboard prompt 方向扩展友好。Rationale:dashboard prompt 支持是 PMPT-V2 后期 phase 的范围(可能 Phase 22+);本期跨 phase 改造会拓 scope。

### Claude's Discretion
- joint mode 下 `PromptModule` 状态机的具体设计 — 用 `_active_section = "__ALL__"` 哨兵、新 `_joint_mode: bool` flag、还是分离的 `JointPromptModule` 子类,由 gsd-planner 在阅读 DSPy 文档与现有 `set_active_section()` 实现后决定。约束:不破坏现有 11 个测试用例;round-robin 路径 set/forward/get_evolved_sections 行为完全等价。
- joint mode 下 `forward()` 的具体实现 — 是把 5 section 文本 concat 成单一 frozen_context 再 selector(0 个 active),还是为 5 section 各启一个 Predict 串行调用合并 output。研究员需明确 GEPA reflection 能否在前一种模式下正确归因到 5 个 Predict 参数;若不行则走后一种。约束:joint 与 round-robin 的 forward 输入输出契约必须可被同一 `PromptBehavioralMetric` 评分。
- A/B baseline run 在 metrics.json / diff.txt / evolved_sections.json 中的存储位置 — 是与 joint run 同 `output/prompts/<ts>/` 共享一组文件(并存 `joint_*` 与 `roundrobin_baseline_*` 前缀),还是 `output/prompts/<ts>/baseline/` 子目录单独一份。Planner 决定,需考虑未来 dashboard 接入时的扫描复杂度。
- 软门 stdout 警告的精确文案、颜色规则。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / 需求
- `.planning/ROADMAP.md` §Phase 17 — Goal、Success Criteria、Depends on Phase 12
- `.planning/REQUIREMENTS.md` §PMPT-V2-01 — Joint section optimization 唯一需求项

### Phase 17 直接依赖的前置 CONTEXT
- `.planning/phases/08-prompt-module/08-CONTEXT.md` — `set_active_section()` API、`section_predictors` 与 `_frozen_instructions` 的双区设计、`named_parameters()` 可见性约束(D4 决策)
- `.planning/phases/09-prompt-evaluation/09-CONTEXT.md` — `PromptBehavioralMetric` per-section eval 模型
- `.planning/phases/10-prompt-constraints-cli/10-CONTEXT.md` — Growth check + role preservation 约束在 joint mode 下的复用

### Phase 16 同期模式参考(不直接依赖,但模式可类比)
- `.planning/phases/16-per-tool-regression-dashboard/16-CONTEXT.md` §D-13 — 软门 "warning + 不返 exit code" 的设计,本期 A/B 软门照搬
- `.planning/phases/16-per-tool-regression-dashboard/16-CONTEXT.md` §D-12 — schema 扩展 + persist helper 复用模式

### 现有实现锚点(planner / executor 必读)
- `evolution/prompts/prompt_module.py` — 完整 `PromptModule` 类,joint mode 在此扩展
- `evolution/prompts/evolve_prompt_sections.py` — 完整 CLI pipeline,joint pipeline 与 A/B baseline 在此扩展
- `evolution/prompts/prompt_dataset.py` — `PromptBehavioralDataset.to_dspy_examples(split, section_texts)`,joint mode 下需确认调用语义
- `evolution/prompts/prompt_metric.py` — `PromptBehavioralMetric`,joint forward 输出需可被同一 metric 评分
- `evolution/prompts/prompt_constraints.py` — `PromptRoleChecker` per-section 检查,joint mode 全 5 section 必须同时过

### DSPy 框架(researcher 查阅)
- DSPy GEPA 官方文档(researcher 通过 Context7 / WebFetch 拉取) — 多参数优化的 `max_metric_calls` 推荐公式;`named_parameters()` 可见性规则;reflection LM 行为

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PromptModule.section_predictors: dict[str, dspy.Predict]` — 已是字典结构,joint mode 下从 1 项扩到 5 项即可,`named_parameters()` 会自动遍历 dict 中所有 Predict
- `PromptModule._frozen_instructions: dict[str, str]` — joint mode 下可设为空 dict(全部上 active),无需删除该字段
- `evolve_prompt_sections.evolve()` — 已有 GEPA → MIPROv2 fallback 链(line 252-283),joint 与 round-robin 都能复用
- `_generate_diff()` — multi-section 输出自然支持,零改动
- `output_dir / "metrics.json"` 落盘逻辑(line 429-445) — 加 `mode` / `joint_score` / `roundrobin_baseline_score` 字段后兼容现有结构

### Established Patterns
- **持久化 helper 不可变模式**(Phase 13 `persist_per_tool_rates` / Phase 16 `persist_raw_predictions`):joint mode 的新字段不直接 mutate metrics dict,通过 helper 注入。本期可考虑新建 `evolution/prompts/prompt_metric.py:persist_ab_baseline(metrics: dict, joint_score: float, roundrobin_baseline_score: float, epsilon_pp: float) -> dict`(planner 决定是否值得 helper,小数据集可能直接 inline)。
- **软门 + stdout 警告模式**(Phase 13 警告、Phase 16 D-13 `--warning-threshold-pp`):本期 A/B 软门直接照搬。
- **Round-robin 循环风格**(line 213-283):for sid → set_active_section → GEPA.compile → fallback to MIPROv2。joint pipeline 是同一段去 for-loop。
- **Click + Rich 组合**:`@click.command()` + `@click.option()` + `Console().print(Table(...))`,与 Phase 1/5/13/15/16 完全一致。

### Integration Points
- `PromptModule.set_active_section()` ↔ joint mode 新方法:状态机需互斥(joint mode 后调 set_active_section 行为如何?planner 决:报错 / 自动退化为 round-robin / 静默切换)
- `dataset.to_dspy_examples(split, section_texts=section_texts)` ↔ joint mode 的 example filtering:joint 下不按 section_id filter,直接全量喂入;此处需确认 `section_texts` 参数在 joint 下的语义(planner 决)
- `ConstraintValidator._check_growth(evolved.text, original.text, "prompt_section")` ↔ joint mode 下 5 个 section 各跑一次 growth check,全部需 pass;现有循环已是 per-section,自然适配。
- `PromptRoleChecker.check_all(original_sections, evolved_sections)` ↔ joint mode 下 5 section 同时演化,checker 已是 list-based,自然适配。

</code_context>

<specifics>
## Specific Ideas

- 启动 stdout 预算预估行格式 D-IT-03 已给样例;细节(对齐、颜色)由 planner / executor 决定。
- A/B 软门警告文案:含 joint_score、roundrobin_baseline_score、delta(pp)三个数值,颜色为 Rich `[yellow]`,与 Phase 13/16 风格一致。
- `--mode` flag 帮助文档:`"Optimization mode: 'joint' (default, optimizes all sections simultaneously via GEPA) or 'round-robin' (legacy, optimizes section-by-section)."`

</specifics>

<deferred>
## Deferred Ideas

- **per-section growth_pct / delta_score 数组进 metrics.json** — 为未来 dashboard prompt 接入预留更细的字段,但本期不预先添加(YAGNI;dashboard 接入是 Phase 22+ 的事)。
- **dashboard 接入 prompt run** — `evolution/tools/regression_dashboard.py` 扩 `--prompt-runs` flag,扫描 `output/prompts/` 同模式渲染 LATEST/DIFF/TREND。属 PMPT-V2 后期 phase。
- **`--joint-iterations N` 单独 flag** — 让用户独立调 joint 与 round-robin baseline 的 budget。当前 `--iterations` 同步控制,YAGNI 至有需要拉开 budget 的场景出现。
- **A/B 硬门 + exit code** — 若未来 holdout 扩到 ≥50 例 / LLM-judge 方差降至 <0.5pp,可考虑 joint < roundrobin - epsilon 时 exit 2 阻断部署。当前条件不成熟。
- **`hybrid` mode**(joint warmup → round-robin fine-tune,或反之) — Click.Choice 留扩展空间,实现待后续 phase。
- **多种 GEPA `max_metric_calls` 公式** — `iterations × 50 × 5` 是起点;researcher 若查到更精确的多参数 budget 推荐(如 `iterations × 30 × n_params + 200`),planner 可微调。
- **Cross section 联动检查** — section A 演化影响 section B 的连贯性、Phase 18 的 personality drift detection 本身就是该方向;不属本期范围。

</deferred>

---

*Phase: 17-joint-section-optimization*
*Context gathered: 2026-05-15*
