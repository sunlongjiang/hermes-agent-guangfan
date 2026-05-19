# Phase 20: Benchmark-Gated Validation — Pattern Map

**Mapped:** 2026-05-19
**Phase:** 20 — Benchmark-Gated Validation (PMPT-V2-03)
**Files analyzed:** 13 (4 新建源码 + 1 新建 CLI + 3 修改 + 3 新建测试 + 2 新建 git-tracked 数据 artifact)
**Analogs found:** 12 / 13(`tblite_runner.py` 的 Async Stream Pipe + State Monitor 在本仓 evolution 包内**无前例**,仅有的 subprocess 用法是 `constraints.py:55-93` 的 `subprocess.run` 阻塞调用 — 详 §No Analog Found)

> **Read instruction:** 本文档为 `gsd-planner` 与 `gsd-execute-phase` 必读资产。所有代码摘录均带文件路径 + 行号,executor 可直接照搬骨架并按 CONTEXT.md D-01..D-18 决策与 §Risk Anchors 改写差异点(差异点已在每个 "Adaptation Delta" 小节列出)。Phase 20 的核心模板来源是 **Phase 18**(`evolve_prompt_sections.py` step 8c / `build_drift_calibration.py` CLI / `drift_detector.py` 类结构),Phase 20 把这些模板从 "in-process LLM judge" 升级到 "subprocess-bound TBLite 二值信号 + Virtual Prompt Overlay"。

---

## File Classification

| New/Modified File | Status | Role | Data Flow | Closest Analog | 行号锚 | Match Quality |
|---|---|---|---|---|---|---|
| `evolution/benchmarks/__init__.py` | **NEW** | package init(lazy import guard) | — | `evolution/code/__init__.py` + `evolution/monitor/__init__.py` | 全文(1-5 行的占位包) | role-match(空 init 模式) |
| `evolution/benchmarks/tblite_runner.py` | **NEW** | service(subprocess wrapper + Async Stream Pipe + State Monitor) | event-driven streaming + transform | `evolution/core/constraints.py:55-93` (subprocess.run + TimeoutExpired) — **唯一前例,但是 blocking,非 stream** | 55-93 | **partial / no exact analog** — Async Pipe + heartbeat 部分需 stdlib `subprocess.Popen` + `threading` 新写,详 §No Analog Found §1 |
| `evolution/benchmarks/benchmark_gate.py` | **NEW** | LLM/binary-judge style constraint module(Risk_Score + Virtual Prompt Overlay) | request-response(orchestrator over subprocess + scoring) | `evolution/prompts/drift_detector.py:77-258` (`DriftDetector` 类 — `check_all` 接口、threshold + σ 决策、ConstraintResult 嵌套 dict) | 77-258 | exact(sibling 类结构,severity ladder 升级为 Risk_Score 阈值)|
| `evolution/benchmarks/build_tblite_calibration.py` | **NEW** | CLI(anchor 校准) | request-response | `evolution/prompts/build_drift_calibration.py:1-473` (整文件) | 1-473 | exact(直接同构 CLI 模板 — Click + Rich + Tier table + git-tracked JSON anchor) |
| `evolution/prompts/evolve_prompt_sections.py` (step 10.5 + CLI flags + subcommands) | **MODIFY** | orchestration / pipeline 插桩 | request-response | 同文件 step 8c drift gate 块(行 641-750)+ step 11 metrics 字段块(行 1067-1086)+ CLI flag 块(行 1176-1200) | 641-750, 1067-1086, 1176-1200 | self-analog(Phase 18 已植入完整 drift gate,Phase 20 完全照搬到 step 10.5 + 把 reject → FAILED_ 路径同步) |
| `evolution/core/config.py` (新增字段) | **MODIFY** | config | — | 同文件 `max_cost_usd: float = 20.0` 字段(行 57-59)+ `run_tblite: bool = False` 字段(行 67-70) | 57-70 | exact(role-match — Phase 13 已建立"cost cap 字段 + EVOLUTION_* env override"模式) |
| `evolution/core/cost_tracker.py` | **READ-ONLY / 实例化** | utility | — | 不修改 — Phase 20 通过两个独立 `CostTracker(max_usd=...)` 实例化(D-16)即可 | — | direct-reuse |
| `datasets/prompts/tblite_anchor.json` | **NEW** | persistent artifact(anchor + dataset_revision_hash + hermes_agent_commit metadata,git-tracked) | file I/O | `datasets/prompts/drift_thresholds.json`(Phase 18 D-CAL-02 git exception 落盘模式) | schema 形式 + .gitignore exception 处理 | role-match(单 JSON 文件 + `_meta` 块 + `!` exception)|
| `datasets/prompts/tblite_stratified_subset.json` | **NEW** | persistent artifact(30-task 白名单 + seed,git-tracked) | file I/O | 同上 `drift_thresholds.json` | 同上 | role-match |
| `.gitignore` | **MODIFY** | gitignore mod | — | 同文件 Phase 18 `!datasets/prompts/drift_*` exception 行(.gitignore:20-23) + `output/` 行(.gitignore:30) | 16-30 | exact(直接追加两行 anchor exception + 新增 `logs/` ignore) |
| `tests/benchmarks/__init__.py` | **NEW** | test package init | — | `tests/prompts/__init__.py` / `tests/tools/__init__.py`(空文件) | 空 | role-match |
| `tests/benchmarks/test_tblite_runner.py` | **NEW** | test scaffold(单元 — mock subprocess + parse samples.jsonl) | unit test | `tests/prompts/test_drift_detector.py:1-198`(典型 mock LM + fake section 拓扑) | 1-198 | partial(测试拓扑沿用,但 mock 对象是 `subprocess.Popen` 而非 `dspy.LM` — 详 §3.B Adaptation Delta) |
| `tests/benchmarks/test_benchmark_gate.py` | **NEW** | test scaffold(单元 — Risk_Score 算法 + 1.96σ 决策) | unit test | `tests/prompts/test_drift_detector.py:1-198`(severity ladder + 阈值边界测试)+ `tests/prompts/test_drift_calibration.py:1-139`(F1 derivation 边界测试) | 1-198, 1-139 | exact(算法测试模板 1:1 沿用,只换公式) |
| `tests/benchmarks/test_build_tblite_calibration.py` | **NEW** | test scaffold(CLI 单元) | unit test | `tests/prompts/test_drift_calibration.py:1-139`(test_derive_thresholds_f1_optimal 模式) | 1-139 | exact |

> **关于 `evolution/core/cost_tracker.py` 不修改:** Phase 20 通过**双 `CostTracker` 实例化**(D-16)即可 — `optimization_tracker = CostTracker(config.max_cost_usd)` + `benchmark_tracker = CostTracker(config.benchmark_max_cost_usd)`,两个 context manager 互不污染。`CostBudgetExceeded` 在 D-17 Pre-flight Watermark 触发时复用现有异常类。

---

## Pattern Assignments

### File 1: `evolution/benchmarks/__init__.py` (NEW)

**Role:** package init,**lazy import guard**(CONTEXT §Discretion 第 1 项)
**Closest analog:** `evolution/code/__init__.py` 与 `evolution/monitor/__init__.py`(Phase 21/22 占位包,均为单纯空 init)
**Interface contract:**
- 文件存在,使 `evolution.benchmarks` 可被 `import` 发现
- **Discretion 决策推荐:** 不在 `__init__.py` 里 eager import `TBLiteRunner` / `TBLiteBenchmarkGate` — 让用户 `from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate` 显式按需。理由:hermes-agent 或 huggingface_hub 不可达时,`evolve_prompt_sections --benchmark=none` 仍需可跑(D-18 默认 none 路径)。eager import 会让 `evolution/__init__.py` 间接 import 链条触发 ImportError。

**Imports + content pattern** — verbatim 空文件即可,可保留一行 docstring:

```python
"""Phase 20: Benchmark-gated validation for evolved prompt artifacts.

Lazy-import guard: submodules (tblite_runner / benchmark_gate /
build_tblite_calibration) are NOT auto-imported here. Callers must
explicitly `from evolution.benchmarks.benchmark_gate import ...` so that
`evolve_prompt_sections --benchmark=none` keeps working when hermes-agent
isn't reachable or huggingface_hub is unavailable.
"""
```

> **Adaptation Delta vs analog:** Phase 21/22 占位 init 是完全空文件;Phase 20 加 docstring 以记录 lazy import 决策(对应 CONTEXT §Discretion 第 1 项)。**禁止**在此文件加任何 `from .tblite_runner import ...` 之类语句。

---

### File 2: `evolution/benchmarks/tblite_runner.py` (NEW)

**Role:** service(subprocess wrapper + Async Stream Pipe + State Monitor)
**Closest analog:** `evolution/core/constraints.py:55-93`(`run_test_suite` — **唯一**用 `subprocess` 的 evolution 模块,但走 `subprocess.run` blocking + `capture_output=True`,**无 stream pipe / heartbeat**)
**Match Quality:** partial — Phase 20 必须用 `subprocess.Popen` + daemon thread 非阻塞读 stdout/stderr,从零写。

**Interface contract:**
- `class TBLiteRunner` 构造 `__init__(self, config: EvolutionConfig, *, heartbeat_seconds: int = 60, max_hangs: int = 3)`
- `def run(self, task_filter: list[str], output_dir: Path, *, runs: int = 1) -> "TBLiteRunResult"` — 启动 subprocess、stream 解析、退出后聚合
- `@dataclass class TBLiteRunResult` 包含字段:`per_task: list[dict]`(每条来自 `samples_<ts>.jsonl` 的 row + `passed: bool` + `category: str` + `task_name: str`)、`subprocess_runtime_seconds: float`、`hang_count: int`、`cost_breakdown: dict[str, float]`、`samples_jsonl_path: Path`、`exit_code: int`、`status: Literal["ok", "hang_timeout", "error"]`
- 模块级常量:`TBLITE_RUNNER_VERSION = "1.0"`(D-15 cache key 需要)、`HEARTBEAT_SECONDS = 60`、`MAX_HANGS = 3`(D-11)
- (Discretion) subprocess 命令行最终选择(`bash run_eval.sh` vs `python tblite_env.py evaluate`)由 planner 在 Task 1 spike 决策(CONTEXT §code_context Risk Anchor 5)

**Anchor — `constraints.py:55-93` 的 blocking 模板(展示 Phase 20 必须改写的边界):**

```python
# evolution/core/constraints.py:55-93 — analog (blocking, NOT what Phase 20 wants)
def run_test_suite(self, hermes_repo: Path) -> ConstraintResult:
    """Run the full hermes-agent test suite. Must pass 100%."""
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
                details=result.stdout.strip().split("\n")[-1] if result.stdout else "",
            )
        else:
            last_lines = result.stdout.strip().split("\n")[-5:] if result.stdout else []
            return ConstraintResult(
                passed=False,
                constraint_name="test_suite",
                message="Test suite failed",
                details="\n".join(last_lines),
            )
    except subprocess.TimeoutExpired:
        return ConstraintResult(
            passed=False,
            constraint_name="test_suite",
            message="Test suite timed out (300s)",
        )
    except Exception as e:
        return ConstraintResult(...)
```

> **Adaptation Delta — 7 个关键差异点(executor 必读 CONTEXT §D-11 + §Risk Anchors):**
>
> 1. **改用 `subprocess.Popen` + `bufsize=1`(line-buffered)+ `text=True`** — 不能 `subprocess.run` 因为它阻塞到 TBLite 完成才返回 stdout(可能 30-120 min)。Phase 20 需要 stream stdout/stderr 逐行解析 `[START]task_name` / `[PASS]task_name` / `[FAIL]task_name` 标记 + tqdm 行用于 Rich Live Table。
> 2. **`threading.Thread(target=_pump_stream, daemon=True)` × 2** — 一个 thread 读 `proc.stdout`,一个读 `proc.stderr`,每行 push 到 `queue.Queue`。主线程 `queue.get(timeout=heartbeat_seconds)` 阻塞;`queue.Empty` → `hang_count += 1` + Rich console 黄警告;`hang_count >= max_hangs` → `proc.terminate()`(SIGTERM)+ 写 `TBLITE_HANG_<ts>/` 目录(同 Phase 18 `FAILED_<ts>/` 模式)。
> 3. **不 `capture_output=True`** — 那需要 wait-then-read,Phase 20 是 read-while-running。
> 4. **`cwd=config.hermes_agent_path`**(同 analog),并增 `env=os.environ.copy()` 透传 `OPENROUTER_API_KEY` / `MODAL_TOKEN_ID` 等(具体 env keys 由 planner Task 1 spike 验证,参考 `~/.hermes/hermes-agent/environments/benchmarks/tblite/default.yaml`)。
> 5. **退出后解析 `samples_<ts>.jsonl`** — TBLite 把 per-task 结果写 `output_dir / "samples_*.jsonl"`(CONTEXT canonical_refs §`terminalbench2_env.py:365-383` 锚定 `_streaming_path` schema)。用 **per-line `try/except json.JSONDecodeError` 跳过 + 计 `jsonl_skipped_lines`**(CONCERNS §M7 / Phase 19 D-24 模式 — 见 §Shared Pattern 4)。
> 6. **`category` 字段映射 tier** — TBLite README §难度分布(Easy:40 / Medium:26 / Hard:26 / Extreme:8 = 100)。planner Task 1 验证字段名:可能是 `category` / `difficulty` / `tier` 之一(CONTEXT §code_context §`terminalbench2_env.py:896-922` 锚)。把任一字段 normalize 成 `{"easy","medium","hard","extreme"}` 之一。
> 7. **infra-failure vs prompt-failure 区分**(CONTEXT §Risk Anchors §TBLite Modal 后端时延)— Modal API 错误 / sandbox 启动失败 → `samples.jsonl` 可能写 `{"passed": false, "error": "Modal timeout"}`。planner 在 PLAN 中决:per-task `error` 字段非空 → mark as `infra_fail` 且**不计入** Risk_Score breach(同 Phase 19 D-24 skip pattern)。

