# Phase 4: Tool Dataset & Evaluation - Research

**Researched:** 2026-04-16
**Domain:** 合成数据集生成、二值评估指标、跨工具回归检测
**Confidence:** HIGH

## Summary

Phase 4 需要在 `evolution/tools/` 包中新建两个模块：`tool_dataset.py`（数据类 + 合成生成器）和 `tool_metric.py`（二值指标 + 跨工具回归检测）。所有模式均可直接从 Phase 1 的 `dataset_builder.py` 和 `fitness.py` 复制并适配，无需引入新依赖。

核心技术挑战有三：(1) DSPy Signature 设计——需要生成带有 confuser 信息的工具选择三元组；(2) 确保每个工具至少 3 条覆盖的生成策略——需要两步生成（先分析工具相似度找 confuser 对，再按工具/按对生成任务）；(3) 跨工具回归检测——需要在 holdout 集上计算 per-tool 选中率并与 baseline 对比。

**Primary recommendation:** 严格复用 Phase 1 的 dataclass + builder + metric 模式，新建两个文件即可覆盖全部 4 个需求。不要试图泛化现有 `EvalDataset`。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** 新建 `ToolSelectionExample` 专用数据类，包含 task_description, correct_tool, correct_params, difficulty, confuser_tools 等字段。不扩展现有 `EvalExample`，两者并存
- **D-02:** 配套新建 `ToolSelectionDataset` 数据类，提供 train/val/holdout 分割和 JSONL 序列化，和 `EvalDataset` 模式一致
- **D-03:** 新建 `ToolDatasetBuilder` 专用类，参考 `SyntheticDatasetBuilder` 的模式（DSPy Signature + ChainOfThought + JSONL 分割保存），但用专用 Signature 生成 (task, correct_tool, correct_params) 三元组
- **D-04:** 数据集来源仅用 LLM 合成生成。不需要 SessionDB 或 golden set
- **D-05:** 保存到 `datasets/tools/selection/`，标准 JSONL 分割（train.jsonl / val.jsonl / holdout.jsonl），50/25/25 比例
- **D-06:** confuser 采用工具相似度分析驱动——先用 LLM 分析所有工具描述找出功能重叠的工具对/组，再针对每对生成 5-10 个 confuser 任务，明确标注正确工具和原因
- **D-07:** hard 难度的任务主要由 confuser 组成
- **D-08:** 难度分布 easy 30% / medium 40% / hard 30%
- **D-09:** 每个工具至少 3 条任务（1 easy + 1 medium + 1 hard/confuser），确保跨工具回归检测有足够样本。50 工具 x 3 = 150 条起步，加上额外 confuser 达到 200-400 总量
- **D-10:** 精确匹配判断工具选择正确性：`selected_tool.strip().lower() == correct_tool.strip().lower()` -> 1 或 0
- **D-11:** correct_params 不纳入 Phase 4 的二值评分，只关注工具选择正确率。数据集中仍记录 correct_params 供未来使用
- **D-12:** 独立 `tool_selection_metric(example, prediction)` 函数，返回 0 或 1，直接作为 GEPA `compile()` 的 metric 参数。和 Phase 1 的 `skill_fitness_metric` 并列
- **D-13:** baseline 通过优化前用原始描述在整个评估数据集上跑一遍，记录 per-tool 正确选中率
- **D-14:** 回归阈值为绝对值 2 个百分点（如 baseline 80% -> 跌至 78% 以下即触发拒绝）
- **D-15:** 跨工具回归检测作为最终门禁（post-optimization gate），在 holdout 集上执行一次。和 Phase 1 的 constraint validation 模式一致

