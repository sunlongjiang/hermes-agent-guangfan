---
phase: 20-benchmark-gated-validation
plan: 02
type: execute
wave: 2
revised_at: 2026-05-19
depends_on:
  - 20-01-config-scaffolding-PLAN.md
files_modified:
  - evolution/benchmarks/tblite_runner.py
  - tests/benchmarks/__init__.py
  - tests/benchmarks/test_tblite_runner.py
autonomous: true
requirements:
  - PMPT-V2-03
requirements_addressed:
  - PMPT-V2-03
tags:
  - phase-20
  - benchmark
  - subprocess
must_haves:
  truths:
    - "evolution/benchmarks/tblite_runner.py exposes TBLiteRunner class with run(task_filter, output_dir, *, runs=1) -> TBLiteRunResult"
    - "TBLiteRunner.run constructs subprocess.Popen with cwd=hermes_agent_path, text=True, bufsize=1, stdout/stderr=PIPE — NOT subprocess.run (must be streaming)"
    - "Two daemon threads pump stdout/stderr into a queue.Queue; main loop polls queue.get(timeout=heartbeat_seconds)"
    - "queue.Empty + subprocess still running -> hang_count += 1; hang_count >= max_hangs -> proc.terminate() + status='hang_timeout'"
    - "samples_*.jsonl parser uses per-line try/except json.JSONDecodeError + counts skipped (Phase 19 D-24 mirror); infra-failure rows (error field set) flagged but NOT raised"
    - "compute_artifact_hash() function returns 16-char hex from sha256(canonical evolved sections + dataset_revision_hash + seed.to_bytes(4) + TBLITE_RUNNER_VERSION) per D-15"
    - "TBLITE_RUNNER_VERSION module-level constant exposed (currently '1.0') for cache-key invalidation across runner upgrades"
    - "Task_filter values are sanitized via shlex.quote / a strict whitelist regex BEFORE being joined into the subprocess args (D-11 / T-20-05 mitigation)"
    - "tests/benchmarks/test_tblite_runner.py contains TestTBLiteRunner class with at least 7 tests covering: popen_args / stream_pipe parse / heartbeat hang / samples parse / jsonl bad-line skip / infra-fail flagging / artifact_hash determinism"
  artifacts:
    - path: evolution/benchmarks/tblite_runner.py
      provides: "TBLiteRunner subprocess wrapper + TBLiteRunResult dataclass + compute_artifact_hash + TBLITE_RUNNER_VERSION + Phase 19 D-24 jsonl-skip"
      contains: "class TBLiteRunner"
      min_lines: 180
    - path: tests/benchmarks/__init__.py
      provides: "empty package marker"
      contains: ""
    - path: tests/benchmarks/test_tblite_runner.py
      provides: "7+ unit tests using unittest.mock.patch('subprocess.Popen')"
      contains: "class TestTBLiteRunner"
      min_lines: 200
  key_links:
    - from: tblite_runner.py
      to: subprocess.Popen
      via: "subprocess.Popen(args, cwd=hermes_agent_path, stdout=PIPE, stderr=PIPE, text=True, bufsize=1)"
      pattern: "subprocess\\.Popen"
    - from: tblite_runner.py
      to: threading.Thread (daemon stdout/stderr pump)
      via: "threading.Thread(target=_pump_stream, args=(proc.stdout, q, 'stdout'), daemon=True).start()"
      pattern: "threading\\.Thread.*daemon=True"
    - from: tblite_runner.py
      to: queue.Queue (heartbeat detection)
      via: "q.get(timeout=heartbeat_seconds) raising queue.Empty -> hang_count += 1"
      pattern: "queue\\.Empty"
    - from: tblite_runner.py
      to: hashlib.sha256 (cache fingerprint)
      via: "hashlib.sha256().update(canonical_json + revision_hash + seed_bytes + runner_version).hexdigest()[:16]"
      pattern: "hashlib\\.sha256"
---

<objective>
Wave 2 (parallel with Plan 03) — Build `TBLiteRunner`, the subprocess wrapper that Phase 20 uses to invoke `~/.hermes/hermes-agent/environments/benchmarks/tblite/tblite_env.py evaluate` and parse its streaming output safely.

This is the ONE file in Phase 20 with no direct evolution-codebase analog (PATTERNS §No Analog Found §1) — `evolution/core/constraints.py:55-93` uses `subprocess.run` (blocking, `capture_output=True`) but TBLite runs 30-120 minutes and must stream output for progress reporting and hang detection.

