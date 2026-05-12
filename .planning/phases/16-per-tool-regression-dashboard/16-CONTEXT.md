# Phase 16: Per-Tool Regression Dashboard - Context

**Gathered:** 2026-05-12
**Status:** Ready for planning

<domain>
## Phase Boundary

为 evolve_tool_descriptions / evolve_tool_params / evolve_tool_reasoning 三条管道交付一个 **standalone Rich console + JSON 仪表盘**，从各自 `metrics.json`（及 Phase 15 `ab_comparison.json`）读取 per-tool 选择率，按 LATEST / DIFF / TREND 三区呈现 baseline → evolved 的变化与跨 run 的趋势，对回归（默认 -2pp）触发 stdout warning。覆盖 ROADMAP §Phase 16 / TOOL-V2-04，并显式承接 PITFALLS Pitfall 10 与 CONCERNS §M3 的「dashboard 聚合」缺口。

**In scope:**
- 新建 `evolution/tools/regression_dashboard.py` (Click + Rich)，命令 `python -m evolution.tools.regression_dashboard`。
- 三区视图：LATEST（最新 run per-tool 表）、DIFF（两 run 对比）、TREND（跨 N run 的工具 evolved_rate 序列 sparkline）。
- 跨 CLI 合并：默认扫描 `output/tools/` + `output/tools_reasoning/` 两个预设根，运行来源列标注 `source ∈ {desc, params, reasoning}`，baseline 含义不同需 legend 标注。
- 双层 distribution（Pitfall 10）：
  - 语义 A：单 run 内跨 task segment（按 `difficulty` / `num_available_tools`）动态切片，在 LATEST/DIFF 表展示 min/p25/median/p75/max。
  - 语义 B：跨历史 run 的同一工具 evolved_rate 序列，在 TREND 区展示分布与 sparkline。
- evolve_* CLI **schema 扩展**（属于本 phase 范围）：三 CLI 在 holdout 评估完成后，往 metrics.json 写新字段 `raw_predictions: list[{correct_tool, selected_tool, difficulty, num_available_tools}]`。共用 helper `evolution.tools.tool_metric.persist_raw_predictions()`，模式对齐 Phase 13 的 `persist_per_tool_rates`。
- ABStudy 区：检测到 `output/tools_reasoning/<ts>/ab_comparison.json` 时，汇总 think-on 救回 / think-on 反错 / 二者都错 三类计数 + top-3 例子摘要。
- 频次柱状图：在 LATEST 表底部按 `sample_count` 渲染 Rich `BarColumn`-风格水平柱（Phase 14 deferred 的工具调用不均衡可视化）。
- Warning 门：默认 -2pp 触发 stdout 黄色警告（`--warning-threshold-pp` 可调），**不返 exit code**，不影响 Phase 13 现有 `CrossToolRegressionChecker` 硬门。
- 输出：stdout Rich Table 三区 + `dashboard.json`（落 CWD 下 `dashboard_<ts>.json`，schema 含 per_tool_changes / regressed_tools / improved_tools / distribution_stats / ab_summary / sample_counts / source_legend / dropped_runs）。
- 老 run 缺 raw_predictions 时：dashboard fall back 到「LATEST 表 baseline_rate / evolved_rate / delta 仅显示，distribution 列出 `n/a`」+ stdout 一行 `[yellow]raw_predictions absent in <ts>; distribution disabled for this run[/yellow]`。
- 老 run 缺 per_tool_baseline_rates / per_tool_evolved_rates（如 evolve_tool_descriptions 历史 run）：整 run 跳过，summary 中报 `dropped_runs[]`。

**Out of scope:**
- p25-based hard-gate / exit code（deferred；Phase 13 的 mean-based 2pp 硬门继续单独跑）。
- SQLite / DB-backed history 存储（Pitfall 10 retention：90 天 / 1000 run cap 的硬约束）。
- 给 evolve_* CLI 加 `--dashboard` inline summary flag（dashboard 仅 standalone 调用）。
- skill / prompt 管道的 dashboard 化（本 phase 仅工具维度）。
- Reasoning 错例修复 / 自动 issue 创建（Phase 15 deferred 中比错例分析更进一步的部分）。
- evolve_tool_descriptions / evolve_tool_reasoning 写 `per_tool_baseline_rates` / `per_tool_evolved_rates`（**本 phase 不补**；只补 `raw_predictions` 一个字段；前者老路径仍走「整 run 跳过 + dropped_runs 列表」）。
- ROADMAP / state.md 的 dashboard `--strict` 模式（即使留 `--strict` flag 槽位也仅作为 deferred 的占位）。

