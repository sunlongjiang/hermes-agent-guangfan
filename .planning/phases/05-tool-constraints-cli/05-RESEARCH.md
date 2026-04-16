# Phase 5: Tool Constraints & CLI - Research

**Researched:** 2026-04-16
**Domain:** 约束验证 + CLI 编排 (Python/DSPy/Click)
**Confidence:** HIGH

## Summary

Phase 5 将 Phase 2-4 的所有工具进化组件串联为端到端可运行的管道。主要工作分三块：(1) 新建 `ToolFactualChecker` 做 LLM-based 事实准确性验证，(2) 在 CLI 中正确调用已有的 `ConstraintValidator._check_size()` 实施尺寸约束，(3) 构建 `evolve_tool_descriptions.py` CLI 入口点。

所有组件均有明确的参考实现：`evolve_skill.py` 提供了完整的 CLI + evolve() 编排流程模板；`LLMJudge` 提供了 DSPy Signature + ChainOfThought + JSON 解析的模式；`ConstraintValidator` 已内建 tool_description/param_description 的 size 检查。Phase 5 的创新性工作仅在 `ToolFactualChecker` 这一个新类上。

**Primary recommendation:** 严格照搬 `evolve_skill.py` 的编排结构，新建 `tool_constraints.py`（`ToolFactualChecker`）和 `evolve_tool_descriptions.py`（CLI），复用现有所有基础设施。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** 验证策略为"原始 vs 进化对比"——将原始描述和进化后描述一起传给 LLM，判断进化后的描述是否声称了原始描述中不存在的能力。不对照工具源代码。
- **D-02:** 输出为 Pass/Fail 二值——声称了虚假能力则 fail，否则 pass。返回 `ConstraintResult` 数据类，和现有约束模式一致。
- **D-03:** 检查器放在独立文件 `evolution/tools/tool_constraints.py`，新建 `ToolFactualChecker` 类。和 `tool_loader.py`、`tool_module.py` 并列。
- **D-04:** 单文件组织——`evolution/tools/evolve_tool_descriptions.py` 包含 Click CLI 入口 `main()` 和业务逻辑 `evolve()` 函数，和 `evolve_skill.py` 模式完全一致。
- **D-05:** 端到端管道复制 `evolve_skill.py` 的流程：loader -> module -> dataset(synthetic/load) -> GEPA optimize -> constraint validate -> holdout evaluate -> save。
- **D-06:** CLI 参数为标准四参数：`--iterations`, `--eval-source`(synthetic/load), `--hermes-repo`, `--dry-run`。保持简洁，不引入额外参数。
- **D-07:** 可通过 `python -m evolution.tools.evolve_tool_descriptions` 运行。
- **D-08:** 组合复用——现有 `ConstraintValidator` 的 `_check_size`（已支持 `tool_description`/`param_description` 类型）+ `_check_growth` + `_check_non_empty` 直接复用，加上新建的 `ToolFactualChecker`。CLI 中顺序调用两者。
- **D-09:** 执行时机为优化后门禁——GEPA 优化完成后、holdout 评估之前执行约束验证。和 Phase 1 的 post-optimization constraint gate 一致。
- **D-10:** 跨工具回归检测（Phase 4 的 `CrossToolRegressionChecker`）也在此阶段作为门禁执行。
- **D-11:** 进化结果保存到 `output/tools/` 目录，不直接修改 hermes-agent 文件。
- **D-12:** 输出内容包含三部分：进化后的描述文本、评估指标 JSON（baseline vs evolved scores）、before/after diff 文本。
- **D-13:** dry-run 模式行为为设置验证 + 预览——验证能找到 hermes-agent、能加载工具、能生成/加载数据集，展示将要优化的工具列表，不运行 GEPA。

