"""Public decorator API for the SDK.

Two-tier:
  Outer:  @evolvable_agent — registers an agent class, intercepts entrypoint methods.
  Inner:  @evolvable_prompt / @evolvable_tool — marks an optimizable text point.

Text source resolution priority:
  1. text=... parameter on the decorator
  2. function return value (only if the function has no args besides self
     AND the body is exactly `return <single string literal>`)
  3. function docstring
  4. else raise ArtifactExtractionError at import time

Decorator import期 invariant: 禁止网络 IO / 写文件 IO. Allowed: read
~/.evolution/optimized/<agent>/*.json once (with fallback).
"""

import ast
import functools
import inspect
import sys
from pathlib import Path
from typing import Callable, Iterable, Optional

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk import registry


class ArtifactExtractionError(Exception):
    """Raised at import time when a decorated artifact can't be resolved."""


# ── Inner decorator factories ────────────────────────────────────────────


def _build_inner_decorator(kind: str):
    """Factory: returns @evolvable_prompt or @evolvable_tool."""

    def decorator(
        *,
        id: str,
        text: Optional[str] = None,
        max_chars: Optional[int] = None,
        max_growth: Optional[float] = None,
        forbidden_patterns: Optional[Iterable[str]] = None,
        required_patterns: Optional[Iterable[str]] = None,
    ):
        if not id:
            raise ArtifactExtractionError("id is required (non-empty string)")

        def wrapper(func: Callable) -> Callable:
            baseline_text, text_source = _resolve_text(func, text)
            constraints = {}
            if max_chars is not None:
                constraints["max_chars"] = max_chars
            if max_growth is not None:
                constraints["max_growth"] = max_growth
            if forbidden_patterns is not None:
                constraints["forbidden_patterns"] = list(forbidden_patterns)
            if required_patterns is not None:
                constraints["required_patterns"] = list(required_patterns)

            try:
                source_file = Path(inspect.getsourcefile(func) or "<unknown>")
            except TypeError:
                source_file = Path("<unknown>")
            try:
                _, lineno = inspect.getsourcelines(func)
            except (OSError, TypeError):
                lineno = 0

            # Stash the partial artifact info on the function; outer @evolvable_agent
            # will collect these and finalize agent_name + global validation.
            func._evolution_artifact = {
                "id": id,
                "kind": kind,
                "baseline_text": baseline_text,
                "text_source": text_source,
                "source_file": source_file,
                "decorator_lineno": lineno,
                "constraints": constraints,
            }
            return func

        return wrapper

    return decorator


evolvable_prompt = _build_inner_decorator("prompt")
evolvable_tool = _build_inner_decorator("tool")


# ── Text resolution helpers ──────────────────────────────────────────────


def _resolve_text(func: Callable, explicit_text: Optional[str]) -> tuple[str, str]:
    """Return (baseline_text, text_source). Raises ArtifactExtractionError if none found."""
    if explicit_text is not None:
        return explicit_text, "param"

    # Form 2: function return value — only if no args (except self) and body is exactly
    # `return <single string literal>`.
    sig = inspect.signature(func)
    params = [p for p in sig.parameters.values()
              if p.name != "self" and p.default is inspect.Parameter.empty
              and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
    if not params:
        literal = _extract_single_string_literal(func)
        if literal is not None:
            return literal, "return_value"

    # Form 3: docstring
    doc = (func.__doc__ or "").strip()
    if doc:
        return doc, "docstring"

    raise ArtifactExtractionError(
        f"no text source found for {func.__qualname__}: "
        "provide text= parameter, return a single string literal with no args, "
        "or add a docstring."
    )


def _extract_single_string_literal(func: Callable) -> Optional[str]:
    """If the function body is exactly `return <single string literal>`, return it.

    Used by Form 2. Returns None if the body is more complex (caller falls back to
    docstring or raises).
    """
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        return None

    # Dedent so AST parses correctly when the function is a class method.
    import textwrap
    source = textwrap.dedent(source)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    fn = tree.body[0]
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None

    # Strip docstring if present.
    body = fn.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]

    if len(body) != 1:
        return None
    stmt = body[0]
    if not isinstance(stmt, ast.Return):
        return None
    val = stmt.value
    if isinstance(val, ast.Constant) and isinstance(val.value, str):
        return val.value
    return None


