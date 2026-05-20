# Phase 21: Darwinian Code Evolution — Pattern Map

**Mapped:** 2026-05-20
**Files analyzed:** 20 (新建/修改)
**Analogs found:** 18 / 20

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `evolution/code/__init__.py` | package init (lazy guard) | N/A | `evolution/benchmarks/__init__.py` | exact |
| `evolution/code/code_target_loader.py` | loader | request-response (filesystem → dataclass) | `evolution/tools/tool_loader.py` | role-match |
| `evolution/code/code_fitness.py` | fitness scorer | batch (candidate path → CodeFitness dataclass) | `evolution/benchmarks/benchmark_gate.py` `TBLiteBenchmarkGate.check` | role-match |
| `evolution/code/code_evolver_adapter.py` | adapter / facade | request-response (EvolutionConfig → openevolve API) | `evolution/benchmarks/benchmark_gate.py` (TBLite facade pattern) | role-match |
| `evolution/code/sandbox_runner.py` | utility / subprocess wrapper | request-response (candidate path → test result) | `evolution/benchmarks/tblite_runner.py` `TBLiteRunner` | exact |
| `evolution/code/evolve_code.py` | CLI orchestrator | request-response (CLI → pipeline) | `evolution/tools/evolve_tool_descriptions.py` | exact |
| `evolution/code/LICENSING.md` | doc | N/A | `evolution/benchmarks/__init__.py` (docstring boundary说明模式) | partial |
| `LICENSE` | config/doc | N/A | 无 (仓根不存在) | none |
| `.pre-commit-config.yaml` | config | N/A | 无 | none |
| `pyproject.toml` (修改) | config | N/A | `pyproject.toml` `[project.optional-dependencies]` | exact |
| `ruff.toml` / `[tool.ruff]` 段 | config | N/A | 无 (仓内无 ruff config) | none |
| `tests/code/__init__.py` | test package init | N/A | `tests/__init__.py` | exact |
| `tests/code/test_import_boundary.py` | test | file-I/O (pathlib scan) | `tests/benchmarks/test_tblite_runner.py` (结构模板) | role-match |
| `tests/code/test_code_target_loader.py` | test | request-response (mock filesystem) | `tests/tools/test_tool_loader.py` | role-match |
| `tests/code/test_code_fitness.py` | test | batch (mock subprocess) | `tests/benchmarks/test_tblite_runner.py` | role-match |
| `tests/code/test_sandbox_runner.py` | test | request-response (mock subprocess) | `tests/benchmarks/test_tblite_runner.py` | exact |
| `tests/code/test_evolve_code_cli.py` | test | request-response (CliRunner + mock) | `tests/tools/test_evolve_tool_descriptions.py` | exact |
| `tests/code/test_ansi_strip_holdout.py` | test (holdout edge case) | request-response (real ansi_strip import) | `~/.hermes/hermes-agent/tests/tools/test_ansi_strip.py` (外部) | role-match |
| `output/code/.gitkeep` | stub | N/A | `output/` (.gitignore 已含，仅占位) | N/A |
| `output/code/<ts>/NOTICE.md` (模板字符串) | doc (runtime artifact) | N/A | `evolution/prompts/evolve_prompt_sections.py` metrics 写盘模式 | partial |

---

## Pattern Assignments

### `evolution/code/__init__.py` (package init, lazy guard)

**Analog:** `evolution/benchmarks/__init__.py`

**完整模板** (analog lines 1-15):
```python
# evolution/benchmarks/__init__.py  lines 1-15
"""Phase 20: Benchmark-gated validation for evolved prompt artifacts.

Lazy-import guard (Phase 20 D-Discretion-1): submodules
(tblite_runner / benchmark_gate / build_tblite_calibration) are NOT
auto-imported here. Callers must explicitly:

    from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
    from evolution.benchmarks.tblite_runner import TBLiteRunner

Rationale: hermes-agent or huggingface_hub may be unreachable on a
given dev machine; `evolve_prompt_sections --benchmark=none` (the
default) MUST keep working without surfacing ImportError from the
evolution package's __init__ chain. Eager imports here would cascade
failure into every CLI entrypoint that touches evolution.*.
"""
```

**adapt_notes:**
1. 将 Phase 编号改为 21、包名改为 `evolution/code/`
2. Rationale 说明改为：openevolve 未安装（`pip install .[code]` 未执行）时不 crash
3. 给出正确的显式 import 示例：`from evolution.code.code_evolver_adapter import evolve_code`
4. 保留 lazy-import 核心理念，不在 `__init__` 里 `import openevolve`

**do_not_copy:**
- 不要在 `__init__.py` 内部写 `import openevolve`（D-03 单点 import 面）

---