### Claude's Discretion
- `ToolFactualChecker` 内部的 DSPy Signature 设计（字段名、判断 prompt 措辞）
- LLM 输出的 JSON 解析策略（复用 fitness.py 的 `_parse_scoring_json` 模式）
- diff 输出的具体格式（unified diff 或自定义文本对比）
- 输出目录的子结构（按时间戳、按运行 ID 等组织方式）

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-09 | Factual accuracy preservation -- LLM-based check that evolved descriptions don't claim false capabilities | 新建 `ToolFactualChecker` 类，使用 DSPy ChainOfThought 做原始 vs 进化对比判断，返回 `ConstraintResult` |
| TOOL-10 | Size constraint enforced (<=500 chars per tool description, <=200 chars per parameter description) | 直接复用 `ConstraintValidator._check_size()` 已支持的 `tool_description` 和 `param_description` artifact_type |
| TOOL-11 | CLI entry point `python -m evolution.tools.evolve_tool_descriptions` with --iterations, --eval-source, --hermes-repo, --dry-run options | 照搬 `evolve_skill.py` 的 Click CLI 模式，创建 `evolve_tool_descriptions.py` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dspy | >=3.0.0 | ChainOfThought for ToolFactualChecker, GEPA optimizer | 项目核心框架 [VERIFIED: pyproject.toml] |
| click | >=8.0 | CLI 参数解析 | 项目已用于 evolve_skill.py [VERIFIED: pyproject.toml] |
| rich | >=13.0 | Console, Panel, Table, Progress 终端输出 | 项目标准输出库 [VERIFIED: pyproject.toml] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| difflib | stdlib | 生成 before/after diff 文本 | 输出进化前后对比 [VERIFIED: Python stdlib] |
| json | stdlib | metrics.json 序列化 | 保存评估指标 [VERIFIED: Python stdlib] |
| pathlib | stdlib | 文件路径操作 | 全项目通用 [VERIFIED: Python stdlib] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| difflib.unified_diff | 自定义文本对比 | difflib 是标准库，输出格式熟悉，无需自建 |

**Installation:** 无需安装新包，所有依赖已在 `pyproject.toml` 中声明。

## Architecture Patterns

### Recommended Project Structure
```
evolution/tools/
├── __init__.py               # 已存在 (Phase placeholder)
├── tool_loader.py            # Phase 2 -- 工具描述提取和回写
├── tool_module.py            # Phase 3 -- DSPy Module 封装
├── tool_dataset.py           # Phase 4 -- 数据集构建
├── tool_metric.py            # Phase 4 -- 选择指标和回归检测
├── tool_constraints.py       # Phase 5 NEW -- ToolFactualChecker
└── evolve_tool_descriptions.py  # Phase 5 NEW -- CLI 入口点
```

### Pattern 1: ToolFactualChecker (DSPy Signature + ChainOfThought)
**What:** 用 LLM 对比原始描述和进化后描述，判断是否新增了虚假能力声明
**When to use:** GEPA 优化完成后，作为约束门禁的一部分
**Example:**
```python
# Source: 参照 evolution/core/fitness.py LLMJudge 模式
class ToolFactualChecker:
    """LLM-based factual accuracy check for evolved tool descriptions."""

    class FactualCheckSignature(dspy.Signature):
        """Compare an evolved tool description against its original.

        Determine whether the evolved description claims any capabilities
        that are NOT present in the original description. New phrasing or
        reorganization is acceptable; inventing new capabilities is not.
        """
        original_description: str = dspy.InputField(
            desc="The original tool description before evolution",
        )
        evolved_description: str = dspy.InputField(
            desc="The evolved tool description after optimization",
        )
        tool_name: str = dspy.InputField(
            desc="Name of the tool being checked",
        )
        has_false_claims: bool = dspy.OutputField(
            desc="True if the evolved description claims capabilities NOT in the original",
        )
        explanation: str = dspy.OutputField(
            desc="Explain what false capabilities were found, or confirm none exist",
        )

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.checker = dspy.ChainOfThought(self.FactualCheckSignature)

    def check(
        self,
        tool_name: str,
        original_description: str,
        evolved_description: str,
    ) -> ConstraintResult:
        """Check one tool description for factual accuracy."""
        lm = dspy.LM(self.config.eval_model)
        with dspy.context(lm=lm):
            result = self.checker(
                original_description=original_description,
                evolved_description=evolved_description,
                tool_name=tool_name,
            )

        has_false = _parse_bool(result.has_false_claims)

        if not has_false:
            return ConstraintResult(
                passed=True,
                constraint_name="factual_accuracy",
                message=f"Tool '{tool_name}': No false capability claims",
                details=str(result.explanation),
            )
        else:
            return ConstraintResult(
                passed=False,
                constraint_name="factual_accuracy",
                message=f"Tool '{tool_name}': False capability claims detected",
                details=str(result.explanation),
            )
```

