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
    TraceRecord, TraceSink, LocalJsonlSink, get_default_sink, _evolution_home,
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
    # Re-create sink each call so EVOLUTION_HOME changes (e.g., in tests) are respected.
    sink: TraceSink = meta.get("sink") or LocalJsonlSink()
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
            output=error_text,  # store error text in output so readers can inspect it
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
    # Heuristic: if single positional arg is a primitive, expose only as "q" for
    # readability (most agents take one input). Otherwise use indexed arg keys.
    if len(args) == 1 and not kwargs and isinstance(args[0], (str, int, float, bool)):
        return {"q": args[0]}
    payload = {}
    for i, a in enumerate(args):
        payload[f"arg{i}"] = _jsonable(a)
    for k, v in kwargs.items():
        payload[k] = _jsonable(v)
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