### `evolution/code/code_target_loader.py` (loader, request-response)

**Analog:** `evolution/tools/evolve_tool_descriptions.py` 中的 `discover_tool_files` + `extract_tool_descriptions` 结构；`evolution/core/constraints.py` 的 `ConstraintResult` dataclass 模式

**Imports pattern** (analog: `evolution/core/constraints.py` lines 1-12):
```python
# evolution/core/constraints.py  lines 1-12
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from evolution.core.config import EvolutionConfig

@dataclass
class ConstraintResult:
    passed: bool
    constraint_name: str
    message: str
    details: Optional[str] = None
```

**Dataclass pattern** (analog: `evolution/core/constraints.py` lines 15-21):
```python
# evolution/core/constraints.py  lines 15-21
@dataclass
class ConstraintResult:
    """Result of constraint validation."""
    passed: bool
    constraint_name: str
    message: str
    details: Optional[str] = None
```

**Loader path-guard pattern** (analog: `evolution/core/config.py` lines 363-388):
```python
# evolution/core/config.py  lines 363-388
def get_hermes_agent_path() -> Path:
    """Discover the hermes-agent repo path.

    Priority:
    1. HERMES_AGENT_REPO env var
    2. ~/.hermes/hermes-agent (standard install location)
    3. ../hermes-agent (sibling directory)
    """
    env_path = os.getenv("HERMES_AGENT_REPO")
    if env_path:
        p = Path(env_path).expanduser()
        if p.exists():
            return p

    home_path = Path.home() / ".hermes" / "hermes-agent"
    if home_path.exists():
        return home_path

    sibling_path = Path(__file__).parent.parent.parent / "hermes-agent"
    if sibling_path.exists():
        return sibling_path

    raise FileNotFoundError(
        "Cannot find hermes-agent repo. Set HERMES_AGENT_REPO env var "
        "or ensure it exists at ~/.hermes/hermes-agent"
    )
```

**adapt_notes:**
1. `CodeTarget` dataclass 含字段：`component_path: Path`、`test_file_path: Path`、`baseline_size_bytes: int`、`original_source: str`（文件内容）
2. `find_target(component: str, hermes_repo: Path) -> CodeTarget` 参照 `get_hermes_agent_path` 的路径探测风格，但额外拒绝 `evolution/` 路径（`raise ValueError("Refusing to evolve evolution/ itself")`）
3. `find_target_tests(target: CodeTarget) -> list[dict]` 使用 `ast.parse` 而非 exec；返回 test manifest JSON-serializable list
4. 加入 `schema_version` + `hermes_agent_commit` 字段到 manifest（D-08 Risk anchor）
5. stratified split 函数将 manifest 按 CSI/SGR/OSC/other 桶化并返回 train_ids / holdout_ids

**do_not_copy:**
- 不要使用 `exec()` 或 `importlib.import_module()` 加载 test 文件（D-08 要求 AST 静态扫描）
- 不要允许 `evolution/` 路径穿透（递归自进化硬 reject）

---

### `evolution/code/code_fitness.py` (fitness scorer, batch)

**Analog:** `evolution/benchmarks/benchmark_gate.py` `TBLiteBenchmarkGate.check` (lines 529-713)

**Imports + dataclass** (analog: `evolution/core/constraints.py` lines 1-21):
```python
# evolution/core/constraints.py  lines 1-21
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from evolution.core.config import EvolutionConfig

@dataclass
class ConstraintResult:
    passed: bool
    constraint_name: str
    message: str
    details: Optional[str] = None
```

**Scoring decision pattern** (analog: `evolution/benchmarks/benchmark_gate.py` lines 656-700):
```python
# evolution/benchmarks/benchmark_gate.py  lines 656-700 (simplified)
        risk_score = self._compute_risk_score(per_tier_report)
        decision = "reject" if risk_score >= self.reject_threshold else "accept"
        # Subprocess-level failure overrides accept
        if run_status_any_error and decision == "accept":
            decision = "reject"
        if failed_runs >= self.runs / 2:
            decision = "reject"

        report = {
            "decision": decision,
            "risk_score": round(risk_score, 4),
            "reject_threshold": self.reject_threshold,
            ...
        }
        reason = (
            f"Risk_Score {risk_score:.2f} "
            f"({'>=' if decision == 'reject' else '<'}) "
            f"reject_threshold {self.reject_threshold:.2f}"
        )
        report["constraint_result"] = ConstraintResult(
            passed=(decision == "accept"),
            constraint_name="tblite_benchmark",
            message=reason,
            details=json.dumps(per_tier_report, sort_keys=True),
        )
```

