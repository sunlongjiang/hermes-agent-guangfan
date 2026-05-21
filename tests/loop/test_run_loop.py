"""Phase 22 Plan 06 — unit tests for evolution.loop.run_loop.

All subprocess.run + filesystem operations are mocked. No real network,
no real git, no real gh. Target runtime: < 2s.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _fake_proc(returncode=0, stdout="", stderr=""):
    p = MagicMock(spec=subprocess.CompletedProcess)
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def test_lazy_import_does_not_load_run_loop_on_package_import():
    # Remove any prior import side effects
    for mod_name in list(sys.modules):
        if mod_name.startswith("evolution.loop"):
            del sys.modules[mod_name]
    import evolution.loop  # noqa: F401
    assert "evolution.loop.run_loop" not in sys.modules, (
        "lazy guard broken — run_loop must not load until accessed"
    )


def test_six_clis_dispatched_in_canonical_order(tmp_path, monkeypatch):
    from evolution.loop import run_loop as rl
    from evolution.core.config import LOOP_CLI_NAMES

    invoked: list[str] = []

    def fake_run(argv, **kwargs):
        for name, cmd in rl.CLI_DISPATCH.items():
            if argv[:3] == cmd:
                invoked.append(name)
                break
        return _fake_proc(returncode=0)

    monkeypatch.setattr(rl.subprocess, "run", fake_run)
    monkeypatch.setattr(rl, "_snapshot_dir_children", lambda root: set())
    monkeypatch.setattr(rl, "_snapshot_for_skill", lambda: {})
    ts = "20260601_120000"
    monkeypatch.setattr(rl, "_find_new_dir", lambda root, snap: Path(f"output/fake/{ts}"))
    monkeypatch.setattr(
        rl, "_find_new_dir_for_skill",
        lambda snap: Path(f"output/skill_default/{ts}"),
    )
    monkeypatch.setattr(rl, "_parse_cost_from_metrics", lambda p: 0.0)
    monkeypatch.setattr(rl, "_parse_holdout_from_metrics", lambda p: None)

    rl.evolve_loop(
        config_path=None, cli_filter=(), dry_run=False, no_pr=True,
        per_cli_timeout=900, loop_output_dir=str(tmp_path),
    )
    assert invoked == list(LOOP_CLI_NAMES), f"order broken: {invoked}"


def test_disabled_cli_skipped_with_status_skipped_disabled(tmp_path, monkeypatch):
    from evolution.loop import run_loop as rl
    from evolution.core.config import EvolutionConfig

    cfg = EvolutionConfig()
    cfg.loop_cli_config["code"]["enabled"] = False
    monkeypatch.setattr(rl.EvolutionConfig, "load", classmethod(lambda cls, **k: cfg))

    invoked = []

    def fake_run(argv, **kwargs):
        invoked.append(argv[:3])
        return _fake_proc(0)

    monkeypatch.setattr(rl.subprocess, "run", fake_run)
    monkeypatch.setattr(rl, "_snapshot_dir_children", lambda root: set())
    monkeypatch.setattr(rl, "_snapshot_for_skill", lambda: {})
    monkeypatch.setattr(
        rl, "_find_new_dir",
        lambda root, snap: Path("output/fake/20260601_120000"),
    )
    monkeypatch.setattr(
        rl, "_find_new_dir_for_skill",
        lambda snap: Path("output/skill/20260601_120000"),
    )
    monkeypatch.setattr(rl, "_parse_cost_from_metrics", lambda p: 0.0)
    monkeypatch.setattr(rl, "_parse_holdout_from_metrics", lambda p: None)

    summary_path = rl.evolve_loop(
        config_path=None, cli_filter=(), dry_run=False, no_pr=True,
        per_cli_timeout=900, loop_output_dir=str(tmp_path),
    )
    summary = json.loads(summary_path.read_text())
    code_record = next(r for r in summary["cli_runs"] if r["name"] == "code")
    assert code_record["status"] == "skipped_disabled"
    assert ["python", "-m", "evolution.code.evolve_code"] not in invoked


def test_cli_filter_skips_unselected(tmp_path, monkeypatch):
    from evolution.loop import run_loop as rl
    from evolution.core.config import EvolutionConfig

    cfg = EvolutionConfig()
    monkeypatch.setattr(rl.EvolutionConfig, "load", classmethod(lambda cls, **k: cfg))

    def fake_run(argv, **kwargs):
        return _fake_proc(0)

    monkeypatch.setattr(rl.subprocess, "run", fake_run)
    monkeypatch.setattr(rl, "_snapshot_dir_children", lambda root: set())
    monkeypatch.setattr(rl, "_snapshot_for_skill", lambda: {})
    monkeypatch.setattr(
        rl, "_find_new_dir",
        lambda root, snap: Path("output/x/20260601_120000"),
    )
    monkeypatch.setattr(
        rl, "_find_new_dir_for_skill",
        lambda snap: Path("output/x/20260601_120000"),
    )
    monkeypatch.setattr(rl, "_parse_cost_from_metrics", lambda p: 0.0)
    monkeypatch.setattr(rl, "_parse_holdout_from_metrics", lambda p: None)

    summary_path = rl.evolve_loop(
        config_path=None, cli_filter=("skill", "code"),
        dry_run=False, no_pr=True, per_cli_timeout=900,
        loop_output_dir=str(tmp_path),
    )
    summary = json.loads(summary_path.read_text())
    statuses = {r["name"]: r["status"] for r in summary["cli_runs"]}
    assert statuses["skill"] == "success"
    assert statuses["code"] == "success"
    assert statuses["tool_descriptions"] == "skipped_filter"
    assert statuses["prompt_sections"] == "skipped_filter"


@pytest.mark.parametrize("dir_name,expected_status,expected_gate", [
    ("20260601_120000", "success", True),
    ("FAILED_20260601_120000", "failed", False),
    ("ABORTED_20260601_120000", "failed", False),
    ("garbage_dir_name", "unknown", False),
])
def test_classify_new_dir(dir_name, expected_status, expected_gate):
    from evolution.loop.run_loop import _classify_new_dir
    status, gate = _classify_new_dir(dir_name)
    assert status == expected_status
    assert gate == expected_gate


def test_no_new_dir_classified_as_crashed(tmp_path, monkeypatch):
    from evolution.loop import run_loop as rl

    cfg = MagicMock()
    cfg.loop_cli_config = {
        n: {"enabled": True, "max_cost_usd": 5.0} for n in rl.LOOP_CLI_NAMES
    }
    cfg.deploy_mode = None
    cfg.hermes_agent_path = tmp_path
    monkeypatch.setattr(rl.EvolutionConfig, "load", classmethod(lambda cls, **k: cfg))
    monkeypatch.setattr(
        rl.subprocess, "run", lambda argv, **k: _fake_proc(returncode=42)
    )
    monkeypatch.setattr(rl, "_snapshot_dir_children", lambda root: set())
    monkeypatch.setattr(rl, "_snapshot_for_skill", lambda: {})
    monkeypatch.setattr(rl, "_find_new_dir", lambda root, snap: None)
    monkeypatch.setattr(rl, "_find_new_dir_for_skill", lambda snap: None)

    summary_path = rl.evolve_loop(
        config_path=None, cli_filter=("code",),
        dry_run=False, no_pr=True, per_cli_timeout=900,
        loop_output_dir=str(tmp_path),
    )
    summary = json.loads(summary_path.read_text())
    code_record = next(r for r in summary["cli_runs"] if r["name"] == "code")
    assert code_record["status"] == "crashed"
    assert code_record["holdout_gate_passed"] is False


def test_timeout_classified_as_timeout(tmp_path, monkeypatch):
    from evolution.loop import run_loop as rl

    cfg = MagicMock()
    cfg.loop_cli_config = {
        n: {"enabled": True, "max_cost_usd": 5.0} for n in rl.LOOP_CLI_NAMES
    }
    cfg.deploy_mode = None
    cfg.hermes_agent_path = tmp_path
    monkeypatch.setattr(rl.EvolutionConfig, "load", classmethod(lambda cls, **k: cfg))

    def raise_timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr(rl.subprocess, "run", raise_timeout)
    monkeypatch.setattr(rl, "_snapshot_dir_children", lambda root: set())
    monkeypatch.setattr(rl, "_snapshot_for_skill", lambda: {})
    monkeypatch.setattr(rl, "_find_new_dir", lambda root, snap: None)
    monkeypatch.setattr(rl, "_find_new_dir_for_skill", lambda snap: None)

    summary_path = rl.evolve_loop(
        config_path=None, cli_filter=("code",),
        dry_run=False, no_pr=True, per_cli_timeout=1,
        loop_output_dir=str(tmp_path),
    )
    summary = json.loads(summary_path.read_text())
    code_record = next(r for r in summary["cli_runs"] if r["name"] == "code")
    assert code_record["status"] == "timeout"


def test_per_cli_failure_does_not_block_subsequent(tmp_path, monkeypatch):
    """D-07: CLI 2 failing must not stop CLIs 3-6."""
    from evolution.loop import run_loop as rl
    from evolution.core.config import EvolutionConfig, LOOP_CLI_NAMES

    cfg = EvolutionConfig()
    monkeypatch.setattr(rl.EvolutionConfig, "load", classmethod(lambda cls, **k: cfg))

    call_count = {"n": 0}

    def fake_run(argv, **kwargs):
        call_count["n"] += 1
        return _fake_proc(0)

    monkeypatch.setattr(rl.subprocess, "run", fake_run)

    # tool_descriptions invocation (n==2) → return FAILED dir; others succeed
    def fake_find_new_dir(root, snap):
        if call_count["n"] == 2:
            return Path("output/tools/FAILED_20260601_120000")
        return Path(f"{root}/20260601_120000")

    monkeypatch.setattr(rl, "_snapshot_dir_children", lambda root: set())
    monkeypatch.setattr(rl, "_snapshot_for_skill", lambda: {})
    monkeypatch.setattr(rl, "_find_new_dir", fake_find_new_dir)
    monkeypatch.setattr(
        rl, "_find_new_dir_for_skill",
        lambda snap: Path("output/skill_default/20260601_120000"),
    )
    monkeypatch.setattr(rl, "_parse_cost_from_metrics", lambda p: 0.0)
    monkeypatch.setattr(rl, "_parse_holdout_from_metrics", lambda p: None)

    summary_path = rl.evolve_loop(
        config_path=None, cli_filter=(), dry_run=False, no_pr=True,
        per_cli_timeout=900, loop_output_dir=str(tmp_path),
    )
    summary = json.loads(summary_path.read_text())
    assert call_count["n"] == len(LOOP_CLI_NAMES), (
        f"D-07 broken: expected {len(LOOP_CLI_NAMES)} subprocess.run calls, "
        f"got {call_count['n']}"
    )
    assert len(summary["cli_runs"]) == len(LOOP_CLI_NAMES)


def test_run_summary_json_shape(tmp_path, monkeypatch):
    from evolution.loop import run_loop as rl
    from evolution.core.config import EvolutionConfig

    cfg = EvolutionConfig()
    monkeypatch.setattr(rl.EvolutionConfig, "load", classmethod(lambda cls, **k: cfg))
    monkeypatch.setattr(rl.subprocess, "run", lambda argv, **k: _fake_proc(0))
    monkeypatch.setattr(rl, "_snapshot_dir_children", lambda root: set())
    monkeypatch.setattr(rl, "_snapshot_for_skill", lambda: {})
    monkeypatch.setattr(
        rl, "_find_new_dir", lambda root, snap: Path(f"{root}/20260601_120000"),
    )
    monkeypatch.setattr(
        rl, "_find_new_dir_for_skill",
        lambda snap: Path("output/skill_default/20260601_120000"),
    )
    monkeypatch.setattr(rl, "_parse_cost_from_metrics", lambda p: 1.5)
    monkeypatch.setattr(rl, "_parse_holdout_from_metrics", lambda p: None)

    summary_path = rl.evolve_loop(
        config_path=None, cli_filter=(), dry_run=True, no_pr=True,
        per_cli_timeout=900, loop_output_dir=str(tmp_path),
    )
    summary = json.loads(summary_path.read_text())

    for k in (
        "loop_ts", "started_at", "finished_at", "config_snapshot",
        "deploy_mode", "cli_runs", "summary",
    ):
        assert k in summary, f"missing top-level key {k}"

    for r in summary["cli_runs"]:
        for k in (
            "name", "status", "started_at", "finished_at",
            "duration_seconds", "max_cost_cap_usd", "cost_usd",
            "output_dir", "holdout_gate_passed", "pr_url",
            "failure_reason", "stdout_tail", "stderr_tail",
        ):
            assert k in r, f"missing cli_runs[*].{k}"

    for k in (
        "total_clis", "succeeded", "failed", "skipped",
        "prs_created", "total_cost_usd",
    ):
        assert k in summary["summary"], f"missing summary.{k}"

    assert summary["summary"]["total_clis"] == 6
    # 6 CLIs × 1.5 = 9.0
    assert summary["summary"]["total_cost_usd"] == pytest.approx(9.0)


def test_deploy_mode_env_passed_to_subprocess(tmp_path, monkeypatch):
    from evolution.loop import run_loop as rl

    cfg = MagicMock()
    cfg.loop_cli_config = {
        n: {"enabled": True, "max_cost_usd": 5.0} for n in rl.LOOP_CLI_NAMES
    }
    cfg.deploy_mode = "production"
    cfg.hermes_agent_path = tmp_path
    monkeypatch.setattr(rl.EvolutionConfig, "load", classmethod(lambda cls, **k: cfg))

    captured_envs = []

    def fake_run(argv, **kwargs):
        captured_envs.append(kwargs.get("env", {}))
        return _fake_proc(0)

    monkeypatch.setattr(rl.subprocess, "run", fake_run)
    monkeypatch.setattr(rl, "_snapshot_dir_children", lambda root: set())
    monkeypatch.setattr(rl, "_snapshot_for_skill", lambda: {})
    monkeypatch.setattr(
        rl, "_find_new_dir", lambda root, snap: Path(f"{root}/20260601_120000"),
    )
    monkeypatch.setattr(
        rl, "_find_new_dir_for_skill",
        lambda snap: Path("output/skill_default/20260601_120000"),
    )
    monkeypatch.setattr(rl, "_parse_cost_from_metrics", lambda p: 0.0)
    monkeypatch.setattr(rl, "_parse_holdout_from_metrics", lambda p: None)

    rl.evolve_loop(
        config_path=None, cli_filter=("code",), dry_run=False, no_pr=True,
        per_cli_timeout=900, loop_output_dir=str(tmp_path),
    )
    assert captured_envs, "subprocess never called"
    assert captured_envs[0].get("EVOLUTION_DEPLOY_MODE") == "production"
