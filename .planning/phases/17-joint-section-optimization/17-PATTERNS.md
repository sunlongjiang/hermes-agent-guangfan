# Phase 17: Joint Section Optimization - Pattern Map

**Mapped:** 2026-05-15
**Files analyzed:** 4 (2 production + 2 tests)
**Analogs found:** 4 / 4 (100% coverage)

> **范围说明:** Phase 17 是 feature-addition 阶段 — 不创建新模块文件,仅在两个现有生产源(`prompt_module.py`、`evolve_prompt_sections.py`)上做 in-place 扩展,并扩 / 新建对应测试。所有"analog"均来自项目内已合并 phase(Phase 8 PromptModule、Phase 13 evolve_tool_params)的现成实现。

## File Classification

| New/Modified File | Type | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|------|-----------|----------------|---------------|
| `evolution/prompts/prompt_module.py` | MODIFY | dspy.Module / state machine | request-response (forward) | self (existing `set_active_section`) + Phase 8 同源设计 | exact (extends self) |
| `evolution/prompts/evolve_prompt_sections.py` | MODIFY | CLI orchestrator | batch optimization + persistence | `evolution/tools/evolve_tool_params.py` (Phase 13) | exact (同 CLI/GEPA 风格) |
| `tests/prompts/test_prompt_module.py` | MODIFY | unit test (pytest class) | mock-based unit | self (TestActiveSection/TestFrozenContext 既有风格) | exact (extends self) |
| `tests/prompts/test_evolve_prompt_sections_cli.py` | **NEW** | integration test (CliRunner) | mock-GEPA CLI exec | `tests/tools/test_evolve_tool_params_cli.py` (Phase 13) | exact |

**Novelty alert:** Joint forward 的「全 13 个 section instructions concat 进 `frozen_context`」是 Phase 17 独创设计,无 codebase 内分析对象 — 见 §Non-Analogous Novelty 章节。

---

## Pattern Assignments

### `evolution/prompts/prompt_module.py` (dspy.Module / state machine)

**Analog:** Self — extends Phase 8 同模块的 `set_active_section` / `forward` / `get_evolved_sections` 三态扩展。

#### Pattern A1 — State-switch helper(`set_active_section` 镜像)

**Source:** `evolution/prompts/prompt_module.py` 第 71-99 行

```python
def set_active_section(self, section_id: str) -> None:
    if section_id not in self._frozen_sections:
        raise ValueError(
            f"Unknown section: {section_id}. "
            f"Available: {self._section_ids}"
        )
    # Move current active back to frozen (extract instructions from Predict)
    if self._active_section is not None:
        pred = self.section_predictors.pop(self._active_section)
        self._frozen_instructions[self._active_section] = (
            pred.signature.instructions
        )

    # Move new active from frozen string to Predict instance
    text = self._frozen_instructions.pop(section_id)
    sig = dspy.Signature(
        "section_text -> confirmation",
        instructions=text,
    )
    self.section_predictors[section_id] = dspy.Predict(sig)
    self._active_section = section_id
```

**新方法须镜像的要点:**
1. 入口 guard(参数校验或 sentinel 检测)→ 抛 `ValueError`/做 idempotent no-op。
2. pop frozen 字符串 → 构造 `dspy.Signature("section_text -> confirmation", instructions=text)` → 包 `dspy.Predict(sig)` → 写入 `self.section_predictors[sid]`(让 `named_predictors()` 自动暴露)。
3. 最末更新 `self._active_section` —— Phase 17 用 sentinel `"__JOINT__"`(RESEARCH Pattern 2)。
4. 反向操作(joint→frozen)对称:pop Predict、取 `pred.signature.instructions`、写回 `_frozen_instructions`。

#### Pattern A2 — Forward 三态分发

**Source:** `evolution/prompts/prompt_module.py` 第 101-122 行

```python
def forward(self, task_input: str) -> dspy.Prediction:
    if self._active_section is None:
        raise RuntimeError(
            "No active section set. Call set_active_section() first."
        )
    frozen_context = self._build_frozen_context()
    result = self.selector(
        frozen_context=frozen_context,
        task_input=task_input,
    )
    return dspy.Prediction(output=result.output)
```

**改造要点:** 把 `_active_section is None` / `== JOINT_SENTINEL` / 普通 sid 拆三分支。`None` 报错语义不变;sentinel 路径构造「全段拼接 frozen_context」并复用同一 `self.selector`(D-discretion 锁定:不另起 selector);单 sid 路径维持现状。返回签名维持 `dspy.Prediction(output=...)`,metric 端零改动。