**Subprocess check=False pattern** (analog: `evolution/core/constraints.py` lines 56-93):
```python
# evolution/core/constraints.py  lines 56-93
    def run_test_suite(self, hermes_repo: Path) -> ConstraintResult:
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-q", "--tb=no"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(hermes_repo),
            )
            if result.returncode == 0:
                return ConstraintResult(
                    passed=True,
                    constraint_name="test_suite",
                    message="All tests passed",
                    ...
                )
            else:
                ...
        except subprocess.TimeoutExpired:
            return ConstraintResult(
                passed=False,
                constraint_name="test_suite",
                message="Test suite timed out (300s)",
            )
        except Exception as e:
            return ConstraintResult(
                passed=False,
                constraint_name="test_suite",
                message=f"Failed to run tests: {e}",
            )
```

**adapt_notes:**
1. `CodeFitness` dataclass 直接沿用 D-11 CONTEXT 中的精确字段（`pytest_passed`、`pytest_total`、`size_baseline_bytes`、`size_evolved_bytes`、`ruff_violations`、`pytest_score`、`size_component`、`ruff_score`、`composite`、`decision`、`reject_reason`、`pytest_failures: list[dict]`、`ruff_findings: list[dict]`）
2. `score_candidate` 是独立函数而非方法（供 openevolve evaluator 文件调用）
3. pytest 子进程用 `check=False` + 解析 returncode；ruff 同样 `check=False`（exit 1 = 有 violations，非错误）
4. 三段 size_component 公式按 D-12 实现；ruff 三段映射按 D-13；composite 按 D-11
5. `to_dict()` 方法输出 `code_*` 前缀字段名

**do_not_copy:**
- 不要使用 `check=True` 调用 ruff（exit 1 会被误判为错误，Pitfall 2）
- 不要使用 LLM judge（D-14 禁止，连 nudge 也不要）

---

### `evolution/code/code_evolver_adapter.py` (adapter/facade, request-response)

**Analog:** `evolution/benchmarks/benchmark_gate.py` (单点 facade 包装外部库的整体模式，lines 95-200)

**Facade 初始化模式** (analog: `evolution/benchmarks/benchmark_gate.py` lines 95-200):
```python
# evolution/benchmarks/benchmark_gate.py  lines 118-200 (constructor)
class TBLiteBenchmarkGate:
    def __init__(
        self,
        config: EvolutionConfig,
        anchor: dict,
        stratified_subset: dict,
        *,
        moving_avg_history: Optional[list] = None,
        tier_weights: Optional[dict] = None,
        reject_threshold: Optional[float] = None,
        runs: Optional[int] = None,
        confidence_z: float = CONFIDENCE_Z,
    ):
        ...
        self.config = config
        ...
        self.runner = TBLiteRunner(config)
```

**openevolve Config 构造** (来自 RESEARCH.md §Code Examples，已验证):
```python
# Source: RESEARCH.md §openevolve Config 构造（adapter 核心）[VERIFIED]
from openevolve import Config, run_evolution
from openevolve.config import LLMModelConfig

def _build_oe_config(evolution_config, iterations: int, sandbox_timeout: int) -> Config:
    oe_config = Config()
    model_cfg = LLMModelConfig(
        name=evolution_config.optimizer_model,
        api_base=evolution_config.api_base or "https://api.openai.com/v1",
        api_key=evolution_config.api_key,
        temperature=0.7,
        max_tokens=4096,
        timeout=sandbox_timeout,
    )
    oe_config.llm.models = [model_cfg]
    oe_config.llm.evaluator_models = [model_cfg]
    oe_config.max_iterations = iterations
    oe_config.database.population_size = 50    # PoC 保守值
    oe_config.database.archive_size = 20
    oe_config.database.num_islands = 3
    oe_config.evaluator.timeout = sandbox_timeout
    oe_config.evaluator.cascade_evaluation = False
    oe_config.evaluator.parallel_evaluations = 1
    return oe_config
```

**adapt_notes:**
1. 这是项目内**唯一**可以写 `import openevolve` 的文件（D-03）
2. 暴露窄接口：`evolve(target: CodeTarget, config: EvolutionConfig, output_dir: Path, iterations: int) -> EvolutionResult`（自定义 dataclass，不暴露 openevolve 内部类型给外层）
3. adapter 负责动态生成 evaluator .py 文件（self-contained，含 eval_dir_base / baseline_size 作为 module-level constants），Pitfall 1 防御
4. 加入 EVOLVE-BLOCK-START/END 标记时只包裹函数体，保留 `import re` + 模块常量在块外（Pitfall 5 防御）
5. `NOTICE.md` 模板常量可定义在此文件顶部（或独立 `notice_template.py`）

**do_not_copy:**
- 不要在其他文件（包括测试文件正文）中写 `import openevolve`（仅此文件 + 字符串字面量例外）
- 不要暴露 openevolve 内部类型（`Population`、`Archive` 等）给 `evolve_code.py`

