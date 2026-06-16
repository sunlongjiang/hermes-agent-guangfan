"""EvolvableArtifact: foundational data class describing one optimizable text point."""

import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal

ArtifactKind = Literal["prompt", "tool"]
TextSource = Literal["param", "return_value", "docstring"]

_VALID_KINDS = {"prompt", "tool"}
_VALID_TEXT_SOURCES = {"param", "return_value", "docstring"}


def compute_baseline_hash(text: str) -> str:
    """Compute the canonical baseline hash for a text artifact.

    Format: 'sha256:<hexdigest>'. Used by runtime.py to detect when a user
    changes their source code — the optimized file becomes stale and is
    silently ignored.

    Args:
        text: The artifact text to hash.

    Returns:
        Hash string in the format 'sha256:<hexdigest>'.
    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


@dataclass
class EvolvableArtifact:
    """One optimizable text point in an agent.

    Created at decorator import time by evolution.sdk.decorators. Consumed by
    optimizer.py (to build AgentModule) and ast_writer.py (to locate the
    source code for patch/pr modes).

    Args:
        agent_name: Name of the agent owning this artifact.
        artifact_id: Unique identifier within the agent (e.g. 'system', 'search').
        kind: Type of artifact — 'prompt' or 'tool'.
        baseline_text: Original unoptimized text at import time.
        text_source: How the text was extracted — 'param', 'return_value', or 'docstring'.
        source_file: Absolute path to the Python file containing the decorator.
        decorator_lineno: Line number of the decorator in source_file.
        constraints: Optional dict of constraint overrides (e.g. max_chars, max_growth).
    """

    agent_name: str
    artifact_id: str
    kind: ArtifactKind
    baseline_text: str
    text_source: TextSource
    source_file: Path
    decorator_lineno: int
    constraints: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"kind must be one of {sorted(_VALID_KINDS)}, got {self.kind!r}"
            )
        if self.text_source not in _VALID_TEXT_SOURCES:
            raise ValueError(
                f"text_source must be one of {sorted(_VALID_TEXT_SOURCES)}, "
                f"got {self.text_source!r}"
            )
        if isinstance(self.source_file, str):
            self.source_file = Path(self.source_file)

    @property
    def baseline_hash(self) -> str:
        """SHA-256 hash of the baseline text, prefixed with 'sha256:'."""
        return compute_baseline_hash(self.baseline_text)

    @property
    def global_id(self) -> str:
        """`<agent_name>:<artifact_id>` — uniquely identifies this artifact across all agents."""
        return f"{self.agent_name}:{self.artifact_id}"

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict. source_file is converted to str.

        Returns:
            Dict with all fields; source_file is a string, not a Path.
        """
        d = asdict(self)
        d["source_file"] = str(self.source_file)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EvolvableArtifact":
        """Deserialize from a dict produced by to_dict().

        Args:
            data: Dict as returned by to_dict().

        Returns:
            A new EvolvableArtifact instance with source_file as a Path.
        """
        d = dict(data)
        d["source_file"] = Path(d["source_file"])
        return cls(**d)
