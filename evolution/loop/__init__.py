"""Phase 22: Continuous evolution loop for hermes-agent.

Lazy-import guard: submodules are NOT auto-imported here.
Callers must explicitly import what they need:

    from evolution.loop.pr_creator import create_pr
    from evolution.loop.run_loop import run_loop

Rationale: this package depends on gh CLI (runtime) and subprocess calls
that must not fire at import time.
"""