**Async Stream Pipe + State Monitor pattern**(全新代码,无 codebase analog — stdlib only):

```python
# evolution/benchmarks/tblite_runner.py — Phase 20 new code,no analog
import subprocess
import threading
import queue
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TBLiteRunResult:
    per_task: list[dict] = field(default_factory=list)
    subprocess_runtime_seconds: float = 0.0
    hang_count: int = 0
    cost_breakdown: dict[str, float] = field(default_factory=dict)
    samples_jsonl_path: Path | None = None
    exit_code: int = -1
    status: str = "ok"  # ok | hang_timeout | error
    jsonl_skipped_lines: int = 0  # Phase 19 D-24 mirror


def _pump_stream(stream, q: queue.Queue, stream_name: str) -> None:
    """Daemon-thread target: push each line + stream_name onto q.

    Exits when stream returns "" (EOF) — Popen closes stdout on subprocess exit.
    """
    for line in iter(stream.readline, ""):
        q.put((stream_name, line.rstrip("\n")))
    stream.close()


class TBLiteRunner:
    def __init__(
        self,
        config,
        *,
        heartbeat_seconds: int = 60,
        max_hangs: int = 3,
    ):
        self.config = config
        self.heartbeat_seconds = heartbeat_seconds
        self.max_hangs = max_hangs

    def run(
        self,
        task_filter: list[str],
        output_dir: Path,
        *,
        runs: int = 1,
    ) -> TBLiteRunResult:
        # Construct subprocess args (planner Task 1 spike — Discretion §3)
        args = [
            "python",
            str(self.config.hermes_agent_path / "environments/benchmarks/tblite/tblite_env.py"),
            "evaluate",
            "--config", str(
                self.config.hermes_agent_path / "environments/benchmarks/tblite/default.yaml"
            ),
            "--env.task_filter", ",".join(task_filter),
            "--env.data_dir_to_save_evals", str(output_dir),
        ]
        result = TBLiteRunResult()
        t_start = time.monotonic()
        proc = subprocess.Popen(
            args,
            cwd=str(self.config.hermes_agent_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        q: queue.Queue = queue.Queue()
        threading.Thread(
            target=_pump_stream, args=(proc.stdout, q, "stdout"), daemon=True
        ).start()
        threading.Thread(
            target=_pump_stream, args=(proc.stderr, q, "stderr"), daemon=True
        ).start()

        while True:
            try:
                stream_name, line = q.get(timeout=self.heartbeat_seconds)
                # parse [START]/[PASS]/[FAIL] markers, update Rich Live Table
                # (planner: pass console + Live to here for --wait mode)
            except queue.Empty:
                if proc.poll() is not None:
                    break  # subprocess exited; drain remaining queue then exit
                result.hang_count += 1
                # Rich yellow warning + heartbeat_seconds*hang_count elapsed
                if result.hang_count >= self.max_hangs:
                    proc.terminate()
                    result.status = "hang_timeout"
                    break

        proc.wait()
        result.subprocess_runtime_seconds = time.monotonic() - t_start
        result.exit_code = proc.returncode

        # Parse samples_<ts>.jsonl (Phase 19 D-24 robust JSONL pattern)
        # ... per-line try/except json.JSONDecodeError ...
        return result
```

> **Adaptation Delta vs analog:** 几乎全新 — 仅 `cwd=` / `subprocess.TimeoutExpired`(改 `proc.terminate()`)/ `text=True` 三个细节沿用 `constraints.py:58-93`。其余的 `Popen` + `threading` + `queue` 三件套是 Phase 20 引入 evolution 包的新基础设施。**禁止**用 `asyncio` 替代 — 项目所有 IO 都是同步,引入 asyncio 会污染 Click CLI 入口的事件循环假设。

**Cache key computation pattern**(D-15):

```python
import hashlib
import json


def _canonical_json(obj) -> str:
    """Canonical JSON for cache key — sorted keys, no spaces."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_artifact_hash(
    evolved_sections: list,
    dataset_revision_hash: str,
    stratified_subset_seed: int,
    tblite_runner_version: str = TBLITE_RUNNER_VERSION,
) -> str:
    """D-15 cache key: sha256(canonical evolved + dataset hash + seed + runner ver)[:16]."""
    h = hashlib.sha256()
    h.update(_canonical_json(
        [{"section_id": s.section_id, "text": s.text} for s in evolved_sections]
    ).encode("utf-8"))
    h.update(dataset_revision_hash.encode("utf-8"))
    h.update(stratified_subset_seed.to_bytes(4, "big"))
    h.update(tblite_runner_version.encode("utf-8"))
    return h.hexdigest()[:16]
```

> **Adaptation Delta:** 此函数本身无 analog(Phase 14 `_normalize_task_hash` 是单字段 hash);Phase 20 第一次引入 "多字段 content-addressed hash"。注意 `sort_keys=True` 是必须 — 防止 dict key 顺序波动影响 cache key。

---

### File 3: `evolution/benchmarks/benchmark_gate.py` (NEW)

**Role:** LLM/binary-judge style constraint module(Risk_Score 算法 + Virtual Prompt Overlay 编排)
**Closest analog:** `evolution/prompts/drift_detector.py:77-258`(`DriftDetector` 类 — `check_all` 接口、threshold + σ 决策、嵌套 ConstraintResult 输出)
**Interface contract:**
- `class TBLiteBenchmarkGate` 构造:
  ```python
  def __init__(
      self,
      config: EvolutionConfig,
      anchor: dict,                    # tblite_anchor.json 顶层 dict
      stratified_subset: dict,          # tblite_stratified_subset.json 顶层 dict
      *,
      moving_avg_history: list[dict] = None,   # tblite_history.json 最近 N=10 条
      tier_weights: dict[str, float] = None,    # 默认 {"easy": 1.0, ...}
      reject_threshold: float = 4.0,
      runs: int = 3,                    # D-03 median-of-3
      confidence_z: float = 1.96,
  )
  ```
- `def check(self, evolved_sections: list, *, cache_dir: Path | None = None, use_cache: bool = True) -> dict` — 主入口,返回与 D-04 `tblite_report.json` schema 1:1 的 dict + 嵌套 `constraint_result: ConstraintResult`
- 模块级常量:
  ```python
  TIER_WEIGHTS = {"easy": 1.0, "medium": 1.5, "hard": 2.0, "extreme": 4.0}
  REJECT_THRESHOLD = 4.0
  CONFIDENCE_Z = 1.96
  STRATIFIED_30 = {"easy": 12, "medium": 8, "hard": 7, "extreme": 3}  # 共 30
  ```
- 私有方法:`_run_overlay(evolved_sections) -> (snapshot_path: Path, overlay_path: Path)` / `_restore_overlay(snapshot_path)` / `_compute_risk_score(per_tier: dict) -> float` / `_check_anchor_existence()` / `_check_overlay_sanity()`

**Imports pattern**(drift_detector.py lines 1-21 沿用 + 新增项):

```python
"""TBLite benchmark-gated validation for evolved prompt sections (Phase 20).

Phase 20 final gate (NOT GEPA in-loop — PITFALL #7 prevention #1 hard
constraint). Compares evolved prompt sections against the anchor + moving
average baseline using TBLite stratified subset (~30 tasks) with 3-run
averaging and tier-weighted Risk_Score. Risk_Score >= 4.0 -> reject.

Virtual Prompt Overlay (D-09): file-level atomic replace of
hermes-agent/agent/prompt_builder.py via os.replace + snapshot/restore.
"""
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintResult
from evolution.benchmarks.tblite_runner import (
    TBLiteRunner, TBLiteRunResult, compute_artifact_hash,
    TBLITE_RUNNER_VERSION,
)


console = Console()
```

> **Adaptation Delta:** 相比 `drift_detector.py` 移除 `import dspy` / `pydantic.ValidationError`(TBLite 无 LLM judge,纯 binary signal);新增 `os` / `shutil`(Virtual Prompt Overlay)、`subprocess`(可选,如果 D-10 Pre-flight `git status --porcelain` 在此处调用而非 build_tblite_calibration 内调用)、`hashlib`(cache key)。模块 docstring 复用 drift_detector.py 的 7 行风格(简短 + Phase 决策号引用)。

**Core class pattern**(drift_detector.py:77-156 — 5 处偏离):

```python
# drift_detector.py:77-156 (analog — TBLiteBenchmarkGate 5 处偏离)
class DriftDetector:
    DriftScoreSignature = DriftScoreSignature  # 类属性暴露

    def __init__(self, config: EvolutionConfig, thresholds: dict):
        missing = set(DRIFT_DIMENSIONS) - set(thresholds.keys())
        if missing:
            raise ValueError(f"thresholds missing dimensions: {sorted(missing)}")
        self.config = config
        self.thresholds = thresholds
        self._lm = dspy.LM(
            config.eval_model, temperature=0.7, cache=False,
            **config.get_lm_kwargs(),
        )
        self.judge = dspy.ChainOfThought(DriftScoreSignature)

    def _check_one_run(self, section_id, original_text, evolved_text):
        try:
            with dspy.context(lm=self._lm):
                result = self.judge(...)
            ...
        except (ValidationError, ValueError, TypeError) as e:
            return ({dim: 0.0 for dim in DRIFT_DIMENSIONS},
                    f"[Parse failure: {type(e).__name__}: {e}]")

    def check(self, section_id, original_text, evolved_text) -> dict:
        runs = []
        for _ in range(3):
            scores, explanation = self._check_one_run(...)
            runs.append(scores)
        per_dim = {}
        for dim in DRIFT_DIMENSIONS:
            raw = [r[dim] for r in runs]
            mean = statistics.mean(raw)
            sd = statistics.stdev(raw)
            exceeded = (mean - sd) > self.thresholds[dim]
            per_dim[dim] = {"mean": ..., "stdev": ..., "exceeded": ..., "raw": ...}
        ...
        return {..., "constraint_result": ConstraintResult(...)}
```