The runner must:
1. Build subprocess args that mirror `bash run_eval.sh --config default.yaml --env.task_filter <csv>` (CONTEXT §Specifics command-line template), passing through cwd=hermes_agent_path + env=os.environ.copy() (transparent OPENROUTER_API_KEY / MODAL_TOKEN_ID).
2. Use **Async Stream Pipe + State Monitor pattern** (PATTERNS §File 2): `subprocess.Popen` + `bufsize=1` + 2 daemon threads pumping stdout/stderr lines into a `queue.Queue` + main loop polling `q.get(timeout=heartbeat_seconds)`. Heartbeat detection: 60s without new line → `hang_count += 1`; `hang_count >= 3` → SIGTERM (D-11).
3. After subprocess exits, parse `output_dir/samples_*.jsonl` with **per-line try/except json.JSONDecodeError** (Phase 19 D-24 + CONCERNS §M7), counting `jsonl_skipped_lines`. Flag rows with non-empty `error` field as `infra_fail` (D-11/Risk Anchor 3) so downstream `BenchmarkGate` (Plan 03) can exclude them from tier pass-rate denominators.
4. Provide `compute_artifact_hash(evolved_sections, dataset_revision_hash, seed) -> str` (D-15 cache key) — used by both `TBLiteBenchmarkGate` (Plan 03) and `build_tblite_calibration` (Plan 04).
5. Expose `TBLITE_RUNNER_VERSION = "1.0"` module-level constant (D-15: bumping invalidates cache).

Purpose: Provide the deterministic, testable subprocess primitive that Plans 03 / 04 / 06 all depend on. Without this, every consumer would need to re-implement subprocess.Popen + threading + jsonl parsing.

Output: 1 production file (`tblite_runner.py`, ~250-300 lines), 1 test package marker, 1 test file (~250 lines, 7+ tests).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/20-benchmark-gated-validation/20-CONTEXT.md
@.planning/phases/20-benchmark-gated-validation/20-PATTERNS.md
@evolution/core/constraints.py
@evolution/core/config.py
@evolution/prompts/drift_detector.py
@tests/prompts/test_drift_detector.py
@./CLAUDE.md

<interfaces>
<!-- Wave 1 contracts being consumed (Plan 01 added these fields). -->
From evolution/core/config.py (Plan 01 additions):
```python
@dataclass
class EvolutionConfig:
    hermes_agent_path: Path = field(default_factory=lambda: get_hermes_agent_path())
    benchmark_max_cost_usd: float = 50.0
    tblite_estimated_cost_per_task_usd: float = 0.4
    benchmark_runs: int = 3
    benchmark_heartbeat_seconds: int = 60
    # ... other existing fields ...
```

