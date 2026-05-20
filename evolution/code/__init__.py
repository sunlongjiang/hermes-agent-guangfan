"""Phase 21: Darwinian code evolution for hermes-agent components.

Lazy-import guard (D-21 / D-03): submodules are NOT auto-imported here.
Callers must explicitly import what they need:

    from evolution.code.code_evolver_adapter import evolve_code
    from evolution.code.code_fitness import CodeFitness, score_candidate
    from evolution.code.code_target_loader import CodeTarget, find_target
    from evolution.code.sandbox_runner import run_pytest_in_sandbox

Rationale: openevolve is an optional dependency (`pip install .[code]`).
`evolve_code --dry-run` or any import of `evolution.code` MUST NOT crash
when openevolve is not installed. Importing `evolution.code.code_evolver_adapter`
at module level would trigger ImportError if openevolve is absent.

Only `evolution/code/code_evolver_adapter.py` may contain `import openevolve`
or `from openevolve ...` statements (D-03 single import surface).
"""
