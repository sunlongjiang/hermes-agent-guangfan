"""Tests for EvolutionConfig — env-var expansion, precedence chain, literal-key warning."""

import os
import pytest

from evolution.core.config import EvolutionConfig, _expand_env, _LITERAL_KEY_RE


# ── _expand_env ─────────────────────────────────────────────────────────────


class TestExpandEnv:
    """Verify env-var reference expansion applied to YAML string values."""

    def test_expands_braced_var(self, monkeypatch):
        monkeypatch.setenv("EVOLVE_TEST_VAR", "expanded-value")
        assert _expand_env("${EVOLVE_TEST_VAR}") == "expanded-value"

    def test_expands_unbraced_var(self, monkeypatch):
        monkeypatch.setenv("EVOLVE_TEST_VAR", "unbraced-value")
        assert _expand_env("$EVOLVE_TEST_VAR") == "unbraced-value"

    def test_unset_var_expands_empty(self, monkeypatch):
        monkeypatch.delenv("EVOLVE_NO_SUCH_VAR", raising=False)
        # os.path.expandvars leaves unset vars literally — matches OS behavior
        result = _expand_env("${EVOLVE_NO_SUCH_VAR}")
        # On POSIX, expandvars returns the literal reference when unset
        assert result in ("", "${EVOLVE_NO_SUCH_VAR}")

    def test_passes_through_non_strings(self):
        assert _expand_env(42) == 42
        assert _expand_env(None) is None
        assert _expand_env(["a"]) == ["a"]

    def test_string_without_refs_unchanged(self):
        assert _expand_env("plain text") == "plain text"


# ── _LITERAL_KEY_RE ─────────────────────────────────────────────────────────


class TestLiteralKeyRegex:
    """The regex used to warn when evolution.yaml holds a literal key."""

    def test_matches_openai_style(self):
        assert _LITERAL_KEY_RE.match("sk-abc123def456")

    def test_matches_github_pat(self):
        assert _LITERAL_KEY_RE.match("ghp_" + "a" * 36)

    def test_matches_aws_access_key(self):
        assert _LITERAL_KEY_RE.match("AKIA" + "A" * 16)

    def test_matches_slack_bot_token(self):
        assert _LITERAL_KEY_RE.match("xoxb-abc-def")

    def test_rejects_env_reference(self):
        # A ${VAR} reference is not a literal key
        assert not _LITERAL_KEY_RE.match("${DASHSCOPE_KEY}")

    def test_rejects_plain_text(self):
        assert not _LITERAL_KEY_RE.match("not-a-key")


# ── EvolutionConfig.load() — env-var reference expansion in YAML ────────────


