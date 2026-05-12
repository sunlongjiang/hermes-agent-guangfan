---
phase: 16
slug: per-tool-regression-dashboard
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-12
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: 16-RESEARCH.md §Validation Architecture (Nyquist 4 dimensions: unit / integration / functional / system).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=7.0 + pytest-asyncio >=0.21 (declared in `pyproject.toml [project.optional-dependencies].dev`) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/pytest tests/tools/test_persist_raw_predictions.py tests/tools/test_regression_dashboard.py -x` |
| **Full suite command** | `.venv/bin/pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds (quick) / ~3 minutes (full) — based on Phase 13 / 15 baseline |

---

## Sampling Rate

- **After every task commit:** Run quick command (helper + dashboard tests for the touched wave)
- **After every plan wave:** Run `.venv/bin/pytest tests/tools/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green + manual `python -m evolution.tools.regression_dashboard --runs output/tools_reasoning` against real data
- **Max feedback latency:** 30 seconds (quick command target; full suite is gate-only)

---

## Per-Task Verification Map

> Task IDs are placeholders (`{N}-{plan}-{task}` format). gsd-planner will assign real IDs in Wave 0–4 plans.

| Task ID | Plan | Wave | Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|----------|-----------|-------------------|-------------|--------|
| 16-00-01 | 00 | 0 | TOOL-V2-04 / D-12 | `persist_raw_predictions` immutability + shape (shallow copy入参不被 mutate, sorted keys, float 强转, None 容错) | unit | `.venv/bin/pytest tests/tools/test_persist_raw_predictions.py::test_immutability_and_shape -x` | ❌ Wave 0 | ⬜ pending |
| 16-00-02 | 00 | 0 | TOOL-V2-04 / D-12 | `persist_raw_predictions` empty list / None 输入 / >2000 项 stdout warning | unit | `.venv/bin/pytest tests/tools/test_persist_raw_predictions.py::test_empty_and_large -x` | ❌ Wave 0 | ⬜ pending |
| 16-00-03 | 00 | 0 | TOOL-V2-04 / D-11 | `to_dspy_examples` 包含 `difficulty` (现有不含) | unit | `.venv/bin/pytest tests/tools/test_tool_dataset.py::test_dspy_example_has_difficulty -x` | ❌ Wave 0 | ⬜ pending |
| 16-00-04 | 00 | 0 | TOOL-V2-04 / D-12 | evolve_tool_params holdout 写 `raw_predictions` + 现有 `per_tool_*_rates` 到 metrics.json | integration | `.venv/bin/pytest tests/tools/test_evolve_tool_params_cli.py::test_metrics_includes_raw_predictions -x` | ⚠️ extend | ⬜ pending |
| 16-00-05 | 00 | 0 | TOOL-V2-04 / D-12 | evolve_tool_descriptions holdout 写 `per_tool_*_rates` + `raw_predictions` (Wave 0 新接) | integration | `.venv/bin/pytest tests/tools/test_evolve_tool_descriptions.py::test_metrics_includes_per_tool_and_raw -x` | ⚠️ extend | ⬜ pending |
| 16-00-06 | 00 | 0 | TOOL-V2-04 / D-12 | evolve_tool_reasoning holdout 写 `per_tool_*_rates` + `raw_predictions` (Wave 0 新接) | integration | `.venv/bin/pytest tests/tools/test_evolve_tool_reasoning.py::test_metrics_includes_per_tool_and_raw -x` | ⚠️ extend | ⬜ pending |
| 16-01-01 | 01 | 1 | TOOL-V2-04 / D-05+D-09 | dashboard LATEST 区渲染 per-tool 表 (sample_count + min/p25/median/p75/max + status) | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_latest_renders_per_tool_table -x` | ❌ Wave 1 | ⬜ pending |
| 16-01-02 | 01 | 1 | TOOL-V2-04 / D-09 | status 颜色编码 OK/WARN(≤-2pp)/FAIL(≤-5pp)/GAIN(≥+5pp) | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_status_color_coding -x` | ❌ Wave 1 | ⬜ pending |
| 16-01-03 | 01 | 1 | TOOL-V2-04 / D-16 | LATEST 表底频次柱图 top-12 + others 聚合行 (`{tool}: ████████ 437`) | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_frequency_bars_aggregate_long_tail -x` | ❌ Wave 1 | ⬜ pending |
| 16-01-04 | 01 | 1 | TOOL-V2-04 / D-11 | per-segment sample_count <3 时 distribution 列渲染 `n/a` (avoid misleading averages) | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_distribution_n_a_when_sample_low -x` | ❌ Wave 1 | ⬜ pending |
| 16-02-01 | 02 | 2 | TOOL-V2-04 / D-05 | DIFF 区仅在传 `--baseline-run` + `--evolved-run` 时启用,缺一报错 exit 2 | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_diff_requires_both_runs -x` | ❌ Wave 2 | ⬜ pending |
| 16-02-02 | 02 | 2 | TOOL-V2-04 / D-06 | TREND 互斥 flag: `--trend-window` + `--trend-days` 同时传 → exit 2 | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_trend_window_days_mutex -x` | ❌ Wave 2 | ⬜ pending |
| 16-02-03 | 02 | 2 | TOOL-V2-04 / D-10 | TREND sparkline 字符序列 (▁▂▃▄▅▆▇█) + 跨 run min/p25/median/p75/max 摘要列 | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_trend_sparkline -x` | ❌ Wave 2 | ⬜ pending |
| 16-03-01 | 03 | 3 | TOOL-V2-04 / D-15 | ABStudy 三类计数 (think_on_saved / think_on_regressed / both_wrong) + top-3 例子 | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_ab_study_categories -x` | ❌ Wave 3 | ⬜ pending |
| 16-03-02 | 03 | 3 | TOOL-V2-04 / D-15 | ABStudy 渲染 task_description / reasoning_text_on 前过 `_contains_secret` redaction | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_ab_study_secret_redaction -x` | ❌ Wave 3 | ⬜ pending |
| 16-03-03 | 03 | 3 | TOOL-V2-04 / D-07 | source 启发顺序: think_ab_gate → reasoning, param_predictors_discovered → params, fallback → desc | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_source_detection -x` | ❌ Wave 3 | ⬜ pending |
| 16-03-04 | 03 | 3 | TOOL-V2-04 / D-08 | 缺 per_tool_*_rates → run dropped + dropped_runs[] | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_fallback_dropped_run -x` | ❌ Wave 3 | ⬜ pending |
| 16-03-05 | 03 | 3 | TOOL-V2-04 / D-08 | 缺 raw_predictions → distribution 列退化 n/a + stdout warning | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_fallback_no_raw_predictions -x` | ❌ Wave 3 | ⬜ pending |
| 16-03-06 | 03 | 3 | TOOL-V2-04 / D-08 | 缺 ab_comparison.json (reasoning source) → ABStudy 区不渲染该 run, stdout 不抱怨 | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_fallback_no_ab_comparison -x` | ❌ Wave 3 | ⬜ pending |
| 16-03-07 | 03 | 3 | TOOL-V2-04 / D-13 | warning threshold 默认 -2pp 触发 stdout 黄色警告且不影响 exit code (=0) | functional | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_warning_threshold_no_exit -x` | ❌ Wave 3 | ⬜ pending |
| 16-04-01 | 04 | 4 | TOOL-V2-04 / D-04+D-17 | E2E: 5 fixture run → dashboard.json schema (latest/diff/trend/ab_study/source_legend/dropped_runs/summary/warnings) | system | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_e2e_dashboard_json_schema -x` | ❌ Wave 4 | ⬜ pending |
| 16-04-02 | 04 | 4 | TOOL-V2-04 / D-04 | dashboard.json 落 CWD 默认 `dashboard_<YYYYMMDD_HHMMSS>.json`; `--output` 覆盖 | system | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_dashboard_json_output_path -x` | ❌ Wave 4 | ⬜ pending |
| 16-04-03 | 04 | 4 | TOOL-V2-04 / D-02 | 默认根 `output/tools/` + `output/tools_reasoning/` 都为空且无 `--runs` → exit 2 | system | `.venv/bin/pytest tests/tools/test_regression_dashboard.py::test_no_runs_exits_2 -x` | ❌ Wave 4 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/tools/test_persist_raw_predictions.py` — 覆盖 D-12 helper 不可变性 + 边界 (≥4 tests)
- [ ] `tests/tools/test_regression_dashboard.py` — 覆盖 Wave 1-4 dashboard 全部行为 (15-20 tests; 文件 Wave 0 创建占位 + Wave 1+ 逐步填)
- [ ] `tests/fixtures/dashboard_runs/` — 5 fixture runs:
  - `desc_old/metrics.json` — 缺 `per_tool_*_rates` (dropped 路径)
  - `params_complete/metrics.json` + `raw_predictions` (LATEST 主路径)
  - `reasoning_complete/metrics.json` + `ab_comparison.json` + `raw_predictions` (ABStudy 路径)
  - `reasoning_old/metrics.json` — Phase 15 现存 17 mock run 之一 (缺 raw_predictions, distribution n/a 路径)
  - `params_no_raw/metrics.json` — 有 per_tool_*_rates 但缺 raw_predictions (distribution 列退化路径)
