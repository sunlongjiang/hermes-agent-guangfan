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
    # Use importlib (not `from evolution.loop import ...`) to avoid recursive
    # __getattr__ dispatch: `from X import Y` re-enters __getattr__ if Y isn't
    # yet on the module, which would loop here forever.
    if name in __all__:
        import importlib
        mod = importlib.import_module(f"evolution.loop.{name}")
        globals()[name] = mod  # cache on the package for subsequent accesses
        return mod
    raise AttributeError(f"module 'evolution.loop' has no attribute {name!r}")