### Pattern 2: CLI evolve() 编排 (照搬 evolve_skill.py)
**What:** 端到端管道函数，串联所有 Phase 2-4 组件
**When to use:** CLI 入口点调用
**Example:**
```python
# Source: 参照 evolution/skills/evolve_skill.py 的编排流程
def evolve(
    iterations: int = 10,
    eval_source: str = "synthetic",
    hermes_repo: Optional[str] = None,
    dry_run: bool = False,
):
    """Main evolution function for tool descriptions."""
    config = EvolutionConfig(iterations=iterations)
    if hermes_repo:
        config.hermes_agent_path = Path(hermes_repo)

    # 1. 发现工具文件 + 提取描述
    tool_files = discover_tool_files(config.hermes_agent_path)
    all_tools = []
    for f in tool_files:
        all_tools.extend(extract_tool_descriptions(f))

    # 2. dry-run: 验证 + 预览，然后返回
    if dry_run:
        # 展示工具列表和数据集统计
        return

    # 3. 构建 ToolModule
    baseline_module = ToolModule(all_tools)

    # 4. 生成/加载数据集
    # (synthetic via ToolDatasetBuilder or load from disk)

    # 5. GEPA 优化
    optimizer = dspy.GEPA(metric=tool_selection_metric, max_steps=iterations)
    optimized_module = optimizer.compile(baseline_module, trainset=trainset, valset=valset)

    # 6. 约束验证 (size + factual + regression)
    #    6a. ConstraintValidator._check_size() for each tool/param
    #    6b. ToolFactualChecker.check() for each tool
    #    6c. CrossToolRegressionChecker.check_regression()

    # 7. holdout 评估

    # 8. 保存结果到 output/tools/
```

### Pattern 3: 约束组合执行
**What:** 顺序执行三类约束门禁，任一失败则拒绝
**When to use:** GEPA 优化完成后
**Example:**
```python
# 6a. Size constraints -- 逐工具逐参数检查
validator = ConstraintValidator(config)
for evolved_tool in evolved_tools:
    results.append(validator._check_size(evolved_tool.description, "tool_description"))
    for param in evolved_tool.params:
        results.append(validator._check_size(param.description, "param_description"))
    results.append(validator._check_growth(evolved_tool.description, original.description, "tool_description"))
    results.append(validator._check_non_empty(evolved_tool.description))

# 6b. Factual accuracy
factual_checker = ToolFactualChecker(config)
for evolved_tool, original_tool in zip(evolved_tools, original_tools):
    results.append(factual_checker.check(
        tool_name=evolved_tool.name,
        original_description=original_tool.description,
        evolved_description=evolved_tool.description,
    ))

# 6c. Cross-tool regression
regression_checker = CrossToolRegressionChecker()
# ... run baseline and evolved on holdout, compute rates, check regression
```

### Anti-Patterns to Avoid
- **直接调用 `validate_all()`:** `ConstraintValidator.validate_all()` 内部对 `artifact_type == "skill"` 有特殊处理（`_check_skill_structure`），不适用于工具描述。应直接调用 `_check_size`/`_check_growth`/`_check_non_empty` 单独方法。 [VERIFIED: constraints.py line 50-51]
- **在 ToolFactualChecker 中检查参数描述:** D-01 明确只检查顶层描述的事实准确性，参数描述只做 size 约束。
- **修改 hermes-agent 文件:** D-11 明确只输出到 `output/tools/`，不调用 `write_back_description()`。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 文本 diff 生成 | 自定义逐行对比 | `difflib.unified_diff()` | 标准库，格式通用 |
| Size 约束检查 | 重新实现长度检查 | `ConstraintValidator._check_size()` | 已支持 tool_description/param_description [VERIFIED: constraints.py lines 95-117] |
| Growth 约束检查 | 重新实现增长率检查 | `ConstraintValidator._check_growth()` | 通用文本增长率计算 [VERIFIED: constraints.py lines 119-134] |
| 回归检测 | 自建 per-tool 对比 | `CrossToolRegressionChecker` | Phase 4 已实现 [VERIFIED: tool_metric.py lines 64-179] |
| JSON 解析 | 自建 LLM 输出解析 | 两阶段策略: `json.loads` + regex fallback | 项目已建立的模式 [VERIFIED: tool_dataset.py `_parse_json_array`] |
| 布尔值解析 | 假设 LLM 返回标准 bool | `_parse_bool()` 辅助函数 | LLM 可能返回 "True"/"true"/"yes" 等各种格式 |