#### Pattern A3 — `_build_frozen_context` 拼接

**Source:** `evolution/prompts/prompt_module.py` 第 124-131 行

```python
def _build_frozen_context(self) -> str:
    parts = []
    for sid in self._section_ids:
        if sid != self._active_section:
            text = self._frozen_instructions[sid]
            parts.append(f"[{sid}]: {text}")
    return "\n\n".join(parts)
```

**Joint mode 改造:** 当 `_active_section == JOINT_SENTINEL`,改读 `self.section_predictors[sid].signature.instructions`(因为 frozen_instructions 在 joint mode 下被清空);拼接格式 `f"[{sid}]: {text}"` + `"\n\n"` 分隔保持不变 — 这是确保 metric 评分一致的关键。

#### Pattern A4 — `get_evolved_sections` 已天然兼容

**Source:** `evolution/prompts/prompt_module.py` 第 133-155 行

```python
for sid in self._section_ids:
    # Active section: read from Predict; frozen: read from string
    if sid in self.section_predictors:
        current_text = self.section_predictors[sid].signature.instructions
    else:
        current_text = self._frozen_instructions[sid]
```

**Joint mode 适配性:** 现有循环已按 `sid in self.section_predictors` 二选一,joint mode 下所有 sid 都在 `section_predictors`,自然走 Predict 分支,**无须修改**。

---

### `evolution/prompts/evolve_prompt_sections.py` (CLI orchestrator)

**Primary analog:** `evolution/tools/evolve_tool_params.py`(Phase 13)— 同一团队同期写就的 GEPA + `--component-selector` CLI pipeline,与 Phase 17 joint mode 拓扑同构。
**Secondary analog:** Self — round-robin pipeline 大体保留,仅按 mode 分叉。

#### Pattern B1 — `--component-selector` Click flag(直接复用风格)

**Source:** `evolution/tools/evolve_tool_params.py` 第 579-581 行

```python
@click.option("--component-selector", default="round_robin",
              type=click.Choice(["round_robin", "all"]),
              help="GEPA component selection strategy")
```

**Phase 17 改造:** Phase 17 不暴露 `--component-selector` 给用户(D-RR-04 锁定用户面是 `--mode`),但内部 mapping 完全一致:

```python
@click.option(
    "--mode",
    default="joint",
    type=click.Choice(["joint", "round-robin"]),
    help="Optimization mode: 'joint' (default, optimizes all sections "
         "simultaneously via GEPA) or 'round-robin' (legacy, "
         "optimizes section-by-section).",
)
```

mode→selector 内部映射:`joint → "all"`,`round-robin → "round_robin"`。

#### Pattern B2 — GEPA 初始化 + budget(多参数公式)

**Source:** `evolution/tools/evolve_tool_params.py` 第 793-813 行

```python
# Budget — exactly one of auto / max_metric_calls (Pitfall 6).
optimizer_init_kwargs: dict[str, Any] = {
    "metric": joint_tool_param_metric_with_feedback,
    "reflection_lm": reflection_lm,
    "component_selector": component_selector,
    "track_stats": True,
    "seed": 0,
    "gepa_kwargs": gepa_kwargs,
}
if auto is not None:
    optimizer_init_kwargs["auto"] = auto
else:
    optimizer_init_kwargs["max_metric_calls"] = max(
        iterations * 50, 3 * num_predictors
    )
optimizer = dspy.GEPA(**optimizer_init_kwargs)
optimized_module = optimizer.compile(
    baseline_module,
    trainset=trainset,
    valset=valset,
)
```

**Phase 17 复用要点:**
- joint 分支 kwargs 设 `component_selector="all"`、`max_metric_calls = max(iterations * 50, 3 * num_predictors)`(RESEARCH Pitfall 6 锁定的多参数公式,代替 CONTEXT D-IT-02 写死的 `× 5`)。
- `num_predictors = len(list(module.predictors()))` 运行时算,不 hardcode 13/14。
- round-robin baseline 内部 for-loop 用 `component_selector="round_robin"`(default),`max_metric_calls=iterations * 50`(单参数预算)。
- 显式传 `seed=0` 与 `track_stats=True` 提升可复现性(Phase 13 已确立这一惯例)。
- Phase 17 不需要 Phase 13 的 `gepa_kwargs["stop_callbacks"]`(CostTracker) —— RESEARCH §Security Domain 已锁定本期不引 CostTracker。

