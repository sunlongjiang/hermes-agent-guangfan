---
plan: 16-02-diff-trend
phase: 16
status: complete
completed: 2026-05-13
commits:
  - 945464c feat(16-02): add _sparkline + _render_diff + _render_trend + main orchestration (D-05/D-06/D-10 B)
  - (this) test(16-02): unskip + implement 3 Wave 2 tests (DIFF/TREND mutex/TREND sparkline)
key-files:
  modified:
    - evolution/tools/regression_dashboard.py
    - tests/tools/test_regression_dashboard.py
  created:
    - tests/fixtures/dashboard_runs/params_complete_v2/metrics.json
---

## Wave 2 — DIFF + TREND + sparkline

在 Wave 1 LATEST 骨架之上扩展 dashboard 两个区:DIFF 双 run 对比、TREND 跨
N run 时间序列 + sparkline + 分位数摘要。完成 Phase 16 dashboard 三大主区中的两个。

### Task 1 — helpers + main orchestration (945464c)

- **_sparkline**:8-char Unicode block(`▁▂▃▄▅▆▇█`),`min(7, int((v-lo)/span*8))` 保证不越界;
  empty list → `""`;single value(zero span)→ 全 `▁`。
- **_render_diff(D-05)**:为两个指定 run 渲染 5 列对比表(tool / baseline_run rate /
  evolved_run rate / delta_pp / status),颜色复用 LATEST 的 `_status_style`。
- **_render_trend(D-10 B)**:为每个工具收集跨 run 的 `evolved_rate` 时间序列,
  渲染 8 列表(tool / sparkline / min / p25 / median / p75 / max / n_runs)+ Panel legend
  说明跨 run 语义。
- **main 编排**:LATEST 渲染后追加 DIFF 与 TREND 编排块。
  - DIFF 单传约束:仅传 `--baseline-run` 或仅传 `--evolved-run` → stdout 黄色 hint
    + skip DIFF(不 abort,LATEST 继续渲染),exit code 仍 0。
  - TREND 窗口选择:`--trend-days N` 用 `Path(run["path"]).stat().st_mtime` cutoff;
    `--trend-window N`(默认 10)用 `valid_runs[-N:]` slice。
  - 互斥校验:`--trend-window` 与 `--trend-days` 同传 → `click.UsageError` → exit 2(D-06)。

### Task 2 — 3 Wave 2 tests unskip & implement

- `test_diff_requires_both_runs`:单传 yellow hint + 双传 DIFF 渲染
- `test_trend_window_days_mutex`:互斥触发 exit 2 + "mutually exclusive" 字符串
- `test_trend_sparkline`:跨 run 渲染 sparkline + min/p25/median/p75/max 5 列

`pytest tests/tools/test_regression_dashboard.py` → 7 passed + 10 skipped(Wave 3-4 占位)。

### DIFF 用 evolved_rate 而非 baseline_rate

D-05 amend 决策:DIFF 对比侧使用 `per_tool_evolved_rates` 而非 `per_tool_baseline_rates`。
理由:每 run 内部已经做了 baseline→evolved,跨 run 对比有意义的是「这 run 的最终 rate」
(即 evolved_rate)——把两个 run 的 evolved 拉到一起对比,语义是「cherry-pick 一个 run
作为新 baseline,另一个 run 是改进候选」。如果用 baseline_rate 对比,跨 run 的 baseline
通常是 v1 frozen / think-off,信息量小。

### TREND window 实现

- `trend-days`:`cutoff = now - days * 86400`,过滤 `metrics_path.stat().st_mtime >= cutoff`。
  使用 metrics.json 文件 mtime 而非 metrics 内 `timestamp` 字段,确保 backfilled run 也
  能按真实时间归类。
- `trend-window`:list slice `valid_runs[-N:]`;`_scan_runs` 已按 mtime 降序排过。
- 互斥:main 入口第一行 `if trend_window is not None and trend_days is not None: raise click.UsageError`。

### sparkline 退化

空 list → 空串(`""`);单值或全相同 → `(hi - lo) or 1.0` 保证 span 非零,
所有 char 落到 `▁`;算法 `min(7, ...)` 保证最大 char 索引不越界。

Wave 2 完成,Wave 3 可在 LATEST/DIFF/TREND 之上扩展 ABStudy + 跨 CLI source 标注 + fallback。