---

### `evolution/code/sandbox_runner.py` (utility/subprocess, request-response)

**Analog:** `evolution/benchmarks/tblite_runner.py` `TBLiteRunner` (lines 163-383)

**核心 subprocess 启动模式** (analog: `evolution/benchmarks/tblite_runner.py` lines 253-326):
```python
# evolution/benchmarks/tblite_runner.py  lines 253-326 (简化)
        proc = subprocess.Popen(
            args,
            cwd=str(Path(self.config.hermes_agent_path)),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        ...
        # Drain queue after exit
        proc.wait()
        result.exit_code = proc.returncode
        if result.status == "ok" and result.exit_code != 0:
            result.status = "error"
```

**timeout + SIGTERM/SIGKILL fallback 模式** (analog: `evolution/benchmarks/tblite_runner.py` lines 299-316):
```python
# evolution/benchmarks/tblite_runner.py  lines 299-316
                if result.hang_count >= self.max_hangs:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                    result.status = "hang_timeout"
                    break
```

**restricted_env 构造** (来自 RESEARCH.md §Code Examples，已验证):
```python
# Source: RESEARCH.md §restricted_env 构造 [VERIFIED: 基于 D-20]
_API_KEY_ENV_VARS = {
    "OPENAI_API_KEY", "OPENROUTER_API_KEY", "DASHSCOPE_KEY",
    "EVOLUTION_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET",
}

def build_restricted_env(eval_dir: Path) -> dict:
    env = os.environ.copy()
    for key in _API_KEY_ENV_VARS:
        env.pop(key, None)
    env["HERMES_AGENT_REPO"] = str(eval_dir)  # 隔离到 eval_dir
    env["PYTHONPATH"] = str(eval_dir)
    return env
```

**adapt_notes:**
1. 使用 `subprocess.run` + `timeout=120`（非 Popen + 心跳线程，Phase 21 是短任务，无需 heartbeat）
2. eval_dir 生命周期用 `contextlib.contextmanager` + `shutil.rmtree` 包裹，确保异常也清理（Pitfall 6）
3. 最小 import 闭包：复制 `tools/__init__.py`（空文件）+ `tools/ansi_strip.py`（candidate）+ `test_ansi_strip.py`，不复制整个 hermes-agent
4. `PYTHONPATH=str(eval_dir)` 限制只允许 eval_dir + stdlib，防止 implicit hermes import（Pitfall 3）
5. timeout 触发 → return `(0, -1, [{"test_name": "timeout", ...}])`，不 raise 异常

**do_not_copy:**
- 不要复用 Popen + 两线程心跳监控（tblite_runner 的核心模式）；Phase 21 sandbox 用简化的 `subprocess.run` 即可
- 不要继承父进程的完整 env（必须删去 API key 环境变量）

---

### `evolution/code/evolve_code.py` (CLI orchestrator, request-response)

**Analog:** `evolution/tools/evolve_tool_descriptions.py` (lines 110-490)

**5-param EvolutionConfig.load 模式** (analog: `evolution/tools/evolve_tool_descriptions.py` lines 134-141):
```python
# evolution/tools/evolve_tool_descriptions.py  lines 134-141
    config = EvolutionConfig.load(
        iterations=iterations,
        hermes_repo=hermes_repo,
        model=model,
        api_base=api_base,
    )
    console.print(
        f"\n[bold cyan]Hermes Agent Self-Evolution[/bold cyan]"
        f" -- Tool Description Optimization\n"
    )
```

**Click CLI 三件套** (analog: `evolution/tools/evolve_tool_descriptions.py` lines 467-490):
```python
# evolution/tools/evolve_tool_descriptions.py  lines 467-490
@click.command()
@click.option("--iterations", default=10, help="Number of GEPA iterations")
@click.option("--eval-source", default="synthetic", type=click.Choice(["synthetic", "load"]),
              help="Source for evaluation dataset")
@click.option("--hermes-repo", default=None, help="Path to hermes-agent repo")
@click.option("--dry-run", is_flag=True, help="Validate setup without running optimization")
@click.option("--model", default=None, help="Override model for all LLM calls (e.g. openai/qwen-plus)")
@click.option("--api-base", default=None, help="Override API base URL (e.g. https://...)")
@click.option("--session-source", default=None, ...)
def main(iterations, eval_source, hermes_repo, dry_run, model, api_base, session_source):
    """Evolve hermes-agent tool descriptions using DSPy + GEPA optimization."""
    evolve(
        iterations=iterations,
        ...
    )

if __name__ == "__main__":
    main()
```