#### Pattern B3 — Round-robin for-loop(保留为 baseline)

**Source:** `evolution/prompts/evolve_prompt_sections.py` 第 213-283 行

```python
for active_sid in sections_to_optimize:
    console.print(f"\n[bold cyan]Optimizing section: {active_sid}[/bold cyan]")
    module.set_active_section(active_sid)

    # Filter dataset for this section
    section_train = [ex for ex in dataset.train if ex.section_id == active_sid]
    section_val = [ex for ex in dataset.val if ex.section_id == active_sid]

    temp_dataset = PromptBehavioralDataset(
        train=section_train, val=section_val, holdout=[],
    )
    trainset = temp_dataset.to_dspy_examples("train", section_texts=section_texts)
    valset = temp_dataset.to_dspy_examples("val", section_texts=section_texts)

    if not trainset:
        console.print(f"  [yellow]Warning: No training data for {active_sid}, skipping[/yellow]")
        continue

    try:
        reflection_lm = dspy.LM(config.optimizer_model, **config.get_lm_kwargs())
        optimizer = dspy.GEPA(
            metric=metric,
            max_metric_calls=iterations * 50,
            reflection_lm=reflection_lm,
        )
        module = optimizer.compile(module, trainset=trainset, valset=valset)
    except Exception as e:
        # Fall back to MIPROv2 ... [略]
```

**Phase 17 复用要点:**
- A/B baseline 内联块(RESEARCH Pattern 5)完全照搬这段 for-loop,只是输入是 fresh `PromptModule(original_sections)`(Pitfall 4 规避 mutation 污染)。
- 现有 GEPA → MIPROv2 fallback 链(line 252-283)保留 — `--mode round-robin` 走这条;joint 分支若 GEPA 抛错,**RESEARCH §Security Domain 建议**沿用 Phase 13 D-15a "loud fail" 模式直接 propagate(planner 决定是否新增 `--allow-miprov2-fallback`,本期 CONTEXT 未要求,默认 loud)。
- A/B baseline 的 holdout 评分循环也要复用现有 holdout 块(第 367-388 行),保证 apples-to-apples。

#### Pattern B4 — 软门 + 黄警告(stdout-only,不阻断)

**Source:** `evolution/tools/regression_dashboard.py` 第 778-787 行(Phase 16 D-13 实现)

```python
if delta <= -warning_threshold_pp:
    warnings_list.append({
        "tool": tool,
        "delta_pp": delta,
        "run_path": latest_run["path"],
    })
    console.print(
        f"[yellow]WARNING: {tool} regressed by {delta:+.2f}pp in "
        f"{latest_run['path']} (threshold: -{warning_threshold_pp:.1f}pp)[/yellow]"
    )
```

**Phase 17 复用要点:**
- 文案三要素:`[yellow]` 前缀 + 三个数值(joint_score / roundrobin_score / delta_pp)+ 建议性短语("review before deploying")。
- 严格不返回非零 exit code、不抛异常、不阻断后续 constraint validation 与 落盘 — 与 Phase 16 D-13 完全一致。
- `epsilon_pp` 是 module 级常量(CONTEXT D-AB-03:`EPSILON_PP = 0.01`)定义在文件顶部 imports 下方,不暴露为 CLI flag。

#### Pattern B5 — Dry-run budget pre-flight stdout

**Source:** `evolution/tools/evolve_tool_params.py` 第 742-751 行

```python
# ── 4. Dry-run early return ────────────────────────────────────────
if dry_run:
    click.echo(f"param_predictors_discovered={num_predictors}")
    click.echo(f"tools_in_scope={len(all_tools)}")
    click.echo(f"iterations_planned={iterations}")
    click.echo(f"eval_source={eval_source}")
    click.echo(f"max_cost_usd_cap={config.max_cost_usd}")
    # Heuristic budget estimate (RESEARCH Pitfall 6 formula).
    budget_estimate = iterations * max(50, 3 * num_predictors)
    click.echo(f"max_metric_calls_estimate={budget_estimate}")
    console.print("[bold green]DRY RUN — setup validated.[/bold green]")
    return 0
```

