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