**metrics.json + output_dir 写盘** (analog: `evolution/prompts/evolve_prompt_sections.py` lines 1372-1375, 1463-1469):
```python
# evolution/prompts/evolve_prompt_sections.py  lines 1372-1375 + 1463-1469
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output") / "prompts" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    ...
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2)
    )
    diff_text = _generate_diff(original_sections, evolved_sections)
    (output_dir / "diff.txt").write_text(diff_text)
    console.print(f"\n  Output saved to {output_dir}/")
```

**dry-run 模式** (analog: `evolution/tools/evolve_tool_descriptions.py` lines 171-180):
```python
# evolution/tools/evolve_tool_descriptions.py  lines 171-180
    if dry_run:
        console.print("[bold green]DRY RUN -- setup validated successfully.[/bold green]")
        console.print(f"  Would optimize {len(all_tools)} tool description(s)")
        console.print(f"  Dataset source: {eval_source}")
        ...
        return
```

**adapt_notes:**
1. CLI flags 按 CONTEXT D-21 设计：`--component / --iterations / --eval-source / --hermes-repo / --dry-run / --max-cost / --allow-fallback`（evolve_tool_descriptions 有 `--model / --api-base`，Phase 21 也加这两个）
2. `evolve()` 业务函数独立于 `main()` CLI 入口（同 evolve_tool_descriptions 模式）
3. pre-flight 检查（D-22 顺序）在 evolve() 函数最前面，用 `raise SystemExit(1)` + Rich 错误消息（不是 `sys.exit(1)`，与项目代码风格一致）
4. 输出目录拓扑：`output/code/<ts>/` + `output/code/FAILED_<ts>/`（对齐 v1 三个 evolve_* 的 FAILED 路径）
5. NOTICE.md 写入前用 `_contains_secret` 过滤（Pitfall 7）

**do_not_copy:**
- 不要复用 `evolve_skill.py` 的 3-param signature（CONCERNS H1；Phase 21 必须用 5-param EvolutionConfig.load 模式）
- 不要在 `evolve_code.py` 里 `import openevolve`（D-03 单点 import 面）

---

### `evolution/code/LICENSING.md` (doc)

**Analog:** `evolution/benchmarks/__init__.py` 的 docstring 边界说明风格（lines 1-15）

**adapt_notes:**
1. 说明 openevolve 是 Apache-2.0，是 `[code]` optional dep 的唯一新库
2. 说明 `evolution/code/` 其余文件属本项目 MIT 许可
3. 说明 `output/code/<ts>/` 产物也属 MIT（不继承 openevolve 许可）
4. 直接对应 D-21 决策中的内容

---

### `LICENSE` (config/doc，仓根)

**Analog:** 无（仓内不存在，Wave 0 必须新建）

**adapt_notes:**
1. MIT 文本，项目名 `hermes-agent-self-evolution`，年份 2026
2. 版权人占位符 `<COPYRIGHT_HOLDER>`，executor 提交前 AskUserQuestion 确认
3. 这是不可逆决策，D-17 要求在 Phase 21 第一个 plan 之前完成

---

### `.pre-commit-config.yaml` (config)

**Analog:** 无（仓内不存在；RESEARCH.md §CI lint gate 提供已验证 YAML 片段）

**来自 CONTEXT.md §D-18 的验证片段：**
```yaml
# .pre-commit-config.yaml  (CONTEXT.md D-18 §CI lint gate)
repos:
  - repo: local
    hooks:
      - id: openevolve-single-import-surface
        name: Block openevolve import outside code_evolver_adapter
        entry: bash -c 'grep -rn "^import openevolve\|^from openevolve" evolution/ --include="*.py" --exclude-dir=__pycache__ | grep -v "evolution/code/code_evolver_adapter.py" && exit 1 || exit 0'
        language: system
        pass_filenames: false
        always_run: true
```

**adapt_notes:**
1. 这是仓内第一个 `.pre-commit-config.yaml`，只包含这一个 hook
2. `language: system` 意味着需要 bash 可用（macOS/Linux CI 均满足）
3. `always_run: true` 确保不受 `--files` 过滤影响

---

### `pyproject.toml` (修改，config)

**Analog:** 当前 `pyproject.toml` `[project.optional-dependencies]` 段 (lines 25-32)

**现有 darwinian extra（必须替换）：**
```toml
# pyproject.toml  lines 25-32 (当前，Wave 0 必须修改)
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]
darwinian = [
    "darwinian-evolver",
]
```

**adapt_notes:**
1. 删除 `darwinian = ["darwinian-evolver"]` 段（D-02，darwinian-evolver 不存在于 PyPI）
2. 新增 `code = ["openevolve>=0.2.27"]`
3. 在 `dev` extra 中加入 `"ruff"` （RESEARCH.md §ruff 配置现状，venv 未安装）
4. 在 `pyproject.toml` 加 `[tool.ruff]` 段（最小配置：`line-length = 120`，`select = ["E", "F", "W"]`）