**Phase 17 复用要点:** Phase 17 的 budget 行不在 `--dry-run` 内,而是在 mode-fork 后真正跑 GEPA 之前打印(CONTEXT D-IT-03 给的样例),始终向 stdout 打 — 让用户在 confirm 前看到。同时建议 `--dry-run` 路径也加同样的预算行,与 Phase 13 接线对齐。格式照搬 CONTEXT D-IT-03:

```
Joint optimization:        iterations=10, max_metric_calls=2500
Round-robin A/B baseline:  iterations=10/section × 5 sections, max_metric_calls=500/section
Total est. LM calls:       ~5000 (joint) + ~2500 (baseline) = ~7500
```

#### Pattern B6 — metrics.json 落盘(schema 扩展)

**Source:** `evolution/prompts/evolve_prompt_sections.py` 第 429-445 行

```python
metrics = {
    "timestamp": timestamp,
    "iterations": iterations,
    "eval_model": config.eval_model,
    "baseline_score": baseline_score,
    "evolved_score": evolved_score,
    "improvement": improvement,
    "section_count": len(evolved_sections),
    "train_examples": len(dataset.train),
    "val_examples": len(dataset.val),
    "holdout_examples": len(dataset.holdout),
    "elapsed_seconds": elapsed,
    "constraints_passed": True,
}
(output_dir / "metrics.json").write_text(
    json.dumps(metrics, indent=2)
)
```

**Phase 17 改造:** 现有 dict 后追加 CONTEXT D-OUT-02 锁定的 4 个新字段。Joint mode 下:

```python
metrics.update({
    "mode": "joint",                              # 必填,所有 run
    "joint_score": joint_score,                   # 仅 joint mode 写
    "roundrobin_baseline_score": roundrobin_baseline_score,  # 仅 joint mode 写
    "epsilon_pp": EPSILON_PP,                     # joint mode 软门常量(0.01)
    "ab_elapsed_seconds": elapsed_ab,             # A/B baseline 跑用时
})
```

Round-robin mode 下只追加 `"mode": "round-robin"`。`baseline_score`、`evolved_score`、`improvement` 字段语义维持 CONTEXT D-OUT-02 说明(对 joint mode 来说 `evolved_score == joint_score`)。

#### Pattern B7 — Constraint validation per-section 已天然适配

**Source:** `evolution/prompts/evolve_prompt_sections.py` 第 298-326 行(`_check_growth` + `_check_non_empty` + `PromptRoleChecker.check_all`)

无须改造 — joint mode 下 evolved_sections 仍是 `list[PromptSection]`,for-loop 自然遍历全 13 段。

---

### `tests/prompts/test_prompt_module.py` (unit tests, extend)

**Analog:** Self — 现有 `TestActiveSection` / `TestFrozenContext` / `TestForward` 类风格直接复刻为 `TestJointMode`。

#### Pattern C1 — Test class + 共享 fixture

**Source:** `tests/prompts/test_prompt_module.py` 第 15-39 行

```python
def _make_prompt_sections() -> list[PromptSection]:
    """Create 3 test PromptSection instances for testing."""
    return [
        PromptSection(
            section_id="default_agent_identity",
            text="You are a helpful AI assistant.",
            char_count=30,
            line_range=(10, 15),
            source_path=Path("/fake/prompt_builder.py"),
        ),
        # ... 2 more
    ]
```

**Phase 17 复用:** `TestJointMode` 类直接用 `_make_prompt_sections()` — 3 段 fixture 已足够覆盖 joint mode 单测(`set_joint_mode(True)` 后 `len(section_predictors) == 3`、`named_predictors()` 含 selector + 3 段 = 4 项)。

#### Pattern C2 — State-switch 单测样板

**Source:** `tests/prompts/test_prompt_module.py` 第 74-103 行(`TestActiveSection`)

```python
def test_set_active_section_moves_to_discoverable(self):
    sections = _make_prompt_sections()
    module = PromptModule(sections)
    module.set_active_section("memory_guidance")

    # Count section predictors (exclude selector)
    assert len(module.section_predictors) == 1
    assert "memory_guidance" in module.section_predictors

def test_switch_active_section(self):
    sections = _make_prompt_sections()
    module = PromptModule(sections)
    module.set_active_section("memory_guidance")
    module.set_active_section("skills_guidance")

    assert len(module.section_predictors) == 1
    assert "skills_guidance" in module.section_predictors
    assert "memory_guidance" not in module.section_predictors
    assert "memory_guidance" in module._frozen_instructions
```

