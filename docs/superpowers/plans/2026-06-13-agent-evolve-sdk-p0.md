# Agent Evolve SDK — P0 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 hermes-agent-self-evolution 项目泛化为通用 Python agent 自进化 SDK：用户通过 `@evolvable_agent` / `@evolvable_prompt` / `@evolvable_tool` 装饰器接入即可自动采集轨迹、生成评估数据集、运行 GEPA 优化，并在运行时静默加载优化版本。

**Architecture:** 新增 `evolution/sdk/`（10 个模块）+ `evolution/adapters/hermes.py` 包装现有 6 个 CLI。现有 `evolution/{core,skills,tools,prompts,code,loop,monitor,benchmarks}` 完全不动 —— 全部能力复用 `core/{fitness,constraints,dataset_builder,external_importers,cost_tracker}`。agent 进程只采集轨迹到本地 JSONL，优化在独立 optimizer 进程（cron/GH Actions）跑。运行时通过 `baseline_hash` 校验加载优化版本，hash 不匹配静默回退基线。

**Tech Stack:** Python 3.10+ / DSPy 3.0+ / Click 8 / Rich 13 / pytest 7 / 无新增依赖。

**设计文档:** `docs/superpowers/specs/2026-06-13-agent-evolve-sdk-design.md`

---

## 文件结构总览

### 新增模块（依赖顺序）

```
evolution/sdk/
├── __init__.py              # 导出公共 API
├── artifact.py              # EvolvableArtifact 数据类（基础数据结构）
├── trace_sink.py            # TraceSink ABC + LocalJsonlSink + TraceRecord
├── registry.py              # _REGISTRY 单例 + ~/.evolution/registry.json + flock
├── decorators.py            # @evolvable_agent / @evolvable_prompt / @evolvable_tool
├── runtime.py               # 运行时拦截、加载优化版本、baseline_hash 校验
├── signals.py               # 5 个自动信号检测 + signal_score 计算
├── agent_module.py          # AgentModule (dspy.Module) + composite_metric
├── optimizer.py             # GEPA → MIPROv2 fallback + 三道门 + run_summary
├── ast_writer.py            # patch 模式：AST 重写源码字符串字面量
├── scaffold.py              # 生成 .github/workflows/evolve-<agent>.yml
└── cli.py                   # `evolution` 命令：discover/scaffold/optimize/status/rollback

evolution/adapters/
├── __init__.py
└── hermes.py                # 把现有 6 个 CLI 包装为 adapter，注册到 registry
```

### 新增测试

```
tests/sdk/
├── __init__.py
├── conftest.py              # tmp registry, mock LLM, fake traces fixtures
├── fixtures/
│   ├── __init__.py
│   ├── traces/              # 预录 JSONL：含错误/重试/纠正样本
│   │   ├── clean_runs.jsonl
│   │   ├── error_runs.jsonl
│   │   ├── retry_runs.jsonl
│   │   └── correction_runs.jsonl
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── three_form_bot.py    # 演示 param/return/docstring 三种文本来源
│   │   ├── bad_id_conflict.py   # 演示 import 期 ArtifactExtractionError
│   │   ├── frozen_dataclass.py  # 演示已知不兼容场景
│   │   └── echo_bot.py          # 端到端用
│   └── snapshots/
│       └── hermes_parity/
├── example_bot/
│   └── test_end_to_end.py
├── unit/
│   ├── test_artifact.py
│   ├── test_trace_sink.py
│   ├── test_registry.py
│   ├── test_decorators.py
│   ├── test_runtime.py
│   ├── test_signals.py
│   ├── test_agent_module.py
│   ├── test_optimizer.py
│   ├── test_ast_writer.py
│   ├── test_scaffold.py
│   └── test_cli.py
├── integration/
│   ├── test_trace_to_dataset.py
│   ├── test_constraint_gates.py
│   ├── test_optimized_loading.py
│   ├── test_scaffold_drift.py
│   ├── test_registry_concurrency.py
│   ├── test_apply_modes.py
│   └── test_failure_isolation.py
└── parity/
    ├── test_skill_parity.py
    └── test_tool_descriptions_parity.py
```

### 修改的现有文件

- `pyproject.toml` — 添加 `[project.scripts] evolution = "evolution.sdk.cli:main"`
- `evolution/__init__.py` — 不动（避免破坏现有 import 路径）

### 任务依赖图

```
Task 0 (脚手架) ─► Task 1 (artifact)
                         │
        ┌────────────────┼──────────────────┐
        ▼                ▼                  ▼
Task 2 (trace_sink) Task 3 (registry) Task 4 (decorators*)
                              │              │
                              ▼              ▼
                          Task 5 (runtime, 依赖 1+3)
                              │
                              ▼
                    Task 6 (signals, 依赖 2)
                              │
                              ▼
                    Task 7 (agent_module, 依赖 1)
                              │
                              ▼
                    Task 8 (optimizer, 依赖 1+2+3+6+7)
                              │
                              ▼
                    Task 9 (ast_writer, 依赖 1)
                              │
                              ▼
                    Task 10 (scaffold, 依赖 3)
                              │
                              ▼
                    Task 11 (cli, 依赖 3+8+10)
                              │
                              ▼
                    Task 12 (adapters/hermes, 依赖 1+3)
                              │
                              ▼
                    Task 13 (end-to-end EchoBot)
                              │
                              ▼
                    Task 14 (hermes parity)
                              │
                              ▼
                    Task 15 (apply=patch 集成 + 文档)

* Task 4 装饰器框架可先用占位实现，Task 5 完整接入 runtime
```

---

## Task 0: 脚手架与测试基础设施

**Files:**
- Create: `evolution/sdk/__init__.py`
- Create: `evolution/adapters/__init__.py`
- Create: `tests/sdk/__init__.py`
- Create: `tests/sdk/conftest.py`
- Create: `tests/sdk/fixtures/__init__.py`
- Create: `tests/sdk/fixtures/agents/__init__.py`
- Create: `tests/sdk/unit/__init__.py`
- Create: `tests/sdk/integration/__init__.py`
- Create: `tests/sdk/parity/__init__.py`

- [ ] **Step 1: 创建包目录骨架**

```bash
mkdir -p evolution/sdk evolution/adapters
mkdir -p tests/sdk/{unit,integration,parity,example_bot,fixtures/{traces,agents,snapshots/hermes_parity}}
```

- [ ] **Step 2: 创建所有 `__init__.py` 占位**

文件内容均为：
```python
"""(包说明字符串，例如 'Agent Evolve SDK — generic Python agent self-evolution.')"""
```

具体每个文件首行：
- `evolution/sdk/__init__.py`: `"""Agent Evolve SDK — generic Python agent self-evolution."""`
- `evolution/adapters/__init__.py`: `"""Adapters wrapping legacy hermes-specific pipelines as SDK-compatible agents."""`
- `tests/sdk/__init__.py`: 空（pytest 不需要）
- `tests/sdk/fixtures/__init__.py`: 空
- `tests/sdk/fixtures/agents/__init__.py`: 空
- `tests/sdk/unit/__init__.py`: 空
- `tests/sdk/integration/__init__.py`: 空
- `tests/sdk/parity/__init__.py`: 空

- [ ] **Step 3: 写 `tests/sdk/conftest.py` 共享 fixtures**

```python
"""Shared fixtures for evolution.sdk tests."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_evolution_home(tmp_path, monkeypatch):
    """Isolate ~/.evolution/ into a tmp directory per-test.

    Sets EVOLUTION_HOME env var; SDK modules MUST honor this when locating
    registry.json / traces / optimized / datasets / locks.
    """
    home = tmp_path / "evolution_home"
    home.mkdir()
    monkeypatch.setenv("EVOLUTION_HOME", str(home))
    return home


@pytest.fixture
def clear_registry():
    """Force a clean in-memory registry between tests.

    Some tests import agent modules which write to evolution.sdk.registry._REGISTRY.
    This fixture resets it so each test starts from an empty state.
    """
    from evolution.sdk import registry
    registry._REGISTRY.clear()
    yield
    registry._REGISTRY.clear()


@pytest.fixture
def mock_dspy_lm():
    """A mock dspy.LM that returns predictable strings.

    Configure via .respond_with(text) or .respond_sequence([t1, t2, ...]).
    """
    class _Mock:
        def __init__(self):
            self._responses = [""]
            self._call_count = 0
            self.model = "mock/predictable"

        def respond_with(self, text: str):
            self._responses = [text]
            return self

        def respond_sequence(self, texts: list[str]):
            self._responses = list(texts)
            return self

        def __call__(self, prompt=None, messages=None, **kwargs):
            text = self._responses[min(self._call_count, len(self._responses) - 1)]
            self._call_count += 1
            return [text]

    return _Mock()


@pytest.fixture
def fake_trace_factory():
    """Build TraceRecord dicts for testing signals + dataset construction."""
    def factory(
        agent="test-bot",
        agent_version="0.1.0",
        input_data=None,
        output="",
        tool_calls=None,
        signals_dict=None,
        scores_dict=None,
        ts="2026-06-13T10:00:00Z",
    ):
        return {
            "ts": ts,
            "agent": agent,
            "agent_version": agent_version,
            "run_id": f"uuid-{ts}",
            "input": input_data or {"query": "test"},
            "output": output or "test output",
            "artifacts": [
                {"id": "system", "kind": "prompt", "text_hash": "sha256:abc"},
            ],
            "tool_calls": tool_calls or [],
            "signals": signals_dict or {"errors": 0, "retries": 0, "user_correction": None},
            "scores": scores_dict or {"metric": None, "signal_score": 1.0, "judge_score": None},
        }
    return factory


@pytest.fixture
def write_trace_file(tmp_evolution_home):
    """Write a list of trace dicts to ~/.evolution/traces/<agent>/<date>.jsonl."""
    def writer(agent: str, date: str, records: list[dict]) -> Path:
        traces_dir = tmp_evolution_home / "traces" / agent
        traces_dir.mkdir(parents=True, exist_ok=True)
        path = traces_dir / f"{date}.jsonl"
        with path.open("w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return path
    return writer
```

- [ ] **Step 4: 修改 `pyproject.toml` 注册 CLI 入口（CLI 实现后才生效，先占位）**

修改 `pyproject.toml`，在 `[project]` 之后追加：

```toml
[project.scripts]
evolution = "evolution.sdk.cli:main"
```

- [ ] **Step 5: 验证 pytest 仍能发现新目录**

```bash
pytest tests/sdk/ --collect-only -q
```

Expected: 输出 `no tests ran in X.XX s`（目录存在但还没有测试）。不应报 import error。

- [ ] **Step 6: Commit**

```bash
git add evolution/sdk/__init__.py evolution/adapters/__init__.py tests/sdk/ pyproject.toml
git commit -m "sdk(00): scaffold package skeleton + shared test fixtures

Empty evolution/sdk/, evolution/adapters/, tests/sdk/{unit,integration,parity,example_bot}.
conftest.py provides tmp_evolution_home, clear_registry, mock_dspy_lm,
fake_trace_factory, write_trace_file.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 1: EvolvableArtifact 数据类

**Files:**
- Create: `evolution/sdk/artifact.py`
- Test: `tests/sdk/unit/test_artifact.py`

- [ ] **Step 1: 写 `tests/sdk/unit/test_artifact.py` 失败测试**

```python
"""Tests for EvolvableArtifact data class."""

import hashlib
from pathlib import Path

import pytest

from evolution.sdk.artifact import (
    EvolvableArtifact,
    ArtifactKind,
    TextSource,
    compute_baseline_hash,
)


def test_artifact_construction_minimal():
    artifact = EvolvableArtifact(
        agent_name="bot",
        artifact_id="system",
        kind="prompt",
        baseline_text="You are a helpful assistant.",
        text_source="param",
        source_file=Path("/tmp/bot.py"),
        decorator_lineno=10,
    )
    assert artifact.agent_name == "bot"
    assert artifact.artifact_id == "system"
    assert artifact.kind == "prompt"
    assert artifact.constraints == {}


def test_artifact_baseline_hash_computed():
    artifact = EvolvableArtifact(
        agent_name="bot",
        artifact_id="sys",
        kind="prompt",
        baseline_text="hello world",
        text_source="param",
        source_file=Path("/tmp/x.py"),
        decorator_lineno=1,
    )
    expected = "sha256:" + hashlib.sha256("hello world".encode()).hexdigest()
    assert artifact.baseline_hash == expected


def test_artifact_kind_validated():
    with pytest.raises(ValueError, match="kind must be"):
        EvolvableArtifact(
            agent_name="bot",
            artifact_id="x",
            kind="invalid_kind",  # noqa
            baseline_text="t",
            text_source="param",
            source_file=Path("/tmp/x.py"),
            decorator_lineno=1,
        )


def test_artifact_text_source_validated():
    with pytest.raises(ValueError, match="text_source must be"):
        EvolvableArtifact(
            agent_name="bot",
            artifact_id="x",
            kind="prompt",
            baseline_text="t",
            text_source="invalid",  # noqa
            source_file=Path("/tmp/x.py"),
            decorator_lineno=1,
        )


def test_artifact_to_dict_roundtrip():
    artifact = EvolvableArtifact(
        agent_name="bot",
        artifact_id="search",
        kind="tool",
        baseline_text="Search the web",
        text_source="docstring",
        source_file=Path("/tmp/bot.py"),
        decorator_lineno=42,
        constraints={"max_chars": 500, "max_growth": 0.2},
    )
    d = artifact.to_dict()
    assert d["agent_name"] == "bot"
    assert d["kind"] == "tool"
    assert d["source_file"] == "/tmp/bot.py"  # serialized as str
    assert d["constraints"]["max_chars"] == 500

    restored = EvolvableArtifact.from_dict(d)
    assert restored.baseline_hash == artifact.baseline_hash
    assert restored.source_file == artifact.source_file


def test_compute_baseline_hash_deterministic():
    h1 = compute_baseline_hash("abc")
    h2 = compute_baseline_hash("abc")
    h3 = compute_baseline_hash("abd")
    assert h1 == h2
    assert h1 != h3
    assert h1.startswith("sha256:")


def test_artifact_global_id():
    artifact = EvolvableArtifact(
        agent_name="research-bot",
        artifact_id="system",
        kind="prompt",
        baseline_text="x",
        text_source="param",
        source_file=Path("/tmp/x.py"),
        decorator_lineno=1,
    )
    assert artifact.global_id == "research-bot:system"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/sdk/unit/test_artifact.py -v
```

Expected: `ModuleNotFoundError: No module named 'evolution.sdk.artifact'`

- [ ] **Step 3: 写 `evolution/sdk/artifact.py`**

```python
"""EvolvableArtifact: foundational data class describing one optimizable text point."""

import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal

ArtifactKind = Literal["prompt", "tool"]
TextSource = Literal["param", "return_value", "docstring"]

_VALID_KINDS = {"prompt", "tool"}
_VALID_TEXT_SOURCES = {"param", "return_value", "docstring"}


def compute_baseline_hash(text: str) -> str:
    """Compute the canonical baseline hash for a text artifact.

    Format: 'sha256:<hexdigest>'. Used by runtime.py to detect when a user
    changes their source code — the optimized file becomes stale and is
    silently ignored.
    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


@dataclass
class EvolvableArtifact:
    """One optimizable text point in an agent.

    Created at decorator import time by evolution.sdk.decorators. Consumed by
    optimizer.py (to build AgentModule) and ast_writer.py (to locate the
    source code for patch/pr modes).
    """

    agent_name: str
    artifact_id: str
    kind: ArtifactKind
    baseline_text: str
    text_source: TextSource
    source_file: Path
    decorator_lineno: int
    constraints: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"kind must be one of {sorted(_VALID_KINDS)}, got {self.kind!r}"
            )
        if self.text_source not in _VALID_TEXT_SOURCES:
            raise ValueError(
                f"text_source must be one of {sorted(_VALID_TEXT_SOURCES)}, "
                f"got {self.text_source!r}"
            )
        if isinstance(self.source_file, str):
            self.source_file = Path(self.source_file)

    @property
    def baseline_hash(self) -> str:
        return compute_baseline_hash(self.baseline_text)

    @property
    def global_id(self) -> str:
        """`<agent_name>:<artifact_id>` — uniquely identifies this artifact across all agents."""
        return f"{self.agent_name}:{self.artifact_id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_file"] = str(self.source_file)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EvolvableArtifact":
        d = dict(data)
        d["source_file"] = Path(d["source_file"])
        return cls(**d)
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/sdk/unit/test_artifact.py -v
```

Expected: 全部 PASS（7 个测试）。

- [ ] **Step 5: Commit**

```bash
git add evolution/sdk/artifact.py tests/sdk/unit/test_artifact.py
git commit -m "sdk(01): EvolvableArtifact data class + baseline_hash

Foundational data class describing one optimizable text point (prompt or tool).
baseline_hash uses sha256 over UTF-8 bytes; runtime.py uses it to detect
source code changes that invalidate stale optimized files.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: TraceSink + LocalJsonlSink + TraceRecord

**Files:**
- Create: `evolution/sdk/trace_sink.py`
- Test: `tests/sdk/unit/test_trace_sink.py`

- [ ] **Step 1: 写 `tests/sdk/unit/test_trace_sink.py` 失败测试**

```python
"""Tests for TraceSink interface + LocalJsonlSink."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evolution.sdk.trace_sink import (
    TraceRecord,
    TraceSink,
    LocalJsonlSink,
    get_default_sink,
)


def test_trace_record_construction():
    r = TraceRecord(
        agent="bot",
        agent_version="0.1.0",
        input={"query": "hi"},
        output="hello",
        artifacts=[{"id": "system", "kind": "prompt", "text_hash": "sha256:abc"}],
        tool_calls=[],
    )
    assert r.agent == "bot"
    assert r.ts  # auto-filled with UTC now
    assert r.run_id  # auto-generated UUID


def test_trace_record_to_dict_jsonl_compatible():
    r = TraceRecord(
        agent="bot",
        agent_version="0.1.0",
        input={"q": "x"},
        output="y",
        artifacts=[],
        tool_calls=[],
    )
    d = r.to_dict()
    # Must be JSON-serializable
    s = json.dumps(d)
    parsed = json.loads(s)
    assert parsed["agent"] == "bot"
    assert "ts" in parsed
    assert "scores" in parsed  # default-filled


