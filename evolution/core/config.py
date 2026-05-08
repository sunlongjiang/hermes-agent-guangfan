"""Configuration and hermes-agent repo discovery."""

import os
import re
import sys
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# Matches things that look like real LLM provider keys so we can warn when
# a literal value (instead of an env-var reference) is baked into evolution.yaml.
_LITERAL_KEY_RE = re.compile(r"^(sk-|sk_|ghp_|gho_|xox[baprs]-|AKIA[0-9A-Z]{16})")


def _expand_env(value):
    """Expand ${VAR} / $VAR references in a string loaded from YAML.

    Non-strings pass through unchanged. Unknown env vars expand to empty string
    (matches os.path.expandvars default — surfaced by later callers).
    """
    if not isinstance(value, str):
        return value
    return os.path.expandvars(value)



@dataclass
class EvolutionConfig:
    """Configuration for a self-evolution optimization run."""

    # hermes-agent repo path
    hermes_agent_path: Path = field(default_factory=lambda: get_hermes_agent_path())

    # Optimization parameters
    iterations: int = 10
    population_size: int = 5

    # LLM configuration
    optimizer_model: str = "openai/gpt-4.1"  # Model for GEPA reflections
    eval_model: str = "openai/gpt-4.1-mini"  # Model for LLM-as-judge scoring
    judge_model: str = "openai/gpt-4.1"  # Model for dataset generation
    # Reflection model for GEPA (D-08/D-13) — falls back to optimizer_model when None
    reflection_model: Optional[str] = None

    # API endpoint configuration
    api_base: Optional[str] = None  # Custom OpenAI-compatible API base URL
    api_key: Optional[str] = None  # Custom API key

    # Constraints
    max_skill_size: int = 15_000  # 15KB default
    max_tool_desc_size: int = 500  # chars
    max_param_desc_size: int = 200  # chars
    max_prompt_growth: float = 0.2  # 20% max growth over baseline

    # Cost cap for GEPA compile + eval (D-13 / folded todo 2026-05-07-max-cost-usd-and-reflection-model.md)
    # USD; enforced by evolution/core/cost_tracker.py. Set <= 0 to disable (not recommended).
    max_cost_usd: float = 20.0

    # Eval dataset
    eval_dataset_size: int = 20  # Total examples to generate
    train_ratio: float = 0.5
    val_ratio: float = 0.25
    holdout_ratio: float = 0.25

    # Benchmark gating
    run_pytest: bool = True
    run_tblite: bool = False  # Expensive — opt-in
    tblite_regression_threshold: float = 0.02  # Max 2% regression allowed

    # Output
    output_dir: Path = field(default_factory=lambda: Path("./output"))
    create_pr: bool = True

    def get_lm_kwargs(self) -> dict:
        """Return kwargs to pass to dspy.LM() for custom API endpoints."""
        kwargs = {}
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        return kwargs

    @classmethod
    def load(cls, config_path: Optional[str] = None, **overrides) -> "EvolutionConfig":
        """Load config from evolution.yaml with env var and CLI overrides.

        Priority (highest wins):
        1. CLI overrides (passed as **overrides)
        2. Environment variables (EVOLUTION_API_BASE, EVOLUTION_API_KEY, EVOLUTION_MODEL)
        3. evolution.yaml config file
        4. Dataclass defaults
        """
        config = cls()

        # ── Load from YAML ────────────────────────────────────────────────
        yaml_path = Path(config_path) if config_path else Path("evolution.yaml")
        yaml_had_literal_key = False
        if yaml_path.exists():
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}

            models = data.get("models", {})
            if models.get("optimizer"):
                config.optimizer_model = _expand_env(models["optimizer"])
            if models.get("eval"):
                config.eval_model = _expand_env(models["eval"])
            if models.get("judge"):
                config.judge_model = _expand_env(models["judge"])
            # Phase 13: reflection_model lives alongside other model names under `models:`
            if models.get("reflection"):
                config.reflection_model = _expand_env(models["reflection"])
            if data.get("api_base"):
                config.api_base = _expand_env(data["api_base"])
            if data.get("api_key"):
                raw_key = data["api_key"]
                # Flag literal keys BEFORE expansion so env-var references are exempt
                if isinstance(raw_key, str) and "$" not in raw_key and _LITERAL_KEY_RE.match(raw_key):
                    yaml_had_literal_key = True
                config.api_key = _expand_env(raw_key)
            # Phase 13: max_cost_usd is a top-level yaml key
            if data.get("max_cost_usd") is not None:
                try:
                    config.max_cost_usd = float(data["max_cost_usd"])
                except (TypeError, ValueError):
                    # WR-02: invalid value → keep default; warn so users
                    # don't silently lose their intended config setting.
                    sys.stderr.write(
                        f"⚠️  evolution.yaml max_cost_usd="
                        f"{data['max_cost_usd']!r} is not a number; "
                        f"falling back to default {config.max_cost_usd}.\n"
                    )

        # ── Environment variable overrides ─────────────────────────────────
        env_base = os.getenv("EVOLUTION_API_BASE")
        if env_base:
            config.api_base = env_base
        env_key = os.getenv("EVOLUTION_API_KEY")
        if env_key:
            config.api_key = env_key
        env_model = os.getenv("EVOLUTION_MODEL")
        if env_model:
            config.optimizer_model = env_model
            config.eval_model = env_model
            config.judge_model = env_model
        # Phase 13: reflection_model + max_cost_usd env overrides
        env_refl = os.getenv("EVOLUTION_REFLECTION_MODEL")
        if env_refl:
            config.reflection_model = env_refl
        env_cost = os.getenv("EVOLUTION_MAX_COST_USD")
        if env_cost:
            try:
                config.max_cost_usd = float(env_cost)
            except ValueError:
                # WR-02: invalid numeric → keep previous layer; warn.
                sys.stderr.write(
                    f"⚠️  EVOLUTION_MAX_COST_USD={env_cost!r} is not a "
                    f"number; keeping previous value "
                    f"{config.max_cost_usd}.\n"
                )

        # ── CLI overrides (highest priority) ───────────────────────────────
        if overrides.get("api_base"):
            config.api_base = overrides["api_base"]
        if overrides.get("api_key"):
            config.api_key = overrides["api_key"]
        if overrides.get("model"):
            config.optimizer_model = overrides["model"]
            config.eval_model = overrides["model"]
            config.judge_model = overrides["model"]
        if overrides.get("iterations"):
            config.iterations = overrides["iterations"]
        if overrides.get("hermes_repo"):
            config.hermes_agent_path = Path(overrides["hermes_repo"])
        # Phase 13: reflection_model + max_cost_usd CLI overrides
        if overrides.get("reflection_model") is not None:
            config.reflection_model = overrides["reflection_model"]
        if overrides.get("max_cost_usd") is not None:
            try:
                config.max_cost_usd = float(overrides["max_cost_usd"])
            except (TypeError, ValueError):
                # WR-02: Click already validates --max-cost-usd as float,
                # so this branch is mostly defense in depth against
                # programmatic callers. Still warn rather than swallow.
                sys.stderr.write(
                    f"⚠️  max_cost_usd override="
                    f"{overrides['max_cost_usd']!r} is not a number; "
                    f"keeping previous value {config.max_cost_usd}.\n"
                )

        # ── Literal-key warning (loud, not fatal) ─────────────────────────
        # Emit once at load time so users see it every run until they migrate
        # the key to an env-var reference. Skipped when EVOLVE_SUPPRESS_KEY_WARN=1
        # (CI / test environments that intentionally check key handling).
        if yaml_had_literal_key and not os.getenv("EVOLVE_SUPPRESS_KEY_WARN"):
            sys.stderr.write(
                "⚠️  evolution.yaml contains a literal API key. "
                "Replace with an env-var reference like api_key: \"${DASHSCOPE_KEY}\" "
                "to avoid plaintext-on-disk leaks. See README.md § Secrets.\n"
            )

        return config


def get_hermes_agent_path() -> Path:
    """Discover the hermes-agent repo path.

    Priority:
    1. HERMES_AGENT_REPO env var
    2. ~/.hermes/hermes-agent (standard install location)
    3. ../hermes-agent (sibling directory)
    """
    env_path = os.getenv("HERMES_AGENT_REPO")
    if env_path:
        p = Path(env_path).expanduser()
        if p.exists():
            return p

    home_path = Path.home() / ".hermes" / "hermes-agent"
    if home_path.exists():
        return home_path

    sibling_path = Path(__file__).parent.parent.parent / "hermes-agent"
    if sibling_path.exists():
        return sibling_path

    raise FileNotFoundError(
        "Cannot find hermes-agent repo. Set HERMES_AGENT_REPO env var "
        "or ensure it exists at ~/.hermes/hermes-agent"
    )
