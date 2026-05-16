---
phase: 18-personality-drift-detection
verified: 2026-05-16T10:00:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
---

# Phase 18: Personality Drift Detection 验证报告

**Phase Goal:** Detect tone/personality changes between original and evolved prompt sections
**Verified:** 2026-05-16T10:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth (ROADMAP Success Criteria + Plan must-haves) | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1   | SC#1: DriftDetector compares original vs evolved text on tone/formality/vocabulary/persona via pairwise LLM judge | VERIFIED | `evolution/prompts/drift_detector.py` 第 110-127 行用 `dspy.LM(config.eval_model, temperature=0.7, cache=False, ...)` 构造判官；`DriftScoreSignature.model_fields['tone_score'/.../persona_score'].annotation is float` 已动态验证通过；10 个 `test_drift_detector.py` 单元测全部 GREEN。 |
| 2   | SC#2: Constraint gate rejects evolved sections with drift score exceeding threshold | VERIFIED | `evolve_prompt_sections.py:515` 实例化 `DriftDetector(config, drift_thresholds)`，`:526-527` 将 `constraint_result.passed=False` 流入 `all_pass=False`，`:627-669` 在 `not all_pass` 时写 `FAILED_<ts>/` 且 `return`（不部署）。`test_two_dim_drift_rejects_and_writes_failed_dir` 集成测以 2-dim 超阈值 drift_results 触发 reject 路径并断言 `FAILED_` 目录、`drift_passed=false`、≥2 exceeded dims、`status="FAILED"`。 |
| 3   | SC#3: Drift report included in optimization output | VERIFIED | 成功路径 `:962-966` 写 `output/prompts/<ts>/drift_report.txt`；FAILED 路径 `:661-663` 写 `FAILED_<ts>/drift_report.txt`；metrics.json 含 `drift_per_dim` / `drift_thresholds` / `drift_passed` / `drift_exceeded_dims`（成功路径 `:938-941`，FAILED 路径 `:640-643`）。`test_metrics_json_has_drift_fields` + `test_round_robin_metrics_json_has_drift_fields` + `test_two_dim_drift_rejects_and_writes_failed_dir` 全 PASS。 |
| 4   | DriftCalibrationBuilder generates 30 calibration examples with ground-truth labels (D-CAL-01..04) | VERIFIED | `datasets/prompts/drift_calibration.jsonl` 实测 30 行；20 drift + 10 no-drift；`drift_dim` 覆盖全部 4 维 (`{formality, persona, tone, vocabulary}`)；5 个 section_id (`default_agent_identity`, `memory_guidance`, `platform_hints.whatsapp`, `session_search_guidance`, `skills_guidance`)。 |
| 5   | drift_thresholds.json contains F1-derived per-dim thresholds + _meta audit block (D-CAL-05) | VERIFIED | `datasets/prompts/drift_thresholds.json`：`tone=0.65 / formality=0.25 / vocabulary=0.60 / persona=0.35` 全部在 [0.10, 0.90]；`_meta.f1_tier=2`、`_meta.f1_self.macro=0.536`、`_meta.f1_targets.preset="v1-pragmatic"`、`_meta.generator_model="openai/qwen-plus"`、`_meta.judge_model="openai/gpt-5.5"`、`_meta.num_examples=30`、`_meta.calibration_timestamp` 完备。 |
| 6   | Both calibration artifacts committed to git (D-CAL-02 exception active) | VERIFIED | `git ls-files datasets/prompts/drift_calibration.jsonl datasets/prompts/drift_thresholds.json` 输出 2 个文件；`.gitignore` 第 22-23 行包含 `!datasets/prompts/drift_calibration.jsonl` 与 `!datasets/prompts/drift_thresholds.json` 反向例外。 |
| 7   | --drift-thresholds-path flag exists; --no-drift-check / --skip-drift-check do NOT exist (D-BYPASS-01/02) | VERIFIED | `--help` 输出含 `--drift-thresholds-path PATH` 选项；`grep -cE '@click\.option\(\s*"--(no\|skip)-drift-check"' evolve_prompt_sections.py` 返回 0；运行时 `python -m evolution.prompts.evolve_prompt_sections --no-drift-check` 退出码 2 并报 "No such option"。 |
| 8   | drift_* metrics fields written UNCONDITIONALLY for BOTH joint AND round-robin (D-ROB-04) | VERIFIED | `evolve_prompt_sections.py:937` `if drift_results:` 处于 4-space 函数体缩进（与 `:928` `if effective_mode == "joint"` 同列），位于 joint-only 条件块**外部**；`test_round_robin_metrics_json_has_drift_fields` 显式以 `--mode round-robin` 调用并断言 4 个 `drift_*` 字段存在，PASS。 |
| 9   | Severity ladder pass/warn/reject implemented with conservative `mean - stdev > threshold` rule (D-GATE-01/02/03/04 + D-ROB-02) | VERIFIED | `drift_detector.py:check()` 实现 3-run averaging + `(mean - sd) > thresholds[dim]` 决策；exceeded_count 0/1/2+ 映射到 severity pass/warn/reject 且 ConstraintResult.passed True/True/False；`test_severity_ladder_pass` / `test_severity_ladder_warn` / `test_severity_ladder_reject` / `test_conservative_decision_rule` 全 PASS。 |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected    | Status | Details |
| -------- | ----------- | ------ | ------- |
| `evolution/prompts/drift_detector.py` | DriftDetector + DriftScoreSignature + DRIFT_DIMENSIONS + _clamp_unit | VERIFIED | 258 行；`DRIFT_DIMENSIONS == ('tone','formality','vocabulary','persona')`；`temperature=0.7` 与 `cache=False` 两个字面值都出现在源码（`:120-121`）；4 个 OutputField 都是 typed-float。 |
| `evolution/prompts/drift_calibration.py` | DriftCalibrationExample + DriftCalibrationDataset + DriftCalibrationBuilder + derive_thresholds | VERIFIED | 283 行；0 个 sklearn/numpy/scipy import（RA3 闭环）；`config.judge_model` 作为 `dspy.LM` 首位置参数出现在 `:160`（RA5 闭环）；纯 stdlib F1 brute scan。 |
| `evolution/prompts/build_drift_calibration.py` | Click CLI: extract → generate → derive → persist | VERIFIED | 473 行；`--help` 列出 14+ 个 flag（包括 `--seed`、`--output-jsonl`、`--output-thresholds`、`--hermes-repo`、`--no-derive`、`--reuse-jsonl`、`--eval-model`、`--target-self`、`--per-dim-floor`、`--macro-floor`、`--accept-tier-3`）；Tier 1/2/3 分类器实现完整。 |
| `evolution/prompts/evolve_prompt_sections.py` | Step 8c DriftDetector wiring + Rich Table + drift_report.txt + --drift-thresholds-path | VERIFIED | 第 32 行 `from evolution.prompts.drift_detector import DRIFT_DIMENSIONS, DriftDetector`；`:515` 实例化；`:589-617` Rich Table；`:961-966` 成功路径 drift_report.txt；`:1044` Click 选项；`:1066` 转发到 evolve()。 |
| `datasets/prompts/drift_calibration.jsonl` | 30 examples, 4-dim drift_dim 覆盖, git-tracked | VERIFIED | 30 行；20 drift + 10 no-drift；`drift_dim` 覆盖全 4 维；git-tracked（D-CAL-02 反向例外生效）。 |
| `datasets/prompts/drift_thresholds.json` | per-dim thresholds + _meta audit block, git-tracked | VERIFIED | 4 dim 阈值 + 完整 `_meta`（含 `f1_self`、`f1_tier=2`、`f1_targets.preset="v1-pragmatic"`、`generator_model`、`judge_model`、`seed`、`num_examples`、`calibration_timestamp`）；git-tracked。 |
| `tests/prompts/test_drift_detector.py` | 10 unit tests (RA1/RA2/D-ROB-02/D-GATE-01 severity ladder) | VERIFIED | 10 个测试方法存在并全部 PASS（`test_typed_float_parsing`、`test_parse_failure_fallback_zero`、`test_lm_constructed_with_temperature`、`test_three_run_stdev_nonzero`、`test_conservative_decision_rule`、`test_check_returns_4_dim_scores`、`test_severity_ladder_pass/warn/reject`、`test_drift_report_payload`）。 |
| `tests/prompts/test_drift_calibration.py` | 4 tests (F1 derivation, no-sklearn guard, judge_model wiring, live skeleton) | VERIFIED | 4 个测试方法存在；3 个非 live 测试 PASS，1 个 `test_f1_target_self_eval` 在 `RUN_LIVE_LLM` 未设时 SKIPPED。 |
| `tests/prompts/test_evolve_prompt_sections_cli.py::TestDriftGate` | 6 integration tests | VERIFIED | 6 个测试方法存在并全部 PASS：`test_metrics_json_has_drift_fields`、`test_round_robin_metrics_json_has_drift_fields`、`test_drift_thresholds_path_flag`、`test_no_skip_drift_flag`、`test_one_dim_drift_warns_but_deploys`、`test_two_dim_drift_rejects_and_writes_failed_dir`。 |
| `tests/prompts/conftest.py` | mock_drift_lm + dummy_thresholds + drift_calibration_mini_path fixtures | VERIFIED | 3 个 fixture 全部存在，被下游测试导入消费。 |
| `tests/prompts/fixtures/drift_calibration_mini.jsonl` | 6-row mini fixture for offline derive_thresholds tests | VERIFIED | 6 行；schema 与 DriftCalibrationExample 1:1 对齐。 |
| `.gitignore` | exception lines for drift_calibration.jsonl + drift_thresholds.json | VERIFIED | 第 22-23 行包含两条反向例外行；calibration 文件已成功 git-tracked。 |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `evolve_prompt_sections.py:515` | `DriftDetector` | `DriftDetector(config, drift_thresholds)` | WIRED | grep 命中 1 次；签名匹配 Wave 1 契约；测试 `test_metrics_json_has_drift_fields` 通过 CLI 集成路径走通。 |
| `evolve_prompt_sections.py:510` | `datasets/prompts/drift_thresholds.json` | `json.loads(drift_thresholds_path.read_text())` | WIRED | 默认路径已在 `:125` / `:1046` 设置为 `Path("datasets/prompts/drift_thresholds.json")`；运行时通过 `click.Path(exists=True)` 校验。 |
| `evolve_prompt_sections.py:516` | `original_sections, evolved_sections` | `detector.check_all(original_sections, evolved_sections)` | WIRED | `:524` 遍历 `drift_results`，`:525` 将 `constraint_result` 推入 `all_constraint_results`，参与 `all_pass` 短路与 metrics 聚合。 |
| `evolve_prompt_sections.py:937-953` | `metrics.json` | `metrics["drift_per_dim"] = ...` 等 6 个字段 | WIRED | 测试 `test_metrics_json_has_drift_fields` 与 `test_round_robin_metrics_json_has_drift_fields` 解析 metrics.json 并断言全部字段存在。 |
| `evolve_prompt_sections.py:964` | `output/prompts/<ts>/drift_report.txt` | `(output_dir / "drift_report.txt").write_text(...)` | WIRED | 测试 `test_two_dim_drift_rejects_and_writes_failed_dir` 断言 markdown 头部 (`## Section:`, `### Dim:`, `Decision:`) 在 FAILED 路径写出。 |
| `evolve_prompt_sections.py:661-663` | `FAILED_<ts>/drift_report.txt` | `(output_dir / "drift_report.txt").write_text(...)` | WIRED | FAILED 路径与成功路径都写 drift_report.txt，5 处 `drift_report.txt` 字面引用。 |
| `evolve_prompt_sections.py:1044-1052` | Click parser | `@click.option("--drift-thresholds-path", type=click.Path(exists=True), default=...)` | WIRED | `--help` 输出包含；`test_drift_thresholds_path_flag` 用自定义文件路径验证 `metrics["drift_thresholds"]` 与 file 内容逐字相等。 |
| `build_drift_calibration.py` | `DriftCalibrationBuilder.generate(sections)` | CLI Step 2 → `dataset.save(path)` | WIRED | `datasets/prompts/drift_calibration.jsonl` 已实际生成（30 行），且 git-tracked。 |
| `build_drift_calibration.py` | `derive_thresholds(dataset, config)` | CLI Step 4 → 写 `output_thresholds` | WIRED | `datasets/prompts/drift_thresholds.json` 已实际生成（4 dim + _meta），与 dataset 同步落盘。 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `drift_detector.py:DriftDetector.check` | `runs` (list of scores+explanation) | `_check_one_run` × 3 → DSPy ChainOfThought judge call | YES — 真实 LLM 判官输出经 try/except 容错（ValidationError → 0.0 fallback），3-run averaging 产生非零 stdev | FLOWING |
| `drift_calibration.py:DriftCalibrationBuilder.generate` | `examples` (DriftCalibrationExample list) | `self.generator(...)` (`config.judge_model` 驱动的 DSPy ChainOfThought) | YES — 真实 LLM 生成 30 个变体（5 section × 6 variants），ground-truth 标签由调用方驱动（drift/preserve 模式 + target_dim） | FLOWING |
| `evolve_prompt_sections.py drift_per_dim_metrics` | aggregated per-section per-dim | `drift_detector.check_all(...)` 输出 | YES — 集成测以 `_make_drift_result` 构造 Wave 1-shape 结果并断言字段在 metrics.json 中逐字落地 | FLOWING |
| `datasets/prompts/drift_thresholds.json` | per-dim float thresholds | `build_drift_calibration` 实际 live LLM 调用 + `derive_thresholds` brute-scan F1 | YES — _meta 块记录真实 generator/judge model id、real F1 self-eval（macro=0.536, persona=0.7273 等），非占位值 | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| `--no-drift-check` flag rejected | `python -m evolution.prompts.evolve_prompt_sections --no-drift-check` | `Error: No such option: --no-drift-check` exit 2 | PASS |
| `--drift-thresholds-path` exposed in help | `python -m evolution.prompts.evolve_prompt_sections --help \| grep drift-thresholds-path` | `--drift-thresholds-path PATH    Path to drift_thresholds.json...` | PASS |
| `build_drift_calibration` CLI runnable | `python -m evolution.prompts.build_drift_calibration --help` | 14+ flags listed including `--seed`, `--reuse-jsonl`, `--eval-model`, `--target-self`, `--accept-tier-3` | PASS |
| DriftDetector module contract | `python -c "from ...drift_detector import DriftDetector, DRIFT_DIMENSIONS; assert DRIFT_DIMENSIONS == ('tone','formality','vocabulary','persona')"` | PASS（动态验证 typed-float annotation 全部正确） | PASS |
| Drift detector + calibration unit tests | `pytest tests/prompts/test_drift_detector.py tests/prompts/test_drift_calibration.py -q` | 13 passed, 1 skipped (live LLM) in 0.16s | PASS |
| TestDriftGate integration tests | `pytest tests/prompts/test_evolve_prompt_sections_cli.py::TestDriftGate -v` | 6 passed in 0.38s | PASS |
| Full repo test suite | `pytest tests/ -q` | **533 passed, 1 skipped, 1 xfailed** in 12.89s — 零回归 | PASS |
| calibration.jsonl shape | `python -c "rows=[json.loads(l) for l in open(...)]; assert len(rows)==30; ..."` | 30 行, 20 drift + 10 no-drift, 4 dim 全覆盖, 5 section_id 覆盖 | PASS |
| thresholds.json shape | `python -c "t=json.load(open(...)); assert all(0.10<=t[d]<=0.90 for d in DRIFT_DIMENSIONS); assert t['_meta']['f1_tier']==2"` | 全部断言通过 | PASS |
| Git tracking of calibration artifacts | `git ls-files datasets/prompts/drift_*` | 2 文件 git-tracked | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| PMPT-V2-02 | 18-01 / 18-02 / 18-03 / 18-04 / 18-05 | Personality/tone drift detection (automated comparison before/after) | SATISFIED | 全部 5 个 plan 在 `requirements: [PMPT-V2-02]` 与 `requirements_addressed: [PMPT-V2-02]` 中声明；REQUIREMENTS.md 已标记 "Phase 18 / Complete"；3 条 ROADMAP Success Criteria 全部由代码 + 测试覆盖（SC#1 → Wave 1 unit tests；SC#2 → `test_two_dim_drift_rejects_and_writes_failed_dir`；SC#3 → `test_metrics_json_has_drift_fields` + `test_round_robin_metrics_json_has_drift_fields` + `test_two_dim_drift_rejects_and_writes_failed_dir`）。 |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| —    | —    | 无重大反模式 | INFO | drift_detector / drift_calibration / build_drift_calibration / evolve_prompt_sections 中未发现 TODO/FIXME/PLACEHOLDER；`return None` / `=[]` 等仅出现在合法初始化或测试 fixture，没有渲染至生产数据流。 |
| datasets/prompts/drift_thresholds.json | _meta.f1_targets.preset | "v1-pragmatic" 替代 research-strict 目标 (0.60 / 0.35 / 0.50 vs 0.85 / 0.70 / 0.80) | INFO | 用户已在 prompt 上下文中显式声明这是有意 tech debt（受限于 qwen-plus + gpt-5.5 reseller 判官组合）；Tier 2 PASS，constraint gate 仍可运行只是更宽松；Plan 18-03 SUMMARY、CONTEXT 与 thresholds.json `_meta` 三处都记录了 preset 选项，可追溯。**不构成 BLOCKER 或 WARNING**——这是显式的 calibration 配置决策，不是隐藏的功能缺失。 |
| —    | —    | API key leakage (OPENAI_API_KEY + reseller key) | INFO | 用户已在 prompt 上下文中显式排除：属操作性事后追踪（应轮换密钥），不是 phase artifact，不在验证范围内。 |