- [ ] 现有 `tests/tools/test_evolve_tool_*.py` 三 CLI 集成测试加 Wave 0 字段断言 (小补丁,不新建文件)
- [ ] `tests/tools/test_tool_dataset.py` — 加 `test_dspy_example_has_difficulty` 断言 (扩 to_dspy_examples)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Rich Table 颜色编码视觉验证 (OK 默认 / WARN 黄 / FAIL 红 / GAIN 绿) | TOOL-V2-04 / D-09 | terminal stdout 颜色 ANSI escape 序列断言可做但脆弱; 视觉确认更稳 | `python -m evolution.tools.regression_dashboard --runs output/tools_reasoning` 在终端肉眼 review 颜色对应 |
| TREND sparkline 视觉对齐 | TOOL-V2-04 / D-10 | unicode block 字符在不同终端字体下宽度差异; 文本断言能验序列正确, 视觉要确认对齐 | 同上, 看 TREND 区每条 tool 的 sparkline 是否人眼可读 |
| 频次柱图 30 列宽归一化视觉 | TOOL-V2-04 / D-16 | Bar 长度由 max sample_count 归一化; 文本断言验比例正确, 视觉验观感 | 同上, 看柱图比例是否合理 |
| Holdout sample size 实数据回归提醒 | TOOL-V2-04 / Pitfall 10 | 当真实 holdout 数据 per-tool sample <10 时 distribution 列退化 `n/a`; 提醒未来扩 holdout 体量后回头看 | Phase gate: 跑实数据 dashboard, 统计 `n/a` 列占比, 若 >50% 在 STATE.md 记一笔 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies (manual items 已显式列出)
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (5 fixture run + 4 test files 已列)
- [ ] No watch-mode flags (`-x` fast-fail mode used; pytest watch 模式不在 CI 内)
- [ ] Feedback latency < 30s for quick command
- [ ] `nyquist_compliant: true` set in frontmatter (after planner 把所有 task IDs 落实)

**Approval:** pending — gsd-planner Wave 0 规划完成后回填 task IDs 与 status, gsd-plan-checker pass 后 sign off
