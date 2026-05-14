---
phase: 16-per-tool-regression-dashboard
status: complete
completed: 2026-05-14
requirements-completed: [TOOL-V2-04]
subsystem: testing
tags: [dashboard, regression, rich, cli, metrics, raw_predictions]
provides:
  - "standalone CLI: python -m evolution.tools.regression_dashboard"
  - "per-tool selection-rate regression tracking across optimization runs"
  - "dashboard.json 8-field schema (latest/diff/trend/ab_study/source_legend/dropped_runs/summary/warnings)"
  - "raw_predictions + per_tool_*_rates wired into all 3 evolve_tool_* CLIs"
affects: [phase-17, phase-22]
key-files:
  created:
    - evolution/tools/regression_dashboard.py
    - tests/tools/test_regression_dashboard.py
    - tests/tools/test_persist_raw_predictions.py
    - tests/fixtures/dashboard_runs/
  modified:
    - evolution/tools/tool_metric.py
    - evolution/tools/tool_dataset.py
    - evolution/tools/evolve_tool_params.py
    - evolution/tools/evolve_tool_descriptions.py
    - evolution/tools/evolve_tool_reasoning.py
    - .gitignore
---

# Phase 16: Per-Tool Regression Dashboard Summary

**Standalone Rich-CLI dashboard tracking per-tool selection-rate regressions across optimization runs — LATEST/DIFF/TREND/ABStudy 四区 stdout + dashboard.json 双产物,raw_predictions schema 接线到全部三个 evolve_tool_* CLI。**

## 交付清单

| 维度 | 交付 |
|------|------|
| Waves | 5(Wave 0 数据基础 → Wave 1 骨架+LATEST → Wave 2 DIFF+TREND → Wave 3 ABStudy+fallback → Wave 4 schema 收口) |
| Plans | 5/5 PLAN.md 全部 executed,5 plan SUMMARY + 本 phase SUMMARY |
| 主文件 | `evolution/tools/regression_dashboard.py` 788 LoC(CLI + 15 helper + main 编排) |
| 测试 | `test_regression_dashboard.py` 17 active tests(0 skipped)+ `test_persist_raw_predictions.py` Wave 0 helper 测试 |
| Fixtures | `tests/fixtures/dashboard_runs/` 11 文件(9 metrics.json + 2 ab_comparison.json) |
| Schema 接线 | `persist_raw_predictions` + `persist_per_tool_rates` 接入 evolve_tool_params / descriptions / reasoning 三 CLI(D-12) |

## ROADMAP Phase 16 成功标准对照

| # | 成功标准 | 落地 |
|---|----------|------|
| 1 | Metrics file records per-tool accuracy before and after optimization | Wave 0(16-00):`persist_per_tool_rates` 接线到全部三 CLI + `persist_raw_predictions` 新 helper,metrics.json 写 `per_tool_baseline_rates` / `per_tool_evolved_rates` / `raw_predictions` |
| 2 | Rich console dashboard shows selection rate changes per tool | Wave 1(16-01)LATEST 区 per-tool 表 12 列 + 频次柱图;Wave 2(16-02)DIFF + TREND 区;Wave 3(16-03)ABStudy 区 |
| 3 | Regression threshold configurable (default: 2pp drop triggers warning) | Wave 3(16-03)`--warning-threshold-pp`(默认 -2pp),D-13 warning 不影响 exit code |

## D-01..D-17 决策落地对照

| D | 决策 | 落地 wave |
|---|------|-----------|
| D-01 | standalone CLI,不动 evolve_* 入口 | W1 |
| D-02 | 默认扫 output/tools[_reasoning]/,空根无 --runs → exit 2 | W1 部分 / W4 守门 |
| D-03 | stdout Rich Table + dashboard.json 双产物 | W1-W4 |
| D-04 | dashboard.json 落 CWD `dashboard_<ts>.json`,--output 覆盖 | W4 |
| D-05 | 三区视图 LATEST/DIFF/TREND | W1-W2 |
| D-06 | TREND --trend-window / --trend-days 互斥 | W2 |
| D-07 | 跨 CLI source 合并 + baseline 语义 legend | W3 |
| D-08 | schema 兼容:三类 fallback(dropped / n/a / 无 ab) | W3 |
| D-09 | LATEST 12 字段 + OK/WARN/FAIL/GAIN 颜色编码 | W1 |
| D-10 | distribution 双层语义都做(LATEST 段内 / TREND 跨 run) | W1 + W2 |
| D-11 | segment 切片 difficulty / pool_size,raw_predictions 喂数 | W0 + W1 |
| D-12 | schema 扩展在范围内:三 CLI 接 persist helpers | W0 |
| D-13 | warning 门 -2pp,不返 exit code | W3 |
| D-14 | [deferred] 不实现 p25-based hard gate | — informational |
| D-15 | ABStudy 三类计数 + top-3 + secret redact | W3 |
| D-16 | LATEST sample_count 列 + 频次柱图 top-12 + others 聚合 | W1 |
| D-17 | 全包括 + 分 5 Wave 组织 | W0-W4 |