### Human Verification Required

无。Plan 18-03 Task 2 在执行期已完成人类抽查检查点（10/10 一致性，由 Plan 18-03 SUMMARY 记录）；其余所有 Success Criteria 与 must-haves 均由自动化测试覆盖。VALIDATION.md §Manual-Only Verifications 也确认 Phase 18 之后无新增 recurring 人工验证需求。

### Gaps Summary

无 gap。Phase goal "Detect tone/personality changes between original and evolved prompt sections" 已完整达成：

1. **检测能力（SC#1）**：DriftDetector 实现完成 4 维 pairwise LLM judge + 3-run averaging + 保守决策规则，10 个单元测全部 GREEN。
2. **门禁能力（SC#2）**：constraint gate 通过 ConstraintResult.passed 传播 reject 信号，2+ dim 触发 FAILED 路径并阻止部署；`test_two_dim_drift_rejects_and_writes_failed_dir` 集成测断言完整闭环。
3. **报告输出能力（SC#3）**：drift_report.txt 在成功与 FAILED 双路径写出；metrics.json 含 4-6 个 `drift_*` 字段且 joint / round-robin 双模式均写入（D-ROB-04 索引非歧义已被 `test_round_robin_metrics_json_has_drift_fields` 锁定）。
4. **calibration 工具链（D-CAL-05）**：build_drift_calibration CLI 在 phase 内完成执行，产出真实 calibration set（30 行）+ thresholds.json（Tier 2，v1-pragmatic）并 git 跟踪。
5. **bypass 防御（D-BYPASS-01）**：无任何 `--no-drift-check` / `--skip-drift-check` 选项，由 `test_no_skip_drift_flag` 在 CI 中永久锁定。
6. **D-ROB-04 索引保护**：4-space function-body 缩进的 `if drift_results:` 块位于 joint-only 条件外，`test_round_robin_metrics_json_has_drift_fields` 提供未来回归保护。

测试结果总览：533 passed, 1 skipped (live-LLM 跳过), 1 xfailed — 零回归。所有 9 条 must-have truth 全部 VERIFIED；所有 12 个核心 artifact 全部 VERIFIED；所有 9 条 key link 全部 WIRED；4 项 Level 4 数据流追踪全部 FLOWING；10 项行为 spot-check 全部 PASS。

v1-pragmatic 校准预设是显式有意的 tech debt（已在三处记录），不构成功能缺失。两个 API key 泄漏属操作性后续，不在 phase artifact 范围。

---

_Verified: 2026-05-16T10:00:00Z_
_Verifier: Claude (gsd-verifier)_
