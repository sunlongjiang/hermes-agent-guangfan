"""Phase 22: Continuous evolution loop for hermes-agent.

Lazy-import guard: submodules are NOT auto-imported. Callers explicitly
import what they need (matches Phase 21 evolution/code/__init__.py idiom):

    from evolution.loop.pr_creator import create_pr
    from evolution.loop.run_loop import evolve_loop

Rationale: this package depends on gh CLI (runtime) and subprocess calls
that must not fire at import time.

A module-level __getattr__ lets callers also do `import evolution.loop;
evolution.loop.run_loop` without an explicit `from ... import` — the
submodule loads on first attribute access.
"""

__all__ = ["run_loop", "pr_creator"]


def __getattr__(name):
    if name == "run_loop":
        from evolution.loop import run_loop as _mod
        return _mod
    if name == "pr_creator":
        from evolution.loop import pr_creator as _mod
        return _mod
    raise AttributeError(f"module 'evolution.loop' has no attribute {name!r}")
