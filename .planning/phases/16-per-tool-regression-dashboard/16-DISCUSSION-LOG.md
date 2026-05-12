# Phase 16: Per-Tool Regression Dashboard - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-12
**Phase:** 16-per-tool-regression-dashboard
**Areas discussed:** CLI 形态 & 调用时机, 数据源 & 历史范围, 指标深度 (Pitfall 10 收口), 范围扩展 (Phase 14/15 deferred)

---

## Gray Area 1 — CLI 形态 & 调用时机

### Q1.1 Phase 16 的主入口怎么设？

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone CLI 为主 | 仅一个 `python -m evolution.tools.regression_dashboard` 独立入口；与 evolve_* 管道正交 | ✓ |
| Standalone + evolve_* inline summary | 主 standalone + evolve_* 末尾默认调 dashboard 输出 panel；`--no-dashboard` opt-out | |
| 仅 evolve_* inline | 不起独立入口，只在 evolve_* 末尾渲染；不能跨 run 比对 | |
| Standalone，不动 evolve_* | 仅独立 CLI，evolve_* 不变 | |

**User's choice:** Standalone CLI 为主
**Notes:** 用户选了与「Standalone，不动 evolve_*」语义近似但更明确的「Standalone CLI 为主」。后续问题验证了不在 evolve_* 末尾自动调 dashboard 的意图。

---

### Q1.2 Standalone CLI 怎么拿输入？

| Option | Description | Selected |
|--------|-------------|----------|
| 默认扫描两个预设根 + --runs 覆盖 | 默认 `output/tools/` + `output/tools_reasoning/`；`--runs <path>` 覆盖 | ✓ |
| 必填 --runs | 不扫描默认目录 | |
| 递归扫描 output/根 | 全 output/ 下所有 metrics.json，自动跳过无 per_tool_* 字段 | |
| 三模式 flag：run / diff / history | --run 单 / --baseline+--evolved 双 / --history 历史 | |

**User's choice:** 默认扫描两个预设根 + --runs 覆盖
**Notes:** 默认行为 + 显式覆盖。但 D-05 三区视图（LATEST/DIFF/TREND）实际上吸收了「三模式」选项的所有能力，只是输入路径以默认根为入口。

---

### Q1.3 Dashboard 输出到哪里？

| Option | Description | Selected |
|--------|-------------|----------|
| 仅 stdout | Rich Table only，不落盘 | |
| stdout + dashboard.json | 双产物，JSON 含 per_tool_changes / regressed_tools / improved_tools / summary | ✓ |
| stdout + .json + .md | 三产物，含人读 .md | |
| stdout + 补入 metrics.json | 写回 evolve 产物（违反只读原则） | |

**User's choice:** stdout + dashboard.json
**Notes:** 双产物兼顾人读 + 下游消费 + CI parse；.md 暂不做。

---

### Q1.4 dashboard.json 写到哪个目录？

| Option | Description | Selected |
|--------|-------------|----------|
| CWD/dashboard_<ts>.json | 写当前工作目录 | ✓ |
| output/dashboards/<ts>/dashboard.json | 与 Phase 5/13/15 输出布局一致 | |
| output/dashboards/<ts>/ + latest.json 软连 | + 软连 latest 给 CI 用 | |
| 必填 --output | 显式指定 | |

**User's choice:** CWD/dashboard_<ts>.json
**Notes:** 简洁优先，dashboard 默认对调用者最近，与 evolve_* 主产物在 output/ 下保持物理分离。

---

## Gray Area 2 — 数据源 & 历史范围

### Q2.1 Dashboard 能看多远？

| Option | Description | Selected |
|--------|-------------|----------|
| 单 run 模式 | 仅看最新一次 metrics.json | |
| 单 + 双 run diff | + --baseline-run / --evolved-run | |
| 三区：LATEST + DIFF + TREND | + sparkline 跨 N 个 run | ✓ |
| 三区 + SQLite history | + history 库（CONCERNS M3 retention） | |

**User's choice:** 三区：LATEST + DIFF + TREND
**Notes:** Pitfall 10 retention/趋势思路覆盖；SQLite 留 Phase 22。

---

### Q2.2 TREND 区看多久的历史？

