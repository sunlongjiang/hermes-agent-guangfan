"""Hermes adapter — registers the legacy 6-CLI pipeline as one SDK agent.

This adapter does NOT change how the legacy pipeline runs (evolution-loop.yml
keeps scheduling it). It just makes hermes visible in the unified registry so
`evolution status --agent hermes` and `evolution scaffold --check` see it.

`schedule_managed_by="evolution-loop.yml"` tells scaffold to skip generation.
"""

from pathlib import Path

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk import registry


# Six legacy CLIs in dispatch order (matches evolution/core/config.LOOP_CLI_NAMES).
HERMES_CLI_NAMES = (
    "skill",
    "tool_descriptions",
    "tool_params",
    "tool_reasoning",
    "prompt_sections",
    "code",
)

# Best-effort kind mapping for each CLI's primary artifact.
_CLI_KIND_MAP = {
    "skill": "prompt",
    "tool_descriptions": "tool",
    "tool_params": "tool",
    "tool_reasoning": "prompt",
    "prompt_sections": "prompt",
    "code": "prompt",  # code-as-text from SDK's perspective
}


def register_hermes_adapter(name: str = "hermes") -> None:
    """Register the hermes adapter agent (idempotent).

    Each of the 6 legacy CLIs becomes one EvolvableArtifact entry. The artifacts
    use placeholder baseline_text — the actual optimizable text lives in the
    hermes-agent repo and is read by the legacy CLI subprocesses, not by the
    SDK runtime path.
    """
    existing = registry.get_agent(name)
    if existing is not None:
        return  # idempotent

    source_file = Path(__file__).resolve()
    artifacts = [
        EvolvableArtifact(
            agent_name=name,
            artifact_id=cli_name,
            kind=_CLI_KIND_MAP[cli_name],
            baseline_text=f"<managed by evolution/{cli_name} CLI>",
            text_source="param",
            source_file=source_file,
            decorator_lineno=0,
            constraints={"managed_by_legacy_cli": True},
        )
        for cli_name in HERMES_CLI_NAMES
    ]

    reg = registry.AgentRegistration(
        name=name,
        module=f"evolution.adapters.hermes:HermesAdapter",
        version="1.0.0",
        schedule="weekly",  # informational; not used by scaffold
        min_samples=0,
        auto_optimize=True,
        apply="pr",
        max_cost_usd=30.0,  # sum of legacy CLI caps
        artifacts=artifacts,
        source_files=[source_file],
        schedule_managed_by="evolution-loop.yml",
    )
    registry.register_agent(reg)


class HermesAdapter:
    """Marker class so registry.module resolves cleanly. No runtime behavior."""

    def run(self, *args, **kwargs):
        raise NotImplementedError(
            "Hermes adapter does not run via SDK invoke path. Use "
            "evolution-loop.yml + python -m evolution.loop.run_loop instead."
        )