**目标形态：**
```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "ruff",
]
code = [
    "openevolve>=0.2.27",
]

[tool.ruff]
line-length = 120
select = ["E", "F", "W"]
```

---

### `tests/code/__init__.py` (test package init)

**Analog:** `tests/__init__.py`（空文件）

**adapt_notes:**
1. 空文件即可，与 `tests/tools/__init__.py` 同模式

---

### `tests/code/test_import_boundary.py` (test, file-I/O)

**Analog:** `tests/benchmarks/test_tblite_runner.py` 的整体测试类结构

**测试类结构** (analog: `tests/benchmarks/test_tblite_runner.py` lines 1-48):
```python
# tests/benchmarks/test_tblite_runner.py  lines 1-48
"""Unit tests for evolution/benchmarks/tblite_runner.py.

Tests use unittest.mock to stub subprocess.Popen — NO real TBLite
invocation.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evolution.core.config import EvolutionConfig


def _make_runner(tmp_hermes_path: Path, *, heartbeat: int = 60, max_hangs: int = 3):
    """Build a TBLiteRunner with a minimal fake config."""
    ...

class TestTBLiteRunner:
    def test_popen_args_constructed(self, tmp_path):
        """args contain evaluate, --env.task_filter <csv>, ..."""
        ...
```

**adapt_notes:**
1. 核心测试：`test_openevolve_import_only_in_adapter`，用 `pathlib.Path` 遍历 `evolution/` 所有 `.py`，正则匹配 `^import openevolve|^from openevolve`，断言仅 `code_evolver_adapter.py` 出现
2. 不 `import openevolve` 本身（允许在未安装 openevolve 的环境通过）
3. 测试须在 `< 1s` 内完成（纯文件读取，无 LLM 调用）

---

### `tests/code/test_code_target_loader.py` (test, request-response)

**Analog:** `tests/tools/test_tool_loader.py` (lines 1-80)

**测试结构** (analog: `tests/tools/test_tool_loader.py` lines 1-20):
```python
# tests/tools/test_tool_loader.py  lines 1-16
"""Tests for tool description extraction and write-back from hermes-agent tool files."""

import py_compile
import shutil

import pytest
from pathlib import Path

from evolution.tools.tool_loader import (
    ToolDescription,
    discover_tool_files,
    extract_tool_descriptions,
)
```

**adapt_notes:**
1. 用 `tmp_path` fixture 建 mock hermes-agent 目录（含 `tools/ansi_strip.py` + `tests/tools/test_ansi_strip.py`）
2. 测试 `find_target("tools/ansi_strip.py", mock_hermes)` → 返回正确 `CodeTarget`
3. 测试 `find_target("evolution/core/config.py", ...)` → 抛 `ValueError`（递归自进化防御）
4. 测试 `find_target_tests(target)` AST 扫描发现 test 函数的数量
5. 覆盖 stratified split 各桶逻辑

---

### `tests/code/test_code_fitness.py` (test, batch)

**Analog:** `tests/benchmarks/test_tblite_runner.py` 的 mock subprocess 模式

**mock subprocess 模式** (analog: `tests/benchmarks/test_tblite_runner.py` lines 28-84):
```python
# tests/benchmarks/test_tblite_runner.py  lines 28-84
def _mock_popen_with_streams(stdout_lines, stderr_lines, exit_code=0):
    stdout_iter = iter(list(stdout_lines) + [""])
    stderr_iter = iter(list(stderr_lines) + [""])
    mock_proc = MagicMock()
    mock_proc.stdout = MagicMock()
    mock_proc.stdout.readline.side_effect = lambda: next(stdout_iter)
    ...
    mock_proc.returncode = exit_code
    return mock_proc


class TestTBLiteRunner:
    def test_popen_args_constructed(self, tmp_path):
        from evolution.benchmarks import tblite_runner as mod
        runner = _make_runner(tmp_path, heartbeat=2)
        with patch.object(mod, "subprocess") as mock_subp:
            mock_subp.Popen.return_value = _mock_popen_with_streams([], [])
            ...
```

**adapt_notes:**
1. mock `subprocess.run` 而非 `subprocess.Popen`（sandbox_runner 用 `run`，不用 `Popen`）
2. 六条测试路径：pytest 全过/不过、size ≤1.2x/≥1.5x、ruff 0条/3条 violations
3. 验证 `composite = 0.0` + `decision = "reject"` 当 pytest 不全过（二进制硬门）
4. 验证 `ruff exit code 1` 不抛 CalledProcessError（Pitfall 2）