| Option | Description | Selected |
|--------|-------------|----------|
| 定数 N 个 run（默认 10） | --trend-window N | |
| 近 D 天（默认 30） | --trend-days D | |
| 二选一 flag | 同时提供两个 flag，互斥；默认 N=10 | ✓ |
| 全加载，表面取 5 | 不限边界 | |

**User's choice:** 二选一 flag
**Notes:** 默认 N=10，显式传 --trend-days 时切换；同时传两个则报错 exit 2。

---

### Q2.3 如何处理 evolve_tool_descriptions / params / reasoning 三个 CLI 的 metrics？

| Option | Description | Selected |
|--------|-------------|----------|
| 全跨 CLI 合并 | 统一 per-tool 表，source 列标 params/desc/reasoning | ✓ |
| 只合并 output/tools/, reasoning opt-in | --include-reasoning 才纳入 | |
| 按 source 拆子表 | 三张子表 | |
| 仅 output/tools/, reasoning 推后 | reasoning 推 deferred | |

**User's choice:** 全跨 CLI 合并
**Notes:** baseline 含义不同需 legend 标注（desc/params=v1 frozen, reasoning=think-off）。

---

### Q2.4 如果跨 CLI 合并但 evolve_tool_descriptions 还没写 per_tool_*_rates，Phase 16 负责补吗？

| Option | Description | Selected |
|--------|-------------|----------|
| 仅读，缺字段跳过 | dashboard 不动 evolve_*，老 run 缺字段整跳过 | ✓ |
| 补全 evolve_* 中缺失的持久化 | 让三 CLI 输出同构 | |
| 只补 evolve_tool_descriptions | 折中 | |

**User's choice:** 仅读，缺字段跳过
**Notes:** ⚠ 这条与 Q3.3「持久化 raw_predictions」表面冲突；冲突收口写入 CONTEXT.md D-08 + D-12：dashboard 仅读老字段，但 raw_predictions 是 Phase 16 范围内新增的字段（schema 扩展），属于 Phase 16 必做。老字段的回填（per_tool_*_rates 补给 evolve_tool_descriptions 老路径）不做。

---

## Gray Area 3 — 指标深度 (Pitfall 10 收口)

### Q3.1 Per-tool 表要丰到什么程度？

| Option | Description | Selected |
|--------|-------------|----------|
| 最小集 | baseline / evolved / delta / status | |
| 最小集 + sample_size | 加 sample_size 列（破仅读原则） | |
| + 按 difficulty 切片 | per-tool × per-difficulty 二维 | |
| + Pitfall 10 全量 distribution | min / p25 / median / p75 / max + 持久化 raw_predictions | ✓ |

**User's choice:** + Pitfall 10 全量 distribution
**Notes:** 这条选择直接触发 Q2.4 的 schema 冲突收口（见 D-12）。

---

### Q3.2 Pitfall 10 distribution 是哪种？（澄清问）

| Option | Description | Selected |
|--------|-------------|----------|
| 语义 A：跨 task 切片 | 单 run 内不同 segment 分布（Pitfall 10 原意） | |
| 语义 B：跨 run 历史 | 同工具历史 evolved_rate 序列分布 | |
| 两个都要 | A 在 LATEST/DIFF + B 在 TREND | ✓ |
| 仅 B，A 推后 | 仅跨 run，零 schema 扩展 | |

**User's choice:** 两个都要
**Notes:** 双层 distribution 同时落，需要 raw_predictions 持久化（语义 A）+ 跨 run aggregation（语义 B）。

---

### Q3.3 「跨 task 切片」(语义 A) 的 segment 怎么定？

| Option | Description | Selected |
|--------|-------------|----------|
| 仅 difficulty | 复用 ToolSelectionExample.difficulty 字段 | |
| 仅 candidate pool size | len(available_tools) 分桶 | |
| difficulty + candidate pool size | 双维 + metrics.json 双字段 | |
| 持久化 raw_predictions，dashboard 动态切 | --segment difficulty | pool_size 灵活 | ✓ |

**User's choice:** 持久化 raw_predictions，dashboard 动态切
**Notes:** 未来加 segment 维度零改 evolve_*；metrics.json 体积增大风险已记入 Specifics（>2000 行 stdout warn）。

---

### Q3.4 Warning 可观察能到 hard gate 改造吗？