> **Adaptation Delta — 5 个核心偏离点(executor 必读 CONTEXT D-01..D-04 + D-09 + D-15):**
>
> 1. **Constructor 接 `anchor: dict` + `stratified_subset: dict` + (可选)`moving_avg_history: list[dict]`** 取代 thresholds。`anchor` 校验:`set(["anchor_per_tier","dataset_revision_hash","hermes_agent_commit","stratified_subset_seed","calibration_timestamp"]).issubset(anchor.keys())` 失败 → `ValueError`。`anchor["anchor_per_tier"]` 包含 `{"easy","medium","hard","extreme"}` 四 tier(D-CAL-01)。
> 2. **不构造 `dspy.LM` / `dspy.ChainOfThought`** — Phase 20 不调 LLM judge。取而代之构造 `self.runner = TBLiteRunner(config)`。
> 3. **`_check_one_run` 被 subprocess 取代** — Phase 20 调 3 次 `self.runner.run(task_filter=...)`(对应 D-03 3-run median-of-N),每次返回 `TBLiteRunResult` → 按 `result.per_task` 聚合 per-tier pass rate:
>    ```python
>    def _one_run_per_tier_pass_rate(self, run_result: TBLiteRunResult) -> dict[str, float]:
>        by_tier: dict[str, list[bool]] = {t: [] for t in ("easy","medium","hard","extreme")}
>        for task in run_result.per_task:
>            if task.get("error"):  # D-11 infra-fail skip
>                continue
>            tier = task.get("category", "unknown").lower()
>            if tier in by_tier:
>                by_tier[tier].append(bool(task.get("passed", False)))
>        return {t: (sum(v) / len(v) if v else 0.0) for t, v in by_tier.items()}
>    ```
> 4. **`check()` 主循环:Virtual Prompt Overlay → 3 × subprocess → tier-wise σ → Risk_Score**:
>    ```python
>    def check(self, evolved_sections, *, cache_dir=None, use_cache=True) -> dict:
>        # 1. cache lookup (D-15)
>        if use_cache and cache_dir is not None:
>            cache_key = compute_artifact_hash(
>                evolved_sections,
>                self.anchor["dataset_revision_hash"],
>                self.anchor["stratified_subset_seed"],
>            )
>            cache_path = cache_dir / cache_key / "result.json"
>            if cache_path.exists():
>                return json.loads(cache_path.read_text())  # cache hit -> short-circuit
>
>        # 2. Pre-flight checks (D-10 / D-14)
>        self._check_anchor_existence()
>        self._check_overlay_sanity()
>
>        # 3. Virtual Prompt Overlay (D-09)
>        snapshot_path, overlay_path = self._run_overlay(evolved_sections)
>        try:
>            # 4. 3-run subprocess (D-03)
>            per_run_per_tier: list[dict[str, float]] = []
>            for run_idx in range(self.runs):
>                run_result = self.runner.run(
>                    task_filter=self._stratified_task_filter(),
>                    output_dir=Path(...),
>                    runs=1,
>                )
>                per_run_per_tier.append(self._one_run_per_tier_pass_rate(run_result))
>        finally:
>            # 5. ALWAYS restore (D-09 step 5 — even on subprocess hang/error)
>            self._restore_overlay(snapshot_path)
>
>        # 6. Tier-wise 1.96σ + Risk_Score (D-01 / D-02)
>        per_tier_report = self._aggregate_per_tier(per_run_per_tier)  # mean/stdev/threshold/anchor/moving_avg/breach
>        risk_score = self._compute_risk_score(per_tier_report)
>        decision = "reject" if risk_score >= self.reject_threshold else "accept"
>
>        # 7. Build tblite_report.json shape (D-04)
>        report = {
>            "decision": decision,
>            "risk_score": risk_score,
>            "reject_threshold": self.reject_threshold,
>            "tier_weights": self.tier_weights,
>            "per_tier": per_tier_report,
>            "samples_jsonl_path": str(run_result.samples_jsonl_path),
>            "subprocess_runtime_seconds": run_result.subprocess_runtime_seconds * self.runs,
>            "cost_breakdown": run_result.cost_breakdown,
>            "dataset_revision_hash": self.anchor["dataset_revision_hash"],
>            "cache_hit": False,
>            "async_full_verify_pending": False,  # set True by caller after dispatch
>            "constraint_result": ConstraintResult(
>                passed=(decision == "accept"),
>                constraint_name="tblite_benchmark",
>                message=f"Risk_Score={risk_score:.2f} (threshold {self.reject_threshold})",
>                details=json.dumps(per_tier_report, sort_keys=True),
>            ),
>        }
>
>        # 8. Cache write (D-15)
>        if use_cache and cache_dir is not None:
>            (cache_dir / cache_key).mkdir(parents=True, exist_ok=True)
>            (cache_dir / cache_key / "result.json").write_text(
>                json.dumps({k: v for k, v in report.items() if k != "constraint_result"},
>                            indent=2)
>            )
>        return report
>    ```
> 5. **`_compute_risk_score` 算法**(D-02 — 唯一无 analog 的算法,见 §No Analog Found §2):
>    ```python
>    def _compute_risk_score(self, per_tier_report: dict) -> float:
>        risk = 0.0
>        for tier, data in per_tier_report.items():
>            if data.get("breach"):
>                risk += self.tier_weights.get(tier, 1.0)
>        return risk
>    ```
>    语义对应 CONTEXT §specifics:extreme 单 breach (4.0) 单点致命达阈;easy+medium+hard 累积 breach (1.0+1.5+2.0=4.5) 累积失效达阈。

**Virtual Prompt Overlay pattern**(D-09,**无 analog,全新代码**,见 §No Analog Found §3):

```python
def _run_overlay(self, evolved_sections: list) -> tuple[Path, Path]:
    """D-09 Virtual Prompt Overlay (file-level atomic).

    Returns (snapshot_path, overlay_path). os.replace is atomic on POSIX
    when src/dst on same fs (RA1: fs-boundary detection -> fallback to copy).
    """
    from evolution.prompts.prompt_loader import write_back_section  # reuse Phase 7 logic

    target = self.config.hermes_agent_path / "agent" / "prompt_builder.py"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp_dir = Path.home() / ".hermes" / "tmp" / f"benchmark_{ts}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = tmp_dir / "prompt_builder.py.original"
    overlay_path = tmp_dir / "prompt_builder.py.evolved"

    # Step 1: snapshot original
    shutil.copy2(target, snapshot_path)

    # Step 2: build evolved prompt_builder.py at overlay_path
    shutil.copy2(target, overlay_path)
    # bottom-up write_back to preserve line ranges (prompt_loader docstring line 153-155)
    sorted_evolved = sorted(
        evolved_sections, key=lambda s: s.line_range[0], reverse=True,
    )
    # NOTE: write_back_section reads/writes target file in place. To overlay,
    # we temporarily point a working file at overlay_path. Planner Task 1
    # validates whether to (a) parametrize write_back_section with a `dest`
    # arg OR (b) os.replace target<->overlay then write_back then os.replace
    # back. The (b) path requires careful exception handling.

    # Step 3: atomic replace target -> evolved (POSIX rename atomic on same fs)
    same_fs = (target.parent.stat().st_dev == overlay_path.parent.stat().st_dev)
    if same_fs:
        os.replace(overlay_path, target)
    else:
        # RA1 fallback: cross-fs -> shutil.copy2 (NOT atomic, but only window
        # is sub-millisecond inside same dir lock)
        shutil.copy2(overlay_path, target)

    return snapshot_path, overlay_path


def _restore_overlay(self, snapshot_path: Path) -> None:
    """D-09 step 5: ALWAYS restore (even on subprocess hang/error)."""
    target = self.config.hermes_agent_path / "agent" / "prompt_builder.py"
    same_fs = (target.parent.stat().st_dev == snapshot_path.parent.stat().st_dev)
    if same_fs:
        os.replace(snapshot_path, target)
    else:
        shutil.copy2(snapshot_path, target)
```

> **Adaptation Delta:** Virtual Prompt Overlay 是 Phase 20 引入的**第一个 deliberate write-restore 路径**(CONTEXT §Risk Anchors §M6 / Reviewed Todos)。注意:
> - **fs-boundary 检测**(Risk Anchor 1)— `target.parent.stat().st_dev` vs `overlay_path.parent.stat().st_dev` 比较,跨 fs 退化到非原子 copy。planner 须在 PLAN 中说明 fallback 风险窗口(实际 < 1ms,但理论存在)。
> - **`try / finally` 保证 restore**(D-09 step 5)— 即使 TBLite subprocess hang 触发 SIGTERM 也要 restore,否则 hermes-agent 被污染。
> - **复用 `prompt_loader.write_back_section`** — 但该函数当前**只接受 in-place 写**(prompt_loader.py:142-182),Phase 20 需要写到 overlay_path 而非 target。planner Task 1 决策:(a) 扩展 `write_back_section(prompt_builder_path: Path, section, new_text, *, dest: Path = None)`;(b) 临时 `os.replace` swap;(c) 直接复制 `_format_paren_concat` 等私有 helper(prompt_loader.py:187-274)到本文件。**推荐 (a)** — 最小侵入、可测、与 Phase 7 契约兼容。

**Pre-flight overlay sanity check pattern**(D-10):

```python
def _check_overlay_sanity(self) -> None:
    """D-10 Pre-flight: validate hermes-agent + tmp/backups paths writable + clean.

    Raises SystemExit(1) on any failure with a Rich-formatted message.
    """
    import sys

    target = self.config.hermes_agent_path / "agent" / "prompt_builder.py"
    if not os.access(target.parent, os.W_OK):
        console.print(f"[red]hermes-agent path not writable: {target.parent}[/red]")
        sys.exit(1)

    for p in [Path.home() / ".hermes" / "tmp", Path.home() / ".hermes" / "backups"]:
        p.mkdir(parents=True, exist_ok=True)
        if not os.access(p, os.W_OK):
            console.print(f"[red]Not writable: {p}[/red]")
            sys.exit(1)

    # git status --porcelain check (CONCERNS §M6 mitigation)
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(self.config.hermes_agent_path),
        capture_output=True, text=True, timeout=10,
    )
    if res.stdout.strip():
        console.print(
            f"[red]hermes-agent has uncommitted changes — refusing overlay.\n"
            f"Stash or commit first:\n{res.stdout}[/red]"
        )
        sys.exit(1)


def _check_anchor_existence(self) -> None:
    """D-14: validate anchor.hermes_agent_commit matches current HEAD.

    Mismatch on hermes_agent_commit -> hard fail (prompt baseline drift).
    Mismatch on dataset_revision_hash -> warn only (dataset upgrade tolerable).
    """
    import sys

    current_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(self.config.hermes_agent_path),
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    if current_commit != self.anchor.get("hermes_agent_commit"):
        console.print(
            f"[red]Anchor stale: anchor hermes_agent_commit="
            f"{self.anchor.get('hermes_agent_commit', '<missing>')[:8]} but current="
            f"{current_commit[:8]}.\n"
            f"Re-calibrate: python -m evolution.benchmarks.build_tblite_calibration[/red]"
        )
        sys.exit(1)
```

> **Adaptation Delta:** `_check_anchor_existence` 直接 mirror Phase 18 `build_drift_calibration.py:295-309` 的 prompt_builder.py 存在性检查模式(CONTEXT canonical_refs)— 但 anchor stale 校验是 Phase 20 新增。`_check_overlay_sanity` 完全新代码(无 analog),3 个 check 是 Phase 20 第一道 transactional 保证。

**check_all 拼写**(drift_detector.py:237-258 沿用):

```python
def check_all(
    self, original_sections: list, evolved_sections: list,
    *, cache_dir: Path | None = None, use_cache: bool = True,
) -> list[dict]:
    """Sibling of DriftDetector.check_all — but only ONE invocation per evolved batch.

    Phase 20 gate operates on the WHOLE evolved set (not per-section),
    because TBLite measures system-level task pass rate. Returns a single-
    element list to match the Phase 18 pipeline contract for drop-in.
    """
    return [self.check(evolved_sections, cache_dir=cache_dir, use_cache=use_cache)]
```

> **Adaptation Delta:** Phase 18 `DriftDetector.check_all` 每个 section 调一次 `check`;Phase 20 `TBLiteBenchmarkGate.check_all` 整批一次 — 因为 TBLite signal 是系统级 task pass rate,不是 per-section。返回 1-elem list 而非 dict,**仅为了 pipeline drop-in 风格统一**(让 `evolve_prompt_sections.py` 用相同 `for r in gate.check_all(...): ...` 循环结构)。

---

### File 4: `evolution/benchmarks/build_tblite_calibration.py` (NEW)

**Role:** CLI(anchor 校准)— mirror Phase 18 D-CAL-01..05
**Closest analog:** `evolution/prompts/build_drift_calibration.py:1-473`(整文件)
**Match Quality:** exact — Phase 20 此 CLI 与 Phase 18 同构度 ~85%,只换 algorithm body(F1 derivation → 3-run × stratified subset → anchor mean/σ)。

**Interface contract:**
- `@click.command()` `main(...)` → 调内部 `_build_anchor(...)`
- 标准 flags(mirror build_drift_calibration):`--hermes-repo` / `--seed` / `--output-json` / `--model` / `--api-base`
- Phase 20 新增 flags:`--runs` (default 3,D-03) / `--benchmark-max-cost` (default 50.0,D-16) / `--accept-stale-anchor`(辅助 flag,默认 fail 当 hermes_agent_commit 不匹配,planner 可决定是否暴露)
- 输出:`datasets/prompts/tblite_anchor.json`(D-CAL-01 schema 见 CONTEXT §specifics)
- Pre-flight `git status --porcelain` check(D-10,与 BenchmarkGate `_check_overlay_sanity` 共享 helper)

**Imports + CLI skeleton pattern**(完全 mirror build_drift_calibration.py:23-44 + 117-241):