---

### `tests/code/test_sandbox_runner.py` (test, request-response)

**Analog:** `tests/benchmarks/test_tblite_runner.py` (整体结构，lines 51-130)

**adapt_notes:**
1. `test_restricted_env_removes_api_keys`：传入含 `OPENAI_API_KEY` 的 env，验证 `build_restricted_env()` 输出不含该 key
2. `test_sandbox_timeout_returns_zero_fitness`：mock `subprocess.run` 抛 `TimeoutExpired`，验证 `(0, -1, [...])`
3. `test_eval_dir_is_cleaned_after_run`：run 后 eval_dir 不存在
4. `test_candidate_with_implicit_hermes_import_fails_cleanly`：写含 `import hermes` 的 candidate，验证 pytest 失败且不 crash sandbox

---

### `tests/code/test_evolve_code_cli.py` (test, request-response)

**Analog:** `tests/tools/test_evolve_tool_descriptions.py` (lines 1-80)

**CliRunner 模式** (analog: `tests/tools/test_evolve_tool_descriptions.py` lines 40-65):
```python
# tests/tools/test_evolve_tool_descriptions.py  lines 40-65
class TestCLI:
    def test_cli_help(self):
        from click.testing import CliRunner
        from evolution.tools.evolve_tool_descriptions import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "--iterations" in result.output
        ...

class TestDryRun:
    @patch("evolution.tools.evolve_tool_descriptions.extract_tool_descriptions")
    @patch("evolution.tools.evolve_tool_descriptions.discover_tool_files")
    def test_dry_run_shows_tools_no_gepa(self, mock_discover, mock_extract):
        ...
```

**adapt_notes:**
1. `test_dry_run_exits_0_without_openevolve_call`：mock `code_evolver_adapter.evolve`，`--dry-run` 下不调用，exit 0
2. `test_preflight_fails_without_license`：mock `LICENSE` 路径不存在，pre-flight 返回 `SystemExit(1)`
3. `test_cli_passes_model_to_evolution_config`：`--model qwen-plus` 正确传入 EvolutionConfig

---

### `tests/code/test_ansi_strip_holdout.py` (test, holdout edge case)

**Analog:** `~/.hermes/hermes-agent/tests/tools/test_ansi_strip.py`（外部，30 个 pytest）

**adapt_notes:**
1. 文件在 evolution 仓内（`tests/code/`），**不**入 hermes-agent
2. 直接 `from tools.ansi_strip import strip_ansi`（需要 `PYTHONPATH` 包含 hermes-agent tools/ 目录，或在 conftest.py 处理）
3. 覆盖 CONTEXT D-07 中列出的 10 个 edge case（超长输入 / Unicode / 嵌套 / 截断 CSI 等）
4. 这些测试也作为 holdout gate 的 edge case 部分（D-15）

---

### `output/code/.gitkeep` (stub)

**Analog:** `.gitignore` 已含 `output/`（RESEARCH.md §基础设施前置验证）

**adapt_notes:**
1. `output/code/` 目录因 `.gitignore` 含 `output/` 而不被 git 跟踪，需要 `.gitkeep` 文件让目录存在于 repo
2. 空文件即可

---

## Shared Patterns

### EvolutionConfig.load 三层配置链
**Source:** `evolution/core/config.py` lines 108-360
**Apply to:** `evolution/code/evolve_code.py`
```python
# evolution/core/config.py  lines 108-142 (load 入口)
@classmethod
def load(cls, config_path: Optional[str] = None, **overrides) -> "EvolutionConfig":
    """Load config from evolution.yaml with env var and CLI overrides.

    Priority (highest wins):
    1. CLI overrides (passed as **overrides)
    2. Environment variables (EVOLUTION_API_BASE, EVOLUTION_API_KEY, EVOLUTION_MODEL)
    3. evolution.yaml config file
    4. Dataclass defaults
    """
    config = cls()
    yaml_path = Path(config_path) if config_path else Path("evolution.yaml")
    ...
    # CLI overrides (highest priority)
    if overrides.get("api_base"):
        config.api_base = overrides["api_base"]
    if overrides.get("model"):
        config.optimizer_model = overrides["model"]
    if overrides.get("iterations"):
        config.iterations = overrides["iterations"]
    if overrides.get("hermes_repo"):
        config.hermes_agent_path = Path(overrides["hermes_repo"])
    ...
    return config
```

### ConstraintResult dataclass (accept/reject 决策封装)
**Source:** `evolution/core/constraints.py` lines 15-21
**Apply to:** `evolution/code/code_fitness.py`（`CodeFitness` 的设计沿用此模式）
```python
# evolution/core/constraints.py  lines 15-21
@dataclass
class ConstraintResult:
    passed: bool
    constraint_name: str
    message: str
    details: Optional[str] = None
```

