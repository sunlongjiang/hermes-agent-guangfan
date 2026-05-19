# Phase 20: Benchmark-Gated Validation - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

为 `evolve_prompt_sections.py` pipeline 末端新增一个 **opt-in TBLite 终极门 (final-only gate)**：所有 in-loop 校验通过(constraints + Phase 18 drift)后,候选 evolved sections 跑一次 TBLite 分层子集(stratified ~30 tasks 跨 4 tier)与 anchor baseline + moving-average 比较,基于 1.96σ 置信区间 + tier-weighted Risk_Score 决定 accept/reject。Gate 在 GEPA 循环 **之外**(PITFALL #7 硬约束),opt-in 默认关闭,无显式 `--no-benchmark` 旁路 flag。

落地三件事:
1. **`evolution/benchmarks/` 新包**: `tblite_runner.py`(subprocess 包装) + `benchmark_gate.py`(constraint-style 验证器 + Risk_Score 计算) + `build_tblite_calibration.py`(独立 CLI 构造 anchor)。
2. **`evolve_prompt_sections.py` 新 flag**: `--benchmark={none,tblite}` (默认 `none`) + `--benchmark-cache/--no-benchmark-cache` + `--wait/--detach` + `--benchmark-tier <csv>` 子集筛选。
3. **Soft-Rollback 机制**: gate fail = `FAILED_<ts>/`(write-back 未发生);gate 过但后台 full-verify regression = 自动 snapshot 当前到 `~/.hermes/backups/<ts>/` + 回退到 `last_known_good` + 挂起 `logs/regression.jsonl` 等人工核验。

**Phase 20 仅落 prompt-domain gate**:
- PMPT-V2-03 在 REQUIREMENTS.md 归属 "Prompt Evolution Enhancements",`evolve_tool_descriptions` / `evolve_skill` 不在本期范围。
- 评估对象 = evolved prompt sections,benchmark 信号 = TBLite task pass_rate per tier。
- 不引入新外部依赖(subprocess + stdlib + 已有 DSPy/Click/Rich)。

**In scope:**
- 新建 `evolution/benchmarks/` 包(`__init__.py`、`tblite_runner.py`、`benchmark_gate.py`、`build_tblite_calibration.py`)
- `evolve_prompt_sections.py` step 10 之后、step 11(write-back) 之前插入 benchmark gate
- Virtual Prompt Overlay 注入机制(symlink swap + snapshot/restore;file-level 实现,planner 决定 symlink/atomic-mv)
- Async Stream Pipe + State Monitor for subprocess(stdout/stderr 非阻塞 read + heartbeat,`--wait` 阻塞或 `--detach` 后台两种 CLI mode)
- Stratified ~30 tasks 子集(per-tier 代表性 task 白名单 + 固定 seed 可重现)
- 后台 async full-verify(完整 100 tasks)+ Soft-Rollback 自动回退路径
- Content-Addressed cache(`~/.cache/hermes-evolution/tblite/<artifact-hash>/`,key 含 HuggingFace dataset commit hash)
- Dual-Track Budget: `max_cost_usd`(优化主路,保留) + `benchmark_max_cost_usd`(新增,默认 50.0)+ Pre-flight Watermark(预估 cost × 3 硬性预检)
- Explicit Anchor Calibration via `python -m evolution.benchmarks.build_tblite_calibration`(mandatory pre-flight check 同 Phase 18 D-CAL-05)
- `datasets/prompts/tblite_anchor.json` git 跟踪 + `.gitignore` exception(mirror Phase 18 D-CAL-02)
- 输出 `output/prompts/<ts>/tblite_report.json`(per-task breakdown + per-tier σ + Risk_Score + decision rationale)
- 测试: `tests/benchmarks/test_tblite_runner.py`(mock subprocess + parse samples.jsonl)、`test_benchmark_gate.py`(Risk_Score 算法 + tier weight + 1.96σ 决策)、`test_build_tblite_calibration.py`(anchor 生成 + 持久化)

**Out of scope:**
- **TBLite 在 GEPA 内循环作为 fitness signal** — PITFALL #7 prevention #1 硬约束;benchmark 只是 final gate,不参与 metric。
- **`evolve_tool_descriptions` / `evolve_skill` 接 `--benchmark`** — PMPT-V2-03 仅指 prompt domain;tool/skill domain 未来若需要再开新 phase。
- **YC-Bench / 完整 TerminalBench2 集成** — PROJECT.md Out-of-Scope 已明确;TBLite 是 TB2 校准过的快子集。
- **per-iteration 跑 benchmark** — 仅 final candidate,不每个 GEPA candidate 都触发。
- **Quarterly 自动重 calibration 调度** — 本期仅交付 `build_tblite_calibration` 工具,何时重跑由 ops 决定(同 Phase 18 D-CAL-05 思路)。
- **`--no-benchmark` 旁路 flag** — Phase 18 D-BYPASS-01 同策略;opt-in 默认 OFF 即为天然 bypass,无需双重 flag。
- **HuggingFace dataset revision pin** — cache fingerprint 读 dataset commit hash 用于 invalidate;不固定 dataset 版本(让上游更新自然 invalidate cache 重跑)。
- **三层 PII 审计(NER + LLM 数据集审)** — 同 Phase 19 D-23/D-25 思路,本期不引入(本期 benchmark 不挖矿,无新 PII surface)。
- **自动 PR 提交 / merge** — PROJECT.md Out-of-Scope,本期仍 `output/` + Soft-Rollback,需人工 review。

</domain>

<decisions>
## Implementation Decisions

### D1 Regression 判定语义 — Adaptive Sliding Window + Tier-Wise Weighted Gating

- **D-01:** **Baseline 策略 = Adaptive Sliding Window**:`pass = candidate_score >= max(anchor_baseline, moving_avg) - 1.96·σ`。anchor = untouched hermes-agent 一次性 calibration 时建立(`datasets/prompts/tblite_anchor.json`),moving_avg = 历次 accepted evolved 的 running 均值(从 `output/prompts/tblite_history.json` 读最近 N=10 条 accepted)。σ 取 candidate-side 3-run stdev(per-tier 各算各的)。**首次 evolve --benchmark** 时 moving_avg 不存在,以 anchor 为退化值(`moving_avg = anchor`)。

- **D-02:** **Aggregation = Tier-Wise Weighted Gating + Gradient-Weighted Blocking**:per-tier 独立 1.96σ 置信区间检查 → `breach_flag[t] ∈ {0,1}`。**Risk_Score = Σ (tier_weight[t] × breach_flag[t])**,默认权重 `{easy: 1.0, medium: 1.5, hard: 2.0, extreme: 4.0}`,**Reject 阈值 = 4.0**。语义:extreme 单 breach (权 4.0) → 单点致命直达阈;低阶 tier 累积 breach (e.g. easy+medium+hard = 4.5) → 累积失效也达阈。双重防御。权重/阈值通过 `EvolutionConfig` 字段暴露可调。

- **D-03:** **Median-of-N 候选侧 = 3-run**:每个 candidate × 每个 tier × 3 runs;mean 与 σ 都从这 3 runs 算。3-run averaging **仅在 Phase 20 final gate** 触发(同 Phase 18 D-ROB-01;GEPA 循环内不调用 TBLite)。

- **D-04:** **Decision rationale 落 `tblite_report.json`**: `{per_tier: {<tier>: {scores: [r1,r2,r3], mean, stdev, threshold, anchor, moving_avg, breach}}, risk_score: float, reject_threshold: 4.0, weights: {...}, decision: "accept" | "reject", reason: <自然语言>}`。 metrics.json 同时写 `benchmark_passed: bool` + `benchmark_risk_score: float` + `benchmark_per_tier: {...}` + `benchmark_decision: "accept" | "reject" | "skipped"`。

### D2 TBLite 子集策略 — Stratified Fast Subset + Async Full Verify

- **D-05:** **默认 stratified subset = ~30 tasks**:per-tier 代表性 task 白名单(easy:12 / medium:8 / hard:7 / extreme:3,共 30,**所有 4 tier 都有样本以保 Risk_Score 计算的完整性**)。白名单 + seed 固定在 `datasets/prompts/tblite_stratified_subset.json` git 跟踪(同 anchor 的 .gitignore exception 策略);可通过 `--benchmark-tier easy,medium,hard,extreme` CSV 子选其中部分 tier(默认 4 tier 全启用)。

- **D-06:** **`--benchmark-full` flag** 切到完整 100 tasks(严谨验证场景),不走 stratified subset。`--benchmark-full` 与 `--detach` 组合最常用(后台跑全量)。Full-run anchor 与 stratified-run anchor 独立校准,各自 `tblite_anchor_full.json` 与 `tblite_anchor_stratified.json` 不互通。

- **D-07:** **Gate 过 + write-back 之后,自动启动后台 async full verification**(默认行为,可 `--no-async-full-verify` 关)。Detached subprocess + `output/prompts/<ts>/.benchmark_full_running.pid` lock + 完成后写 `tblite_full_report.json`。`evolve_prompt_sections --check-benchmark <ts>` 子命令查询完成状态/拉结果。

- **D-08:** **Async Full Regression → Soft-Rollback**:async full Risk_Score >= 4.0 触发:(a) `~/.hermes/backups/<ts>/prompt_builder.py` snapshot 当前 production 版本;(b) restore `last_known_good`(从 `output/prompts/tblite_history.json` 读最近 1 条 accepted-and-verified 状态);(c) append `logs/regression.jsonl`(项目根目录 `logs/`,gitignored)记录 commit_id + 旧/新 Risk_Score + restore 路径,**pending human review**(人工核验后通过 `evolve_prompt_sections --restore <ts>` 反向恢复或 `--confirm-rollback <ts>` 永久保留 rollback)。

### D3 evolved sections 注入 TBLite 机制 — Virtual Prompt Overlay + Async Stream Pipe

- **D-09:** **Virtual Prompt Overlay (Symlink Overwrite,file-level 变体)**:Phase 20 不直接修改 `hermes-agent/agent/prompt_builder.py`。流程:
  1. snapshot 原 `prompt_builder.py` 到 `~/.hermes/tmp/benchmark_<ts>/prompt_builder.py.original`
  2. 写入 evolved 版本到 `~/.hermes/tmp/benchmark_<ts>/prompt_builder.py.evolved`
  3. **原子替换**(planner 决定: file-level symlink 还是 `os.replace` atomic mv):`hermes-agent/agent/prompt_builder.py` ← evolved 版本
  4. 启动 TBLite subprocess(`tblite_env.py evaluate ...`)
  5. subprocess 退出 / gate 失败 → 用 snapshot restore 回 `prompt_builder.py.original`
  6. gate 过 → keep evolved + 把 evolved 版本 promote 到 history ledger(`tblite_history.json` 新 entry,含 commit_id placeholder)。

  **零复制**:不复制完整 hermes-agent 仓库(几百 MB),只动 prompt_builder.py 这一个文件。**原子级切换**:用 `os.replace`(POSIX rename atomic)或 symlink swap 保证 in-flight TBLite worker 不会看到 half-written state。**物理隔离**:tmp dir 在 `~/.hermes/tmp/`,backups 在 `~/.hermes/backups/`,evolution 项目仓不污染 hermes-agent。

- **D-10:** **Pre-flight overlay sanity check**:`build_tblite_calibration` 与 `evolve_prompt_sections --benchmark=tblite` 启动时先 dry-run overlay:确认 (a) hermes-agent 路径写权限存在,(b) `~/.hermes/tmp/` + `~/.hermes/backups/` 可写,(c) 同一 hermes-agent 没有未提交修改(`git status --porcelain` empty)防止意外覆盖人工正在编辑的 prompt_builder.py。任一失败 → `raise SystemExit(1)` + 明确错误。 **CONCERNS §M6 (hermes-agent 未强制只读) 直接相关**:Phase 20 是第一个 deliberate 多步骤 write-restore 路径,需要 transactional 保证。

- **D-11:** **Async Stream Pipe + State Monitor for TBLite subprocess**:`subprocess.Popen(args, stdout=PIPE, stderr=PIPE, bufsize=1)` + daemon thread 非阻塞读 stdout/stderr。stdout 行实时解析(TBLite 写 `[START]task_name`/`[PASS]task_name`/`[FAIL]task_name` 标记 + tqdm 行)。**heartbeat detection**:60 秒内无新 stdout 行 → 视为 hang,Rich console 黄警告 + 计 hang_count;hang_count >= 3 → `SIGTERM` + 写 `TBLITE_HANG_<ts>/`(不 Soft-Rollback,因 overlay 还在 restore 路径上)。

- **D-12:** **`--wait` / `--detach` CLI mode**:
  - **`--wait`**(默认): evolve_prompt_sections 阻塞等 TBLite subprocess 退出,Rich Live Table 实时显示 `已完成 X/30 tasks,已耗 Y 分,~ETA Z 分`。subprocess 退出后立即 gate 判定 → write-back 或 FAILED_。
  - **`--detach`**: evolve_prompt_sections 启动 detached subprocess 后立即返回(打印 ` benchmark_run_id`),evolved sections 写入 `output/prompts/<ts>/.pending_gate.json`。`evolve_prompt_sections --check-benchmark <ts>` 子命令完成 gate 判定 + write-back / FAILED。两 mode 共享 same gate 算法,仅 orchestration 不同。

### D4 Calibration + Cache + Cost Cap — Explicit Anchor + Content-Addressed + Dual-Track Budget

- **D-13:** **Explicit Anchor Calibration via 独立 CLI 子命令** (mirror Phase 18 D-CAL-01):新增 `python -m evolution.benchmarks.build_tblite_calibration`(Click + Rich)。功能:跑 untouched hermes-agent × 3 runs × stratified subset → 算每 tier mean + σ → 落 `datasets/prompts/tblite_anchor.json`(schema: `{anchor_per_tier: {<tier>: {mean: float, stdev: float, n: int=3, scores: [r1,r2,r3]}}, dataset_revision_hash: str, hermes_agent_commit: str, calibration_timestamp: str}`)。git 跟踪 + `.gitignore` 加 `!datasets/prompts/tblite_anchor.json` exception(同 Phase 18 D-CAL-02)。 **Phase 20 工期内必须完成 calibration**(同 Phase 18 D-CAL-05 思路,不允许 placeholder)。

- **D-14:** **Pre-flight Anchor Existence Check**(mandatory):`evolve_prompt_sections --benchmark=tblite` 启动时 `check_anchor_existence()` 校验 `datasets/prompts/tblite_anchor.json` 存在 + `hermes_agent_commit` 与当前 hermes-agent commit 匹配(漂移则 `raise SystemExit(1)` 引导重 calibration)。**漂移容忍**:dataset_revision_hash 不匹配可降级到 warn(同 dataset version,可继续);hermes_agent_commit 不匹配硬 fail(因为 anchor 是基于具体 prompt baseline,prompt 变就 baseline 无效)。

- **D-15:** **Content-Addressed Cache (默认开)**:cache_dir = `~/.cache/hermes-evolution/tblite/`,key = `sha256(canonical_json(evolved_sections) + dataset_revision_hash + stratified_subset_seed + tblite_runner_version)[:16]`。命中 → 跳过 subprocess,直接读 cache `result.json` + `samples.jsonl`。`dataset_revision_hash` 走 `huggingface_hub.HfApi().dataset_info("NousResearch/openthoughts-tblite").sha`(或同等 API)取上游 dataset commit。**零维护、零过期误报**:上游更新 dataset → revision_hash 变 → cache 自动失效。 `--no-benchmark-cache` 可禁用单次。 cache 内容寻址不过期。

- **D-16:** **Dual-Track Decoupled Budget**:
  - `EvolutionConfig.max_cost_usd`(默认 20.0,Phase 13 引入)保留管优化主路(GEPA + LLM judge)。
  - **新增 `EvolutionConfig.benchmark_max_cost_usd`(默认 50.0)** 专属 TBLite subprocess + Modal compute + OpenRouter inference。
  - 两个独立 `CostTracker` 实例,**互不污染**。
  - metrics.json 写 `total_cost_breakdown: {optimization: <usd>, benchmark: <usd>}` 双轨账单(便于 Phase 16 dashboard 接入按前缀分桶)。

- **D-17:** **Pre-flight Watermark Check**:subprocess 启动前估算单次 cost = (per-task LLM cost × num_tasks × num_runs)。**水位 = 预估 cost × 3** 硬性余额预检 vs `benchmark_max_cost_usd - already_spent`。水位低于硬阈 → `raise SystemExit(1)` 提示用户增加 `--benchmark-max-cost` 或减 `--benchmark-tier`。默认 per-task cost 假设(`config.tblite_estimated_cost_per_task_usd=0.4`,可调)用户首次 calibration 时由 `build_tblite_calibration` 实测后回写。

- **D-18:** **`evolve_prompt_sections.py` 集成点**:benchmark gate 插在 step 10(Report results)之后、step 11(Save results)之前。当前 step 11 包含 evolved_sections.json 持久化 + (隐式)write-back 路径。Phase 20 重组:
  - **新 step 10.5 (benchmark gate)**: 若 `benchmark != "none"`,运行 Virtual Prompt Overlay → TBLite subprocess → Risk_Score → accept/reject。
  - reject → 走 Phase 18 D-GATE-04 风格 `FAILED_<ts>/` 路径(已存在),metrics.json 加 `benchmark_passed: false` + `benchmark_risk_score` + `benchmark_reason`。
  - accept → 走 step 11 + 追加 history ledger entry + 启动 async full verify(若 `--no-async-full-verify` 不传)。
  - 若 `benchmark == "none"`(默认) → 不触发 gate,metrics.json 写 `benchmark_decision: "skipped"`,行为 = pre-Phase-20 完全一致。

### Claude's Discretion

- `evolution/benchmarks/__init__.py` 是否做 lazy import 防 ImportError(无 TBLite 时 evolve_prompt_sections 仍可跑;同 Phase 21 `evolution/code/__init__.py` 模式)
- Virtual Prompt Overlay 具体实现:file-level symlink 还是 `os.replace` atomic mv(planner 在阅读 hermes-agent prompt_builder.py 结构后决,POSIX rename 已足够 atomic)
- TBLite subprocess 命令行精确构造:`bash run_eval.sh --config default.yaml --env.task_filter <stratified_csv>` 还是 `python tblite_env.py evaluate --config ... --env.task_filter ...`(planner 测试两路 + 选稳的)
- TBLite output 解析 helper:tail `samples_<ts>.jsonl` per-line 解析 `{task_name, passed, ...}` 还是 evaluate 退出后 batch read(planner 决,Async Stream Pipe 偏向 per-line)
- `stratified subset` 30 tasks 白名单的具体 task name 选择:可参考 TBLite README 数据集 + Claude Haiku 4.5 reference pass rate 分桶,每 tier 选最具区分度的 N tasks(planner 实际从 dataset 读 task 名再抽样)
- tier weight {easy:1, medium:1.5, hard:2, extreme:4} 与 reject threshold 4.0 的精确数字:计划在 calibration 步落地,允许 ±10% 调参(暴露 `EvolutionConfig` 字段)
- `logs/regression.jsonl` 与 `~/.hermes/backups/<ts>/` 的精确 schema(commit_id placeholder 怎么填、是否走 git stash 还是裸 file copy)
- `evolve_prompt_sections --check-benchmark <ts>` / `--restore <ts>` / `--confirm-rollback <ts>` 这些子命令的 Click subcommand vs flag 形式
- HuggingFace API 获取 dataset_revision_hash 的具体调用(`HfApi().dataset_info` vs `huggingface_hub.snapshot_download` metadata)
- `last_known_good` 的具体定义:`tblite_history.json` 最近 1 条 `accepted: true AND async_full_verify: passed` 还是只看 gate accepted
- `tblite_estimated_cost_per_task_usd` 实测回写策略:每次 calibration 都更新还是手动 ops 决定
- Rich Live Table 的列设计(任务名 / status / elapsed / tier)与 `--wait` mode 下的 ETA 算法
- `--detach` mode 下 evolved_sections 怎么 staging(临时 evolved_sections.json 在 `output/prompts/<ts>/.pending_gate.json` vs `output/prompts/.pending/<ts>.json` 全局 staging 区)
- Test fixture 设计:mock TBLite subprocess 输出 samples.jsonl 用什么 fake 数据集生成(deterministic,不调外部 API)

### Reviewed Todos (not folded)

- **`.planning/todos/pending/2026-05-07-enforce-readonly-hermes-agent.md`** — Phase 20 是首个 deliberate 多步骤 write-restore 路径(D-09 / D-10),CONCERNS §M6 read-only 现状被 Phase 20 进一步打破。但 deploy_mode gate 全局化(检查所有 evolve_* 写回是否在合法 context)的工作量超出 Phase 20 scope,留 Phase 22 持续进化循环或独立 hygiene phase。D-10 Pre-flight `git status --porcelain` 检查作为 Phase 20 内部的局部保护。
- **`.planning/todos/pending/2026-05-07-centralize-lm-retry-handling.md`** — LLM 重试集中化与本 phase 弱相关(Phase 20 主要 cost 在 Modal compute,不在 LM judge);planner 可参考但非主线。
- **`.planning/todos/pending/2026-05-07-expand-secret-patterns.md`** — Phase 14/19 已落地,Phase 20 不引入新 PII surface(benchmark 不挖矿),复用即可。
- **`.planning/todos/pending/2026-05-07-harden-llm-output-parsing.md`** — Phase 20 不新增 LLM-as-judge Signature(TBLite 是 task pass/fail binary signal,无 free-text 解析需求),不适用。
- **`.planning/todos/pending/2026-05-07-jsonl-skip-bad-lines.md`** — Phase 20 读 `samples_<ts>.jsonl`(TBLite 输出)走 per-line `try/except json.JSONDecodeError` 跳过 + 计 `jsonl_skipped_lines`(同 Phase 19 D-24);属于 implicit 复用,无新落地。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 项目规划文档(必读)
- `.planning/REQUIREMENTS.md` §PMPT-V2-03 — Phase 20 需求来源
- `.planning/ROADMAP.md` §Phase 20 — 三条成功标准(opt-in flag / 可配置 pass threshold / benchmark results 落 metrics)
- `.planning/PROJECT.md` §Constraints — 尺寸 / 依赖 / hermes-agent 只读约束;§Out of Scope 明确 "TBLite/YC-Bench per-iteration gating" 排除,Phase 20 是 bounded 版本

### 直接前置 CONTEXT(强相关)
- `.planning/phases/18-personality-drift-detection/18-CONTEXT.md` — **Phase 18 D-CAL-01..D-CAL-05 (calibration set) / D-GATE-01..04 (阶梯门) / D-ROB-01..04 (3-run averaging) / D-OUT-01..04 (drift_report) / D-BYPASS-01..02 (无 bypass) 全部是 Phase 20 决策直接模板**;Phase 20 D-01..D-18 中超过一半与 Phase 18 同构
- `.planning/phases/17-joint-section-optimization/17-CONTEXT.md` — joint vs round-robin pipeline 拓扑;Phase 20 step 10.5 插入位置需兼容两条 pipeline + A/B baseline 行为
- `.planning/phases/14-sessiondb-mining-for-tools/14-CONTEXT.md` — D-16 `--i-have-consent` gate / D-15 `SECRET_PATTERNS` 复用模板(Phase 20 不挖矿但 jsonl_skipped_lines 模式复用)

### 研究与约束(载荷决策)
- `.planning/research/SUMMARY.md` §7 Phase 20 — TBLite 内置 hermes-agent / median-of-3 / artifact-hash cache / opt-in default
- `.planning/research/SUMMARY.md` §121 — 小样本 variance 实验 calibrate "median-of-3 + 3pp band"(被本期升级为 "1.96σ + tier-weighted")
- `.planning/research/FEATURES.md` §PMPT-V2-03 — "evolve_prompt_sections --benchmark=tblite" / "fast subset (~20 tasks, ~20 min)" / "opt-in via --benchmark={tblite,tblite-fast,none}"(本期 30 tasks stratified 替代 ~20 random)
- `.planning/research/PITFALLS.md` §Pitfall 7 (TBLite Benchmark Gating) — **本期最关键约束来源**:5 条 prevention(out-of-loop / median-of-3 / subset / cost cap / cache / opt-in)逐条对应 Phase 20 D-01/D-03/D-05/D-15/D-16/D-17
- `.planning/research/ARCHITECTURE.md` §3.8 Phase 20 — 新包结构 `evolution/benchmarks/{tblite_runner.py, benchmark_gate.py}`(本期 D-09/D-13 增 `build_tblite_calibration.py`)
- `.planning/research/STACK.md` §Per-Phase Integration Plan §20 — subprocess into `hermes-agent/environments/benchmarks/tblite/tblite_env.py`,wrapper 管 cwd/env/timeout/output 解析
- `.planning/codebase/CONCERNS.md` §M6 — hermes-agent Read-Only Not Enforced;Phase 20 Pre-flight `git status --porcelain` check (D-10) 是局部缓解
- `.planning/codebase/CONCERNS.md` §M7 — JSONL Loaders Abort on Single Bad Line;Phase 20 读 `samples_<ts>.jsonl` 复用 Phase 19 D-24 模式
- `.planning/codebase/CONCERNS.md` §H4 — `output/` Not in .gitignore;Phase 20 output 默认走 `output/prompts/<ts>/`,继承已有 .gitignore 状态(若 H4 未修则继承风险)

### Phase 20 实现锚点(planner / executor 必读)
- **hermes-agent 侧**:
  - `~/.hermes/hermes-agent/environments/benchmarks/tblite/tblite_env.py` — TBLite 主入口,`evaluate` subcommand;基于 `TerminalBench2EvalEnv` 继承
  - `~/.hermes/hermes-agent/environments/benchmarks/tblite/default.yaml` — 默认配置(Modal backend,OpenRouter `anthropic/claude-opus-4.6`,terminal_timeout 300s,task_timeout 1200s)
  - `~/.hermes/hermes-agent/environments/benchmarks/tblite/run_eval.sh` — shell wrapper,Phase 20 可绕过直接调 `python tblite_env.py evaluate`
  - `~/.hermes/hermes-agent/environments/benchmarks/tblite/README.md` — 难度分布(Easy:40 / Medium:26 / Hard:26 / Extreme:8 = 100 tasks),Claude Haiku 4.5 reference pass rate
  - `~/.hermes/hermes-agent/environments/benchmarks/terminalbench_2/terminalbench2_env.py` lines 365-383 — `_streaming_path = samples_<ts>.jsonl` 输出,`_save_result` per-task append
  - `~/.hermes/hermes-agent/environments/benchmarks/terminalbench_2/terminalbench2_env.py` lines 896-922 — `eval/pass_rate` + per-category metrics 聚合;Phase 20 Risk_Score 计算需要的 per-tier breakdown 在这里
  - `~/.hermes/hermes-agent/agent/prompt_builder.py` — Phase 20 Virtual Prompt Overlay 目标文件(D-09);Phase 7 `extract_prompt_sections` 解析的同一文件
- **evolution 项目侧**:
  - `evolution/prompts/evolve_prompt_sections.py` step 10/11 (lines 1000-1100) — Phase 20 step 10.5 插入点;`drift_passed` / `drift_per_dim` 风格模板(D-18)
  - `evolution/prompts/evolve_prompt_sections.py` step 8 (lines 645-800) — Phase 18 drift gate 实现模板;Phase 20 benchmark gate 同模式(`FAILED_<ts>/` + metrics 写入)
  - `evolution/prompts/drift_detector.py` — DriftDetector 类作为 `BenchmarkGate` 类的结构模板(`check(...)` + `check_all(...)` + 内部 inner Signature)
  - `evolution/prompts/build_drift_calibration.py` — `build_tblite_calibration` CLI 直接模板(D-13);Click + Rich + datasets/prompts/<artifact>.json + 顶层 calibration_timestamp/seed 元字段
  - `evolution/prompts/prompt_loader.py` — `extract_prompt_sections` / `write_back_section`(Phase 20 Virtual Prompt Overlay 内复用 write_back 但走 `~/.hermes/tmp/` 目标)
  - `evolution/core/config.py` lines 30-65 — `EvolutionConfig.max_cost_usd` 字段;Phase 20 新增 `benchmark_max_cost_usd` 与 `tblite_estimated_cost_per_task_usd` 字段(D-16)
  - `evolution/core/cost_tracker.py` — `CostTracker` context manager;Phase 20 实例化两个独立 tracker 不共享 ledger(D-16)
  - `evolution/core/external_importers.py` lines 47-119 — `SECRET_PATTERNS` + `_contains_secret`(Phase 20 不挖矿,但 logs/regression.jsonl 写出前过滤防泄漏)
- **新建文件锚点**:
  - `evolution/benchmarks/__init__.py` — lazy ImportError guard(若 hermes-agent 不可达或 huggingface_hub 缺失)
  - `evolution/benchmarks/tblite_runner.py` — `TBLiteRunner` 类(Async Stream Pipe + State Monitor,D-11)
  - `evolution/benchmarks/benchmark_gate.py` — `TBLiteBenchmarkGate` 类(Risk_Score 算法 + Virtual Prompt Overlay,D-02/D-09)
  - `evolution/benchmarks/build_tblite_calibration.py` — anchor builder CLI(D-13)
  - `datasets/prompts/tblite_anchor.json` — anchor + 元数据(git 跟踪)
  - `datasets/prompts/tblite_stratified_subset.json` — 30-task 白名单(git 跟踪)
  - `~/.cache/hermes-evolution/tblite/<artifact-hash>/` — cache dir(用户 home,git 外)
  - `~/.hermes/tmp/benchmark_<ts>/` — Virtual Prompt Overlay 工作目录(用户 home,git 外)
  - `~/.hermes/backups/<ts>/` — Soft-Rollback 快照目录(用户 home,git 外)
  - `logs/regression.jsonl` — async regression 审计日志(项目根 `logs/`,需 .gitignore 加 `logs/`)

### 外部依赖(无新 pip dep,但需 API 调用)
- `subprocess` (stdlib) — TBLite subprocess.Popen 包装(D-11)
- `huggingface_hub` (via dspy/litellm 依赖链已存在;若不在直接依赖中 planner 验证)— `HfApi().dataset_info` 拿 dataset_revision_hash(D-15)
- `pathlib`, `json`, `hashlib`, `os.replace` (stdlib) — Virtual Prompt Overlay + atomic file replace(D-09)
- `threading` (stdlib) — Async Stream Pipe daemon thread for stdout/stderr non-blocking read(D-11)
- DSPy 不直接参与 Phase 20 gate(benchmark 不调 LLM-as-judge,只调外部 TBLite subprocess + Modal/OpenRouter inference)

### TBLite 行为参考
- TBLite dataset: HuggingFace `NousResearch/openthoughts-tblite`(100 tasks, 4 tier);上游来源 `open-thoughts/OpenThoughts-TBLite`
- TBLite 完整 run: ~30-120 min(Modal backend, parallel up to 128 tasks)
- TBLite cost(粗估,可被 D-17 实测覆盖): full 100 tasks × Claude Opus 4.6 ≈ $15-40/run;stratified 30 × $0.4/task × 3 runs ≈ $36 worst case(在 $50 cap 内)
- TBLite 输出: `samples_<ts>.jsonl` per-task + 聚合 `eval/pass_rate` + per-category metrics(从 `terminalbench2_env.py` lines 896-922 推导 Phase 20 解析 schema)
- TBLite per-task schema(从 `_save_result` 推导): `{task_name, category, passed: bool, score: float, reward: float, ...}`;`category` 字段映射 tier(planner 验证字段对齐)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `evolution/prompts/drift_detector.py` `DriftDetector` 类结构 — `BenchmarkGate` 直接模板(check + check_all + inner schema)
- `evolution/prompts/build_drift_calibration.py` Click + Rich CLI — `build_tblite_calibration` 直接模板(D-13)
- `evolution/prompts/prompt_loader.py` `write_back_section` — Virtual Prompt Overlay 写 `~/.hermes/tmp/` 目标时复用其 sectiontext-replace 逻辑(D-09)
- `evolution/core/config.py` `EvolutionConfig.load` 多层级配置链路(evolution.yaml < env < CLI override)— `benchmark_max_cost_usd` 等新字段沿用同链路(D-16)
- `evolution/core/cost_tracker.py` `CostTracker` context manager — Phase 20 instantiate 两个独立 tracker(D-16)
- `evolution/prompts/evolve_prompt_sections.py` `FAILED_<ts>/` 模板(lines 760-800)— Phase 20 gate fail 路径同模式(D-04)
- `evolution/prompts/evolve_prompt_sections.py` Rich Table summary 模板 — Phase 20 per-tier 报告 + `--wait` Live Table(D-12)
- `evolution/prompts/evolve_prompt_sections.py` lines 100-260 step 0-5 配置 + 数据集 — Phase 20 step 10.5 插入位置已隐含
- `~/.hermes/hermes-agent/environments/benchmarks/tblite/` 全套文件 — TBLite 外部子进程直接 entry point(D-11)
- HuggingFace dataset revision API(`huggingface_hub.HfApi`)— cache fingerprint(D-15)

### Established Patterns
- DSPy Module + inner Signature 类(Phase 1/3/13/14/18 统一)— Phase 20 不新增 DSPy Signature(benchmark 是外部 binary signal),但 BenchmarkGate 类沿用 `check_all` 接口
- Click CLI + Rich console + metrics.json 三件套(Phase 5/13/14/17/19 统一)— D-13/D-18 沿用
- FAILED_/ABORTED_ 输出目录约定(Phase 5/13/14/18)— D-04 沿用
- 数据集 calibration 落 `datasets/prompts/*.json` + git exception(Phase 18 D-CAL-02)— D-13 沿用
- 多模型 layered config(evolution.yaml < env < CLI)— D-16 沿用
- Pre-flight validation hard fail(Phase 18 D-CAL-05)— D-10 / D-14 沿用
- 共享 `output/prompts/<ts>/` 目录(Phase 17 D-OUT-04)— D-18 沿用,新增 `tblite_report.json` + `.pending_gate.json` + `.benchmark_full_running.pid` 同目录
- 3-run averaging 仅在 final constraint gate 触发(Phase 18 D-ROB-01)— D-03 沿用

### Integration Points
- `evolve_prompt_sections.py --benchmark=tblite` → check anchor + cache → Virtual Prompt Overlay → TBLiteRunner.run() (subprocess.Popen + stream parse) → samples.jsonl → BenchmarkGate.check() → Risk_Score → accept/reject 分支 → write-back / FAILED_<ts>/ → 若 accept + `--no-async-full-verify` 不传 → detached full-run subprocess → tblite_full_report.json → Soft-Rollback if regress
- `build_tblite_calibration` → Virtual Prompt Overlay(空 evolved,即 untouched)→ TBLiteRunner × 3 runs × stratified subset → per-tier mean+σ → `tblite_anchor.json`
- `evolve_prompt_sections --check-benchmark <ts>` → 读 `.pending_gate.json` + 等 `.benchmark_running.lock` 释放 → gate 判定 + write-back / FAILED
- `evolve_prompt_sections --restore <ts>` / `--confirm-rollback <ts>` → 操作 `~/.hermes/backups/<ts>/` + `logs/regression.jsonl` 状态机
- Cache 命中路径: `~/.cache/hermes-evolution/tblite/<artifact-hash>/result.json` 存在 → 跳过 subprocess → 直接喂 BenchmarkGate.check()
- Cost 累加路径: subprocess wrapper 内估算每 task LLM cost(读 OpenRouter response usage)→ 累加 benchmark_tracker → 超 `benchmark_max_cost_usd` raise CostBudgetExceeded(同 Phase 13 模式)

### Risk Anchors (Pre-execution)
- **Virtual Prompt Overlay 的原子性证明**:`os.replace` 在 POSIX 上是 atomic(同 fs);但 hermes-agent 与 `~/.hermes/tmp/` 可能跨 fs(symlink 路径) → 退化到 non-atomic copy。planner 在 PLAN 中明确 fs-boundary 检测 + fallback。
- **CONCERNS §M6 read-only 加重**:Phase 20 是首个 deliberate 多步 write-restore 路径,Pre-flight `git status --porcelain` (D-10) 是局部缓解,但用户在 hermes-agent 仓里有 stash 时 `--porcelain` 仍 empty。planner 在 PLAN 中考虑是否额外 check `git stash list`。
- **TBLite Modal 后端时延 + 配额**:Modal API 限流 / sandbox 启动失败 / 网络中断 → Async Stream Pipe heartbeat(D-11)是第一道防线;但 Modal 内部错误 hermes-agent 已抛 TimeoutError(samples.jsonl 写 fail 状态),Phase 20 Risk_Score 计算需把"task failed for infra reason"与"task failed for prompt reason"区分(planner 在 PLAN 中明确字段映射)。
- **anchor / moving_avg 数值漂移**:hermes-agent 主代码变更 → anchor commit_hash 不匹配 → D-14 硬 fail;但 moving_avg 历史(`tblite_history.json`)若版本跨度大,新旧 hermes-agent 评分不可比 → planner 在 PLAN 中决策:moving_avg 是否也按 hermes_agent_commit 分桶,还是只取同一 commit 的 history。
- **HuggingFace API 不可用 / 限流**:`HfApi().dataset_info` 抛网络错误 → cache fingerprint 退化策略(planner 决:fail open 跳过 cache / fail closed 拒跑 / fallback 到本地 dataset checksum)。
- **TBLite `--env.task_filter` 语义验证**:Phase 20 假设 task_filter CSV 是 task name CSV,但 TBLite 实际可能是 category filter。planner Task 1 必须先 spike 验证(可参考 `run_eval.sh --env.task_filter broken-python,pandas-etl`)。
- **`benchmark_max_cost_usd=50` 默认值是否安全**:stratified 30 × 3 runs ≈ $36 worst case + async full 100 × 1 run ≈ $20 → 总额 ~$56 超 $50。planner 需要 D-16 默认值复核(可能要 $80 才稳妥),或 async full 走独立 budget。

</code_context>

<specifics>
## Specific Ideas

- Risk_Score 阈值与权重(D-02 default):
  ```python
  TIER_WEIGHTS = {"easy": 1.0, "medium": 1.5, "hard": 2.0, "extreme": 4.0}
  REJECT_THRESHOLD = 4.0
  CONFIDENCE_Z = 1.96  # 95% one-sided
  ```
- Stratified subset 默认分布(D-05):
  ```python
  STRATIFIED_30 = {"easy": 12, "medium": 8, "hard": 7, "extreme": 3}  # 共 30
  ```
- Cache key 公式(D-15):
  ```python
  artifact_hash = sha256(
      canonical_json(evolved_sections).encode()
      + dataset_revision_hash.encode()
      + stratified_subset_seed.to_bytes(4, "big")
      + tblite_runner_version.encode()
  ).hexdigest()[:16]
  ```
- Pre-flight Watermark(D-17):
  ```python
  estimated_cost = tblite_estimated_cost_per_task_usd × num_tasks × num_runs
  watermark = estimated_cost * 3
  available = benchmark_max_cost_usd - already_spent
  if watermark > available:
      raise SystemExit(f"Insufficient benchmark budget: need {watermark:.2f}, have {available:.2f}")
  ```
- `tblite_anchor.json` schema:
  ```json
  {
    "anchor_per_tier": {
      "easy": {"mean": 0.85, "stdev": 0.02, "n": 3, "scores": [0.83, 0.86, 0.86]},
      "medium": {...}, "hard": {...}, "extreme": {...}
    },
    "dataset_revision_hash": "abc123...",
    "hermes_agent_commit": "def456...",
    "stratified_subset_seed": 42,
    "tblite_estimated_cost_per_task_usd": 0.4,
    "calibration_timestamp": "2026-05-19T10:00:00Z",
    "calibration_model": "anthropic/claude-opus-4.6"
  }
  ```
- `tblite_report.json` schema:
  ```json
  {
    "decision": "accept|reject",
    "risk_score": 2.5,
    "reject_threshold": 4.0,
    "tier_weights": {...},
    "per_tier": {
      "easy": {"scores": [0.83, 0.86, 0.86], "mean": 0.85, "stdev": 0.014, "threshold": 0.82, "anchor": 0.85, "moving_avg": 0.86, "breach": false},
      "medium": {...}, "hard": {...}, "extreme": {...}
    },
    "samples_jsonl_path": "...",
    "subprocess_runtime_seconds": 1834,
    "cost_breakdown": {"modal_compute_usd": 12.0, "openrouter_inference_usd": 8.5},
    "dataset_revision_hash": "...",
    "cache_hit": false,
    "async_full_verify_pending": true
  }
  ```
- Async full verify lock file: `output/prompts/<ts>/.benchmark_full_running.pid` 含 detached subprocess PID + start_time;`evolve_prompt_sections --check-benchmark <ts>` 校 PID 是否存活(`os.kill(pid, 0)`)
- `logs/regression.jsonl` 每行 schema:
  ```json
  {"timestamp": "...", "phase": "20", "hermes_commit_before": "...", "hermes_commit_after_restore": "...", "evolved_sections_artifact": "output/prompts/<ts>/evolved_sections.json", "risk_score_async_full": 4.5, "snapshot_path": "~/.hermes/backups/<ts>/", "last_known_good": "output/prompts/<prev-ts>/evolved_sections.json", "status": "pending_human_review|confirmed|restored"}
  ```
- Click CLI 新增 flags(D-12):
  ```
  --benchmark={none,tblite,tblite-full}  default: none
  --benchmark-tier <csv>                 default: easy,medium,hard,extreme
  --benchmark-cache / --no-benchmark-cache  default: enabled
  --wait / --detach                      default: --wait
  --no-async-full-verify                 default: disabled (即 default 跑 async full verify)
  --benchmark-max-cost <usd>             default: 50.0
  ```
  + subcommands: `--check-benchmark <ts>` / `--restore <ts>` / `--confirm-rollback <ts>`
- `build_tblite_calibration` 输出栏 Rich Table 字段: `Tier | N tasks | Run 1 | Run 2 | Run 3 | Mean | Stdev | Anchor`
- TBLite subprocess 命令行候选:
  ```bash
  cd ~/.hermes/hermes-agent && python environments/benchmarks/tblite/tblite_env.py evaluate \
    --config environments/benchmarks/tblite/default.yaml \
    --env.task_filter "<task1,task2,...>" \
    --openai.model_name "anthropic/claude-opus-4.6" \
    --env.data_dir_to_save_evals "<output_path>"
  ```
- Heartbeat detection: 60s 无 stdout 行 → `hang_count++`;hang_count >= 3 → SIGTERM + 写 `TBLITE_HANG_<ts>/`(D-11)

</specifics>

<deferred>
## Deferred Ideas

- **`evolve_tool_descriptions --benchmark` / `evolve_skill --benchmark`** — 同 PMPT-V2-03 scope 之外;若未来 tool/skill 域也想门控,独立 phase 推进。
- **HuggingFace dataset revision pin (`--tblite-dataset-revision <sha>`)** — 本期 cache fingerprint 用 dataset commit 自动 invalidate;若需复现历史 calibration,这 flag 让 ops 钉版本。
- **YC-Bench / 完整 TerminalBench2 集成** — PROJECT.md Out-of-Scope;TBLite 是 v2.0 唯一支持的 benchmark。
- **per-iteration benchmark(放 GEPA loop 内)** — PITFALL #7 prevention #1 硬约束,Phase 20 内永不开启。
- **Quarterly 自动重 calibration 调度** — 同 Phase 18 D-CAL-05 思路,留 ops。
- **`--benchmark=tblite-fast`(基于难度子集)+ `--benchmark=tblite-full`(全量)+ `--benchmark=tblite-tier <tier>` 三档** — Features §PMPT-V2-03 草稿;本期 D-05/D-06 用 `--benchmark={none,tblite}` + `--benchmark-tier <csv>` + `--benchmark-full` flag 组合,等价但更简洁。若用户反馈三档更直观再拆。
- **Risk_Score 阈值与权重运行期自适应**(根据 calibration variance 动态调)— 本期硬编默认 + 字段暴露可调;若多次 calibration 后看到趋势再决策。
- **Per-section attribution of benchmark regression**(哪段 section 害得 TBLite 哪个 tier 掉)— 需要在 prompt_builder.py 重组中插探针,scope 显著扩大,留 Phase 23+。
- **Cache 内容主动失效(`--clear-benchmark-cache`)** — 本期 content-addressed 自然失效;若用户报 cache size 膨胀再加。
- **Dataset 本地镜像(`huggingface_hub.snapshot_download` 缓存 TBLite dataset)** — 减网络依赖;TBLite Docker images 已经 cache 在 nousresearch/tblite-* 但 dataset metadata 仍线上读。若 ops 报频繁限流再加。
- **Modal backend 替代(本地 Docker)** — TBLite default Modal,但有 local backend;本期不暴露,planner 决定是否 expose `--terminal-backend` flag。
- **Phase 16 dashboard 接入 `benchmark_*` 字段** — metrics.json 已用 `benchmark_*` 前缀便于未来 dashboard 接入按前缀分桶;具体接入留 Phase 16 v3 / 单独 phase。

### Reviewed Todos (not folded)

- **`.planning/todos/pending/2026-05-07-enforce-readonly-hermes-agent.md`** — Phase 20 是首个 deliberate write-restore 路径(D-09 / D-10),CONCERNS §M6 read-only 现状被 Phase 20 进一步打破。deploy_mode gate 全局化(检查所有 evolve_* 写回是否在合法 context)的工作量超出 Phase 20 scope,留 Phase 22 持续进化循环或独立 hygiene phase。D-10 Pre-flight `git status --porcelain` + Soft-Rollback transactional 保证作为 Phase 20 内部的局部保护。
- **`.planning/todos/pending/2026-05-07-centralize-lm-retry-handling.md`** — LLM 重试集中化与本 phase 弱相关(Phase 20 主要 cost 在 Modal compute,不在 LM judge);留独立 hygiene phase。
- **`.planning/todos/pending/2026-05-07-expand-secret-patterns.md`** — Phase 14/19 已落地,Phase 20 不引入新 PII surface,复用即可。
- **`.planning/todos/pending/2026-05-07-harden-llm-output-parsing.md`** — Phase 20 不新增 LLM-as-judge Signature(TBLite 是 binary pass/fail signal),不适用。
- **`.planning/todos/pending/2026-05-07-jsonl-skip-bad-lines.md`** — Phase 20 读 `samples_<ts>.jsonl` 复用 Phase 19 D-24 模式,implicit 复用无新落地。
- **`.planning/todos/pending/2026-05-07-add-lockfile-dspy-pin.md`** — 依赖锁定,与本期无关。

</deferred>

---

*Phase: 20-benchmark-gated-validation*
*Context gathered: 2026-05-19*