### Claude's Discretion
- `ToolSelectionExample` 和 `ToolSelectionDataset` 的具体字段命名和辅助方法
- `ToolDatasetBuilder` 内部的 DSPy Signature 设计（字段名、desc 文本）
- 工具相似度分析的具体实现（LLM prompt 设计、相似度阈值）
- 跨工具回归检测函数的具体接口设计和返回格式

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-05 | Binary tool selection metric -- given (task, available_tools), score whether agent picks the correct tool (0 or 1) | `tool_selection_metric()` 函数，精确匹配 D-10，函数签名参照 `skill_fitness_metric` 模式 |
| TOOL-06 | Synthetic dataset builder generates 200-400 (task_description, correct_tool, correct_params) triples with difficulty levels | `ToolDatasetBuilder` 两步生成：工具相似度分析 + 按工具/按对生成任务，保存 JSONL |
| TOOL-07 | Dataset includes "confuser" tasks where 2+ tools overlap but one is clearly better | confuser 由工具相似度分析驱动（D-06），hard 难度主要由 confuser 组成（D-07） |
| TOOL-08 | Cross-tool joint evaluation -- fitness function penalizes any individual tool's selection rate regression >2% | `CrossToolRegressionChecker` 在 holdout 集上对比 per-tool baseline vs evolved 选中率，绝对值 >2pp 则拒绝 |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python >=3.10，使用 `.venv` (Python 3.13.3)
- 严格遵循 Phase 1 的代码模式和目录结构
- 不引入新的外部依赖，复用现有 DSPy/Click/Rich 栈
- hermes-agent 只读访问，通过 `HERMES_AGENT_REPO` 环境变量定位
- 工具描述 <=500 chars，参数描述 <=200 chars
- Dataclass + `to_dict()` / `from_dict()` 序列化模式
- DSPy Signature 内部类 + ChainOfThought 生成
- Module-level `Console()` + Rich 输出
- JSONL 格式的 train/val/holdout 分割保存
- Google-style docstrings with `Args:` and `Returns:`
- `snake_case` 函数/变量，`PascalCase` 类名
- `from X import Y` 风格导入
- 不使用 bare `print()`，用 `console.print()` + Rich markup

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dspy | 3.1.3 | LLM Signature + ChainOfThought 生成 | 项目核心框架，已安装 [VERIFIED: .venv pip] |
| dataclasses | stdlib | ToolSelectionExample / ToolSelectionDataset 数据类 | Phase 1 既定模式 [VERIFIED: codebase] |
| json | stdlib | JSONL 序列化/反序列化 | Phase 1 既定模式 [VERIFIED: codebase] |
| random | stdlib | 数据集 shuffle 和分割 | Phase 1 既定模式 [VERIFIED: codebase] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rich | >=13.0 | Console 输出、进度条 | 所有用户面向的输出 [VERIFIED: pyproject.toml] |
| pathlib | stdlib | 文件路径操作 | 数据集保存/加载 |
| collections.defaultdict | stdlib | per-tool 统计聚合 | 跨工具回归检测 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 新建 ToolSelectionExample | 扩展 EvalExample | D-01 已锁定：不扩展，两者并存 |
| LLM 合成 | SessionDB 挖掘 | D-04 已锁定：仅 LLM 合成 |
| 精确字符串匹配 | 模糊匹配/别名映射 | D-10 已锁定：`strip().lower()` 精确匹配 |

**Installation:** 无需安装新包。所有依赖已在 `pyproject.toml` 中声明。

## Architecture Patterns

### Recommended Project Structure
```
evolution/tools/
    __init__.py          # 已存在
    tool_loader.py       # 已存在 (Phase 2)
    tool_module.py       # 已存在 (Phase 3)
    tool_dataset.py      # 新建: ToolSelectionExample, ToolSelectionDataset, ToolDatasetBuilder
    tool_metric.py       # 新建: tool_selection_metric(), CrossToolRegressionChecker

datasets/tools/selection/
    train.jsonl          # 50% 训练集
    val.jsonl            # 25% 验证集
    holdout.jsonl        # 25% 留出集（回归检测用）

tests/tools/
    test_tool_dataset.py # 新建: 数据类 + builder 测试
    test_tool_metric.py  # 新建: 指标 + 回归检测测试
```

### Pattern 1: ToolSelectionExample 数据类
**What:** 专用数据类，包含工具选择评估所需的全部字段
**When to use:** 构建和序列化工具选择数据集
**Example:**
```python
# Source: 参照 evolution/core/dataset_builder.py EvalExample 模式
@dataclass
class ToolSelectionExample:
    """A single tool selection evaluation example."""
    task_description: str       # 用户任务描述
    correct_tool: str           # 正确工具名称
    correct_params: dict = field(default_factory=dict)  # 正确参数（Phase 4 不评分，未来使用）
    difficulty: str = "medium"  # easy, medium, hard
    confuser_tools: list[str] = field(default_factory=list)  # 混淆工具列表
    reason: str = ""            # 为什么 correct_tool 是最佳选择
    source: str = "synthetic"

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "ToolSelectionExample": ...
```
[VERIFIED: 模式来自 `evolution/core/dataset_builder.py` lines 21-41]