| Option | Description | Selected |
|--------|-------------|----------|
| Dashboard 仅 warning，不返 exit code | 与 Phase 13 现有 hard 门职责分离 | ✓ |
| 默认 warning + --strict exit 1 | --strict 触发 CI fail | |
| 默认 p25 hard gate | Pitfall 10 双中门 | |
| warning + --strict，p25 门推后 | 折中 | |

**User's choice:** Dashboard 仅 warning，不返 exit code
**Notes:** Phase 13 现有 mean-based 2pp 硬门继续单独跑；p25-based hard gate 留 deferred（D-14）。

---

## Gray Area 4 — 范围扩展 (Phase 14 / 15 deferred)

### Q4.1 要不要把 Phase 15 的 ab_comparison.json 错例分析合入 Phase 16 dashboard？

| Option | Description | Selected |
|--------|-------------|----------|
| 及。Phase 15 ab 错例分析合入 dashboard | ABStudy 区 + top-3 例子 | ✓ |
| 不及。Phase 15 ab 错例推 deferred | 仅检测 + stdout 提示 | |
| 部分。仅补 ab_summary 到 JSON | JSON 字段加 counts，不渲染 Rich Table | |

**User's choice:** 及。Phase 15 ab 错例分析合入 dashboard
**Notes:** ABStudy 区展示 think-on 救回 / 反错 / 双错 三类计数 + top-3 例子摘要（D-15）。

---

### Q4.2 要不要呈 Phase 14 提到的工具调用频次不均衡？

| Option | Description | Selected |
|--------|-------------|----------|
| 及。加 sample_count 列 + 表底 工具频次分布柱图 | 复用 raw_predictions 零额外 schema | ✓ |
| 不及。Phase 14 deferred 推后 | 等 session_miner 跑起来再说 | |

**User's choice:** 及。加 sample_count 列 + 表底 工具频次分布柱图
**Notes:** Rich BarColumn 风格，limit 12 行 + 长尾聚合（D-16）。

---

### Q4.3 Phase 16 总合交付范围怎么划？

| Option | Description | Selected |
|--------|-------------|----------|
| 全包括，分 Wave 实施 | 4 部分一次交付，多 Wave 组织 | ✓ |
| Phase 16 仅 v1 骨架，二期拆 phase | 拆 Phase 16.5 / 下一 phase | |
| 全包括，不分 Wave 交 planner | 单 PLAN.md，由 planner 决定切分 | |

**User's choice:** 全包括，分 Wave 实施
**Notes:** Plan 应以多 Wave 组织（D-17 给出 5 Wave 建议骨架），细节由 gsd-planner 决定。

---

## Claude's Discretion

- `dashboard.json` 顶层字段名（D-04 / D-12 给出 schema 草稿，planner 可微调）。
- Rich Table 颜色编码细节（OK / WARN / FAIL / GAIN 基调由 context 锁定，具体 hex / Rich style 名由 planner 选）。
- TREND sparkline 字符集合（建议 `▁▂▃▄▅▆▇█`）。
- 老 run 自动检测的启发：metrics.json 字段集 + 目录名 fallback 顺序。
- ABStudy top-3 排序键（建议「按 reasoning 长度倒序 + 任务难度倒序」）。
- `persist_raw_predictions` 字段精确名（建议 correct_tool / selected_tool / difficulty / num_available_tools，planner 在 Wave 0 测试中 pin）。
- Segment `pool_size` 分桶边界（默认 1-3 / 4-7 / 8+）。
- Wave 切分细粒度（D-17 给出 5 Wave 建议骨架，planner 可压成 4 Wave 或拆成 6 Wave）。

## Deferred Ideas

（完整列表见 CONTEXT.md `<deferred>` 区，节录 Phase 16 期间提及但推后的核心项：）

- p25-based hard gate（D-14 推后）
- SQLite history DB / 90 天 / 1000 run cap retention
- evolve_* CLI inline summary（dashboard 仅 standalone 调用）
- `--strict` exit 1 / CI 集成（Phase 22 持续进化循环）
- skill / prompt 管道的 dashboard 化（Phase 17 / 18 后再考虑）
- Reasoning 错例自动 issue / repair skill（Phase 22+）
- per_tool_*_rates 回填 evolve_tool_descriptions 历史 run（不做）
- Pool size 分桶自适应 / quantile-based 分桶
- Rich Live / 交互式 dashboard（Phase 22 持续进化循环）
- 多 source baseline 含义对齐 / cross-source 比较 normalization
