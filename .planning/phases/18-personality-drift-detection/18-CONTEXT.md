# Phase 18: Personality Drift Detection - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

在已优化的 prompt section 上,新增一个 `DriftDetector` 约束层 — 对比 original (untouched hermes-agent prompt) vs evolved 文本在 **tone / formality / vocabulary / persona** 四个维度上的偏移。检测以 LLM-as-judge **pairwise** 方式给每维 0-1 漂移分数,基于 calibration 集 F1 最优化的 per-dim 阈值判定;**1 维超阈 = stdout 黄警告 + metrics.json 落盘但仍 deploy;2+ 维超阈 = constraint FAILED,evolved sections 写入 `output/prompts/FAILED_<ts>/` 不 deploy**。覆盖 ROADMAP §Phase 18 / PMPT-V2-02 的三条 Success Criteria。

**In scope:**
- 新增 `evolution/prompts/drift_detector.py`(或扩展 `prompt_constraints.py`,由 planner 决定 — 见 Claude's Discretion):`DriftDetector` 类,DSPy ChainOfThought + Pairwise Signature `(section_id, original_text, evolved_text) → (tone_score, formality_score, vocabulary_score, persona_score, explanation)`;评分语义统一为 0 = 无漂移 / 1 = 完全漂移。沿用 `PromptRoleChecker` 接口模式(`check(...) -> DriftResult` + `check_all(orig, evolved) -> list[DriftResult]`),返回 `ConstraintResult`-兼容 + drift-specific payload。
- **3-run averaging 仅在 final constraint gate 触发**:GEPA 内循环、Phase 17 A/B baseline run 完全不触发 DriftDetector。在 `evolve_prompt_sections.py` step 8c 之后(role check 之后)、step 9 (holdout) 之前,对每个 evolved section × 每维 跑 3 次 LLM judge,decision = `mean - 1·stdev > threshold[dim]`(保守 — 偏向 false negative)。joint mode 下 5 段 × 4 维 × 3 次 = **60 次 judge 调用**/run,只发生 1 次;round-robin 路径在每次写出 evolved 前同样跑一次(单段也照走全 4 维)。
- **30 例 drift-labeled calibration set,Synthetic LLM 生成(Phase 18 Task 1)**:新增 `evolution/prompts/drift_calibration.py`(`DriftCalibrationBuilder`),沿用 `PromptDatasetBuilder` 模式(DSPy Signature + Click subcommand 或 makefile target — planner 决)。对 5 个 hermes-agent prompt section 各生成 6 个变体(3 真漂移 + 3 无漂移)= 30 对。真漂移 prompt = "改写但显著改变 tone/formality/vocabulary/persona 之一";无漂移 prompt = "改写但保持语气和角色"。每对标注 ground-truth `is_drift: bool` + `drift_dim: tone|formality|vocabulary|persona|none`。落盘到 `datasets/prompts/drift_calibration.jsonl`,git 跟踪(便于复现 + 团队 review)。
- **F1-optimized threshold derivation**:Task 1 完成后,在 calibration set 上跑 DriftDetector → 对每维扫描 threshold ∈ [0.1, 0.9] step 0.05,选 F1 最优的 threshold,落盘到 `datasets/prompts/drift_thresholds.json`(per-dim: `{tone: 0.55, formality: 0.50, vocabulary: 0.45, persona: 0.65}` — 占位值,实际由 calibration 决定)。Phase 18 后续 phase 可手动 / quarterly 重跑这个 derivation step,但本期不做自动调度。
- **drift 报告输出**:
  - (a) **stdout Rich table** — `Section × Dim` 矩阵展示 mean/stdev/threshold/exceeded 状态,与 Phase 17 `Configuring optimizer` / `Evolution Results` 风格一致(`evolve_prompt_sections.py` 已有 Rich 导入)。
  - (b) **metrics.json 新增字段**(joint 与 round-robin 都写):`drift_per_dim: {<section_id>: {tone: {mean: 0.X, stdev: 0.X, exceeded: bool}, formality: {...}, ...}}` + `drift_max_dim: <highest scoring dim across all sections>` + `drift_exceeded_dims: [{section, dim}, ...]` + `drift_passed: bool` + `drift_thresholds: {tone: 0.55, ...}`(本次 run 使用的阈值快照,便于复现)。
  - (c) **单独 `drift_report.txt`**:per-section × per-dim 的 3 次 raw scores、mean、stdev、threshold、decision(pass/warn/reject)、explanation(LLM 最后一次 run 输出的解释 — 不存 3 个 explanation 避免文件膨胀);constraint FAILED 时也写入 `FAILED_<ts>/drift_report.txt`(便于事后排查)。
- **Bypass flag 明确不实现**:per PITFALL #6 prevention,**绝不**加 `--no-drift-check` / `--skip-drift-check` flag。用户想跳过只能通过 `--mode round-robin` 路径或修改源码(后者写在 docstring 警告)。但保留 `--drift-thresholds-path <path>` flag 允许指向自定义 thresholds.json(便于不同部署环境用不同阈值)。
- **测试**:
  - `tests/prompts/test_drift_detector.py`:DriftDetector 单元测(mock LLM 返回固定分数,验证 3-run averaging、mean-1stdev 决策、阶梯门判定逻辑、`check_all` 配对正确性)。
  - `tests/prompts/test_drift_calibration.py`:`DriftCalibrationBuilder` 生成 30 例(mock LLM)、F1 derivation 正确性、threshold persistence。
  - `tests/prompts/test_evolve_prompt_sections_cli.py` 扩展:drift gate 触发 FAILED 路径、1 dim 警告 + 仍 deploy 路径、metrics.json 含 drift_per_dim 字段。

**Out of scope:**
- **embedding-based 相似度 / cosine 距离作为额外信号** — 仅做 LLM-as-judge pairwise(per PITFALL #6 prevention #2)。引入 embedding 会增加依赖(sentence-transformers / OpenAI embedding API)且 LLM judge 已能 captured semantic drift。
- **运行期阈值自动调节 / online learning** — thresholds 是 calibration 时一次性 derive,落盘到 `drift_thresholds.json`,后续 run 直接读取。运行期不自动调。
- **DriftDetector 接入 GEPA 优化内循环作为 metric 信号** — drift 只是 gate,不参与 fitness score。GEPA 仍以 `PromptBehavioralMetric` 为唯一目标。理由:drift 反向作用于 fitness 会让 GEPA 学会绕过 drift 判官而非真正提升质量(Goodhart's law)。
- **A/B baseline (Phase 17 round-robin baseline run) 上跑 drift 检查** — A/B baseline 仅用于 score 对比,不输出 deploy artifact;额外跑 drift 是 ×2 成本但零收益。
- **per-section 可配置 dim 个数门禁**(e.g. DEFAULT_AGENT_IDENTITY 用 "任 1 维超 = reject" 而 PLATFORM_HINTS 用 "2+ 维超 = reject") — YAGNI,本期统一 1/2 阶梯。如未来发现 identity 漂移特别危险,后续 phase 加 per-section override。
- **Quarterly 重新 calibration 的自动化调度** — research 推荐的 cadence 是 process,不是代码;本期仅交付 `drift_calibration.py` 工具,何时重跑由 ops 决定。
- **bypass flag (`--no-drift-check`)** — 明确不做,见 In scope 描述。

</domain>

<decisions>
## Implementation Decisions

### Gate type & severity ladder
- **D-GATE-01:** 采用**阶梯门**:**1 维超阈 = stdout 黄警告 + metrics.json 记录 `drift_exceeded_dims` + `drift_passed: true` + 仍走 holdout deploy**;**2+ 维超阈 = `drift_passed: false` + constraint FAILED + evolved sections 写 `FAILED_<ts>/`、不 deploy**。Rationale:research PITFALL #6 prevention #4 推荐的混合门;1 维超阈往往是合理风格调整(formality 从严肃→轻松)而非真漂移,硬 reject 会让优化停滞;2+ 维同时超大概率是系统性人格偏移(identity → "Helpful AI assistant" 通用化)。ROADMAP success criteria 2 "reject… exceeding threshold" 在 operational 层面解读为 "2+ dim 超" = 真正的 exceeding。
- **D-GATE-02:** 阶梯门统一全部 5 个 section,**不**支持 per-section 阈值或 per-section 阶梯重定义。Rationale:YAGNI;若未来 identity 漂移特别危险,后续 phase 加 per-section override 即可。
- **D-GATE-03:** 软警告路径(1 dim 超)stdout 文案为 `[yellow]Drift warning: section '<sid>' dim '<dim>' = X.XX (threshold Y.YY) — review evolved text before deploying[/yellow]`,**不 exit 2**,**不阻断 evolved_sections.json 写盘**。与 Phase 17 D-AB-02 软门语义对齐。
- **D-GATE-04:** Hard reject 路径(2+ dim 超)stdout 文案为 `[red]Drift detected: section '<sid>' exceeded N dims [...] — REJECTED, evolved prompts NOT deployed[/red]`,然后 `metrics.json` 写 `constraints_passed: false` + `drift_passed: false`,evolved_sections.json 与 diff.txt 仍写到 `FAILED_<ts>/` 便于事后排查。Phase 17 现有的 FAILED 路径行为零改动。

### Calibration set construction (Phase 18 Task 1, 必须先于 DriftDetector 实现)
- **D-CAL-01:** **Synthetic LLM 生成 30 例 calibration set**(15 真漂移 + 15 无漂移),复用 `PromptDatasetBuilder` 的 DSPy Signature 模式。新增 `evolution/prompts/drift_calibration.py:DriftCalibrationBuilder`。Rationale:与现有 PromptDatasetBuilder 架构一致;成本可控(~30 次 LLM 调用 + ~30 次 ground-truth 标注);可复现(seed 固定);落盘后人工抽查后可手动修正再 git commit。风险已 prevention:同源偏误通过 ground-truth label + 后续人工 spot-check 缓解。
- **D-CAL-02:** Calibration set **落盘到 `datasets/prompts/drift_calibration.jsonl`** 并 git 跟踪。Rationale:与 v1/v2 dataset 落盘惯例不一致(`datasets/` 在 `.gitignore` 之 `datasets/**/*.jsonl` 排除),但 calibration set 是 **stable 评估资产**(类似 golden set),不是 run-time 生成的临时数据 — 必须 git 跟踪以保证 thresholds.json 可复现。**实施时确认 .gitignore exception**:在 `.gitignore` 加 `!datasets/prompts/drift_calibration.jsonl` exception 行。
- **D-CAL-03:** 30 例分布:**5 个 hermes-agent prompt section 各 6 个变体(3 真漂移 + 3 无漂移)**。Rationale:覆盖所有 section_id 让 threshold derivation 不偏向某段;5 × 6 = 30 与 research 建议数量精确对齐。
- **D-CAL-04:** Ground-truth 标签 schema:每对带 `is_drift: bool` + `drift_dim: tone|formality|vocabulary|persona|none`(无漂移时 `drift_dim: "none"`)。Rationale:多维标签让 per-dim F1 derivation 可行(per-dim threshold 必须有 per-dim ground truth);单维 `is_drift` 不足以 calibrate 4 个独立阈值。
- **D-CAL-05:** Phase 18 工期内**必须**完成 calibration set 生成 → F1 derivation → thresholds.json 落盘 → 单元测;不允许把 threshold 写死占位然后下期再校准。Rationale:research PITFALL #6 prevention #1 明确把 calibration 列为 Task 1 阻塞 DriftDetector code;跳过会立刻踩坑。

### Robustness (3-run averaging 应用范围)
- **D-ROB-01:** **3-run averaging 只在 final constraint gate 触发**(GEPA 内循环、A/B baseline 评估、calibration 都是 1-run)。Rationale:run-time 成本主要在 GEPA 反复调用,gate 调用是 1 次/run;3-run × 5 段 × 4 维 = 60 次/run 在可控范围(对应 ~$0.5-2 额外 cost);GEPA 内循环若也 3-run 会让 joint mode 总 LM 调用 ×3,实际开支 +$30-100/run 不可接受;calibration 是构建阶段,1-run + 后续人工 spot-check 已足。
- **D-ROB-02:** 决策规则:对每维独立运行 3 次 DriftDetector judge,取 3 个分数的 `mean` 与 `stdev`;**判定 `mean - 1·stdev > threshold[dim]` 则该维超阈**。Rationale:research PITFALL #6 prevention #3 推荐的保守判定(偏向 false negative,避免误杀有效优化);减 1·stdev 让噪声大的判官输出不易触发 reject(噪声越大 stdev 越大,门越宽松)。
- **D-ROB-03:** 3 次 LLM judge 之间**不重置 LM context / 不变 temperature seed** — 让 DSPy 默认行为产生 3 个独立调用样本。Rationale:重置 seed 会让 3 次 run 完全一致失去 averaging 意义;依赖 DSPy 默认的 stochastic LM 行为产生差异。temperature 不显式设置,沿用 config.eval_model 默认。
- **D-ROB-04:** Round-robin mode 与 joint mode 都触发 final constraint gate 的 3-run(单段优化不简化为 1-run)。Rationale:`evolve_prompt_sections.py --section <id>` 单点优化仍可能引入 dim 漂移,3-run 防噪同样适用;且代码路径统一便于维护。

### Drift report output schema
- **D-OUT-01:** stdout 输出 **Rich Table**:title `"Drift Detection (per-section × per-dim)"`,列 `Section`、`Dim`、`Mean`、`Stdev`、`Threshold`、`Exceeded`、`Status`,行按 section_id × dim 展开(5 × 4 = 20 行)。颜色规则:`exceeded` 列在 false 时绿色 ✓、true 时红色 ✗;`Status` 在 pass 时空、warn 时黄色 "WARN"、reject 时红色 "REJECT"。
- **D-OUT-02:** metrics.json 新增字段(joint 与 round-robin 都写):
  ```json
  {
    "drift_per_dim": {
      "<section_id>": {
        "tone": {"mean": 0.X, "stdev": 0.X, "exceeded": bool},
        "formality": {...},
        "vocabulary": {...},
        "persona": {...}
      },
      ...
    },
    "drift_thresholds": {"tone": 0.55, "formality": 0.50, "vocabulary": 0.45, "persona": 0.65},
    "drift_max_dim": "tone",
    "drift_max_section": "memory_guidance",
    "drift_exceeded_dims": [{"section": "skills_guidance", "dim": "formality"}, ...],
    "drift_passed": true|false
  }
  ```
  保留 Phase 17 已有的 `mode`、`joint_score`、`roundrobin_baseline_score`、`epsilon_pp`、`joint_vs_roundrobin_delta_pp` 等字段不变。Rationale:drift 字段命名前缀统一 `drift_*` 便于未来 dashboard 接入按前缀分桶;`drift_thresholds` 嵌入便于复现 — 不同 run 用不同 thresholds.json 时可在 metrics.json 自包含追溯。
- **D-OUT-03:** 单独 `drift_report.txt`(成功路径写 `output/prompts/<ts>/drift_report.txt`;FAILED 路径写 `output/prompts/FAILED_<ts>/drift_report.txt`)。内容是 markdown-style 段落,每个 section × dim 一段,含:`Mean`、`Stdev`、`Threshold`、`Decision (pass/warn/reject)`、`Raw scores: [r1, r2, r3]`、`Explanation`(只存第 3 次 LLM run 的 explanation 字段,避免 3× 文本膨胀)。Rationale:metrics.json 是机器消费;drift_report.txt 是人类 review 时的友好格式 — explanation 是 free-text 不适合塞 JSON。
- **D-OUT-04:** 与 Phase 17 共用 `output/prompts/<ts>/` 目录,**不**另起 `output/prompts_drift/`。Rationale:与 Phase 17 D-OUT-01 共目录策略一致;drift artifact 是 evolve 流程的一部分,不是独立 run。

### Bypass policy
- **D-BYPASS-01:** **不实现 `--no-drift-check` / `--skip-drift-check` flag**,per PITFALL #6 prevention 的硬性约束。Rationale:bypass flag 会让用户在 first false-positive 时永久 disable gate,defeat 整个 Phase 18 目的;若用户必须跳过(e.g. calibration set 出问题),只能 `--mode round-robin` + 手动 review evolved_sections.json,或修改源码(后者在 docstring 警告 "do not bypass without re-calibrating thresholds")。
- **D-BYPASS-02:** **允许 `--drift-thresholds-path <path>` flag**(默认 `datasets/prompts/drift_thresholds.json`)。Rationale:这是合理 ops 灵活性 — 团队可在不同 deploy 环境用不同阈值(staging 宽松、production 严格);不破坏 prevention(用户依然必须经过 calibration → derive threshold 流程,只是允许换 thresholds 文件)。Click.Option type=click.Path(exists=True)。

### Claude's Discretion
- `DriftDetector` 类的具体 Python 文件 — 新建 `evolution/prompts/drift_detector.py` 还是扩展 `evolution/prompts/prompt_constraints.py` 加 `DriftDetector` 类,由 gsd-planner 在阅读现有 `prompt_constraints.py` 后决定。约束:必须沿用 `PromptRoleChecker` 接口(`check_all(original_sections, evolved_sections) -> list[<some_result>]`),返回类型可以是 `ConstraintResult` 列表 + 同时返回 drift-specific `DriftDetailResult` payload(用于写 drift_report.txt),也可以是统一的 `ConstraintResult` 加 `details` 字段塞 JSON-encoded payload。planner 决。
- `DriftCalibrationBuilder` 的 CLI 入口形式 — 新建独立 `python -m evolution.prompts.build_drift_calibration` 子命令,还是作为 `evolve_prompt_sections.py` 的 `--build-calibration` 子模式,由 planner 决。前者更模块化便于 quarterly 重跑;后者用户路径少一个 entry point。
- 30 例 calibration set 的 LLM 生成 prompt(DSPy Signature 字段名、instruction 措辞) — 由 planner 根据 PromptBehavioralDataset Signature 模式撰写。约束:必须 deterministically reproducible(固定 seed 或显式 prompt 模板),且生成完成后须落盘 `seed`、`generator_model`、`generation_timestamp` 元字段以便复现。
- F1 derivation 的具体算法实现 — 暴力扫描 [0.1, 0.9] step 0.05 即可,~17 个候选点 × 30 例 = 510 次评估,~5 分钟;或用 sklearn `precision_recall_curve` 直接拿 optimal F1。planner 决,前者不引入新依赖。
- DriftDetector 在 evolve_prompt_sections.py 的精确插入位置(在 step 8b role check 之后、step 9 holdout 之前)— planner 在阅读现有代码后决定与 role check 的代码块顺序、共享 `original_map` 等局部变量的最简方式。
- 软警告 / 硬 reject 的 Rich 颜色微调与 emoji 用法 — planner / executor 美学决定,与 Phase 13/16/17 stdout 风格保持一致即可。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / 需求
- `.planning/ROADMAP.md` §Phase 18 — Goal、Success Criteria、Depends on Phase 17
- `.planning/REQUIREMENTS.md` §PMPT-V2-02 — Personality drift detection 唯一需求项

### Phase 18 直接依赖的前置 CONTEXT
- `.planning/phases/10-prompt-constraints-cli/10-CONTEXT.md` — `PromptRoleChecker` 接口模式(D2)、约束门禁顺序(D4)— DriftDetector 沿用相同接口与门禁位置
- `.planning/phases/09-prompt-evaluation/09-CONTEXT.md` — `PromptBehavioralMetric` 与 PromptDatasetBuilder 模式 — calibration builder 复用此模式
- `.planning/phases/17-joint-section-optimization/17-CONTEXT.md` — joint vs round-robin pipeline 拓扑、metrics.json schema(D-OUT-02)、软门 + 共目录(D-OUT-01/02)— Phase 18 drift 字段必须兼容 Phase 17 schema,共目录策略一致

### 研究锚点(researcher 与 planner 必读)
- `.planning/research/PITFALLS.md` §Pitfall 6 (lines 197-230) — Phase 18 校准失败的所有 prevention 已在此明确,本期决策直接照搬 prevention #1-6;若 planner 想偏离 prevention 必须在 PLAN.md 提供反证
- `.planning/codebase/CONCERNS.md` §M2 (silent GEPA→MIPROv2 fallback,lines 114-128) — DriftDetector 不接入 GEPA,但 calibration builder 若启用 GEPA 优化需注意 M2
- `.planning/codebase/CONCERNS.md` §M4 (LLM-output parsing brittleness,lines 146-162) — DriftDetector 解析 4 个 OutputField 时需 prefer `dspy.OutputField(type=float)` 强类型,而非手动 `_parse_score` 0.5 fallback

### 现有实现锚点(planner / executor 必读)
- `evolution/prompts/prompt_constraints.py` — 完整 `PromptRoleChecker` 类,DriftDetector 沿用同接口(`check_all(original, evolved) -> list[ConstraintResult]`);_parse_bool helper 模式可参考
- `evolution/prompts/evolve_prompt_sections.py` lines 466-529 — step 8 constraint validation pipeline,DriftDetector 插入位置在 8b (role check) 之后;`all_pass = False` 累加 + FAILED_<ts>/ 写盘逻辑保留
- `evolution/prompts/prompt_dataset.py` — PromptDatasetBuilder + PromptBehavioralDataset 模式,DriftCalibrationBuilder 沿用此模式(DSPy Signature + JSONL 持久化)
- `evolution/prompts/prompt_loader.py` — `extract_prompt_sections` 返回的 `PromptSection` 列表,calibration 生成需基于此提取 5 个 section 作为原料
- `evolution/core/constraints.py` — `ConstraintResult` dataclass,DriftDetector 输出兼容
- `evolution/core/config.py` — `EvolutionConfig` 与 `get_lm_kwargs()`,DriftDetector LM 调用复用现有 backend 配置;若需新增 `drift_thresholds_path` 字段需加进 EvolutionConfig

### DSPy 框架(researcher 查阅)
- DSPy ChainOfThought / Signature 文档 — pairwise judge signature 的输入/输出最佳实践;`dspy.OutputField(type=float)` 在 DSPy 3.x 的支持范围(CONCERNS §M4 提到的 typed outputs 是否可用)
- DSPy LM 的 stochastic 行为 — 3-run averaging 依赖 LM 默认 sampling(researcher 验证 temperature 默认是否产生足够差异)

### 配置 / Lockfile
- `.gitignore` — 须在 D-CAL-02 实施时新增 `!datasets/prompts/drift_calibration.jsonl` exception 行;现有 `datasets/**/*.jsonl` 通配会默认拒绝 calibration set

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PromptRoleChecker` (evolution/prompts/prompt_constraints.py lines 32-147) — 完整 LLM-as-judge + DSPy ChainOfThought + ConstraintResult 模式,DriftDetector 几乎可平移结构(改 Signature 字段、改 `check` 返回多维分数、改 `check_all` 聚合)
- `_parse_bool` helper (prompt_constraints.py lines 15-29) — 类似 helper 可加 `_parse_float_score(value, default=0.5) -> float`,clamp 到 [0, 1],若 D-OUT-02 用 `dspy.OutputField(type=float)` 则 helper 可省
- `PromptBehavioralMetric` + `PromptDatasetBuilder` (prompt_metric.py + prompt_dataset.py) — calibration builder 直接复用 builder 接口签名与 JSONL 持久化(`PromptBehavioralDataset.save/load`)
- `evolve_prompt_sections.py` step 8(lines 466-529)constraint validation 块 — DriftDetector 插入处仅需 1 个新调用 + 累加到 `all_constraint_results`;`if not all_pass: FAILED_<ts>` 逻辑零改动
- `output/prompts/<ts>/` 目录布局(evolve_prompt_sections.py lines 752-816) — 新增 `drift_report.txt` 与现有 `evolved_sections.json` / `metrics.json` / `diff.txt` 平级即可

### Established Patterns
- **LLM-as-judge + ChainOfThought + ConstraintResult**(Phase 5 ToolFactualChecker、Phase 10 PromptRoleChecker)— DriftDetector 第三个实例化
- **持久化 helper 接受 dict + 注入新字段**(Phase 13 `persist_per_tool_rates`、Phase 17 D-OUT-02 metrics.json 新增字段块)— Phase 18 metrics.json drift_* 字段可直接 inline 添加(field 数量不算多),或抽 `persist_drift_metrics(metrics: dict, drift_per_dim, thresholds, ...) -> dict` helper 由 planner 权衡
- **软门 + stdout 警告 + 仍 deploy**(Phase 17 D-AB-02、Phase 16 D-13)— D-GATE-03 1-dim 软警告路径直接照搬
- **`output/prompts/<ts>/` 共享目录区分通过 metrics.json 字段**(Phase 17 D-OUT-01)— Phase 18 drift artifact 不另起新 root,通过 `drift_passed` 字段分桶
- **30 例 calibration set 的 LLM 合成 + JSONL 落盘 + git 跟踪**(类似 Phase 9 80 例 behavioral dataset,Phase 17 沿用)

### Integration Points
- `PromptRoleChecker.check_all` ↔ `DriftDetector.check_all`:两者都在 evolve_prompt_sections.py step 8 调用,可在 planner 阶段决定是抽公共 `apply_section_checker(checker, original_sections, evolved_sections, results, ...)` helper,还是平铺两次调用(本期推荐平铺,YAGNI)
- `EvolutionConfig` ↔ `--drift-thresholds-path` flag:Click option 通过 `--drift-thresholds-path` 传入,在 `evolve()` 早期(extract sections 之后、optimizer 之前)读取 thresholds 文件 → 传给 DriftDetector 构造器;EvolutionConfig 可新增 `drift_thresholds_path: Optional[Path] = None` 字段(可选,planner 权衡是否需要写进 config)
- `metrics.json` schema ↔ Phase 17 已有字段:Phase 18 新增字段全部以 `drift_*` 前缀,不与 Phase 17 字段冲突;`constraints_passed: bool`(已存在)与 `drift_passed: bool`(新增)互不取代 — `constraints_passed = growth_passed AND role_passed AND drift_passed`(在 step 8c 终结后聚合)
- `_generate_diff()` ↔ drift gate:diff.txt 仍由 evolve 后期生成,与 drift 检查解耦;若 drift 触发 FAILED,diff.txt 仍在 FAILED_<ts>/ 生成便于事后排查"为什么 reject"

### Risk Anchors (Pre-execution)
- **同源偏误**(Synthetic LLM 生成 calibration set + LLM-as-judge DriftDetector,二者可能"共同犯错"使 F1 虚高)— planner 在 PLAN.md 必须明确人工 spot-check 步骤(抽 10 例由用户 review,不通过则重生成);Phase 18 verify 阶段也必须验证 thresholds 在新合成 30 例上 F1 ≥ 0.8(在 calibration set 自身上 F1 ≥ 0.85),不达标则 PLAN 需返工
- **DSPy 3.x typed OutputField**(CONCERNS §M4)— planner / researcher 必须确认 `dspy.OutputField(type=float)` 在当前 DSPy 版本可工作;不行则回退到 `_parse_float_score` helper(0.0 fallback 而非 0.5,per M4 prevention)
- **3-run averaging 的 stochasticity 依赖**(D-ROB-03)— 若 DSPy LM 默认 temperature=0,3-run 完全一致失去 averaging 意义;researcher 必须确认 config.eval_model(openai/gpt-4.1-mini)在 DSPy 默认配置下 temperature ≠ 0,否则需在 DriftDetector 内显式 `dspy.LM(..., temperature=0.7)` 覆盖

</code_context>

<specifics>
## Specific Ideas

- Calibration set 文件路径:`datasets/prompts/drift_calibration.jsonl` + `datasets/prompts/drift_thresholds.json`(并存,前者是数据、后者是 derive 后的产物)。
- Threshold derivation 默认扫描范围 [0.1, 0.9] step 0.05(17 候选点),per-dim 独立 F1 最优。
- 30 例分布:5 sections × 6 variants = 30 对,每段固定 3 真漂移 + 3 无漂移。
- 3 个真漂移 variant 的 LLM prompt 模板示意:`"改写以下 prompt section,显著改变 {tone|formality|vocabulary|persona} 但保持其他维度不变"`(per-dim 各 1 个,确保每维有标注样本)。
- 3 个无漂移 variant 的 LLM prompt 模板示意:`"改写以下 prompt section,改善流畅度或精简表达,但完全保持原有的 tone、formality、vocabulary、persona"`。
- Rich Table title 推荐:`"Drift Detection (per-section × per-dim, 3-run averaged)"`,与 Phase 17 `"Evolution Results"` 字符长度相近便于终端对齐。
- D-OUT-02 metrics.json 字段命名前缀统一 `drift_*`,与 Phase 17 `joint_*` / Phase 16 `per_tool_*` 风格一致,未来 dashboard 接入按前缀分桶。
- 软警告颜色 `[yellow]`、硬 reject 颜色 `[red]`,与 Phase 13/16/17 stdout 风格一致。

</specifics>

<deferred>
## Deferred Ideas

- **Embedding-based 相似度作为额外 drift 信号** — 不与 LLM-judge 互斥,可作为 Phase 19+ 或 v2.x 后期增强。引入 sentence-transformers / OpenAI embedding API 是新依赖。
- **per-section 阈值 / per-section 阶梯重定义**(e.g. DEFAULT_AGENT_IDENTITY 用任 1 维超 reject,PLATFORM_HINTS 用 3+ 维超 reject)— YAGNI,本期统一 1/2 阶梯;若运行后发现 identity 漂移特别危险或 platform_hints 误杀严重,后续 phase 加 per-section override。
- **运行期阈值在线 / online learning** — calibration 是一次性 derive,后续 quarterly 由 ops 手动重跑;自动调度不在本期。
- **DriftDetector 接入 GEPA 优化内循环作为 secondary fitness signal** — 引入会让 GEPA 学会"通过 drift 判官的应试技巧"(Goodhart's law)而非真正提升质量;保持 drift 仅为 gate。
- **A/B baseline(Phase 17 round-robin baseline run)上跑 drift 检查** — A/B baseline 不输出 deploy artifact,跑 drift 无意义;`output/prompts/<ts>/roundrobin_baseline_evolved_sections.json` 即使 drift 异常也不会 deploy。
- **`drift_report.json` 结构化输出**(对应 D-OUT-03 选项 d)— metrics.json + drift_report.txt 已覆盖机器+人类两类消费者;若未来 dashboard 接入需要结构化 drift_report,届时再加 .json 镜像。
- **Phase 18 quarterly 自动重新 calibration** — research PITFALL #6 prevention #6 提到 cadence,但属 process / ops 责任,本期仅交付 `drift_calibration.py` 工具。

### Reviewed Todos (not folded)

cross_reference_todos 找到 6 个 score ≥ 0.2 的 todo,本期均未折叠(score 都低于自动折叠阈值 0.4 或与本期 scope 无强匹配):
- `2026-05-07-enforce-readonly-hermes-agent.md` (score 0.4) — hermes-agent 写保护门禁,本期 DriftDetector 不写回 hermes-agent,无强相关
- `2026-05-07-harden-llm-output-parsing.md` (score 0.4) — LLM 输出解析鲁棒性,CONCERNS §M4,已作为 Risk Anchor 在 code_context 中标注;若 planner 决定使用 `dspy.OutputField(type=float)` 则间接缓解,但不在 Phase 18 主线 scope
- `2026-05-07-add-lockfile-dspy-pin.md` (score 0.2) — 依赖锁定,不在本期 scope
- `2026-05-07-expand-secret-patterns.md` (score 0.2) — Phase 14 SessionDB 范围,不在本期 scope

</deferred>

---

*Phase: 18-personality-drift-detection*
*Context gathered: 2026-05-15*