**Key insight:** Phase 5 的 90% 工作是 "胶水代码"——串联已有组件。唯一的新逻辑是 `ToolFactualChecker`，其模式也完全参照 `LLMJudge`。

## Common Pitfalls

### Pitfall 1: validate_all() 会添加 skill_structure 检查
**What goes wrong:** 如果对工具描述调用 `validate_all(text, "tool_description")`，虽然不会触发 `_check_skill_structure`（因为 `artifact_type != "skill"`），但 validate_all 的接口设计是以整个制品文本为单位，不适合逐工具逐参数的检查场景。
**Why it happens:** `validate_all` 接收单个 artifact_text，但工具进化需要对多个工具的多个参数分别检查。
**How to avoid:** 直接调用 `_check_size`、`_check_growth`、`_check_non_empty` 单独方法。在 CLI 中用循环对每个工具和每个参数逐一检查。
**Warning signs:** 代码中出现 `validator.validate_all(tool.description, "tool_description")`——这能工作但无法覆盖参数描述。

### Pitfall 2: DSPy bool 输出解析
**What goes wrong:** `FactualCheckSignature` 的 `has_false_claims: bool` 输出字段，DSPy 可能返回字符串 "True"/"False" 而非 Python bool。
**Why it happens:** LLM 输出经 DSPy 解析后格式不确定，特别是使用 ChainOfThought 时。
**How to avoid:** 编写 `_parse_bool()` 辅助函数，处理 `bool`, `str("True"/"true"/"yes"/"1")` 等各种格式。参照 `fitness.py` 的 `_parse_score()` 防御性解析模式。
**Warning signs:** 测试中 factual check 总是返回 pass 或总是返回 fail。

### Pitfall 3: 跨工具回归检测需要两轮推理
**What goes wrong:** 回归检测需要 baseline 和 evolved 两组 per-tool 正确率，但 CLI 只运行了 evolved 推理。
**Why it happens:** 忘记在 holdout 评估前先用原始 ToolModule 跑一遍 baseline。
**How to avoid:** 在 GEPA 优化前保存 baseline_module 的引用，在 holdout 阶段先跑 baseline 再跑 evolved，收集 (correct_tool, selected_tool) 对，分别调用 `compute_per_tool_rates()`。
**Warning signs:** `check_regression()` 的 baseline_rates 为空或全为 0。

### Pitfall 4: dry-run 中的数据集处理
**What goes wrong:** dry-run 应该验证数据集能否加载/生成，但如果 eval_source="synthetic" 则会触发昂贵的 LLM 调用。
**Why it happens:** `evolve_skill.py` 的 dry-run 在步骤 1 后就返回了（找到技能即可），但 D-13 要求 dry-run "验证能生成/加载数据集"。
**How to avoid:** dry-run 对 "load" 模式验证文件路径存在；对 "synthetic" 模式只展示将会生成的信息（工具数量、预计示例数），不实际调用 LLM。
**Warning signs:** dry-run 耗时超过几秒或产生 API 费用。

### Pitfall 5: ToolModule.get_evolved_descriptions() 返回的 params 是原始的
**What goes wrong:** `get_evolved_descriptions()` 返回的 `ToolDescription` 中 params 是从 `_frozen_tools` 复制来的原始参数，参数描述未被进化。
**Why it happens:** Phase 3 的 `ToolModule` 设计只优化顶层描述，参数描述不在 GEPA 优化范围内。
**How to avoid:** 这是正确行为，不是 bug。约束检查参数描述时应检查原始值（确认它们一开始就符合 size limit），或者只检查顶层描述的变化。
**Warning signs:** 对参数描述做 growth 检查时 delta 始终为 0。