class TestLoadEnvReferences:
    """Verify that ${VAR} references in evolution.yaml are expanded at load time."""

    def test_api_key_env_reference_expands(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TEST_KEY_VAR", "sk-from-env")
        monkeypatch.setenv("EVOLVE_SUPPRESS_KEY_WARN", "1")
        (tmp_path / "evolution.yaml").write_text(
            'api_key: "${TEST_KEY_VAR}"\n'
        )
        cfg = EvolutionConfig.load()
        assert cfg.api_key == "sk-from-env"

    def test_api_base_env_reference_expands(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TEST_BASE_VAR", "https://example.test/v1")
        (tmp_path / "evolution.yaml").write_text(
            'api_base: "${TEST_BASE_VAR}"\n'
        )
        cfg = EvolutionConfig.load()
        assert cfg.api_base == "https://example.test/v1"

    def test_model_env_reference_expands(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TEST_MODEL_VAR", "openai/some-model")
        (tmp_path / "evolution.yaml").write_text(
            "models:\n"
            '  optimizer: "${TEST_MODEL_VAR}"\n'
            '  eval: "${TEST_MODEL_VAR}"\n'
            '  judge: "${TEST_MODEL_VAR}"\n'
        )
        cfg = EvolutionConfig.load()
        assert cfg.optimizer_model == "openai/some-model"
        assert cfg.eval_model == "openai/some-model"
        assert cfg.judge_model == "openai/some-model"

    def test_literal_key_in_yaml_still_loads(self, tmp_path, monkeypatch, capsys):
        """Literal keys still work (back-compat) but emit a stderr warning."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("EVOLVE_SUPPRESS_KEY_WARN", raising=False)
        (tmp_path / "evolution.yaml").write_text(
            'api_key: "sk-abcdef1234567890abcd"\n'
        )
        cfg = EvolutionConfig.load()
        assert cfg.api_key == "sk-abcdef1234567890abcd"
        captured = capsys.readouterr()
        assert "literal API key" in captured.err

    def test_env_reference_suppresses_warning(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("TEST_KEY_VAR", "sk-from-env-abcdef")
        monkeypatch.delenv("EVOLVE_SUPPRESS_KEY_WARN", raising=False)
        (tmp_path / "evolution.yaml").write_text(
            'api_key: "${TEST_KEY_VAR}"\n'
        )
        EvolutionConfig.load()
        captured = capsys.readouterr()
        assert "literal API key" not in captured.err

    def test_suppress_flag_hides_warning(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EVOLVE_SUPPRESS_KEY_WARN", "1")
        (tmp_path / "evolution.yaml").write_text(
            'api_key: "sk-abcdef1234567890abcd"\n'
        )
        EvolutionConfig.load()
        captured = capsys.readouterr()
        assert "literal API key" not in captured.err


# ── Precedence chain (yaml < env < CLI) ─────────────────────────────────────


class TestLoadPrecedence:
    """CLI overrides > env vars > evolution.yaml > dataclass defaults."""

    def test_env_beats_yaml(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EVOLUTION_API_BASE", "https://env.wins/v1")
        monkeypatch.setenv("EVOLVE_SUPPRESS_KEY_WARN", "1")
        (tmp_path / "evolution.yaml").write_text(
            'api_base: "https://yaml.loses/v1"\n'
        )
        cfg = EvolutionConfig.load()
        assert cfg.api_base == "https://env.wins/v1"

    def test_cli_beats_env(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EVOLUTION_API_BASE", "https://env.loses/v1")
        cfg = EvolutionConfig.load(api_base="https://cli.wins/v1")
        assert cfg.api_base == "https://cli.wins/v1"

    def test_model_cli_flag_sets_all_three(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = EvolutionConfig.load(model="test/model")
        assert cfg.optimizer_model == "test/model"
        assert cfg.eval_model == "test/model"
        assert cfg.judge_model == "test/model"

    def test_evolution_model_env_sets_all_three(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EVOLUTION_MODEL", "env/model")
        cfg = EvolutionConfig.load()
        assert cfg.optimizer_model == "env/model"
        assert cfg.eval_model == "env/model"
        assert cfg.judge_model == "env/model"


# ── get_lm_kwargs ───────────────────────────────────────────────────────────


class TestGetLmKwargs:
    """Values threaded into every dspy.LM(...) call site via **kwargs."""

    def test_omits_unset_fields(self):
        cfg = EvolutionConfig()
        assert cfg.get_lm_kwargs() == {}

    def test_includes_api_base_and_key(self):
        cfg = EvolutionConfig(api_base="https://x/v1", api_key="sk-x")
        kwargs = cfg.get_lm_kwargs()
        assert kwargs == {"api_base": "https://x/v1", "api_key": "sk-x"}


# ── skill_fitness_metric signature check ────────────────────────────────────


def test_skill_fitness_metric_is_5_param():
    """Regression gate — mirrors the check from CONCERNS.md H1.

    GEPA requires (example, prediction, trace, pred_name, pred_trace).
    A 3-param variant silently triggers MIPROv2 fallback.
    """
    import inspect
    from evolution.core.fitness import skill_fitness_metric

    sig = inspect.signature(skill_fitness_metric)
    assert len(sig.parameters) == 5, (
        f"skill_fitness_metric must accept 5 params for GEPA compat, "
        f"got {len(sig.parameters)}: {list(sig.parameters)}"
    )


# ── Phase 13 additions: max_cost_usd + reflection_model ─────────────────────


def test_evolution_config_defaults_phase13():
    cfg = EvolutionConfig()
    assert cfg.max_cost_usd == 20.0
    assert cfg.reflection_model is None


def test_evolution_config_max_cost_usd_from_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yaml_file = tmp_path / "evolution.yaml"
    yaml_file.write_text("max_cost_usd: 5.5\n")
    monkeypatch.delenv("EVOLUTION_MAX_COST_USD", raising=False)
    monkeypatch.delenv("EVOLUTION_REFLECTION_MODEL", raising=False)
    # load() defaults to ./evolution.yaml — use explicit path via config_path kwarg
    cfg = EvolutionConfig.load(config_path=str(yaml_file))
    assert cfg.max_cost_usd == 5.5


def test_evolution_config_max_cost_usd_env_overrides_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yaml_file = tmp_path / "evolution.yaml"
    yaml_file.write_text("max_cost_usd: 5.5\n")
    monkeypatch.setenv("EVOLUTION_MAX_COST_USD", "3.25")
    cfg = EvolutionConfig.load(config_path=str(yaml_file))
    assert cfg.max_cost_usd == 3.25


def test_evolution_config_max_cost_usd_cli_overrides_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yaml_file = tmp_path / "evolution.yaml"
    yaml_file.write_text("max_cost_usd: 5.5\n")
    monkeypatch.setenv("EVOLUTION_MAX_COST_USD", "3.25")
    cfg = EvolutionConfig.load(config_path=str(yaml_file), max_cost_usd=1.0)
    assert cfg.max_cost_usd == 1.0


# ── WR-02: invalid max_cost_usd must warn, not silently drop ────────────────


def test_wr02_invalid_yaml_max_cost_usd_warns_stderr(tmp_path, monkeypatch, capsys):
    """WR-02: a non-numeric YAML max_cost_usd must emit a stderr warning.

    Pre-fix the three except blocks silently `pass`ed on TypeError/ValueError,
    so a typo like `max_cost_usd: "twenty"` was discarded with the default
    20.0 used instead — no signal to the user that their config was ignored.
    """
    monkeypatch.chdir(tmp_path)
    yaml_file = tmp_path / "evolution.yaml"
    yaml_file.write_text('max_cost_usd: "twenty"\n')
    monkeypatch.delenv("EVOLUTION_MAX_COST_USD", raising=False)
    cfg = EvolutionConfig.load(config_path=str(yaml_file))
    # Behavior preserved: fall back to default.
    assert cfg.max_cost_usd == 20.0
    captured = capsys.readouterr()
    # Must mention max_cost_usd and the bogus value in stderr.
    assert "max_cost_usd" in captured.err
    assert "twenty" in captured.err


def test_wr02_invalid_env_max_cost_usd_warns_stderr(tmp_path, monkeypatch, capsys):
    """WR-02: a non-numeric EVOLUTION_MAX_COST_USD must emit a stderr warning."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVOLUTION_MAX_COST_USD", "not-a-number")
    cfg = EvolutionConfig.load()
    # Behavior preserved: fall back to previous layer.
    assert cfg.max_cost_usd == 20.0
    captured = capsys.readouterr()
    assert "EVOLUTION_MAX_COST_USD" in captured.err
    assert "not-a-number" in captured.err


def test_evolution_config_reflection_model_env_and_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yaml_file = tmp_path / "evolution.yaml"
    yaml_file.write_text("models:\n  reflection: openai/gpt-4.1\n")
    monkeypatch.delenv("EVOLUTION_REFLECTION_MODEL", raising=False)
    cfg = EvolutionConfig.load(config_path=str(yaml_file))
    assert cfg.reflection_model == "openai/gpt-4.1"
    monkeypatch.setenv("EVOLUTION_REFLECTION_MODEL", "openai/gpt-4o")
    cfg = EvolutionConfig.load(config_path=str(yaml_file))
    assert cfg.reflection_model == "openai/gpt-4o"
    cfg = EvolutionConfig.load(config_path=str(yaml_file), reflection_model="custom/m")
    assert cfg.reflection_model == "custom/m"
