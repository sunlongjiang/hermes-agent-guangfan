# Phase 18: Personality Drift Detection - Pattern Map

**Mapped:** 2026-05-15
**Files analyzed:** 10
**Analogs found:** 9 / 10（1 个为新建无直接类比的产物文件)

> **Read instruction:** 本文档为 `gsd-planner` 与 `gsd-execute-phase` 必读资产。所有代码摘录均带文件路径 + 行号,executor 可直接照搬骨架并按 CONTEXT.md 决策与 RESEARCH.md 风险锚改写差异点(差异点已在每个"Adaptation Delta"小节列出)。

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | 行号锚 | Match Quality |
|---|---|---|---|---|---|
| `evolution/prompts/drift_detector.py` (NEW) | LLM-as-judge constraint module | request-response (LLM judge × 3-run) | `evolution/prompts/prompt_constraints.py:32-147` (`PromptRoleChecker`) | 32-147 | exact (sibling class, 同接口) |
| `evolution/prompts/drift_calibration.py` (NEW) | dataset builder + F1 derivation | batch generation + transform | `evolution/prompts/prompt_dataset.py:69-154` (`PromptBehavioralDataset`) + `:160-329` (`PromptDatasetBuilder`) | 69-329 | exact (mirror builder + dataset 模式) |
| `evolution/prompts/evolve_prompt_sections.py` (MODIFY) | CLI integration / pipeline 插桩 | request-response (orchestrator) | 同文件 step 8b role check 块(行 493-501)+ step 11 metrics 写盘(行 772-796) | 493-501, 772-796, 839-877 | self-analog (Phase 17 已植入 role check + joint_* 字段) |
| `evolution/core/config.py` (OPTIONAL MODIFY) | config | — | 同文件 `EvolutionConfig.api_base / api_key` 字段(行 47-49) | 47-49 | role-match (planner 可选择不改 — 见 §Optional Path) |
| `datasets/prompts/drift_calibration.jsonl` (NEW) | persistent artifact (dataset) | file I/O | `PromptBehavioralDataset.save()` JSONL 行式落盘模式(prompt_dataset.py:85-101) | 85-101 | role-match (JSONL 行式 + git 跟踪的 stable asset) |
| `datasets/prompts/drift_thresholds.json` (NEW) | persistent artifact (config-time data) | file I/O | metrics.json 持久化模式(evolve_prompt_sections.py:794-796) | 794-796 | role-match(JSON 单文件 dump) |
| `.gitignore` (MODIFY) | gitignore mod | — | 现有 `datasets/.gitkeep` exception 模式(.gitignore:19) | 17-19 | exact |
| `tests/prompts/test_drift_detector.py` (NEW) | test scaffold | unit test | `tests/prompts/test_prompt_constraints.py:75-233` (`TestPromptRoleChecker`) | 75-233 | exact (sibling test class,同 mock 拓扑) |
| `tests/prompts/test_drift_calibration.py` (NEW) | test scaffold | unit test | `tests/prompts/test_prompt_dataset.py:192-327` (`TestPromptDatasetBuilder`) | 192-327 | exact |
| `tests/prompts/test_evolve_prompt_sections_cli.py` (MODIFY) | test scaffold | unit + integration | 同文件 `test_joint_mode_runs_inline_ab_baseline` (行 464-517) + `test_soft_gate_warns_but_does_not_block` (行 519-559) | 464-559 | self-analog |
| `tests/prompts/conftest.py` (CREATE — 当前不存在) | fixture | — | 沿用 `tests/tools/conftest.py` 内 `mock_lm_with_usage` Phase 13 pattern(RESEARCH §Test Fixture Pattern 已概要描述)+ test_prompt_constraints.py 内 `_make_checker` 辅助函数 | — | role-match (新建文件,沿用 Phase 13 fixture 风格) |

> **Note about `tests/prompts/conftest.py`:** 目录里**当前不存在** conftest.py(已用 `ls tests/prompts/` 确认)。Phase 18 是首次为该目录添加 conftest 的 phase — planner 与 executor 需 `Write` 而非 `Edit`。fixture 模式直接参考 `test_prompt_constraints.py:78-82` 的 `_make_checker` 与 RESEARCH.md §Test Fixture Pattern 的样例代码即可。

---

## Pattern Assignments

### File 1: `evolution/prompts/drift_detector.py` (NEW)

**Role:** LLM-as-judge constraint module (DriftDetector class + DriftScoreSignature inner Signature)
**Closest analog:** `evolution/prompts/prompt_constraints.py:32-147` (`PromptRoleChecker`)
**Interface contract (must match):**
- `class DriftDetector` with constructor `__init__(self, config: EvolutionConfig, thresholds: dict[str, float])`
- `def check(self, section_id: str, original_text: str, evolved_text: str) -> dict` — 返回包含 `section_id` / `per_dim` / `exceeded_count` / `severity` / `explanation` / `constraint_result: ConstraintResult` 的字典(RESEARCH §Code Examples Example 1 已固定形状)
- `def check_all(self, original_sections: list, evolved_sections: list) -> list[dict]` — 镜像 `PromptRoleChecker.check_all` 签名以便 pipeline drop-in
- Inner `class DriftScoreSignature(dspy.Signature)`:5 个 OutputField(`tone_score: float` / `formality_score: float` / `vocabulary_score: float` / `persona_score: float` / `explanation: str`)+ 3 个 InputField(`section_id` / `original_text` / `evolved_text`)
- 模块级常量 `DRIFT_DIMENSIONS = ("tone", "formality", "vocabulary", "persona")`

**Imports pattern** (prompt_constraints.py lines 1-13 + DriftDetector 新增项):

```python
"""Personality drift detection across 4 dimensions.

Compares original vs evolved prompt sections using a pairwise LLM judge.
3-run averaging at the final constraint gate (NOT inside GEPA). Threshold
per-dim from F1-optimized calibration. Severity ladder: 0 dims exceeded
= pass, 1 = warn, 2+ = reject.
"""

import json
import statistics
from typing import Optional

import dspy
from pydantic import ValidationError  # NEW — typed-float parse-failure fallback

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintResult
```