```python
"""Standalone CLI for building the TBLite anchor calibration.

Phase 20 D-13: blocking step before TBLiteBenchmarkGate goes live in
evolve_prompt_sections.py. Pitfall 7 prevention #6: this CLI MUST run
before `python -m evolution.prompts.evolve_prompt_sections --benchmark=tblite`
the first time on a fresh hermes-agent revision.

Usage:
    python -m evolution.benchmarks.build_tblite_calibration \\
        [--hermes-repo PATH] [--seed N] [--runs 3] \\
        [--output-json PATH] [--benchmark-max-cost USD]
"""
import dataclasses
import json
import os
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from evolution.core.config import EvolutionConfig
from evolution.core.cost_tracker import CostTracker, CostBudgetExceeded
from evolution.benchmarks.tblite_runner import TBLiteRunner, TBLITE_RUNNER_VERSION


console = Console()


@click.command()
@click.option("--hermes-repo", default=None, type=click.Path(), ...)
@click.option("--seed", default=42, type=int, ...)
@click.option("--runs", default=3, type=int,
              help="Number of TBLite runs to average for anchor (D-03 median-of-3).")
@click.option(
    "--output-json",
    default=Path("datasets/prompts/tblite_anchor.json"),
    type=click.Path(path_type=Path),
    help="Output path for anchor JSON (git-tracked per D-CAL-02 .gitignore exception).",
)
@click.option("--benchmark-max-cost", default=50.0, type=float,
              help="Phase 20 D-16 dual-track budget for THIS calibration run.")
@click.option("--model", default=None, ...)
@click.option("--api-base", default=None, ...)
def main(hermes_repo, seed, runs, output_json, benchmark_max_cost, model, api_base):
    """Build TBLite anchor + persist datasets/prompts/tblite_anchor.json."""
    console.print("[bold]Phase 20: TBLite anchor calibration[/bold]\n")
    overrides = {}
    if hermes_repo:
        overrides["hermes_repo"] = hermes_repo
    if model:
        overrides["model"] = model
    if api_base:
        overrides["api_base"] = api_base
    config = EvolutionConfig.load(**overrides)

    # 1. Pre-flight (D-10 mirror BenchmarkGate._check_overlay_sanity)
    console.print("\n[bold]1. Pre-flight checks[/bold]")
    _check_hermes_clean(config.hermes_agent_path)  # SystemExit(1) on uncommitted
    current_commit = _git_head(config.hermes_agent_path)
    dataset_revision_hash = _hf_dataset_revision()  # huggingface_hub.HfApi (D-15)

    # 2. Load stratified subset (planner decides where this lives —
    # ship a default datasets/prompts/tblite_stratified_subset.json or
    # generate on first run with seed=42)
    stratified_path = Path("datasets/prompts/tblite_stratified_subset.json")
    if not stratified_path.exists():
        # Generate from TBLite README task list (planner Task 1)
        stratified = _generate_default_stratified(seed=seed)
        stratified_path.write_text(json.dumps(stratified, indent=2, sort_keys=True))
    stratified = json.loads(stratified_path.read_text())

    # 3. Run TBLite N times on stratified subset (D-03)
    runner = TBLiteRunner(config)
    tracker = CostTracker(max_usd=benchmark_max_cost)
    per_run_per_tier: list[dict[str, float]] = []
    with tracker:
        for r in range(runs):
            console.print(f"\n[bold]Run {r+1}/{runs}[/bold]")
            result = runner.run(
                task_filter=stratified["task_filter"],
                output_dir=Path("output/prompts/_calibration") / f"run_{r}",
            )
            per_run_per_tier.append(_one_run_per_tier_pass_rate(result))
            if tracker.exceeded():
                raise CostBudgetExceeded(tracker.spent_usd, tracker.max_usd)

    # 4. Aggregate per-tier mean/σ (mirror Phase 18 _classify_f1_tier table)
    anchor_per_tier: dict[str, dict] = {}
    for tier in ("easy", "medium", "hard", "extreme"):
        scores = [r.get(tier, 0.0) for r in per_run_per_tier]
        anchor_per_tier[tier] = {
            "mean": statistics.mean(scores),
            "stdev": statistics.stdev(scores) if len(scores) > 1 else 0.0,
            "n": runs,
            "scores": scores,
        }

    # 5. Rich Table summary (mirror build_drift_calibration.py:388-417)
    table = Table(title="TBLite Anchor Calibration")
    table.add_column("Tier", style="bold")
    table.add_column("N tasks", justify="right")
    for i in range(runs):
        table.add_column(f"Run {i+1}", justify="right")
    table.add_column("Mean", justify="right")
    table.add_column("Stdev", justify="right")
    for tier in ("easy", "medium", "hard", "extreme"):
        row = [tier, str(stratified["per_tier_counts"].get(tier, 0))]
        for s in anchor_per_tier[tier]["scores"]:
            row.append(f"{s:.3f}")
        row.extend([
            f"{anchor_per_tier[tier]['mean']:.3f}",
            f"{anchor_per_tier[tier]['stdev']:.3f}",
        ])
        table.add_row(*row)
    console.print(table)

    # 6. Persist anchor JSON with metadata (D-CAL-01 schema)
    anchor = {
        "anchor_per_tier": anchor_per_tier,
        "dataset_revision_hash": dataset_revision_hash,
        "hermes_agent_commit": current_commit,
        "stratified_subset_seed": seed,
        "tblite_estimated_cost_per_task_usd": tracker.spent_usd / (
            len(stratified["task_filter"]) * runs
        ),
        "calibration_timestamp": datetime.now(timezone.utc).isoformat(),
        "calibration_model": config.optimizer_model,  # planner verifies
        "tblite_runner_version": TBLITE_RUNNER_VERSION,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(anchor, indent=2, sort_keys=True))
    console.print(f"\n  Wrote {output_json} (cost ${tracker.spent_usd:.2f})")
    console.print("\n[bold green]Anchor calibration complete.[/bold green]")
    console.print("  Next: commit datasets/prompts/tblite_anchor.json to git.")


if __name__ == "__main__":
    main()
```

> **Adaptation Delta vs build_drift_calibration.py — 6 个差异点:**
>
> 1. **不引入 DSPy** — 无 generator(`DriftCalibrationBuilder`)、无 F1 derivation(`derive_thresholds`)、无 LLM judge(`DriftDetector`)。完全基于 TBLite subprocess 二值信号 + statistics 聚合。
> 2. **CostTracker 实际使用**(Phase 18 build_drift_calibration **没有**集成 CostTracker — 仅 stdout 报告预估 cost;Phase 20 必须 enforce `benchmark_max_cost_usd` 因 TBLite Modal compute 单次 $15-40)。Pre-flight Watermark check(D-17)在 `with tracker:` 进入前估算:`watermark = config.tblite_estimated_cost_per_task_usd * len(task_filter) * runs * 3 > benchmark_max_cost` 则 `sys.exit(1)`。
> 3. **Pre-flight `git status --porcelain`**(D-10)— Phase 18 没有(prompt 不 overlay)。Phase 20 calibration 也走 untouched hermes-agent(`evolved_sections=original`),但需要 commit_id 干净便于 anchor 锁定。
> 4. **HuggingFace dataset_revision_hash 获取**(D-15)— `huggingface_hub.HfApi().dataset_info("NousResearch/openthoughts-tblite").sha`。**Risk Anchor 5(HF API 不可用)** — planner 在 PLAN 中决:fail open 跳过 cache fingerprint(anchor 仍可写,标记 `dataset_revision_hash: "unknown_v<TBLITE_RUNNER_VERSION>"`)/ fail closed 拒跑 / fallback 本地 dataset 文件 checksum。推荐 fail open + warn。
> 5. **Rich Table 列数 = 2 + runs + 2**(Tier / N tasks / Run 1..N / Mean / Stdev) vs Phase 18 固定 3 列(Dim / F1 / Status)。
> 6. **不分 Tier 1/2/3 F1 gating** — TBLite 无 F1 概念(binary signal),anchor 始终接受,但 stdev > 0.10 时 Rich warn(planner 决精确阈值)。

**HuggingFace dataset_info helper pattern**(全新代码,Phase 20 第一次使用 `huggingface_hub`):

```python
def _hf_dataset_revision() -> str:
    """D-15 cache fingerprint: read NousResearch/openthoughts-tblite commit sha.

    Risk Anchor 5: graceful fallback to 'unknown_v<runner_version>' on API
    failure (network / rate limit / dataset moved). The fallback STILL
    invalidates cache when TBLITE_RUNNER_VERSION bumps.
    """
    try:
        from huggingface_hub import HfApi
        info = HfApi().dataset_info("NousResearch/openthoughts-tblite")
        return info.sha
    except Exception as e:
        console.print(
            f"[yellow]HuggingFace dataset_info failed ({type(e).__name__}: "
            f"{e}); falling back to 'unknown_v{TBLITE_RUNNER_VERSION}' as "
            f"dataset_revision_hash.[/yellow]"
        )
        return f"unknown_v{TBLITE_RUNNER_VERSION}"
```

> **Adaptation Delta:** `huggingface_hub` 应当通过 DSPy / litellm 间接依赖链已经在 venv 中。planner Task 1 必须 `python -c "import huggingface_hub; print(huggingface_hub.__version__)"` 验证;不在则 fail-open 路径仍可走。

---

### File 5: `evolution/prompts/evolve_prompt_sections.py` (MODIFY)

**Role:** orchestration / pipeline 插桩
**Self-analog locations:** 同文件 step 8c drift gate 块(行 641-750)+ step 11 metrics 字段块(行 1067-1086)+ CLI flag 块(行 1176-1200)— Phase 18 + Phase 19 已建立完整的 gate / metrics / CLI 三段插桩模式,Phase 20 完全同款,差异仅在:
  - 插入位置:Phase 20 插在 **step 10 之后 step 11 之前**(CONTEXT D-18),而 Phase 18 在 step 8b 之后
  - 信号源:Phase 20 是 subprocess 二值信号(`run_result.per_task`),不是 LLM judge dict
  - 失败路径:Phase 20 reject → `FAILED_<ts>/` + 不 write-back(write-back 在 step 11 内,gate 在 step 10.5 拦截整段)

#### Insertion point 1 — Step 10.5 benchmark gate 块

**Insert location:** 在 lines **1021**(step 10 console.print(result_table) 结束)**之后**, **1023**(`# ── 11. Save results ──`)**之前**。

**Anchor — existing step 8c drift gate**(evolve_prompt_sections.py:641-750):

```python
# evolve_prompt_sections.py:641-750 — Phase 18 drift gate (Phase 20 直接同款翻译)
# 8c. Personality drift detection (Phase 18, 3-run averaging per D-ROB-01/04)
console.print("  Running personality drift detection (3-run averaging)...")
drift_thresholds_raw = json.loads(drift_thresholds_path.read_text())
drift_thresholds = {
    d: drift_thresholds_raw[d] for d in DRIFT_DIMENSIONS
}
drift_detector = DriftDetector(config, drift_thresholds)
drift_results = drift_detector.check_all(
    original_sections, evolved_sections,
)

drift_exceeded_dims: list = []
drift_per_dim_metrics: dict = {}
drift_report_lines: list = []

for dr in drift_results:
    all_constraint_results.append(dr["constraint_result"])
    if not dr["constraint_result"].passed:
        all_pass = False
    # ... aggregation, severity-ladder stdout, drift_report.txt build ...
    drift_table.add_row(...)
console.print(drift_table)
```

**Insert delta — Step 10.5(完全新代码,沿用 Phase 18 风格):**