<!-- Blocking analog: evolution/core/constraints.py:55-93. This is the ONLY subprocess usage in the evolution package. Phase 20 must NOT pattern-match this (it's blocking) but should match its cwd/text/timeout style. -->
From evolution/core/constraints.py:55-93:
```python
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
            return ConstraintResult(passed=True, constraint_name="test_suite", ...)
        else:
            return ConstraintResult(passed=False, constraint_name="test_suite", ...)
    except subprocess.TimeoutExpired:
        return ConstraintResult(passed=False, constraint_name="test_suite", message="Test suite timed out (300s)")
```

<!-- hermes-agent target subprocess (read-only reference, NOT modified). -->
TBLite CLI invocation template (from CONTEXT §Specifics):
```bash
cd ~/.hermes/hermes-agent && python environments/benchmarks/tblite/tblite_env.py evaluate \
  --config environments/benchmarks/tblite/default.yaml \
  --env.task_filter "task1,task2,task3,..." \
  --env.data_dir_to_save_evals "<output_path>"
```
Output: `<output_path>/samples_<ts>.jsonl` — one JSON object per task with at least: {task_name, category, passed, score, ...}.

<!-- D-15 cache key formula from CONTEXT §Specifics. -->
```python
artifact_hash = sha256(
    canonical_json(evolved_sections).encode()
    + dataset_revision_hash.encode()
    + stratified_subset_seed.to_bytes(4, "big")
    + tblite_runner_version.encode()
).hexdigest()[:16]
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create evolution/benchmarks/tblite_runner.py with TBLiteRunner + TBLiteRunResult + compute_artifact_hash + TBLITE_RUNNER_VERSION</name>
  <files>evolution/benchmarks/tblite_runner.py</files>
  <read_first>
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 2 (entire section — Adaptation Delta 7 differences, Async Stream Pipe pattern, cache key formula, fs-boundary discussion)
    - .planning/phases/20-benchmark-gated-validation/20-CONTEXT.md §D-11 (Async Stream Pipe + State Monitor) + §D-15 (cache key) + §Risk Anchors §"TBLite Modal 后端时延" + §Risk Anchors §"TBLite --env.task_filter 语义验证"
    - .planning/phases/20-benchmark-gated-validation/20-CONTEXT.md §Specifics (TBLite subprocess command-line + heartbeat 60s + max_hangs 3 + Risk_Score weights)
    - evolution/core/constraints.py lines 55-93 (analog subprocess.run blocking usage — explicitly NOT the pattern Phase 20 uses, but cwd/text style is reusable)
    - evolution/core/config.py lines 30-75 (EvolutionConfig field declarations + Plan 01's 4 new fields)
    - ./CLAUDE.md (naming, indentation, snake_case, no logging-framework usage — use rich console)
  </read_first>
  <behavior>
    The unit test file in Task 3 will exercise these behaviors. Required (each maps to one or more tests):
    - test_popen_args_constructed: Calling `TBLiteRunner.run(task_filter=['t1','t2'], output_dir=tmp_path)` invokes `subprocess.Popen(args, cwd=str(hermes_agent_path), text=True, bufsize=1, stdout=PIPE, stderr=PIPE)` with `args` containing `'evaluate'`, `'--env.task_filter'`, `'t1,t2'`, `'--env.data_dir_to_save_evals'`, `str(output_dir)`.
    - test_popen_args_reject_unsafe_task_names: `TBLiteRunner.run(task_filter=['ok-task', 'bad;rm -rf /'])` raises `ValueError` BEFORE Popen is called (task_filter sanitization, T-20-05 mitigation).
    - test_stream_pipe_parses_pass_fail_markers: Mock stdout yields `'[START]task1\n', '[PASS]task1\n', '[FAIL]task2\n', ''` → runner consumes all 3 markers without hanging.
    - test_heartbeat_timeout_triggers_hang: Mock subprocess yields `''` immediately (EOF before any line) AND `poll()` returns None → `queue.Empty` on every `get` → `hang_count` increments → after `max_hangs` reached, `proc.terminate()` is called and `result.status == 'hang_timeout'`.
    - test_samples_jsonl_per_task_parse: Writing a fake `<output_dir>/samples_2026.jsonl` with 3 lines `{"task_name":"a","category":"easy","passed":true}`, etc. → `result.per_task` has 3 entries with `category` mapped to lowercase tier strings.
    - test_jsonl_skip_bad_lines: One line is malformed JSON (`'not json\n'`) → `result.jsonl_skipped_lines == 1`, other lines still parsed.
    - test_infra_failure_marked_separately: A samples row `{"task_name":"x","category":"easy","passed":false,"error":"Modal timeout"}` → that row's `infra_fail` flag is True (so Plan 03 BenchmarkGate excludes it from tier denominators).
    - test_cache_key_deterministic: `compute_artifact_hash(sections_A, "hashX", 42)` returns the same 16-char hex on repeated calls; `compute_artifact_hash(sections_A, "hashY", 42)` returns a different hash.
    - test_tblite_runner_version_constant: `TBLITE_RUNNER_VERSION` is a string equal to `"1.0"` (must change when subprocess output schema or env interaction changes).
  </behavior>
  <action>
    Create `evolution/benchmarks/tblite_runner.py` using the Write tool with the structure outlined below. Total file should be ~250-300 lines.

    **Module docstring + imports** (matches Phase 18 drift_detector.py:1-21 docstring style):

    ```python
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
    ```

    **Module-level constants** (CONTEXT §Specifics + D-15 + D-11):

    ```python
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
    ```

    **TBLiteRunResult dataclass**:

    ```python
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
    ```

    **Daemon thread pump function** (PATTERNS §File 2 pattern):

    ```python
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
    ```

    **Sanitization helper** (T-20-05 mitigation):

    ```python
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
    ```

    **TBLiteRunner class** (PATTERNS §File 2 Async Stream Pipe pattern):

    ```python
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
                            f"[red]TBLite hung {result.max_hangs} × "
                            f"{self.heartbeat_seconds}s — sending SIGTERM[/red]"
                            .replace("result.", "")
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
    ```

    **Cache key helper** (D-15 — must be top-level so Plans 03/04 can import it):

    ```python
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
    ```

    Use the Write tool to create the complete file. Once written, verify import with `.venv/bin/python -c "from evolution.benchmarks.tblite_runner import TBLiteRunner, TBLiteRunResult, compute_artifact_hash, TBLITE_RUNNER_VERSION; print(TBLITE_RUNNER_VERSION)"`.

    Implements: PATTERNS §File 2 (Async Stream Pipe + State Monitor + cache key); CONTEXT §D-11 + §D-15 + §Risk Anchors §"Modal infra failures" + §T-20-05; ./CLAUDE.md (snake_case, Rich console for output, no logging framework, type hints).
  </action>
  <verify>
    <automated>.venv/bin/python -c "from evolution.benchmarks.tblite_runner import TBLiteRunner, TBLiteRunResult, compute_artifact_hash, TBLITE_RUNNER_VERSION, _validate_task_filter; assert TBLITE_RUNNER_VERSION == '1.0', f'TBLITE_RUNNER_VERSION wrong: {TBLITE_RUNNER_VERSION!r}'; print('OK imports')" && .venv/bin/python -c "from evolution.benchmarks.tblite_runner import _validate_task_filter; r = _validate_task_filter(['ok-task', 'another.task', 'task_3']); assert r == 'ok-task,another.task,task_3', f'csv join wrong: {r!r}'; print('OK csv')" && .venv/bin/python -c "from evolution.benchmarks.tblite_runner import _validate_task_filter; raised = False; 
try:
    _validate_task_filter(['ok', 'bad; rm -rf /'])
except ValueError:
    raised = True
assert raised, 'expected ValueError for shell metachar in task name'
print('OK shell-metachar rejected')" && .venv/bin/python -c "from evolution.benchmarks.tblite_runner import compute_artifact_hash; h1 = compute_artifact_hash([{'section_id':'a','text':'hello'}], 'rev1', 42); h2 = compute_artifact_hash([{'section_id':'a','text':'hello'}], 'rev1', 42); h3 = compute_artifact_hash([{'section_id':'a','text':'hello'}], 'rev2', 42); assert h1 == h2, f'determinism fail: {h1} != {h2}'; assert h1 != h3, f'rev_hash should change hash: {h1} == {h3}'; assert len(h1) == 16, f'hash len wrong: {len(h1)}'; print('OK cache key')" && grep -c 'subprocess\.Popen' evolution/benchmarks/tblite_runner.py | awk '{ if ($1 < 1) { print "FAIL: subprocess.Popen call missing"; exit 1 } else { print "OK" } }' && grep -c 'queue\.Empty' evolution/benchmarks/tblite_runner.py | awk '{ if ($1 < 1) { print "FAIL: queue.Empty handler missing"; exit 1 } else { print "OK" } }' && grep -cE 'threading\.Thread.*daemon=True' evolution/benchmarks/tblite_runner.py | awk '{ if ($1 < 2) { print "FAIL: need 2 daemon threads (stdout + stderr), found " $1; exit 1 } else { print "OK 2 daemon threads" } }' && grep -c 'subprocess\.run' evolution/benchmarks/tblite_runner.py | awk '{ if ($1 != 0) { print "FAIL: subprocess.run is BLOCKING — Phase 20 must NOT use it (use Popen)"; exit 1 } else { print "OK: no blocking subprocess.run" } }'</automated>
  </verify>
  <acceptance_criteria>
    - `from evolution.benchmarks.tblite_runner import TBLiteRunner, TBLiteRunResult, compute_artifact_hash, TBLITE_RUNNER_VERSION` succeeds.
    - `TBLITE_RUNNER_VERSION == "1.0"`.
    - `_validate_task_filter(['ok-task'])` returns `'ok-task'`; `_validate_task_filter(['bad; rm -rf /'])` raises `ValueError` (T-20-05).
    - `compute_artifact_hash` is deterministic and 16-char hex.
    - `grep -c 'subprocess\.Popen' evolution/benchmarks/tblite_runner.py` >= 1.
    - `grep -c 'subprocess\.run' evolution/benchmarks/tblite_runner.py` == 0 (must NOT use blocking call).
    - `grep -cE 'threading\.Thread.*daemon=True' evolution/benchmarks/tblite_runner.py` >= 2 (one for stdout, one for stderr).
    - `grep -c 'queue\.Empty' evolution/benchmarks/tblite_runner.py` >= 1.
    - File line count >= 180.
  </acceptance_criteria>
  <done>
    - tblite_runner.py created with all 4 public symbols (TBLiteRunner, TBLiteRunResult, compute_artifact_hash, TBLITE_RUNNER_VERSION)
    - Async Stream Pipe + State Monitor pattern correctly implemented (Popen + 2 daemon pumps + queue.get timeout + hang_count + SIGTERM)
    - samples.jsonl parser uses per-line try/except (Phase 19 D-24 mirror) and flags infra_fail rows
    - Task name sanitization rejects shell metachars BEFORE Popen
    - File imports cleanly in venv
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Create empty tests/benchmarks/__init__.py package marker</name>
  <files>tests/benchmarks/__init__.py</files>
  <read_first>
    - tests/__init__.py (existing — see what content sibling test packages use; usually empty)
    - tests/prompts/__init__.py (existing — sibling reference)
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 11
  </read_first>
  <action>
    Create `tests/benchmarks/__init__.py` as an EMPTY file (0 bytes is acceptable, but most contributors add a 1-line comment for editor compatibility). Use the Write tool with this content:

    ```python
    # tests/benchmarks/__init__.py — empty package marker for Phase 20.
    ```

    Verify with `test -f tests/benchmarks/__init__.py && python -c "import tests.benchmarks"`.
  </action>
  <verify>
    <automated>test -f tests/benchmarks/__init__.py || (echo "FAIL: file not created"; exit 1) && wc -l < tests/benchmarks/__init__.py | awk '{ if ($1 > 5) { print "FAIL: __init__.py too long ($1 lines) — should be 1-line marker"; exit 1 } else { print "OK: minimal init" } }' && .venv/bin/python -c "import tests.benchmarks; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `tests/benchmarks/__init__.py` exists.
    - File is < 5 lines (it's a package marker, not a module).
    - `python -c "import tests.benchmarks"` exits 0.
  </acceptance_criteria>
  <done>
    - tests/benchmarks/ is a valid Python package
    - pytest can discover tests under it (verified next task)
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Create tests/benchmarks/test_tblite_runner.py with 9 unit tests covering subprocess mock + samples parse + cache key</name>
  <files>tests/benchmarks/test_tblite_runner.py</files>
  <read_first>
    - tests/prompts/test_drift_detector.py (entire file — helper class _FakeSection, patch usage, helper factories, test naming conventions)
    - tests/prompts/conftest.py (see fixture patterns used by sibling test files)
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 12 (test scaffold)
    - .planning/phases/20-benchmark-gated-validation/20-CONTEXT.md §Risk Anchors (Modal infra failure handling, task_filter semantics)
    - evolution/benchmarks/tblite_runner.py (just-written file — confirm public interface)
  </read_first>
  <behavior>
    Each test must use `unittest.mock.patch("subprocess.Popen")` (or `patch.object(tblite_runner, "subprocess")`) — NO real subprocess invocation in unit tests. Mock the stream pumps by patching `_pump_stream` to populate the queue with predefined messages, OR by giving the mocked stdout/stderr an `iter(stream.readline, '')`-compatible iterable.

    The 9 required tests (all should PASS once Task 1's tblite_runner.py exists; this is NOT pure RED — Task 1 produces working code; tests verify it):

    1. test_popen_args_constructed
    2. test_popen_rejects_unsafe_task_names (T-20-05)
    3. test_stream_pipe_parses_pass_fail_markers
    4. test_heartbeat_timeout_triggers_hang
    5. test_samples_jsonl_per_task_parse
    6. test_jsonl_skip_bad_lines
    7. test_infra_failure_marked_separately
    8. test_cache_key_deterministic
    9. test_tblite_runner_version_constant
  </behavior>
  <action>
    Create `tests/benchmarks/test_tblite_runner.py` using the Write tool. Skeleton + 9 concrete tests:

    ```python
    """Unit tests for evolution/benchmarks/tblite_runner.py.

    Tests use unittest.mock to stub subprocess.Popen — NO real TBLite
    invocation. The pumps + queue mechanism is exercised through
    MagicMock streams.
    """

    import json
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    import pytest

    from evolution.core.config import EvolutionConfig


    def _make_runner(tmp_hermes_path: Path, *, heartbeat: int = 60, max_hangs: int = 3):
        """Build a TBLiteRunner with a minimal fake config."""
        config = EvolutionConfig.__new__(EvolutionConfig)
        config.hermes_agent_path = tmp_hermes_path
        config.tblite_estimated_cost_per_task_usd = 0.4
        config.benchmark_heartbeat_seconds = heartbeat
        config.benchmark_runs = 3
        from evolution.benchmarks.tblite_runner import TBLiteRunner
        return TBLiteRunner(config, heartbeat_seconds=heartbeat, max_hangs=max_hangs)


    def _mock_popen_with_streams(stdout_lines, stderr_lines, exit_code=0):
        """Build a MagicMock that mimics subprocess.Popen."""
        # readline returns one line per call; ends with '' (EOF).
        stdout_iter = iter(list(stdout_lines) + [""])
        stderr_iter = iter(list(stderr_lines) + [""])

        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.side_effect = lambda: next(stdout_iter)
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline.side_effect = lambda: next(stderr_iter)
        mock_proc.poll.return_value = exit_code  # already exited from main loop's view
        mock_proc.wait.return_value = exit_code
        mock_proc.returncode = exit_code
        return mock_proc


    class TestTBLiteRunner:
        def test_popen_args_constructed(self, tmp_path):
            """args contain evaluate, --env.task_filter <csv>, --env.data_dir_to_save_evals."""
            from evolution.benchmarks import tblite_runner as mod
            runner = _make_runner(tmp_path)
            with patch.object(mod, "subprocess") as mock_subp:
                mock_subp.Popen.return_value = _mock_popen_with_streams([], [])
                mock_subp.TimeoutExpired = Exception  # match the real symbol path
                runner.run(["task1", "task2"], tmp_path / "out")
            args_list = mock_subp.Popen.call_args.args[0]
            assert "evaluate" in args_list, f"args missing evaluate: {args_list}"
            idx = args_list.index("--env.task_filter")
            assert args_list[idx + 1] == "task1,task2", \
                f"csv wrong: {args_list[idx + 1]}"
            idx2 = args_list.index("--env.data_dir_to_save_evals")
            assert args_list[idx2 + 1] == str(tmp_path / "out")
            kw = mock_subp.Popen.call_args.kwargs
            assert kw["cwd"] == str(tmp_path), f"cwd wrong: {kw['cwd']}"
            assert kw["text"] is True
            assert kw["bufsize"] == 1

        def test_popen_rejects_unsafe_task_names(self, tmp_path):
            """T-20-05: shell metachars in task names raise ValueError BEFORE Popen."""
            from evolution.benchmarks import tblite_runner as mod
            runner = _make_runner(tmp_path)
            with patch.object(mod, "subprocess") as mock_subp:
                with pytest.raises(ValueError, match="Unsafe task name"):
                    runner.run(["ok-task", "bad; rm -rf /"], tmp_path / "out")
            assert not mock_subp.Popen.called, \
                "T-20-05 violation: Popen was called despite unsafe task name"

        def test_stream_pipe_parses_pass_fail_markers(self, tmp_path):
            """[START]/[PASS]/[FAIL] markers are consumed without hanging."""
            from evolution.benchmarks import tblite_runner as mod
            runner = _make_runner(tmp_path, heartbeat=120)  # long enough for sync test
            with patch.object(mod, "subprocess") as mock_subp:
                mock_subp.Popen.return_value = _mock_popen_with_streams(
                    [
                        "[START]task1\n",
                        "[PASS]task1\n",
                        "[FAIL]task2\n",
                    ],
                    [],
                )
                mock_subp.TimeoutExpired = Exception
                # Write a fake samples file so parser has something to read.
                out = tmp_path / "out"
                out.mkdir(parents=True, exist_ok=True)
                samples = out / "samples_test.jsonl"
                samples.write_text(
                    '{"task_name":"task1","category":"easy","passed":true}\n'
                    '{"task_name":"task2","category":"easy","passed":false}\n'
                )
                result = runner.run(["task1", "task2"], out)
            assert result.exit_code == 0
            assert result.status == "ok"
            assert len(result.per_task) == 2

        def test_heartbeat_timeout_triggers_hang(self, tmp_path):
            """No output + poll() returns None -> hang_count climbs -> SIGTERM."""
            from evolution.benchmarks import tblite_runner as mod
            runner = _make_runner(tmp_path, heartbeat=1, max_hangs=2)

            mock_proc = MagicMock()
            # Streams return '' immediately so the pump thread exits quickly,
            # leaving the queue empty.
            mock_proc.stdout = MagicMock()
            mock_proc.stdout.readline.return_value = ""
            mock_proc.stderr = MagicMock()
            mock_proc.stderr.readline.return_value = ""
            # poll() returns None until terminate() is called — simulate
            # subprocess still 'running' so hang detection fires.
            poll_calls = {"n": 0}
            def _poll():
                # Allow the main loop to reach max_hangs before reporting exit.
                if poll_calls["n"] < 5:
                    poll_calls["n"] += 1
                    return None
                return -15
            mock_proc.poll.side_effect = _poll
            mock_proc.wait.return_value = -15
            mock_proc.returncode = -15
            mock_proc.terminate = MagicMock()
            mock_proc.kill = MagicMock()

            with patch.object(mod, "subprocess") as mock_subp:
                mock_subp.Popen.return_value = mock_proc
                mock_subp.TimeoutExpired = Exception
                result = runner.run(["task1"], tmp_path / "out")
            assert mock_proc.terminate.called, "terminate not called after max_hangs"
            assert result.status == "hang_timeout", \
                f"status wrong: {result.status}"
            assert result.hang_count >= 2, \
                f"hang_count too low: {result.hang_count}"

        def test_samples_jsonl_per_task_parse(self, tmp_path):
            """samples_*.jsonl rows are loaded into per_task with category lowercased."""
            from evolution.benchmarks import tblite_runner as mod
            runner = _make_runner(tmp_path)
            out = tmp_path / "out"
            out.mkdir(parents=True, exist_ok=True)
            (out / "samples_abc.jsonl").write_text(
                '{"task_name":"a","category":"Easy","passed":true}\n'
                '{"task_name":"b","category":"HARD","passed":false}\n'
                '{"task_name":"c","category":"extreme","passed":true}\n'
            )
            with patch.object(mod, "subprocess") as mock_subp:
                mock_subp.Popen.return_value = _mock_popen_with_streams([], [])
                mock_subp.TimeoutExpired = Exception
                result = runner.run(["a", "b", "c"], out)
            assert len(result.per_task) == 3
            cats = sorted(r["category"] for r in result.per_task)
            assert cats == ["easy", "extreme", "hard"], \
                f"categories not lowercased: {cats}"

        def test_jsonl_skip_bad_lines(self, tmp_path):
            """Malformed JSON line is counted, other rows still parsed (Phase 19 D-24)."""
            from evolution.benchmarks import tblite_runner as mod
            runner = _make_runner(tmp_path)
            out = tmp_path / "out"
            out.mkdir(parents=True, exist_ok=True)
            (out / "samples_x.jsonl").write_text(
                '{"task_name":"a","category":"easy","passed":true}\n'
                'not json at all\n'
                '{"task_name":"b","category":"medium","passed":false}\n'
                '\n'  # blank line ignored
            )
            with patch.object(mod, "subprocess") as mock_subp:
                mock_subp.Popen.return_value = _mock_popen_with_streams([], [])
                mock_subp.TimeoutExpired = Exception
                result = runner.run(["a", "b"], out)
            assert result.jsonl_skipped_lines == 1, \
                f"expected 1 skipped, got {result.jsonl_skipped_lines}"
            assert len(result.per_task) == 2, \
                f"expected 2 valid rows, got {len(result.per_task)}"

        def test_infra_failure_marked_separately(self, tmp_path):
            """Rows with 'error' field are flagged infra_fail (Risk Anchor 3)."""
            from evolution.benchmarks import tblite_runner as mod
            runner = _make_runner(tmp_path)
            out = tmp_path / "out"
            out.mkdir(parents=True, exist_ok=True)
            (out / "samples_y.jsonl").write_text(
                '{"task_name":"a","category":"easy","passed":true}\n'
                '{"task_name":"b","category":"easy","passed":false,"error":"Modal timeout"}\n'
                '{"task_name":"c","category":"easy","passed":false}\n'
            )
            with patch.object(mod, "subprocess") as mock_subp:
                mock_subp.Popen.return_value = _mock_popen_with_streams([], [])
                mock_subp.TimeoutExpired = Exception
                result = runner.run(["a", "b", "c"], out)
            by_name = {r["task_name"]: r for r in result.per_task}
            assert by_name["a"]["infra_fail"] is False
            assert by_name["b"]["infra_fail"] is True, \
                "task with non-empty error must be flagged infra_fail"
            assert by_name["c"]["infra_fail"] is False, \
                "task without error must be False"

        def test_cache_key_deterministic(self):
            """compute_artifact_hash is stable for identical inputs."""
            from evolution.benchmarks.tblite_runner import compute_artifact_hash
            sections = [
                {"section_id": "memory_guidance", "text": "Use memory."},
                {"section_id": "session_search_guidance", "text": "Search hints."},
            ]
            h1 = compute_artifact_hash(sections, "rev_abc", 42)
            h2 = compute_artifact_hash(sections, "rev_abc", 42)
            h3 = compute_artifact_hash(sections, "rev_xyz", 42)
            h4 = compute_artifact_hash(sections, "rev_abc", 99)
            assert h1 == h2, f"determinism failed: {h1} != {h2}"
            assert h1 != h3, "different dataset_revision_hash must give different cache key"
            assert h1 != h4, "different seed must give different cache key"
            assert len(h1) == 16, f"length wrong: {len(h1)}"
            # All hex chars.
            int(h1, 16)

        def test_tblite_runner_version_constant(self):
            """TBLITE_RUNNER_VERSION is a string equal to '1.0' (current schema version)."""
            from evolution.benchmarks.tblite_runner import TBLITE_RUNNER_VERSION
            assert isinstance(TBLITE_RUNNER_VERSION, str), \
                f"version must be string, got {type(TBLITE_RUNNER_VERSION).__name__}"
            assert TBLITE_RUNNER_VERSION == "1.0", \
                f"version mismatch: {TBLITE_RUNNER_VERSION!r}"
    ```

    After writing, run `.venv/bin/pytest tests/benchmarks/test_tblite_runner.py -v` and confirm all 9 tests PASS. Per project convention, no logging framework, no print() in production code — but pytest is allowed to use console output.

    Implements: PATTERNS §File 12 (test scaffold) + Behavior list from above.
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/benchmarks/test_tblite_runner.py -v --tb=short 2>&1 | tail -30 && .venv/bin/pytest tests/benchmarks/test_tblite_runner.py -q 2>&1 | tail -3 | grep -E '[0-9]+ passed' || (echo "FAIL: pytest tests/benchmarks/test_tblite_runner.py did not all pass"; exit 1) && grep -c 'def test_' tests/benchmarks/test_tblite_runner.py | awk '{ if ($1 < 9) { print "FAIL: only " $1 " tests, need >= 9"; exit 1 } else { print "OK: " $1 " tests" } }' && grep -c 'patch.*subprocess' tests/benchmarks/test_tblite_runner.py | awk '{ if ($1 < 1) { print "FAIL: tests must mock subprocess"; exit 1 } else { print "OK: subprocess mocked" } }' && grep -c 'T-20-05\|test_popen_rejects_unsafe' tests/benchmarks/test_tblite_runner.py | awk '{ if ($1 < 1) { print "FAIL: T-20-05 sanitization test missing"; exit 1 } else { print "OK: sanitization test present" } }'</automated>
  </verify>
  <acceptance_criteria>
    - `pytest tests/benchmarks/test_tblite_runner.py -v` exits 0 with all 9+ tests PASSED.
    - `grep -c 'def test_' tests/benchmarks/test_tblite_runner.py` >= 9.
    - Tests mock `subprocess` via `patch.object` or `patch("subprocess.Popen")` (no real subprocess invocations).
    - `test_popen_rejects_unsafe_task_names` exists (T-20-05 regression guard).
    - `test_cache_key_deterministic` covers same-input determinism + different-input divergence.
    - `test_heartbeat_timeout_triggers_hang` calls `mock_proc.terminate` at least once.
  </acceptance_criteria>
  <done>
    - All 9 unit tests pass
    - subprocess.Popen is mocked in every test (no real subprocess)
    - T-20-05 regression guard is in place
    - tests/benchmarks/ contributes ~9 new passing tests; tests/prompts/ + tests/tools/ baseline unchanged
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| task_filter list[str] → subprocess args | UNTRUSTED in principle (eventually wired from `--benchmark-tier` CSV in Plan 06 + datasets/prompts/tblite_stratified_subset.json). Whitelist regex `_TASK_NAME_RE` rejects shell metachars BEFORE `subprocess.Popen` args list is built. |
| hermes-agent path → subprocess cwd | Local filesystem path resolved from `HERMES_AGENT_REPO` env var. Trusted at the developer-shell level. |
| os.environ.copy() → subprocess env | Inherits user's OPENROUTER_API_KEY / MODAL_TOKEN_ID. Not modified or logged by TBLiteRunner. |
| samples_*.jsonl → per_task list | UNTRUSTED file produced by external subprocess. Per-line try/except json.JSONDecodeError + bounded stderr_tail (last 20 lines) prevent malformed output from raising or OOMing the runner. |
| stderr stream → stderr_tail buffer | Capped at 1000 lines during streaming, truncated to last 20 in result. Mitigates DoS via runaway error spam. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-20-05 | I (Injection / Tampering) | task_filter -> subprocess args | mitigate | `_validate_task_filter` rejects any task name failing `^[A-Za-z0-9][A-Za-z0-9_\-./]{0,127}$` BEFORE Popen. List-form args (NOT shell=True) prevents word-splitting even if regex were bypassed. Unit test `test_popen_rejects_unsafe_task_names` is the regression guard. |
| T-20-06 | D (Denial of Service) | TBLite hang -> infinite wait | mitigate | Async Stream Pipe heartbeat: 60s without output × max_hangs=3 → SIGTERM → SIGKILL fallback (wait timeout=5). `result.status="hang_timeout"` lets downstream callers (Plan 03 BenchmarkGate) emit `TBLITE_HANG_<ts>/` and NOT proceed to write-back. |
| T-20-07 | I (Information disclosure) | stderr_tail in TBLiteRunResult | accept | Last 20 stderr lines are saved for debugging. Modal / OpenRouter HTTP errors may contain partial request bodies but no API keys (those go in headers, not bodies). Plan 03 BenchmarkGate / Plan 06 evolve_prompt_sections will pass stderr_tail through Phase 14 SECRET_PATTERNS filter before persisting to disk. |
| T-20-08 | T (Tampering) | samples_*.jsonl → per_task | mitigate | Per-line try/except json.JSONDecodeError + counted in jsonl_skipped_lines. Skip-rate warning at 5% (Phase 19 D-24 mirror). infra_fail flag distinguishes Modal/sandbox errors from prompt-quality failures so Risk_Score (Plan 03) only penalizes the latter. |
| T-20-09 | D (Denial of Service) | unbounded stderr_buf during streaming | mitigate | stderr_buf capped at 1000 lines in-memory (truncates rolling oldest), final result.stderr_tail capped at last 20. |
| T-20-10 | T (Tampering) | heartbeat_seconds = 0 or negative | mitigate | Constructor `max(1, int(hb_raw))` clamp prevents config users from disabling hang detection by setting `EVOLUTION_BENCHMARK_HEARTBEAT_SECONDS=0`. |
</threat_model>

<verification>
- `from evolution.benchmarks.tblite_runner import TBLiteRunner, TBLiteRunResult, compute_artifact_hash, TBLITE_RUNNER_VERSION` succeeds.
- `TBLITE_RUNNER_VERSION == "1.0"`.
- `grep -c 'subprocess\.Popen' evolution/benchmarks/tblite_runner.py` >= 1.
- `grep -c 'subprocess\.run' evolution/benchmarks/tblite_runner.py` == 0 (must NOT use blocking subprocess.run).
- `grep -cE 'threading\.Thread.*daemon=True' evolution/benchmarks/tblite_runner.py` >= 2.
- `grep -c 'queue\.Empty' evolution/benchmarks/tblite_runner.py` >= 1.
- `pytest tests/benchmarks/test_tblite_runner.py -v` exits 0 with all 9+ tests passing.
- `pytest tests/ --collect-only` still succeeds globally (no regression in tests/prompts/ or tests/tools/).
- `grep -c 'def test_' tests/benchmarks/test_tblite_runner.py` >= 9.
</verification>

<success_criteria>
- ROADMAP SC #1 (`--benchmark` flag triggers TBLite evaluation): subprocess wrapper now exists and is unit-testable.
- D-11 covered: Async Stream Pipe + State Monitor + heartbeat detection are implemented.
- D-15 covered: `compute_artifact_hash` + `TBLITE_RUNNER_VERSION` available for Plan 03/04 cache logic.
- Risk Anchor 3 covered: infra_fail flagging lets Plan 03 BenchmarkGate distinguish Modal failures from prompt failures.
- T-20-05 mitigated: shell-metachar task names raise `ValueError` before Popen (unit-tested).
- Phase 19 D-24 / CONCERNS §M7 covered: per-line jsonl parse + skip counter + 5% warn threshold.
- tests/benchmarks/ now contributes 9+ passing tests; full test suite remains green.
</success_criteria>

<output>
After completion, create `.planning/phases/20-benchmark-gated-validation/20-02-tblite-runner-SUMMARY.md` covering:
- Line counts: tblite_runner.py ~250-300 lines; test_tblite_runner.py ~200-250 lines.
- Grep evidence: 2 daemon threads (`threading.Thread.*daemon=True`), 1 `subprocess.Popen`, 0 `subprocess.run`, 1 `queue.Empty`.
- pytest summary line showing all tests/benchmarks/test_tblite_runner.py tests pass.
- Total project-wide test count change (should be +9).
- Confirmation that `import evolution.benchmarks.tblite_runner` works.
</output>
</content>
</invoke>

## Revision Log

- 2026-05-19 (W-7 propagation): `_validate_task_filter` continues to accept `list[str]` task NAMES; upstream callers (Plan 04 calibration, Plan 06 evolve integration) extract `name` from the new `{name, tier}` object schema in `tblite_stratified_subset.json` BEFORE passing to `TBLiteRunner.run`. No behavior change in this plan — only consumer-side adaptation in Plans 04 and 06.