</domain>

<decisions>
## Implementation Decisions

### CLI 形态 & 调用时机
- **D-01:** 主入口为 standalone CLI `python -m evolution.tools.regression_dashboard`。**不动** evolve_tool_descriptions / evolve_tool_params / evolve_tool_reasoning 的入口行为；不在它们末尾自动调 dashboard。Rationale：dashboard 是只读分析工具，与优化管道职责分离；evolve_* CLI 已经各自有详细 stdout（Phase 5/13/15），再加 dashboard 段会膨胀。
- **D-02:** 输入：默认扫描 `output/tools/` + `output/tools_reasoning/` 两个预设根。`--runs <path>` 可重复传以覆盖默认或追加额外目录（多次出现累加）。当默认根为空且未传 `--runs` 时直接 stdout 报错并 exit 2。
- **D-03:** 输出：stdout Rich Table（LATEST + DIFF + TREND + ABStudy）+ `dashboard.json` 双产物。
- **D-04:** `dashboard.json` 落 **CWD**，文件名 `dashboard_<YYYYMMDD_HHMMSS>.json`（与 Phase 5/13 的 ts 格式一致）。`--output <path>` 可显式指定路径覆盖默认。

### 数据源 & 历史范围
- **D-05:** **三区视图**：
  - **LATEST**：扫描结果按 mtime 排序后取最新一个 metrics.json，单 run per-tool 表 + 单 run 内 distribution（语义 A）。
  - **DIFF**：仅在传 `--baseline-run <path-or-ts>` 与 `--evolved-run <path-or-ts>` 时启用；二者都需指向单个 run 目录。两 run per-tool 双对比 + distribution diff。
  - **TREND**：扫描结果中所有 run 的同工具 evolved_rate 序列；按 D-06 窗口约束。
- **D-06:** TREND 窗口：互斥两 flag：`--trend-window N`（默认 10，按 mtime 取最近 N）与 `--trend-days D`（按 mtime 过滤近 D 天）。同时传则 stdout 报错 exit 2。
- **D-07:** 跨 CLI **全合并**：output/tools/ 和 output/tools_reasoning/ 的 run 进同一表，`source` 列分别标 `desc` / `params` / `reasoning`，由 metrics.json 中的现有字段（如 reasoning 区有 `think_ab_gate`）自动判定，无字段则 fallback 到目录名启发。表头脚注 / Rich Panel legend 显式说明 baseline 含义差异：「desc/params source 的 baseline = v1 frozen；reasoning source 的 baseline = think-off」。
- **D-08:** schema 兼容策略：dashboard **仅读 metrics.json 现有 + Phase 16 新增 raw_predictions 字段**。
  - 缺 `per_tool_baseline_rates` / `per_tool_evolved_rates`：**整 run 跳过**，stdout 一行 warning，summary 块的 `dropped_runs: list[str]` 记录 ts 与原因。
  - 缺 `raw_predictions`（老 run 没有）：**仅退化 distribution**，per-tool 双点 + delta 仍显示。
  - 缺 `ab_comparison.json`（仅 reasoning source 必须）：ABStudy 区不渲染该 run，stdout 不抱怨。

### 指标深度 (Pitfall 10 收口)
- **D-09:** 每个工具的展示字段在 LATEST 区：`source`, `tool`, `baseline_rate`, `evolved_rate`, `delta_pp`, `sample_count`, `min`, `p25`, `median`, `p75`, `max`, `status`。其中 `min/p25/median/p75/max` 来自单 run 内 raw_predictions 按 `--segment difficulty|pool_size`（默认 `difficulty`）动态切片后的 per-segment evolved_rate 序列。`status ∈ {OK✅, WARN⚠️ (delta ≤ -2pp), FAIL❌ (delta ≤ -5pp), GAIN✨ (delta ≥ +5pp)}`，颜色编码 OK=默认 / WARN=黄 / FAIL=红 / GAIN=绿。
- **D-10:** **distribution 双层语义都做**：
  - 语义 A：单 run 内跨 task segment 切片（D-09 的 min/p25/.../max 列）。
  - 语义 B：跨 run 历史的同工具 evolved_rate 序列（在 TREND 区展示，Rich 文本 sparkline + min/p25/median/p75/max 摘要列）。
