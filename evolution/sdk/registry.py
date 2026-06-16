"""Process-local agent registry + optional ~/.evolution/registry.json persistence.

CRITICAL: decorator import期 only writes to in-memory _REGISTRY. Persisting to
disk requires either:
  - explicit call: persist_to_file() (e.g., from `evolution discover` CLI)
  - env var: EVOLUTION_AUTO_REGISTER=1 (advanced; opt-in)

This avoids "production app imports user module → writes home directory"
as a安全雷区.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.trace_sink import _evolution_home


class DuplicateAgentError(Exception):
    """Raised when two different modules register the same agent name."""


@dataclass
class AgentRegistration:
    """Metadata for one registered agent."""
    name: str
    module: str                       # "myapp.bots.research:ResearchBot"
    version: str
    schedule: Optional[str]
    min_samples: int
    auto_optimize: bool
    apply: str                        # "runtime" | "patch" | "pr"
    max_cost_usd: float
    artifacts: list[EvolvableArtifact]
    source_files: list[Path]
    schedule_managed_by: Optional[str] = None  # 'evolution-loop.yml' for hermes adapter
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    last_optimized: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "module": self.module,
            "version": self.version,
            "schedule": self.schedule,
            "min_samples": self.min_samples,
            "auto_optimize": self.auto_optimize,
            "apply": self.apply,
            "max_cost_usd": self.max_cost_usd,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "source_files": [str(p) for p in self.source_files],
            "schedule_managed_by": self.schedule_managed_by,
            "registered_at": self.registered_at,
            "last_optimized": self.last_optimized,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentRegistration":
        return cls(
            name=data["name"],
            module=data["module"],
            version=data["version"],
            schedule=data.get("schedule"),
            min_samples=data["min_samples"],
            auto_optimize=data["auto_optimize"],
            apply=data["apply"],
            max_cost_usd=data["max_cost_usd"],
            artifacts=[EvolvableArtifact.from_dict(a) for a in data["artifacts"]],
            source_files=[Path(p) for p in data["source_files"]],
            schedule_managed_by=data.get("schedule_managed_by"),
            registered_at=data.get("registered_at", ""),
            last_optimized=data.get("last_optimized"),
        )


# Process-local in-memory registry.
_REGISTRY: dict[str, AgentRegistration] = {}


def register_agent(reg: AgentRegistration) -> None:
    """Register or replace an agent in-memory.

    Raises DuplicateAgentError if another module already registered the same name.
    Re-registering from the same module is idempotent (replaces silently — covers
    reimport during tests / IDE reload).
    """
    existing = _REGISTRY.get(reg.name)
    if existing is not None and existing.module != reg.module:
        raise DuplicateAgentError(
            f"agent name {reg.name!r} already registered by different module "
            f"{existing.module!r} (new: {reg.module!r}). Choose a unique name."
        )
    _REGISTRY[reg.name] = reg


def get_agent(name: str) -> Optional[AgentRegistration]:
    return _REGISTRY.get(name)


def list_agents() -> list[str]:
    return sorted(_REGISTRY.keys())


def _registry_path() -> Path:
    return _evolution_home() / "registry.json"


def persist_to_file() -> Path:
    """Atomically write the in-memory registry to ~/.evolution/registry.json.

    Uses fcntl.flock to serialize concurrent writers (best-effort on POSIX;
    silently degrades on Windows where fcntl is unavailable).
    """
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": 1,
        "agents": {name: reg.to_dict() for name, reg in _REGISTRY.items()},
    }

    tmp = path.with_suffix(".tmp")
    lock_path = path.with_suffix(".lock")

    # Acquire lock (best-effort).
    try:
        import fcntl
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            tmp.write_text(json.dumps(payload, indent=2))
            os.replace(tmp, path)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
    except ImportError:
        # Windows fallback: no locking, but atomic rename still applies.
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, path)

    return path


def load_from_file() -> None:
    """Load ~/.evolution/registry.json into _REGISTRY.

    No-op if the file doesn't exist. Does NOT clear existing in-memory entries;
    callers wanting a fresh state should _REGISTRY.clear() first.
    """
    path = _registry_path()
    if not path.exists():
        return
    data = json.loads(path.read_text())
    if data.get("version") != 1:
        raise ValueError(f"unsupported registry.json version {data.get('version')!r}")
    for name, entry in data.get("agents", {}).items():
        _REGISTRY[name] = AgentRegistration.from_dict(entry)
