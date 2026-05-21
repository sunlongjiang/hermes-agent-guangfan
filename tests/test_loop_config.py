"""Phase 22 D-06 / D-08: loop_cli_config schema parsing unit tests."""
import tempfile
from pathlib import Path

import pytest

from evolution.core.config import (
    EvolutionConfig,
    LOOP_CLI_NAMES,
    LOOP_DEFAULT_MAX_COST_USD,
)


def _write_yaml(text: str) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    f.write(text)
    f.close()
    return Path(f.name)


def test_loop_default_all_six_clis_enabled():
    c = EvolutionConfig()
    assert set(c.loop_cli_config.keys()) == set(LOOP_CLI_NAMES)
    for name in LOOP_CLI_NAMES:
        assert c.loop_cli_config[name]["enabled"] is True
        assert c.loop_cli_config[name]["max_cost_usd"] == LOOP_DEFAULT_MAX_COST_USD


def test_yaml_missing_loop_section_uses_defaults(tmp_path):
    p = _write_yaml("models:\n  optimizer: openai/qwen-max\n")
    try:
        c = EvolutionConfig.load(config_path=str(p))
        for name in LOOP_CLI_NAMES:
            assert c.loop_cli_config[name]["enabled"] is True
            assert c.loop_cli_config[name]["max_cost_usd"] == 5.0
    finally:
        p.unlink()


def test_yaml_partial_cli_keeps_other_defaults():
    p = _write_yaml(
        "loop:\n  cli:\n    skill:\n      max_cost_usd: 3.0\n"
    )
    try:
        c = EvolutionConfig.load(config_path=str(p))
        assert c.loop_cli_config["skill"]["max_cost_usd"] == 3.0
        assert c.loop_cli_config["skill"]["enabled"] is True
        assert c.loop_cli_config["code"]["max_cost_usd"] == 5.0
    finally:
        p.unlink()


def test_yaml_can_disable_one_cli():
    p = _write_yaml(
        "loop:\n  cli:\n    tool_reasoning:\n      enabled: false\n"
    )
    try:
        c = EvolutionConfig.load(config_path=str(p))
        assert c.loop_cli_config["tool_reasoning"]["enabled"] is False
        assert c.loop_cli_config["skill"]["enabled"] is True
    finally:
        p.unlink()


def test_yaml_can_override_max_cost():
    p = _write_yaml(
        "loop:\n  cli:\n    code:\n      max_cost_usd: 12.5\n"
    )
    try:
        c = EvolutionConfig.load(config_path=str(p))
        assert c.loop_cli_config["code"]["max_cost_usd"] == 12.5
    finally:
        p.unlink()


def test_unknown_cli_name_warns_but_loaded(capsys):
    p = _write_yaml(
        "loop:\n  cli:\n    future_cli:\n      enabled: true\n"
    )
    try:
        c = EvolutionConfig.load(config_path=str(p))
        captured = capsys.readouterr()
        assert "future_cli" in captured.err
        assert "future_cli" in c.loop_cli_config
    finally:
        p.unlink()


def test_malformed_enabled_falls_back_with_warning(capsys):
    p = _write_yaml(
        'loop:\n  cli:\n    skill:\n      enabled: "yes"\n'
    )
    try:
        c = EvolutionConfig.load(config_path=str(p))
        captured = capsys.readouterr()
        assert "enabled" in captured.err
        assert c.loop_cli_config["skill"]["enabled"] is True
    finally:
        p.unlink()


def test_malformed_max_cost_falls_back_with_warning(capsys):
    p = _write_yaml(
        'loop:\n  cli:\n    skill:\n      max_cost_usd: "five"\n'
    )
    try:
        c = EvolutionConfig.load(config_path=str(p))
        captured = capsys.readouterr()
        assert "max_cost_usd" in captured.err
        assert c.loop_cli_config["skill"]["max_cost_usd"] == 5.0
    finally:
        p.unlink()