```python
    # ── 10.5. Benchmark gate (Phase 20 D-18) — opt-in, OUT OF GEPA loop ─
    benchmark_results: list = []
    benchmark_decision = "skipped"
    benchmark_risk_score: Optional[float] = None
    benchmark_per_tier: dict = {}

    if benchmark != "none":
        console.print(
            f"\n[bold]Running TBLite benchmark gate (mode={benchmark})[/bold]"
        )
        from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate

        # Load anchor + stratified subset (D-CAL-01 / D-CAL-03)
        anchor = json.loads(
            Path("datasets/prompts/tblite_anchor.json").read_text()
        )
        stratified = json.loads(
            Path("datasets/prompts/tblite_stratified_subset.json").read_text()
        )

        # Filter tiers if --benchmark-tier given (D-05)
        if benchmark_tier:
            stratified = _filter_stratified_by_tier(
                stratified, benchmark_tier.split(",")
            )

        # Load moving_avg_history (D-01)
        history_path = Path("output/prompts/tblite_history.json")
        moving_avg_history = (
            json.loads(history_path.read_text())
            if history_path.exists() else []
        )

        gate = TBLiteBenchmarkGate(
            config,
            anchor=anchor,
            stratified_subset=stratified,
            moving_avg_history=moving_avg_history,
        )

        cache_dir = Path.home() / ".cache" / "hermes-evolution" / "tblite"
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            benchmark_results = gate.check_all(
                original_sections, evolved_sections,
                cache_dir=cache_dir,
                use_cache=benchmark_cache,
            )
        except CostBudgetExceeded as e:
            console.print(f"[red]Benchmark cost budget exceeded: {e}[/red]")
            # write FAILED_<ts>/ with benchmark_decision="aborted_cost"
            _write_failed_aborted(...)
            return

        # Single-element list (TBLiteBenchmarkGate.check_all contract)
        bench = benchmark_results[0]
        benchmark_decision = bench["decision"]
        benchmark_risk_score = bench["risk_score"]
        benchmark_per_tier = bench["per_tier"]

        # Rich Table (mirror drift_table style at line 722-750)
        bench_table = Table(
            title=f"TBLite Benchmark Gate (Risk_Score={benchmark_risk_score:.2f})"
        )
        bench_table.add_column("Tier", style="bold")
        bench_table.add_column("Mean", justify="right")
        bench_table.add_column("Stdev", justify="right")
        bench_table.add_column("Threshold", justify="right")
        bench_table.add_column("Anchor", justify="right")
        bench_table.add_column("MovingAvg", justify="right")
        bench_table.add_column("Breach", justify="center")
        for tier in ("easy", "medium", "hard", "extreme"):
            v = benchmark_per_tier.get(tier, {})
            if not v:
                continue
            breach_icon = "[red]x[/red]" if v.get("breach") else "[green]ok[/green]"
            bench_table.add_row(
                tier,
                f"{v.get('mean', 0):.3f}",
                f"{v.get('stdev', 0):.3f}",
                f"{v.get('threshold', 0):.3f}",
                f"{v.get('anchor', 0):.3f}",
                f"{v.get('moving_avg', 0):.3f}",
                breach_icon,
            )
        console.print(bench_table)

        # Hard reject -> FAILED_<ts>/ (NOT write-back, NOT history ledger)
        if benchmark_decision == "reject":
            console.print(
                f"[red]Benchmark gate REJECTED "
                f"(Risk_Score={benchmark_risk_score:.2f} >= 4.0) -- "
                f"evolved prompts NOT deployed[/red]"
            )
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path("output") / "prompts" / f"FAILED_{timestamp}"
            output_dir.mkdir(parents=True, exist_ok=True)
            failed_metrics = {
                "timestamp": timestamp,
                "status": "FAILED",
                "constraints_passed": False,
                "benchmark_decision": "reject",
                "benchmark_risk_score": benchmark_risk_score,
                "benchmark_per_tier": benchmark_per_tier,
                "benchmark_reason": (
                    f"Risk_Score {benchmark_risk_score:.2f} >= 4.0"
                ),
            }
            (output_dir / "metrics.json").write_text(
                json.dumps(failed_metrics, indent=2)
            )
            (output_dir / "tblite_report.json").write_text(
                json.dumps({k: v for k, v in bench.items()
                             if k != "constraint_result"}, indent=2)
            )
            # Also persist evolved_sections.json + diff.txt for human review
            (output_dir / "evolved_sections.json").write_text(
                json.dumps(
                    [{"section_id": s.section_id, "text": s.text}
                     for s in evolved_sections],
                    indent=2,
                )
            )
            (output_dir / "diff.txt").write_text(
                _generate_diff(original_sections, evolved_sections)
            )
            console.print(f"  Saved failed results to {output_dir}/")
            return
```

> **Adaptation Delta vs analog:** 完全沿用 Phase 18 step 8c 模式 — `console.print` + `json.loads(path.read_text())` 加载 anchor/stratified + Rich Table + `FAILED_<ts>/` 落盘三段。区别:
> - **Anchor / stratified 是从 git-tracked JSON 加载,不调 LLM**(Phase 18 是 `dspy.LM` + `dspy.ChainOfThought`)
> - **Risk_Score reject 直接 `return`**(Phase 18 是 push to `all_constraint_results` + `all_pass = False`)— 因为 gate 在 step 10 之后,write-back 在 step 11 内,直接 return 即等同 reject(不修改 hermes-agent)。`return` 前必须写 `FAILED_<ts>/metrics.json` + `tblite_report.json`(D-04)。
> - **新增 async full verify 启动**(D-07):accept 路径在 step 11 之后插 `_start_async_full_verify(output_dir, ...)` 调用,detached subprocess + `.benchmark_full_running.pid` 锁(CONTEXT §specifics)。

#### Insertion point 2 — Step 11 metrics.json benchmark_* 字段

**Anchor — existing step 11 metrics dict + drift block**(evolve_prompt_sections.py:1045-1089):

```python
# evolve_prompt_sections.py:1045-1089 (existing — Phase 18 drift block 已写完整)
metrics = {
    "timestamp": timestamp,
    "mode": effective_mode,
    "iterations": iterations,
    "eval_model": config.eval_model,
    "baseline_score": baseline_score,
    "evolved_score": evolved_score,
    "improvement": improvement,
    ...
    "constraints_passed": True,
}
if effective_mode == "joint" and roundrobin_baseline_score is not None:
    metrics["joint_score"] = evolved_score
    ...
# Phase 18 / D-OUT-02 + D-ROB-04: drift_* fields written UNCONDITIONALLY
if drift_results:
    metrics["drift_per_dim"] = drift_per_dim_metrics
    metrics["drift_thresholds"] = drift_thresholds
    metrics["drift_exceeded_dims"] = drift_exceeded_dims
    metrics["drift_passed"] = drift_passed
    ...
(output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
```

**Insert delta — 在 `if drift_results:` 块之后, `(output_dir / "metrics.json").write_text(...)` 之前**(D-04 + D-16):

```python
    # Phase 20 / D-04: benchmark_* fields (always present, "skipped" when not run)
    metrics["benchmark_decision"] = benchmark_decision  # accept | reject | skipped
    if benchmark_results:
        metrics["benchmark_passed"] = (benchmark_decision == "accept")
        metrics["benchmark_risk_score"] = benchmark_risk_score
        metrics["benchmark_per_tier"] = benchmark_per_tier
    # D-16 dual-track cost breakdown
    metrics["total_cost_breakdown"] = {
        "optimization": optimization_tracker.spent_usd,
        "benchmark": benchmark_tracker.spent_usd if benchmark != "none" else 0.0,
    }

    # Also persist tblite_report.json side-by-side (D-04 schema)
    if benchmark_results:
        (output_dir / "tblite_report.json").write_text(
            json.dumps(
                {k: v for k, v in benchmark_results[0].items()
                 if k != "constraint_result"},
                indent=2,
            )
        )
```

> **Adaptation Delta:** 完全沿用 Phase 18 `if drift_results: metrics[...] = ...` 风格;`benchmark_decision: "skipped"` 默认写入(即使 `--benchmark=none`)便于 Phase 16 dashboard 按字段筛选(D-04 + CONTEXT §Deferred Ideas Phase 16 dashboard 接入)。**新增 `total_cost_breakdown`** dict — Phase 13 `max_cost_usd` 之后第一次写双轨账单字段。

#### Insertion point 3 — `evolve()` 函数签名 + CLI flags

**Anchor — existing evolve() signature**(evolve_prompt_sections.py:188-199):

```python
def evolve(
    section: Optional[str] = None,
    iterations: int = 10,
    eval_source: str = "synthetic",
    hermes_repo: Optional[str] = None,
    dry_run: bool = False,
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    mode: str = "joint",
    drift_thresholds_path: Path = Path("datasets/prompts/drift_thresholds.json"),
    session_source: Optional[Path] = None,
):
```

**Insert delta — 在 `session_source` 之后追加 Phase 20 参数**:

```python
def evolve(
    section: Optional[str] = None,
    iterations: int = 10,
    ...
    session_source: Optional[Path] = None,
    # Phase 20 D-12 + D-15 + D-16
    benchmark: str = "none",                # none | tblite | tblite-full
    benchmark_tier: Optional[str] = None,    # CSV: "easy,medium,hard,extreme"
    benchmark_cache: bool = True,
    benchmark_max_cost: float = 50.0,
    wait_mode: str = "wait",                 # wait | detach
    async_full_verify: bool = True,
):
```

**Anchor — existing CLI flag block**(evolve_prompt_sections.py:1176-1200,`--drift-thresholds-path` + `--session-source`):

```python
@click.option(
    "--drift-thresholds-path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("datasets/prompts/drift_thresholds.json"),
    help=("Path to drift_thresholds.json ..."),
)
@click.option(
    "--session-source",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help=("Phase 19 D-21. ..."),
)
```

**Insert delta — Phase 20 CLI flags**(CONTEXT §specifics §Click CLI 新增 flags):

```python
@click.option(
    "--benchmark",
    type=click.Choice(["none", "tblite", "tblite-full"]),
    default="none",
    help=(
        "Phase 20 D-18. Run TBLite benchmark gate after step 10 (out of "
        "GEPA loop, PITFALL #7). 'none' = pre-Phase-20 behavior (default). "
        "'tblite' = stratified 30-task subset. 'tblite-full' = 100-task "
        "(use with --detach for background)."
    ),
)
@click.option(
    "--benchmark-tier",
    default=None,
    help=(
        "CSV of tiers to include (subset of easy,medium,hard,extreme). "
        "Default = all four. Phase 20 D-05."
    ),
)
@click.option(
    "--benchmark-cache/--no-benchmark-cache",
    default=True,
    help=(
        "Content-addressed cache at ~/.cache/hermes-evolution/tblite/ "
        "(Phase 20 D-15). Disable for a single forced re-run."
    ),
)
@click.option(
    "--benchmark-max-cost",
    default=50.0,
    type=float,
    help=(
        "USD cap for the benchmark cost tracker (Phase 20 D-16 dual-track). "
        "Distinct from --max-cost-usd which governs GEPA + LLM judge."
    ),
)
@click.option(
    "--wait/--detach",
    default=True,
    help=(
        "Phase 20 D-12. --wait blocks until TBLite subprocess exits then "
        "decides write-back. --detach returns immediately with a "
        "benchmark_run_id; resolve later via --check-benchmark <ts>."
    ),
)
@click.option(
    "--async-full-verify/--no-async-full-verify",
    default=True,
    help=(
        "Phase 20 D-07. After accept + write-back, fire-and-forget a "
        "detached full 100-task run. --no- to disable."
    ),
)
def main(section, iterations, eval_source, hermes_repo, dry_run,
         model, api_base, mode, drift_thresholds_path, session_source,
         benchmark, benchmark_tier, benchmark_cache, benchmark_max_cost,
         wait, async_full_verify):
    evolve(
        section=section,
        iterations=iterations,
        ...,
        drift_thresholds_path=drift_thresholds_path,
        session_source=session_source,
        benchmark=benchmark,
        benchmark_tier=benchmark_tier,
        benchmark_cache=benchmark_cache,
        benchmark_max_cost=benchmark_max_cost,
        wait_mode="wait" if wait else "detach",
        async_full_verify=async_full_verify,
    )
```

> **Adaptation Delta:** 全部 6 个 flags 严格 mirror Phase 18 `--drift-thresholds-path` + Phase 19 `--session-source` 句法 — `click.Choice` / `default` / 多行 `help` / `boolean toggle pair`(`--benchmark-cache/--no-benchmark-cache`)。**故意不加** `--no-benchmark` bypass flag — D-BYPASS-01 / CONTEXT §Out of Scope:`--benchmark=none` 默认 OFF 即为天然 bypass,无须双重 flag。

#### Insertion point 4 — Click subcommands(D-12 / D-07 / D-08)

**Anchor — Phase 19 已有 `mine_prompt_sessions.py` 独立 CLI 模式;Phase 20 选择 click subcommands 而非独立 CLI 文件**(CONTEXT §Discretion 第 7 项)。

**Insert delta — 在主 `main` 之外新增 3 个 subcommand**(planner 决:是否拆成独立 click group):

```python
@click.command(name="check-benchmark")
@click.argument("timestamp", type=str)
def check_benchmark(timestamp: str):
    """D-07/D-12: resolve a --detach benchmark run.

    Reads output/prompts/<ts>/.pending_gate.json + .benchmark_full_running.pid,
    polls subprocess liveness via os.kill(pid, 0), invokes gate.check() once
    samples.jsonl is complete, writes metrics.json + tblite_report.json or
    falls back to FAILED_<ts>/.
    """
    ...


@click.command(name="restore")
@click.argument("timestamp", type=str)
def restore(timestamp: str):
    """D-08: restore from ~/.hermes/backups/<ts>/ snapshot."""
    ...


@click.command(name="confirm-rollback")
@click.argument("timestamp", type=str)
def confirm_rollback(timestamp: str):
    """D-08: confirm a Soft-Rollback as permanent."""
    ...
```