### Pattern 2: 两步数据集生成
**What:** Step 1 分析工具相似度找 confuser 对，Step 2 按工具/按对生成任务
**When to use:** `ToolDatasetBuilder.generate()` 的核心流程
**Example:**
```python
# Source: 参照 SyntheticDatasetBuilder 的 DSPy Signature + ChainOfThought 模式
class ToolDatasetBuilder:
    class AnalyzeToolSimilarity(dspy.Signature):
        """分析所有工具描述，找出功能重叠的工具对/组。"""
        tool_summaries: str = dspy.InputField(desc="所有工具的 name + description 列表")
        confuser_pairs: str = dspy.OutputField(desc="JSON array of {tools: [tool_a, tool_b], overlap: str}")

    class GenerateToolTasks(dspy.Signature):
        """为指定工具生成工具选择评估任务。"""
        tool_name: str = dspy.InputField(desc="目标工具名称")
        tool_description: str = dspy.InputField(desc="工具描述")
        all_tools: str = dspy.InputField(desc="所有可用工具的简要列表")
        difficulty: str = dspy.InputField(desc="easy, medium, or hard")
        num_tasks: int = dspy.InputField(desc="要生成的任务数量")
        tasks: str = dspy.OutputField(desc="JSON array of {task_description, correct_params, confuser_tools}")

    class GenerateConfuserTasks(dspy.Signature):
        """为功能重叠的工具对生成 confuser 任务。"""
        tool_a_name: str = dspy.InputField()
        tool_a_description: str = dspy.InputField()
        tool_b_name: str = dspy.InputField()
        tool_b_description: str = dspy.InputField()
        overlap_description: str = dspy.InputField(desc="两个工具功能重叠的描述")
        num_tasks: int = dspy.InputField()
        tasks: str = dspy.OutputField(desc="JSON array of {task_description, correct_tool, correct_params, reason}")
```
[VERIFIED: Signature 模式来自 `dataset_builder.py` lines 96-109, `tool_module.py` lines 16-31]

### Pattern 3: 二值指标函数
**What:** DSPy metric 兼容函数，返回 0 或 1
**When to use:** 作为 GEPA `compile(metric=...)` 参数
**Example:**
```python
# Source: 参照 evolution/core/fitness.py skill_fitness_metric 模式
def tool_selection_metric(example: dspy.Example, prediction: dspy.Prediction, trace=None) -> float:
    """DSPy-compatible metric for tool selection. Returns 0.0 or 1.0."""
    selected = getattr(prediction, "selected_tool", "") or ""
    correct = getattr(example, "correct_tool", "") or ""
    if selected.strip().lower() == correct.strip().lower():
        return 1.0
    return 0.0
```
[VERIFIED: 函数签名模式来自 `fitness.py` lines 107-136]

### Pattern 4: 跨工具回归检测
**What:** post-optimization gate，对比 per-tool baseline vs evolved 选中率
**When to use:** 优化完成后在 holdout 集上执行一次
**Example:**
```python
@dataclass
class ToolRegressionResult:
    """跨工具回归检测结果。"""
    passed: bool
    tool_results: dict[str, dict]  # {tool_name: {baseline_rate, evolved_rate, delta}}
    regression_threshold: float
    regressed_tools: list[str]    # 回归超过阈值的工具列表

class CrossToolRegressionChecker:
    def __init__(self, regression_threshold: float = 0.02):
        self.regression_threshold = regression_threshold

    def compute_baseline(
        self, module: "ToolModule", dataset: "ToolSelectionDataset",
    ) -> dict[str, float]:
        """在 holdout 集上用原始描述跑一遍，记录 per-tool 正确率。"""
        ...

    def check_regression(
        self, baseline_rates: dict[str, float],
        evolved_rates: dict[str, float],
    ) -> ToolRegressionResult:
        """对比 baseline vs evolved，任何工具回归 >threshold 则 passed=False。"""
        ...
```
[ASSUMED: 接口设计基于 D-13/D-14/D-15 决策推导]

### Anti-Patterns to Avoid
- **扩展 EvalExample:** D-01 明确禁止。`ToolSelectionExample` 是独立数据类
- **一次性生成全部任务:** 会导致工具覆盖不均。必须两步生成——先确保每工具至少 3 条，再补充 confuser
- **模糊匹配工具名:** D-10 明确使用精确匹配（`strip().lower()`），不要引入别名或编辑距离
- **在 val 集上做回归检测:** D-15 明确要求在 holdout 集上执行

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON 解析 LLM 输出 | 自定义 parser | `json.loads()` + regex fallback | Phase 1 已有模式 (`dataset_builder.py` line 136-145) |
| 数据集分割 | 自定义分割逻辑 | 复制 `SyntheticDatasetBuilder.generate()` 的 shuffle + split | 保持 50/25/25 一致性 |
| DSPy Example 转换 | 手动构造 | `to_dspy_examples()` 方法 | Phase 1 模式一致 |