**Phase 17 新增测试(RESEARCH §Wave 0 Gaps):**
1. `test_set_joint_mode_exposes_all_predictors` — `set_joint_mode(True)` 后 `len(module.section_predictors) == 3`、`len(module._frozen_instructions) == 0`、`module._active_section == "__JOINT__"`。
2. `test_set_joint_mode_idempotent` — 连调两次 `set_joint_mode(True)`,state 不变,不抛。
3. `test_joint_then_set_active_section_auto_demotes`(Pitfall 3 fix)— `set_joint_mode(True)` → `set_active_section("memory_guidance")`,断言 `_active_section == "memory_guidance"`、`section_predictors` 仅含 memory_guidance、其它两段回到 `_frozen_instructions`。
4. `test_named_predictors_in_joint_mode` — 验证 `[n for n, _ in module.named_predictors()]` 含 3 个 `section_predictors[...]` + 1 个 `selector.predict` = 4 项(RESEARCH Pattern 4 实测)。
5. `test_forward_in_joint_mode_works` — mock `module.selector.forward`,joint mode 下 forward("input") 返回 `dspy.Prediction(output=...)`,且 `frozen_context` 参数含全 3 段拼接(用 `mock.call_args` 检查)。

#### Pattern C3 — Mock selector 验证 forward 不抛

**Source:** `tests/prompts/test_prompt_module.py` 第 152-163 行

```python
def test_forward_returns_prediction(self):
    sections = _make_prompt_sections()
    module = PromptModule(sections)
    module.set_active_section("memory_guidance")

    mock_result = dspy.Prediction(output="mocked response")
    with patch.object(module.selector, "forward", return_value=mock_result):
        result = module.forward("test input")

    assert isinstance(result, dspy.Prediction)
    assert result.output == "mocked response"
```

**Phase 17 复用:** 5 号测试用 `patch.object(module.selector, "forward")` 同模式;额外用 `mock_selector.assert_called_once()` 并检查 `call_args.kwargs["frozen_context"]` 含 `[default_agent_identity]:`、`[memory_guidance]:`、`[skills_guidance]:` 三段 — 证明 joint forward 把全段 concat 进了 frozen_context(Pitfall 1 关键)。

---

### `tests/prompts/test_evolve_prompt_sections_cli.py` (NEW, integration tests)

**Analog:** `tests/tools/test_evolve_tool_params_cli.py`(Phase 13)— 同 CliRunner + multi-patch 风格;直接复刻其 mock fixture 设计。

#### Pattern D1 — CliRunner + multi-layer patch

**Source:** `tests/tools/test_evolve_tool_params_cli.py` 第 64-108 行

```python
runner = CliRunner()

with patch(
    "evolution.tools.evolve_tool_params._load_tool_descriptions",
    return_value=[fake_tool],
), patch(
    "evolution.tools.evolve_tool_params._load_dataset",
    return_value=(fake_ds, fake_ds, fake_ds),
), patch(
    "evolution.tools.evolve_tool_params.dspy.GEPA"
) as mock_gepa, patch(
    "evolution.tools.evolve_tool_params.dspy.LM"
):
    mock_gepa.return_value.compile.side_effect = RuntimeError("gepa blew up")
    result = runner.invoke(evolve, [], catch_exceptions=True)

    # CRITICAL: prove dspy.GEPA was actually instantiated AND .compile() was called
    assert mock_gepa.called, (
        "dspy.GEPA was never instantiated — the empty-tools short-circuit "
        "prevented the test from reaching the GEPA branch."
    )
    assert mock_gepa.return_value.compile.called, (
        "dspy.GEPA().compile() was never called — side_effect did not fire."
    )

    assert result.exit_code != 0, ...
```

**Phase 17 新增测试(RESEARCH §Wave 0 Gaps):**

