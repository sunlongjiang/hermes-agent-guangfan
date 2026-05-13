---
plan: 16-03-abstudy-source-fallback
phase: 16
status: complete
completed: 2026-05-13
key-files:
  modified:
    - evolution/tools/regression_dashboard.py
    - tests/tools/test_regression_dashboard.py
  created:
    - tests/fixtures/dashboard_runs/reasoning_with_secret/metrics.json
    - tests/fixtures/dashboard_runs/reasoning_with_secret/ab_comparison.json
    - tests/fixtures/dashboard_runs/json_corrupt/metrics.json
    - tests/fixtures/dashboard_runs/params_multi_regress/metrics.json
---

## Wave 3 — ABStudy + secret redact + 三类 fallback + warning gate

收口 dashboard 三大主区(LATEST/DIFF/TREND)外的 ABStudy 第四区,叠加 D-08 三类 fallback 与
D-13 warning 阈值不影响 exit code 的双 case 守门。Wave 1+2+3 共 14 active tests 全绿。

### Task 1 — 新增 3 helpers + main 编排 + 4 fixtures

**helpers**:
- `_safe_truncate(text, max_len=80)`:含 secret(经 `_contains_secret`)→ `[REDACTED — secret-like content]`;否则 truncate + `...` 后缀。
- `_count_ab_categories(ab_records)`:D-15 三类计数 + 各类 top-3。
  - saved: `is_correct_off=False AND is_correct_on=True`,按 reasoning_text_on 长度 DESC 排
  - regressed: `is_correct_off=True AND is_correct_on=False`,按 task_description 长度 DESC 排
  - both_wrong: `is_correct_off=False AND is_correct_on=False`,任意序
  - 「both_right」不作为类别(Phase 16 只 surface deltas)
- `_render_ab_study(reasoning_runs)`:渲染 3 列汇总 Table + 每 run 一个 top-3 Panel。

**main 编排**:在 Wave 2 TREND 渲染之后追加 ABStudy、warnings、详细 dropped 列表。

**4 fixtures**:
- `reasoning_with_secret/metrics.json` + `ab_comparison.json`:reasoning source + 3 ab records,record 0 / 1 的 `reasoning_text_on` 含 AWS access key `AKIAIOSFODNN7EXAMPLE`,record 0 的 `task_description` 含 `sk-...` API key,均触发 `_contains_secret` 而被 redact(W3 fix)
- `json_corrupt/metrics.json`:故意非法 JSON,触发 `_load_run` 的 `_drop_reason` 路径
- `params_multi_regress/metrics.json`(B3 fix):params source,3 个负向 delta(read_file -0.5pp、browser_navigate -5.0pp、edit_file -1.5pp),为 warning-threshold 严苛阈值测试供数

### Task 2 — unskip + 实现 7 个 Wave 3 测试

| Test | 守门点 |
|------|--------|
| `test_ab_study_categories` | reasoning_complete fixture 渲染 3 类计数 + Panel 标签 |
| `test_ab_study_secret_redaction` | sk- key + AKIA AWS key 双字段双断言不泄漏 + REDACTED 标签出现(W3 fix) |
| `test_source_detection` | `_detect_source` 单元测试 7 case(reasoning 优先 / desc / None / 目录名 fallback) |
| `test_fallback_dropped_run` | desc_old(缺 per_tool_*_rates)→ dropped 段落出现 |
| `test_fallback_no_raw_predictions` | params_no_raw → LATEST 渲染 + distribution disabled 黄色 hint + n/a 出现 |
| `test_fallback_no_ab_comparison` | reasoning_old(无 ab + 无 per_tool)→ ABStudy 段不出现 |
| `test_warning_threshold_no_exit` (B3) | Case A: params_complete + 2.0pp → 1 WARNING + exit 0; Case B: params_multi_regress + 0.1pp → ≥3 WARNINGs + exit 0 |

`pytest tests/tools/test_regression_dashboard.py` → **14 passed + 3 skipped**(Wave 4 stubs)。

### ABStudy top-3 排序键确认

| 类别 | 排序键 | 语义 |
|------|--------|------|
| saved | `len(reasoning_text_on)` DESC | 最长 reasoning = 最有解释力的 think-on 救场 |
| regressed | `len(task_description)` DESC | 最长 task = 最可能是难题，回归值得分析 |
| both_wrong | unsorted | 没有引导性排序;两路都失败属于「数据集 / 工具集 问题」类别 |

### Secret redact 实测命中模式

| 模式 | 字段 | 命中路径 |
|------|------|----------|
| `sk-1234567890abcdefghijklmnopqrstuvwxyz0123456789ABCD` | `task_description` (record 0) | SECRET_PATTERNS 的 `sk-` 前缀 + 50 字符长度 |
| `AKIAIOSFODNN7EXAMPLE` | `reasoning_text_on` (records 0, 1) | SECRET_PATTERNS 的 AWS 模式 (`AKIA[A-Z0-9]{16}`) + Shannon entropy heuristic |

W3 fix 让两字段都覆盖了 `_safe_truncate` 调用路径——test 断言 `REDACTED` 出现 + 两 secret 字符串都不在 stdout。

### D-13 warning 不影响 exit code(B3 fix 双 case)

| Case | Fixture | 阈值 | 期望 WARNING: 数 | 期望 exit |
|------|---------|------|------------------|-----------|
| A | params_complete | 2.0pp | 1(browser_navigate -5pp) | 0 |
| B | params_multi_regress | 0.1pp | ≥3(read_file -0.5pp / browser_navigate -5pp / edit_file -1.5pp) | 0 |

如果未来有人「智能化」加上 `if len(warnings_list) > N: return 1`,Case A 仍过(1<N),Case B 立即挂(3≥N)。双 case 共同守门。

### params_multi_regress 数学验证

| tool             | baseline | evolved | delta_pp | Case B (≤ -0.1pp) |
|------------------|----------|---------|----------|-------------------|
| search_files     | 0.80     | 0.84    | +4.0     | gain — skip       |
| read_file        | 0.85     | 0.845   | -0.5     | **WARNING:**      |
| browser_navigate | 0.50     | 0.45    | -5.0     | **WARNING: + FAIL** |
| edit_file        | 0.92     | 0.905   | -1.5     | **WARNING:**      |
| list_files       | 0.90     | 0.92    | +2.0     | gain — skip       |

Wave 3 完成,Wave 4 收口 `dashboard.json` schema + E2E + .gitignore。