- **D-11:** **segment 切片策略**：evolve_* CLI 持久化 `raw_predictions: list[{correct_tool, selected_tool, difficulty, num_available_tools}]`；dashboard 启动时按 `--segment difficulty|pool_size` 动态计算 per-segment evolved_rate。`difficulty` 为 ToolSelectionExample 现有字段；`num_available_tools` = `len(example.available_tools)`，dashboard 内分桶 `1-3 / 4-7 / 8+`。Rationale：未来加新 segment 维度（如 `has_confuser`）时零改 evolve_*。
- **D-12:** **schema 扩展是 Phase 16 范围内**——这是 D-08 的对称面：dashboard 仅读，但 evolve_* CLI 必须新增 `raw_predictions` 字段才能给 distribution 喂数据。新建共用 helper `evolution/tools/tool_metric.py:persist_raw_predictions(metrics: dict, predictions: list[dict]) -> dict`（不可变模式，对齐 `persist_per_tool_rates`）。三 CLI 在 holdout 评估完成、metrics 落盘前各调用一次。
- **D-13:** **Warning 门**：dashboard 默认 -2pp warning（与 ROADMAP 成功标准 3 对齐），CLI flag `--warning-threshold-pp <float>` 可调。**不返 exit code**——dashboard 是观察工具，不参与 CI 决策。Phase 13 现有 `CrossToolRegressionChecker` 的 mean-based 2pp 硬门继续在 evolve_* CLI 内单独跑，路径不变。
- **D-14:** **不**实现 p25-based hard gate（Pitfall 10 双中门的右侧）。Rationale：当前 holdout per-tool sample_count 通常 < 20，p25 估计方差大，硬 gate 容易误杀；先靠 dashboard warning + 人工 review，待 Phase 14 session 数据 + Phase 19 prompt 数据扩 holdout 体量后再评估。归 deferred。

### 范围扩展（Phase 14 / 15 deferred）
- **D-15:** **Phase 15 ab_comparison.json 错例分析合入**——新建 `ABStudy` 区（仅在扫到 reasoning source 的 run 时渲染）。展示三类计数：`think_on_saved`（off 错 / on 对）、`think_on_regressed`（off 对 / on 错）、`both_wrong`（双错）。每类列 top-3 示例，字段：`task_description`（截 80 字）、`correct_tool`、`selected_off`、`selected_on`、`reasoning_text_on`（截 200 字）。来源：ab_comparison.json 已含全部所需字段（`is_correct_off / is_correct_on / reasoning_text_on / task_description / correct_tool / selected_off / selected_on`）。
- **D-16:** **Phase 14 工具频次不均衡可视化合入**——LATEST 表加 `sample_count` 列（来源 raw_predictions 中 correct_tool 的出现次数），表底渲染 Rich 水平柱（每行 `tool: ████████ 437` 直观对比）。柱按 sample_count 降序、limit 12 行 + 「others (N tools)」聚合行避免长尾。Rationale：Phase 14 deferred 直接受益于 D-12 的 raw_predictions 持久化，零额外 schema 成本。
- **D-17:** **总合交付：全包括 + 分 Wave**。Plan 应以多 Wave 组织：
  - Wave 0：raw_predictions schema + persist helper + 三 CLI 接线 + 单测（解锁后续 wave 的数据基础）。
  - Wave 1：dashboard CLI 骨架 + LATEST 区（含 sample_count + distribution 列 + 频次柱图）。
  - Wave 2：DIFF 区 + TREND 区 + sparkline。
  - Wave 3：ABStudy 区 + 跨 CLI source 标注 + 老 run fallback。
  - Wave 4：dashboard.json schema 收口 + 端到端集成测试。
  Wave 切分细节由 gsd-planner 决定，Phase 16 不预先 pin。