**Key insight:** Phase 4 的所有组件在 Phase 1 中都有直接对应模式。不要发明新模式，复制并适配。

## Common Pitfalls

### Pitfall 1: LLM 生成的工具名与实际工具名不匹配
**What goes wrong:** LLM 生成 `correct_tool` 时可能用略有不同的名称（如 `"Memory"` vs `"memory"`，或 `"list_files"` vs `"list-files"`）
**Why it happens:** DSPy Signature 输出是自由文本，LLM 不保证精确使用传入的工具名
**How to avoid:** 生成后做标准化校验——将 `correct_tool` 与实际工具名列表匹配（`strip().lower()`），无法匹配的条目应丢弃或修正
**Warning signs:** 数据集中的 `correct_tool` 值与 `tool_loader` 提取的工具名不一致

### Pitfall 2: 工具覆盖不足
**What goes wrong:** 某些冷门工具可能 0 条评估数据，导致回归检测无法工作
**Why it happens:** LLM 倾向为常见工具生成更多任务，忽略小众工具
**How to avoid:** 第一步按工具逐个生成保底的 3 条（D-09），然后再补充 confuser。生成后验证覆盖率
**Warning signs:** per-tool 任务计数中有工具 <3 条

### Pitfall 3: Confuser 任务中两个工具都合理
**What goes wrong:** LLM 生成的 confuser 任务可能对两个工具同样适用，没有明确的"正确"答案
**Why it happens:** 工具功能确实重叠，任务描述不够精确
**How to avoid:** confuser Signature 要求 LLM 提供 `reason` 字段解释为什么 correct_tool 更好。生成后可人工抽检
**Warning signs:** confuser 任务的 metric 分数始终在 50% 左右（随机猜测水平）

### Pitfall 4: DSPy ChainOfThought 输出非法 JSON
**What goes wrong:** LLM 输出中 JSON 格式不完整或包含额外文本
**Why it happens:** ChainOfThought 会在 JSON 前后添加推理文本
**How to avoid:** 采用 Phase 1 的二级 JSON 解析策略：先 `json.loads()`，失败则 regex 提取 `[...]`
**Warning signs:** 生成过程中频繁出现 `ValueError` / `JSONDecodeError`

### Pitfall 5: 跨工具回归阈值误用相对值
**What goes wrong:** 用相对百分比（如 "下降了 2.5%"）而非绝对百分点
**Why it happens:** 混淆 "percentage" 和 "percentage point"
**How to avoid:** D-14 已明确：绝对值 2 个百分点。`baseline_rate - evolved_rate > 0.02` 即触发拒绝
**Warning signs:** 高 baseline 工具（95%）几乎不会触发，低 baseline 工具（50%）极容易触发

## Code Examples

### ToolSelectionDataset 的 to_dspy_examples 转换
```python
# Source: 参照 EvalDataset.to_dspy_examples (dataset_builder.py lines 77-86)
def to_dspy_examples(self, split: str = "train") -> list[dspy.Example]:
    """Convert a split to DSPy Example objects for optimization."""
    data = getattr(self, split)
    return [
        dspy.Example(
            task_description=ex.task_description,
            correct_tool=ex.correct_tool,
        ).with_inputs("task_description")
        for ex in data
    ]
```
[VERIFIED: 模式来自 `dataset_builder.py` lines 77-86]

### 数据集保存 JSONL
```python
# Source: 参照 EvalDataset.save (dataset_builder.py lines 54-60)
def save(self, path: Path):
    """Save dataset splits to JSONL files."""
    path.mkdir(parents=True, exist_ok=True)
    for split_name, split_data in [("train", self.train), ("val", self.val), ("holdout", self.holdout)]:
        with open(path / f"{split_name}.jsonl", "w") as f:
            for ex in split_data:
                f.write(json.dumps(ex.to_dict()) + "\n")
```
[VERIFIED: 直接引用 `dataset_builder.py` lines 54-60]