> **Adaptation Delta:** Phase 20 是项目里第一次引入 `click.command` subcommand 集合(此前所有 CLI 是单 command + flags)。planner 在 PLAN 中决:
> (a) `click.Group` 模式 — 改 main 为 group + 4 子命令(`evolve` / `check-benchmark` / `restore` / `confirm-rollback`);**破坏向后兼容**(`python -m evolution.prompts.evolve_prompt_sections --section X` 失效)。
> (b) `--check-benchmark <ts>` 作 flag,主 main 内分支处理 — **保留向后兼容**,但 main 体增大。**推荐 (b)**。
> 三个 subcommands 内部都调入 `output/prompts/<ts>/` 目录读 `.pending_gate.json` / `metrics.json` 状态机。

---

### File 6: `evolution/core/config.py` (MODIFY)

**Role:** config — 新增 `benchmark_max_cost_usd` + `tblite_estimated_cost_per_task_usd` 等字段
**Closest analog:** 同文件 `max_cost_usd: float = 20.0` 字段(config.py:57-59,Phase 13 引入)+ `run_tblite: bool = False` 字段(config.py:67-70)
**Interface contract:**
- 4 个新字段(D-16 / D-17):`benchmark_max_cost_usd: float = 50.0`、`tblite_estimated_cost_per_task_usd: float = 0.4`、`benchmark_runs: int = 3`、`benchmark_heartbeat_seconds: int = 60`
- 加入 `EvolutionConfig.load()` 的 3-tier override 链(YAML < env < CLI)— Phase 13 `max_cost_usd` 已建立模板,Phase 20 完全 1:1 复制

**Anchor — existing `max_cost_usd` field + YAML/env override**(config.py:57-59 + 122-134 + 151-161 + 179-190):

```python
# config.py:57-59 (field declaration)
# Cost cap for GEPA compile + eval (D-13 / folded todo 2026-05-07-max-cost-usd-and-reflection-model.md)
# USD; enforced by evolution/core/cost_tracker.py. Set <= 0 to disable (not recommended).
max_cost_usd: float = 20.0

# config.py:122-134 (YAML override)
# Phase 13: max_cost_usd is a top-level yaml key
if data.get("max_cost_usd") is not None:
    try:
        config.max_cost_usd = float(data["max_cost_usd"])
    except (TypeError, ValueError):
        sys.stderr.write(
            f"⚠️  evolution.yaml max_cost_usd="
            f"{data['max_cost_usd']!r} is not a number; "
            f"falling back to default {config.max_cost_usd}.\n"
        )

# config.py:151-161 (env override)
env_cost = os.getenv("EVOLUTION_MAX_COST_USD")
if env_cost:
    try:
        config.max_cost_usd = float(env_cost)
    except ValueError:
        sys.stderr.write(
            f"⚠️  EVOLUTION_MAX_COST_USD={env_cost!r} is not a "
            f"number; keeping previous value "
            f"{config.max_cost_usd}.\n"
        )

# config.py:179-190 (CLI override)
if overrides.get("max_cost_usd") is not None:
    try:
        config.max_cost_usd = float(overrides["max_cost_usd"])
    except (TypeError, ValueError):
        sys.stderr.write(...)
```

**Insert delta — 4 个新字段 + 完整 override 链**:

```python
# config.py 新增字段 — 紧贴 max_cost_usd 之后
# Phase 20 D-16: dual-track benchmark cost cap (independent from GEPA max_cost_usd)
benchmark_max_cost_usd: float = 50.0
# Phase 20 D-17: per-task LLM cost estimate (calibration refreshes this)
tblite_estimated_cost_per_task_usd: float = 0.4
# Phase 20 D-03: 3-run averaging in benchmark gate
benchmark_runs: int = 3
# Phase 20 D-11: subprocess heartbeat detection
benchmark_heartbeat_seconds: int = 60

# YAML override block — 紧贴 max_cost_usd 之后
if data.get("benchmark_max_cost_usd") is not None:
    try:
        config.benchmark_max_cost_usd = float(data["benchmark_max_cost_usd"])
    except (TypeError, ValueError):
        sys.stderr.write(
            f"⚠️  evolution.yaml benchmark_max_cost_usd="
            f"{data['benchmark_max_cost_usd']!r} is not a number; "
            f"falling back to default {config.benchmark_max_cost_usd}.\n"
        )
# ... 3 more identical blocks for tblite_estimated_cost_per_task_usd,
#     benchmark_runs, benchmark_heartbeat_seconds

# env override block — 紧贴 EVOLUTION_MAX_COST_USD 之后
env_bench_cost = os.getenv("EVOLUTION_BENCHMARK_MAX_COST_USD")
if env_bench_cost:
    try:
        config.benchmark_max_cost_usd = float(env_bench_cost)
    except ValueError:
        sys.stderr.write(...)
# ... env keys: EVOLUTION_TBLITE_COST_PER_TASK_USD / EVOLUTION_BENCHMARK_RUNS /
#               EVOLUTION_BENCHMARK_HEARTBEAT_SECONDS

# CLI override block — 紧贴 max_cost_usd CLI override 之后
if overrides.get("benchmark_max_cost_usd") is not None:
    try:
        config.benchmark_max_cost_usd = float(overrides["benchmark_max_cost_usd"])
    except (TypeError, ValueError):
        sys.stderr.write(...)
# ... 3 more
```

> **Adaptation Delta:** 完全 1:1 复制 Phase 13 `max_cost_usd` 的 4 个块结构(declaration / YAML / env / CLI)— 仅换字段名 + env 前缀。**注意:** `tblite_estimated_cost_per_task_usd` 实测回写策略(CONTEXT §Discretion 第 10 项)— planner 在 PLAN 中决:每次 `build_tblite_calibration` 完成后是否回写 `evolution.yaml`(自动)还是仅写入 `tblite_anchor.json._meta`(手动 ops);**推荐后者**,避免自动改用户配置文件。

---

### File 7: `evolution/core/cost_tracker.py` (READ-ONLY / 实例化)

**Role:** utility(不修改 — Phase 20 实例化 2 个 CostTracker)
**Closest analog:** 自身 — 已是产品代码(Phase 13 D-13 引入)
**Match Quality:** direct-reuse

**Usage pattern in Phase 20**(evolve_prompt_sections.py step 10.5 + build_tblite_calibration.py):

```python
# evolve_prompt_sections.py — dual-tracker instantiation
from evolution.core.cost_tracker import CostTracker, CostBudgetExceeded

# Step 1: optimization tracker (existing — wraps GEPA + LLM judge)
optimization_tracker = CostTracker(max_usd=config.max_cost_usd)

# Step 10.5: benchmark tracker (Phase 20 new)
benchmark_tracker = CostTracker(max_usd=config.benchmark_max_cost_usd)

# Tracker contexts can be entered SEPARATELY (NOT nested) — DSPy
# track_usage() is global so nesting two CostTrackers double-counts.
with optimization_tracker:
    # ... GEPA compile (steps 6-9) ...
    pass

with benchmark_tracker:
    # ... TBLite subprocess + scoring (step 10.5) ...
    pass
```

> **Adaptation Delta:** **不修改 cost_tracker.py** 但在 evolve_prompt_sections.py 内 instantiate 2 个 — 关键约束是**两个 context manager 不可嵌套**(CONTEXT §code_context Reusable Assets §`CostTracker`)。planner 在 PLAN 中明确:GEPA optimize 步段 enter optimization_tracker,exit 后再 enter benchmark_tracker;两 spent_usd 写入 `metrics["total_cost_breakdown"]`(D-16)。

---

### File 8: `datasets/prompts/tblite_anchor.json` (NEW — persistent artifact)

**Role:** persistent artifact(anchor + dataset_revision_hash + hermes_agent_commit metadata,git-tracked)
**Closest analog:** `datasets/prompts/drift_thresholds.json`(Phase 18 D-CAL-02 git exception 落盘模式)
**Schema**(CONTEXT §specifics):

```json
{
  "anchor_per_tier": {
    "easy":    {"mean": 0.85, "stdev": 0.02, "n": 3, "scores": [0.83, 0.86, 0.86]},
    "medium":  {"mean": ..., ...},
    "hard":    {"mean": ..., ...},
    "extreme": {"mean": ..., ...}
  },
  "dataset_revision_hash": "abc123...",
  "hermes_agent_commit": "def456...",
  "stratified_subset_seed": 42,
  "tblite_estimated_cost_per_task_usd": 0.4,
  "calibration_timestamp": "2026-05-19T10:00:00Z",
  "calibration_model": "anthropic/claude-opus-4.6",
  "tblite_runner_version": "1.0"
}
```

**Interface contract:** 由 `python -m evolution.benchmarks.build_tblite_calibration` 生成;`TBLiteBenchmarkGate.__init__` 通过 `json.loads(path.read_text())` 加载并 `_check_anchor_existence` 校验。

> **Adaptation Delta vs Phase 18 drift_thresholds.json:**
> - **顶层无 `_meta` 块** — Phase 20 把 metadata flatten 到顶层(`dataset_revision_hash` / `hermes_agent_commit` / `seed` 等),因 `TBLiteBenchmarkGate` 直接消费这些字段而非 ignore。`anchor_per_tier` 嵌套是 Phase 18 没有的(因 anchor 是 per-tier 4 个 mean/σ 而非 per-dim 4 个 scalar threshold)。
> - **必须 commit 到 git** — `.gitignore` exception 见 File 10。schema 必须 `json.dumps(..., indent=2, sort_keys=True)` 以最小化 diff(Phase 18 模式)。

---

### File 9: `datasets/prompts/tblite_stratified_subset.json` (NEW — persistent artifact)

**Role:** persistent artifact(30-task 白名单 + seed,git-tracked)
**Closest analog:** 同上 `tblite_anchor.json`
**Schema**(planner Task 1 验证 task name 格式):

```json
{
  "seed": 42,
  "per_tier_counts": {"easy": 12, "medium": 8, "hard": 7, "extreme": 3},
  "task_filter": [
    "broken-python",
    "pandas-etl",
    "task-XYZ-easy-1",
    "..."
  ],
  "source": "NousResearch/openthoughts-tblite",
  "generated_timestamp": "2026-05-19T..."
}
```

**Interface contract:** 由 `build_tblite_calibration` 首次运行时生成(若不存在);`TBLiteBenchmarkGate` 通过 `json.loads(...)` 加载,`task_filter` 字段透传给 `TBLiteRunner.run(task_filter=...)`。

> **Adaptation Delta:** task name 选择策略(CONTEXT §Discretion 第 5 项)— planner 在 Task 1 spike 后决定;选每 tier 最具区分度的 N 个 task(reference pass rate 分桶取中位数附近)。`seed=42` 是 Phase 18 D-CAL-01 沿用约定。

---

### File 10: `.gitignore` (MODIFY)

**Role:** gitignore mod — 给 tblite_anchor + stratified_subset 加 git-track exception;新增 `logs/` ignore
**Closest analog:** Phase 18 `!datasets/prompts/drift_*` exception(.gitignore:20-23)+ 现有 `output/`(.gitignore:30)

**Anchor — existing Phase 18 exception block**(.gitignore:16-23):

```gitignore
# Generated eval datasets (local, not shared)
datasets/**/*.jsonl
datasets/**/*.json
!datasets/.gitkeep
# Phase 18: drift calibration assets are stable evaluation artifacts (golden-set-like),
# tracked in git so threshold derivation is reproducible across machines / recals.
!datasets/prompts/drift_calibration.jsonl
!datasets/prompts/drift_thresholds.json
```

**Insert delta — 在 Phase 18 exception 块之后追加 2 行 + 末尾增 `logs/` ignore**(D-CAL-02 + D-08):

```gitignore
# Phase 20: TBLite benchmark anchor + stratified subset (golden-set-like, git-tracked)
!datasets/prompts/tblite_anchor.json
!datasets/prompts/tblite_stratified_subset.json
```

**追加到文件末尾**(在 `*.swo` 之后):

```gitignore

# Phase 20 Soft-Rollback regression audit log (D-08)
logs/
```

> **Adaptation Delta:** 严格沿用 Phase 18 `!datasets/.gitkeep` 和 `!datasets/prompts/drift_*` 句法。**顺序很关键**:`!` exception 必须在原 `datasets/**/*.json` ignore 之后(.gitignore 顺序敏感)— 追加到 Phase 18 块之后正好满足。`logs/` ignore 是新增 — Phase 20 是首次落 `logs/` 目录(D-08 `logs/regression.jsonl`),`output/` 已 ignored 但 `logs/` 独立。

