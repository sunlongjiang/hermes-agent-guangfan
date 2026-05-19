"""Configuration and hermes-agent repo discovery."""

import os
import sys
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


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

    # API endpoint configuration
    api_base: Optional[str] = None  # Custom OpenAI-compatible API base URL
    api_key: Optional[str] = None  # Custom API key

    # Constraints
    max_skill_size: int = 15_000  # 15KB default
    max_tool_desc_size: int = 500  # chars
    max_param_desc_size: int = 200  # chars
    max_prompt_growth: float = 0.2  # 20% max growth over baseline

    # Eval dataset
    eval_dataset_size: int = 20  # Total examples to generate
    train_ratio: float = 0.5
    val_ratio: float = 0.25
    holdout_ratio: float = 0.25

    # Benchmark gating
    run_pytest: bool = True
    run_tblite: bool = False  # Expensive — opt-in
    tblite_regression_threshold: float = 0.02  # Max 2% regression allowed

    # Phase 20 D-16: dual-track benchmark cost cap (independent from GEPA max_cost_usd).
    # Enforced by a SECOND CostTracker instance in evolve_prompt_sections step 10.5
    # and build_tblite_calibration; NOT shared with optimization tracker (D-16 explicit).
    benchmark_max_cost_usd: float = 50.0

    # Phase 20 D-17: per-task LLM/Modal cost estimate for Pre-flight Watermark check.
    # build_tblite_calibration measures this on first run and persists into
    # datasets/prompts/tblite_anchor.json as the source-of-truth value;
    # the EvolutionConfig default is the bootstrap fallback.
    tblite_estimated_cost_per_task_usd: float = 0.4

    # Phase 20 D-03: TBLite 3-run median-of-N for the benchmark gate.
    # ONLY at the final gate (out of GEPA loop). Lowering to 1 disables
    # the conservative stdev rule and is intended for fast local debugging
    # only — production calibration / production gates must keep 3.
    benchmark_runs: int = 3

    # Phase 20 D-11: subprocess heartbeat detection — seconds without new
    # stdout line before TBLiteRunner increments hang_count. hang_count >= 3
    # triggers SIGTERM. Lower for short-task benchmarks; raise for Modal cold
    # starts. Refer to PATTERNS §File 2 Async Stream Pipe pattern.
    benchmark_heartbeat_seconds: int = 60

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
        if yaml_path.exists():
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}

            models = data.get("models", {})
            if models.get("optimizer"):
                config.optimizer_model = models["optimizer"]
            if models.get("eval"):
                config.eval_model = models["eval"]
            if models.get("judge"):
                config.judge_model = models["judge"]
            if data.get("api_base"):
                config.api_base = data["api_base"]
            if data.get("api_key"):
                config.api_key = data["api_key"]

            # Phase 20 D-16: benchmark_max_cost_usd top-level yaml key
            if data.get("benchmark_max_cost_usd") is not None:
                try:
                    config.benchmark_max_cost_usd = float(data["benchmark_max_cost_usd"])
                except (TypeError, ValueError):
                    sys.stderr.write(
                        f"⚠️  evolution.yaml benchmark_max_cost_usd="
                        f"{data['benchmark_max_cost_usd']!r} is not a number; "
                        f"falling back to default {config.benchmark_max_cost_usd}.\n"
                    )
            # Phase 20 D-17: tblite_estimated_cost_per_task_usd top-level yaml key
            if data.get("tblite_estimated_cost_per_task_usd") is not None:
                try:
                    config.tblite_estimated_cost_per_task_usd = float(
                        data["tblite_estimated_cost_per_task_usd"]
                    )
                except (TypeError, ValueError):
                    sys.stderr.write(
                        f"⚠️  evolution.yaml tblite_estimated_cost_per_task_usd="
                        f"{data['tblite_estimated_cost_per_task_usd']!r} is not a number; "
                        f"falling back to default {config.tblite_estimated_cost_per_task_usd}.\n"
                    )
            # Phase 20 D-03: benchmark_runs top-level yaml key
            if data.get("benchmark_runs") is not None:
                try:
                    config.benchmark_runs = int(data["benchmark_runs"])
                except (TypeError, ValueError):
                    sys.stderr.write(
                        f"⚠️  evolution.yaml benchmark_runs="
                        f"{data['benchmark_runs']!r} is not an int; "
                        f"falling back to default {config.benchmark_runs}.\n"
                    )
            # Phase 20 D-11: benchmark_heartbeat_seconds top-level yaml key
            if data.get("benchmark_heartbeat_seconds") is not None:
                try:
                    config.benchmark_heartbeat_seconds = int(
                        data["benchmark_heartbeat_seconds"]
                    )
                except (TypeError, ValueError):
                    sys.stderr.write(
                        f"⚠️  evolution.yaml benchmark_heartbeat_seconds="
                        f"{data['benchmark_heartbeat_seconds']!r} is not an int; "
                        f"falling back to default {config.benchmark_heartbeat_seconds}.\n"
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

        # Phase 20 D-16: EVOLUTION_BENCHMARK_MAX_COST_USD env override
        env_bench_cost = os.getenv("EVOLUTION_BENCHMARK_MAX_COST_USD")
        if env_bench_cost:
            try:
                config.benchmark_max_cost_usd = float(env_bench_cost)
            except ValueError:
                sys.stderr.write(
                    f"⚠️  EVOLUTION_BENCHMARK_MAX_COST_USD={env_bench_cost!r} is not a "
                    f"number; keeping previous value "
                    f"{config.benchmark_max_cost_usd}.\n"
                )
        # Phase 20 D-17: EVOLUTION_TBLITE_COST_PER_TASK_USD env override
        env_tblite_cost = os.getenv("EVOLUTION_TBLITE_COST_PER_TASK_USD")
        if env_tblite_cost:
            try:
                config.tblite_estimated_cost_per_task_usd = float(env_tblite_cost)
            except ValueError:
                sys.stderr.write(
                    f"⚠️  EVOLUTION_TBLITE_COST_PER_TASK_USD={env_tblite_cost!r} is "
                    f"not a number; keeping previous value "
                    f"{config.tblite_estimated_cost_per_task_usd}.\n"
                )
        # Phase 20 D-03: EVOLUTION_BENCHMARK_RUNS env override
        env_runs = os.getenv("EVOLUTION_BENCHMARK_RUNS")
        if env_runs:
            try:
                config.benchmark_runs = int(env_runs)
            except ValueError:
                sys.stderr.write(
                    f"⚠️  EVOLUTION_BENCHMARK_RUNS={env_runs!r} is not an int; "
                    f"keeping previous value {config.benchmark_runs}.\n"
                )
        # Phase 20 D-11: EVOLUTION_BENCHMARK_HEARTBEAT_SECONDS env override
        env_hb = os.getenv("EVOLUTION_BENCHMARK_HEARTBEAT_SECONDS")
        if env_hb:
            try:
                config.benchmark_heartbeat_seconds = int(env_hb)
            except ValueError:
                sys.stderr.write(
                    f"⚠️  EVOLUTION_BENCHMARK_HEARTBEAT_SECONDS={env_hb!r} is not an "
                    f"int; keeping previous value "
                    f"{config.benchmark_heartbeat_seconds}.\n"
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

        # Phase 20 D-16: benchmark_max_cost_usd CLI override
        if overrides.get("benchmark_max_cost_usd") is not None:
            try:
                config.benchmark_max_cost_usd = float(overrides["benchmark_max_cost_usd"])
            except (TypeError, ValueError):
                sys.stderr.write(
                    f"⚠️  benchmark_max_cost_usd override="
                    f"{overrides['benchmark_max_cost_usd']!r} is not a number; "
                    f"keeping previous value {config.benchmark_max_cost_usd}.\n"
                )
        # Phase 20 D-17: tblite_estimated_cost_per_task_usd CLI override
        if overrides.get("tblite_estimated_cost_per_task_usd") is not None:
            try:
                config.tblite_estimated_cost_per_task_usd = float(
                    overrides["tblite_estimated_cost_per_task_usd"]
                )
            except (TypeError, ValueError):
                sys.stderr.write(
                    f"⚠️  tblite_estimated_cost_per_task_usd override="
                    f"{overrides['tblite_estimated_cost_per_task_usd']!r} is not a "
                    f"number; keeping previous value "
                    f"{config.tblite_estimated_cost_per_task_usd}.\n"
                )
        # Phase 20 D-03: benchmark_runs CLI override
        if overrides.get("benchmark_runs") is not None:
            try:
                config.benchmark_runs = int(overrides["benchmark_runs"])
            except (TypeError, ValueError):
                sys.stderr.write(
                    f"⚠️  benchmark_runs override={overrides['benchmark_runs']!r} is "
                    f"not an int; keeping previous value {config.benchmark_runs}.\n"
                )
        # Phase 20 D-11: benchmark_heartbeat_seconds CLI override
        if overrides.get("benchmark_heartbeat_seconds") is not None:
            try:
                config.benchmark_heartbeat_seconds = int(
                    overrides["benchmark_heartbeat_seconds"]
                )
            except (TypeError, ValueError):
                sys.stderr.write(
                    f"⚠️  benchmark_heartbeat_seconds override="
                    f"{overrides['benchmark_heartbeat_seconds']!r} is not an int; "
                    f"keeping previous value {config.benchmark_heartbeat_seconds}.\n"
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
