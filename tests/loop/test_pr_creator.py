"""Tests for evolution.loop.pr_creator — Plan 22-04 TDD RED phase.

Tests cover:
- Contract: create_pr() returns dict with correct keys
- Contract: function never raises — errors → result dict
- Branch naming: D-05 pattern evolution/auto-loop/<ts>/<artifact-kind>
- Title: "auto-loop: <artifact-kind> evolved at <loop_ts>"
- PR labels: auto-loop + requires-human-review
- CLI mapping: CLI_TO_ARTIFACT_KIND covers all 6 CLIs
- Defense-in-depth: _redact replaces secrets
- skipped_no_gh when gh CLI absent
- skipped_no_changes when diff --cached returns 0
- error when hermes_repo dirty
- error when hermes_repo does not exist
- Body assembly: NOTICE.md used when present
- Body assembly: fallback template with metrics.json
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ── Import under test ────────────────────────────────────────────────────────

from evolution.loop.pr_creator import (
    CLI_TO_ARTIFACT_KIND,
    PR_LABELS,
    STAGING_BASE,
    create_pr,
    _build_branch,
    _build_title,
    _build_body,
    _redact,
    _copy_artifacts_into_staging,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_hermes_repo(tmp_path: Path) -> Path:
    """Create a minimal fake hermes-agent repo dir."""
    repo = tmp_path / "hermes-agent"
    repo.mkdir()
    (repo / ".git").mkdir()  # make it look like a git repo
    return repo


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    """Create a fake output dir with some evolved files."""
    out = tmp_path / "output" / "tools" / "20260601_030542"
    out.mkdir(parents=True)
    (out / "evolved_tool_descriptions.json").write_text(
        '{"description": "evolved"}', encoding="utf-8"
    )
    (out / "metrics.json").write_text(
        json.dumps({"holdout_gate_passed": True, "score": 0.87}), encoding="utf-8"
    )
    return out


# ── Constants contract ────────────────────────────────────────────────────────


def test_cli_to_artifact_kind_covers_all_six():
    """CLI_TO_ARTIFACT_KIND must cover all 6 CLIs (D-06)."""
    expected = {
        "skill",
        "tool_descriptions",
        "tool_params",
        "tool_reasoning",
        "prompt_sections",
        "code",
    }
    assert set(CLI_TO_ARTIFACT_KIND.keys()) == expected


def test_cli_to_artifact_kind_values():
    """Dash-cased artifact-kind values per D-05."""
    assert CLI_TO_ARTIFACT_KIND["tool_descriptions"] == "tool-descriptions"
    assert CLI_TO_ARTIFACT_KIND["tool_params"] == "tool-params"
    assert CLI_TO_ARTIFACT_KIND["tool_reasoning"] == "tool-reasoning"
    assert CLI_TO_ARTIFACT_KIND["prompt_sections"] == "prompt-sections"
    assert CLI_TO_ARTIFACT_KIND["skill"] == "skill"
    assert CLI_TO_ARTIFACT_KIND["code"] == "code"


def test_pr_labels_tuple():
    """PR_LABELS must be exactly ('auto-loop', 'requires-human-review')."""
    assert PR_LABELS == ("auto-loop", "requires-human-review")


def test_staging_base_constant():
    """STAGING_BASE must be 'evolution-loop'."""
    assert STAGING_BASE == "evolution-loop"


# ── _build_branch ─────────────────────────────────────────────────────────────


def test_build_branch_d05_pattern():
    """D-05: branch = evolution/auto-loop/<loop_ts>/<artifact-kind>."""
    assert (
        _build_branch("20260601_030000", "tool-descriptions")
        == "evolution/auto-loop/20260601_030000/tool-descriptions"
    )


def test_build_branch_skill():
    assert _build_branch("20260601_030000", "skill") == "evolution/auto-loop/20260601_030000/skill"


def test_build_branch_sanitizes_ts():
    """Non-numeric characters in ts are stripped to prevent shell injection."""
    branch = _build_branch("2026abc01_03", "skill")
    assert "abc" not in branch
    assert "evolution/auto-loop/" in branch


def test_build_branch_sanitizes_kind():
    """Non-alphanumeric-or-dash chars in kind are stripped."""
    branch = _build_branch("20260101_000000", "tool;rm -rf /")
    assert "rm" not in branch
    assert "evolution/auto-loop/" in branch


# ── _build_title ──────────────────────────────────────────────────────────────


def test_build_title_pattern():
    """Title = 'auto-loop: <artifact-kind> evolved at <loop_ts>'."""
    assert (
        _build_title("prompt-sections", "20260601_030000")
        == "auto-loop: prompt-sections evolved at 20260601_030000"
    )


def test_build_title_skill():
    assert _build_title("skill", "20260601_030000") == "auto-loop: skill evolved at 20260601_030000"


# ── _redact ───────────────────────────────────────────────────────────────────


def test_redact_clean_text():
    """Clean text passes through unchanged."""
    assert _redact("hello world") == "hello world"


def test_redact_secret_text():
    """Text containing a secret pattern is replaced with [REDACTED]."""
    # Use a known SECRET_PATTERNS prefix
    assert _redact("sk-ant-api01-SECRETKEY123456789") == "[REDACTED]"


def test_redact_empty():
    assert _redact("") == ""


# ── _build_body ───────────────────────────────────────────────────────────────


def test_build_body_uses_notice_md(tmp_output_dir: Path):
    """When NOTICE.md is present, body is taken from it."""
    notice_content = "# NOTICE\n\nCustom content UNREVIEWED"
    (tmp_output_dir / "NOTICE.md").write_text(notice_content, encoding="utf-8")
    body = _build_body("code", "code", "20260601_030542", tmp_output_dir)
    assert body == notice_content


def test_build_body_fallback_template(tmp_output_dir: Path):
    """Without NOTICE.md, body uses fallback template with UNREVIEWED marker."""
    body = _build_body("tool_descriptions", "tool-descriptions", "20260601_030542", tmp_output_dir)
    assert "UNREVIEWED" in body
    assert "tool-descriptions" in body
    assert "20260601_030542" in body
    assert "evolve_tool_descriptions" in body


def test_build_body_includes_metrics(tmp_output_dir: Path):
    """Fallback body includes metrics.json content."""
    body = _build_body("skill", "skill", "20260601_030542", tmp_output_dir)
    assert "holdout_gate_passed" in body


def test_build_body_no_metrics(tmp_path: Path):
    """When metrics.json is absent, body says (no metrics.json)."""
    out = tmp_path / "empty_output"
    out.mkdir()
    body = _build_body("skill", "skill", "20260601_030542", out)
    assert "no metrics.json" in body


# ── _copy_artifacts_into_staging ──────────────────────────────────────────────


def test_copy_artifacts_creates_staging_dir(tmp_output_dir: Path, tmp_hermes_repo: Path):
    """Staging dir evolution-loop/<kind>/<ts>/ is created."""
    staging = _copy_artifacts_into_staging(
        tmp_output_dir, tmp_hermes_repo, "tool-descriptions", "20260601_030542"
    )
    assert staging.exists()
    assert staging == tmp_hermes_repo / "evolution-loop" / "tool-descriptions" / "20260601_030542"


def test_copy_artifacts_copies_files(tmp_output_dir: Path, tmp_hermes_repo: Path):
    """Files from output_dir are copied into staging."""
    _copy_artifacts_into_staging(
        tmp_output_dir, tmp_hermes_repo, "tool-descriptions", "20260601_030542"
    )
    staged = tmp_hermes_repo / "evolution-loop" / "tool-descriptions" / "20260601_030542"
    assert (staged / "evolved_tool_descriptions.json").exists()
    assert (staged / "metrics.json").exists()


# ── create_pr() return contract ───────────────────────────────────────────────


def test_create_pr_returns_dict_with_required_keys(tmp_output_dir: Path, tmp_hermes_repo: Path):
    """create_pr() always returns dict with status, pr_url, reason, branch."""
    with patch("shutil.which", return_value=None):
        result = create_pr(
            cli_name="skill",
            output_dir=tmp_output_dir,
            loop_ts="20260101_000000",
            hermes_repo=tmp_hermes_repo,
        )
    assert isinstance(result, dict)
    assert "status" in result
    assert "pr_url" in result
    assert "reason" in result
    assert "branch" in result


def test_create_pr_branch_in_result(tmp_output_dir: Path, tmp_hermes_repo: Path):
    """branch key always set even on early exit."""
    with patch("shutil.which", return_value=None):
        result = create_pr(
            cli_name="tool_descriptions",
            output_dir=tmp_output_dir,
            loop_ts="20260601_030000",
            hermes_repo=tmp_hermes_repo,
        )
    assert result["branch"] == "evolution/auto-loop/20260601_030000/tool-descriptions"


def test_create_pr_never_raises(tmp_output_dir: Path, tmp_path: Path):
    """create_pr() must not raise even for totally broken inputs."""
    try:
        result = create_pr(
            cli_name="skill",
            output_dir=tmp_output_dir,
            loop_ts="20260101_000000",
            hermes_repo=tmp_path / "nonexistent_xyz",
        )
    except Exception as exc:
        pytest.fail(f"create_pr() raised {type(exc).__name__}: {exc}")
    assert isinstance(result, dict)
    assert result["status"] in {"error", "skipped_no_gh"}


# ── skipped_no_gh ─────────────────────────────────────────────────────────────


def test_create_pr_skipped_no_gh_when_gh_not_on_path(
    tmp_output_dir: Path, tmp_hermes_repo: Path
):
    """Returns status='skipped_no_gh' when gh CLI is not on PATH."""
    with patch("shutil.which", return_value=None):
        result = create_pr(
            cli_name="skill",
            output_dir=tmp_output_dir,
            loop_ts="20260601_030000",
            hermes_repo=tmp_hermes_repo,
        )
    assert result["status"] == "skipped_no_gh"
    assert "gh" in result["reason"].lower()


# ── error when hermes_repo does not exist ─────────────────────────────────────


def test_create_pr_error_when_hermes_repo_missing(tmp_output_dir: Path, tmp_path: Path):
    """Returns status='error' when hermes_repo path does not exist."""
    missing = tmp_path / "no_such_repo"
    with patch("shutil.which", return_value="/usr/bin/gh"):
        result = create_pr(
            cli_name="skill",
            output_dir=tmp_output_dir,
            loop_ts="20260601_030000",
            hermes_repo=missing,
        )
    assert result["status"] == "error"
    assert result["reason"] is not None


# ── error when hermes_repo is dirty ──────────────────────────────────────────


def test_create_pr_error_when_repo_dirty(tmp_output_dir: Path, tmp_hermes_repo: Path):
    """Returns status='error' when git status shows uncommitted changes."""
    def fake_run(cmd, **kwargs):
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.returncode = 0
        if "status" in cmd:
            proc.stdout = "M  some_file.py\n"  # dirty
            proc.stderr = ""
        return proc

    with patch("shutil.which", return_value="/usr/bin/gh"):
        with patch("evolution.loop.pr_creator._run", side_effect=fake_run):
            result = create_pr(
                cli_name="skill",
                output_dir=tmp_output_dir,
                loop_ts="20260601_030000",
                hermes_repo=tmp_hermes_repo,
            )
    assert result["status"] == "error"
    assert "uncommitted" in result["reason"].lower()


# ── skipped_no_changes ────────────────────────────────────────────────────────


def test_create_pr_skipped_no_changes(tmp_output_dir: Path, tmp_hermes_repo: Path):
    """Returns status='skipped_no_changes' when diff --cached is clean after copy."""
    call_log = []

    def fake_run(cmd, **kwargs):
        proc = MagicMock(spec=subprocess.CompletedProcess)
        call_log.append(cmd)
        proc.stderr = ""
        proc.stdout = ""
        if "status" in cmd and "--porcelain" in cmd:
            proc.returncode = 0
            proc.stdout = ""  # clean
        elif "config" in cmd and "remote.origin.url" in cmd:
            proc.returncode = 0
            proc.stdout = "https://github.com/owner/hermes-agent.git"
        elif "repo" in cmd and "view" in cmd:
            proc.returncode = 0
            proc.stdout = "owner/hermes-agent"
        elif "checkout" in cmd:
            proc.returncode = 0
        elif "add" in cmd:
            proc.returncode = 0
        elif "diff" in cmd and "--cached" in cmd:
            proc.returncode = 0  # no diff = skipped_no_changes
        else:
            proc.returncode = 0
        return proc

    with patch("shutil.which", return_value="/usr/bin/gh"):
        with patch("evolution.loop.pr_creator._run", side_effect=fake_run):
            result = create_pr(
                cli_name="skill",
                output_dir=tmp_output_dir,
                loop_ts="20260601_030000",
                hermes_repo=tmp_hermes_repo,
            )
    assert result["status"] == "skipped_no_changes"


# ── successful PR creation ────────────────────────────────────────────────────


def test_create_pr_success_returns_pr_url(tmp_output_dir: Path, tmp_hermes_repo: Path):
    """Returns status='created' with pr_url when gh pr create succeeds."""
    def fake_run(cmd, **kwargs):
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.stderr = ""
        proc.stdout = ""
        if "status" in cmd and "--porcelain" in cmd:
            proc.returncode = 0
            proc.stdout = ""
        elif "repo" in cmd and "view" in cmd:
            proc.returncode = 0
            proc.stdout = "owner/hermes-agent"
        elif "checkout" in cmd:
            proc.returncode = 0
        elif "add" in cmd:
            proc.returncode = 0
        elif "diff" in cmd and "--cached" in cmd:
            proc.returncode = 1  # changes exist
        elif "commit" in cmd:
            proc.returncode = 0
        elif "push" in cmd:
            proc.returncode = 0
        elif "pr" in cmd and "create" in cmd:
            proc.returncode = 0
            proc.stdout = "https://github.com/owner/hermes-agent/pull/42\n"
        else:
            proc.returncode = 0
        return proc

    with patch("shutil.which", return_value="/usr/bin/gh"):
        with patch("evolution.loop.pr_creator._run", side_effect=fake_run):
            result = create_pr(
                cli_name="tool_descriptions",
                output_dir=tmp_output_dir,
                loop_ts="20260601_030000",
                hermes_repo=tmp_hermes_repo,
            )
    assert result["status"] == "created"
    assert result["pr_url"] == "https://github.com/owner/hermes-agent/pull/42"
    assert result["reason"] is None


def test_create_pr_success_includes_both_labels(tmp_output_dir: Path, tmp_hermes_repo: Path):
    """gh pr create call must include both --label auto-loop and --label requires-human-review."""
    captured_cmds = []

    def fake_run(cmd, **kwargs):
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.stderr = ""
        proc.stdout = ""
        captured_cmds.append(cmd)
        if "status" in cmd and "--porcelain" in cmd:
            proc.returncode = 0
            proc.stdout = ""
        elif "repo" in cmd and "view" in cmd:
            proc.returncode = 0
            proc.stdout = "owner/hermes-agent"
        elif "checkout" in cmd:
            proc.returncode = 0
        elif "add" in cmd:
            proc.returncode = 0
        elif "diff" in cmd and "--cached" in cmd:
            proc.returncode = 1
        elif "commit" in cmd:
            proc.returncode = 0
        elif "push" in cmd:
            proc.returncode = 0
        elif "pr" in cmd and "create" in cmd:
            proc.returncode = 0
            proc.stdout = "https://github.com/owner/hermes-agent/pull/99\n"
        else:
            proc.returncode = 0
        return proc

    with patch("shutil.which", return_value="/usr/bin/gh"):
        with patch("evolution.loop.pr_creator._run", side_effect=fake_run):
            create_pr(
                cli_name="skill",
                output_dir=tmp_output_dir,
                loop_ts="20260601_030000",
                hermes_repo=tmp_hermes_repo,
            )

    # Find the gh pr create command
    pr_cmd = next((c for c in captured_cmds if "gh" in c and "pr" in c and "create" in c), None)
    assert pr_cmd is not None, "gh pr create was never called"
    assert "--label" in pr_cmd
    assert "auto-loop" in pr_cmd
    assert "requires-human-review" in pr_cmd


def test_create_pr_success_has_correct_branch_in_cmd(tmp_output_dir: Path, tmp_hermes_repo: Path):
    """gh pr create --head must match D-05 branch naming."""
    captured_cmds = []

    def fake_run(cmd, **kwargs):
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.stderr = ""
        proc.stdout = ""
        captured_cmds.append(cmd)
        if "status" in cmd and "--porcelain" in cmd:
            proc.returncode = 0
            proc.stdout = ""
        elif "repo" in cmd and "view" in cmd:
            proc.returncode = 0
            proc.stdout = "owner/hermes-agent"
        elif "checkout" in cmd:
            proc.returncode = 0
        elif "add" in cmd:
            proc.returncode = 0
        elif "diff" in cmd and "--cached" in cmd:
            proc.returncode = 1
        elif "commit" in cmd:
            proc.returncode = 0
        elif "push" in cmd:
            proc.returncode = 0
        elif "pr" in cmd and "create" in cmd:
            proc.returncode = 0
            proc.stdout = "https://github.com/owner/hermes-agent/pull/1\n"
        else:
            proc.returncode = 0
        return proc

    with patch("shutil.which", return_value="/usr/bin/gh"):
        with patch("evolution.loop.pr_creator._run", side_effect=fake_run):
            create_pr(
                cli_name="prompt_sections",
                output_dir=tmp_output_dir,
                loop_ts="20260601_030000",
                hermes_repo=tmp_hermes_repo,
            )

    pr_cmd = next((c for c in captured_cmds if "gh" in c and "pr" in c and "create" in c), None)
    assert pr_cmd is not None
    head_idx = pr_cmd.index("--head")
    branch_val = pr_cmd[head_idx + 1]
    assert branch_val == "evolution/auto-loop/20260601_030000/prompt-sections"


# ── git push failure ──────────────────────────────────────────────────────────


def test_create_pr_error_on_push_failure(tmp_output_dir: Path, tmp_hermes_repo: Path):
    """Returns status='error' when git push fails."""
    def fake_run(cmd, **kwargs):
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.stderr = ""
        proc.stdout = ""
        if "status" in cmd and "--porcelain" in cmd:
            proc.returncode = 0
            proc.stdout = ""
        elif "repo" in cmd and "view" in cmd:
            proc.returncode = 0
            proc.stdout = "owner/hermes-agent"
        elif "checkout" in cmd:
            proc.returncode = 0
        elif "add" in cmd:
            proc.returncode = 0
        elif "diff" in cmd and "--cached" in cmd:
            proc.returncode = 1
        elif "commit" in cmd:
            proc.returncode = 0
        elif "push" in cmd:
            proc.returncode = 1  # push fails
            proc.stderr = "remote: Permission denied"
        else:
            proc.returncode = 0
        return proc

    with patch("shutil.which", return_value="/usr/bin/gh"):
        with patch("evolution.loop.pr_creator._run", side_effect=fake_run):
            result = create_pr(
                cli_name="skill",
                output_dir=tmp_output_dir,
                loop_ts="20260601_030000",
                hermes_repo=tmp_hermes_repo,
            )
    assert result["status"] == "error"
    assert "push" in result["reason"].lower()


# ── gh pr create failure ──────────────────────────────────────────────────────


def test_create_pr_error_on_gh_pr_create_failure(tmp_output_dir: Path, tmp_hermes_repo: Path):
    """Returns status='error' when gh pr create fails."""
    def fake_run(cmd, **kwargs):
        proc = MagicMock(spec=subprocess.CompletedProcess)
        proc.stderr = ""
        proc.stdout = ""
        if "status" in cmd and "--porcelain" in cmd:
            proc.returncode = 0
            proc.stdout = ""
        elif "repo" in cmd and "view" in cmd:
            proc.returncode = 0
            proc.stdout = "owner/hermes-agent"
        elif "checkout" in cmd:
            proc.returncode = 0
        elif "add" in cmd:
            proc.returncode = 0
        elif "diff" in cmd and "--cached" in cmd:
            proc.returncode = 1
        elif "commit" in cmd:
            proc.returncode = 0
        elif "push" in cmd:
            proc.returncode = 0
        elif "pr" in cmd and "create" in cmd:
            proc.returncode = 1
            proc.stderr = "GraphQL: repository not found"
        else:
            proc.returncode = 0
        return proc

    with patch("shutil.which", return_value="/usr/bin/gh"):
        with patch("evolution.loop.pr_creator._run", side_effect=fake_run):
            result = create_pr(
                cli_name="skill",
                output_dir=tmp_output_dir,
                loop_ts="20260601_030000",
                hermes_repo=tmp_hermes_repo,
            )
    assert result["status"] == "error"
    assert "gh pr create" in result["reason"].lower()


# ── D-04: no HTTP libs ────────────────────────────────────────────────────────


def test_no_http_lib_imports():
    """D-04: pr_creator must not import requests, httpx, or PyGithub."""
    import ast
    import importlib.util

    spec = importlib.util.find_spec("evolution.loop.pr_creator")
    assert spec is not None
    src = Path(spec.origin).read_text(encoding="utf-8")
    tree = ast.parse(src)

    forbidden = {"requests", "httpx", "github", "PyGithub"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in getattr(node, "names", [])]
            mod = getattr(node, "module", "") or ""
            for name in names + [mod]:
                for bad in forbidden:
                    assert bad.lower() not in name.lower(), (
                        f"Forbidden import '{name}' found (D-04)"
                    )


# ── Plan 06 supplementary tests (gh-slug failure + secret redaction) ────────


def test_create_pr_returns_error_when_repo_slug_undeterminable(monkeypatch, tmp_hermes_repo):
    """If both `gh repo view` and `git config --get remote.origin.url` fail,
    create_pr cannot derive owner/repo and must return error (not raise)."""
    import subprocess as _sp

    monkeypatch.setattr(
        "evolution.loop.pr_creator.shutil.which",
        lambda _name: "/usr/bin/gh",
    )

    def fake_run(argv, **kwargs):
        p = MagicMock(spec=_sp.CompletedProcess)
        if argv[:2] == ["git", "status"]:
            p.returncode = 0
            p.stdout = ""
            p.stderr = ""
        elif argv[:2] == ["gh", "repo"]:
            p.returncode = 1
            p.stdout = ""
            p.stderr = "not authenticated"
        elif argv[:3] == ["git", "config", "--get"]:
            p.returncode = 1
            p.stdout = ""
            p.stderr = "no remote"
        else:
            p.returncode = 0
            p.stdout = ""
            p.stderr = ""
        return p

    monkeypatch.setattr("evolution.loop.pr_creator.subprocess.run", fake_run)

    result = create_pr(
        cli_name="skill", output_dir=tmp_hermes_repo,
        loop_ts="20260601_030000", hermes_repo=tmp_hermes_repo,
    )
    assert result["status"] == "error"
    assert "owner/repo" in (result["reason"] or "")


def test_secret_redaction_applied_to_stderr_tails(monkeypatch, tmp_hermes_repo):
    """Defense-in-depth: if subprocess stderr contains a secret pattern, the
    redaction layer replaces the offending tail with [REDACTED] before it
    lands in the result dict (where it would otherwise forward to
    run_summary.json via run_loop)."""
    import subprocess as _sp

    monkeypatch.setattr(
        "evolution.loop.pr_creator.shutil.which",
        lambda _name: "/usr/bin/gh",
    )
    # Force _contains_secret to flag anything containing "sk-"
    monkeypatch.setattr(
        "evolution.loop.pr_creator._contains_secret",
        lambda t: bool(t and "sk-" in t),
    )

    def fake_run(argv, **kwargs):
        p = MagicMock(spec=_sp.CompletedProcess)
        if argv[:2] == ["git", "status"]:
            p.returncode = 1
            p.stdout = ""
            p.stderr = "error: sk-abc123secret leaked here"
        else:
            p.returncode = 0
            p.stdout = ""
            p.stderr = ""
        return p

    monkeypatch.setattr("evolution.loop.pr_creator.subprocess.run", fake_run)

    result = create_pr(
        cli_name="skill", output_dir=tmp_hermes_repo,
        loop_ts="20260601_030000", hermes_repo=tmp_hermes_repo,
    )
    assert result["status"] == "error"
    assert "[REDACTED]" in (result["reason"] or "")
    assert "sk-abc123secret" not in (result["reason"] or "")