---

### File 11: `tests/benchmarks/__init__.py` (NEW)

**Role:** test package init
**Closest analog:** `tests/prompts/__init__.py` / `tests/tools/__init__.py`(空文件)
**Interface contract:** 单纯空文件,让 pytest discovery 找到 `tests/benchmarks/` 子树

```python
# tests/benchmarks/__init__.py — empty package marker
```

---

### File 12: `tests/benchmarks/test_tblite_runner.py` (NEW)

**Role:** test scaffold(单元 — mock subprocess + parse samples.jsonl)
**Closest analog:** `tests/prompts/test_drift_detector.py:1-198`(典型 mock LM + fake section + helper 函数拓扑)
**Match Quality:** partial(测试拓扑沿用,mock 对象是 `subprocess.Popen` 而非 `dspy.LM`)

**Interface contract** — 测试场景(per CONTEXT §In scope + §Risk Anchors):
- `test_popen_args_constructed` — `TBLiteRunner.run(task_filter=["X","Y"])` 时 `subprocess.Popen` 接收正确的 args(`cd hermes_agent_path; python tblite_env.py evaluate --env.task_filter X,Y ...`)
- `test_stream_pipe_parses_pass_fail_markers` — mock stdout yield `[PASS]task1\n[FAIL]task2\n` → runner 解析并更新 Rich progress
- `test_heartbeat_timeout_triggers_hang` — mock subprocess that never writes stdout → `queue.Empty` 触发 `hang_count++` → max 3 后 `proc.terminate()` 调用 + `result.status == "hang_timeout"`
- `test_samples_jsonl_per_task_parse` — 写一个 fake `samples_<ts>.jsonl` 文件 → `result.per_task` 正确填充 + `category` 字段映射 tier
- `test_jsonl_skip_bad_lines` — 写 fake jsonl 含 1 行 malformed → `result.jsonl_skipped_lines == 1`,其余条目仍解析(Phase 19 D-24 模式)
- `test_infra_failure_marked_separately` — fake samples.jsonl 含 `{"passed": false, "error": "Modal timeout"}` → 该条目 `infra_fail` flag(不计入 Risk_Score 后续计算)
- `test_cache_key_deterministic` — `compute_artifact_hash` 对同一 evolved_sections + dataset_hash + seed 返回稳定值;改 1 个字段 → hash 变

**Helper pattern**(test_drift_detector.py:19-39 沿用):

```python
"""RED tests for TBLiteRunner (Phase 20).

Tests use unittest.mock to stub subprocess.Popen — no real TBLite invocation.
"""
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evolution.core.config import EvolutionConfig


def _make_runner(tmp_hermes_path: Path):
    """Helper: TBLiteRunner with fake hermes path."""
    config = EvolutionConfig.__new__(EvolutionConfig)
    config.hermes_agent_path = tmp_hermes_path
    config.tblite_estimated_cost_per_task_usd = 0.4
    from evolution.benchmarks.tblite_runner import TBLiteRunner
    return TBLiteRunner(config)


class TestTBLiteRunner:
    def test_popen_args_constructed(self, tmp_path):
        runner = _make_runner(tmp_path)
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value.stdout = iter(["[PASS]task1\n", ""])
            mock_popen.return_value.stderr = iter([""])
            mock_popen.return_value.poll.return_value = 0
            mock_popen.return_value.returncode = 0
            mock_popen.return_value.wait.return_value = 0
            # ... runner.run(["task1"], tmp_path / "out") ...
            args, kwargs = mock_popen.call_args
            assert "evaluate" in args[0]
            assert kwargs["cwd"] == str(tmp_path)
            assert kwargs["text"] is True
```

> **Adaptation Delta vs test_drift_detector.py:** mock 对象从 `dspy.LM` 改成 `subprocess.Popen`;helper `_make_detector` → `_make_runner`;`thresholds` arg 改成 `tmp_hermes_path`(fixture)。`patch("subprocess.Popen")` 必须返回 MagicMock with `stdout` / `stderr` 是 iterable(`_pump_stream` 用 `iter(stream.readline, "")` 消费)+ `poll()` / `wait()` / `returncode` 三 mock。

---

### File 13: `tests/benchmarks/test_benchmark_gate.py` (NEW)

**Role:** test scaffold(单元 — Risk_Score 算法 + 1.96σ 决策 + Virtual Prompt Overlay)
**Closest analog:** `tests/prompts/test_drift_detector.py:1-198`(severity ladder 三分支测试)+ `tests/prompts/test_drift_calibration.py:1-139`(算法边界测试)
**Match Quality:** exact

**Interface contract** — 测试场景:
- `test_risk_score_extreme_single_breach_rejects` — 单 extreme breach (weight 4.0) → Risk_Score=4.0 → reject
- `test_risk_score_cumulative_low_tier_rejects` — easy+medium+hard 全 breach (1+1.5+2 = 4.5) → reject
- `test_risk_score_below_threshold_accepts` — easy+medium breach (1+1.5 = 2.5) → accept
- `test_anchor_existence_check_stale_commit_fails` — mock hermes-agent commit ≠ anchor.hermes_agent_commit → SystemExit(1)
- `test_overlay_sanity_check_dirty_git_fails` — mock `git status --porcelain` 非空 → SystemExit(1)
- `test_atomic_replace_fs_boundary_fallback` — mock `Path.stat().st_dev` 跨 fs → 走 `shutil.copy2` fallback path
- `test_restore_overlay_called_on_subprocess_error` — TBLiteRunner.run raises → `_restore_overlay` 仍被调用(`try/finally` 保证)
- `test_cache_hit_short_circuits_subprocess` — 预写 `cache_dir/<hash>/result.json` → `TBLiteBenchmarkGate.check` 不调 runner.run
- `test_cache_key_uses_dataset_revision_hash` — 改 anchor.dataset_revision_hash → cache key 变 → cache miss
- `test_moving_avg_falls_back_to_anchor_on_first_run` — `moving_avg_history=[]` → 退化 `moving_avg = anchor`(D-01)
- `test_per_tier_threshold_computed_with_z_1_96` — 给定 anchor mean=0.85, stdev=0.02, candidate stdev=0.01 → threshold = max(0.85, moving_avg) - 1.96 * 0.01 = 0.8304
- `test_infra_fail_skipped_in_pass_rate` — `samples.jsonl` 含 `error` 字段 task → 该 task 不计入 tier pass rate 分母

**Test helper pattern**(test_drift_detector.py:35-39 + test_drift_calibration.py 类似 fake fixture):

```python
class _FakeSection:
    def __init__(self, section_id, text, line_range=(1, 1), source_path=Path("/")):
        self.section_id = section_id
        self.text = text
        self.line_range = line_range
        self.source_path = source_path


def _make_anchor(easy=0.85, medium=0.7, hard=0.5, extreme=0.3, stdev=0.02):
    return {
        "anchor_per_tier": {
            "easy":    {"mean": easy, "stdev": stdev, "n": 3, "scores": [easy]*3},
            "medium":  {"mean": medium, "stdev": stdev, "n": 3, "scores": [medium]*3},
            "hard":    {"mean": hard, "stdev": stdev, "n": 3, "scores": [hard]*3},
            "extreme": {"mean": extreme, "stdev": stdev, "n": 3, "scores": [extreme]*3},
        },
        "dataset_revision_hash": "test_hash",
        "hermes_agent_commit": "test_commit",
        "stratified_subset_seed": 42,
        "tblite_estimated_cost_per_task_usd": 0.4,
        "calibration_timestamp": "2026-05-19T00:00:00Z",
        "calibration_model": "test/model",
        "tblite_runner_version": "1.0",
    }


def _make_run_result(per_task_passed: dict[str, dict[str, bool]]):
    """Build a fake TBLiteRunResult from {tier: {task_name: passed_bool}}."""
    from evolution.benchmarks.tblite_runner import TBLiteRunResult
    per_task = []
    for tier, tasks in per_task_passed.items():
        for name, passed in tasks.items():
            per_task.append({
                "task_name": name,
                "category": tier,
                "passed": passed,
            })
    return TBLiteRunResult(per_task=per_task, status="ok")
```

> **Adaptation Delta vs test_drift_detector.py:** `_FakeSection` 同 Phase 18(已含 `line_range` / `source_path` 因 Phase 20 Virtual Prompt Overlay 走 prompt_loader.write_back_section);`_make_anchor` / `_make_run_result` 全新 — Phase 20 测试不 mock LLM 调用,改为 mock `TBLiteRunner.run(...)` 返回固定 `TBLiteRunResult`(`patch.object(gate, "runner")`)。`_check_overlay_sanity` 测试必须 mock `subprocess.run`(`git status --porcelain`)而非 LLM。

---

### File 14: `tests/benchmarks/test_build_tblite_calibration.py` (NEW)

**Role:** test scaffold(CLI 单元)
**Closest analog:** `tests/prompts/test_drift_calibration.py:1-139`(Phase 18 build_drift_calibration 单元测) + Phase 18 CliRunner pattern

**Interface contract** — 测试场景:
- `test_anchor_json_schema_complete` — CLI 写出的 JSON 顶层有所有 D-CAL-01 schema 必备 keys
- `test_seed_is_persisted` — `--seed 7` → `anchor["stratified_subset_seed"] == 7`
- `test_huggingface_fallback_on_api_error` — `HfApi().dataset_info` raise → `anchor["dataset_revision_hash"] == "unknown_v1.0"`
- `test_git_dirty_check_blocks_calibration` — mock `git status --porcelain` 非空 → CliRunner exit_code != 0
- `test_pre_flight_watermark_blocks_when_insufficient_budget` — `--benchmark-max-cost 5.0` with estimated 30 task × 3 run × $0.4 = $36 → SystemExit(1) before subprocess

**CliRunner pattern**(test_drift_calibration.py CLI 测试沿用):

```python
from click.testing import CliRunner
from unittest.mock import patch


def test_anchor_json_schema_complete(tmp_path):
    runner = CliRunner()
    with patch(
        "evolution.benchmarks.build_tblite_calibration.TBLiteRunner"
    ) as mock_runner_cls, patch(
        "evolution.benchmarks.build_tblite_calibration._hf_dataset_revision",
        return_value="abc123",
    ), patch(
        "evolution.benchmarks.build_tblite_calibration._git_head",
        return_value="def456",
    ):
        mock_runner_cls.return_value.run.return_value = _make_run_result({
            "easy": {"t1": True, "t2": True},
            "medium": {"t3": True},
            "hard": {"t4": False},
            "extreme": {"t5": True},
        })
        from evolution.benchmarks.build_tblite_calibration import main
        result = runner.invoke(main, [
            "--hermes-repo", str(tmp_path / "hermes"),
            "--seed", "42",
            "--output-json", str(tmp_path / "anchor.json"),
            "--runs", "1",
            "--benchmark-max-cost", "100",
        ])
        assert result.exit_code == 0, result.output
        anchor = json.loads((tmp_path / "anchor.json").read_text())
        for k in ("anchor_per_tier", "dataset_revision_hash",
                   "hermes_agent_commit", "stratified_subset_seed",
                   "calibration_timestamp"):
            assert k in anchor
```

> **Adaptation Delta:** 完全沿用 Phase 18 CliRunner pattern;`TBLiteRunner` 必须 patch(测试不能调真 subprocess);`_hf_dataset_revision` + `_git_head` 也 patch(单元测无网络/git 假设)。

---

## Shared Patterns

### Shared Pattern 1: Click + Rich + git-tracked JSON anchor CLI(Phase 18 D-CAL-01..05 三件套)

**Source:** `evolution/prompts/build_drift_calibration.py:1-473`(整文件,Phase 18 CLI 模板)
**Apply to:** `evolution/benchmarks/build_tblite_calibration.py`(File 4)

**Key contract elements:**
- Module docstring 给 `Usage:` 块 + `Phase X D-CAL-0X` 引用
- `@click.option` 参数集合至少包含:`--hermes-repo` / `--seed` / `--output-json` / `--model` / `--api-base`
- `console.print` `[bold]N. Step name[/bold]` 编号 step 风格(build_drift_calibration:243, 295, 313, 348, 363, 371, 440)
- Rich `Table` 输出 anchor / threshold 表格(build_drift_calibration:388-417)
- `json.dumps(anchor_with_meta, indent=2, sort_keys=True)` 落盘(build_drift_calibration:461-463)
- `console.print("\n[bold green]X complete.[/bold green]")` + "Next: ..." 提示(build_drift_calibration:465-469)

