"""TBLite subprocess wrapper for Phase 20 benchmark-gated validation.

Async Stream Pipe + State Monitor: subprocess.Popen + 2 daemon threads
pump stdout/stderr into a queue.Queue. Main loop polls q.get(timeout=
heartbeat_seconds) and increments hang_count on queue.Empty. After
max_hangs consecutive empties, SIGTERM the subprocess and return
status='hang_timeout' (D-11).

After subprocess exits (or is terminated), parse samples_*.jsonl with
per-line try/except json.JSONDecodeError (Phase 19 D-24 / CONCERNS §M7);
rows with non-empty 'error' field are flagged infra_fail for
BenchmarkGate to exclude from tier pass-rate denominators (Risk
Anchor 3 in CONTEXT.md — distinguish infra failures from prompt
failures).

compute_artifact_hash() implements D-15 content-addressed cache key
formula: sha256(canonical_json(evolved) + dataset_revision_hash +
seed.to_bytes(4) + TBLITE_RUNNER_VERSION).hexdigest()[:16].

TBLITE_RUNNER_VERSION is a module-level constant; bumping it
invalidates all cached results across runner upgrades.

Security boundary: task_filter values are validated against a strict
whitelist regex BEFORE being joined into the subprocess args (T-20-05
mitigation — TBLite task names follow the [a-zA-Z0-9_-]+ pattern).
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()

# ── Module-level constants ─────────────────────────────────────────────────────

# D-15 cache key: bump when subprocess command shape, env interaction,
# or samples.jsonl parsing schema changes. Every consumer of
# compute_artifact_hash() reads this constant — never hardcode.
TBLITE_RUNNER_VERSION = "1.0"

# D-11 heartbeat defaults (overridable per-instance via constructor).
HEARTBEAT_SECONDS = 60
MAX_HANGS = 3

# T-20-05 mitigation: TBLite task names are alphanumeric + hyphen + underscore.
# Reject anything outside this whitelist BEFORE subprocess construction so
# shell metachars (';', '$', '`', '|', '&', spaces, newlines) cannot be
# smuggled in via crafted --benchmark-tier CSV or dataset poisoning.
_TASK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-./]{0,127}$")

# Phase 19 D-24 mirror: warn when bad-line ratio > 5%.
_JSONL_BAD_LINE_WARN_THRESHOLD = 0.05


# ── TBLiteRunResult dataclass ──────────────────────────────────────────────────

@dataclass
class TBLiteRunResult:
    """Result of one TBLite subprocess invocation.

    Attributes:
        per_task: list of dicts parsed from samples_*.jsonl. Each dict
            has at least {task_name: str, category: str, passed: bool,
            infra_fail: bool}. Additional fields from TBLite are
            forwarded through unchanged.
        subprocess_runtime_seconds: monotonic time spent in proc.wait().
        hang_count: number of heartbeat_seconds intervals with no new
            stdout/stderr line.
        cost_breakdown: dict of cost source -> usd. Populated by
            downstream caller (TBLiteRunner does not parse Modal/OpenRouter
            usage — that's BenchmarkGate's job once we wire CostTracker).
        samples_jsonl_path: absolute path to the parsed samples file,
            or None when subprocess exited before producing one.
        exit_code: subprocess return code (-1 = never ran).
        status: 'ok' | 'hang_timeout' | 'error'.
        jsonl_skipped_lines: count of malformed samples.jsonl lines
            (Phase 19 D-24 mirror).
        stderr_tail: last 20 stderr lines (debugging aid for hang_timeout
            / error paths).
    """

    per_task: list[dict] = field(default_factory=list)
    subprocess_runtime_seconds: float = 0.0
    hang_count: int = 0
    cost_breakdown: dict[str, float] = field(default_factory=dict)
    samples_jsonl_path: Optional[Path] = None
    exit_code: int = -1
    status: str = "ok"
    jsonl_skipped_lines: int = 0
    stderr_tail: list[str] = field(default_factory=list)


# ── Daemon thread pump function ────────────────────────────────────────────────

def _pump_stream(stream, q: "queue.Queue", stream_name: str) -> None:
    """Daemon-thread target: push (stream_name, line) onto q until EOF.

    Exits when stream.readline returns '' (subprocess closed the stream
    on exit). The sentinel iter(stream.readline, '') gives line-buffered
    reads thanks to subprocess.Popen(text=True, bufsize=1).

    This function must NEVER raise — it runs in a daemon thread, and an
    unhandled exception would silently kill the pump without surfacing
    a signal to the main loop. Use a broad try/except.
    """
    try:
        for line in iter(stream.readline, ""):
            q.put((stream_name, line.rstrip("\n")))
    except (ValueError, OSError):
        # ValueError: I/O on closed file (race with terminate()).
        # OSError: broken pipe.
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


# ── Sanitization helper ────────────────────────────────────────────────────────

def _validate_task_filter(task_filter: list[str]) -> str:
    """Validate + join task names into a single CSV string.

    Raises ValueError if any task name fails _TASK_NAME_RE. Returns the
    CSV string ready for --env.task_filter.
    """
    if not isinstance(task_filter, list) or not task_filter:
        raise ValueError(
            "task_filter must be a non-empty list of task names"
        )
    for name in task_filter:
        if not isinstance(name, str) or not _TASK_NAME_RE.match(name):
            raise ValueError(
                f"Unsafe task name {name!r}: must match "
                f"[A-Za-z0-9][A-Za-z0-9_\\-./]{{0,127}}. T-20-05 "
                f"mitigation: shell metachars are rejected at the gate."
            )
    return ",".join(task_filter)


# ── TBLiteRunner class ─────────────────────────────────────────────────────────

class TBLiteRunner:
    """Subprocess wrapper for hermes-agent's TBLite benchmark.

    Args:
        config: EvolutionConfig — provides hermes_agent_path,
            benchmark_heartbeat_seconds, benchmark_runs (latter is
            consumed by callers, not by this class).
        heartbeat_seconds: override config.benchmark_heartbeat_seconds.
        max_hangs: consecutive heartbeat_seconds intervals without
            output before SIGTERM.
    """

    def __init__(
        self,
        config,
        *,
        heartbeat_seconds: Optional[int] = None,
        max_hangs: int = MAX_HANGS,
    ):
        self.config = config
        # T-20-04 clamp: never accept heartbeat_seconds <= 0.
        hb_raw = (
            heartbeat_seconds
            if heartbeat_seconds is not None
            else getattr(config, "benchmark_heartbeat_seconds", HEARTBEAT_SECONDS)
        )
        self.heartbeat_seconds = max(1, int(hb_raw))
        self.max_hangs = max(1, int(max_hangs))

    def _build_args(self, task_csv: str, output_dir: Path) -> list[str]:
        """Build subprocess args for `python tblite_env.py evaluate ...`.

        Uses python directly (not run_eval.sh) so cwd and env propagation
        are explicit. The exact tblite_env.py invocation is documented in
        ~/.hermes/hermes-agent/environments/benchmarks/tblite/README.md.
        """
        hermes_path = Path(self.config.hermes_agent_path)
        return [
            "python",
            str(hermes_path / "environments" / "benchmarks" / "tblite" / "tblite_env.py"),
            "evaluate",
            "--config",
            str(hermes_path / "environments" / "benchmarks" / "tblite" / "default.yaml"),
            "--env.task_filter",
            task_csv,
            "--env.data_dir_to_save_evals",
            str(output_dir),
        ]

    def run(
        self,
        task_filter: list[str],
        output_dir: Path,
        *,
        runs: int = 1,  # CALLERS handle multi-run aggregation; this is per-call.
    ) -> TBLiteRunResult:
        """Run TBLite once on task_filter, parse samples.jsonl, return result.

        For 3-run averaging (D-03), the caller invokes run() 3 times and
        aggregates — keeping a single subprocess.Popen per call simplifies
        error handling and cache key computation.

        Args:
            task_filter: list of task names (validated against _TASK_NAME_RE).
            output_dir: where TBLite writes samples_<ts>.jsonl.
            runs: kept for forward compatibility; currently ignored
                (use repeated run() calls for runs > 1).

        Returns:
            TBLiteRunResult with per_task / status / jsonl_skipped_lines /
            exit_code populated.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        task_csv = _validate_task_filter(task_filter)
        args = self._build_args(task_csv, output_dir)

        result = TBLiteRunResult()
        t_start = time.monotonic()

        # Inherit user env so OPENROUTER_API_KEY / MODAL_TOKEN_ID / etc.
        # propagate to the subprocess (D-11 / CONTEXT §Specifics).
        env = os.environ.copy()

        console.print(
            f"[bold]TBLite subprocess starting[/bold] "
            f"({len(task_filter)} tasks, heartbeat {self.heartbeat_seconds}s)"
        )

        proc = subprocess.Popen(
            args,
            cwd=str(Path(self.config.hermes_agent_path)),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

        q: "queue.Queue" = queue.Queue()
        t_out = threading.Thread(
            target=_pump_stream,
            args=(proc.stdout, q, "stdout"),
            daemon=True,
        )
        t_err = threading.Thread(
            target=_pump_stream,
            args=(proc.stderr, q, "stderr"),
            daemon=True,
        )
        t_out.start()
        t_err.start()

        stderr_buf: list[str] = []
        while True:
            try:
                stream_name, line = q.get(timeout=self.heartbeat_seconds)
                # Reset hang counter on ANY line (stdout or stderr).
                result.hang_count = 0
                if stream_name == "stderr":
                    stderr_buf.append(line)
                    # Keep tail bounded to avoid OOM on huge log spew.
                    if len(stderr_buf) > 1000:
                        stderr_buf = stderr_buf[-1000:]
                # Forward [PASS]/[FAIL]/[START] markers and tqdm lines to
                # console for --wait mode visibility. Plan 06 may swap in
                # rich.live.Live; this baseline is plain stdout.
                if line.startswith(("[START]", "[PASS]", "[FAIL]")):
                    console.print(f"  {line}")
            except queue.Empty:
                if proc.poll() is not None:
                    # Subprocess exited while queue was draining — exit loop.
                    break
                result.hang_count += 1
                console.print(
                    f"[yellow]TBLite hang #{result.hang_count}/{self.max_hangs} "
                    f"({self.heartbeat_seconds}s no output)[/yellow]"
                )
                if result.hang_count >= self.max_hangs:
                    console.print(
                        f"[red]TBLite hung {self.max_hangs} x "
                        f"{self.heartbeat_seconds}s — sending SIGTERM[/red]"
                    )
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                    result.status = "hang_timeout"
                    break

        # Drain anything left in the queue after exit.
        while True:
            try:
                stream_name, line = q.get_nowait()
                if stream_name == "stderr":
                    stderr_buf.append(line)
            except queue.Empty:
                break

        proc.wait()
        result.subprocess_runtime_seconds = time.monotonic() - t_start
        result.exit_code = proc.returncode
        result.stderr_tail = stderr_buf[-20:]

        if result.status == "ok" and result.exit_code != 0:
            result.status = "error"

        # Parse samples_<ts>.jsonl regardless of status — partial results
        # are still useful for diagnosis (the gate ignores them on error
        # path; the calibration CLI may also choose to abort).
        samples_files = sorted(output_dir.glob("samples_*.jsonl"))
        if samples_files:
            result.samples_jsonl_path = samples_files[-1]
            per_task, skipped = self._parse_samples_jsonl(result.samples_jsonl_path)
            result.per_task = per_task
            result.jsonl_skipped_lines = skipped
            total = len(per_task) + skipped
            if total > 0 and skipped / total > _JSONL_BAD_LINE_WARN_THRESHOLD:
                console.print(
                    f"[yellow]TBLite samples.jsonl: skipped {skipped}/{total} "
                    f"bad lines ({skipped / total * 100:.1f}%) > "
                    f"{int(_JSONL_BAD_LINE_WARN_THRESHOLD * 100)}% threshold[/yellow]"
                )

        return result

    def _parse_samples_jsonl(self, jsonl_path: Path) -> tuple[list[dict], int]:
        """Per-line JSON parse + infra_fail flagging (Phase 19 D-24 mirror).

        A row is infra_fail when its 'error' field is a non-empty string.
        BenchmarkGate uses infra_fail to exclude rows from tier pass-rate
        denominators (Risk Anchor 3 — distinguish infra vs prompt failures).
        """
        per_task: list[dict] = []
        skipped = 0
        with open(jsonl_path) as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
                # Normalize tier: TBLite emits 'category' but spec allows
                # 'difficulty' / 'tier' as fallback. Lowercase + strip.
                tier_raw = (
                    row.get("category")
                    or row.get("difficulty")
                    or row.get("tier")
                    or "unknown"
                )
                row["category"] = str(tier_raw).strip().lower()
                err = row.get("error") or ""
                row["infra_fail"] = bool(isinstance(err, str) and err.strip())
                per_task.append(row)
        return per_task, skipped


# ── Cache key helpers ──────────────────────────────────────────────────────────

def _canonical_json(obj) -> str:
    """Stable JSON encoding for hashing: sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_artifact_hash(
    evolved_sections,
    dataset_revision_hash: str,
    stratified_subset_seed: int,
    tblite_runner_version: str = TBLITE_RUNNER_VERSION,
) -> str:
    """D-15 cache key formula.

    Accepts either:
      - a list of objects with .section_id and .text attributes (PromptSection
        from evolution.prompts.prompt_loader), OR
      - a list of dicts already shaped as {'section_id': str, 'text': str}.

    Args:
        evolved_sections: see above.
        dataset_revision_hash: HuggingFace dataset commit sha for
            NousResearch/openthoughts-tblite (or 'unknown_v<ver>'
            fallback when the API is unavailable — see Plan 04).
        stratified_subset_seed: seed from
            datasets/prompts/tblite_stratified_subset.json.
        tblite_runner_version: defaults to module-level constant.

    Returns:
        16-char hex digest. SHORT BY DESIGN — the cache directory
        name is human-readable.
    """
    normalized = []
    for s in evolved_sections:
        if hasattr(s, "section_id") and hasattr(s, "text"):
            normalized.append({"section_id": s.section_id, "text": s.text})
        elif isinstance(s, dict):
            # CR-04 (2026-05-19): raise TypeError on missing required keys
            # instead of letting KeyError bubble out of bare subscription.
            # The gate's check() invokes this; a malformed cache lookup
            # should fail with a clear error pointing at the offending
            # dict, not a stack trace inside the cache code.
            if "section_id" not in s or "text" not in s:
                raise TypeError(
                    f"evolved_sections dict missing required keys "
                    f"'section_id' and/or 'text': got keys={sorted(s.keys())}"
                )
            normalized.append({
                "section_id": s["section_id"],
                "text": s["text"],
            })
        else:
            raise TypeError(
                f"evolved_sections items must be PromptSection or "
                f"dict; got {type(s).__name__}"
            )
    h = hashlib.sha256()
    h.update(_canonical_json(normalized).encode("utf-8"))
    h.update(dataset_revision_hash.encode("utf-8"))
    h.update(int(stratified_subset_seed).to_bytes(4, "big"))
    h.update(tblite_runner_version.encode("utf-8"))
    return h.hexdigest()[:16]