### Claude's Discretion
- `dashboard.json` 顶层字段名（建议 `latest`, `diff`, `trend`, `ab_study`, `source_legend`, `dropped_runs`, `summary`，但 planner 可微调）。
- Rich Table 颜色编码细节（OK 默认 / WARN 黄 / FAIL 红 / GAIN 绿基调由本 context 锁定，但具体 hex / Rich style 名由 planner 选）。
- TREND sparkline 的字符集合（▁▂▃▄▅▆▇█ 还是其他 ASCII）。
- 老 run 自动检测的启发：metrics.json 字段集 + 目录名 fallback 顺序。
- ABStudy top-3 排序键（建议「按 reasoning_text_on 长度倒序 + 任务难度倒序」，但 planner 可优化）。
- `persist_raw_predictions` 的字段精确名（`correct_tool` / `selected_tool` / `difficulty` / `num_available_tools` 是建议，planner 在 Wave 0 测试中 pin）。
- segment `pool_size` 分桶边界（默认 1-3 / 4-7 / 8+，可调）。

### Folded Todos
None — `gsd-sdk query todo.match-phase 16` 仅返回低分（≤0.4）的不相关项目，未折叠任何 todo 入 Phase 16 scope。详见 `<deferred>` Reviewed Todos。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 项目规划文档
- `.planning/ROADMAP.md` §Phase 16 — 目标、依赖（Phase 14）、需求（TOOL-V2-04）、3 条 Success Criteria（per-tool rates 持久化 / Rich console dashboard / 可配 regression threshold）
- `.planning/REQUIREMENTS.md` §TOOL-V2-04 — 需求定义「Per-tool regression guard with individual selection rate tracking dashboard」
- `.planning/PROJECT.md` §Constraints — 不引入新依赖、复用 DSPy/Click/Rich 栈、≤500 / ≤200 / ≤+20% size 约束（Phase 16 不动文本但需遵循只读 hermes-agent 约束）