### subprocess 错误处理模式
**Source:** `evolution/core/constraints.py` lines 56-93
**Apply to:** `evolution/code/sandbox_runner.py`、`evolution/code/code_fitness.py`
```python
# evolution/core/constraints.py  lines 56-93
        try:
            result = subprocess.run([...], capture_output=True, text=True, timeout=300, cwd=str(hermes_repo))
            if result.returncode == 0:
                return ConstraintResult(passed=True, ...)
            else:
                ...
        except subprocess.TimeoutExpired:
            return ConstraintResult(passed=False, message="Test suite timed out (300s)")
        except Exception as e:
            return ConstraintResult(passed=False, message=f"Failed to run tests: {e}")
```

### FAILED_<ts>/ + metrics.json 输出拓扑
**Source:** `evolution/prompts/evolve_prompt_sections.py` lines 1320-1365 (FAILED 路径) + 1372-1375 (成功路径)
**Apply to:** `evolution/code/evolve_code.py`
```python
# evolution/prompts/evolve_prompt_sections.py  lines 1372-1375
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output") / "prompts" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    ...
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (output_dir / "diff.txt").write_text(diff_text)
```

### _contains_secret 过滤
**Source:** `evolution/core/external_importers.py` lines 108-130
**Apply to:** `evolution/code/evolve_code.py`（写 NOTICE.md 前调用）
```python
# evolution/core/external_importers.py  lines 108-115
def _contains_secret(text: str) -> bool:
    """Check if text contains potential API keys or tokens.

    Layer 1: pattern match against known secret prefixes/formats.
    Layer 2 (D-15): Shannon entropy heuristic over ≥24-char base64-like
    tokens — flag if entropy > _SECRET_ENTROPY_THRESHOLD.
    """
```

### Rich console + Panel/Table 输出
**Source:** `evolution/tools/evolve_tool_descriptions.py` lines 37-38, 163-169
**Apply to:** `evolution/code/evolve_code.py`
```python
# evolution/tools/evolve_tool_descriptions.py  lines 37-38 + 163-169
console = Console()
...
    table = Table(title="Discovered Tools")
    table.add_column("Tool Name", style="bold")
    table.add_column("Description Length", justify="right")
    ...
    console.print(table)
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `LICENSE` | doc | N/A | 仓内无 LICENSE 文件（RESEARCH.md §基础设施前置），Wave 0 按 MIT 标准模板新建 |
| `.pre-commit-config.yaml` | config | N/A | 仓内无 pre-commit 配置；CONTEXT D-18 提供完整 YAML hook 片段，可直接使用 |
| `ruff.toml` / `[tool.ruff]` 段 | config | N/A | 仓内无 ruff 配置（RESEARCH.md §ruff 配置现状）；最小 E/F/W 配置直接写 |

---

## Metadata

**Analog search scope:** `evolution/`、`tests/`、`pyproject.toml`
**Files scanned:** 12 个生产文件 + 6 个测试文件
**Pattern extraction date:** 2026-05-20

---

## PATTERN MAPPING COMPLETE

**Phase:** 21 - Darwinian Code Evolution
**Files classified:** 20
**Analogs found:** 17 / 20

### Coverage
- Files with exact analog: 5 (`__init__.py`、`sandbox_runner.py`、`evolve_code.py`、`tests/code/__init__.py`、`test_evolve_code_cli.py`)
- Files with role-match analog: 10 (`code_target_loader.py`、`code_fitness.py`、`code_evolver_adapter.py`、`pyproject.toml`修改、全部 test_*.py)
- Files with no analog: 3 (`LICENSE`、`.pre-commit-config.yaml`、`ruff.toml/[tool.ruff]`)
- N/A (stub/doc): 2 (`output/code/.gitkeep`、`NOTICE.md` 模板)

### Key Patterns Identified
- 所有 CLI 入口用 `evolve_tool_descriptions.py` 三件套（Click + Rich + EvolutionConfig.load 5-param）
- sandbox_runner.py 是 tblite_runner.py 的简化同构（subprocess.run 替代 Popen + 心跳）
- code_fitness.py 的 accept/reject 决策封装对齐 ConstraintResult dataclass 模式
- code_evolver_adapter.py 是 TBLiteBenchmarkGate 的 facade 精神同构（单点包装外部库）
- evolution/code/__init__.py 的 lazy import guard 直接复制 evolution/benchmarks/__init__.py 结构

### File Created
`.planning/phases/21-darwinian-code-evolution/21-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner 可基于本 PATTERNS.md 在每个 PLAN.md action 中引用 analog 文件路径 + 行号，直接指定"copy from X lines N-M, adapt as follows"。