### Per-tool 正确率统计
```python
# Source: [ASSUMED] 基于 D-13 的 baseline 计算需求
from collections import defaultdict

def compute_per_tool_rates(
    module: "ToolModule",
    examples: list["ToolSelectionExample"],
) -> dict[str, float]:
    """Compute per-tool selection accuracy."""
    correct_by_tool = defaultdict(int)
    total_by_tool = defaultdict(int)

    for ex in examples:
        total_by_tool[ex.correct_tool] += 1
        prediction = module.forward(task_description=ex.task_description)
        selected = prediction.selected_tool.strip().lower()
        if selected == ex.correct_tool.strip().lower():
            correct_by_tool[ex.correct_tool] += 1

    return {
        tool: correct_by_tool[tool] / total_by_tool[tool]
        for tool in total_by_tool
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 手工编写评估集 | LLM 合成生成 + confuser 分析 | DSPy 3.x 时代 | 可快速生成大规模多样化数据集 |
| 单一聚合指标 | Per-tool 细粒度 + 回归门禁 | 本项目设计 | 防止"牺牲少数工具换取整体提升"的退化 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `CrossToolRegressionChecker` 接口设计可行 | Architecture Pattern 4 | 低 -- 逻辑简单，只是统计对比 |
| A2 | hermes-agent 约有 50 个工具 | User Constraints D-09 引用 | 中 -- 工具数量影响数据集大小计算。实际数可通过 `extract_tool_descriptions()` 获取 |
| A3 | DSPy 3.1.3 的 `dspy.Example.with_inputs()` 支持 `correct_tool` 作为标签字段 | Code Examples | 低 -- Phase 1 已验证此模式 |

## Open Questions

1. **实际工具数量**
   - What we know: D-09 假设约 50 个工具
   - What's unclear: 实际 hermes-agent 有多少个注册工具
   - Recommendation: 第一个 task 应调用 `discover_tool_files()` + `extract_tool_descriptions()` 确认实际数量，据此调整生成数量

2. **LLM 生成 confuser 的质量**
   - What we know: D-06 采用工具相似度分析驱动
   - What's unclear: LLM 能否可靠地识别功能重叠并生成有区分度的 confuser 任务
   - Recommendation: 建议 builder 返回生成统计（总数、丢弃数、每工具覆盖数），便于调试

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/tools/ -x -q` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TOOL-05 | tool_selection_metric returns 0 or 1 | unit | `python -m pytest tests/tools/test_tool_metric.py::TestToolSelectionMetric -x` | Wave 0 |
| TOOL-06 | ToolDatasetBuilder generates 200-400 examples with splits | unit | `python -m pytest tests/tools/test_tool_dataset.py::TestToolDatasetBuilder -x` | Wave 0 |
| TOOL-07 | Dataset includes confuser tasks from similarity analysis | unit | `python -m pytest tests/tools/test_tool_dataset.py::TestConfuserGeneration -x` | Wave 0 |
| TOOL-08 | CrossToolRegressionChecker detects >2% regression | unit | `python -m pytest tests/tools/test_tool_metric.py::TestCrossToolRegression -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/tools/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/tools/test_tool_dataset.py` -- covers TOOL-06, TOOL-07
- [ ] `tests/tools/test_tool_metric.py` -- covers TOOL-05, TOOL-08

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A |
| V5 Input Validation | yes | JSON 解析使用 `json.loads()` + 二级 fallback，不使用 `eval()` |
| V6 Cryptography | no | N/A |

### Known Threat Patterns for LLM 合成数据管道

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| LLM 输出注入恶意 JSON | Tampering | `json.loads()` 严格解析，不使用 `eval()` |
| 生成的 correct_params 包含敏感信息 | Information Disclosure | correct_params 仅用于未来参考，Phase 4 不执行 |

## Sources

### Primary (HIGH confidence)
- `evolution/core/dataset_builder.py` -- EvalExample/EvalDataset/SyntheticDatasetBuilder 模式
- `evolution/core/fitness.py` -- skill_fitness_metric 函数签名和 DSPy metric 模式
- `evolution/tools/tool_loader.py` -- ToolDescription/ToolParam 数据类和 extract_tool_descriptions()
- `evolution/tools/tool_module.py` -- ToolModule.forward() 返回 dspy.Prediction(selected_tool=...)
- `evolution/core/constraints.py` -- ConstraintResult 和 validate_all() 门禁模式
- `evolution/core/config.py` -- EvolutionConfig 参数，包含 train_ratio=0.5, val_ratio=0.25

### Secondary (MEDIUM confidence)
- DSPy 3.1.3 installed [VERIFIED: .venv pip] -- Signature/ChainOfThought/Example API
- pytest 9.0.3 with testpaths=["tests"] [VERIFIED: pyproject.toml]

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- 全部复用现有依赖，无新引入
- Architecture: HIGH -- 严格遵循 Phase 1 模式，所有参考代码已验证
- Pitfalls: HIGH -- 基于 Phase 1 LLM 合成生成的实践经验

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (稳定领域，30 天有效)