> **Adaptation Delta vs analog:** 新增 `import statistics`(3-run mean/stdev,RESEARCH §Don't Hand-Roll 已指定 stdlib)、`from pydantic import ValidationError`(RESEARCH §Pitfall B 强制 fallback 路径)。其余风格(模块 docstring → 单引号/双引号 → blank-line 分组)与 prompt_constraints.py 一致。

**Inner Signature pattern** (analog at prompt_constraints.py:44-66 — boolean output; DriftDetector 改 4 个 typed float):

```python
# prompt_constraints.py:44-66 (analog skeleton — DO NOT COPY VERBATIM)
class RoleCheckSignature(dspy.Signature):
    """Compare original and evolved prompt sections to verify role preservation.

    Determine whether the evolved section still fulfills the same functional
    role as the original. ...
    """
    section_id: str = dspy.InputField(
        desc="Section identifier (e.g. memory_guidance)",
    )
    original_text: str = dspy.InputField(
        desc="Original section text before evolution",
    )
    evolved_text: str = dspy.InputField(
        desc="Evolved section text to check",
    )
    role_preserved: bool = dspy.OutputField(
        desc="True if evolved text maintains the same functional role as original",
    )
    explanation: str = dspy.OutputField(
        desc="Explanation of role assessment",
    )
```

> **Adaptation Delta:** DriftDetector 改 `role_preserved: bool` → 4 个 `<dim>_score: float = dspy.OutputField(desc="<dim> drift 0.0 (same) - 1.0 (totally different)")` 字段;explanation 字段保留;docstring 添加 RESEARCH §Pattern 1 给出的"0.0=no drift, 1.0=total drift"语义 + "Output each score as a single decimal between 0.0 and 1.0, nothing else on the score lines"(RESEARCH §Assumption A4 反 Prefix-prefix-leak)。

**Core class pattern** (analog at prompt_constraints.py:68-113):

```python
# prompt_constraints.py:68-113 (analog — DriftDetector 需在 5 处偏离)
class PromptRoleChecker:
    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.checker = dspy.ChainOfThought(self.RoleCheckSignature)

    def check(
        self,
        section_id: str,
        original_text: str,
        evolved_text: str,
    ) -> ConstraintResult:
        lm = dspy.LM(self.config.eval_model, **self.config.get_lm_kwargs())

        with dspy.context(lm=lm):
            result = self.checker(
                section_id=section_id,
                original_text=original_text,
                evolved_text=evolved_text,
            )

        role_kept = _parse_bool(result.role_preserved)
        explanation = str(result.explanation)

        if role_kept:
            return ConstraintResult(
                passed=True,
                constraint_name="role_preservation",
                ...
            )
        else:
            return ConstraintResult(passed=False, ...)
```

> **Adaptation Delta — 5 个偏离点 (executor 必读 RESEARCH.md §Code Examples Example 1 的 832 行完整骨架,这里给出关键差异):**
>
> 1. **Constructor 接 `thresholds: dict[str, float]`** + 缺失维度校验:`missing = set(DRIFT_DIMENSIONS) - set(thresholds.keys()); if missing: raise ValueError(...)`
> 2. **LM 构造移到 `__init__` 并必须 `temperature=0.7`**(RESEARCH §Pitfall A / Risk Anchor 2 — `dspy.LM(config.eval_model, temperature=0.7, **config.get_lm_kwargs())`)— 不可像 PromptRoleChecker 那样每次 `check()` 内构造默认 LM。Belt-and-suspenders:同时加 `cache=False`(RESEARCH §Open Questions Q1 推荐)。
> 3. **新增 `_check_one_run(...)` 私有方法**返回 `tuple[dict[str, float], str]`,内部 `try/except (ValidationError, ValueError, TypeError)` 捕获后 fallback `{dim: 0.0 for dim in DRIFT_DIMENSIONS}`(RESEARCH §Pitfall B,**0.0 NOT 0.5**)+ explanation = `f"[Parse failure: {type(e).__name__}: {e}]"`。
> 4. **`check()` 内运行 3 次 `_check_one_run` 并做 `statistics.mean` / `statistics.stdev`**;`exceeded = (mean - sd) > self.thresholds[dim]`(D-ROB-02 保守判定)。
> 5. **`check()` 返回 dict 而非 bare `ConstraintResult`**:dict 包含 `per_dim`(每维 mean/stdev/exceeded/raw)+ `severity` ∈ {pass, warn, reject} + `constraint_result`(嵌套 ConstraintResult,`details` 字段 `json.dumps(per_dim, sort_keys=True)` 编码以供后续 metrics.json 与 drift_report.txt 双消费)。Severity ladder 三分支(D-GATE-01):0 exceeded → severity=pass / passed=True / message="Drift OK in '<sid>': no dims exceeded";1 exceeded → severity=warn / passed=True / message=`"Drift WARN in '<sid>': dim '<dim>' exceeded — review before deploying"`;2+ exceeded → severity=reject / passed=False / message=`"Drift REJECT in '<sid>': {count} dims exceeded"`。

**check_all pattern** (analog at prompt_constraints.py:115-147):

```python
# prompt_constraints.py:115-147 — DriftDetector 几乎原样照搬
def check_all(
    self,
    original_sections: list,
    evolved_sections: list,
) -> list[ConstraintResult]:
    original_map = {s.section_id: s for s in original_sections}
    results = []
    for evolved in evolved_sections:
        original = original_map.get(evolved.section_id)
        if original is None:
            continue
        result = self.check(
            evolved.section_id,
            original.text,
            evolved.text,
        )
        results.append(result)
    return results
```

> **Adaptation Delta:** 返回类型 `list[ConstraintResult]` → `list[dict]`(因 `check()` 返回 dict);其余 `original_map` lookup + 跳过 unmatched 的逻辑 1:1 沿用。

---

### File 2: `evolution/prompts/drift_calibration.py` (NEW)

**Role:** dataset builder + F1 threshold derivation
**Closest analog:** `evolution/prompts/prompt_dataset.py:69-154` (`PromptBehavioralDataset`) + `:160-329` (`PromptDatasetBuilder`)
**Interface contract:**
- `@dataclass class DriftCalibrationExample` with fields: `section_id: str`, `original_text: str`, `evolved_text: str`, `is_drift: bool`, `drift_dim: str`(one of `DRIFT_DIMENSIONS` 或 `"none"`), `generation_metadata: dict`
- `@dataclass class DriftCalibrationDataset` with `examples: list[DriftCalibrationExample]` + `save(path: Path)` / `load(path: Path) -> DriftCalibrationDataset` 类方法
- `class DriftCalibrationBuilder` with constructor `__init__(self, config: EvolutionConfig, seed: int = 42)` + `def generate(self, sections: list[PromptSection]) -> DriftCalibrationDataset`(5 section × 6 variant = 30 例,3 drift + 3 preserve per section,D-CAL-03)
- Module-level `def derive_thresholds(calibration: DriftCalibrationDataset, config: EvolutionConfig) -> dict[str, float]` — F1 暴力扫描([0.10, 0.90] step 0.05,RESEARCH §F1 Derivation Example 3)
- (Discretion)CLI 入口形式 planner 决:独立 `python -m evolution.prompts.build_drift_calibration` 子命令(推荐,quarterly 可重跑)或挂载到 `evolve_prompt_sections.py --build-calibration` 子模式

**Inner Signature pattern** (analog at prompt_dataset.py:180-194):

```python
# prompt_dataset.py:180-194 — analog
class GenerateSectionScenarios(dspy.Signature):
    """Generate behavioral test scenarios for a prompt section. ..."""
    section_text: str = dspy.InputField(desc="The prompt section text being tested")
    section_id: str = dspy.InputField(desc="Section identifier ...")
    num_scenarios: int = dspy.InputField(desc="Number of scenarios to generate")
    difficulty_mix: str = dspy.InputField(desc="...")
    scenarios: str = dspy.OutputField(desc="JSON array of ...")
```

> **Adaptation Delta:** 改 4 个 InputField(`original_text`, `mode` ∈ {drift, preserve}, `target_dim` ∈ DRIFT_DIMENSIONS ∪ {"none"})+ 1 个 OutputField(`evolved_text: str`)。Signature docstring 描述 drift / preserve 两个 mode 的语义 — 参考 RESEARCH §Example 4(prompt_dataset.py:160-198 + Mitigation 5 显式 per-dim 目标)。生成 prompt 措辞由 planner 撰写,**必须固定 seed**(D-CAL-01 / RESEARCH §Q3 推荐 seed=42 + `--seed` CLI flag 可覆盖)。

**Builder constructor + generate pattern** (analog at prompt_dataset.py:196-269 高 cherry-picked):

```python
# prompt_dataset.py:196-198 — constructor analog
def __init__(self, config: EvolutionConfig):
    self.config = config
    self.generator = dspy.ChainOfThought(self.GenerateSectionScenarios)

# prompt_dataset.py:277-280 — LM context analog
lm = dspy.LM(self.config.judge_model, **self.config.get_lm_kwargs())
all_examples: list[PromptBehavioralExample] = []
with dspy.context(lm=lm):
    for section_id, target_count in targets.items():
        ...
```

> **Adaptation Delta:**
> 1. **constructor 增 `seed: int = 42`** 并 store 到 `self.seed`;在 `generate()` 开头 `random.seed(self.seed)`(RESEARCH §Q3)。
> 2. **LM 用 `config.judge_model`(gpt-4.1)**而非 `eval_model`(RESEARCH §Calibration Anti-Bias Mitigation 1)— `dspy.LM(config.judge_model, temperature=0.9, **config.get_lm_kwargs())`(temp=0.9 提高多样性,RESEARCH §Mitigation 3)。
> 3. **生成循环结构改写**:用 `sections[:5]`(前 5 个 section,D-CAL-03)外层 + 内层先 3 次 drift(`for target_dim in ["tone", "formality", "vocabulary", "persona"][:3]` — planner 决 dim 轮转策略)再 3 次 preserve。每个 example 都 append `generation_metadata={"seed": ..., "generator_model": config.judge_model, "target_dim": ..., "hermes_repo_git_sha": <optional, RESEARCH §Q4>}`。
> 4. **不再做 80 例 D2 权重分配 + 50/25/25 split**(那是 `PromptDatasetBuilder` 的逻辑);calibration set 不分 train/val/holdout,直接以 `examples: list[...]` 形式整体落盘。

**Persistence pattern** (analog at prompt_dataset.py:85-123):

```python
# prompt_dataset.py:85-101 — save analog
def save(self, path: Path):
    path.mkdir(parents=True, exist_ok=True)
    for split_name, split_data in [
        ("train", self.train),
        ("val", self.val),
        ("holdout", self.holdout),
    ]:
        with open(path / f"{split_name}.jsonl", "w") as f:
            for ex in split_data:
                f.write(json.dumps(ex.to_dict()) + "\n")

# prompt_dataset.py:103-123 — load analog (round-trip ready)
@classmethod
def load(cls, path: Path) -> "PromptBehavioralDataset":
    dataset = cls()
    for split_name in ["train", "val", "holdout"]:
        split_file = path / f"{split_name}.jsonl"
        if split_file.exists():
            examples = []
            with open(split_file) as f:
                for line in f:
                    if line.strip():
                        examples.append(PromptBehavioralExample.from_dict(json.loads(line)))
            setattr(dataset, split_name, examples)
    return dataset
```

> **Adaptation Delta:** DriftCalibrationDataset.save / load 不分 split — 单一 `examples` 列表落 `datasets/prompts/drift_calibration.jsonl`(D-CAL-02)。`save(path: Path)` 接受**文件路径**(不是目录),`open(path, "w")` 直接行式写入;`load(cls, path: Path)` 同理读单文件。`drift_thresholds.json` 落盘使用 `json.dumps(thresholds, indent=2, sort_keys=True)`(参考 evolve_prompt_sections.py:794-796)单 JSON 文件。

**F1 derivation pattern** (NO analog in codebase — pure new logic per RESEARCH §F1 Derivation Example 3):

```python
def derive_thresholds(
    calibration: DriftCalibrationDataset,
    config: EvolutionConfig,
) -> dict[str, float]:
    """Brute-scan thresholds in [0.1, 0.9] step 0.05, pick F1-optimal per dim.

    Pure stdlib (sklearn not installed — verified RESEARCH §Risk Anchor 3).
    """
    # 第一遍:1-run-per-example collect raw scores (D-ROB-01: calibration is 1-run)
    detector = DriftDetector(config, thresholds={d: 0.5 for d in DRIFT_DIMENSIONS})
    scored: list[tuple[bool, str, dict[str, float]]] = []
    for ex in calibration.examples:
        scores, _ = detector._check_one_run(
            ex.section_id, ex.original_text, ex.evolved_text
        )
        scored.append((ex.is_drift, ex.drift_dim, scores))

    # 第二遍:per-dim 17 候选 × 30 例 F1 扫描
    best: dict[str, float] = {}
    for dim in DRIFT_DIMENSIONS:
        labeled = [
            (s[dim], (is_drift and dim_truth == dim))
            for is_drift, dim_truth, s in scored
        ]
        best_t, best_f1 = 0.5, -1.0
        for t10 in range(10, 91, 5):  # 0.10, 0.15, ..., 0.90 → 17 candidates
            t = t10 / 100
            tp = sum(1 for sc, gt in labeled if sc > t and gt)
            fp = sum(1 for sc, gt in labeled if sc > t and not gt)
            fn = sum(1 for sc, gt in labeled if sc <= t and gt)
            if tp == 0:
                f1 = 0.0
            else:
                p = tp / (tp + fp)
                r = tp / (tp + fn)
                f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            if f1 > best_f1:
                best_t, best_f1 = t, f1
            # Tie-break: 当前 if 是严格 >,自动保留较小 t(更保守,RESEARCH §F1 Edge Cases)
        best[dim] = best_t
    return best
```

> **Adaptation Delta vs analog:** 无直接 analog — F1 derivation 是 Phase 18 唯一全新算法。参考 RESEARCH §Code Examples Example 3 完整。注意 edge cases:tie 规则文档化为"取更小 t"(更保守);all-zero F1 emit warning + fallback `t=0.5`(D-CAL-05 隐含);per-dim 正例样本可能只有 3-4 个(RESEARCH §Verification F1 Targets),F1 ≥ 0.85 不达标时 planner 需触发 Tier 2 macro-F1 fallback。

---

### File 3: `evolution/prompts/evolve_prompt_sections.py` (MODIFY)

**Role:** CLI integration / pipeline 插桩
**Self-analog locations:** Phase 17 已在同文件加 `joint_*` metrics 字段、A/B baseline 块、软门 stdout 警告 — Phase 18 完全照同样模式叠加 `drift_*` 字段、3-run 检查块、severity ladder 警告。

#### Insertion point 1 — Step 8c DriftDetector 调用块

**Insert location:** 在 lines **501** (8b role check 结束) **之后**, **502** (现有 "Print all constraint results" 块) **之前**。

**Anchor — existing step 8b code** (evolve_prompt_sections.py:493-501):

```python
    # 8b. Role preservation check
    console.print("  Running role preservation check...")
    role_checker = PromptRoleChecker(config)
    role_results = role_checker.check_all(original_sections, evolved_sections)
    all_constraint_results.extend(role_results)
    for r in role_results:
        if not r.passed:
            all_pass = False
```

**Insert delta** (新增 step 8c — DriftDetector 3-run 门):

```python
    # 8c. Personality drift check (Phase 18) — 3-run averaged per dim
    console.print("  Running personality drift detection (3-run averaging)...")
    drift_thresholds = json.loads(drift_thresholds_path.read_text())
    drift_detector = DriftDetector(config, drift_thresholds)
    drift_results = drift_detector.check_all(original_sections, evolved_sections)

    drift_exceeded_dims: list[dict] = []  # for metrics.json
    drift_per_dim_metrics: dict[str, dict] = {}
    drift_report_lines: list[str] = []  # for drift_report.txt

    for dr in drift_results:
        all_constraint_results.append(dr["constraint_result"])
        if not dr["constraint_result"].passed:
            all_pass = False
        # Aggregate for metrics.json (D-OUT-02)
        drift_per_dim_metrics[dr["section_id"]] = {
            dim: {"mean": v["mean"], "stdev": v["stdev"], "exceeded": v["exceeded"]}
            for dim, v in dr["per_dim"].items()
        }
        for dim, v in dr["per_dim"].items():
            if v["exceeded"]:
                drift_exceeded_dims.append({"section": dr["section_id"], "dim": dim})

        # Severity-ladder stdout (D-GATE-03 / D-GATE-04)
        if dr["severity"] == "warn":
            exceeded_dim = next(d for d, v in dr["per_dim"].items() if v["exceeded"])
            t = drift_thresholds[exceeded_dim]
            mean = dr["per_dim"][exceeded_dim]["mean"]
            console.print(
                f"  [yellow]Drift warning: section '{dr['section_id']}' "
                f"dim '{exceeded_dim}' = {mean:.2f} (threshold {t:.2f}) — "
                f"review evolved text before deploying[/yellow]"
            )
        elif dr["severity"] == "reject":
            console.print(
                f"  [red]Drift detected: section '{dr['section_id']}' "
                f"exceeded {dr['exceeded_count']} dims — REJECTED, "
                f"evolved prompts NOT deployed[/red]"
            )

        # Build drift_report.txt sections (D-OUT-03 — last-run explanation only)
        drift_report_lines.append(f"## Section: {dr['section_id']}\n")
        for dim, v in dr["per_dim"].items():
            decision = "pass" if not v["exceeded"] else (
                "warn" if dr["severity"] == "warn" else "reject"
            )
            drift_report_lines.append(
                f"### Dim: {dim}\n"
                f"- Mean: {v['mean']:.4f}\n"
                f"- Stdev: {v['stdev']:.4f}\n"
                f"- Threshold: {drift_thresholds[dim]:.2f}\n"
                f"- Decision: {decision}\n"
                f"- Raw scores: {v['raw']}\n"
            )
        drift_report_lines.append(f"\n**Explanation:** {dr['explanation']}\n\n")

    drift_passed = not any(
        dr["severity"] == "reject" for dr in drift_results
    )

    # Rich Table (D-OUT-01) — 5 sections × 4 dims
    drift_table = Table(title="Drift Detection (per-section × per-dim, 3-run averaged)")
    drift_table.add_column("Section", style="bold")
    drift_table.add_column("Dim")
    drift_table.add_column("Mean", justify="right")
    drift_table.add_column("Stdev", justify="right")
    drift_table.add_column("Threshold", justify="right")
    drift_table.add_column("Exceeded", justify="center")
    drift_table.add_column("Status")
    for dr in drift_results:
        for dim in ("tone", "formality", "vocabulary", "persona"):
            v = dr["per_dim"][dim]
            exc_str = "[red]x[/red]" if v["exceeded"] else "[green]✓[/green]"
            status = ""
            if dr["severity"] == "warn" and v["exceeded"]:
                status = "[yellow]WARN[/yellow]"
            elif dr["severity"] == "reject" and v["exceeded"]:
                status = "[red]REJECT[/red]"
            drift_table.add_row(
                dr["section_id"], dim,
                f"{v['mean']:.3f}", f"{v['stdev']:.3f}",
                f"{drift_thresholds[dim]:.2f}", exc_str, status,
            )
    console.print(drift_table)
```

> **Adaptation Delta:** 完全新代码,但模仿 evolve_prompt_sections.py 现有局部惯例 — `console.print()` Rich markup、`Path(...).read_text()`、`json.loads` / `json.dumps`、`Table.add_column(..., justify="right")` 风格(Phase 17 step 10 `result_table` lines 728-748 是同一风格)。

#### Insertion point 2 — Step 8d/11 metrics.json drift_* 字段

**Anchor — existing step 11 metrics dict** (evolve_prompt_sections.py:772-796):

```python
    metrics = {
        "timestamp": timestamp,
        "mode": effective_mode,
        "iterations": iterations,
        ...
        "constraints_passed": True,
    }
    # Joint-mode-only A/B baseline fields (D-OUT-02 + W3 explicit A/B delta)
    if effective_mode == "joint" and roundrobin_baseline_score is not None:
        metrics["joint_score"] = evolved_score
        metrics["roundrobin_baseline_score"] = roundrobin_baseline_score
        metrics["epsilon_pp"] = EPSILON_PP
        metrics["joint_vs_roundrobin_delta_pp"] = joint_vs_roundrobin_delta_pp
        metrics["ab_elapsed_seconds"] = ab_elapsed
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2)
    )
```

**Insert delta — 在 `metrics["ab_elapsed_seconds"] = ab_elapsed` 之后,write_text 之前**(D-OUT-02):

```python
    # Drift detection fields (Phase 18 / D-OUT-02) — joint AND round-robin
    if drift_results:  # only present when step 8c ran (always, since 18+)
        metrics["drift_per_dim"] = drift_per_dim_metrics
        metrics["drift_thresholds"] = drift_thresholds
        metrics["drift_exceeded_dims"] = drift_exceeded_dims
        metrics["drift_passed"] = drift_passed
        # Find max dim/section by mean score (D-OUT-02)
        if drift_exceeded_dims:
            max_entry = max(
                ((sid, dim, drift_per_dim_metrics[sid][dim]["mean"])
                 for sid in drift_per_dim_metrics
                 for dim in drift_per_dim_metrics[sid]),
                key=lambda x: x[2],
            )
            metrics["drift_max_section"] = max_entry[0]
            metrics["drift_max_dim"] = max_entry[1]
        # constraints_passed already reflects drift via `all_pass` — no override needed.

    # NEW — drift_report.txt write (D-OUT-03)
    (output_dir / "drift_report.txt").write_text("".join(drift_report_lines))
```

> **Adaptation Delta:** Phase 17 已建立"`if effective_mode == "joint": metrics[...] = ...`"风格,Phase 18 同款,只是条件是 `if drift_results:`(round-robin 也写,因为 D-OUT-02 明确两 mode 都写)。`drift_report.txt` 写盘同 `evolved_sections.json` / `diff.txt` 平级(evolve_prompt_sections.py:760-762 / :799-800)。

#### Insertion point 3 — FAILED_<ts>/ 路径也写 drift_report.txt

**Anchor — existing FAILED_<ts>/ 块** (evolve_prompt_sections.py:510-528):

```python
    if not all_pass:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("output") / "prompts" / f"FAILED_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "metrics.json").write_text(
            json.dumps(
                {
                    "timestamp": timestamp,
                    "status": "FAILED",
                    "constraints_passed": False,
                },
                indent=2,
            )
        )
        console.print(
            "[red]Constraint validation FAILED -- not deploying[/red]"
        )
        console.print(f"  Saved failed results to {output_dir}/")
        return
```

**Insert delta — 在 `output_dir.mkdir(...)` 之后, `(output_dir / "metrics.json").write_text(...)` 之前**(D-GATE-04 / D-OUT-03):

```python
        # Phase 18: FAILED 路径下也写 drift artifact 便于事后排查
        if drift_results:
            (output_dir / "drift_report.txt").write_text("".join(drift_report_lines))
            # 也补 evolved_sections.json + diff.txt(便于人工 review 拒绝原因)
            evolved_data = [
                {"section_id": s.section_id, "text": s.text}
                for s in evolved_sections
            ]
            (output_dir / "evolved_sections.json").write_text(
                json.dumps(evolved_data, indent=2)
            )
            (output_dir / "diff.txt").write_text(
                _generate_diff(original_sections, evolved_sections)
            )
        # 同时把 drift_* 字段写进 FAILED_<ts>/metrics.json
        failed_metrics = {
            "timestamp": timestamp,
            "status": "FAILED",
            "constraints_passed": False,
        }
        if drift_results:
            failed_metrics["drift_passed"] = drift_passed
            failed_metrics["drift_per_dim"] = drift_per_dim_metrics
            failed_metrics["drift_thresholds"] = drift_thresholds
            failed_metrics["drift_exceeded_dims"] = drift_exceeded_dims
        (output_dir / "metrics.json").write_text(
            json.dumps(failed_metrics, indent=2)
        )
        # 原本下面的 metrics.json write_text 行需删掉(被上面覆盖)
```

> **Adaptation Delta:** 把原 inline 的 `metrics.json` 写盘提取为 `failed_metrics` dict,允许按需追加 drift_* 字段(D-GATE-04 要 `drift_passed: false` 出现在 FAILED metrics 中)。

#### Insertion point 4 — `--drift-thresholds-path` Click option + main 签名

**Anchor — existing CLI option block** (evolve_prompt_sections.py:839-877):

```python
@click.command()
@click.option(
    "--section",
    default=None,
    help="Section ID to optimize (default: all sections)",
)
@click.option(
    "--iterations",
    default=10,
    help="Number of GEPA iterations per section",
)
...
@click.option(
    "--mode",
    default="joint",
    type=click.Choice(["joint", "round-robin"]),
    help="...",
)
def main(section, iterations, eval_source, hermes_repo, dry_run, model, api_base, mode):
    evolve(
        section=section,
        iterations=iterations,
        ...
        mode=mode,
    )
```

**Insert delta — 紧贴 `--mode` option 后(在 `def main(...)` 上方)**:

```python
@click.option(
    "--drift-thresholds-path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("datasets/prompts/drift_thresholds.json"),
    help="Path to drift_thresholds.json (per-dim F1-optimized thresholds derived "
         "by `python -m evolution.prompts.build_drift_calibration`). Phase 18 "
         "D-BYPASS-02 — there is NO --no-drift-check / --skip-drift-check flag. "
         "WARNING: do not bypass without re-calibrating thresholds.",
)
def main(section, iterations, eval_source, hermes_repo, dry_run,
         model, api_base, mode, drift_thresholds_path):
    evolve(
        section=section,
        ...
        mode=mode,
        drift_thresholds_path=drift_thresholds_path,
    )
```

> **Adaptation Delta:** `click.Path(exists=True, path_type=Path)` 沿用现有 `--hermes-repo` 路径风格(类似 Phase 17 `Path` 类型转换);**故意不加**任何 `--no-drift-check` / `--skip-drift-check`(D-BYPASS-01 prevention)。executor 须在 `evolve(...)` 函数签名处 + 函数体处对应增加 `drift_thresholds_path: Path` 参数。

---

### File 4: `evolution/core/config.py` (OPTIONAL MODIFY)

**Role:** config(可选添加 `drift_thresholds_path` 字段)
**Closest analog:** `EvolutionConfig.api_base / api_key: Optional[...] = None` 字段(config.py:47-49)
**Interface contract:** 如 planner 选择 config-routed 路径,则在 `EvolutionConfig` 加 `drift_thresholds_path: Optional[Path] = None` 字段;否则 planner 应明确写在 PLAN.md "此 phase 不修改 config.py — drift_thresholds_path 仅作为 Click flag + 函数参数透传"。

**Anchor — existing Optional field block** (config.py:46-49):

```python
    # API endpoint configuration
    api_base: Optional[str] = None  # Custom OpenAI-compatible API base URL
    api_key: Optional[str] = None  # Custom API key
```

**Insert delta (if planner chooses config-routed path):**

```python
    # Phase 18: Drift detection thresholds path
    # Default = datasets/prompts/drift_thresholds.json (derived via
    # python -m evolution.prompts.build_drift_calibration). CLI flag
    # --drift-thresholds-path overrides this.
    drift_thresholds_path: Optional[Path] = None
```

> **Adaptation Delta + Recommendation:** RESEARCH §Integration Points + CONTEXT §`canonical_refs` 都把这一字段标为 "可选(planner 权衡)"。**推荐**:不改 config.py。理由:`--drift-thresholds-path` 是单一 CLI flag,直接在 `evolve()` 签名透传比走 EvolutionConfig 更直接,且 evolve_prompt_sections.py 已有 `--hermes-repo` 不走 config 的先例(它直接 store 到 `config.hermes_agent_path`)。若 planner 决定走 config 路径,executor 需补 `EvolutionConfig.load(..., drift_thresholds_path=...)` 的 `**overrides` 分支(config.py:163-190 风格)。

---

### File 5: `datasets/prompts/drift_calibration.jsonl` (NEW — persistent artifact)

**Role:** persistent artifact (calibration dataset,git-tracked)
**Closest analog (JSONL 行式落盘):** `PromptBehavioralDataset.save()` (prompt_dataset.py:85-101)
**Schema (per line):**
```json
{"section_id": "memory_guidance", "original_text": "...", "evolved_text": "...", "is_drift": true, "drift_dim": "tone", "generation_metadata": {"seed": 42, "generator_model": "openai/gpt-4.1", "target_dim": "tone", "generation_timestamp": "2026-05-15T..."}}
```
**Interface contract:** 由 `DriftCalibrationBuilder.generate()` + `DriftCalibrationDataset.save()` 写入;`DriftDetector` 与 `derive_thresholds()` 通过 `DriftCalibrationDataset.load()` 读取。
**Insertion / location:** 文件由 `python -m evolution.prompts.build_drift_calibration`(或 planner 选择的 CLI 入口)生成;phase 18 工期内 commit 入 git(D-CAL-02)。

> **Adaptation Delta vs analog:** 不分 train/val/holdout splits — calibration set 是 30 例单文件(D-CAL-03)。schema 字段命名与 `DriftCalibrationExample` dataclass 1:1。

---

### File 6: `datasets/prompts/drift_thresholds.json` (NEW — persistent artifact)

**Role:** persistent artifact (derived F1-optimized thresholds,git-tracked)
**Closest analog (JSON dump):** `metrics.json` 写盘模式(evolve_prompt_sections.py:794-796)
**Schema:**
```json
{
  "tone": 0.55,
  "formality": 0.50,
  "vocabulary": 0.45,
  "persona": 0.65,
  "_meta": {
    "derived_from": "datasets/prompts/drift_calibration.jsonl",
    "f1_self": {"tone": 0.88, "formality": 0.83, "vocabulary": 0.91, "persona": 0.87, "macro": 0.87},
    "f1_fresh": {"tone": 0.82, "formality": 0.71, "vocabulary": 0.85, "persona": 0.79, "macro": 0.79},
    "f1_tier": 2,
    "f1_warned_dims": ["formality"],
    "calibration_timestamp": "2026-05-15T...",
    "generator_model": "openai/gpt-4.1",
    "judge_model": "openai/gpt-4.1-mini"
  }
}
```
**Interface contract:** 由 `derive_thresholds(...)` + Tier-gating 逻辑写入;`DriftDetector` 通过 `json.loads(drift_thresholds_path.read_text())` 加载顶层 4 个 dim 键(RESEARCH §F1 Verification Targets Tier table)。`_meta` 字段对 detector 是 ignored,仅 ops 追溯。

> **Adaptation Delta:** 顶层 4 dim 键是必读 contract;`_meta` 字段命名与 RESEARCH §Verification F1 Targets §Action for planner 列出的 `f1_self` / `f1_fresh` / `f1_tier` / `f1_warned_dims` 对齐。落盘用 `json.dumps(..., indent=2, sort_keys=True)` 沿用 evolve_prompt_sections.py:794-796 风格。

---

### File 7: `.gitignore` (MODIFY)

**Role:** gitignore mod — 给 calibration / thresholds 加 git-track exception
**Closest analog:** 现有 `!datasets/.gitkeep` exception 行(`.gitignore:19`)

**Anchor — existing exception** (.gitignore:16-19):

```gitignore
# Generated eval datasets (local, not shared)
datasets/**/*.jsonl
datasets/**/*.json
!datasets/.gitkeep
```

**Insert delta — 在 `!datasets/.gitkeep` 之后追加两行**(D-CAL-02):

```gitignore
# Phase 18: drift calibration assets are stable evaluation artifacts (like golden sets),
# tracked in git so threshold derivation is reproducible across machines / quarterly recals.
!datasets/prompts/drift_calibration.jsonl
!datasets/prompts/drift_thresholds.json
```

> **Adaptation Delta:** 严格沿用现有 `!datasets/.gitkeep` 注释 + exception 句法。两个 `!` 通配前的 `datasets/**/*.jsonl` 与 `datasets/**/*.json` 顺序很关键(`.gitignore` 顺序敏感:negation 必须在原 ignore 之后) — 安全因为我们追加到现有 4 行之尾。

---

### File 8: `tests/prompts/test_drift_detector.py` (NEW)

**Role:** test scaffold(DriftDetector 单元测)
**Closest analog:** `tests/prompts/test_prompt_constraints.py:75-233` (`TestPromptRoleChecker` + `TestGrowthConstraint`)
**Interface contract:** 9 个测试场景(per RESEARCH §Test Map):
- `test_check_returns_4_dim_scores` — check() 返回 dict 含全 4 维 mean/stdev/exceeded/raw
- `test_severity_ladder_pass` — 0 exceeded → severity="pass" / passed=True
- `test_severity_ladder_warn` — 1 exceeded → severity="warn" / passed=True / stdout yellow
- `test_severity_ladder_reject` — 2+ exceeded → severity="reject" / passed=False
- `test_typed_float_parsing` — DSPy typed float OutputField 正确解析
- `test_parse_failure_fallback_zero` — ValidationError 时 fallback 0.0 (NOT 0.5)
- `test_lm_constructed_with_temperature` — dspy.LM 接收 `temperature=0.7` (RESEARCH §Pitfall A 验证)
- `test_three_run_stdev_nonzero` — 3-run averaging 在 mock stochastic LM 下 stdev > 0
- `test_conservative_decision_rule` — `mean - 1·stdev > threshold` 边界 case 测试

**Helper pattern** (analog at test_prompt_constraints.py:78-82):

```python
# test_prompt_constraints.py:78-82 — analog
def _make_checker(self):
    """Create a PromptRoleChecker with mocked config."""
    config = EvolutionConfig.__new__(EvolutionConfig)
    config.eval_model = "openai/gpt-4.1-mini"
    return PromptRoleChecker(config)
```

> **Adaptation Delta:** DriftDetector 构造期会立刻调 `dspy.LM(...)`,helper 内必须 `patch("evolution.prompts.drift_detector.dspy.LM")` 包裹返回值。helper 改成:
> ```python
> def _make_detector(self, thresholds=None):
>     config = EvolutionConfig.__new__(EvolutionConfig)
>     config.eval_model = "openai/gpt-4.1-mini"
>     config.api_base = None
>     config.api_key = None
>     thresholds = thresholds or {"tone": 0.5, "formality": 0.5,
>                                  "vocabulary": 0.5, "persona": 0.5}
>     with patch("evolution.prompts.drift_detector.dspy.LM"):
>         return DriftDetector(config, thresholds)
> ```

**Mock pattern** (analog at test_prompt_constraints.py:84-105 — `test_check_role_preserved`):

```python
# test_prompt_constraints.py:84-105 — analog
def test_check_role_preserved(self):
    checker = self._make_checker()
    mock_result = MagicMock()
    mock_result.role_preserved = "True"
    mock_result.explanation = "Role maintained: still provides memory guidance"
    with patch.object(checker, "checker", return_value=mock_result):
        with patch("evolution.prompts.prompt_constraints.dspy.LM"):
            with patch("evolution.prompts.prompt_constraints.dspy.context"):
                result = checker.check(
                    "memory_guidance",
                    "Guide the agent on memory usage.",
                    "Help the agent use memory effectively.",
                )
    assert isinstance(result, ConstraintResult)
    assert result.passed is True
```

> **Adaptation Delta:** DriftDetector 的 `check()` 内部跑 **3 次** `judge(...)`,所以 `patch.object(detector, "judge", side_effect=[mock_run_1, mock_run_2, mock_run_3])` 而非 `return_value=...`;每个 mock 必须有 4 个 score 属性 + explanation。`assert result["per_dim"]["tone"]["mean"]` 替代 `assert result.passed`,且 `result["constraint_result"]` 是嵌套 ConstraintResult。

---

### File 9: `tests/prompts/test_drift_calibration.py` (NEW)

**Role:** test scaffold(DriftCalibrationBuilder + derive_thresholds 单元测)
**Closest analog:** `tests/prompts/test_prompt_dataset.py:192-327` (`TestPromptDatasetBuilder`)
**Interface contract:** 4 个测试场景(per RESEARCH §Test Map):
- `test_derive_thresholds_f1_optimal` — 给定 mock 1-run scores,F1 derivation 选出 F1 最优 threshold
- `test_no_sklearn_dependency` — F1 derivation 不 `import sklearn`(grep + AST assertion)
- `test_generator_uses_judge_model` — DriftCalibrationBuilder 内 `dspy.LM` 被传 `config.judge_model`(不是 `eval_model`,RESEARCH §Mitigation 1)
- `test_f1_target_self_eval` — F1 ≥ 0.85 on calibration set itself,**`@pytest.mark.skipif(not os.getenv("RUN_LIVE_LLM"))`**(live LLM 测,默认 skip)

**Side-effect generator pattern** (analog at test_prompt_dataset.py:282-296):

```python
# test_prompt_dataset.py:282-296 — analog
def generator_side_effect(**kwargs):
    section_id = kwargs.get("section_id", "")
    num_scenarios = kwargs.get("num_scenarios", 0)
    call_log.append({"section_id": section_id, "num_scenarios": num_scenarios})
    result = MagicMock()
    scenarios = [
        {
            "user_message": f"Scenario {i} for {section_id}",
            "expected_behavior": f"Expected behavior {i}",
            "difficulty": ["easy", "medium", "hard"][i % 3],
        }
        for i in range(num_scenarios)
    ]
    result.scenarios = json.dumps(scenarios)
    return result
builder.generator = MagicMock(side_effect=generator_side_effect)
```

> **Adaptation Delta:** 对 DriftCalibrationBuilder,side_effect 函数读 `kwargs["mode"]` ∈ {drift, preserve} + `kwargs["target_dim"]`,返回 `MagicMock(evolved_text=f"<rewritten for {target_dim} ...>")`。call_log 记录 mode+target_dim 二元组,assert 5 section × 6 variant = 30 次调用,且 drift / preserve = 15 / 15。

---

### File 10: `tests/prompts/test_evolve_prompt_sections_cli.py` (MODIFY)

**Role:** test scaffold(扩展 — 新增 drift gate 触发路径 3 个测试)
**Self-analog:** 同文件 `TestJointPipeline._ab_patched_run` (lines 250-462) 与 `test_joint_mode_runs_inline_ab_baseline` (lines 464-517) — Phase 18 完全照搬此 multi-patch 风格,只是 `PromptRoleChecker` mock 旁加 `DriftDetector` mock。

**Anchor — existing patch stack** (test_evolve_prompt_sections_cli.py:417-447 — `_ab_patched_run`):

```python
with patch(
    "evolution.prompts.evolve_prompt_sections.extract_prompt_sections",
    return_value=fake_sections,
), patch(
    "evolution.prompts.evolve_prompt_sections.PromptDatasetBuilder",
    return_value=mock_builder_instance,
), patch(
    "evolution.prompts.evolve_prompt_sections.PromptBehavioralMetric",
    return_value=mock_metric_instance,
), patch(
    "evolution.prompts.evolve_prompt_sections.ConstraintValidator",
    return_value=mock_constraint,
), patch(
    "evolution.prompts.evolve_prompt_sections.PromptRoleChecker",
    return_value=mock_role,
), patch(
    "evolution.prompts.evolve_prompt_sections.PromptModule",
    side_effect=_make_spy_module,
), patch(
    "evolution.prompts.evolve_prompt_sections.dspy.GEPA"
) as mock_gepa, patch(
    "evolution.prompts.evolve_prompt_sections.dspy.LM"
), patch(
    "evolution.prompts.evolve_prompt_sections.dspy.configure"
), patch(
    "evolution.prompts.evolve_prompt_sections.dspy.context",
    MagicMock(),
):
```

**Insert delta — 在 `PromptRoleChecker` patch 之后增加 DriftDetector patch**:

```python
    ), patch(
        "evolution.prompts.evolve_prompt_sections.DriftDetector",
        return_value=mock_drift,
    ), patch(
        # drift_thresholds_path is a click.Path(exists=True) — must stub readable file
        "pathlib.Path.read_text",
        return_value=json.dumps({"tone": 0.5, "formality": 0.5,
                                 "vocabulary": 0.5, "persona": 0.5}),
    ),
```

**Three new tests to add** (helper + test signatures):

```python
def test_metrics_json_has_drift_fields(self, tmp_path):
    """metrics.json contains drift_per_dim / drift_thresholds / drift_passed."""
    # mock_drift.check_all.return_value = [
    #     {"section_id": "section_0", "per_dim": {...all 4 dims with exceeded=False}},
    #     ...
    # ]
    # ... assert json.loads(metrics).keys() ⊇ {"drift_per_dim", "drift_thresholds", "drift_passed", ...}

def test_drift_thresholds_path_flag(self, tmp_path):
    """--drift-thresholds-path accepts custom path; default resolves to datasets/prompts/."""
    # Write custom thresholds file to tmp_path/custom_thresholds.json
    # Invoke main([..., "--drift-thresholds-path", str(custom)])
    # Assert exit_code == 0 + custom thresholds embedded in metrics["drift_thresholds"]

def test_no_skip_drift_flag(self):
    """Regression guard: --no-drift-check / --skip-drift-check are NOT registered (D-BYPASS-01)."""
    runner = CliRunner()
    result = runner.invoke(main, ["--no-drift-check"], catch_exceptions=False)
    assert result.exit_code != 0  # Click rejects unknown flag
    assert "no such option" in result.output.lower() or "no-drift-check" in result.output
```

> **Adaptation Delta:** 完全沿用 `_ab_patched_run` multi-patch 风格;唯一新增是 `DriftDetector` 与 `pathlib.Path.read_text` 的 patches。`mock_drift` 是 `MagicMock()` 其 `check_all` 返回**预先构造的 drift dict list**(与 DriftDetector.check 返回 schema 1:1)。

---

### File 11: `tests/prompts/conftest.py` (CREATE — 当前不存在)

**Role:** fixture (mock_drift_lm + dummy_thresholds)
**Closest analog:** RESEARCH §Test Fixture Pattern 示例代码 + test_prompt_constraints.py:78-82 `_make_checker` 辅助函数

**Interface contract:**
- `mock_drift_lm` fixture — patch `dspy.LM` 返回可设分数的 mock(`mock.set_scores(tone=0.8, ...)`)
- `dummy_thresholds` fixture — 返回占位值 `{"tone": 0.55, "formality": 0.50, "vocabulary": 0.45, "persona": 0.65}`(D-CAL-01 placeholder)

**Full pattern** (直接照搬 RESEARCH §Test Fixture Pattern):

```python
# tests/prompts/conftest.py (NEW FILE)
import pytest
from unittest.mock import patch
import dspy


@pytest.fixture
def mock_drift_lm():
    """Patch dspy.LM to return predictable 4-dim drift scores.

    Usage in test:
        def test_severity_ladder_warn(mock_drift_lm):
            mock_drift_lm.set_scores(tone=0.8, formality=0.2,
                                     vocabulary=0.2, persona=0.2)
            # ... DriftDetector instance, check, assert severity=='warn'
    """
    class _MockLM:
        def __init__(self):
            self._scores = {"tone": 0.0, "formality": 0.0,
                            "vocabulary": 0.0, "persona": 0.0}
            self._explanation = "mock"

        def set_scores(self, **kwargs):
            self._scores.update(kwargs)

        # ... DSPy LM call interface — planner / executor 完善
        # (likely __call__ returning dspy.Prediction shape)

    mock = _MockLM()
    with patch("evolution.prompts.drift_detector.dspy.LM", return_value=mock):
        yield mock


@pytest.fixture
def dummy_thresholds():
    """Placeholder drift thresholds matching D-CAL-01 example values."""
    return {
        "tone": 0.55,
        "formality": 0.50,
        "vocabulary": 0.45,
        "persona": 0.65,
    }
```

> **Adaptation Delta:** 当前 tests/prompts 目录无 conftest.py(已用 `ls` 验证) — 这是首次创建。其余 fixture pattern 直接照 RESEARCH §Test Fixture Pattern 抄。planner 须决定 `_MockLM.__call__` 的精确 DSPy Prediction 形状(返回 `dspy.Prediction(tone_score=0.8, formality_score=0.2, ...)` 还是返回更 lower-level 的 chat completion 形状);**推荐**用 `dspy.Prediction(**self._scores, explanation=self._explanation)` 因为 DriftDetector.judge 是 `dspy.ChainOfThought` 直接消费 Prediction。

---

## Shared Patterns

### Shared Pattern 1: LLM-as-judge with `dspy.ChainOfThought` + typed OutputField + ValidationError fallback

**Source:** `evolution/prompts/prompt_constraints.py:44-66` (Signature) + `:68-95` (`dspy.LM` + `dspy.context` 包裹 + `self.checker(...)` 调用) + RESEARCH §Pattern 1 (typed float + ValidationError fallback)
**Apply to:** `drift_detector.py`(主)、间接 `drift_calibration.py:GenerateDriftVariant`(generator 也用 ChainOfThought,但单一 str output 不需要 ValidationError fallback)

**Excerpt** (prompt_constraints.py:88-95):

```python
lm = dspy.LM(self.config.eval_model, **self.config.get_lm_kwargs())
with dspy.context(lm=lm):
    result = self.checker(
        section_id=section_id,
        original_text=original_text,
        evolved_text=evolved_text,
    )
```

> **Phase 18 augmentation:** LM 构造必须显式 `temperature=0.7, cache=False`(RESEARCH §Pitfall A / Open Q1);对 DriftDetector 把 `dspy.LM(...)` 提到 `__init__` 避免每次 check 重新构造;`self.checker(...)` 调用必须 wrap 在 `try/except (ValidationError, ValueError, TypeError)` 内,fallback 全 0.0(RESEARCH §Pitfall B)。

### Shared Pattern 2: ConstraintResult-compatible payload

**Source:** `evolution/core/constraints.py:15-22`
**Apply to:** DriftDetector 的所有 `check_all` 返回项的 `constraint_result` 字段

**Excerpt** (constraints.py:15-22):

```python
@dataclass
class ConstraintResult:
    """Result of constraint validation."""
    passed: bool
    constraint_name: str
    message: str
    details: Optional[str] = None
```

> **Phase 18 augmentation:** DriftDetector 使用 `details=json.dumps(per_dim, sort_keys=True)`(D-OUT-02 决策 — details 字段 stash JSON-encoded payload)以与 PromptRoleChecker 输出 schema 互不冲突。

### Shared Pattern 3: stdout Rich Table for per-section × per-metric matrix

**Source:** `evolution/prompts/evolve_prompt_sections.py:727-748` (`result_table = Table(title="Evolution Results")`)
**Apply to:** evolve_prompt_sections.py step 8c 新增 drift_table(D-OUT-01)

**Excerpt** (evolve_prompt_sections.py:727-748):

```python
result_table = Table(title="Evolution Results")
result_table.add_column("Metric", style="bold")
result_table.add_column("Baseline", justify="right")
result_table.add_column("Evolved", justify="right")
result_table.add_column("Change", justify="right")

change_color = "green" if improvement > 0 else "red"
result_table.add_row(
    "Holdout Score",
    f"{baseline_score:.3f}",
    f"{evolved_score:.3f}",
    f"[{change_color}]{improvement:+.3f}[/{change_color}]",
)
console.print(result_table)
```

> **Phase 18 augmentation:** drift_table 列数 7 vs Evolution Results 4 列 — 但风格(title 大小、`style="bold"` 首列、`justify="right"` 数值列、`[color]...[/color]` 内联标记)1:1 沿用。

### Shared Pattern 4: metrics.json conditional field block

**Source:** `evolution/prompts/evolve_prompt_sections.py:786-793`(`if effective_mode == "joint": metrics["joint_score"] = ...`)
**Apply to:** evolve_prompt_sections.py step 11 增 drift_* 块、FAILED_<ts>/ 块同样追加

**Excerpt** (evolve_prompt_sections.py:786-793):

```python
if effective_mode == "joint" and roundrobin_baseline_score is not None:
    metrics["joint_score"] = evolved_score
    metrics["roundrobin_baseline_score"] = roundrobin_baseline_score
    metrics["epsilon_pp"] = EPSILON_PP
    metrics["joint_vs_roundrobin_delta_pp"] = joint_vs_roundrobin_delta_pp
    metrics["ab_elapsed_seconds"] = ab_elapsed
```

> **Phase 18 augmentation:** 同款 `if drift_results: metrics["drift_per_dim"] = ...; metrics["drift_thresholds"] = ...`(D-OUT-02)。`drift_passed` 是独立 bool,不与 `constraints_passed` 冲突 — 后者已通过 `all_pass` accumulator 自动反映 drift severity=reject(D-GATE-04)。

### Shared Pattern 5: 多 patch CLI 测试拓扑

**Source:** `tests/prompts/test_evolve_prompt_sections_cli.py:417-447` (`_ab_patched_run`)
**Apply to:** `test_evolve_prompt_sections_cli.py` 新增 3 个 drift 测试(File 10)+ `test_drift_detector.py` 部分 patch 嵌套(File 8)

**Excerpt** — 已在 File 10 anchor 完整列出,略。

---

## No Analog Found

| File | Role | Reason |
|---|---|---|
| `datasets/prompts/drift_thresholds.json` | persistent artifact (config-time data) | 项目里目前没有"derived calibration constants"类的 git-tracked JSON 文件;`metrics.json` 是最近的 JSON-dump 类比,但语义不同(run-time 输出 vs config-time data)。schema 完全由 Phase 18 定义。 |

F1 derivation function 本身(`derive_thresholds` in `drift_calibration.py`)在算法层面也无 analog,但已在 RESEARCH §Code Examples Example 3 给出可直接使用的完整骨架,executor 照搬即可。

---

## Metadata

**Analog search scope:** `evolution/prompts/*.py`(4 个核心文件)+ `evolution/core/*.py`(2 个 config/constraints)+ `tests/prompts/*.py`(7 个测试文件)+ `.gitignore`
**Files scanned:** 14
**Pattern extraction date:** 2026-05-15
**Phase:** 18-personality-drift-detection

---

## PATTERN MAPPING COMPLETE

**Phase:** 18 - Personality Drift Detection
**Files classified:** 11(10 in CONTEXT scope + `conftest.py` 推断为 NEW)
**Analogs found:** 10 / 11

### Coverage
- Files with exact analog: 7
- Files with role-match analog: 3
- Files with no analog: 1(`drift_thresholds.json` schema 由 Phase 18 全新定义)

### Key Patterns Identified
1. **DriftDetector 镜像 PromptRoleChecker 接口形状** — same `check_all(orig, evolved)` 入口、same DSPy ChainOfThought + ConstraintResult-compat 返回,但增 thresholds dict 参数 + 4-dim typed-float Signature + 3-run mean/stdev + severity-ladder dict 输出。
2. **DriftCalibrationBuilder 镜像 PromptDatasetBuilder 模式** — same DSPy Signature + ChainOfThought + JSONL save/load,但用 `judge_model`(非 `eval_model`)、temperature=0.9 高多样性、不分 split。
3. **evolve_prompt_sections.py 完全沿用 Phase 17 的 metrics-field-augmentation + Rich Table + FAILED_<ts>/ 共目录策略** — `drift_*` 字段完全平铺,不破坏现有 `joint_*` / `mode` / `constraints_passed` 字段。
4. **Test mocking 沿用 `tests/prompts/test_evolve_prompt_sections_cli.py` 的 multi-patch 拓扑** — 旁加 `DriftDetector` patch + `pathlib.Path.read_text` patch 模拟 thresholds 文件存在即可。
5. **`.gitignore` exception** 严格沿用现有 `!datasets/.gitkeep` 句法,仅追加两行。

### Phase 18 唯一无 analog 的代码
- `derive_thresholds()` F1 暴力扫描函数 — RESEARCH §Example 3 已提供完整骨架(纯 stdlib,2040 ops < 1ms,RESEARCH §Risk Anchor 3 验证)。
- `drift_thresholds.json` schema — Phase 18 全新定义。

### Ready for Planning
Pattern mapping 完成,planner 可直接引用本文档的 11 个 file 段落中"Anchor + Adaptation Delta"模式撰写 PLAN.md 的 task 与 action 项。每段已显式给出:
- (a) 类比文件路径 + 行号
- (b) 5-15 行类比代码摘录
- (c) DriftDetector / DriftCalibrationBuilder 接口契约
- (d) Insertion point(对于 `evolve_prompt_sections.py` 修改:4 个精确 anchor 行号)
- (e) 与 RESEARCH.md Risk Anchor 的交叉引用(M4 / Pitfall A / Pitfall B / Mitigation 1-5)