```python
# TestJointPipeline::test_joint_mode_calls_gepa_with_component_selector_all
with patch(
    "evolution.prompts.evolve_prompt_sections.extract_prompt_sections",
    return_value=fake_sections,
), patch(
    "evolution.prompts.evolve_prompt_sections.PromptDatasetBuilder"
) as mock_ds_builder, patch(
    "evolution.prompts.evolve_prompt_sections.PromptBehavioralMetric"
), patch(
    "evolution.prompts.evolve_prompt_sections.ConstraintValidator"
) as mock_validator_cls, patch(
    "evolution.prompts.evolve_prompt_sections.PromptRoleChecker"
) as mock_role_cls, patch(
    "dspy.GEPA"
) as mock_gepa, patch("dspy.LM"), patch("dspy.configure"):
    mock_gepa.return_value.compile.side_effect = lambda mod, trainset, valset=None: mod
    # ... wire fake dataset / constraint / role results passing ...

    runner = CliRunner()
    result = runner.invoke(main, ["--mode", "joint", "--iterations", "2", "--hermes-repo", "/fake"])
    assert result.exit_code == 0

    # PROOF: GEPA was instantiated with component_selector="all"
    init_kwargs = mock_gepa.call_args.kwargs
    assert init_kwargs.get("component_selector") == "all", (
        f"Joint mode must call GEPA with component_selector='all', "
        f"got {init_kwargs.get('component_selector')!r}"
    )
    # PROOF: single compile call (not 13×) for joint phase + 13× for A/B
    assert mock_gepa.return_value.compile.call_count == 1 + len(fake_sections)
```

#### Pattern D2 — 重用现有 test_evolve_prompt_sections.py 的 mock 链

**Source:** `tests/prompts/test_evolve_prompt_sections.py` 第 92-174 行(`test_evolve_orchestration_order`)

```python
@patch("evolution.prompts.evolve_prompt_sections.PromptRoleChecker")
@patch("evolution.prompts.evolve_prompt_sections.ConstraintValidator")
@patch("evolution.prompts.evolve_prompt_sections.PromptBehavioralMetric")
@patch("evolution.prompts.evolve_prompt_sections.PromptDatasetBuilder")
@patch("evolution.prompts.evolve_prompt_sections.PromptModule")
@patch("evolution.prompts.evolve_prompt_sections.extract_prompt_sections")
@patch("dspy.GEPA")
@patch("dspy.LM")
@patch("dspy.configure")
def test_evolve_orchestration_order(self, mock_configure, mock_lm, mock_gepa_cls, ...):
    fake_sections = _make_fake_sections()
    mock_extract.return_value = fake_sections

    mock_module = MagicMock()
    mock_module._section_ids = ["default_agent_identity", "memory_guidance"]
    mock_module.get_evolved_sections.return_value = fake_sections
    mock_module_cls.return_value = mock_module
    # ... (GEPA, dataset, validator, role_checker, metric mocks)
```

**Phase 17 复用要点:**
- 复刻这套 decorator stack 是 round-robin 路径整测的"祖传配方";Phase 17 新增 `TestJointPipeline::test_round_robin_mode_compiles_per_section` 时无须重写 mock 链,只多设 `--mode round-robin` flag。
- `TestJointPipeline::test_section_flag_forces_round_robin` 也走这条 — 验证 `--section memory_guidance --mode joint` 仍走 round-robin(`mock_module.set_active_section.call_args_list` 仅含一次 memory_guidance call,GEPA.compile 仅调一次)。
- `TestABBaseline::test_joint_mode_runs_inline_ab_baseline` 验证 `PromptModule` 类被实例化 ≥ 3 次(joint module、baseline_module for holdout、ab_baseline_module for A/B)。
- `TestABBaseline::test_soft_gate_warns_but_does_not_block` 用 `mock_metric.side_effect = [...]` 控制 joint_score < rr_score - 0.01,断言 `"[yellow]" in result.output` + `result.exit_code == 0` + `(output_dir / "metrics.json").exists()`。
- `TestDryRun::test_dry_run_prints_budget_estimate` 验证 `--mode joint --dry-run` 输出含 `"Joint optimization:"`、`"Round-robin A/B baseline:"`、`"Total est."` 三行子串。

---

## Shared Patterns

### S1 - Module-level Rich Console
**Source:** `evolution/prompts/evolve_prompt_sections.py` 第 34 行
**Apply to:** 所有新增 stdout 输出
```python
console = Console()
# ...
console.print("[bold cyan]...[/bold cyan]")
console.print("[yellow]WARNING: ...[/yellow]")
console.print("[green]+ ...[/green]")
```
不用 bare `print()`(CLAUDE.md "logging" 节锁定)。

### S2 - Section separator comments
**Source:** `evolution/prompts/evolve_prompt_sections.py` 全文(`# ── 6. Per-section GEPA optimization ────`)
**Apply to:** 新 joint mode 分支 + A/B baseline 分支
```python
# ── 6a. Mode fork: joint vs round-robin ──────────────────────────────
if mode == "joint" and not section:
    # ── 6a-i. Joint GEPA compile ─────────────────────────────────
    ...
else:
    # ── 6a-ii. Round-robin per-section loop ──────────────────────
    ...
```