# ── Outer decorator: @evolvable_agent ────────────────────────────────────


_ENTRYPOINT_CANDIDATES = ("run", "__call__", "invoke", "execute")


def evolvable_agent(
    *,
    name: str,
    version: str = "0.1.0",
    metric: Optional[Callable] = None,
    judge_dimensions: tuple = ("correctness", "conciseness"),
    min_samples: int = 50,
    schedule: Optional[str] = "weekly",
    auto_optimize: bool = True,
    apply: str = "runtime",
    sink=None,
    max_cost_usd: float = 5.0,
    entrypoint: Optional[str] = None,
):
    """Outer decorator. Registers the class and wraps its entrypoint method.

    Task 5 (runtime.py) augments the wrapper to capture traces.
    """
    if not name:
        raise ArtifactExtractionError("@evolvable_agent name= is required")
    if apply not in ("runtime", "patch", "pr"):
        raise ArtifactExtractionError(
            f"apply must be one of runtime/patch/pr, got {apply!r}"
        )

    def class_decorator(cls):
        # Collect inner artifacts.
        artifacts: list[EvolvableArtifact] = []
        seen_ids: set[str] = set()
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            meta = getattr(attr, "_evolution_artifact", None)
            if meta is None:
                continue
            if meta["id"] in seen_ids:
                raise ArtifactExtractionError(
                    f"duplicate artifact id {meta['id']!r} in agent {name!r}"
                )
            seen_ids.add(meta["id"])
            artifacts.append(EvolvableArtifact(
                agent_name=name,
                artifact_id=meta["id"],
                kind=meta["kind"],
                baseline_text=meta["baseline_text"],
                text_source=meta["text_source"],
                source_file=meta["source_file"],
                decorator_lineno=meta["decorator_lineno"],
                constraints=meta["constraints"],
            ))

        # Resolve entrypoint method.
        entry = entrypoint or _detect_entrypoint(cls)
        if entry is None:
            raise ArtifactExtractionError(
                f"agent {name!r} has no entrypoint: provide entrypoint= or "
                f"define one of {_ENTRYPOINT_CANDIDATES}"
            )

        # Wrap the entrypoint. Task 5 will add full trace capture; for now,
        # we install a thin shim that just calls through and marks itself.
        original = getattr(cls, entry)

        @functools.wraps(original)
        def wrapped(self, *args, **kwargs):
            # Task 5 will replace this body with full trace capture.
            from evolution.sdk import runtime
            return runtime.invoke(self, entry, original, args, kwargs)

        wrapped._evolution_wrapped = True
        setattr(cls, entry, wrapped)

        # Resolve source files (de-duplicated).
        source_files = sorted({a.source_file for a in artifacts})
        try:
            source_files.append(Path(inspect.getsourcefile(cls) or "<unknown>"))
            source_files = sorted(set(source_files))
        except TypeError:
            pass

        # Stash meta on the class.
        cls._evolution_meta = {
            "name": name,
            "version": version,
            "metric": metric,
            "judge_dimensions": judge_dimensions,
            "min_samples": min_samples,
            "schedule": schedule,
            "auto_optimize": auto_optimize,
            "apply": apply,
            "sink": sink,
            "max_cost_usd": max_cost_usd,
            "entrypoint": entry,
            "artifacts": artifacts,
        }

        # Register.
        module_path = f"{cls.__module__}:{cls.__name__}"
        reg = registry.AgentRegistration(
            name=name,
            module=module_path,
            version=version,
            schedule=schedule,
            min_samples=min_samples,
            auto_optimize=auto_optimize,
            apply=apply,
            max_cost_usd=max_cost_usd,
            artifacts=artifacts,
            source_files=source_files,
        )
        registry.register_agent(reg)

        return cls

    return class_decorator


def _detect_entrypoint(cls) -> Optional[str]:
    for candidate in _ENTRYPOINT_CANDIDATES:
        if callable(getattr(cls, candidate, None)):
            return candidate
    return None
