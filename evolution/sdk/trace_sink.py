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