### S3 - JSONL/JSON persistence
**Source:** `evolution/prompts/evolve_prompt_sections.py` 第 443-444 行
**Apply to:** 扩展后的 metrics.json
```python
(output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
```
保持 `indent=2` 的 human-readable 风格(CLAUDE.md "Serialization" 节)。

### S4 - typing imports
**Source:** `evolution/prompts/evolve_prompt_sections.py` 第 15 行
**Apply to:** 新增函数签名
```python
from typing import Optional
# ...
def evolve(
    mode: str = "joint",
    section: Optional[str] = None,
    iterations: int = 10,
    ...
):
```
CLAUDE.md "Code Style" 节锁定 `Optional[X]` over `X | None`(注意:`prompt_module.py` 第 56 行用了 `str | None`,这是 PEP 604 新写法,Phase 17 新代码沿用模块内既有风格 — `evolve_prompt_sections.py` 用 `Optional`,`prompt_module.py` 用 `| None`)。

### S5 - Constants at module top
**Source:** `evolution/core/dataset_builder.py:21-86`(EvalExample-style 常量), `evolution/tools/evolve_tool_params.py` 顶部
**Apply to:** `EPSILON_PP = 0.01`、`JOINT_SENTINEL = "__JOINT__"`
```python
# 在 imports 后、helper 函数前的常量块,UPPER_SNAKE_CASE 风格(CLAUDE.md "Naming Patterns" 节)
JOINT_SENTINEL = "__JOINT__"
EPSILON_PP = 0.01  # Soft-gate threshold: joint must not regress by more than 1pp vs round-robin
```

---

## Non-Analogous Novelty

### Joint forward concat — 无 codebase 直接分析对象

**Where:** `evolution/prompts/prompt_module.py` 的 joint mode forward 路径
**What's new:** 把所有 13 个 `section_predictors[sid].signature.instructions` concat 进单一 `frozen_context` 字符串,再调 **同一个** `self.selector`。这是 Phase 17 独创设计 — 既不是现有 round-robin 的「frozen 多段 + active Predict 独立」结构,也不是「N 个 Predict 串行调用合并 output」候选方案 b。
**Why no analog:** 项目内之前没有「多 Predict 共享 forward 输出」需求 — Phase 1 SkillModule 单 Predict、Phase 13 ToolModule 每 tool 独立 Predict 但 GEPA 各自归因。Phase 17 是首次让 GEPA `component_selector="all"` 与一个统一 selector 协作。
**Pattern source:** RESEARCH §Architecture Patterns Pattern 3(新设计,本地 venv 实测 dspy 3.1.3 接受 `component_selector="all"`、`named_predictors()` 暴露全 dict 项)。Planner 把 RESEARCH Pattern 3 的代码块作为 plan 的实现参照。
**Risk:** RESEARCH §Assumptions Log A2 - GEPA reflection_lm 把多 section 反思正确归因到各自 Predict 是 hypothesis;Phase 17 success criterion 3「joint ≥ round-robin」本身就是该 hypothesis 的实证检验,A/B 软门即风险护栏。

---

## No Analog Found

| File | Reason |
|------|--------|
| (none) | 全部 4 个文件都有项目内现成 analog |

---

## Metadata

**Analog search scope:**
- `evolution/prompts/` — 主修改区
- `evolution/tools/` — Phase 13 (`evolve_tool_params.py`) + Phase 16 (`regression_dashboard.py`) 双 prior art
- `evolution/skills/` — 跳过(skill 是单 Predict,无 multi-param GEPA 模式可借)
- `evolution/core/` — 仅引用 `EvolutionConfig` / `ConstraintValidator`,无新模式
- `tests/prompts/` — 单元测试现存风格基线(14 个 PromptModule tests + CLI 整测)
- `tests/tools/` — Phase 13 CLI 测试(`test_evolve_tool_params_cli.py`)是 NEW CLI 测试文件的直接 analog

**Files scanned:** 8 production + 4 test = 12 files

**Pattern extraction date:** 2026-05-15

**Phase 17 范围内的 "no new module file":** Phase 17 没有需要查找 analog 的全新生产模块 — 所有 production 改动都是 MODIFY 现有 2 文件,加 1 个 NEW 测试文件(其 analog 是 Phase 13 同名风格 CLI 测试)。
