---
plan: 16-04-schema-e2e
phase: 16
status: complete
completed: 2026-05-14
requirements-completed: [TOOL-V2-04]
key-files:
  modified:
    - evolution/tools/regression_dashboard.py
    - tests/tools/test_regression_dashboard.py
    - .gitignore
---

## Wave 4 — dashboard.json schema 收口 + E2E 集成测试 + .gitignore 卫生

收口 Phase 16 全部范围:把 Wave 1-3 收集的 LATEST/DIFF/TREND/ABStudy 数据 + dropped_runs +
warnings + source_legend + summary 共 8 顶层字段序列化为 `dashboard.json`(D-04 双产物收口),
补 D-02 空根 exit 2 守门,unskip 最后 3 个 Wave 4 测试。**17 active tests 全绿,0 skipped。**

### Task 1 — `_write_dashboard_json` + main 收集 8 字段 + .gitignore — `c9dbf15` (feat)

**helper**:`_write_dashboard_json(output_path, *, scanned_runs, dropped_runs, latest_data,
diff_data, trend_data, ab_study_data, warnings_list, summary)` — 组装 `generated_at` +
`scanned_runs` 两个辅助字段 + 8 顶层字段,`json.dumps(payload, indent=2, sort_keys=True)`
写盘。

**main 编排改动**:
- `_render_latest` / `_render_diff` / `_render_trend` / `_render_ab_study` 的返回值收集为
  `latest_data` / `diff_data` / `trend_data` / `ab_study_data`
- 全分类扫描:每个 scanned run 要么 usable 要么 dropped,`latest_run` = 最新 usable;
  所有 unusable run(无论位置)都进 `dropped_runs[]`,给 dashboard.json 完整画面
- `latest_run is None` 不再 short-circuit `return 0` —— fall-through 到 dashboard.json
  写盘,即使 0 usable run 也能 dump dropped_runs 列表
- main 末尾:`--output` 显式路径覆盖默认 CWD `dashboard_<YYYYMMDD_HHMMSS>.json`

**.gitignore**:加 `dashboard_*.json`(CONCERNS §H4 —— 防 dashboard 落 repo root 被
git status 看到)。

### Task 2 — unskip + 实现 3 个 Wave 4 测试 — `7e30633` (test)

| Test | 守门点 |
|------|--------|
| `test_e2e_dashboard_json_schema` | 5 fixture run(desc_old + params_complete + params_no_raw + reasoning_complete + reasoning_old)→ main → dashboard.json 含 8 顶层字段 + `scanned_runs == 5` + `dropped_runs` 含 desc_old & reasoning_old(均缺 per_tool_*_rates) |
| `test_dashboard_json_output_path` | `--output` 显式路径写指定文件;无 `--output` → CWD 落 `dashboard_<ts>.json`,文件名匹配 `^dashboard_\d{8}_\d{6}\.json$` |
| `test_no_runs_exits_2` | patch `DEFAULT_ROOTS=()` + `_scan_runs=[]` + 无 `--runs` → `click.UsageError` → exit 2(D-02) |

### 验证结果

- `.venv/bin/pytest tests/tools/test_regression_dashboard.py` → **17 passed, 0 skipped**
- `.venv/bin/pytest tests/` → **493 passed, 1 xfailed**(Phase 13/14/15 零破坏)
- 真实 E2E:`python -m evolution.tools.regression_dashboard` 跑 `output/tools[_reasoning]/`
  → exit 0,扫 26 run、18 dropped、latest 已填,dashboard.json 16KB,8 顶层字段齐全

### 已知遗留

- `datetime.utcnow()` 触发 DeprecationWarning(Python 3.13)。代码按 16-04 计划模板原样
  落地;后续可换 `datetime.now(datetime.UTC)`,非本 wave 范围。
- `@pytest.mark.skip` grep 计数为 1 —— 是 module docstring 里对历史 stub 策略的文字描述,
  非真实装饰器(`0 skipped` 已确认)。

## Deviations from Plan

None —— 计划逐条执行。代码在工作树已完成但未提交、缺 SUMMARY;本次按用户决策将其拆为
2 个原子提交(feat + test)并补全 SUMMARY,未改动代码逻辑。

---
*Phase: 16-per-tool-regression-dashboard*
*Completed: 2026-05-14*
