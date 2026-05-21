"""Phase 22 D-11: deploy_mode gate unit tests.

Closes CONCERNS §M6 (hermes-agent Read-Only Not Enforced) by asserting that
EVOLUTION_DEPLOY_MODE=production raises PermissionError on write-back paths
before any file I/O occurs.
"""
import pytest
from pathlib import Path

from evolution.core.config import EvolutionConfig
from evolution.tools.tool_loader import write_back_description
from evolution.prompts.prompt_loader import write_back_section


def test_default_deploy_mode_is_none():
    assert EvolutionConfig().deploy_mode is None


def test_env_var_sets_production(monkeypatch):
    monkeypatch.setenv("EVOLUTION_DEPLOY_MODE", "production")
    assert EvolutionConfig.load().deploy_mode == "production"


def test_cli_override_beats_env(monkeypatch):
    monkeypatch.setenv("EVOLUTION_DEPLOY_MODE", "production")
    assert EvolutionConfig.load(deploy_mode="dev").deploy_mode == "dev"


def test_production_blocks_write_back_description(monkeypatch, tmp_path):
    monkeypatch.setenv("EVOLUTION_DEPLOY_MODE", "production")
    with pytest.raises(PermissionError, match="read-only in production deploy_mode"):
        write_back_description(tmp_path / "any.py", None, "new desc")


def test_production_blocks_write_back_section_in_place(monkeypatch, tmp_path):
    monkeypatch.setenv("EVOLUTION_DEPLOY_MODE", "production")
    with pytest.raises(PermissionError, match="read-only in production deploy_mode"):
        write_back_section(tmp_path / "any.py", None, "new text")


def test_production_allows_write_back_section_with_dest(monkeypatch, tmp_path):
    """Phase 20 Virtual Prompt Overlay path stays open in production."""
    monkeypatch.setenv("EVOLUTION_DEPLOY_MODE", "production")
    # Construct a real source file so prompt_loader gets past the env guard
    # and reaches downstream code (which may fail on the None section — we
    # only assert the env guard did NOT fire).
    src = tmp_path / "src.py"
    src.write_text("DEFAULT_AGENT_IDENTITY = 'foo'\n")
    overlay = tmp_path / "overlay.py"
    try:
        write_back_section(src, None, "new text", dest=overlay)
    except PermissionError as e:
        pytest.fail(f"Overlay path must not be blocked in production: {e}")
    except Exception:
        # Other errors (e.g. AttributeError on None section) are
        # acceptable — the env-guard did its job by not firing.
        pass