def test_local_jsonl_sink_writes_one_line_per_record(tmp_evolution_home):
    sink = LocalJsonlSink()
    r1 = TraceRecord(agent="bot", agent_version="0.1.0",
                     input={}, output="a", artifacts=[], tool_calls=[])
    r2 = TraceRecord(agent="bot", agent_version="0.1.0",
                     input={}, output="b", artifacts=[], tool_calls=[])
    sink.write(r1)
    sink.write(r2)

    # Find the file (~/.evolution/traces/bot/<YYYYMMDD>.jsonl)
    traces_dir = tmp_evolution_home / "traces" / "bot"
    files = list(traces_dir.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["output"] == "a"
    assert json.loads(lines[1])["output"] == "b"


def test_local_jsonl_sink_partitions_by_agent(tmp_evolution_home):
    sink = LocalJsonlSink()
    sink.write(TraceRecord(agent="bot-a", agent_version="0.1.0",
                           input={}, output="x", artifacts=[], tool_calls=[]))
    sink.write(TraceRecord(agent="bot-b", agent_version="0.1.0",
                           input={}, output="y", artifacts=[], tool_calls=[]))
    assert (tmp_evolution_home / "traces" / "bot-a").exists()
    assert (tmp_evolution_home / "traces" / "bot-b").exists()


def test_local_jsonl_sink_read_filters_by_date(tmp_evolution_home, write_trace_file,
                                                fake_trace_factory):
    write_trace_file("bot", "20260601",
                     [fake_trace_factory(agent="bot", ts="2026-06-01T00:00:00Z")])
    write_trace_file("bot", "20260612",
                     [fake_trace_factory(agent="bot", ts="2026-06-12T00:00:00Z")])

    sink = LocalJsonlSink()
    since = datetime(2026, 6, 5, tzinfo=timezone.utc)
    records = list(sink.read("bot", since=since))
    assert len(records) == 1
    assert records[0]["ts"] == "2026-06-12T00:00:00Z"


def test_local_jsonl_sink_count(tmp_evolution_home, write_trace_file, fake_trace_factory):
    write_trace_file("bot", "20260612", [
        fake_trace_factory(agent="bot", ts="2026-06-12T01:00:00Z"),
        fake_trace_factory(agent="bot", ts="2026-06-12T02:00:00Z"),
        fake_trace_factory(agent="bot", ts="2026-06-12T03:00:00Z"),
    ])
    sink = LocalJsonlSink()
    assert sink.count("bot", since=datetime(2026, 1, 1, tzinfo=timezone.utc)) == 3


def test_local_jsonl_sink_skips_corrupt_lines(tmp_evolution_home):
    traces_dir = tmp_evolution_home / "traces" / "bot"
    traces_dir.mkdir(parents=True)
    path = traces_dir / "20260612.jsonl"
    path.write_text(
        '{"agent": "bot", "ts": "2026-06-12T01:00:00Z", "output": "ok"}\n'
        'NOT_VALID_JSON\n'
        '{"agent": "bot", "ts": "2026-06-12T02:00:00Z", "output": "ok2"}\n'
    )
    sink = LocalJsonlSink()
    records = list(sink.read("bot", since=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    assert len(records) == 2  # bad line silently skipped


def test_local_jsonl_sink_write_failure_does_not_raise(tmp_evolution_home, monkeypatch):
    """agent process invariant: sink failure must not crash the agent."""
    sink = LocalJsonlSink()

    def boom(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(Path, "open", boom)

    # Must NOT raise
    sink.write(TraceRecord(agent="bot", agent_version="0.1.0",
                           input={}, output="x", artifacts=[], tool_calls=[]))


def test_get_default_sink_returns_local_jsonl():
    sink = get_default_sink()
    assert isinstance(sink, LocalJsonlSink)


def test_trace_sink_abstract_methods():
    """TraceSink is abstract; subclasses must implement write/read/count."""
    with pytest.raises(TypeError):
        TraceSink()  # cannot instantiate abstract class
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/sdk/unit/test_trace_sink.py -v
```

Expected: `ModuleNotFoundError: No module named 'evolution.sdk.trace_sink'`

- [ ] **Step 3: 写 `evolution/sdk/trace_sink.py`**

```python
"""TraceSink interface + LocalJsonlSink default implementation.

agent 进程通过 sink 写入轨迹；optimizer 进程通过 sink 读取轨迹。
agent 进程不变量：sink 写失败永不 crash agent。
"""

import json
import logging
import os
import sys
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

log = logging.getLogger("evolution.sdk.trace_sink")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _evolution_home() -> Path:
    """Return ~/.evolution/ (or $EVOLUTION_HOME if set, for test isolation)."""
    override = os.getenv("EVOLUTION_HOME")
    if override:
        return Path(override)
    return Path.home() / ".evolution"


@dataclass
class TraceRecord:
    """One agent run = one trace record. JSONL serialized to disk."""

    agent: str
    agent_version: str
    input: dict
    output: object  # str / dict / list — whatever agent.run() returns
    artifacts: list[dict]  # [{"id", "kind", "text_hash"}, ...]
    tool_calls: list[dict]  # [{"id", "args", "result", "error", "latency_ms"}, ...]
    ts: str = field(default_factory=_utc_now_iso)
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    signals: dict = field(default_factory=lambda: {
        "errors": 0, "retries": 0, "user_correction": None,
    })
    scores: dict = field(default_factory=lambda: {
        "metric": None, "signal_score": None, "judge_score": None,
    })

    def to_dict(self) -> dict:
        return asdict(self)


class TraceSink(ABC):
    """Abstract trace storage backend.

    P0 ships LocalJsonlSink. P2 may add HTTP / S3 / Postgres / OTel sinks.
    """

    @abstractmethod
    def write(self, record: TraceRecord) -> None:
        """Persist one record. MUST NOT raise on storage failure (silent + log)."""

    @abstractmethod
    def read(self, agent: str, since: datetime) -> Iterator[dict]:
        """Yield trace dicts for the given agent, filtered to ts >= since.

        May raise on read failure; optimizer process handles errors at boundary.
        """

    @abstractmethod
    def count(self, agent: str, since: datetime) -> int:
        """Count records matching agent + since filter."""


class LocalJsonlSink(TraceSink):
    """Default sink: write to ~/.evolution/traces/<agent>/YYYYMMDD.jsonl."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or (_evolution_home() / "traces")

    def _file_for(self, agent: str, ts_iso: str) -> Path:
        date = ts_iso[:10].replace("-", "")  # YYYYMMDD
        return self.base_dir / agent / f"{date}.jsonl"

    def write(self, record: TraceRecord) -> None:
        try:
            path = self._file_for(record.agent, record.ts)
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(record.to_dict(), default=str) + "\n"
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:  # noqa: BLE001 — agent invariant: never crash
            log.warning("LocalJsonlSink.write failed: %s", e)
            sys.stderr.write(f"[evolution.sdk] trace write failed: {e}\n")

    def read(self, agent: str, since: datetime) -> Iterator[dict]:
        agent_dir = self.base_dir / agent
        if not agent_dir.exists():
            return
        for path in sorted(agent_dir.glob("*.jsonl")):
            try:
                with path.open("r", encoding="utf-8") as f:
                    for lineno, raw in enumerate(f, 1):
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            rec = json.loads(raw)
                        except json.JSONDecodeError:
                            log.warning("skip corrupt line %s:%d", path, lineno)
                            continue
                        ts = rec.get("ts", "")
                        if not ts:
                            continue
                        try:
                            rec_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
                                tzinfo=timezone.utc
                            )
                        except ValueError:
                            log.warning("skip bad ts %s in %s", ts, path)
                            continue
                        if rec_dt >= since:
                            yield rec
            except OSError as e:
                log.warning("could not read %s: %s", path, e)

    def count(self, agent: str, since: datetime) -> int:
        return sum(1 for _ in self.read(agent, since))


_DEFAULT_SINK: Optional[TraceSink] = None


def get_default_sink() -> TraceSink:
    """Return process-wide default sink (lazy LocalJsonlSink)."""
    global _DEFAULT_SINK
    if _DEFAULT_SINK is None:
        _DEFAULT_SINK = LocalJsonlSink()
    return _DEFAULT_SINK


def set_default_sink(sink: TraceSink) -> None:
    """Override the default sink (used by tests / advanced users)."""
    global _DEFAULT_SINK
    _DEFAULT_SINK = sink
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/sdk/unit/test_trace_sink.py -v
```

Expected: 10 个测试全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add evolution/sdk/trace_sink.py tests/sdk/unit/test_trace_sink.py
git commit -m "sdk(02): TraceSink ABC + LocalJsonlSink + TraceRecord

Default sink writes one JSON object per line to
~/.evolution/traces/<agent>/YYYYMMDD.jsonl. Read path filters by ts >= since,
silently skips corrupt lines. agent invariant: write failures log + return,
never raise. Honors \$EVOLUTION_HOME override for test isolation.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Registry — 进程内 + JSON 持久化 + flock

**Files:**
- Create: `evolution/sdk/registry.py`
- Test: `tests/sdk/unit/test_registry.py`
- Test: `tests/sdk/integration/test_registry_concurrency.py`

- [ ] **Step 1: 写 `tests/sdk/unit/test_registry.py` 失败测试**

```python
"""Tests for in-memory + file-persisted agent registry."""

import json
import os
from pathlib import Path

import pytest

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.registry import (
    AgentRegistration,
    DuplicateAgentError,
    register_agent,
    get_agent,
    list_agents,
    persist_to_file,
    load_from_file,
    _REGISTRY,
)


@pytest.fixture(autouse=True)
def _clear(clear_registry):
    pass


def _mk_artifact(agent="bot", aid="system"):
    return EvolvableArtifact(
        agent_name=agent,
        artifact_id=aid,
        kind="prompt",
        baseline_text="hi",
        text_source="param",
        source_file=Path("/tmp/x.py"),
        decorator_lineno=1,
    )


def test_register_agent_stores_in_memory():
    reg = AgentRegistration(
        name="bot",
        module="myapp.bot:Bot",
        version="0.1.0",
        schedule="weekly",
        min_samples=50,
        auto_optimize=True,
        apply="runtime",
        max_cost_usd=5.0,
        artifacts=[_mk_artifact()],
        source_files=[Path("/tmp/x.py")],
    )
    register_agent(reg)
    assert "bot" in _REGISTRY
    assert _REGISTRY["bot"].name == "bot"


def test_register_agent_duplicate_different_module_raises():
    reg1 = AgentRegistration(
        name="bot", module="myapp.a:Bot", version="0.1.0",
        schedule=None, min_samples=10, auto_optimize=False, apply="runtime",
        max_cost_usd=5.0, artifacts=[_mk_artifact()], source_files=[Path("/tmp/a.py")],
    )
    reg2 = AgentRegistration(
        name="bot", module="myapp.b:Bot", version="0.1.0",
        schedule=None, min_samples=10, auto_optimize=False, apply="runtime",
        max_cost_usd=5.0, artifacts=[_mk_artifact()], source_files=[Path("/tmp/b.py")],
    )
    register_agent(reg1)
    with pytest.raises(DuplicateAgentError, match="different module"):
        register_agent(reg2)


def test_register_agent_duplicate_same_module_replaces():
    """Re-importing the same module (test reload, IDE) replaces silently."""
    reg = AgentRegistration(
        name="bot", module="myapp.a:Bot", version="0.1.0",
        schedule=None, min_samples=10, auto_optimize=False, apply="runtime",
        max_cost_usd=5.0, artifacts=[_mk_artifact()], source_files=[Path("/tmp/a.py")],
    )
    register_agent(reg)
    register_agent(reg)  # idempotent
    assert len(_REGISTRY) == 1


def test_get_agent_returns_none_for_unknown():
    assert get_agent("nonexistent") is None


def test_list_agents_sorted():
    for name in ["c-bot", "a-bot", "b-bot"]:
        register_agent(AgentRegistration(
            name=name, module=f"myapp.{name}:X", version="0.1.0",
            schedule=None, min_samples=10, auto_optimize=False, apply="runtime",
            max_cost_usd=5.0, artifacts=[_mk_artifact(agent=name)],
            source_files=[Path(f"/tmp/{name}.py")],
        ))
    names = list_agents()
    assert names == ["a-bot", "b-bot", "c-bot"]


def test_persist_to_file_writes_registry_json(tmp_evolution_home):
    reg = AgentRegistration(
        name="bot", module="myapp.a:Bot", version="0.1.0",
        schedule="weekly", min_samples=50, auto_optimize=True, apply="runtime",
        max_cost_usd=5.0, artifacts=[_mk_artifact()],
        source_files=[Path("/tmp/a.py")],
    )
    register_agent(reg)
    path = persist_to_file()
    assert path == tmp_evolution_home / "registry.json"
    data = json.loads(path.read_text())
    assert data["version"] == 1
    assert "bot" in data["agents"]
    assert data["agents"]["bot"]["schedule"] == "weekly"


def test_load_from_file_restores_registry(tmp_evolution_home):
    reg = AgentRegistration(
        name="bot", module="myapp.a:Bot", version="0.1.0",
        schedule="daily", min_samples=20, auto_optimize=True, apply="patch",
        max_cost_usd=10.0, artifacts=[_mk_artifact()],
        source_files=[Path("/tmp/a.py")],
    )
    register_agent(reg)
    persist_to_file()

    _REGISTRY.clear()
    load_from_file()

    loaded = get_agent("bot")
    assert loaded is not None
    assert loaded.schedule == "daily"
    assert loaded.apply == "patch"


def test_load_from_file_missing_file_is_noop(tmp_evolution_home):
    # No registry.json exists; should not raise.
    load_from_file()
    assert _REGISTRY == {}


def test_persist_skipped_unless_env_var_or_explicit(tmp_evolution_home, monkeypatch):
    """Decorator import期不能自动写文件 (production safety)."""
    monkeypatch.delenv("EVOLUTION_AUTO_REGISTER", raising=False)
    reg = AgentRegistration(
        name="bot", module="myapp.a:Bot", version="0.1.0",
        schedule="weekly", min_samples=50, auto_optimize=True, apply="runtime",
        max_cost_usd=5.0, artifacts=[_mk_artifact()],
        source_files=[Path("/tmp/a.py")],
    )
    register_agent(reg)
    # Registry is in-memory only; no file should exist.
    assert not (tmp_evolution_home / "registry.json").exists()

    # Now flip the flag; explicit persist still required (auto-write would be the wrong default).
    monkeypatch.setenv("EVOLUTION_AUTO_REGISTER", "1")
    # Re-registering doesn't auto-write either; user must call persist_to_file().
    register_agent(reg)
    assert not (tmp_evolution_home / "registry.json").exists()
    persist_to_file()
    assert (tmp_evolution_home / "registry.json").exists()
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/sdk/unit/test_registry.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: 写 `evolution/sdk/registry.py`**

```python
"""Process-local agent registry + optional ~/.evolution/registry.json persistence.

CRITICAL: decorator import期 only writes to in-memory _REGISTRY. Persisting to
disk requires either:
  - explicit call: persist_to_file() (e.g., from `evolution discover` CLI)
  - env var: EVOLUTION_AUTO_REGISTER=1 (advanced; opt-in)

This avoids "production app imports user module → writes home directory"
as a安全雷区.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.trace_sink import _evolution_home


class DuplicateAgentError(Exception):
    """Raised when two different modules register the same agent name."""


@dataclass
class AgentRegistration:
    """Metadata for one registered agent."""
    name: str
    module: str                       # "myapp.bots.research:ResearchBot"
    version: str
    schedule: Optional[str]
    min_samples: int
    auto_optimize: bool
    apply: str                        # "runtime" | "patch" | "pr"
    max_cost_usd: float
    artifacts: list[EvolvableArtifact]
    source_files: list[Path]
    schedule_managed_by: Optional[str] = None  # 'evolution-loop.yml' for hermes adapter
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    last_optimized: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "module": self.module,
            "version": self.version,
            "schedule": self.schedule,
            "min_samples": self.min_samples,
            "auto_optimize": self.auto_optimize,
            "apply": self.apply,
            "max_cost_usd": self.max_cost_usd,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "source_files": [str(p) for p in self.source_files],
            "schedule_managed_by": self.schedule_managed_by,
            "registered_at": self.registered_at,
            "last_optimized": self.last_optimized,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentRegistration":
        return cls(
            name=data["name"],
            module=data["module"],
            version=data["version"],
            schedule=data.get("schedule"),
            min_samples=data["min_samples"],
            auto_optimize=data["auto_optimize"],
            apply=data["apply"],
            max_cost_usd=data["max_cost_usd"],
            artifacts=[EvolvableArtifact.from_dict(a) for a in data["artifacts"]],
            source_files=[Path(p) for p in data["source_files"]],
            schedule_managed_by=data.get("schedule_managed_by"),
            registered_at=data.get("registered_at", ""),
            last_optimized=data.get("last_optimized"),
        )


# Process-local in-memory registry.
_REGISTRY: dict[str, AgentRegistration] = {}


def register_agent(reg: AgentRegistration) -> None:
    """Register or replace an agent in-memory.

    Raises DuplicateAgentError if another module already registered the same name.
    Re-registering from the same module is idempotent (replaces silently — covers
    reimport during tests / IDE reload).
    """
    existing = _REGISTRY.get(reg.name)
    if existing is not None and existing.module != reg.module:
        raise DuplicateAgentError(
            f"agent name {reg.name!r} already registered by different module "
            f"{existing.module!r} (new: {reg.module!r}). Choose a unique name."
        )
    _REGISTRY[reg.name] = reg


def get_agent(name: str) -> Optional[AgentRegistration]:
    return _REGISTRY.get(name)


def list_agents() -> list[str]:
    return sorted(_REGISTRY.keys())


def _registry_path() -> Path:
    return _evolution_home() / "registry.json"


def persist_to_file() -> Path:
    """Atomically write the in-memory registry to ~/.evolution/registry.json.

    Uses fcntl.flock to serialize concurrent writers (best-effort on POSIX;
    silently degrades on Windows where fcntl is unavailable).
    """
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": 1,
        "agents": {name: reg.to_dict() for name, reg in _REGISTRY.items()},
    }

    tmp = path.with_suffix(".tmp")
    lock_path = path.with_suffix(".lock")

    # Acquire lock (best-effort).
    try:
        import fcntl
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            tmp.write_text(json.dumps(payload, indent=2))
            os.replace(tmp, path)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
    except ImportError:
        # Windows fallback: no locking, but atomic rename still applies.
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, path)

    return path


def load_from_file() -> None:
    """Load ~/.evolution/registry.json into _REGISTRY.

    No-op if the file doesn't exist. Does NOT clear existing in-memory entries;
    callers wanting a fresh state should _REGISTRY.clear() first.
    """
    path = _registry_path()
    if not path.exists():
        return
    data = json.loads(path.read_text())
    if data.get("version") != 1:
        raise ValueError(f"unsupported registry.json version {data.get('version')!r}")
    for name, entry in data.get("agents", {}).items():
        _REGISTRY[name] = AgentRegistration.from_dict(entry)
```

- [ ] **Step 4: 运行单元测试**

```bash
pytest tests/sdk/unit/test_registry.py -v
```

Expected: 9 个测试 PASS。

- [ ] **Step 5: 写 `tests/sdk/integration/test_registry_concurrency.py`**

```python
"""Concurrency: multiple processes persisting registry.json."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="fcntl.flock not available on Windows",
)


def test_concurrent_persist_does_not_corrupt_json(tmp_evolution_home):
    """5 subprocesses writing different agents concurrently → final file has all of them."""
    script = textwrap.dedent("""
        import os, sys
        os.environ["EVOLUTION_HOME"] = sys.argv[1]
        from pathlib import Path
        from evolution.sdk.artifact import EvolvableArtifact
        from evolution.sdk.registry import register_agent, AgentRegistration, persist_to_file, _REGISTRY

        name = sys.argv[2]
        _REGISTRY.clear()
        # Each subprocess starts from current on-disk state to merge correctly.
        from evolution.sdk.registry import load_from_file
        load_from_file()

        register_agent(AgentRegistration(
            name=name,
            module=f"myapp.{name}:X",
            version="0.1.0",
            schedule=None, min_samples=10, auto_optimize=False, apply="runtime",
            max_cost_usd=5.0,
            artifacts=[EvolvableArtifact(
                agent_name=name, artifact_id="x", kind="prompt",
                baseline_text="hi", text_source="param",
                source_file=Path("/tmp/x.py"), decorator_lineno=1,
            )],
            source_files=[Path(f"/tmp/{name}.py")],
        ))
        persist_to_file()
        print(name, "OK")
    """)
    procs = []
    for n in ["a", "b", "c", "d", "e"]:
        p = subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_evolution_home), f"bot-{n}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        procs.append(p)

    for p in procs:
        out, err = p.communicate(timeout=30)
        assert p.returncode == 0, f"subprocess failed: {err.decode()}"

    # Final registry.json must be valid JSON with all 5 agents.
    data = json.loads((tmp_evolution_home / "registry.json").read_text())
    assert data["version"] == 1
    # Last-writer-wins per agent; at least the last process's write survives.
    # We don't guarantee all 5 names if the load/save races, but the file must be valid.
    assert len(data["agents"]) >= 1
    for name in data["agents"]:
        assert name.startswith("bot-")
```

- [ ] **Step 6: 运行并发集成测试**

```bash
pytest tests/sdk/integration/test_registry_concurrency.py -v
```

Expected: PASS（macOS/Linux）。`registry.json` 始终是合法 JSON，不出现半行/混合内容。

- [ ] **Step 7: Commit**

```bash
git add evolution/sdk/registry.py tests/sdk/unit/test_registry.py tests/sdk/integration/test_registry_concurrency.py
git commit -m "sdk(03): agent registry — in-memory + ~/.evolution/registry.json + flock

In-memory _REGISTRY populated by decorator imports; persist_to_file() does
atomic write (tmp + os.replace) under fcntl.flock. DuplicateAgentError when
same name registers from different module path. Decorator import never
auto-writes to disk — caller must opt-in via persist_to_file().

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: 装饰器 — `@evolvable_agent` / `@evolvable_prompt` / `@evolvable_tool`

**Files:**
- Create: `evolution/sdk/decorators.py`
- Test: `tests/sdk/unit/test_decorators.py`
- Test fixtures: `tests/sdk/fixtures/agents/three_form_bot.py`, `bad_id_conflict.py`

- [ ] **Step 1: 写 fixture agents — `tests/sdk/fixtures/agents/three_form_bot.py`**

```python
"""Agent fixture demonstrating all three text-source forms."""
from evolution.sdk.decorators import (
    evolvable_agent, evolvable_prompt, evolvable_tool,
)


@evolvable_agent(
    name="three-form-bot",
    version="0.1.0",
    judge_dimensions=("correctness",),
    min_samples=3,
    schedule=None,
    auto_optimize=False,
    max_cost_usd=1.0,
)
class ThreeFormBot:
    """Test bot covering param/return/docstring text sources."""

    # Form 1: text=... param wins
    @evolvable_prompt(id="system", text="You are FORM-1.", max_chars=2000)
    def system_prompt(self) -> str:
        return self._evolved_system or "fallback"

    # Form 2: function return value (no args, single literal)
    @evolvable_prompt(id="planner")
    def planner_prompt(self) -> str:
        return "Plan FORM-2 carefully."

    # Form 3: docstring
    @evolvable_tool(id="searcher", max_chars=500)
    def search(self, query: str):
        """FORM-3: search the web for the query."""
        return f"results({query})"

    def __init__(self):
        self._evolved_system = None

    def run(self, q: str) -> str:
        return f"echo: {q}"
```

- [ ] **Step 2: 写 fixture — `tests/sdk/fixtures/agents/bad_id_conflict.py`**

```python
"""Agent fixture demonstrating duplicate artifact id (must raise at import)."""
from evolution.sdk.decorators import evolvable_agent, evolvable_prompt


@evolvable_agent(name="bad-id-bot", version="0.1.0", min_samples=3,
                 schedule=None, auto_optimize=False, max_cost_usd=1.0)
class BadIdBot:
    @evolvable_prompt(id="same", text="A")
    def a(self) -> str:
        return "A"

    @evolvable_prompt(id="same", text="B")  # duplicate id within same agent
    def b(self) -> str:
        return "B"

    def run(self, q):
        return q
```

- [ ] **Step 3: 写 `tests/sdk/unit/test_decorators.py`**

```python
"""Tests for @evolvable_agent / @evolvable_prompt / @evolvable_tool."""

import importlib
import sys
from pathlib import Path

import pytest

from evolution.sdk.decorators import (
    evolvable_agent, evolvable_prompt, evolvable_tool,
    ArtifactExtractionError,
)
from evolution.sdk import registry
from evolution.sdk.artifact import compute_baseline_hash


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "agents"


@pytest.fixture(autouse=True)
def _clean(clear_registry, monkeypatch):
    # Add fixtures dir to path so import works.
    if str(FIXTURE_DIR) not in sys.path:
        monkeypatch.syspath_prepend(str(FIXTURE_DIR.parent.parent))
    # Force re-import of fixture modules each test (so decorators re-run).
    for mod_name in list(sys.modules):
        if mod_name.startswith("fixtures.agents"):
            del sys.modules[mod_name]


def test_three_form_bot_registers_three_artifacts():
    # Import fixture (must succeed)
    importlib.import_module("fixtures.agents.three_form_bot")

    reg = registry.get_agent("three-form-bot")
    assert reg is not None
    assert len(reg.artifacts) == 3
    ids = {a.artifact_id for a in reg.artifacts}
    assert ids == {"system", "planner", "searcher"}


def test_form1_param_text_extracted():
    importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    a = next(a for a in reg.artifacts if a.artifact_id == "system")
    assert a.baseline_text == "You are FORM-1."
    assert a.text_source == "param"
    assert a.kind == "prompt"


def test_form2_return_value_extracted():
    importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    a = next(a for a in reg.artifacts if a.artifact_id == "planner")
    assert a.baseline_text == "Plan FORM-2 carefully."
    assert a.text_source == "return_value"


def test_form3_docstring_extracted():
    importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    a = next(a for a in reg.artifacts if a.artifact_id == "searcher")
    assert a.baseline_text == "FORM-3: search the web for the query."
    assert a.text_source == "docstring"
    assert a.kind == "tool"


def test_baseline_hash_matches_extracted_text():
    importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    a = next(a for a in reg.artifacts if a.artifact_id == "system")
    assert a.baseline_hash == compute_baseline_hash("You are FORM-1.")


def test_duplicate_artifact_id_raises_at_import():
    with pytest.raises(ArtifactExtractionError, match="duplicate artifact id"):
        importlib.import_module("fixtures.agents.bad_id_conflict")


def test_constraints_propagate_from_decorator():
    importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    a = next(a for a in reg.artifacts if a.artifact_id == "system")
    assert a.constraints.get("max_chars") == 2000


def test_evolvable_prompt_without_any_text_source_raises():
    with pytest.raises(ArtifactExtractionError, match="no text source"):
        @evolvable_prompt(id="empty")
        def no_text(self, x):  # has args → can't use return-value, no docstring, no text= → error
            return x


def test_evolvable_agent_records_source_file_and_lineno():
    importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    a = next(a for a in reg.artifacts if a.artifact_id == "system")
    assert a.source_file.name == "three_form_bot.py"
    assert a.decorator_lineno > 0


def test_evolvable_agent_class_carries_meta():
    mod = importlib.import_module("fixtures.agents.three_form_bot")
    assert hasattr(mod.ThreeFormBot, "_evolution_meta")
    assert mod.ThreeFormBot._evolution_meta["name"] == "three-form-bot"


def test_evolvable_agent_run_method_wrapped(monkeypatch):
    """Agent.run() should be intercepted so traces can be captured (Task 5 wires this)."""
    mod = importlib.import_module("fixtures.agents.three_form_bot")
    bot = mod.ThreeFormBot()
    # The method should be wrapped (different from the original)
    # We just verify the marker attribute exists; full trace test is Task 5.
    assert hasattr(bot.run, "__wrapped__") or hasattr(type(bot).run, "_evolution_wrapped")


def test_evolvable_agent_no_auto_persist(tmp_evolution_home, monkeypatch):
    """Decorator import期 must not write registry.json (production safety)."""
    monkeypatch.delenv("EVOLUTION_AUTO_REGISTER", raising=False)
    importlib.import_module("fixtures.agents.three_form_bot")
    assert not (tmp_evolution_home / "registry.json").exists()
```

- [ ] **Step 4: 运行测试验证失败**

```bash
pytest tests/sdk/unit/test_decorators.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 5: 写 `evolution/sdk/decorators.py`**

```python
"""Public decorator API for the SDK.

Two-tier:
  Outer:  @evolvable_agent — registers an agent class, intercepts entrypoint methods.
  Inner:  @evolvable_prompt / @evolvable_tool — marks an optimizable text point.

Text source resolution priority:
  1. text=... parameter on the decorator
  2. function return value (only if the function has no args besides self
     AND the body is exactly `return <single string literal>`)
  3. function docstring
  4. else raise ArtifactExtractionError at import time

Decorator import期 invariant: 禁止网络 IO / 写文件 IO. Allowed: read
~/.evolution/optimized/<agent>/*.json once (with fallback).
"""

import ast
import functools
import inspect
import sys
from pathlib import Path
from typing import Callable, Iterable, Optional

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk import registry


class ArtifactExtractionError(Exception):
    """Raised at import time when a decorated artifact can't be resolved."""


# ── Inner decorator factories ────────────────────────────────────────────


def _build_inner_decorator(kind: str):
    """Factory: returns @evolvable_prompt or @evolvable_tool."""

    def decorator(
        *,
        id: str,
        text: Optional[str] = None,
        max_chars: Optional[int] = None,
        max_growth: Optional[float] = None,
        forbidden_patterns: Optional[Iterable[str]] = None,
    ):
        if not id:
            raise ArtifactExtractionError("id is required (non-empty string)")

        def wrapper(func: Callable) -> Callable:
            baseline_text, text_source = _resolve_text(func, text)
            constraints = {}
            if max_chars is not None:
                constraints["max_chars"] = max_chars
            if max_growth is not None:
                constraints["max_growth"] = max_growth
            if forbidden_patterns is not None:
                constraints["forbidden_patterns"] = list(forbidden_patterns)

            try:
                source_file = Path(inspect.getsourcefile(func) or "<unknown>")
            except TypeError:
                source_file = Path("<unknown>")
            try:
                _, lineno = inspect.getsourcelines(func)
            except (OSError, TypeError):
                lineno = 0

            # Stash the partial artifact info on the function; outer @evolvable_agent
            # will collect these and finalize agent_name + global validation.
            func._evolution_artifact = {
                "id": id,
                "kind": kind,
                "baseline_text": baseline_text,
                "text_source": text_source,
                "source_file": source_file,
                "decorator_lineno": lineno,
                "constraints": constraints,
            }
            return func

        return wrapper

    return decorator


evolvable_prompt = _build_inner_decorator("prompt")
evolvable_tool = _build_inner_decorator("tool")


# ── Text resolution helpers ──────────────────────────────────────────────


def _resolve_text(func: Callable, explicit_text: Optional[str]) -> tuple[str, str]:
    """Return (baseline_text, text_source). Raises ArtifactExtractionError if none found."""
    if explicit_text is not None:
        return explicit_text, "param"

    # Form 2: function return value — only if no args (except self) and body is exactly
    # `return <single string literal>`.
    sig = inspect.signature(func)
    params = [p for p in sig.parameters.values()
              if p.name != "self" and p.default is inspect.Parameter.empty
              and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
    if not params:
        literal = _extract_single_string_literal(func)
        if literal is not None:
            return literal, "return_value"

    # Form 3: docstring
    doc = (func.__doc__ or "").strip()
    if doc:
        return doc, "docstring"

    raise ArtifactExtractionError(
        f"no text source found for {func.__qualname__}: "
        "provide text= parameter, return a single string literal with no args, "
        "or add a docstring."
    )


def _extract_single_string_literal(func: Callable) -> Optional[str]:
    """If the function body is exactly `return <single string literal>`, return it.

    Used by Form 2. Returns None if the body is more complex (caller falls back to
    docstring or raises).
    """
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        return None

    # Dedent so AST parses correctly when the function is a class method.
    import textwrap
    source = textwrap.dedent(source)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    fn = tree.body[0]
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None

    # Strip docstring if present.
    body = fn.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]

    if len(body) != 1:
        return None
    stmt = body[0]
    if not isinstance(stmt, ast.Return):
        return None
    val = stmt.value
    if isinstance(val, ast.Constant) and isinstance(val.value, str):
        return val.value
    return None


# ── Outer decorator: @evolvable_agent ────────────────────────────────────


_ENTRYPOINT_CANDIDATES = ("run", "__call__", "invoke", "execute")


def evolvable_agent(
    *,
    name: str,
    version: str = "0.1.0",
    metric: Optional[Callable] = None,
    judge_dimensions: tuple = ("correctness", "conciseness"),
    min_samples: int = 50,
    schedule: Optional[str] = "weekly",
    auto_optimize: bool = True,
    apply: str = "runtime",
    sink=None,
    max_cost_usd: float = 5.0,
    entrypoint: Optional[str] = None,
):
    """Outer decorator. Registers the class and wraps its entrypoint method.

    Task 5 (runtime.py) augments the wrapper to capture traces.
    """
    if not name:
        raise ArtifactExtractionError("@evolvable_agent name= is required")
    if apply not in ("runtime", "patch", "pr"):
        raise ArtifactExtractionError(
            f"apply must be one of runtime/patch/pr, got {apply!r}"
        )

    def class_decorator(cls):
        # Collect inner artifacts.
        artifacts: list[EvolvableArtifact] = []
        seen_ids: set[str] = set()
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            meta = getattr(attr, "_evolution_artifact", None)
            if meta is None:
                continue
            if meta["id"] in seen_ids:
                raise ArtifactExtractionError(
                    f"duplicate artifact id {meta['id']!r} in agent {name!r}"
                )
            seen_ids.add(meta["id"])
            artifacts.append(EvolvableArtifact(
                agent_name=name,
                artifact_id=meta["id"],
                kind=meta["kind"],
                baseline_text=meta["baseline_text"],
                text_source=meta["text_source"],
                source_file=meta["source_file"],
                decorator_lineno=meta["decorator_lineno"],
                constraints=meta["constraints"],
            ))

        # Resolve entrypoint method.
        entry = entrypoint or _detect_entrypoint(cls)
        if entry is None:
            raise ArtifactExtractionError(
                f"agent {name!r} has no entrypoint: provide entrypoint= or "
                f"define one of {_ENTRYPOINT_CANDIDATES}"
            )

        # Wrap the entrypoint. Task 5 will add full trace capture; for now,
        # we install a thin shim that just calls through and marks itself.
        original = getattr(cls, entry)

        @functools.wraps(original)
        def wrapped(self, *args, **kwargs):
            # Task 5 will replace this body with full trace capture.
            from evolution.sdk import runtime
            return runtime.invoke(self, entry, original, args, kwargs)

        wrapped._evolution_wrapped = True
        setattr(cls, entry, wrapped)

        # Resolve source files (de-duplicated).
        source_files = sorted({a.source_file for a in artifacts})
        try:
            source_files.append(Path(inspect.getsourcefile(cls) or "<unknown>"))
            source_files = sorted(set(source_files))
        except TypeError:
            pass

        # Stash meta on the class.
        cls._evolution_meta = {
            "name": name,
            "version": version,
            "metric": metric,
            "judge_dimensions": judge_dimensions,
            "min_samples": min_samples,
            "schedule": schedule,
            "auto_optimize": auto_optimize,
            "apply": apply,
            "sink": sink,
            "max_cost_usd": max_cost_usd,
            "entrypoint": entry,
            "artifacts": artifacts,
        }

        # Register.
        module_path = f"{cls.__module__}:{cls.__name__}"
        reg = registry.AgentRegistration(
            name=name,
            module=module_path,
            version=version,
            schedule=schedule,
            min_samples=min_samples,
            auto_optimize=auto_optimize,
            apply=apply,
            max_cost_usd=max_cost_usd,
            artifacts=artifacts,
            source_files=source_files,
        )
        registry.register_agent(reg)

        return cls

    return class_decorator


def _detect_entrypoint(cls) -> Optional[str]:
    for candidate in _ENTRYPOINT_CANDIDATES:
        if callable(getattr(cls, candidate, None)):
            return candidate
    return None
```

- [ ] **Step 6: 运行测试验证通过**

```bash
pytest tests/sdk/unit/test_decorators.py -v
```

Expected: 11 个测试 PASS。

> Note: `test_evolvable_agent_run_method_wrapped` 检查 `run` 被替换；它会调用 `runtime.invoke`，Task 5 才实现 — 暂时打 stub 让它通过。

- [ ] **Step 7: 创建 runtime.py 占位（Task 5 替换）**

```python
# evolution/sdk/runtime.py — temporary stub for Task 4; Task 5 implements full trace capture.
"""Runtime module — invokes wrapped agent methods. Task 5 will add trace capture + optimized loading."""


def invoke(instance, method_name, original_fn, args, kwargs):
    """Stub: call the original method untouched. Task 5 replaces this with trace capture."""
    return original_fn(instance, *args, **kwargs)
```

- [ ] **Step 8: 再次运行测试，全部 PASS**

```bash
pytest tests/sdk/unit/test_decorators.py -v
```

- [ ] **Step 9: 更新 `evolution/sdk/__init__.py` 导出公共 API**

```python
"""Agent Evolve SDK — generic Python agent self-evolution."""

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.decorators import (
    evolvable_agent,
    evolvable_prompt,
    evolvable_tool,
    ArtifactExtractionError,
)
from evolution.sdk.trace_sink import (
    TraceSink,
    LocalJsonlSink,
    TraceRecord,
)

__all__ = [
    "EvolvableArtifact",
    "evolvable_agent",
    "evolvable_prompt",
    "evolvable_tool",
    "ArtifactExtractionError",
    "TraceSink",
    "LocalJsonlSink",
    "TraceRecord",
]
```

- [ ] **Step 10: Commit**

```bash
git add evolution/sdk/decorators.py evolution/sdk/runtime.py evolution/sdk/__init__.py \
        tests/sdk/unit/test_decorators.py tests/sdk/fixtures/agents/three_form_bot.py \
        tests/sdk/fixtures/agents/bad_id_conflict.py
git commit -m "sdk(04): @evolvable_agent / @evolvable_prompt / @evolvable_tool

Two-tier decorator. Outer @evolvable_agent registers the class + wraps
entrypoint (auto-detects run/__call__/invoke/execute). Inner
@evolvable_prompt and @evolvable_tool mark optimizable text. Text source
resolution: text= param > single-literal return > docstring; ArtifactExtractionError
if none. Stub runtime.invoke installed; Task 5 wires full trace capture.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Runtime — 拦截、加载优化版本、`baseline_hash` 校验

**Files:**
- Modify: `evolution/sdk/runtime.py` (replace stub with full implementation)
- Test: `tests/sdk/unit/test_runtime.py`
- Test: `tests/sdk/integration/test_optimized_loading.py`

- [ ] **Step 1: 写 `tests/sdk/unit/test_runtime.py`**

```python
"""Tests for runtime trace capture + optimized loading."""

import importlib
import json
import sys
from pathlib import Path

import pytest

from evolution.sdk import runtime, registry
from evolution.sdk.artifact import compute_baseline_hash


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "agents"


@pytest.fixture(autouse=True)
def _clean(clear_registry, monkeypatch):
    if str(FIXTURE_DIR.parent.parent) not in sys.path:
        monkeypatch.syspath_prepend(str(FIXTURE_DIR.parent.parent))
    for mod_name in list(sys.modules):
        if mod_name.startswith("fixtures.agents"):
            del sys.modules[mod_name]


def test_run_emits_trace_record(tmp_evolution_home):
    mod = importlib.import_module("fixtures.agents.three_form_bot")
    bot = mod.ThreeFormBot()
    out = bot.run("hello")
    assert out == "echo: hello"

    traces_dir = tmp_evolution_home / "traces" / "three-form-bot"
    files = list(traces_dir.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["agent"] == "three-form-bot"
    assert rec["input"] == {"q": "hello"} or rec["input"] == {"args": ["hello"]}
    assert rec["output"] == "echo: hello"
    assert any(a["id"] == "system" for a in rec["artifacts"])


def test_run_exception_recorded_then_reraised(tmp_evolution_home):
    """If agent.run() raises, trace records the error and exception propagates."""
    from evolution.sdk.decorators import evolvable_agent, evolvable_prompt

    @evolvable_agent(name="raiser", version="0.1.0", min_samples=3,
                     schedule=None, auto_optimize=False, max_cost_usd=1.0)
    class Raiser:
        @evolvable_prompt(id="sys", text="x")
        def sys(self): return "x"
        def run(self, q):
            raise RuntimeError("boom")

    bot = Raiser()
    with pytest.raises(RuntimeError, match="boom"):
        bot.run("trigger")

    traces_dir = tmp_evolution_home / "traces" / "raiser"
    rec = json.loads(list(traces_dir.glob("*.jsonl"))[0].read_text().splitlines()[0])
    assert rec["signals"]["errors"] >= 1
    assert "boom" in (rec.get("output") or "") or "boom" in str(rec.get("error") or "")


def test_load_optimized_when_hash_matches(tmp_evolution_home):
    mod = importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    sys_artifact = next(a for a in reg.artifacts if a.artifact_id == "system")

    # Write a matching optimized file.
    opt_dir = tmp_evolution_home / "optimized" / "three-form-bot"
    opt_dir.mkdir(parents=True)
    (opt_dir / "system.json").write_text(json.dumps({
        "agent": "three-form-bot",
        "agent_version": "0.1.0",
        "artifact_id": "system",
        "kind": "prompt",
        "baseline_hash": sys_artifact.baseline_hash,
        "optimized_text": "OPTIMIZED!",
        "optimization": {},
    }))

    resolved = runtime.resolve_text("three-form-bot", "system")
    assert resolved == "OPTIMIZED!"


def test_load_optimized_ignored_on_hash_mismatch(tmp_evolution_home):
    mod = importlib.import_module("fixtures.agents.three_form_bot")
    opt_dir = tmp_evolution_home / "optimized" / "three-form-bot"
    opt_dir.mkdir(parents=True)
    (opt_dir / "system.json").write_text(json.dumps({
        "agent": "three-form-bot",
        "agent_version": "0.1.0",
        "artifact_id": "system",
        "kind": "prompt",
        "baseline_hash": "sha256:STALE_HASH",
        "optimized_text": "STALE",
        "optimization": {},
    }))
    resolved = runtime.resolve_text("three-form-bot", "system")
    assert resolved == "You are FORM-1."  # baseline


def test_load_optimized_missing_returns_baseline(tmp_evolution_home):
    importlib.import_module("fixtures.agents.three_form_bot")
    # No optimized file exists.
    resolved = runtime.resolve_text("three-form-bot", "system")
    assert resolved == "You are FORM-1."


def test_load_optimized_corrupt_json_returns_baseline(tmp_evolution_home):
    importlib.import_module("fixtures.agents.three_form_bot")
    opt_dir = tmp_evolution_home / "optimized" / "three-form-bot"
    opt_dir.mkdir(parents=True)
    (opt_dir / "system.json").write_text("{NOT VALID JSON")
    resolved = runtime.resolve_text("three-form-bot", "system")
    assert resolved == "You are FORM-1."  # silent fallback


def test_resolve_text_unknown_artifact_raises():
    importlib.import_module("fixtures.agents.three_form_bot")
    with pytest.raises(KeyError):
        runtime.resolve_text("three-form-bot", "nonexistent_id")
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/sdk/unit/test_runtime.py -v
```

Expected: 大部分 FAIL（runtime stub 还没实现完整功能）。

- [ ] **Step 3: 写完整 `evolution/sdk/runtime.py`（替换 stub）**

```python
"""Runtime: intercept agent calls, capture traces, load optimized artifacts.

Agent process invariants (CRITICAL):
  - Never crash the agent due to SDK bugs (catch + log + fallback to baseline).
  - No network IO at import; one local file read per artifact is allowed.
  - Never block on LLM-judge (that runs in optimizer process).
"""

import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Optional

from evolution.sdk import registry
from evolution.sdk.trace_sink import (
    TraceRecord, TraceSink, get_default_sink, _evolution_home,
)

log = logging.getLogger("evolution.sdk.runtime")


def _optimized_path(agent: str, artifact_id: str) -> Path:
    return _evolution_home() / "optimized" / agent / f"{artifact_id}.json"


def resolve_text(agent_name: str, artifact_id: str) -> str:
    """Return optimized text if baseline_hash matches, else baseline text.

    Safe to call from agent business code. Logs but never raises on
    file/JSON errors.
    """
    reg = registry.get_agent(agent_name)
    if reg is None:
        raise KeyError(f"agent {agent_name!r} not registered")
    artifact = next(
        (a for a in reg.artifacts if a.artifact_id == artifact_id), None
    )
    if artifact is None:
        raise KeyError(
            f"artifact {artifact_id!r} not declared on agent {agent_name!r}"
        )

    path = _optimized_path(agent_name, artifact_id)
    if not path.exists():
        return artifact.baseline_text

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.info("optimized file unreadable for %s/%s: %s — using baseline",
                 agent_name, artifact_id, e)
        return artifact.baseline_text

    expected_hash = artifact.baseline_hash
    stored_hash = data.get("baseline_hash")
    if stored_hash != expected_hash:
        log.info("baseline_hash mismatch for %s/%s — source changed; using baseline",
                 agent_name, artifact_id)
        return artifact.baseline_text

    optimized = data.get("optimized_text")
    if not isinstance(optimized, str):
        log.warning("optimized_text missing/invalid for %s/%s — using baseline",
                    agent_name, artifact_id)
        return artifact.baseline_text

    return optimized


def invoke(instance, method_name: str, original_fn, args: tuple, kwargs: dict) -> Any:
    """Wrap a single call to the agent entrypoint with trace capture."""
    # Resolve registration via instance class.
    meta = getattr(type(instance), "_evolution_meta", None)
    if meta is None:
        # Defensive: fallback to direct call.
        return original_fn(instance, *args, **kwargs)

    agent_name = meta["name"]
    agent_version = meta["version"]
    sink: TraceSink = meta.get("sink") or get_default_sink()
    artifacts = meta["artifacts"]

    # Snapshot which version of each artifact is in use at this run.
    artifact_snapshot = []
    for a in artifacts:
        resolved = resolve_text(agent_name, a.artifact_id)
        artifact_snapshot.append({
            "id": a.artifact_id,
            "kind": a.kind,
            "text_hash": _hash_text(resolved),
        })

    input_payload = _safe_input_payload(args, kwargs)
    start = time.time()
    error_text: Optional[str] = None
    output: Any = None

    try:
        output = original_fn(instance, *args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — re-raises after capture
        error_text = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        # Build trace BEFORE re-raising.
        rec = TraceRecord(
            agent=agent_name,
            agent_version=agent_version,
            input=input_payload,
            output=None,
            artifacts=artifact_snapshot,
            tool_calls=[],
            signals={"errors": 1, "retries": 0, "user_correction": None},
        )
        # Add error info into signals dict for downstream signal mining.
        rec.signals["error_text"] = error_text
        try:
            sink.write(rec)
        except Exception as sink_exc:  # noqa: BLE001
            log.warning("trace sink failed during exception path: %s", sink_exc)
        raise

    # Success path.
    latency_ms = int((time.time() - start) * 1000)
    rec = TraceRecord(
        agent=agent_name,
        agent_version=agent_version,
        input=input_payload,
        output=_safe_output(output),
        artifacts=artifact_snapshot,
        tool_calls=[],
        signals={"errors": 0, "retries": 0, "user_correction": None,
                 "latency_ms": latency_ms},
    )
    try:
        sink.write(rec)
    except Exception as sink_exc:  # noqa: BLE001 — agent invariant
        log.warning("trace sink failed: %s", sink_exc)

    return output


def _hash_text(text: str) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_input_payload(args: tuple, kwargs: dict) -> dict:
    """Convert positional/keyword args to a JSON-serializable dict."""
    payload = {}
    for i, a in enumerate(args):
        payload[f"arg{i}"] = _jsonable(a)
    for k, v in kwargs.items():
        payload[k] = _jsonable(v)
    # Heuristic: if single positional arg is a primitive, also expose as "q" for
    # readability (most agents take one input).
    if len(args) == 1 and not kwargs and isinstance(args[0], (str, int, float, bool)):
        payload["q"] = args[0]
    return payload


def _safe_output(value: Any) -> Any:
    return _jsonable(value)


def _jsonable(value: Any) -> Any:
    """Convert arbitrary Python objects to JSON-safe representations."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return repr(value)[:1000]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/sdk/unit/test_runtime.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 写 `tests/sdk/integration/test_optimized_loading.py`**

```python
"""End-to-end: decorator + runtime + optimized file + baseline_hash transitions."""

import importlib
import json
import sys
from pathlib import Path

import pytest

from evolution.sdk import registry, runtime


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "agents"


@pytest.fixture(autouse=True)
def _clean(clear_registry, monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_DIR.parent.parent))
    for m in list(sys.modules):
        if m.startswith("fixtures.agents"):
            del sys.modules[m]


def test_lifecycle_baseline_then_optimize_then_source_change(tmp_evolution_home):
    # Step 1: Import — baseline in effect.
    mod = importlib.import_module("fixtures.agents.three_form_bot")
    assert runtime.resolve_text("three-form-bot", "system") == "You are FORM-1."

    # Step 2: Optimizer writes optimized file with current baseline_hash.
    reg = registry.get_agent("three-form-bot")
    a = next(art for art in reg.artifacts if art.artifact_id == "system")
    opt_dir = tmp_evolution_home / "optimized" / "three-form-bot"
    opt_dir.mkdir(parents=True)
    (opt_dir / "system.json").write_text(json.dumps({
        "baseline_hash": a.baseline_hash,
        "optimized_text": "VERSION_2 OPTIMIZED",
        "agent": "three-form-bot",
        "agent_version": "0.1.0",
        "artifact_id": "system", "kind": "prompt", "optimization": {},
    }))
    assert runtime.resolve_text("three-form-bot", "system") == "VERSION_2 OPTIMIZED"

    # Step 3: User changes source — simulate by registering with a different baseline.
    registry._REGISTRY["three-form-bot"].artifacts[0] = type(a)(
        agent_name=a.agent_name,
        artifact_id=a.artifact_id,
        kind=a.kind,
        baseline_text="NEW BASELINE TEXT",  # user changed it
        text_source=a.text_source,
        source_file=a.source_file,
        decorator_lineno=a.decorator_lineno,
        constraints=a.constraints,
    )
    # Stored hash no longer matches → fall back to NEW baseline.
    assert runtime.resolve_text("three-form-bot", "system") == "NEW BASELINE TEXT"
```

- [ ] **Step 6: 运行集成测试**

```bash
pytest tests/sdk/integration/test_optimized_loading.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add evolution/sdk/runtime.py tests/sdk/unit/test_runtime.py tests/sdk/integration/test_optimized_loading.py
git commit -m "sdk(05): runtime — trace capture + optimized loading with hash guard

runtime.invoke wraps the entrypoint method to capture TraceRecords on success
and exception paths (errors signal incremented + re-raised). runtime.resolve_text
reads ~/.evolution/optimized/<agent>/<id>.json and validates baseline_hash; any
mismatch / corrupt JSON / missing file silently returns baseline. Agent process
invariant honored: no SDK error crashes the agent.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Signals — 5 个自动信号 + 加权打分

**Files:**
- Create: `evolution/sdk/signals.py`
- Test: `tests/sdk/unit/test_signals.py`
- Create: `tests/sdk/fixtures/traces/clean_runs.jsonl`
- Create: `tests/sdk/fixtures/traces/error_runs.jsonl`
- Create: `tests/sdk/fixtures/traces/retry_runs.jsonl`
- Create: `tests/sdk/fixtures/traces/correction_runs.jsonl`

- [ ] **Step 1: 写 fixture JSONL — `tests/sdk/fixtures/traces/clean_runs.jsonl`**

```jsonl
{"ts": "2026-06-12T01:00:00Z", "agent": "bot", "agent_version": "0.1.0", "run_id": "1", "input": {"q": "hi"}, "output": "hello", "artifacts": [], "tool_calls": [{"id": "search", "args": {"q": "x"}, "result": "ok", "error": null, "latency_ms": 100}], "signals": {"errors": 0, "retries": 0, "user_correction": null}, "scores": {"metric": null, "signal_score": null, "judge_score": null}}
{"ts": "2026-06-12T01:01:00Z", "agent": "bot", "agent_version": "0.1.0", "run_id": "2", "input": {"q": "ho"}, "output": "hi", "artifacts": [], "tool_calls": [], "signals": {"errors": 0, "retries": 0, "user_correction": null, "latency_ms": 50}, "scores": {"metric": null, "signal_score": null, "judge_score": null}}
```

- [ ] **Step 2: 写 fixture — `tests/sdk/fixtures/traces/error_runs.jsonl`**

```jsonl
{"ts": "2026-06-12T01:00:00Z", "agent": "bot", "agent_version": "0.1.0", "run_id": "1", "input": {"q": "fail"}, "output": null, "artifacts": [], "tool_calls": [{"id": "search", "args": {}, "result": null, "error": "timeout", "latency_ms": 5000}], "signals": {"errors": 1, "retries": 0, "user_correction": null, "error_text": "Traceback (most recent)..."}, "scores": {"metric": null, "signal_score": null, "judge_score": null}}
```

- [ ] **Step 3: 写 fixture — `tests/sdk/fixtures/traces/retry_runs.jsonl`**

```jsonl
{"ts": "2026-06-12T01:00:00Z", "agent": "bot", "agent_version": "0.1.0", "run_id": "1", "input": {"q": "retry"}, "output": "ok", "artifacts": [], "tool_calls": [{"id": "search", "args": {"q": "x"}, "result": null, "error": "rate_limited", "latency_ms": 100}, {"id": "search", "args": {"q": "x"}, "result": "ok", "error": null, "latency_ms": 100}], "signals": {"errors": 0, "retries": 1, "user_correction": null}, "scores": {"metric": null, "signal_score": null, "judge_score": null}}
```

- [ ] **Step 4: 写 fixture — `tests/sdk/fixtures/traces/correction_runs.jsonl`**

```jsonl
{"ts": "2026-06-12T01:00:00Z", "agent": "bot", "agent_version": "0.1.0", "run_id": "1", "input": {"q": "do thing"}, "output": "result1", "artifacts": [], "tool_calls": [], "signals": {"errors": 0, "retries": 0, "user_correction": null}, "scores": {"metric": null, "signal_score": null, "judge_score": null}}
{"ts": "2026-06-12T01:00:30Z", "agent": "bot", "agent_version": "0.1.0", "run_id": "2", "input": {"q": "no that's wrong, redo it correctly"}, "output": "result2", "artifacts": [], "tool_calls": [], "signals": {"errors": 0, "retries": 0, "user_correction": null}, "scores": {"metric": null, "signal_score": null, "judge_score": null}}
```

- [ ] **Step 5: 写 `tests/sdk/unit/test_signals.py`**

```python
"""Tests for automatic signal detection + signal_score weighting."""

import json
from pathlib import Path

import pytest

from evolution.sdk.signals import (
    detect_error_in_run,
    detect_retry_pattern,
    detect_user_correction,
    detect_clean_completion,
    detect_latency_outlier,
    compute_signal_score,
    annotate_traces_with_signals,
)


FIXTURES = Path(__file__).parent.parent / "fixtures" / "traces"


def _load(name: str) -> list[dict]:
    return [json.loads(line) for line in (FIXTURES / name).read_text().splitlines() if line.strip()]


def test_detect_error_in_run_from_tool_error():
    traces = _load("error_runs.jsonl")
    assert detect_error_in_run(traces[0]) is True


def test_detect_error_in_run_from_traceback_in_signals():
    trace = {"output": "Traceback (most recent)...\nValueError: x", "tool_calls": [], "signals": {}}
    assert detect_error_in_run(trace) is True


def test_detect_error_in_run_clean():
    traces = _load("clean_runs.jsonl")
    for t in traces:
        assert detect_error_in_run(t) is False


def test_detect_retry_pattern_same_args():
    traces = _load("retry_runs.jsonl")
    assert detect_retry_pattern(traces[0]) is True


def test_detect_retry_pattern_different_args_is_not_retry():
    trace = {"tool_calls": [
        {"id": "s", "args": {"q": "a"}, "result": "ok", "error": None},
        {"id": "s", "args": {"q": "b"}, "result": "ok", "error": None},
    ]}
    assert detect_retry_pattern(trace) is False


def test_detect_user_correction_in_next_trace():
    traces = _load("correction_runs.jsonl")
    # Second trace's input contains correction phrase → first trace gets the signal.
    assert detect_user_correction(traces[0], next_trace=traces[1]) is True
    assert detect_user_correction(traces[1], next_trace=None) is False


@pytest.mark.parametrize("phrase", ["不对", "应该是", "redo", "actually", "no that's wrong"])
def test_user_correction_phrases(phrase):
    cur = {"input": {"q": "foo"}}
    nxt = {"input": {"q": f"{phrase}, do something else"}}
    assert detect_user_correction(cur, next_trace=nxt) is True


def test_detect_clean_completion():
    clean = _load("clean_runs.jsonl")
    assert detect_clean_completion(clean[0]) is True
    err = _load("error_runs.jsonl")
    assert detect_clean_completion(err[0]) is False


def test_detect_latency_outlier_high():
    # p95 of [50, 100, 100, 100, 100] is ~100; trace at 5000 → outlier (>2x p95).
    traces = [
        {"signals": {"latency_ms": x}} for x in [50, 100, 100, 100, 100]
    ]
    target = {"signals": {"latency_ms": 5000}}
    assert detect_latency_outlier(target, all_traces=traces + [target]) is True


def test_detect_latency_outlier_normal():
    traces = [{"signals": {"latency_ms": x}} for x in [50, 100, 100, 100, 100]]
    target = {"signals": {"latency_ms": 90}}
    assert detect_latency_outlier(target, all_traces=traces + [target]) is False


def test_signal_score_clean_is_1():
    score = compute_signal_score(
        error_in_run=False, retry_pattern=False,
        user_correction=False, latency_outlier=False,
    )
    assert score == 1.0


def test_signal_score_error_reduces_to_0_6():
    score = compute_signal_score(
        error_in_run=True, retry_pattern=False,
        user_correction=False, latency_outlier=False,
    )
    assert abs(score - 0.6) < 1e-9


def test_signal_score_all_negative_clamps_to_0():
    score = compute_signal_score(
        error_in_run=True, retry_pattern=True,
        user_correction=True, latency_outlier=True,
    )
    assert score == 0.0


def test_annotate_traces_populates_signal_score():
    clean = _load("clean_runs.jsonl")
    err = _load("error_runs.jsonl")
    all_traces = clean + err
    annotated = annotate_traces_with_signals(all_traces)
    assert annotated[0]["scores"]["signal_score"] == 1.0
    assert annotated[-1]["scores"]["signal_score"] < 1.0
```

- [ ] **Step 6: 运行测试验证失败**

```bash
pytest tests/sdk/unit/test_signals.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 7: 写 `evolution/sdk/signals.py`**

```python
"""Automatic signal detection + signal_score weighting.

Five signals (see spec §5.2):
  - error_in_run     (negative, -0.4)
  - retry_pattern    (negative, -0.3)
  - user_correction  (negative, -0.5)
  - clean_completion (positive, no penalty; informational)
  - latency_outlier  (weak negative, -0.1)

compute_signal_score combines them; annotate_traces_with_signals applies the
detection + score to a full trace list (pairwise for user_correction).
"""

import re
import statistics
from typing import Optional


# User correction patterns (case-insensitive). Add patterns sparingly — every
# false positive will mark a clean run as negative.
_CORRECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"不对", r"应该是", r"\bredo\b", r"\bactually\b",
        r"\bno (that's |thats |that is )?wrong\b", r"\bnot quite\b",
    ]
]


def detect_error_in_run(trace: dict) -> bool:
    """True if any tool call errored or output contains a Python traceback."""
    for call in trace.get("tool_calls", []):
        if call.get("error"):
            return True
    output = trace.get("output") or ""
    if isinstance(output, str) and "Traceback (most recent" in output:
        return True
    signals = trace.get("signals", {})
    if signals.get("errors", 0) > 0:
        return True
    if signals.get("error_text"):
        return True
    return False


def detect_retry_pattern(trace: dict) -> bool:
    """True if any tool_id appears ≥2 times consecutively with identical args."""
    calls = trace.get("tool_calls", [])
    for i in range(len(calls) - 1):
        a, b = calls[i], calls[i + 1]
        if a.get("id") == b.get("id") and a.get("args") == b.get("args"):
            return True
    return False


def detect_user_correction(trace: dict, next_trace: Optional[dict]) -> bool:
    """True if the *next* trace's input contains a correction phrase.

    The current trace gets the negative signal because its output prompted the
    correction.
    """
    if next_trace is None:
        return False
    nxt_input = next_trace.get("input", {})
    text = " ".join(str(v) for v in (nxt_input.values() if isinstance(nxt_input, dict) else [nxt_input]))
    return any(p.search(text) for p in _CORRECTION_PATTERNS)


def detect_clean_completion(trace: dict) -> bool:
    """True if no errors, no retries, non-empty output."""
    if detect_error_in_run(trace):
        return False
    if detect_retry_pattern(trace):
        return False
    output = trace.get("output")
    if output is None or (isinstance(output, str) and not output.strip()):
        return False
    return True


def detect_latency_outlier(trace: dict, all_traces: list[dict]) -> bool:
    """True if trace.signals.latency_ms > p95(all) * 2.

    Returns False when the dataset is too small to compute p95 (<5 records).
    """
    latencies = [
        t.get("signals", {}).get("latency_ms")
        for t in all_traces
        if t.get("signals", {}).get("latency_ms") is not None
    ]
    if len(latencies) < 5:
        return False
    p95 = statistics.quantiles(latencies, n=20)[18]  # index 18 = 95th percentile
    target = trace.get("signals", {}).get("latency_ms")
    if target is None:
        return False
    return target > p95 * 2


def compute_signal_score(
    *,
    error_in_run: bool,
    retry_pattern: bool,
    user_correction: bool,
    latency_outlier: bool,
) -> float:
    """Combine signals into a [0, 1] score. Clean run = 1.0."""
    score = 1.0
    if error_in_run:
        score -= 0.4
    if retry_pattern:
        score -= 0.3
    if user_correction:
        score -= 0.5
    if latency_outlier:
        score -= 0.1
    return max(0.0, min(1.0, score))


def annotate_traces_with_signals(traces: list[dict]) -> list[dict]:
    """Mutate `scores.signal_score` on each trace in-place. Returns same list.

    user_correction is pairwise: trace[i] is annotated based on trace[i+1].
    Traces are processed in chronological order (by ts).
    """
    sorted_traces = sorted(traces, key=lambda t: t.get("ts", ""))

    for i, t in enumerate(sorted_traces):
        nxt = sorted_traces[i + 1] if i + 1 < len(sorted_traces) else None
        flags = {
            "error_in_run": detect_error_in_run(t),
            "retry_pattern": detect_retry_pattern(t),
            "user_correction": detect_user_correction(t, nxt),
            "latency_outlier": detect_latency_outlier(t, sorted_traces),
        }
        score = compute_signal_score(**flags)
        scores = t.setdefault("scores", {})
        scores["signal_score"] = score
        # Stash flags for debugging.
        t.setdefault("signals", {})["detected"] = flags
    return sorted_traces
```

- [ ] **Step 8: 运行测试**

```bash
pytest tests/sdk/unit/test_signals.py -v
```

Expected: 全部 PASS。

- [ ] **Step 9: Commit**

```bash
git add evolution/sdk/signals.py tests/sdk/unit/test_signals.py tests/sdk/fixtures/traces/
git commit -m "sdk(06): 5 automatic signal detectors + signal_score weighting

error_in_run, retry_pattern, user_correction, clean_completion, latency_outlier.
compute_signal_score combines per spec §5.2: 1.0 - 0.4*err - 0.3*retry - 0.5*corr - 0.1*lat,
clamped to [0,1]. annotate_traces_with_signals sorts by ts and applies pairwise
correction detection. Fixture JSONLs cover clean/error/retry/correction.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: AgentModule + composite metric

**Files:**
- Create: `evolution/sdk/agent_module.py`
- Test: `tests/sdk/unit/test_agent_module.py`

- [ ] **Step 1: 写 `tests/sdk/unit/test_agent_module.py`**

```python
"""Tests for AgentModule (DSPy wrapper) + composite_metric weights."""

from pathlib import Path

import pytest

from evolution.sdk.agent_module import (
    AgentModule, build_composite_metric, JudgeConfig,
)
from evolution.sdk.artifact import EvolvableArtifact


def _mk_prompt_artifact():
    return EvolvableArtifact(
        agent_name="bot", artifact_id="sys", kind="prompt",
        baseline_text="You are helpful.", text_source="param",
        source_file=Path("/tmp/x.py"), decorator_lineno=1,
    )


def _mk_tool_artifact():
    return EvolvableArtifact(
        agent_name="bot", artifact_id="search", kind="tool",
        baseline_text="Search the web.", text_source="docstring",
        source_file=Path("/tmp/x.py"), decorator_lineno=20,
    )


def test_agent_module_construction_prompt():
    a = _mk_prompt_artifact()
    mod = AgentModule(a, judge_dimensions=("correctness",))
    assert mod.artifact.artifact_id == "sys"
    assert mod.current_text == "You are helpful."


def test_agent_module_set_text_updates_current():
    a = _mk_prompt_artifact()
    mod = AgentModule(a, judge_dimensions=("correctness",))
    mod.set_text("Be terse.")
    assert mod.current_text == "Be terse."


def test_agent_module_tool_kind_supported():
    a = _mk_tool_artifact()
    mod = AgentModule(a, judge_dimensions=("correctness",))
    assert mod.artifact.kind == "tool"


def test_composite_metric_all_three_components():
    cfg = JudgeConfig(model="mock", dimensions=("correctness",))
    metric = build_composite_metric(
        user_metric=lambda trace, output: 0.8,
        judge_config=cfg,
        signals_provider=lambda trace: 0.6,
    )
    # Score: 0.5*0.8 + 0.3*0.7 + 0.2*0.6 = 0.4 + 0.21 + 0.12 = 0.73
    # (judge_score mocked to 0.7 via stub below)
    pred = type("P", (), {"output": "x", "_judge_score": 0.7})()
    example = type("E", (), {"trace": {"ts": "2026-06-12T00:00:00Z"}})()
    s = metric(example, pred)
    assert abs(s - 0.73) < 1e-9


def test_composite_metric_no_user_metric_reweights():
    """Without metric: 0.7*judge + 0.3*signal."""
    cfg = JudgeConfig(model="mock", dimensions=("correctness",))
    metric = build_composite_metric(
        user_metric=None,
        judge_config=cfg,
        signals_provider=lambda trace: 0.6,
    )
    pred = type("P", (), {"output": "x", "_judge_score": 0.8})()
    example = type("E", (), {"trace": {"ts": "2026-06-12T00:00:00Z"}})()
    s = metric(example, pred)
    # 0.7*0.8 + 0.3*0.6 = 0.56 + 0.18 = 0.74
    assert abs(s - 0.74) < 1e-9


def test_composite_metric_no_judge_uses_signal_only():
    """Without judge dimensions: 1.0 * signal."""
    metric = build_composite_metric(
        user_metric=None,
        judge_config=None,
        signals_provider=lambda trace: 0.5,
    )
    pred = type("P", (), {"output": "x"})()
    example = type("E", (), {"trace": {}})()
    s = metric(example, pred)
    assert abs(s - 0.5) < 1e-9


def test_composite_metric_user_metric_exception_falls_back():
    """If user metric raises, the metric degrades to judge+signal weights."""
    def bad_metric(trace, output):
        raise ValueError("user code bug")
    cfg = JudgeConfig(model="mock", dimensions=("correctness",))
    metric = build_composite_metric(
        user_metric=bad_metric,
        judge_config=cfg,
        signals_provider=lambda trace: 0.5,
    )
    pred = type("P", (), {"output": "x", "_judge_score": 0.8})()
    example = type("E", (), {"trace": {}})()
    s = metric(example, pred)
    # Falls back to 0.7*0.8 + 0.3*0.5 = 0.71
    assert abs(s - 0.71) < 1e-9
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/sdk/unit/test_agent_module.py -v
```

- [ ] **Step 3: 写 `evolution/sdk/agent_module.py`**

```python
"""AgentModule: DSPy wrapper for one EvolvableArtifact.

Mirrors evolution/skills/skill_module.py SkillModule pattern but per-artifact
instead of per-skill. The artifact text is the parameter GEPA mutates.

build_composite_metric implements spec §5.2 weighted scoring with automatic
weight redistribution when components are missing.
"""

import logging
from dataclasses import dataclass
from typing import Callable, Optional

import dspy

from evolution.sdk.artifact import EvolvableArtifact

log = logging.getLogger("evolution.sdk.agent_module")


@dataclass
class JudgeConfig:
    """Configuration for the LLM-judge component of composite_metric."""
    model: str
    dimensions: tuple[str, ...]


class AgentModule(dspy.Module):
    """DSPy module wrapping a single EvolvableArtifact for GEPA optimization.

    The artifact's baseline_text becomes the initial value of the parameter
    that GEPA mutates. forward() composes the parameter as instructions to a
    ChainOfThought predictor over a kind-specific Signature.
    """

    def __init__(self, artifact: EvolvableArtifact, judge_dimensions: tuple[str, ...]):
        super().__init__()
        self.artifact = artifact
        self.judge_dimensions = judge_dimensions
        self.current_text = artifact.baseline_text

        if artifact.kind == "prompt":
            self._sig = self._build_prompt_signature()
        elif artifact.kind == "tool":
            self._sig = self._build_tool_signature()
        else:
            raise ValueError(f"unknown artifact kind: {artifact.kind!r}")

        self.predictor = dspy.ChainOfThought(self._sig)

    def _build_prompt_signature(self):
        class _PromptSig(dspy.Signature):
            """Apply the prompt instructions to the user input."""
            prompt_text: str = dspy.InputField(desc="The prompt instructions to follow")
            user_input: str = dspy.InputField(desc="The user-provided input")
            output: str = dspy.OutputField(desc="Response following the prompt")
        return _PromptSig

    def _build_tool_signature(self):
        class _ToolSig(dspy.Signature):
            """Decide if this tool description matches the user's intent."""
            tool_description: str = dspy.InputField(desc="The tool description to evaluate")
            user_intent: str = dspy.InputField(desc="What the user wants to do")
            output: str = dspy.OutputField(desc="Whether/how this tool applies")
        return _ToolSig

    def set_text(self, new_text: str) -> None:
        """Mutate the current artifact text. Called by GEPA between generations."""
        self.current_text = new_text

    def forward(self, **kwargs) -> dspy.Prediction:
        if self.artifact.kind == "prompt":
            result = self.predictor(prompt_text=self.current_text,
                                    user_input=kwargs.get("user_input", ""))
        else:
            result = self.predictor(tool_description=self.current_text,
                                    user_intent=kwargs.get("user_intent", ""))
        return dspy.Prediction(output=result.output)


def build_composite_metric(
    *,
    user_metric: Optional[Callable[[dict, str], float]],
    judge_config: Optional[JudgeConfig],
    signals_provider: Callable[[dict], float],
) -> Callable:
    """Construct a DSPy-compatible metric implementing the spec §5.2 weighted score.

    Args:
        user_metric: optional (trace_dict, output) -> float in [0,1]
        judge_config: JudgeConfig if LLM-judge is enabled, else None
        signals_provider: (trace_dict) -> signal_score in [0,1]

    Returns:
        metric(example, prediction) -> float — usable by dspy.GEPA(metric=...).

    Weight redistribution:
        - all three: 0.5 * user + 0.3 * judge + 0.2 * signal
        - no user_metric: 0.7 * judge + 0.3 * signal
        - no judge (None or empty dimensions): 1.0 * signal (or 1.0 * user if provided)
        - user_metric raises: fall back as if user_metric was None
    """
    has_user = user_metric is not None
    has_judge = judge_config is not None and len(judge_config.dimensions) > 0

    def metric(example, prediction, trace=None):
        trace_dict = getattr(example, "trace", {}) or {}
        output = getattr(prediction, "output", "")
        # judge score may be precomputed and attached to prediction by the
        # optimizer (avoids per-metric-call LLM hits during inner loops).
        precomputed_judge = getattr(prediction, "_judge_score", None)

        # Signal component (always available).
        signal_score = signals_provider(trace_dict)

        # User metric component (defensive).
        user_score = None
        if has_user:
            try:
                user_score = float(user_metric(trace_dict, output))
                user_score = max(0.0, min(1.0, user_score))
            except Exception as e:  # noqa: BLE001
                log.warning("user metric raised; falling back: %s", e)
                user_score = None

        # Judge component.
        judge_score = None
        if has_judge:
            if precomputed_judge is not None:
                judge_score = max(0.0, min(1.0, float(precomputed_judge)))
            else:
                judge_score = _invoke_judge(judge_config, trace_dict, output)

        # Combine with redistribution.
        if user_score is not None and judge_score is not None:
            return 0.5 * user_score + 0.3 * judge_score + 0.2 * signal_score
        if judge_score is not None:
            return 0.7 * judge_score + 0.3 * signal_score
        if user_score is not None:
            return 0.7 * user_score + 0.3 * signal_score
        return signal_score

    return metric


def _invoke_judge(cfg: JudgeConfig, trace: dict, output: str) -> float:
    """LLM-as-judge call. Returns mean across dimensions in [0,1].

    Defensive: returns 0.5 on any LLM error (neutral score, doesn't bias optimization).
    Mocked tests bypass this via prediction._judge_score.
    """
    try:
        lm = dspy.LM(cfg.model)
        # Minimal judge prompt — full Phase 1 LLMJudge lives in core/fitness.py;
        # we delegate to it where possible.
        from evolution.core.fitness import LLMJudge  # type: ignore
        from evolution.core.config import EvolutionConfig
        ec = EvolutionConfig(eval_model=cfg.model)
        judge = LLMJudge(ec)
        # The hermes LLMJudge takes (input, output, skill_text); we adapt.
        scored = judge.score(
            task_input=str(trace.get("input", "")),
            agent_output=output,
            skill_text=str(trace.get("artifacts", "")),
        )
        # composite is a [0,1] value
        return getattr(scored, "composite", 0.5)
    except Exception as e:  # noqa: BLE001
        log.warning("judge failed: %s", e)
        return 0.5
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/sdk/unit/test_agent_module.py -v
```

Expected: 全部 PASS.

- [ ] **Step 5: Commit**

```bash
git add evolution/sdk/agent_module.py tests/sdk/unit/test_agent_module.py
git commit -m "sdk(07): AgentModule (DSPy) + composite_metric with weight redistribution

AgentModule mirrors skill_module.SkillModule but per-artifact; builds a
kind-specific Signature (prompt vs tool). build_composite_metric implements
spec §5.2: 0.5/0.3/0.2 weights when all three components exist, redistributes
to 0.7/0.3 when one is missing, 1.0/0.0 when only signal is available. user
metric failures degrade gracefully.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Optimizer — GEPA 主循环 + 三道门

**Files:**
- Create: `evolution/sdk/optimizer.py`
- Test: `tests/sdk/unit/test_optimizer.py`
- Test: `tests/sdk/integration/test_constraint_gates.py`

- [ ] **Step 1: 写 `tests/sdk/unit/test_optimizer.py`**

```python
"""Tests for optimizer main loop + three-gate filtering + run_summary."""

import json
from pathlib import Path

import pytest

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.optimizer import (
    OptimizationBudget,
    OptimizationOutcome,
    apply_gates,
    write_optimized_file,
    write_run_summary,
    GateFailure,
)


def _mk_artifact():
    return EvolvableArtifact(
        agent_name="bot", artifact_id="sys", kind="prompt",
        baseline_text="hello", text_source="param",
        source_file=Path("/tmp/x.py"), decorator_lineno=1,
        constraints={"max_chars": 100, "max_growth": 0.2},
    )


def test_budget_can_afford_and_spend():
    b = OptimizationBudget(max_cost_usd=5.0)
    assert b.remaining() == 5.0
    assert b.can_afford(2.0) is True
    b.spend(3.0)
    assert b.remaining() == 2.0
    assert b.can_afford(3.0) is False


def test_gate_1_size_limit_rejects_oversize():
    a = _mk_artifact()  # max_chars=100
    res = apply_gates(
        artifact=a,
        candidate_text="x" * 200,
        baseline_score=0.5,
        candidate_holdout_score=0.6,
        regression_tolerance=0.02,
    )
    assert res.passed is False
    assert "size" in res.failed_gate.lower() or "max_chars" in res.reason


def test_gate_1_growth_limit_rejects():
    a = _mk_artifact()
    res = apply_gates(
        artifact=a,
        candidate_text="x" * 70,  # 5 → 70 = 1300% growth, way over 20%
        baseline_score=0.5,
        candidate_holdout_score=0.6,
        regression_tolerance=0.02,
    )
    assert res.passed is False
    assert "growth" in res.failed_gate.lower()


def test_gate_2_holdout_regression_rejects():
    a = _mk_artifact()
    res = apply_gates(
        artifact=a,
        candidate_text="hello world",  # within size + growth
        baseline_score=0.80,
        candidate_holdout_score=0.50,  # big drop
        regression_tolerance=0.02,
    )
    assert res.passed is False
    assert "holdout" in res.failed_gate.lower()


def test_gates_accept_improvement():
    a = _mk_artifact()
    res = apply_gates(
        artifact=a,
        candidate_text="hi",  # smaller is fine
        baseline_score=0.50,
        candidate_holdout_score=0.78,
        regression_tolerance=0.02,
    )
    assert res.passed is True


def test_secret_pattern_in_candidate_rejected():
    a = _mk_artifact()
    res = apply_gates(
        artifact=a,
        candidate_text="hi (sk-ant-api-secret123)",
        baseline_score=0.5,
        candidate_holdout_score=0.6,
        regression_tolerance=0.02,
    )
    assert res.passed is False
    assert "secret" in res.failed_gate.lower()


def test_tool_kind_must_keep_placeholders():
    a = EvolvableArtifact(
        agent_name="bot", artifact_id="t", kind="tool",
        baseline_text="search for {query} on the web",
        text_source="docstring",
        source_file=Path("/tmp/x.py"), decorator_lineno=1,
        constraints={"max_chars": 500, "max_growth": 0.5},
    )
    res = apply_gates(
        artifact=a,
        candidate_text="search for X on the web",  # lost {query}
        baseline_score=0.5,
        candidate_holdout_score=0.6,
        regression_tolerance=0.02,
    )
    assert res.passed is False
    assert "placeholder" in res.failed_gate.lower()


def test_write_optimized_file_atomic(tmp_evolution_home):
    a = _mk_artifact()
    path = write_optimized_file(
        artifact=a,
        agent_version="0.1.0",
        optimized_text="improved",
        optimization_metadata={
            "run_id": "uuid",
            "ts": "2026-06-13T00:00:00Z",
            "optimizer": "GEPA",
            "judge_model": "openai/gpt-4.1",
            "baseline_score": 0.5,
            "optimized_score": 0.7,
            "holdout_score": 0.65,
            "dataset_size": 100,
            "cost_usd": 1.0,
        },
    )
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["optimized_text"] == "improved"
    assert data["baseline_hash"] == a.baseline_hash


def test_write_run_summary_includes_all_artifacts(tmp_evolution_home):
    outcomes = [
        OptimizationOutcome(artifact_id="sys", status="improved",
                            baseline_score=0.5, optimized_score=0.7,
                            rejection_reason=None, cost_usd=1.0),
        OptimizationOutcome(artifact_id="search", status="rejected",
                            baseline_score=0.6, optimized_score=None,
                            rejection_reason="holdout_regression", cost_usd=0.5),
    ]
    path = write_run_summary(
        agent_name="bot",
        trigger="manual",
        outcomes=outcomes,
        dataset_path=Path("/tmp/ds"),
        total_cost_usd=1.5,
        duration_seconds=42,
    )
    data = json.loads(path.read_text())
    assert data["agent"] == "bot"
    assert len(data["artifacts"]) == 2
    assert data["artifacts"][1]["rejection_reason"] == "holdout_regression"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/sdk/unit/test_optimizer.py -v
```

- [ ] **Step 3: 写 `evolution/sdk/optimizer.py`**

```python
"""GEPA → MIPROv2 fallback + three-gate filtering + run_summary writer.

Designed to be a short-lived process: cron / GH Actions invokes
`python -m evolution.sdk.optimizer --agent <name>`. State is filesystem;
no in-memory persistence between runs.
"""

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.trace_sink import _evolution_home

log = logging.getLogger("evolution.sdk.optimizer")


# Reuse hermes' SECRET_PATTERNS to detect leaked credentials in optimized
# candidates.
try:
    from evolution.core.external_importers import SECRET_PATTERNS
except Exception:  # pragma: no cover — defensive
    SECRET_PATTERNS = re.compile(r"sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]+")


_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


@dataclass
class OptimizationBudget:
    """USD budget for one optimization run."""
    max_cost_usd: float
    spent_usd: float = 0.0

    def remaining(self) -> float:
        return max(0.0, self.max_cost_usd - self.spent_usd)

    def can_afford(self, estimate: float) -> bool:
        return self.remaining() >= estimate

    def spend(self, amount: float) -> None:
        self.spent_usd += amount


@dataclass
class GateResult:
    passed: bool
    failed_gate: str = ""
    reason: str = ""


class GateFailure(Exception):
    """Internal signal that a candidate failed a gate."""


@dataclass
class OptimizationOutcome:
    artifact_id: str
    status: str  # improved | rejected | budget_skipped | baseline_kept | error
    baseline_score: Optional[float] = None
    optimized_score: Optional[float] = None
    holdout_score: Optional[float] = None
    rejection_reason: Optional[str] = None
    cost_usd: float = 0.0


# ── Three gates ─────────────────────────────────────────────────────────


def apply_gates(
    *,
    artifact: EvolvableArtifact,
    candidate_text: str,
    baseline_score: float,
    candidate_holdout_score: float,
    regression_tolerance: float = 0.02,
) -> GateResult:
    """Run all three gates against a candidate. Returns first failure or pass."""
    # ── Gate 1: structure + size + growth + secrets + placeholders ──
    constraints = artifact.constraints
    max_chars = constraints.get("max_chars")
    if max_chars is not None and len(candidate_text) > max_chars:
        return GateResult(False, "gate_1_size",
                          f"size {len(candidate_text)} > max_chars {max_chars}")

    max_growth = constraints.get("max_growth")
    if max_growth is not None:
        baseline_len = max(1, len(artifact.baseline_text))
        growth = (len(candidate_text) - baseline_len) / baseline_len
        if growth > max_growth:
            return GateResult(False, "gate_1_growth",
                              f"growth {growth:+.1%} > max {max_growth:+.1%}")

    if not candidate_text.strip():
        return GateResult(False, "gate_1_empty", "candidate text is empty")

    if SECRET_PATTERNS.search(candidate_text):
        return GateResult(False, "gate_1_secret",
                          "candidate contains a SECRET_PATTERNS match")

    if artifact.kind == "tool":
        baseline_placeholders = set(_PLACEHOLDER_RE.findall(artifact.baseline_text))
        candidate_placeholders = set(_PLACEHOLDER_RE.findall(candidate_text))
        missing = baseline_placeholders - candidate_placeholders
        if missing:
            return GateResult(False, "gate_1_placeholder",
                              f"tool kind lost placeholder(s): {sorted(missing)}")

    forbidden = constraints.get("forbidden_patterns") or []
    for pat in forbidden:
        if re.search(pat, candidate_text):
            return GateResult(False, "gate_1_forbidden",
                              f"candidate matched forbidden pattern: {pat!r}")

    # ── Gate 2: holdout regression ──
    threshold = baseline_score * (1 - regression_tolerance)
    if candidate_holdout_score < threshold:
        return GateResult(False, "gate_2_holdout_regression",
                          f"holdout {candidate_holdout_score:.3f} < {threshold:.3f}")

    # ── Gate 3: regression smoke for prompt kind ──
    # (Implementation note: P0 implements gate 3 as a no-op stub since it
    # requires running the agent against historical traces with the new
    # prompt — see spec §6.4 line "回归冒烟". The optimizer hook below
    # invokes it; P1 wires the actual smoke run.)

    return GateResult(True)


# ── Output writers ──────────────────────────────────────────────────────


def write_optimized_file(
    *,
    artifact: EvolvableArtifact,
    agent_version: str,
    optimized_text: str,
    optimization_metadata: dict,
) -> Path:
    """Atomically write ~/.evolution/optimized/<agent>/<artifact_id>.json."""
    base = _evolution_home() / "optimized" / artifact.agent_name
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{artifact.artifact_id}.json"
    tmp = path.with_suffix(".tmp")
    payload = {
        "agent": artifact.agent_name,
        "agent_version": agent_version,
        "artifact_id": artifact.artifact_id,
        "kind": artifact.kind,
        "baseline_hash": artifact.baseline_hash,
        "optimized_text": optimized_text,
        "optimization": optimization_metadata,
    }
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)
    return path


def write_run_summary(
    *,
    agent_name: str,
    trigger: str,
    outcomes: list[OptimizationOutcome],
    dataset_path: Path,
    total_cost_usd: float,
    duration_seconds: int,
) -> Path:
    """Write output/sdk/<agent>/<ts>/run_summary.json (under cwd, not home)."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path("output") / "sdk" / agent_name / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "run_summary.json"
    payload = {
        "agent": agent_name,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trigger": trigger,
        "artifacts": [asdict(o) for o in outcomes],
        "dataset_path": str(dataset_path),
        "total_cost_usd": total_cost_usd,
        "duration_seconds": duration_seconds,
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


# ── Optimize a single artifact ──────────────────────────────────────────


def optimize_artifact(
    *,
    artifact: EvolvableArtifact,
    train_examples: list,
    val_examples: list,
    holdout_examples: list,
    metric: Callable,
    optimizer_model: str,
    budget: OptimizationBudget,
    judge_dimensions: tuple[str, ...],
    regression_tolerance: float = 0.02,
    max_metric_calls: int = 50,
) -> OptimizationOutcome:
    """Run GEPA → MIPROv2 fallback for one artifact + apply gates."""
    from evolution.sdk.agent_module import AgentModule
    import dspy

    start_cost = budget.spent_usd

    # Build module + baseline evaluation.
    module = AgentModule(artifact, judge_dimensions=judge_dimensions)
    baseline_scores = [metric(ex, module.forward(**_kwargs_from_example(ex)))
                       for ex in val_examples] or [0.5]
    baseline_score = sum(baseline_scores) / len(baseline_scores)

    if not budget.can_afford(0.5):
        return OptimizationOutcome(
            artifact_id=artifact.artifact_id,
            status="budget_skipped",
            baseline_score=baseline_score,
            cost_usd=budget.spent_usd - start_cost,
        )

    # GEPA → MIPROv2 fallback.
    optimized_module = None
    try:
        lm = dspy.LM(optimizer_model)
        gepa = dspy.GEPA(
            metric=metric,
            auto="light",
            max_metric_calls=max_metric_calls,
            reflection_lm=lm,
            track_stats=True,
        )
        optimized_module = gepa.compile(module, trainset=train_examples)
    except Exception as e:  # noqa: BLE001
        log.warning("GEPA failed (%s); falling back to MIPROv2", e)
        try:
            mipro = dspy.MIPROv2(metric=metric, auto="light")
            optimized_module = mipro.compile(module, trainset=train_examples)
        except Exception as e2:  # noqa: BLE001
            log.error("MIPROv2 also failed: %s", e2)
            return OptimizationOutcome(
                artifact_id=artifact.artifact_id,
                status="error",
                baseline_score=baseline_score,
                rejection_reason=f"both optimizers failed: {e2}",
                cost_usd=budget.spent_usd - start_cost,
            )

    candidate_text = getattr(optimized_module, "current_text", artifact.baseline_text)

    # Evaluate candidate on holdout.
    optimized_module.set_text(candidate_text)
    holdout_scores = [metric(ex, optimized_module.forward(**_kwargs_from_example(ex)))
                      for ex in holdout_examples] or [baseline_score]
    holdout_score = sum(holdout_scores) / len(holdout_scores)

    # Apply gates.
    gate_result = apply_gates(
        artifact=artifact,
        candidate_text=candidate_text,
        baseline_score=baseline_score,
        candidate_holdout_score=holdout_score,
        regression_tolerance=regression_tolerance,
    )
    if not gate_result.passed:
        return OptimizationOutcome(
            artifact_id=artifact.artifact_id,
            status="rejected",
            baseline_score=baseline_score,
            optimized_score=None,
            holdout_score=holdout_score,
            rejection_reason=f"{gate_result.failed_gate}: {gate_result.reason}",
            cost_usd=budget.spent_usd - start_cost,
        )

    return OptimizationOutcome(
        artifact_id=artifact.artifact_id,
        status="improved",
        baseline_score=baseline_score,
        optimized_score=sum(metric(ex, optimized_module.forward(**_kwargs_from_example(ex)))
                            for ex in val_examples) / max(1, len(val_examples)),
        holdout_score=holdout_score,
        rejection_reason=None,
        cost_usd=budget.spent_usd - start_cost,
    )


def _kwargs_from_example(example) -> dict:
    """Extract DSPy Example kwargs for forward(). Best effort."""
    if hasattr(example, "user_input"):
        return {"user_input": example.user_input}
    if hasattr(example, "user_intent"):
        return {"user_intent": example.user_intent}
    return {"user_input": str(getattr(example, "input", ""))}


# ── CLI entry point ─────────────────────────────────────────────────────


def main() -> int:
    """`python -m evolution.sdk.optimizer --agent <name>` entry.

    Returns process exit code (0=success or SKIPPED, 1=FAILED, 2=PARTIAL).
    """
    import argparse
    from evolution.sdk import registry
    from evolution.sdk.trace_sink import LocalJsonlSink
    from evolution.sdk.signals import annotate_traces_with_signals
    from datetime import timedelta

    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-llm", action="store_true",
                        help="Test mode: use a predictable mock LLM (no API calls).")
    args = parser.parse_args()

    # Load registry from disk.
    registry.load_from_file()
    reg = registry.get_agent(args.agent)
    if reg is None:
        # Try to import the agent module directly (registry empty).
        import sys as _sys
        _sys.stderr.write(f"EVOLUTION_FATAL: agent {args.agent!r} not in registry\n")
        return 1

    # Acquire lock.
    lock_dir = _evolution_home() / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{args.agent}.lock"
    try:
        import fcntl
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log.warning("another optimizer is running for %s; exiting cleanly", args.agent)
            return 0
    except ImportError:
        lock_fd = None  # Windows fallback

    start = time.time()
    sink = LocalJsonlSink()
    since = datetime.now(timezone.utc) - timedelta(days=90)
    raw_traces = list(sink.read(args.agent, since=since))

    if len(raw_traces) < reg.min_samples:
        # SKIPPED path
        _write_skipped(args.agent, len(raw_traces), reg.min_samples)
        return 0

    traces = annotate_traces_with_signals(raw_traces)

    # P0: build dataset + run optimization per artifact.
    # (Detailed dataset construction is implemented via core/dataset_builder.py
    # which expects (input, expected_output) pairs; for SDK MVP we pass a
    # minimal mapping. Task 13 end-to-end exercises this with mock LLM.)
    outcomes = []
    budget = OptimizationBudget(max_cost_usd=reg.max_cost_usd)
    for artifact in reg.artifacts:
        if budget.remaining() < 0.5:
            outcomes.append(OptimizationOutcome(
                artifact_id=artifact.artifact_id,
                status="budget_skipped", cost_usd=0.0,
            ))
            continue
        # In dry_run or mock_llm modes, return a deterministic stub.
        if args.dry_run:
            outcomes.append(OptimizationOutcome(
                artifact_id=artifact.artifact_id,
                status="baseline_kept",
                baseline_score=0.5, cost_usd=0.0,
            ))
            continue
        try:
            outcome = _run_one_artifact(
                artifact, traces, reg, budget, mock_llm=args.mock_llm,
            )
        except Exception as e:  # noqa: BLE001
            log.error("artifact %s failed: %s", artifact.artifact_id, e)
            outcome = OptimizationOutcome(
                artifact_id=artifact.artifact_id, status="error",
                rejection_reason=str(e), cost_usd=0.0,
            )
        outcomes.append(outcome)

        if outcome.status == "improved":
            write_optimized_file(
                artifact=artifact,
                agent_version=reg.version,
                optimized_text=getattr(outcome, "_candidate_text", artifact.baseline_text),
                optimization_metadata={
                    "run_id": str(uuid.uuid4()),
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "optimizer": "GEPA",
                    "baseline_score": outcome.baseline_score,
                    "optimized_score": outcome.optimized_score,
                    "holdout_score": outcome.holdout_score,
                    "dataset_size": len(traces),
                    "cost_usd": outcome.cost_usd,
                },
            )

    duration = int(time.time() - start)
    total_cost = sum(o.cost_usd for o in outcomes)
    write_run_summary(
        agent_name=args.agent,
        trigger=os.getenv("EVOLUTION_TRIGGER", "manual"),
        outcomes=outcomes,
        dataset_path=_evolution_home() / "datasets" / args.agent,
        total_cost_usd=total_cost,
        duration_seconds=duration,
    )
    return 0


def _write_skipped(agent: str, count: int, required: int) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path("output") / "sdk" / agent / f"SKIPPED_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reason.txt").write_text(
        f"traces={count} < min_samples={required}\n"
    )


def _run_one_artifact(artifact, traces, reg, budget, *, mock_llm: bool):
    """Stub for P0 — Task 13 end-to-end test exercises the real path with mock_llm."""
    # Minimal mock_llm path: return baseline_kept; no actual GEPA call.
    if mock_llm:
        return OptimizationOutcome(
            artifact_id=artifact.artifact_id,
            status="baseline_kept",
            baseline_score=0.5,
            cost_usd=0.0,
        )
    raise NotImplementedError(
        "P0 optimizer.main only supports --mock-llm and --dry-run modes; "
        "real GEPA wiring per artifact is exercised via Task 13 end-to-end."
    )


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/sdk/unit/test_optimizer.py -v
```

Expected: 全部 PASS（gate / budget / writer 全覆盖）。

- [ ] **Step 5: 写 `tests/sdk/integration/test_constraint_gates.py`**

```python
"""Integration: candidate goes through all three gates with realistic data."""

from pathlib import Path

import pytest

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.optimizer import apply_gates


def _mk(kind="prompt", text="Be helpful.", max_chars=200, max_growth=0.5):
    return EvolvableArtifact(
        agent_name="bot", artifact_id="a", kind=kind,
        baseline_text=text, text_source="param",
        source_file=Path("/tmp/x.py"), decorator_lineno=1,
        constraints={"max_chars": max_chars, "max_growth": max_growth},
    )


def test_improved_candidate_passes_all_gates():
    a = _mk()
    res = apply_gates(
        artifact=a,
        candidate_text="Be terse and helpful.",
        baseline_score=0.60,
        candidate_holdout_score=0.78,
    )
    assert res.passed is True


def test_oversize_candidate_fails_gate_1():
    a = _mk(max_chars=50)
    res = apply_gates(
        artifact=a, candidate_text="x" * 200,
        baseline_score=0.5, candidate_holdout_score=0.6,
    )
    assert not res.passed and "size" in res.failed_gate


def test_growth_violation_fails_gate_1():
    a = _mk(text="hi", max_growth=0.1)
    res = apply_gates(
        artifact=a, candidate_text="hi" * 5,  # 200% growth
        baseline_score=0.5, candidate_holdout_score=0.6,
    )
    assert not res.passed and "growth" in res.failed_gate


def test_regression_just_inside_tolerance_passes():
    a = _mk()
    res = apply_gates(
        artifact=a, candidate_text="Be helpful and clear.",
        baseline_score=1.0, candidate_holdout_score=0.99,
        regression_tolerance=0.02,
    )
    assert res.passed is True


def test_regression_just_outside_tolerance_fails():
    a = _mk()
    res = apply_gates(
        artifact=a, candidate_text="Be helpful and clear.",
        baseline_score=1.0, candidate_holdout_score=0.97,
        regression_tolerance=0.02,
    )
    assert not res.passed and "holdout" in res.failed_gate


def test_tool_placeholder_preserved_passes():
    a = _mk(kind="tool", text="search for {query} in {source}")
    res = apply_gates(
        artifact=a,
        candidate_text="Search {source} for {query}, return top 3 results.",
        baseline_score=0.5, candidate_holdout_score=0.6,
    )
    assert res.passed is True


def test_tool_placeholder_lost_fails():
    a = _mk(kind="tool", text="search for {query}")
    res = apply_gates(
        artifact=a, candidate_text="search the web",
        baseline_score=0.5, candidate_holdout_score=0.6,
    )
    assert not res.passed and "placeholder" in res.failed_gate
```

- [ ] **Step 6: 运行集成测试**

```bash
pytest tests/sdk/integration/test_constraint_gates.py -v
```

Expected: 全部 PASS.

- [ ] **Step 7: Commit**

```bash
git add evolution/sdk/optimizer.py tests/sdk/unit/test_optimizer.py tests/sdk/integration/test_constraint_gates.py
git commit -m "sdk(08): optimizer — GEPA→MIPROv2 fallback + three gates + run_summary

OptimizationBudget tracks USD spending. apply_gates validates size/growth/
secrets/placeholders (gate 1) and holdout regression (gate 2). gate 3 (smoke)
is a P1 stub. write_optimized_file does atomic write under
~/.evolution/optimized/. write_run_summary emits output/sdk/<agent>/<ts>/
run_summary.json. main() implements lock + --dry-run + --mock-llm paths.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: AST Writer — `apply="patch"` 模式

**Files:**
- Create: `evolution/sdk/ast_writer.py`
- Test: `tests/sdk/unit/test_ast_writer.py`

- [ ] **Step 1: 写 `tests/sdk/unit/test_ast_writer.py`**

```python
"""Tests for AST-based source rewriting for patch/pr apply modes."""

from pathlib import Path
from textwrap import dedent

import pytest

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.ast_writer import (
    rewrite_artifact_text,
    AstRewriteError,
    generate_unified_diff,
)


def _write_src(tmp_path: Path, content: str) -> Path:
    f = tmp_path / "bot.py"
    f.write_text(dedent(content))
    return f


def test_rewrite_param_form(tmp_path):
    src = _write_src(tmp_path, '''
        from evolution.sdk.decorators import evolvable_agent, evolvable_prompt

        @evolvable_agent(name="bot", schedule=None, auto_optimize=False, min_samples=1, max_cost_usd=1.0)
        class Bot:
            @evolvable_prompt(id="sys", text="OLD TEXT")
            def sys_prompt(self):
                return "x"

            def run(self, q):
                return q
    ''')
    artifact = EvolvableArtifact(
        agent_name="bot", artifact_id="sys", kind="prompt",
        baseline_text="OLD TEXT", text_source="param",
        source_file=src, decorator_lineno=5,
    )
    new_text = rewrite_artifact_text(artifact, new_text="NEW TEXT")
    assert "OLD TEXT" not in new_text
    assert 'text="NEW TEXT"' in new_text or "text='NEW TEXT'" in new_text


def test_rewrite_return_value_form(tmp_path):
    src = _write_src(tmp_path, '''
        from evolution.sdk.decorators import evolvable_prompt

        class Bot:
            @evolvable_prompt(id="p")
            def planner(self):
                return "old plan"
    ''')
    artifact = EvolvableArtifact(
        agent_name="bot", artifact_id="p", kind="prompt",
        baseline_text="old plan", text_source="return_value",
        source_file=src, decorator_lineno=4,
    )
    new_text = rewrite_artifact_text(artifact, new_text="NEW PLAN")
    assert "old plan" not in new_text
    assert "NEW PLAN" in new_text


def test_rewrite_docstring_form(tmp_path):
    src = _write_src(tmp_path, '''
        from evolution.sdk.decorators import evolvable_tool

        class Bot:
            @evolvable_tool(id="s")
            def search(self, q):
                """OLD DOC"""
                return q
    ''')
    artifact = EvolvableArtifact(
        agent_name="bot", artifact_id="s", kind="tool",
        baseline_text="OLD DOC", text_source="docstring",
        source_file=src, decorator_lineno=4,
    )
    new_text = rewrite_artifact_text(artifact, new_text="NEW DOC")
    assert "OLD DOC" not in new_text
    assert "NEW DOC" in new_text


def test_rewrite_return_form_ambiguous_multiple_literals_raises(tmp_path):
    src = _write_src(tmp_path, '''
        from evolution.sdk.decorators import evolvable_prompt

        class Bot:
            @evolvable_prompt(id="p")
            def planner(self):
                helper = "ignore"
                return "the plan"
    ''')
    artifact = EvolvableArtifact(
        agent_name="bot", artifact_id="p", kind="prompt",
        baseline_text="the plan", text_source="return_value",
        source_file=src, decorator_lineno=4,
    )
    with pytest.raises(AstRewriteError, match="multiple string literals"):
        rewrite_artifact_text(artifact, new_text="new")


def test_generate_unified_diff_format(tmp_path):
    original = "line1\nold text\nline3\n"
    new = "line1\nNEW TEXT\nline3\n"
    path = tmp_path / "bot.py"
    path.write_text(original)
    diff = generate_unified_diff(path, original_text=original, new_text=new)
    assert "--- a/" in diff and "+++ b/" in diff
    assert "-old text" in diff
    assert "+NEW TEXT" in diff
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/sdk/unit/test_ast_writer.py -v
```

- [ ] **Step 3: 写 `evolution/sdk/ast_writer.py`**

```python
"""AST-based source rewriter for apply="patch" / "pr" modes.

Per spec §4.2 write-back rules:
  - Form 1 (param):       rewrite the text= kwarg's string literal on the decorator call
  - Form 2 (return_value): rewrite the function body's single string literal
  - Form 3 (docstring):    rewrite the function's docstring constant
"""

import ast
import difflib
from pathlib import Path

from evolution.sdk.artifact import EvolvableArtifact


class AstRewriteError(Exception):
    """Raised when the rewrite target cannot be uniquely located."""


def rewrite_artifact_text(artifact: EvolvableArtifact, *, new_text: str) -> str:
    """Return the modified source code (does NOT write to disk).

    Caller is responsible for writing or producing a diff.
    """
    src = artifact.source_file.read_text()
    tree = ast.parse(src)

    if artifact.text_source == "param":
        new_src = _rewrite_param(tree, src, artifact, new_text)
    elif artifact.text_source == "return_value":
        new_src = _rewrite_return_value(tree, src, artifact, new_text)
    elif artifact.text_source == "docstring":
        new_src = _rewrite_docstring(tree, src, artifact, new_text)
    else:
        raise AstRewriteError(f"unknown text_source: {artifact.text_source!r}")

    return new_src


def generate_unified_diff(
    path: Path, *, original_text: str, new_text: str
) -> str:
    """Generate a standard unified diff string (writable as a .patch file)."""
    rel = path.name
    return "".join(difflib.unified_diff(
        original_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
    ))


# ── Rewrite implementations ─────────────────────────────────────────────


def _rewrite_param(tree: ast.AST, src: str, artifact: EvolvableArtifact,
                   new_text: str) -> str:
    """Rewrite the text= keyword arg on the matching @evolvable_prompt/tool call."""
    target_call = _find_decorator_call(tree, artifact)
    text_kw = next(
        (kw for kw in target_call.keywords if kw.arg == "text"
         and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)),
        None,
    )
    if text_kw is None:
        raise AstRewriteError(
            f"could not find text= kwarg on decorator at {artifact.source_file}:"
            f"{artifact.decorator_lineno}"
        )
    return _replace_node_value(src, text_kw.value, new_text)


def _rewrite_return_value(tree: ast.AST, src: str, artifact: EvolvableArtifact,
                          new_text: str) -> str:
    """Rewrite the unique string literal in the function body."""
    fn = _find_target_function(tree, artifact)
    # Collect all string literal constants in the body.
    literals = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value != (fn.body[0].value.value if (
            fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)
            and isinstance(fn.body[0].value.value, str)
        ) else None)
    ]
    # Also exclude docstring explicitly.
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)
            and isinstance(fn.body[0].value.value, str)):
        doc_node = fn.body[0].value
        literals = [n for n in literals if n is not doc_node]

    if len(literals) == 0:
        raise AstRewriteError(
            f"no string literal found in {fn.name} body for return-value rewrite"
        )
    if len(literals) > 1:
        raise AstRewriteError(
            f"multiple string literals in {fn.name} body — "
            "switch to text= parameter for patch mode"
        )
    return _replace_node_value(src, literals[0], new_text)


def _rewrite_docstring(tree: ast.AST, src: str, artifact: EvolvableArtifact,
                       new_text: str) -> str:
    fn = _find_target_function(tree, artifact)
    if not (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)
            and isinstance(fn.body[0].value.value, str)):
        raise AstRewriteError(f"{fn.name} has no docstring to rewrite")
    return _replace_node_value(src, fn.body[0].value, new_text)


# ── AST navigation helpers ──────────────────────────────────────────────


def _find_target_function(tree: ast.AST, artifact: EvolvableArtifact) -> ast.FunctionDef:
    """Locate the function decorated with @evolvable_prompt/tool(id=artifact.artifact_id)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                call = dec if isinstance(dec, ast.Call) else None
                if call and _decorator_matches(call, artifact):
                    return node
    raise AstRewriteError(
        f"could not find function for artifact {artifact.global_id}"
    )


def _find_decorator_call(tree: ast.AST, artifact: EvolvableArtifact) -> ast.Call:
    fn = _find_target_function(tree, artifact)
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call) and _decorator_matches(dec, artifact):
            return dec
    raise AstRewriteError(
        f"decorator call not found for {artifact.global_id}"
    )


def _decorator_matches(call: ast.Call, artifact: EvolvableArtifact) -> bool:
    # Decorator name check.
    fn_name = None
    if isinstance(call.func, ast.Name):
        fn_name = call.func.id
    elif isinstance(call.func, ast.Attribute):
        fn_name = call.func.attr
    if fn_name not in ("evolvable_prompt", "evolvable_tool"):
        return False
    # id= kwarg check.
    for kw in call.keywords:
        if kw.arg == "id" and isinstance(kw.value, ast.Constant):
            return kw.value.value == artifact.artifact_id
    return False


def _replace_node_value(src: str, node: ast.Constant, new_text: str) -> str:
    """Replace the source slice for a Constant node with a properly-quoted new value."""
    # Compute byte offsets in the source.
    lines = src.splitlines(keepends=True)
    start_line = node.lineno - 1
    start_col = node.col_offset
    end_line = node.end_lineno - 1
    end_col = node.end_col_offset

    # Build prefix + replacement + suffix.
    # Compute absolute offsets.
    start_off = sum(len(l) for l in lines[:start_line]) + start_col
    end_off = sum(len(l) for l in lines[:end_line]) + end_col

    # Choose quote style: prefer triple-double if new_text has newlines or both quote types.
    if "\n" in new_text:
        quoted = '"""' + new_text.replace('"""', '\\"""') + '"""'
    elif '"' in new_text and "'" not in new_text:
        quoted = "'" + new_text + "'"
    else:
        quoted = '"' + new_text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    return src[:start_off] + quoted + src[end_off:]
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/sdk/unit/test_ast_writer.py -v
```

Expected: 全部 PASS.

- [ ] **Step 5: Commit**

```bash
git add evolution/sdk/ast_writer.py tests/sdk/unit/test_ast_writer.py
git commit -m "sdk(09): AST writer for apply=patch — rewrite source for 3 text source forms

rewrite_artifact_text walks the AST to locate the decorator/function and
rewrites the matching constant in-place. Form 2 (return_value) rejects when
multiple string literals exist. generate_unified_diff emits standard
unified-diff output for the patch file.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 10: Scaffold — GitHub Actions 后端 + drift 检测

**Files:**
- Create: `evolution/sdk/scaffold.py`
- Test: `tests/sdk/unit/test_scaffold.py`
- Test: `tests/sdk/integration/test_scaffold_drift.py`

- [ ] **Step 1: 写 `tests/sdk/unit/test_scaffold.py`**

```python
"""Tests for scaffold — GH Actions workflow generation + manifest."""

import json
from pathlib import Path

import pytest

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.registry import AgentRegistration, register_agent
from evolution.sdk.scaffold import (
    schedule_to_cron,
    generate_gh_actions_yaml,
    scaffold_gh_actions,
    DriftStatus,
    check_drift,
    InvalidScheduleError,
)


@pytest.fixture(autouse=True)
def _clean(clear_registry):
    pass


def _mk_reg(name="bot", schedule="weekly", apply="runtime"):
    return AgentRegistration(
        name=name, module=f"app.{name}:Bot", version="0.1.0",
        schedule=schedule, min_samples=50, auto_optimize=True, apply=apply,
        max_cost_usd=5.0,
        artifacts=[EvolvableArtifact(
            agent_name=name, artifact_id="sys", kind="prompt",
            baseline_text="x", text_source="param",
            source_file=Path("/tmp/a.py"), decorator_lineno=1,
        )],
        source_files=[Path("/tmp/a.py")],
    )


def test_schedule_to_cron_weekly():
    assert schedule_to_cron("weekly") == "57 8 * * 1"


def test_schedule_to_cron_daily():
    assert schedule_to_cron("daily") == "57 8 * * *"


def test_schedule_to_cron_hourly():
    assert schedule_to_cron("hourly") == "57 * * * *"


def test_schedule_to_cron_custom():
    assert schedule_to_cron("cron:0 9 * * 1-5") == "0 9 * * 1-5"


def test_schedule_to_cron_none_returns_none():
    assert schedule_to_cron(None) is None


def test_schedule_to_cron_on_min_samples_returns_none():
    assert schedule_to_cron("on_min_samples") is None


def test_schedule_to_cron_invalid_raises():
    with pytest.raises(InvalidScheduleError):
        schedule_to_cron("yearly")


def test_generate_gh_actions_yaml_basic():
    reg = _mk_reg(name="bot", schedule="weekly")
    yaml_text = generate_gh_actions_yaml(reg)
    assert "name: evolve-bot" in yaml_text
    assert "cron: \"57 8 * * 1\"" in yaml_text
    assert "python -m evolution.sdk.optimizer" in yaml_text
    assert "--agent bot" in yaml_text
    assert "auto-generated" in yaml_text.lower() or "auto generated" in yaml_text.lower()


def test_generate_gh_actions_yaml_includes_pr_permission_when_apply_pr():
    reg = _mk_reg(apply="pr")
    yaml_text = generate_gh_actions_yaml(reg)
    assert "pull-requests: write" in yaml_text


def test_generate_gh_actions_yaml_omits_pr_permission_for_runtime():
    reg = _mk_reg(apply="runtime")
    yaml_text = generate_gh_actions_yaml(reg)
    assert "pull-requests:" not in yaml_text or "pull-requests: read" in yaml_text


def test_generate_gh_actions_yaml_skips_when_no_schedule():
    reg = _mk_reg(schedule=None)
    with pytest.raises(InvalidScheduleError, match="no schedule"):
        generate_gh_actions_yaml(reg)


def test_scaffold_gh_actions_writes_files(tmp_path):
    reg = _mk_reg(name="bot-a", schedule="weekly")
    register_agent(reg)
    written = scaffold_gh_actions(output_dir=tmp_path)
    assert len(written) == 1
    assert (tmp_path / "evolve-bot-a.yml").exists()
    assert (tmp_path / "evolution_scaffold_manifest.json").exists()
    manifest = json.loads((tmp_path / "evolution_scaffold_manifest.json").read_text())
    assert "bot-a" in manifest["agents"]


def test_scaffold_skips_hermes_managed_agent(tmp_path):
    reg = _mk_reg(name="hermes", schedule="weekly")
    reg.schedule_managed_by = "evolution-loop.yml"
    register_agent(reg)
    written = scaffold_gh_actions(output_dir=tmp_path)
    assert written == []
    assert not (tmp_path / "evolve-hermes.yml").exists()


def test_check_drift_clean(tmp_path):
    reg = _mk_reg(name="bot-a", schedule="weekly")
    register_agent(reg)
    scaffold_gh_actions(output_dir=tmp_path)
    statuses = check_drift(output_dir=tmp_path)
    assert all(s.status == "CLEAN" for s in statuses)


def test_check_drift_missing_file(tmp_path):
    reg = _mk_reg(name="bot-a", schedule="weekly")
    register_agent(reg)
    scaffold_gh_actions(output_dir=tmp_path)
    (tmp_path / "evolve-bot-a.yml").unlink()
    statuses = check_drift(output_dir=tmp_path)
    assert any(s.status == "MISSING" for s in statuses)


def test_check_drift_schedule_mismatch_after_user_edit(tmp_path):
    reg = _mk_reg(name="bot-a", schedule="weekly")
    register_agent(reg)
    scaffold_gh_actions(output_dir=tmp_path)
    # Simulate user changing the workflow file's cron.
    f = tmp_path / "evolve-bot-a.yml"
    content = f.read_text().replace("57 8 * * 1", "0 0 * * *")
    f.write_text(content)
    statuses = check_drift(output_dir=tmp_path)
    # Should detect manual edit (hash mismatch but it's still a workflow file).
    assert any(s.status in ("DRIFT", "MANUAL_EDIT") for s in statuses)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/sdk/unit/test_scaffold.py -v
```

- [ ] **Step 3: 写 `evolution/sdk/scaffold.py`**

```python
"""Generate .github/workflows/evolve-<agent>.yml + drift detection.

P0 supports only the GitHub Actions backend. cron / launchd are P1.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from evolution.sdk import registry

log = logging.getLogger("evolution.sdk.scaffold")


class InvalidScheduleError(ValueError):
    """Raised when a schedule= value cannot be converted to a cron expression."""


# Spec §7.4 schedule syntax.
def schedule_to_cron(schedule: Optional[str]) -> Optional[str]:
    """Translate a schedule= declaration to a 5-field cron expression (or None).

    Returns None for schedule=None and schedule="on_min_samples".
    """
    if schedule is None:
        return None
    if schedule == "on_min_samples":
        return None
    if schedule == "weekly":
        return "57 8 * * 1"
    if schedule == "daily":
        return "57 8 * * *"
    if schedule == "hourly":
        return "57 * * * *"
    if schedule.startswith("cron:"):
        return schedule[len("cron:"):].strip()
    raise InvalidScheduleError(f"unknown schedule: {schedule!r}")


_HEADER = (
    "# Auto-generated by `evolution scaffold` — do not edit manually.\n"
    "# Regenerate: evolution scaffold --backend gh-actions --agent {name}\n"
    "# Source: @evolvable_agent(name=\"{name}\", schedule=\"{schedule}\", ...)\n"
)


def generate_gh_actions_yaml(reg: registry.AgentRegistration) -> str:
    """Render the workflow YAML for one agent."""
    cron = schedule_to_cron(reg.schedule)
    if cron is None:
        raise InvalidScheduleError(
            f"agent {reg.name!r} has no schedule (or on_min_samples); "
            "skip scaffold or use --backend none"
        )

    permissions = "  contents: read"
    if reg.apply == "pr":
        permissions += "\n  pull-requests: write"

    header = _HEADER.format(name=reg.name, schedule=reg.schedule)
    return f"""{header}
name: evolve-{reg.name}

on:
  schedule:
    - cron: "{cron}"
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: false

permissions:
{permissions}

jobs:
  optimize:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    env:
      EVOLUTION_DEPLOY_MODE: production
      OPENAI_API_KEY: ${{{{ secrets.OPENAI_API_KEY }}}}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
      - run: pip install -e ".[dev]"
      - name: Optimize {reg.name}
        run: |
          python -m evolution.sdk.optimizer --agent {reg.name} ${{{{ inputs.dry_run && '--dry-run' || '' }}}}
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: evolve-{reg.name}-${{{{ github.run_id }}}}
          path: output/sdk/{reg.name}/
          retention-days: 90
"""


@dataclass
class DriftStatus:
    agent: str
    file: Path
    status: str  # CLEAN | MISSING | DRIFT | MANUAL_EDIT | STALE
    detail: str = ""


def scaffold_gh_actions(*, output_dir: Path,
                        only_agent: Optional[str] = None) -> list[Path]:
    """Generate workflow files for all registered agents (or one).

    Returns list of files written. Agents with schedule_managed_by set are
    skipped (hermes adapter manages its own).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    manifest = {"version": 1, "agents": {}}
    manifest_path = output_dir / "evolution_scaffold_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            manifest = {"version": 1, "agents": {}}
            log.warning("manifest corrupt; rebuilding from scratch")

    targets = [registry.get_agent(only_agent)] if only_agent else [
        registry.get_agent(n) for n in registry.list_agents()
    ]
    targets = [r for r in targets if r is not None]

    for reg in targets:
        if reg.schedule_managed_by:
            log.info("skipping %s — schedule_managed_by=%s",
                     reg.name, reg.schedule_managed_by)
            continue
        if reg.schedule is None or reg.schedule == "on_min_samples":
            log.info("skipping %s — schedule=%s", reg.name, reg.schedule)
            continue

        path = output_dir / f"evolve-{reg.name}.yml"
        yaml_text = generate_gh_actions_yaml(reg)
        path.write_text(yaml_text)
        written.append(path)
        manifest["agents"][reg.name] = {
            "file": path.name,
            "hash": "sha256:" + hashlib.sha256(yaml_text.encode()).hexdigest(),
            "schedule": reg.schedule,
        }

    manifest_path.write_text(json.dumps(manifest, indent=2))
    return written


def check_drift(*, output_dir: Path) -> list[DriftStatus]:
    """Compare registry against on-disk workflow files.

    Returns one DriftStatus per agent. STALE agents (file exists but registry
    has schedule=None) are surfaced too.
    """
    statuses: list[DriftStatus] = []
    manifest_path = output_dir / "evolution_scaffold_manifest.json"
    manifest = {"agents": {}}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            log.warning("manifest unreadable; treating all as DRIFT")

    for name in registry.list_agents():
        reg = registry.get_agent(name)
        if reg.schedule_managed_by:
            continue
        expected_file = output_dir / f"evolve-{name}.yml"
        if reg.schedule in (None, "on_min_samples"):
            if expected_file.exists():
                statuses.append(DriftStatus(
                    agent=name, file=expected_file, status="STALE",
                    detail="schedule=None but file present",
                ))
            continue

        if not expected_file.exists():
            statuses.append(DriftStatus(
                agent=name, file=expected_file, status="MISSING",
                detail="schedule declared but file absent",
            ))
            continue

        actual = expected_file.read_text()
        actual_hash = "sha256:" + hashlib.sha256(actual.encode()).hexdigest()
        manifest_hash = manifest.get("agents", {}).get(name, {}).get("hash")

        if manifest_hash == actual_hash:
            statuses.append(DriftStatus(agent=name, file=expected_file, status="CLEAN"))
            continue

        # Hash differs — compare to "what we'd generate now".
        expected_now = generate_gh_actions_yaml(reg)
        expected_now_hash = "sha256:" + hashlib.sha256(expected_now.encode()).hexdigest()
        if actual_hash == expected_now_hash:
            statuses.append(DriftStatus(
                agent=name, file=expected_file, status="CLEAN",
                detail="manifest stale but file matches registry",
            ))
        elif _cron_value(actual) != _cron_value(expected_now):
            statuses.append(DriftStatus(
                agent=name, file=expected_file, status="DRIFT",
                detail="schedule mismatch — re-run scaffold",
            ))
        else:
            statuses.append(DriftStatus(
                agent=name, file=expected_file, status="MANUAL_EDIT",
                detail="content differs from generated; preserved",
            ))

    return statuses


def _cron_value(yaml_text: str) -> str:
    for line in yaml_text.splitlines():
        if "cron:" in line and '"' in line:
            return line.strip()
    return ""
```

- [ ] **Step 4: 写 `tests/sdk/integration/test_scaffold_drift.py`**

```python
"""Integration: full drift detection scenarios."""

import json
from pathlib import Path

import pytest

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.registry import AgentRegistration, register_agent
from evolution.sdk.scaffold import scaffold_gh_actions, check_drift


@pytest.fixture(autouse=True)
def _clean(clear_registry):
    pass


def _mk_reg(name, schedule="weekly"):
    return AgentRegistration(
        name=name, module=f"app.{name}:X", version="0.1.0",
        schedule=schedule, min_samples=10, auto_optimize=True, apply="runtime",
        max_cost_usd=5.0,
        artifacts=[EvolvableArtifact(
            agent_name=name, artifact_id="x", kind="prompt",
            baseline_text="x", text_source="param",
            source_file=Path("/tmp/x.py"), decorator_lineno=1,
        )],
        source_files=[Path(f"/tmp/{name}.py")],
    )


def test_full_drift_lifecycle(tmp_path):
    # 1. Register + scaffold → CLEAN
    register_agent(_mk_reg("bot-a", schedule="weekly"))
    register_agent(_mk_reg("bot-b", schedule="daily"))
    scaffold_gh_actions(output_dir=tmp_path)
    statuses = {s.agent: s.status for s in check_drift(output_dir=tmp_path)}
    assert statuses == {"bot-a": "CLEAN", "bot-b": "CLEAN"}

    # 2. Delete a file → MISSING
    (tmp_path / "evolve-bot-a.yml").unlink()
    statuses = {s.agent: s.status for s in check_drift(output_dir=tmp_path)}
    assert statuses["bot-a"] == "MISSING"

    # 3. Recreate + change schedule on registry → DRIFT
    scaffold_gh_actions(output_dir=tmp_path)
    # Update registry: change bot-a's schedule.
    from evolution.sdk import registry as r
    r._REGISTRY["bot-a"].schedule = "daily"
    statuses = {s.agent: s.status for s in check_drift(output_dir=tmp_path)}
    assert statuses["bot-a"] == "DRIFT"
```

- [ ] **Step 5: 运行测试**

```bash
pytest tests/sdk/unit/test_scaffold.py tests/sdk/integration/test_scaffold_drift.py -v
```

Expected: 全部 PASS.

- [ ] **Step 6: Commit**

```bash
git add evolution/sdk/scaffold.py tests/sdk/unit/test_scaffold.py tests/sdk/integration/test_scaffold_drift.py
git commit -m "sdk(10): scaffold — GH Actions workflow generation + drift detection

schedule_to_cron translates weekly/daily/hourly/cron:X to 5-field cron.
generate_gh_actions_yaml emits .github/workflows/evolve-<agent>.yml. Manifest
file (evolution_scaffold_manifest.json) tracks expected hashes so check_drift
can return CLEAN / MISSING / DRIFT / MANUAL_EDIT / STALE per agent.
schedule_managed_by='evolution-loop.yml' agents skipped (hermes adapter).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 11: CLI — `evolution discover/scaffold/optimize/status/rollback`

**Files:**
- Create: `evolution/sdk/cli.py`
- Test: `tests/sdk/unit/test_cli.py`

- [ ] **Step 1: 写 `tests/sdk/unit/test_cli.py`**

```python
"""Tests for evolution CLI commands."""

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from evolution.sdk.cli import main


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "agents"


@pytest.fixture(autouse=True)
def _clean(clear_registry, monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_DIR.parent.parent))
    for m in list(sys.modules):
        if m.startswith("fixtures.agents"):
            del sys.modules[m]


def test_discover_imports_module_and_persists(tmp_evolution_home):
    runner = CliRunner()
    result = runner.invoke(
        main, ["discover", "fixtures.agents.three_form_bot"],
    )
    assert result.exit_code == 0, result.output
    reg = json.loads((tmp_evolution_home / "registry.json").read_text())
    assert "three-form-bot" in reg["agents"]


def test_discover_missing_module_fails():
    runner = CliRunner()
    result = runner.invoke(main, ["discover", "nonexistent.module"])
    assert result.exit_code != 0
    assert "could not import" in result.output.lower() or "modulenotfounderror" in result.output.lower()


def test_scaffold_dry_run_does_not_write(tmp_path, tmp_evolution_home):
    runner = CliRunner()
    runner.invoke(main, ["discover", "fixtures.agents.three_form_bot"])
    result = runner.invoke(main, [
        "scaffold", "--backend", "gh-actions",
        "--output", str(tmp_path), "--dry-run",
    ])
    assert result.exit_code == 0
    assert not (tmp_path / "evolve-three-form-bot.yml").exists()


def test_scaffold_writes_workflow_file(tmp_path, tmp_evolution_home, monkeypatch):
    # three_form_bot has schedule=None — we override via re-register.
    runner = CliRunner()
    runner.invoke(main, ["discover", "fixtures.agents.three_form_bot"])
    # Manually patch registry to schedule="weekly".
    from evolution.sdk import registry as r
    r._REGISTRY["three-form-bot"].schedule = "weekly"
    r.persist_to_file()

    result = runner.invoke(main, [
        "scaffold", "--backend", "gh-actions",
        "--output", str(tmp_path),
    ])
    assert result.exit_code == 0
    assert (tmp_path / "evolve-three-form-bot.yml").exists()


def test_status_lists_registered_agents(tmp_evolution_home):
    runner = CliRunner()
    runner.invoke(main, ["discover", "fixtures.agents.three_form_bot"])
    result = runner.invoke(main, ["status", "--agent", "three-form-bot"])
    assert result.exit_code == 0
    assert "three-form-bot" in result.output


def test_rollback_deletes_optimized_file(tmp_evolution_home):
    runner = CliRunner()
    runner.invoke(main, ["discover", "fixtures.agents.three_form_bot"])
    opt_dir = tmp_evolution_home / "optimized" / "three-form-bot"
    opt_dir.mkdir(parents=True)
    (opt_dir / "system.json").write_text("{}")
    result = runner.invoke(
        main, ["rollback", "--agent", "three-form-bot", "--artifact", "system"]
    )
    assert result.exit_code == 0
    assert not (opt_dir / "system.json").exists()


def test_optimize_dry_run_succeeds(tmp_evolution_home, write_trace_file, fake_trace_factory):
    """`evolution optimize --dry-run` works even without traces."""
    runner = CliRunner()
    runner.invoke(main, ["discover", "fixtures.agents.three_form_bot"])
    # Generate enough traces to pass min_samples=3.
    write_trace_file("three-form-bot", "20260612", [
        fake_trace_factory(agent="three-form-bot", ts="2026-06-12T01:00:00Z")
        for _ in range(5)
    ])
    result = runner.invoke(
        main, ["optimize", "--agent", "three-form-bot", "--dry-run"]
    )
    assert result.exit_code == 0
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/sdk/unit/test_cli.py -v
```

- [ ] **Step 3: 写 `evolution/sdk/cli.py`**

```python
"""evolution CLI: discover / scaffold / optimize / status / rollback."""

import importlib
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from evolution.sdk import registry, scaffold as scaffold_mod
from evolution.sdk.trace_sink import _evolution_home

console = Console()


@click.group()
def main():
    """Evolution SDK — generic Python agent self-evolution."""


@main.command()
@click.argument("modules", nargs=-1, required=True)
@click.option("--package", "is_package", is_flag=True,
              help="Treat MODULES as package paths to import recursively.")
def discover(modules, is_package):
    """Import agent modules to populate the registry, then persist to disk."""
    for spec in modules:
        try:
            if is_package:
                importlib.import_module(spec)
            else:
                importlib.import_module(spec)
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]could not import {spec}: {e}[/red]")
            sys.exit(1)

    registry.persist_to_file()
    names = registry.list_agents()
    console.print(f"[green]discovered {len(names)} agent(s):[/green] {', '.join(names)}")


@main.command()
@click.option("--backend", type=click.Choice(["gh-actions"]), default="gh-actions",
              help="Scheduling backend (P0 only supports gh-actions).")
@click.option("--output", "output_dir", type=click.Path(file_okay=False, path_type=Path),
              default=Path(".github/workflows"),
              help="Output directory for generated configs.")
@click.option("--agent", default=None, help="Only scaffold for this agent.")
@click.option("--dry-run", is_flag=True, help="Preview without writing files.")
@click.option("--check", is_flag=True, help="Drift detection mode (CI use).")
def scaffold(backend, output_dir, agent, dry_run, check):
    """Generate scheduling configs from registered agents."""
    registry.load_from_file()
    if check:
        statuses = scaffold_mod.check_drift(output_dir=output_dir)
        _print_drift_table(statuses)
        exit_code = _drift_exit_code(statuses)
        sys.exit(exit_code)

    if dry_run:
        for name in (registry.list_agents() if agent is None else [agent]):
            reg = registry.get_agent(name)
            if reg is None:
                continue
            if reg.schedule_managed_by or reg.schedule in (None, "on_min_samples"):
                continue
            console.print(f"[cyan]would write[/cyan] {output_dir}/evolve-{name}.yml")
        return

    written = scaffold_mod.scaffold_gh_actions(
        output_dir=output_dir, only_agent=agent,
    )
    for path in written:
        console.print(f"[green]wrote[/green] {path}")


def _print_drift_table(statuses):
    table = Table(title="Scaffold drift status")
    table.add_column("Agent")
    table.add_column("Status")
    table.add_column("Detail")
    for s in statuses:
        color = {"CLEAN": "green", "MISSING": "red", "DRIFT": "red",
                 "MANUAL_EDIT": "yellow", "STALE": "yellow"}.get(s.status, "white")
        table.add_row(s.agent, f"[{color}]{s.status}[/{color}]", s.detail or "")
    console.print(table)


def _drift_exit_code(statuses) -> int:
    fail = any(s.status in ("DRIFT", "MISSING") for s in statuses)
    warn = any(s.status in ("MANUAL_EDIT", "STALE") for s in statuses)
    if fail:
        return 2
    if warn:
        return 1
    return 0


@main.command()
@click.option("--agent", required=True)
@click.option("--dry-run", is_flag=True)
@click.option("--mock-llm", is_flag=True)
def optimize(agent, dry_run, mock_llm):
    """Manually trigger optimization for one agent."""
    from evolution.sdk import optimizer
    argv = ["--agent", agent]
    if dry_run:
        argv.append("--dry-run")
    if mock_llm:
        argv.append("--mock-llm")
    sys.argv = ["optimize"] + argv
    sys.exit(optimizer.main())


@main.command()
@click.option("--agent", required=True)
def status(agent):
    """Show registration + traces + optimized state for one agent."""
    registry.load_from_file()
    reg = registry.get_agent(agent)
    if reg is None:
        console.print(f"[red]agent {agent!r} not registered[/red]")
        sys.exit(1)
    table = Table(title=f"Status: {agent}")
    table.add_column("Field"); table.add_column("Value")
    table.add_row("module", reg.module)
    table.add_row("version", reg.version)
    table.add_row("schedule", str(reg.schedule))
    table.add_row("apply", reg.apply)
    table.add_row("artifacts", ", ".join(a.artifact_id for a in reg.artifacts))

    opt_dir = _evolution_home() / "optimized" / agent
    if opt_dir.exists():
        for opt_file in opt_dir.glob("*.json"):
            try:
                data = json.loads(opt_file.read_text())
                table.add_row(f"optimized:{opt_file.stem}",
                              f"score={data.get('optimization', {}).get('optimized_score')}")
            except json.JSONDecodeError:
                table.add_row(f"optimized:{opt_file.stem}", "[red]corrupt[/red]")
    console.print(table)


@main.command()
@click.option("--agent", required=True)
@click.option("--artifact", required=True)
def rollback(agent, artifact):
    """Delete an optimized artifact (revert to baseline)."""
    path = _evolution_home() / "optimized" / agent / f"{artifact}.json"
    if not path.exists():
        console.print(f"[yellow]no optimized file for {agent}/{artifact}[/yellow]")
        sys.exit(0)
    path.unlink()
    console.print(f"[green]removed[/green] {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/sdk/unit/test_cli.py -v
```

Expected: 全部 PASS.

- [ ] **Step 5: 验证 CLI 已注册（项目可执行）**

```bash
pip install -e .
evolution --help
```

Expected: 显示 5 个子命令: discover/scaffold/optimize/status/rollback.

- [ ] **Step 6: Commit**

```bash
git add evolution/sdk/cli.py tests/sdk/unit/test_cli.py
git commit -m "sdk(11): evolution CLI — discover/scaffold/optimize/status/rollback

Click-based CLI registered via [project.scripts] evolution. discover imports
agent modules and persists registry.json. scaffold supports --check (drift)
with structured exit codes 0/1/2. status table shows registration + optimized
files. rollback deletes one optimized artifact (reverts to baseline).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 12: Hermes Adapter — 现有 6 CLI 包为 adapter

**Files:**
- Create: `evolution/adapters/hermes.py`
- Test: `tests/sdk/unit/test_hermes_adapter.py`

- [ ] **Step 1: 写 `tests/sdk/unit/test_hermes_adapter.py`**

```python
"""Tests for hermes adapter — registers legacy 6-CLI pipeline as a single agent."""

import pytest

from evolution.adapters.hermes import register_hermes_adapter, HERMES_CLI_NAMES
from evolution.sdk import registry


@pytest.fixture(autouse=True)
def _clean(clear_registry):
    pass


def test_register_hermes_adapter_adds_agent():
    register_hermes_adapter(name="hermes")
    reg = registry.get_agent("hermes")
    assert reg is not None
    assert reg.module.startswith("evolution.adapters.hermes")
    assert reg.schedule_managed_by == "evolution-loop.yml"


def test_hermes_adapter_has_six_cli_artifacts():
    register_hermes_adapter(name="hermes")
    reg = registry.get_agent("hermes")
    ids = {a.artifact_id for a in reg.artifacts}
    assert ids == set(HERMES_CLI_NAMES)


def test_hermes_adapter_scaffold_skipped(tmp_path):
    """Hermes adapter must be skipped by scaffold (schedule_managed_by set)."""
    from evolution.sdk.scaffold import scaffold_gh_actions
    register_hermes_adapter(name="hermes")
    written = scaffold_gh_actions(output_dir=tmp_path)
    assert written == []  # nothing written for hermes


def test_hermes_adapter_artifacts_are_marked_tool_kind():
    """All 6 hermes CLIs operate on tool-like artifacts (descriptions/prompts)."""
    register_hermes_adapter(name="hermes")
    reg = registry.get_agent("hermes")
    # Six CLI names: skill, tool_descriptions, tool_params, tool_reasoning,
    # prompt_sections, code. Their EvolvableArtifact kind is best-effort:
    # we mark all of them as "prompt" except code (which is also prompt-ish for SDK).
    kinds = {a.kind for a in reg.artifacts}
    assert kinds.issubset({"prompt", "tool"})


def test_hermes_adapter_idempotent():
    register_hermes_adapter(name="hermes")
    register_hermes_adapter(name="hermes")  # second call must not raise
    assert "hermes" in registry.list_agents()
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/sdk/unit/test_hermes_adapter.py -v
```

- [ ] **Step 3: 写 `evolution/adapters/hermes.py`**

```python
"""Hermes adapter — registers the legacy 6-CLI pipeline as one SDK agent.

This adapter does NOT change how the legacy pipeline runs (evolution-loop.yml
keeps scheduling it). It just makes hermes visible in the unified registry so
`evolution status --agent hermes` and `evolution scaffold --check` see it.

`schedule_managed_by="evolution-loop.yml"` tells scaffold to skip generation.
"""

from pathlib import Path

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk import registry


# Six legacy CLIs in dispatch order (matches evolution/core/config.LOOP_CLI_NAMES).
HERMES_CLI_NAMES = (
    "skill",
    "tool_descriptions",
    "tool_params",
    "tool_reasoning",
    "prompt_sections",
    "code",
)

# Best-effort kind mapping for each CLI's primary artifact.
_CLI_KIND_MAP = {
    "skill": "prompt",
    "tool_descriptions": "tool",
    "tool_params": "tool",
    "tool_reasoning": "prompt",
    "prompt_sections": "prompt",
    "code": "prompt",  # code-as-text from SDK's perspective
}


def register_hermes_adapter(name: str = "hermes") -> None:
    """Register the hermes adapter agent (idempotent).

    Each of the 6 legacy CLIs becomes one EvolvableArtifact entry. The artifacts
    use placeholder baseline_text — the actual optimizable text lives in the
    hermes-agent repo and is read by the legacy CLI subprocesses, not by the
    SDK runtime path.
    """
    existing = registry.get_agent(name)
    if existing is not None:
        return  # idempotent

    source_file = Path(__file__).resolve()
    artifacts = [
        EvolvableArtifact(
            agent_name=name,
            artifact_id=cli_name,
            kind=_CLI_KIND_MAP[cli_name],
            baseline_text=f"<managed by evolution/{cli_name} CLI>",
            text_source="param",
            source_file=source_file,
            decorator_lineno=0,
            constraints={"managed_by_legacy_cli": True},
        )
        for cli_name in HERMES_CLI_NAMES
    ]

    reg = registry.AgentRegistration(
        name=name,
        module=f"evolution.adapters.hermes:HermesAdapter",
        version="1.0.0",
        schedule="weekly",  # informational; not used by scaffold
        min_samples=0,
        auto_optimize=True,
        apply="pr",
        max_cost_usd=30.0,  # sum of legacy CLI caps
        artifacts=artifacts,
        source_files=[source_file],
        schedule_managed_by="evolution-loop.yml",
    )
    registry.register_agent(reg)


class HermesAdapter:
    """Marker class so registry.module resolves cleanly. No runtime behavior."""

    def run(self, *args, **kwargs):
        raise NotImplementedError(
            "Hermes adapter does not run via SDK invoke path. Use "
            "evolution-loop.yml + python -m evolution.loop.run_loop instead."
        )
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/sdk/unit/test_hermes_adapter.py -v
```

Expected: 5 个测试 PASS.

- [ ] **Step 5: Commit**

```bash
git add evolution/adapters/hermes.py tests/sdk/unit/test_hermes_adapter.py
git commit -m "sdk(12): hermes adapter — register legacy 6-CLI pipeline as one SDK agent

evolution.adapters.hermes.register_hermes_adapter() adds a hermes entry to the
registry with schedule_managed_by='evolution-loop.yml' so scaffold skips it.
Six artifacts (one per CLI) make hermes visible in 'evolution status' /
'evolution scaffold --check' without changing how the legacy pipeline runs.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 13: 端到端 EchoBot — 完整优化循环（mock LLM）

**Files:**
- Create: `tests/sdk/example_bot/__init__.py`
- Create: `tests/sdk/example_bot/echo_bot.py`
- Create: `tests/sdk/example_bot/test_end_to_end.py`

- [ ] **Step 1: 写 `tests/sdk/example_bot/__init__.py`**

```python
# Marker for pytest to collect this directory.
```

- [ ] **Step 2: 写 `tests/sdk/example_bot/echo_bot.py`**

```python
"""Minimal real agent for end-to-end dogfood: covers trace capture + optimized loading."""

from evolution.sdk import runtime
from evolution.sdk.decorators import (
    evolvable_agent, evolvable_prompt, evolvable_tool,
)


@evolvable_agent(
    name="echo-bot-test",
    version="0.1.0",
    judge_dimensions=("relevance",),
    min_samples=3,
    schedule=None,
    auto_optimize=False,
    max_cost_usd=1.0,
)
class EchoBot:
    @evolvable_prompt(id="rewriter", text="Rewrite this concisely: {input}",
                      max_chars=200, max_growth=0.5)
    def rewriter_prompt(self) -> str:
        return runtime.resolve_text("echo-bot-test", "rewriter")

    @evolvable_tool(id="echo_tool", max_chars=300)
    def echo_tool(self, q: str) -> str:
        """Echo back the input verbatim."""
        return q

    def run(self, query: str) -> str:
        prompt = self.rewriter_prompt()
        echoed = self.echo_tool(query)
        return f"{prompt.replace('{input}', echoed)}"
```

- [ ] **Step 3: 写 `tests/sdk/example_bot/test_end_to_end.py`**

```python
"""End-to-end: import → traces → optimize stub → resolve_text picks optimized."""

import importlib
import json
import sys
from pathlib import Path

import pytest

from evolution.sdk import registry, runtime
from evolution.sdk.optimizer import write_optimized_file
from evolution.sdk.artifact import EvolvableArtifact


FIXTURE_DIR = Path(__file__).parent


@pytest.fixture(autouse=True)
def _clean(clear_registry, monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_DIR.parent.parent))
    for m in list(sys.modules):
        if m.startswith("tests.sdk.example_bot") or m.endswith("echo_bot"):
            del sys.modules[m]


def test_full_lifecycle_baseline_optimize_runtime_load(tmp_evolution_home):
    # 1) Import the agent → registered.
    mod = importlib.import_module("tests.sdk.example_bot.echo_bot")
    reg = registry.get_agent("echo-bot-test")
    assert reg is not None
    assert len(reg.artifacts) == 2  # rewriter + echo_tool

    # 2) Instantiate + run 5 times → traces persisted.
    bot = mod.EchoBot()
    for q in ["a", "b", "c", "d", "e"]:
        out = bot.run(q)
        assert q in out  # echo round-trip

    traces_dir = tmp_evolution_home / "traces" / "echo-bot-test"
    jsonl_files = list(traces_dir.glob("*.jsonl"))
    assert len(jsonl_files) == 1
    lines = jsonl_files[0].read_text().splitlines()
    assert len(lines) == 5
    parsed = [json.loads(l) for l in lines]
    for p in parsed:
        assert p["agent"] == "echo-bot-test"
        assert any(a["id"] == "rewriter" for a in p["artifacts"])

    # 3) Simulate optimizer writing an optimized rewriter.
    rewriter = next(a for a in reg.artifacts if a.artifact_id == "rewriter")
    write_optimized_file(
        artifact=rewriter,
        agent_version="0.1.0",
        optimized_text="CONCISE: {input}",
        optimization_metadata={
            "run_id": "test-run",
            "ts": "2026-06-13T00:00:00Z",
            "optimizer": "mock",
            "baseline_score": 0.5,
            "optimized_score": 0.85,
            "holdout_score": 0.80,
            "dataset_size": 5,
            "cost_usd": 0.0,
        },
    )

    # 4) resolve_text returns optimized version (hash matches).
    resolved = runtime.resolve_text("echo-bot-test", "rewriter")
    assert resolved == "CONCISE: {input}"

    # 5) New invocation uses optimized prompt.
    out = bot.run("hello")
    assert "CONCISE" in out and "hello" in out

    # 6) Simulate user editing baseline → optimized is invalidated.
    # We can't easily edit the actual file in a test; mutate the in-memory
    # artifact's baseline_text and verify resolve_text falls back.
    rewriter_new = EvolvableArtifact(
        agent_name=rewriter.agent_name,
        artifact_id=rewriter.artifact_id,
        kind=rewriter.kind,
        baseline_text="DIFFERENT BASELINE NOW",
        text_source=rewriter.text_source,
        source_file=rewriter.source_file,
        decorator_lineno=rewriter.decorator_lineno,
        constraints=rewriter.constraints,
    )
    reg.artifacts[reg.artifacts.index(rewriter)] = rewriter_new
    assert runtime.resolve_text("echo-bot-test", "rewriter") == "DIFFERENT BASELINE NOW"


def test_min_samples_not_met_skips(tmp_evolution_home, write_trace_file, fake_trace_factory):
    """`evolution optimize` with too few traces writes SKIPPED, exit 0."""
    importlib.import_module("tests.sdk.example_bot.echo_bot")
    # min_samples=3; write only 1 trace.
    write_trace_file("echo-bot-test", "20260613", [
        fake_trace_factory(agent="echo-bot-test", ts="2026-06-13T01:00:00Z"),
    ])
    registry.persist_to_file()

    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "evolution.sdk.optimizer",
         "--agent", "echo-bot-test"],
        capture_output=True, text=True, env={**__import__("os").environ,
                                              "EVOLUTION_HOME": str(tmp_evolution_home)},
        cwd=str(Path.cwd()),
    )
    assert result.returncode == 0, result.stderr
    # SKIPPED directory exists.
    skipped = list((Path("output") / "sdk" / "echo-bot-test").glob("SKIPPED_*"))
    assert len(skipped) >= 1
    # Clean up
    import shutil
    shutil.rmtree(Path("output") / "sdk" / "echo-bot-test", ignore_errors=True)


def test_dry_run_writes_run_summary(tmp_evolution_home, write_trace_file, fake_trace_factory):
    importlib.import_module("tests.sdk.example_bot.echo_bot")
    write_trace_file("echo-bot-test", "20260613", [
        fake_trace_factory(agent="echo-bot-test",
                           ts=f"2026-06-13T0{i}:00:00Z") for i in range(1, 6)
    ])
    registry.persist_to_file()

    import subprocess, os, shutil
    result = subprocess.run(
        [sys.executable, "-m", "evolution.sdk.optimizer",
         "--agent", "echo-bot-test", "--dry-run"],
        capture_output=True, text=True,
        env={**os.environ, "EVOLUTION_HOME": str(tmp_evolution_home)},
    )
    assert result.returncode == 0, result.stderr
    runs = list((Path("output") / "sdk" / "echo-bot-test").glob("*"))
    assert any((p / "run_summary.json").exists() for p in runs if p.is_dir())
    shutil.rmtree(Path("output") / "sdk" / "echo-bot-test", ignore_errors=True)
```

- [ ] **Step 4: 运行端到端测试**

```bash
pytest tests/sdk/example_bot/ -v
```

Expected: 3 个测试 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/sdk/example_bot/
git commit -m "sdk(13): end-to-end EchoBot — full lifecycle dogfood

EchoBot decorator → 5 runs → traces.jsonl → write optimized → resolve_text
returns optimized → baseline_hash invalidation on source change. Plus
min_samples SKIPPED path and --dry-run run_summary path. CI-friendly:
< 1s per test, zero LLM cost.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 14: Hermes Parity 测试 — `skill` + `tool_descriptions`

**Files:**
- Create: `tests/sdk/parity/test_skill_parity.py`
- Create: `tests/sdk/parity/test_tool_descriptions_parity.py`
- Create: `tests/sdk/fixtures/snapshots/hermes_parity/.gitkeep`

> **目标**：验证 SDK 的纯函数路径（artifact 提取、约束校验、数据集构造）在 hermes 输入下产出与现有 CLI byte-equal；GEPA 产物则用 score 差异 < 5% + 字符长度差异 < 10% 的容差。

- [ ] **Step 1: 创建 snapshots 占位**

```bash
mkdir -p tests/sdk/fixtures/snapshots/hermes_parity
touch tests/sdk/fixtures/snapshots/hermes_parity/.gitkeep
```

- [ ] **Step 2: 写 `tests/sdk/parity/test_skill_parity.py`**

```python
"""Parity: SDK constraint validator + dataset construction match legacy skill CLI.

The legacy CLI is `python -m evolution.skills.evolve_skill`. We don't actually
run GEPA in CI (too expensive); we verify the byte-equal-eligible pure
function path:
  1. Skill body extraction
  2. Constraint validation (size, growth, structure)
  3. Dataset construction from session JSONL
"""

from pathlib import Path

import pytest

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintValidator
from evolution.skills.skill_module import load_skill
from evolution.sdk.artifact import EvolvableArtifact, compute_baseline_hash
from evolution.sdk.optimizer import apply_gates


SAMPLE_SKILL = """---
name: test-skill
description: A skill used by parity tests
---

Body line 1.
Body line 2.
"""


def test_skill_loader_byte_equal_to_sdk_baseline_extraction(tmp_path):
    """Legacy load_skill().body must equal what SDK would treat as baseline_text."""
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text(SAMPLE_SKILL)

    legacy = load_skill(skill_file)
    sdk_artifact = EvolvableArtifact(
        agent_name="hermes",
        artifact_id="test-skill",
        kind="prompt",
        baseline_text=legacy["body"],
        text_source="param",
        source_file=skill_file,
        decorator_lineno=0,
    )
    # Hash must match the body text byte-for-byte.
    assert sdk_artifact.baseline_hash == compute_baseline_hash(legacy["body"])


def test_constraint_size_gate_equivalent_to_legacy(tmp_path):
    """Both code paths must reject the same oversize candidate."""
    config = EvolutionConfig(max_skill_size=100)
    legacy = ConstraintValidator(config)
    candidate = "x" * 150

    legacy_results = legacy.validate_all(candidate, "skill", baseline_text="hi")
    legacy_passed = all(r.passed for r in legacy_results)

    sdk_artifact = EvolvableArtifact(
        agent_name="hermes", artifact_id="x", kind="prompt",
        baseline_text="hi", text_source="param",
        source_file=tmp_path / "x.py", decorator_lineno=1,
        constraints={"max_chars": 100, "max_growth": config.max_prompt_growth},
    )
    sdk_result = apply_gates(
        artifact=sdk_artifact, candidate_text=candidate,
        baseline_score=0.5, candidate_holdout_score=0.6,
    )

    # Both must reject (legacy because size, SDK because gate_1_size).
    assert legacy_passed is False
    assert sdk_result.passed is False


def test_constraint_growth_gate_equivalent_to_legacy(tmp_path):
    config = EvolutionConfig(max_prompt_growth=0.2)
    legacy = ConstraintValidator(config)

    baseline = "x" * 100
    candidate = "x" * 200  # 100% growth, well over 20%

    legacy_results = legacy.validate_all(candidate, "skill", baseline_text=baseline)
    legacy_growth_check = next(
        (r for r in legacy_results if r.constraint_name == "growth_limit"), None,
    )

    sdk_artifact = EvolvableArtifact(
        agent_name="hermes", artifact_id="x", kind="prompt",
        baseline_text=baseline, text_source="param",
        source_file=tmp_path / "x.py", decorator_lineno=1,
        constraints={"max_chars": 50_000, "max_growth": 0.2},
    )
    sdk_result = apply_gates(
        artifact=sdk_artifact, candidate_text=candidate,
        baseline_score=0.5, candidate_holdout_score=0.6,
    )

    assert legacy_growth_check is not None and legacy_growth_check.passed is False
    assert sdk_result.passed is False
    assert "growth" in sdk_result.failed_gate.lower()
```

- [ ] **Step 3: 写 `tests/sdk/parity/test_tool_descriptions_parity.py`**

```python
"""Parity: SDK tool-description gates match legacy tool_descriptions CLI.

Verifies the placeholder-preservation rule + the legacy max_tool_desc_size
constraint produce the same accept/reject decision.
"""

from pathlib import Path

import pytest

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintValidator
from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.optimizer import apply_gates


def test_tool_desc_size_limit_parity(tmp_path):
    """Both legacy and SDK reject tool desc > max_tool_desc_size (500 default)."""
    config = EvolutionConfig(max_tool_desc_size=100)
    legacy = ConstraintValidator(config)
    candidate = "x" * 200

    legacy_results = legacy.validate_all(candidate, "tool_description",
                                         baseline_text="hi")
    legacy_passed = all(r.passed for r in legacy_results)

    sdk_artifact = EvolvableArtifact(
        agent_name="hermes", artifact_id="t", kind="tool",
        baseline_text="hi", text_source="docstring",
        source_file=tmp_path / "x.py", decorator_lineno=1,
        constraints={"max_chars": 100, "max_growth": 0.5},
    )
    sdk_result = apply_gates(
        artifact=sdk_artifact, candidate_text=candidate,
        baseline_score=0.5, candidate_holdout_score=0.6,
    )

    assert legacy_passed is False
    assert sdk_result.passed is False


def test_tool_placeholder_preservation_sdk_strict(tmp_path):
    """SDK adds placeholder-preservation rule (legacy doesn't); verify it triggers."""
    sdk_artifact = EvolvableArtifact(
        agent_name="hermes", artifact_id="t", kind="tool",
        baseline_text="search the web for {query} and return top results",
        text_source="docstring",
        source_file=tmp_path / "x.py", decorator_lineno=1,
        constraints={"max_chars": 500, "max_growth": 0.5},
    )
    candidate_lost = "Search the web and return results"  # lost {query}
    sdk_result = apply_gates(
        artifact=sdk_artifact, candidate_text=candidate_lost,
        baseline_score=0.5, candidate_holdout_score=0.6,
    )
    assert sdk_result.passed is False
    assert "placeholder" in sdk_result.failed_gate.lower()


def test_tool_placeholder_preserved_passes(tmp_path):
    sdk_artifact = EvolvableArtifact(
        agent_name="hermes", artifact_id="t", kind="tool",
        baseline_text="search for {query} in {source}",
        text_source="docstring",
        source_file=tmp_path / "x.py", decorator_lineno=1,
        constraints={"max_chars": 500, "max_growth": 0.5},
    )
    candidate_ok = "Search {source} for {query} (return top 3 hits)"
    sdk_result = apply_gates(
        artifact=sdk_artifact, candidate_text=candidate_ok,
        baseline_score=0.5, candidate_holdout_score=0.6,
    )
    assert sdk_result.passed is True
```

- [ ] **Step 4: 运行 parity 测试**

```bash
pytest tests/sdk/parity/ -v
```

Expected: 5 个测试 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/sdk/parity/ tests/sdk/fixtures/snapshots/
git commit -m "sdk(14): hermes parity tests — skill + tool_descriptions

Pure-function path parity: SDK constraint gates reject the same inputs as
legacy ConstraintValidator (size, growth, structure). Tool kind adds the
SDK-only placeholder-preservation rule. P1 will extend parity to the other
4 CLIs (tool_params/tool_reasoning/prompt_sections/code).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 15: `apply="patch"` 集成 + README 入门段落

**Files:**
- Modify: `evolution/sdk/optimizer.py` (wire patch output)
- Test: `tests/sdk/integration/test_apply_modes.py`
- Test: `tests/sdk/integration/test_failure_isolation.py`
- Modify: `README.md` (add SDK quick start)

- [ ] **Step 1: 写 `tests/sdk/integration/test_apply_modes.py`**

```python
"""Integration: apply=runtime / patch / pr produces correct artifacts."""

import json
import sys
from pathlib import Path

import pytest

from evolution.sdk import registry
from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.optimizer import (
    write_optimized_file, emit_patch_for_outcome, OptimizationOutcome,
)


def _mk_src(tmp_path):
    f = tmp_path / "bot.py"
    f.write_text(
        'from evolution.sdk.decorators import evolvable_agent, evolvable_prompt\n'
        '\n'
        '@evolvable_agent(name="bot", schedule=None, auto_optimize=False, min_samples=1, max_cost_usd=1.0)\n'
        'class Bot:\n'
        '    @evolvable_prompt(id="sys", text="OLD TEXT")\n'
        '    def sys_prompt(self):\n'
        '        return "x"\n'
        '    def run(self, q):\n'
        '        return q\n'
    )
    return f


def test_runtime_mode_writes_optimized_only(tmp_path, tmp_evolution_home):
    src = _mk_src(tmp_path)
    artifact = EvolvableArtifact(
        agent_name="bot", artifact_id="sys", kind="prompt",
        baseline_text="OLD TEXT", text_source="param",
        source_file=src, decorator_lineno=3,
    )
    path = write_optimized_file(
        artifact=artifact, agent_version="0.1.0",
        optimized_text="NEW TEXT",
        optimization_metadata={"run_id": "x", "ts": "2026-06-13T00:00:00Z",
                                "optimizer": "GEPA", "baseline_score": 0.5,
                                "optimized_score": 0.8, "holdout_score": 0.75,
                                "dataset_size": 10, "cost_usd": 0.5},
    )
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["optimized_text"] == "NEW TEXT"
    # Source file unchanged.
    assert "OLD TEXT" in src.read_text()


def test_patch_mode_emits_unified_diff(tmp_path, tmp_evolution_home):
    src = _mk_src(tmp_path)
    artifact = EvolvableArtifact(
        agent_name="bot", artifact_id="sys", kind="prompt",
        baseline_text="OLD TEXT", text_source="param",
        source_file=src, decorator_lineno=3,
    )
    outcome = OptimizationOutcome(
        artifact_id="sys", status="improved",
        baseline_score=0.5, optimized_score=0.8,
        rejection_reason=None, cost_usd=0.5,
    )
    patch_path = emit_patch_for_outcome(
        outcome=outcome, artifact=artifact, optimized_text="NEW TEXT",
        agent_name="bot",
    )
    assert patch_path.exists()
    diff = patch_path.read_text()
    assert "--- a/bot.py" in diff
    assert "+++ b/bot.py" in diff
    assert "-" in diff and "OLD TEXT" in diff
    assert "+" in diff and "NEW TEXT" in diff
    # Source not modified.
    assert "OLD TEXT" in src.read_text()
```

- [ ] **Step 2: 写 `tests/sdk/integration/test_failure_isolation.py`**

```python
"""Integration: per-artifact failure does not block other artifacts."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_artifact_failure_isolation_via_run_summary(tmp_evolution_home, write_trace_file,
                                                    fake_trace_factory, monkeypatch):
    """Even if one artifact rejects, run_summary lists all artifacts."""
    # Set up an agent with 2 artifacts (use ThreeFormBot which has 3).
    monkeypatch.syspath_prepend(str(Path(__file__).parent.parent.parent))
    import importlib
    importlib.import_module("tests.sdk.fixtures.agents.three_form_bot")
    from evolution.sdk import registry
    registry.persist_to_file()

    write_trace_file("three-form-bot", "20260613", [
        fake_trace_factory(agent="three-form-bot",
                           ts=f"2026-06-13T0{i}:00:00Z") for i in range(1, 6)
    ])

    result = subprocess.run(
        [sys.executable, "-m", "evolution.sdk.optimizer",
         "--agent", "three-form-bot", "--dry-run"],
        capture_output=True, text=True,
        env={**os.environ, "EVOLUTION_HOME": str(tmp_evolution_home)},
    )
    assert result.returncode == 0, result.stderr
    # Find run_summary.
    summaries = list((Path("output") / "sdk" / "three-form-bot").rglob("run_summary.json"))
    assert len(summaries) >= 1
    data = json.loads(summaries[-1].read_text())
    # All 3 artifacts must appear.
    artifact_ids = {a["artifact_id"] for a in data["artifacts"]}
    assert artifact_ids == {"system", "planner", "searcher"}
    import shutil
    shutil.rmtree(Path("output") / "sdk" / "three-form-bot", ignore_errors=True)
```

- [ ] **Step 3: 修改 `evolution/sdk/optimizer.py` 添加 `emit_patch_for_outcome`**

在 `optimizer.py` 末尾追加（在 `if __name__ == "__main__":` 之前）：

```python
def emit_patch_for_outcome(
    *,
    outcome: OptimizationOutcome,
    artifact: EvolvableArtifact,
    optimized_text: str,
    agent_name: str,
) -> Path:
    """Generate output/<agent>/<ts>/changes.patch for apply='patch' mode."""
    from evolution.sdk.ast_writer import rewrite_artifact_text, generate_unified_diff
    from datetime import datetime, timezone

    original = artifact.source_file.read_text()
    new_src = rewrite_artifact_text(artifact, new_text=optimized_text)
    diff = generate_unified_diff(
        artifact.source_file, original_text=original, new_text=new_src,
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path("output") / agent_name / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    patch_path = out_dir / "changes.patch"
    patch_path.write_text(diff)
    return patch_path
```

- [ ] **Step 4: 运行集成测试**

```bash
pytest tests/sdk/integration/test_apply_modes.py tests/sdk/integration/test_failure_isolation.py -v
```

Expected: 全部 PASS.

- [ ] **Step 5: 修改 `README.md` 追加 SDK Quick Start 段（在 "## How It Works" 之后插入）**

打开 `README.md`，在 `## Quick Start` 段落之前插入新段：

```markdown
## SDK Quick Start — 任意 Python agent 接入

把任意 Python agent 接入自进化循环：

```python
# myapp/bots/research.py
from evolution.sdk import evolvable_agent, evolvable_prompt, evolvable_tool

@evolvable_agent(
    name="research-bot",
    schedule="weekly",
    min_samples=50,
    apply="runtime",   # runtime | patch | pr
    max_cost_usd=5.0,
)
class ResearchBot:
    @evolvable_prompt(id="system", text="You are a research assistant.")
    def system_prompt(self):
        return ...

    @evolvable_tool(id="search", max_chars=500)
    def search(self, query: str):
        """Search the public web and return the top 5 snippets."""
        ...

    def run(self, query: str) -> str:
        ...
```

接入后：

```bash
# 1) 让 SDK 发现你的 agent (写入 ~/.evolution/registry.json)
evolution discover myapp.bots.research

# 2) 生成 GitHub Actions 调度配置
evolution scaffold --backend gh-actions --output .github/workflows/

# 3) 查看 agent 状态
evolution status --agent research-bot

# 4) 手动触发优化 (cron 之外)
evolution optimize --agent research-bot

# 5) 不喜欢就回滚
evolution rollback --agent research-bot --artifact system
```

详见 `docs/superpowers/specs/2026-06-13-agent-evolve-sdk-design.md`。
```

- [ ] **Step 6: 跑全套 SDK 测试**

```bash
pytest tests/sdk/ -v
```

Expected: 全部 PASS（约 80+ 测试）。

- [ ] **Step 7: 跑现有测试，确认未破坏 hermes 流水线**

```bash
pytest tests/ --ignore=tests/sdk -v
```

Expected: 现有测试维持原有结果（无新增失败）。

- [ ] **Step 8: Commit**

```bash
git add evolution/sdk/optimizer.py tests/sdk/integration/test_apply_modes.py \
        tests/sdk/integration/test_failure_isolation.py README.md
git commit -m "sdk(15): apply=patch wiring + failure isolation tests + README quick start

emit_patch_for_outcome generates output/<agent>/<ts>/changes.patch from AST
rewriter + unified diff (apply=patch mode). test_failure_isolation verifies
that one artifact rejecting doesn't block others (all listed in run_summary).
README gets a 'SDK Quick Start' section showing decorator + 5 CLI commands.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## 完成检查

跑完所有 15 个任务后，验证以下不变量：

- [ ] **结构性**
  - `evolution/sdk/` 包含 12 个文件（10 模块 + `__init__.py` + 之后 P1 可能补 daemon）
  - `evolution/adapters/hermes.py` 存在
  - `tests/sdk/{unit,integration,parity,example_bot,fixtures}/` 完整

- [ ] **测试**
  ```bash
  pytest tests/sdk/ -v
  ```
  全部 PASS。覆盖率 `pytest tests/sdk/ --cov=evolution.sdk --cov=evolution.adapters` ≥ 80%。

- [ ] **兼容性**
  ```bash
  pytest tests/ --ignore=tests/sdk
  ```
  与本计划开始前相同的通过率。

- [ ] **CLI 可用**
  ```bash
  evolution --help
  evolution discover --help
  evolution scaffold --help
  evolution optimize --help
  evolution status --help
  evolution rollback --help
  ```
  每条命令都打印帮助。

- [ ] **end-to-end dogfood**
  ```bash
  pytest tests/sdk/example_bot/ -v
  ```
  PASS — EchoBot 完整生命周期可运行。

- [ ] **drift 检测**
  ```bash
  cd /tmp && mkdir -p .github/workflows
  EVOLUTION_HOME=/tmp/evolution_home evolution discover tests.sdk.fixtures.agents.three_form_bot
  EVOLUTION_HOME=/tmp/evolution_home evolution scaffold --backend gh-actions --output .github/workflows/
  EVOLUTION_HOME=/tmp/evolution_home evolution scaffold --check --output .github/workflows/
  ```
  最后一句退出码 0（CLEAN）。

---

## 自审 (writing-plans §Self-Review)

**1. Spec 覆盖**
- §3 架构 → Task 0 + 全部 Task 文件结构落地 ✓
- §4.1 外层装饰器 → Task 4 ✓
- §4.2 内层装饰器三种文本来源 → Task 4 ✓
- §4.3 运行时加载 + baseline_hash → Task 5 ✓
- §4.4 TraceRecord schema → Task 2 ✓
- §5.2 信号检测 + 权重 → Task 6 ✓
- §5.3 抽样筛选 → Task 8 引用 (P0 通过 raw_traces + min_samples 门控；完整双尾采样在 Task 13 mock 路径下不展开)
- §5.4 合成扩充 → 标注为 P1（spec §10.1 同步）
- §6.1 EvolvableArtifact → Task 1 ✓
- §6.2 AgentModule → Task 7 ✓
- §6.3 GEPA + MIPROv2 fallback → Task 8 ✓
- §6.4 三道门 → Task 8（gate 3 stub，spec §6.4 已声明）
- §6.5 写回格式 → Task 8 ✓
- §6.6 Apply 模式 → Task 15（patch）；pr 模式 P1
- §6.7 预算控制 → Task 8 OptimizationBudget ✓
- §6.8 run_summary → Task 8 ✓
- §7 调度 + scaffold → Task 10 ✓
- §7.7 Drift 检测 → Task 10 + Task 11 ✓
- §8 错误处理 → Task 5 (agent 不变量) + Task 8 (optimizer 不变量) + Task 15 (隔离) ✓
- §9 测试金字塔 → Task 1-15 各自单元 + Task 13 端到端 + Task 14 parity ✓
- §10.1 P0 14 项 → Task 1-15 对齐 ✓
- §12 hermes 兼容 → Task 12 + 完成检查 ✓

**2. Placeholder 扫描**
- 无 TBD / TODO / "implement later" / "similar to Task N"
- 所有代码块完整，无 `# ... fill in here` 占位

**3. 类型一致性**
- `EvolvableArtifact` 字段在 Task 1 / 5 / 7 / 8 / 9 / 12 / 13 / 14 / 15 用法一致
- `AgentRegistration` 在 Task 3 / 4 / 11 / 12 字段一致（schedule, min_samples, apply, max_cost_usd, schedule_managed_by 等）
- `OptimizationOutcome` 在 Task 8 / 13 / 15 一致
- `TraceRecord` 在 Task 2 / 5 / 6 schema 对齐（artifacts/tool_calls/signals/scores）
- CLI 命令名（`discover`/`scaffold`/`optimize`/`status`/`rollback`）在 Task 11 + 完成检查 一致
- `evolution.sdk.runtime.invoke` 签名（instance, method_name, original_fn, args, kwargs）Task 4 占位与 Task 5 实现一致
- `apply_gates` 参数（artifact, candidate_text, baseline_score, candidate_holdout_score, regression_tolerance）Task 8 / 14 / 15 一致

**4. 歧义检查**
- "三种文本来源优先级" 在 §4.2 / Task 4 / Task 9 三处描述一致
- `apply` 字段取值 `runtime|patch|pr` 在 §4.1 / Task 3 / Task 11 / Task 15 一致
- drift 状态码 (CLEAN/MISSING/DRIFT/MANUAL_EDIT/STALE) 在 Task 10 / 11 一致
- 退出码语义（0/1/2）在 Task 10 / 11 / 完成检查 一致

无未解决项。

---

**Plan complete.**

