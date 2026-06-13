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