## Pitfall 10「distribution 双层语义」收口确认

- **语义 A(LATEST / DIFF)**:`min/p25/median/p75/max` = 单 run 内 `raw_predictions` 按
  `--segment difficulty|pool_size` 切片后的 per-segment evolved_rate 序列。
- **语义 B(TREND)**:`min/p25/median/p75/max` = 跨 N 个 run 的 evolved_rate 时间序列分布
  (cross-run,非 within-run segment),stdout TREND legend Panel 显式说明。
- per-tool sample_count < 3 时 distribution 列退化 `n/a`(D-11 / 16-01-04),避免误导性均值。
- D-14 明确不做 p25-based hard gate:当前 holdout per-tool sample 通常 < 20,p25 方差大,
  先靠 dashboard warning + 人工 review,归 deferred。

## VALIDATION.md task verification

23 个 per-task verification 全部覆盖并 green:
- 16-00-01..06(6)— Wave 0 helper 不可变性 / 边界 / difficulty 字段 / 三 CLI metrics 接线
- 16-01-01..04(4)— LATEST 表 / 颜色编码 / 频次柱图 / distribution n/a
- 16-02-01..03(3)— DIFF 双 run 必填 / TREND flag 互斥 / sparkline
- 16-03-01..07(7)— ABStudy 三类 / secret redact / source 启发 / 三类 fallback / warning 不影响 exit
- 16-04-01..03(3)— E2E dashboard.json schema / 输出路径 / 空根 exit 2

`.venv/bin/pytest tests/` → **493 passed, 1 xfailed**(Phase 13/14/15 零破坏)。

## 实测 dashboard(真实 output/tools[_reasoning]/)

`python -m evolution.tools.regression_dashboard --output /tmp/dashboard_smoke.json`:
- exit 0,stdout 渲染 source legend Panel + LATEST 表 + 频次柱图 + TREND legend + TREND 表
  + ABStudy 表 + 详细 dropped 列表
- 扫描 26 run,18 dropped(多为 Phase 15 现存 reasoning run 缺 `per_tool_*_rates`,
  及 1 个 `FAILED_*` unknown source)
- `dashboard.json` 16KB,8 顶层字段齐全(`ab_study/diff/dropped_runs/latest/source_legend/
  summary/trend/warnings` + `generated_at/scanned_runs`)
- 印证 D-12 的必要性:若未接线 persist helpers,90% 现存 run 会全进 dropped_runs

## 已知遗留 / 后续优化

- `datetime.utcnow()` 在 Python 3.13 触发 DeprecationWarning(W4 按计划模板原样落地)—
  后续可换 `datetime.now(datetime.UTC)`。
- D-14 p25-based hard gate 归 deferred,待 Phase 14 session 数据 + Phase 19 prompt 数据
  扩 holdout 体量后再评估。
- 真实数据 18/26 run 落 dropped — 多为 Phase 16 接线之前产出的旧 run;新优化 run 会带
  完整 schema。Manual-only 验证项「n/a 列占比 > 50% 在 STATE.md 记一笔」可在后续 phase
  gate 复查。

## Next Phase Readiness

- Phase 17(Joint Section Optimization)依赖 Phase 16 的 regression tracking 基础设施已就位。
- dashboard.json 8-field schema 为 Phase 22(Continuous Evolution Loop)的回归门提供机器可读
  产物。

---
*Phase: 16-per-tool-regression-dashboard*
*Completed: 2026-05-14*
