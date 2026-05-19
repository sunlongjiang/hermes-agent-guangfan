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
    """Build a MagicMock that mimics subprocess.Popen.

    readline returns one line per call; ends with '' (EOF).
    The pump threads use iter(stream.readline, '') to consume lines.
    """
    stdout_iter = iter(list(stdout_lines) + [""])
    stderr_iter = iter(list(stderr_lines) + [""])

    mock_proc = MagicMock()
    mock_proc.stdout = MagicMock()
    mock_proc.stdout.readline.side_effect = lambda: next(stdout_iter)
    mock_proc.stdout.close = MagicMock()
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.readline.side_effect = lambda: next(stderr_iter)
    mock_proc.stderr.close = MagicMock()
    # poll() returns exit_code so the main loop eventually exits (subprocess done)
    mock_proc.poll.return_value = exit_code
    mock_proc.wait.return_value = exit_code
    mock_proc.returncode = exit_code
    return mock_proc


class TestTBLiteRunner:
    # ── Test 1: subprocess args ────────────────────────────────────────────

    def test_popen_args_constructed(self, tmp_path):
        """args contain evaluate, --env.task_filter <csv>, --env.data_dir_to_save_evals."""
        from evolution.benchmarks import tblite_runner as mod
        runner = _make_runner(tmp_path, heartbeat=2)  # short heartbeat for test speed
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

    # ── Test 2: T-20-05 sanitization ──────────────────────────────────────

    def test_popen_rejects_unsafe_task_names(self, tmp_path):
        """T-20-05: shell metachars in task names raise ValueError BEFORE Popen."""
        from evolution.benchmarks import tblite_runner as mod
        runner = _make_runner(tmp_path, heartbeat=2)  # short heartbeat for test speed
        with patch.object(mod, "subprocess") as mock_subp:
            with pytest.raises(ValueError, match="Unsafe task name"):
                runner.run(["ok-task", "bad; rm -rf /"], tmp_path / "out")
        assert not mock_subp.Popen.called, \
            "T-20-05 violation: Popen was called despite unsafe task name"

    # ── Test 3: stream pipe marker parsing ────────────────────────────────

    def test_stream_pipe_parses_pass_fail_markers(self, tmp_path):
        """[START]/[PASS]/[FAIL] markers are consumed without hanging."""
        from evolution.benchmarks import tblite_runner as mod
        runner = _make_runner(tmp_path, heartbeat=2)  # short heartbeat so test completes fast
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

    # ── Test 4: heartbeat hang detection ──────────────────────────────────

    def test_heartbeat_timeout_triggers_hang(self, tmp_path):
        """No output + poll() returns None -> hang_count climbs -> SIGTERM."""
        from evolution.benchmarks import tblite_runner as mod
        runner = _make_runner(tmp_path, heartbeat=1, max_hangs=2)

        mock_proc = MagicMock()
        # Streams return '' immediately so the pump thread exits quickly,
        # leaving the queue empty.
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = ""
        mock_proc.stdout.close = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline.return_value = ""
        mock_proc.stderr.close = MagicMock()
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

    # ── Test 5: samples.jsonl parsing ─────────────────────────────────────

    def test_samples_jsonl_per_task_parse(self, tmp_path):
        """samples_*.jsonl rows are loaded into per_task with category lowercased."""
        from evolution.benchmarks import tblite_runner as mod
        runner = _make_runner(tmp_path, heartbeat=2)  # short heartbeat so test completes fast
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

    # ── Test 6: bad line skip (Phase 19 D-24) ─────────────────────────────

    def test_jsonl_skip_bad_lines(self, tmp_path):
        """Malformed JSON line is counted, other rows still parsed (Phase 19 D-24)."""
        from evolution.benchmarks import tblite_runner as mod
        runner = _make_runner(tmp_path, heartbeat=2)  # short heartbeat so test completes fast
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

    # ── Test 7: infra_fail flagging (Risk Anchor 3) ───────────────────────

    def test_infra_failure_marked_separately(self, tmp_path):
        """Rows with 'error' field are flagged infra_fail (Risk Anchor 3)."""
        from evolution.benchmarks import tblite_runner as mod
        runner = _make_runner(tmp_path, heartbeat=2)  # short heartbeat so test completes fast
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

    # ── Test 8: cache key determinism (D-15) ──────────────────────────────

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

    def test_cache_key_missing_dict_keys_raises_typeerror(self):
        """CR-04 regression: dict items missing 'section_id' or 'text'
        must raise TypeError consistent with the else branch, not let
        KeyError leak from bare subscription.
        """
        from evolution.benchmarks.tblite_runner import compute_artifact_hash
        with pytest.raises(TypeError, match="missing required keys"):
            compute_artifact_hash(
                [{"id": "memory_guidance", "text": "x"}],  # wrong key
                "rev_abc", 42,
            )
        with pytest.raises(TypeError, match="missing required keys"):
            compute_artifact_hash(
                [{"section_id": "memory_guidance", "body": "x"}],  # wrong key
                "rev_abc", 42,
            )
        with pytest.raises(TypeError, match="missing required keys"):
            compute_artifact_hash(
                [{"section_id": "memory_guidance"}],  # missing text
                "rev_abc", 42,
            )

    # ── Test 9: TBLITE_RUNNER_VERSION constant ─────────────────────────────

    def test_tblite_runner_version_constant(self):
        """TBLITE_RUNNER_VERSION is a string equal to '1.0' (current schema version)."""
        from evolution.benchmarks.tblite_runner import TBLITE_RUNNER_VERSION
        assert isinstance(TBLITE_RUNNER_VERSION, str), \
            f"version must be string, got {type(TBLITE_RUNNER_VERSION).__name__}"
        assert TBLITE_RUNNER_VERSION == "1.0", \
            f"version mismatch: {TBLITE_RUNNER_VERSION!r}"