> **Phase 20 augmentation:** 加 `CostTracker` enter/exit(Phase 18 没有);加 HuggingFace API 调用 + fail-open(Phase 18 没有);Rich Table 列动态 by `--runs`。

### Shared Pattern 2: `check_all` 接口 + `ConstraintResult` 嵌套 dict(Phase 18 D-OUT-02)

**Source:** `evolution/prompts/drift_detector.py:237-258` (`DriftDetector.check_all` 返回 `list[dict]` with `constraint_result: ConstraintResult` 嵌套字段)
**Apply to:** `evolution/benchmarks/benchmark_gate.py` `TBLiteBenchmarkGate.check_all`(File 3)

**Excerpt**(drift_detector.py:237-258):

```python
def check_all(
    self,
    original_sections: list,
    evolved_sections: list,
) -> list:
    original_map = {s.section_id: s for s in original_sections}
    results = []
    for evolved in evolved_sections:
        original = original_map.get(evolved.section_id)
        if original is None:
            continue
        results.append(
            self.check(evolved.section_id, original.text, evolved.text)
        )
    return results
```

> **Phase 20 augmentation:** Phase 20 `check_all` 不分 section 循环 — 返回单 elem list(整个 evolved set 一次性 benchmark)。但 list-of-dict + 嵌套 ConstraintResult 的契约形状对 pipeline 兼容 — `evolve_prompt_sections.py` 可同款 `for r in gate.check_all(...): all_constraint_results.append(r["constraint_result"]); if not r["constraint_result"].passed: all_pass = False`(若 planner 选择把 benchmark 接到 `all_pass` accumulator;**推荐不接** — Phase 20 reject 直接 `return` 比 push 到 all_constraint_results 后再循环 check 更清晰)。

### Shared Pattern 3: `FAILED_<ts>/` 持久化(Phase 5/13/14/18 统一)

**Source:** `evolution/prompts/evolve_prompt_sections.py:760-802`(Phase 18 drift FAILED 块)
**Apply to:** evolve_prompt_sections.py step 10.5 benchmark reject 路径

**Excerpt**(evolve_prompt_sections.py:760-779):

```python
if not all_pass:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output") / "prompts" / f"FAILED_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
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
```

> **Phase 20 augmentation:** 同款写 `metrics.json`,但 `benchmark_*` 字段:
> ```python
> failed_metrics["benchmark_decision"] = "reject"
> failed_metrics["benchmark_risk_score"] = benchmark_risk_score
> failed_metrics["benchmark_per_tier"] = benchmark_per_tier
> failed_metrics["benchmark_reason"] = f"Risk_Score {risk_score:.2f} >= 4.0"
> ```
> + 额外写 `tblite_report.json`(完整 D-04 schema)+ `evolved_sections.json` + `diff.txt`(便于 human review)。

### Shared Pattern 4: 每行 `try/except json.JSONDecodeError` 跳过(Phase 19 D-24 / CONCERNS §M7)

**Source:** Phase 19 `session_prompt_miner.py` 内 `_load_session` 模式(单行解析失败 → 跳过 + 计 `jsonl_skipped_lines`)
**Apply to:** `tblite_runner.py` `_parse_samples_jsonl` 解析 TBLite 输出

**Pattern**(per CONCERNS §M7 标准模板):

```python
def _parse_samples_jsonl(self, jsonl_path: Path) -> tuple[list[dict], int]:
    per_task: list[dict] = []
    skipped = 0
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                per_task.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
                continue
    return per_task, skipped
```

> **Phase 20 augmentation:** TBLite samples.jsonl 可能因 Modal worker crash 写半截 JSON line — skip + 计数,但**不 fail-fast**(continue 处理其余行)。`skipped / total > 0.05` 时 Rich warn(同 Phase 19 D-24 `JSONL_BAD_LINE_WARN_THRESHOLD`)。

### Shared Pattern 5: Rich Live Table for streaming subprocess progress(`--wait` mode,Phase 20 新增)

**Source:** **无 codebase analog** — Phase 20 第一次用 `rich.live.Live`。`rich.progress.Progress` 在 `external_importers.py:241-251` 有用法,但 Phase 20 需要 Table 行实时刷新(每 task 一行)。
**Apply to:** `tblite_runner.py` `--wait` mode 阻塞时的 stdout(planner Task 1 决具体列设计;参考 CONTEXT §Discretion 第 14 项)

**Pattern**(stdlib `rich.live.Live` + `rich.table.Table`):

```python
from rich.live import Live
from rich.table import Table

def _live_table_factory(task_filter: list[str]) -> Table:
    t = Table(title="TBLite Progress")
    t.add_column("Task", style="bold")
    t.add_column("Tier")
    t.add_column("Status")
    t.add_column("Elapsed", justify="right")
    for tname in task_filter:
        t.add_row(tname, "?", "pending", "")
    return t


# In TBLiteRunner.run(...) --wait mode:
with Live(_live_table_factory(task_filter), refresh_per_second=2) as live:
    while True:
        # ... parse [START] / [PASS] / [FAIL] markers, mutate the table ...
        live.update(updated_table)
```

> **Adaptation Delta:** 完全无 analog;planner 在 Task 1 验证 Rich Live 与 daemon thread 并存的线程安全(Rich Live 是 main thread 唯一访问)。

---

## No Analog Found

| File / Functionality | Reason | Mitigation |
|---|---|---|
| **`tblite_runner.py` Async Stream Pipe + State Monitor**(File 2 §1-2) | evolution 包内仅有 `constraints.py:58` 一处 `subprocess.run` blocking 用法,无 stream pipe / heartbeat / daemon thread / queue.Queue 前例 | planner Task 1 spike 验证(threading + queue + Popen 组合);test 用 `unittest.mock.patch("subprocess.Popen")` 完整覆盖。 |
| **`benchmark_gate.py` `_compute_risk_score` 算法**(File 3 §5) | Phase 20 第一次引入 tier-weighted breach 累加 + reject_threshold 决策(D-02);Phase 18 是 0/1/2+ severity 三分支 binary | 算法本身极简(单循环 + dict.get),但默认权重 / 阈值需 §Risk Anchor 6 复核(`benchmark_max_cost_usd=50` + async full extra $20 → 总额 ~$56 超 $50,planner 在 PLAN 中决:提到 $80 或 async full 走独立 budget)。 |
| **`benchmark_gate.py` Virtual Prompt Overlay**(File 3 §_run_overlay / _restore_overlay) | Phase 20 是首个 deliberate write-restore 路径(CONCERNS §M6);prompt_loader.py 只支持 in-place write_back(`prompt_loader.py:142-182`) | planner Task 1 决:(a) 扩展 `write_back_section` 接 `dest` 参数(推荐); (b) `os.replace` swap;(c) 复制 `_format_paren_concat` 等私有 helper。`try/finally` 保证 restore + fs-boundary 检测 + fallback。 |
| **HuggingFace `huggingface_hub.HfApi().dataset_info` 调用**(File 4 `_hf_dataset_revision`) | evolution 包从未直接调用 `huggingface_hub`(仅通过 DSPy/litellm 间接依赖) | planner Task 1 验证 venv 中有 `huggingface_hub` package(`python -c "import huggingface_hub"`);fail-open fallback `"unknown_v<TBLITE_RUNNER_VERSION>"`(Risk Anchor 5)。 |
| **`rich.live.Live` 用法**(Shared Pattern 5) | Rich Progress 在 external_importers.py:241 有,但 Live 是 Phase 20 新引入 | planner Task 1 验证 + 测试 `rich.live` 在 venv `rich>=13.0`(pyproject 已声明)中可用。 |

---

## Metadata

**Analog search scope:**
- `evolution/prompts/*.py` (12 个核心文件 — Phase 18/19 模板源)
- `evolution/core/*.py` (6 个 — config/constraints/cost_tracker/dataset_builder/external_importers/fitness)
- `evolution/tools/*.py` (6 个 — Phase 13/14 dual-tracker + miner subprocess 风格参考)
- `tests/prompts/*.py` (15 个 — Phase 18/19 测试拓扑模板)
- `.gitignore`、`.planning/phases/18-*/18-PATTERNS.md`(直接前置模板)、`.planning/phases/19-*/19-PATTERNS.md`(最新格式范例)
- hermes-agent 仓的 `environments/benchmarks/tblite/`(只读,CONTEXT canonical_refs 已锚定 6 个具体文件 + 行号,planner 在 Task 1 spike 时再读;模式抽取仅围绕 evolution 仓)

**Files scanned (evolution 仓):** 39
**Pattern extraction date:** 2026-05-19
**Phase:** 20-benchmark-gated-validation

---

## PATTERN MAPPING COMPLETE

**Phase:** 20 - Benchmark-Gated Validation
**Files classified:** 14(4 NEW source + 1 NEW CLI source + 3 MODIFY + 4 NEW data/test artifact + 1 MODIFY data artifact + 1 READ-ONLY)
**Analogs found:** 12 / 13(`tblite_runner.py` 异步 stream pipe 部分需新写)

### Coverage
- Files with exact analog: 9(File 1, 3, 4, 5, 6, 8, 9, 11, 13, 14 — 大部分直接 mirror Phase 18 模板)
- Files with role-match analog: 3(File 7 `cost_tracker.py` 直接实例化复用、File 10 `.gitignore` 句法复用、File 12 `test_tblite_runner.py` 测试拓扑沿用但 mock 对象不同)
- Files with no/partial analog: 1(File 2 `tblite_runner.py` Async Stream Pipe 部分需从零写)
- Sub-features with no analog: 4(Risk_Score 算法、Virtual Prompt Overlay 双向写、HuggingFace dataset_info 调用、Rich Live Table)— 全部 §No Analog Found 已列 mitigation

### Key Patterns Identified
1. **Phase 18 build_drift_calibration.py 是 Phase 20 build_tblite_calibration.py 的 1:1 模板** — Click + Rich + Pre-flight git check + git-tracked JSON anchor + Tier Table summary。差异仅在 algorithm body(F1 derivation → TBLite subprocess + statistics 聚合)。
2. **Phase 18 DriftDetector 是 Phase 20 TBLiteBenchmarkGate 的类结构模板** — `__init__(config, thresholds_or_anchor) → check_all → check → ConstraintResult 嵌套 dict` 接口共形,但 LLM judge 换 subprocess + Risk_Score。
3. **Phase 18 evolve_prompt_sections.py 的 drift gate 块(step 8c + step 11 metrics + CLI flag)是 Phase 20 step 10.5 + step 11 metrics + 6 个新 CLI flag 的精确插桩模板** — 完全沿用 `if X != "none": ... ; metrics[<prefix>_*] = ...` 风格。
4. **Phase 13 `max_cost_usd` 的 4-block override 链(field / YAML / env / CLI)是 Phase 20 4 个新 config 字段的 1:1 模板** — 仅换字段名 + env 前缀。
5. **Phase 18 `.gitignore` `!datasets/prompts/drift_*` exception 是 Phase 20 `!datasets/prompts/tblite_*` exception 的精确句法模板** — 顺序与缩进 1:1 沿用。

### Phase 20 唯一无 analog 的代码
- `evolution/benchmarks/tblite_runner.py` Async Stream Pipe + State Monitor(`subprocess.Popen` + `threading` + `queue` 三件套)
- `evolution/benchmarks/benchmark_gate.py` Virtual Prompt Overlay(`os.replace` + fs-boundary 检测 + `try/finally` restore)
- `evolution/benchmarks/benchmark_gate.py` `_compute_risk_score`(tier-weighted breach 累加)
- HuggingFace `huggingface_hub.HfApi().dataset_info` 调用(fail-open fallback)
- `rich.live.Live` Streaming Table(`--wait` mode 进度展示)

### Ready for Planning
Pattern mapping 完成。planner 可直接引用本文档的 14 个 file 段落中"Anchor + Adaptation Delta"模式撰写 PLAN.md 的 task 与 action 项。每段已显式给出:
- (a) 类比文件路径 + 行号(`evolve_prompt_sections.py:641-750` / `build_drift_calibration.py:1-473` / `drift_detector.py:77-258` / `cost_tracker.py:131-269` / `prompt_loader.py:142-182`)
- (b) 5-25 行类比代码摘录
- (c) `TBLiteRunner` / `TBLiteBenchmarkGate` / `build_tblite_calibration` 接口契约
- (d) Insertion point(对于 `evolve_prompt_sections.py` 修改:4 个精确 anchor 行号 — step 10.5 / step 11 / evolve() 签名 / CLI flags + subcommands)
- (e) 与 CONTEXT.md Decisions(D-01..D-18)+ Risk Anchors(fs-boundary / HF API / Modal infra failure / Watermark)的交叉引用