## Code Examples

### ToolFactualChecker 完整实现参考

```python
# Source: 基于 evolution/core/fitness.py LLMJudge 模式
import dspy
from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintResult


def _parse_bool(value) -> bool:
    """Parse a boolean value from LLM output."""
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in ("true", "yes", "1")


class ToolFactualChecker:
    """LLM-based factual accuracy check for evolved tool descriptions."""

    class FactualCheckSignature(dspy.Signature):
        """Compare an evolved tool description against its original to detect false capability claims.

        The evolved description may rephrase, reorganize, or clarify the original.
        That is acceptable. What is NOT acceptable is claiming capabilities that
        the original description does not mention or imply.
        """
        tool_name: str = dspy.InputField(desc="Name of the tool being checked")
        original_description: str = dspy.InputField(desc="The original tool description before evolution")
        evolved_description: str = dspy.InputField(desc="The evolved tool description after optimization")
        has_false_claims: bool = dspy.OutputField(desc="True if evolved claims capabilities NOT in original, False otherwise")
        explanation: str = dspy.OutputField(desc="What false capabilities were found, or confirm none exist")

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.checker = dspy.ChainOfThought(self.FactualCheckSignature)

    def check(self, tool_name: str, original_description: str, evolved_description: str) -> ConstraintResult:
        lm = dspy.LM(self.config.eval_model)
        with dspy.context(lm=lm):
            result = self.checker(
                tool_name=tool_name,
                original_description=original_description,
                evolved_description=evolved_description,
            )
        has_false = _parse_bool(result.has_false_claims)
        if not has_false:
            return ConstraintResult(
                passed=True,
                constraint_name="factual_accuracy",
                message=f"Tool '{tool_name}': No false capability claims",
                details=str(result.explanation),
            )
        return ConstraintResult(
            passed=False,
            constraint_name="factual_accuracy",
            message=f"Tool '{tool_name}': False capability claims detected",
            details=str(result.explanation),
        )

    def check_all(self, original_tools: list, evolved_tools: list) -> list[ConstraintResult]:
        """Check all tools, returns list of ConstraintResult."""
        results = []
        original_map = {t.name: t for t in original_tools}
        for evolved in evolved_tools:
            original = original_map.get(evolved.name)
            if original:
                results.append(self.check(evolved.name, original.description, evolved.description))
        return results
```

### CLI evolve() 函数编排顺序参考

```python
# Source: 参照 evolution/skills/evolve_skill.py 结构
import difflib

def _generate_diff(original_tools, evolved_tools) -> str:
    """Generate unified diff for all tools."""
    lines = []
    original_map = {t.name: t for t in original_tools}
    for evolved in evolved_tools:
        original = original_map.get(evolved.name)
        if not original:
            continue
        diff = difflib.unified_diff(
            original.description.splitlines(keepends=True),
            evolved.description.splitlines(keepends=True),
            fromfile=f"{evolved.name} (original)",
            tofile=f"{evolved.name} (evolved)",
        )
        lines.extend(diff)
    return "".join(lines)
```

### Click CLI 参数参考