### 研究 / 风险（必读）
- `.planning/research/PITFALLS.md` §Pitfall 10 — Per-Tool Regression Dashboard Stores Misleading Averages；distribution 双层语义、p25-based gate（D-14 拒绝）、retention（推 deferred）的原始论证
- `.planning/codebase/CONCERNS.md` §M3 — Cross-Tool Regression Gate Is Pass/Fail Only；Phase 13 仅落 rates 持久化、「dashboard 聚合」明确推给 Phase 16
- `.planning/codebase/CONCERNS.md` §M4 — LLM 输出解析脆弱；与 dashboard 无直接耦合，但 Phase 16 schema 扩展应保持解析容错风格
- `.planning/codebase/CONCERNS.md` §H4 — `output/` 未 gitignore；本 phase 写 `dashboard_<ts>.json` 到 CWD（默认）+ 读 output/* 数据，需在 plan 中复核 .gitignore（Phase 12 已加 output/）

### 上游 Phase 决策（先验上下文）
- `.planning/phases/13-per-parameter-description-optimization/13-CONTEXT.md` §D-12 — `per_tool_baseline_rates` / `per_tool_evolved_rates` schema 与 `persist_per_tool_rates` 不可变 helper 模式（D-12 的对称面）
- `.planning/phases/13-per-parameter-description-optimization/13-CONTEXT.md` §D-15 — `--max-cost-usd` 与 `--reflection-model` flag 风格（Phase 16 dashboard 不调 LLM 故无需，但 CLI flag 命名风格沿用）
- `.planning/phases/14-sessiondb-mining-for-tools/14-CONTEXT.md` §Deferred — Phase 16 承接「session 加权后的工具不均衡可视化」（D-16 来源）
- `.planning/phases/15-think-augmented-tool-selection/15-CONTEXT.md` §D-11 — `output/tools_reasoning/<ts>/` 输出目录约定 + `ab_comparison.json` 字段（D-15 来源）
- `.planning/phases/15-think-augmented-tool-selection/15-CONTEXT.md` §Deferred — 「Reasoning 错例分析归入 Phase 16 dashboard 的延展」（D-15 来源）

### 代码基座（必读）
- `evolution/tools/tool_metric.py` — `CrossToolRegressionChecker.compute_per_tool_rates`（rates 来源）+ `persist_per_tool_rates`（D-12 helper 模板，D-12 的 `persist_raw_predictions` 镜像它）
- `evolution/tools/evolve_tool_params.py` lines 1012-1017 — Phase 13 在 holdout 评估后调 `persist_per_tool_rates` 的接线点；Phase 16 在同一处加 `persist_raw_predictions` 一行
- `evolution/tools/evolve_tool_descriptions.py` — Phase 5 holdout 评估路径；Phase 16 需在此处补 `persist_per_tool_rates` 调用 + `persist_raw_predictions` 调用（**注意**：根据 D-08 老 run 跳过策略，Phase 16 内补 `per_tool_*_rates` 写入是 D-12 schema 一致性收口的一部分，不是 deferred；但 D-08 描述的 fallback 是为了兼容历史已存的老 run）
- `evolution/tools/evolve_tool_reasoning.py` — Phase 15 CLI；新 CLI 同样需在 holdout 评估后调 `persist_per_tool_rates`（如未调）+ `persist_raw_predictions`，并保持现有 `ab_comparison.json` 输出不变
- `evolution/tools/tool_dataset.py` — `ToolSelectionExample` 的 `difficulty` / `available_tools` / `correct_tool` 字段（D-11 segment 切片来源）
- `evolution/core/constraints.py` — `ConstraintResult` dataclass（dashboard CLI 不直接使用，但 schema 风格对齐）
- `output/tools_reasoning/<ts>/ab_comparison.json` — 实际 schema：`list[{task_id, task_description, correct_tool, selected_off, selected_on, is_correct_off, is_correct_on, is_ambiguous, confuser_tools, reasoning_text_on}]`（D-15 ABStudy 字段来源）
- `output/tools/<ts>/metrics.json` 与 `output/tools_reasoning/<ts>/metrics.json` — 实际字段集（用于 D-07 source 启发与 D-08 fallback 判定）

### 外部框架
- DSPy 3.x — Phase 16 dashboard 不调 LLM；schema 扩展中 raw_predictions 完全本地数据，无 DSPy 直接依赖
- Click `>=8.0` `@click.option` 风格（沿用 Phase 13 / 15）
- Rich `>=13.0` `Console / Panel / Table / BarColumn / sparkline`（D-09 / D-16 / D-10 都需用）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `evolution/tools/tool_metric.py:persist_per_tool_rates` —— 不可变 helper 模式（shallow copy + sorted keys + float 强转），D-12 的 `persist_raw_predictions` 直接镜像该模式，预计 25-40 LoC。
- `evolution/tools/tool_metric.py:CrossToolRegressionChecker.compute_per_tool_rates` —— rates 计算逻辑已有，dashboard 端不重新计算；从 metrics.json 直接读 `per_tool_baseline_rates` / `per_tool_evolved_rates`。
- `evolution/tools/evolve_tool_params.py` lines 75 / 1012-1017 —— `persist_per_tool_rates` 的导入与 wire 处；Phase 16 三 CLI（包括 evolve_tool_descriptions / evolve_tool_reasoning）的 `persist_raw_predictions` 接线点同位置。
- `evolution/tools/tool_dataset.py:ToolSelectionExample` —— 现有 `difficulty: str` / `available_tools: list[str]` / `correct_tool: str` 字段，D-11 segment 切片完全复用。
- `evolution/core/external_importers.py:_contains_secret` —— dashboard 渲染 ABStudy 区的 task_description / reasoning_text_on 截断前应过 `_contains_secret`，避免 stdout 泄露 secret（hermes-agent session 已有过滤，但二次 re-render 谨慎些）。
- Rich Console / Panel / Table / `BarColumn` / sparkline 字符模式（Phase 5 / 13 / 15 高亮 PASS/FAIL 已用熟）。

### Established Patterns
- **Click + Rich + metrics.json 三件套**：Phase 5 / 13 / 15 统一；Phase 16 dashboard 沿用，但**不写 metrics.json**（写 dashboard.json）。
- **Helper 不可变模式**：`persist_per_tool_rates` 返回新 dict 不 mutate 入参；`persist_raw_predictions` 必须沿用，便于 unit test。
- **DSPy Module + inner Signature** —— 不适用（dashboard 无 LLM 调用）。
- **FAILED_<ts>/ vs ABORTED_<ts>/ 输出目录约定** —— 不适用（dashboard 不会进入这两个状态）。
- **Constraint chain fail-closed** —— 不适用（dashboard 仅 warning）。
- **`@click.option` 默认值 + 帮助文本** —— Phase 16 沿用，特别是 `--runs` 多次出现累加（`multiple=True`）的风格与 Phase 14 的 `--signals` 类似。

### Integration Points
- **三 CLI 接线**（Wave 0）：`evolve_tool_descriptions.py` / `evolve_tool_params.py` / `evolve_tool_reasoning.py` 在调 `persist_per_tool_rates(...)` 后立刻调 `persist_raw_predictions(...)`，metrics 写盘前合并。该接线对 Phase 13 / 15 现有测试零影响（向后兼容字段加法）。
- **Dashboard 入口**（Wave 1+）：新建 `evolution/tools/regression_dashboard.py`，命令注册 `__main__.py` 或在 evolution/tools/`__init__.py` 加 `__all__` 暴露 `main` —— 沿用 Phase 5 / 13 / 15 入口注册方式。
- **测试根**：`tests/tools/test_regression_dashboard.py` + `tests/tools/test_persist_raw_predictions.py`（与 Phase 13 `test_persist_per_tool_rates.py` 文件结构对称）。
- **集成测试**：构造两个 fixture metrics.json（含 raw_predictions）+ 一个 ab_comparison.json fixture，跑完整 dashboard 回路验证 stdout + dashboard.json schema。
- **数据流**：metrics.json[raw_predictions] → dashboard CLI 内 in-memory pandas-style 切片（不引 pandas，用 dict + collections.Counter）→ Rich Table render + JSON dump。

</code_context>

<specifics>
## Specific Ideas

- `dashboard.json` 顶层 schema 草稿（Claude's Discretion 内可微调）：
  ```json
  {
    "generated_at": "2026-05-12T16:30:00Z",
    "scanned_runs": 18,
    "dropped_runs": [{"path": "...", "reason": "missing per_tool_baseline_rates"}],
    "source_legend": {"desc": "evolve_tool_descriptions, baseline=v1 frozen", "params": "...", "reasoning": "..."},
    "latest": {"run_path": "...", "source": "params", "per_tool": [{"tool": "read_file", "baseline_rate": 0.85, "evolved_rate": 0.87, "delta_pp": 2.0, "sample_count": 437, "distribution": {"min": 0.40, "p25": 0.78, "median": 0.88, "p75": 0.95, "max": 1.0}, "status": "OK"}, ...]},
    "diff": {...},
    "trend": {"window_kind": "n", "window_value": 10, "tools": [{"tool": "read_file", "series": [{"ts": "...", "rate": 0.85}, ...], "summary": {"min": 0.78, "p25": 0.83, "median": 0.85, "p75": 0.87, "max": 0.91}}]},
    "ab_study": {"detected_runs": 3, "by_run": [{"run_path": "...", "think_on_saved": 12, "think_on_regressed": 4, "both_wrong": 8, "top_examples": {"saved": [...], "regressed": [...], "both_wrong": [...]}}]},
    "warnings": [{"tool": "search_files", "delta_pp": -2.4, "run_path": "..."}]
  }
  ```
- TREND sparkline 字符集采用 `▁▂▃▄▅▆▇█`（unicode block elements），与 git/htop 习惯一致。
- 频次柱图：每柱长度按 max sample_count 归一化到 30 列宽，超 12 行时聚合 「others (N tools): ███████ 234」。
- ABStudy top-3 排序键建议：`saved` 按 reasoning_text_on 长度降序（看长 reasoning 是否有用）；`regressed` 按 task_description 长度降序（看复杂任务 think 是否帮倒忙）；`both_wrong` 随机抽（不引导）。
- `--segment` flag 接受 `difficulty | pool_size | none`；`none` 跳过 distribution 列只渲染 baseline/evolved/delta。
- `persist_raw_predictions` 应在 raw_predictions list 长度 >2000 时 stdout warning「raw_predictions large; metrics.json size %.1fMB」，提示后续可能需 retention（Pitfall 10 retention 的占位）。
- 跨 CLI source 启发判定：metrics.json 含 `think_ab_gate` 字段 → reasoning；含 `param_predictors_discovered` 字段 → params；都不含但 `optimizer_used` 存在 → desc；都不含 → 整 run 跳过 + dropped_runs。

</specifics>

<deferred>
## Deferred Ideas

- **p25-based hard gate**（Pitfall 10 双中门右侧）：当前 holdout sample_count < 20，p25 估计方差大；待 Phase 14 session 数据 + Phase 19 prompt 数据扩 holdout 后评估。可能落到 Phase 19 / 20 / 22。
- **SQLite history DB / 90 天 / 1000 run cap retention**（Pitfall 10 retention 思路）：本 phase 不引 DB 依赖；run 多时 dashboard 启动慢的问题先靠 `--trend-window` / `--trend-days` 缓解。Phase 22 持续进化循环时再评估是否需要 history 库。
- **inline summary 作为 evolve_* CLI 末尾段**（Gray Area 1 选项 B / D）：本 phase 拒绝；若用户后续反馈「跑完 evolve 不愿手动调 dashboard」，作为 Phase 16.5 / Phase 23 跟进。
- **`--strict` flag 让 dashboard 返 exit 1**（CI 集成）：Phase 16 仅 warning 模式；CI 集成留 Phase 22 持续进化循环时统一 wire 一道 dashboard hard-gate。
- **skill / prompt 管道的 dashboard 化**：本 phase 仅工具维度。Phase 18（Personality Drift Detection）和 Phase 17（Joint Section Optimization）落地后再考虑给 prompt 加 per-section dashboard。
- **Reasoning 错例自动 issue / repair skill**（Phase 15 deferred 中 ABStudy 之外的部分）：本 phase 仅做 stdout / JSON 呈现错例；自动修复 / issue 路径留 Phase 22+。
- **`per_tool_*_rates` 补全到 evolve_tool_descriptions 历史 run**：Phase 16 仅给三 CLI 加新字段（前向兼容），不回填老 run 的 metrics.json。
- **Pool size 分桶自适应**：默认 1-3 / 4-7 / 8+ 是经验值；若发现分布不合理，留 follow-up 调阈值或加 quantile-based 分桶。
- **Rich Live / 交互式 dashboard**：本 phase 是一次性 render；交互/实时刷新留 Phase 22 持续进化循环时考虑。
- **多 source baseline 含义对齐**：descriptions 与 params 的 baseline 都是 v1 frozen，但 reasoning 的 baseline 是 think-off；本 phase 仅在 legend 文字标注。若未来要做严格的 cross-source 比较（如「reasoning 比 params 强多少」），需要重新设计 baseline normalization——留 Phase 22+。

### Reviewed Todos (not folded)

`gsd-sdk query todo.match-phase 16` 返回 4 项，全部低分（≤0.4），均不与 Phase 16 dashboard 范围匹配；逐项说明：

- **`.planning/todos/pending/2026-05-07-centralize-lm-retry-handling.md`** (score 0.4) — LLM retry/rate-limit 集中化；Phase 16 dashboard **零 LLM 调用**，无需此项。归 evolution-core hygiene。
- **`.planning/todos/pending/2026-05-07-add-lockfile-dspy-pin.md`** (score 0.2) — DSPy 锁文件；与 dashboard 范围无关，归 tooling 维度。
- **`.planning/todos/pending/2026-05-07-enforce-readonly-hermes-agent.md`** (score 0.2) — hermes-agent 只读 deploy_mode 门；Phase 16 完全不调 hermes-agent 写回路径，无落地点。留 Phase 22。
- **`.planning/todos/pending/2026-05-07-expand-secret-patterns.md`** (score 0.2) — Phase 14 已 fold；Phase 16 dashboard 在渲染 ABStudy / 频次柱图时**复用** `_contains_secret` 即可，不需要新扩 patterns。

</deferred>

---

*Phase: 16-per-tool-regression-dashboard*
*Context gathered: 2026-05-12*