```python
# Source: 参照 evolution/skills/evolve_skill.py lines 296-319
@click.command()
@click.option("--iterations", default=10, help="Number of GEPA iterations")
@click.option("--eval-source", default="synthetic", type=click.Choice(["synthetic", "load"]),
              help="Source for evaluation dataset")
@click.option("--hermes-repo", default=None, help="Path to hermes-agent repo")
@click.option("--dry-run", is_flag=True, help="Validate setup without running optimization")
def main(iterations, eval_source, hermes_repo, dry_run):
    """Evolve hermes-agent tool descriptions using DSPy + GEPA optimization."""
    evolve(
        iterations=iterations,
        eval_source=eval_source,
        hermes_repo=hermes_repo,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    main()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 手动审查工具描述 | GEPA 自动优化 + 约束门禁 | 本项目 | 系统性改进 + 安全保障 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DSPy `bool` OutputField 可能返回字符串而非 Python bool | Pitfalls | 如果 DSPy 已原生处理 bool 解析，`_parse_bool` 多余但无害 |
| A2 | `difflib.unified_diff` 对短文本（<500 chars）的 diff 输出足够清晰 | Code Examples | 可能需要改为 side-by-side 或自定义格式，但 unified diff 是通用选择 |

**说明：** 本次研究的所有关键断言均已通过代码验证（constraints.py、evolve_skill.py、tool_module.py、tool_metric.py、config.py），无需额外的用户确认。

## Open Questions

1. **eval-source "load" 的数据集路径**
   - What we know: D-06 规定 `--eval-source` 接受 `synthetic` 和 `load` 两个选项
   - What's unclear: "load" 模式下数据集路径是固定的 `datasets/tools/` 还是需要额外 `--dataset-path` 参数
   - Recommendation: 参照 `evolve_skill.py` 的做法，"load" 模式默认从 `datasets/tools/` 加载，如果目录不存在则报错退出。不额外添加 `--dataset-path`，因为 D-06 明确 "不引入额外参数"。

2. **参数描述的 factual check**
   - What we know: D-01 说 "判断进化后的描述是否声称了原始描述中不存在的能力"，指的是顶层描述
   - What's unclear: 参数描述是否也需要 factual check
   - Recommendation: 不需要——ToolModule 只优化顶层描述，参数描述保持冻结（来自 `_frozen_tools`）。只对参数描述做 size check。

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=7.0 |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/tools/ -x -q` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TOOL-09 | ToolFactualChecker 检测虚假能力声明 | unit | `python -m pytest tests/tools/test_tool_constraints.py -x` | Wave 0 |
| TOOL-09 | ToolFactualChecker 通过无虚假声明的描述 | unit | `python -m pytest tests/tools/test_tool_constraints.py -x` | Wave 0 |
| TOOL-10 | Size constraint rejects >500 char tool desc | unit | `python -m pytest tests/tools/test_tool_constraints.py::test_size_constraint_tool_desc -x` | Wave 0 |
| TOOL-10 | Size constraint rejects >200 char param desc | unit | `python -m pytest tests/tools/test_tool_constraints.py::test_size_constraint_param_desc -x` | Wave 0 |
| TOOL-11 | CLI runs with --dry-run | integration | `python -m pytest tests/tools/test_evolve_tool_cli.py::test_dry_run -x` | Wave 0 |
| TOOL-11 | CLI --help shows correct options | unit | `python -m pytest tests/tools/test_evolve_tool_cli.py::test_cli_help -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/tools/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/tools/test_tool_constraints.py` -- covers TOOL-09, TOOL-10
- [ ] `tests/tools/test_evolve_tool_cli.py` -- covers TOOL-11

## Sources

### Primary (HIGH confidence)
- `evolution/skills/evolve_skill.py` -- 完整 CLI + evolve() 编排参考 [VERIFIED: 直接阅读源码]
- `evolution/core/constraints.py` -- ConstraintValidator 已支持 tool_description/param_description [VERIFIED: 直接阅读源码 lines 95-117]
- `evolution/core/fitness.py` -- LLMJudge DSPy Signature 模式参考 [VERIFIED: 直接阅读源码]
- `evolution/tools/tool_module.py` -- ToolModule.get_evolved_descriptions() 接口 [VERIFIED: 直接阅读源码 lines 88-112]
- `evolution/tools/tool_metric.py` -- CrossToolRegressionChecker 接口 [VERIFIED: 直接阅读源码 lines 64-179]
- `evolution/tools/tool_dataset.py` -- ToolDatasetBuilder 和 ToolSelectionDataset 接口 [VERIFIED: 直接阅读源码]
- `evolution/core/config.py` -- EvolutionConfig.max_tool_desc_size=500, max_param_desc_size=200 [VERIFIED: 直接阅读源码 lines 28-29]
- `pyproject.toml` -- 依赖声明和 pytest 配置 [VERIFIED: 直接阅读]

### Secondary (MEDIUM confidence)
None needed -- all claims verified against codebase.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- 全部复用现有依赖，无新包引入
- Architecture: HIGH -- 完全照搬 evolve_skill.py 的模式，所有组件接口已验证
- Pitfalls: HIGH -- 基于直接阅读源码识别的具体问题

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (stable project, 30 days)
