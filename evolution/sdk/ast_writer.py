"""AST-based source rewriter for apply="patch" / "pr" modes.

Per spec §4.2 write-back rules:
  - Form 1 (param):       rewrite the text= kwarg's string literal on the decorator call
  - Form 2 (return_value): rewrite the function body's single string literal
  - Form 3 (docstring):    rewrite the function's docstring constant
"""

import ast
import difflib
from pathlib import Path

from evolution.sdk.artifact import EvolvableArtifact


class AstRewriteError(Exception):
    """Raised when the rewrite target cannot be uniquely located."""


def rewrite_artifact_text(artifact: EvolvableArtifact, *, new_text: str) -> str:
    """Return the modified source code (does NOT write to disk).

    Caller is responsible for writing or producing a diff.
    """
    src = artifact.source_file.read_text()
    tree = ast.parse(src)

    if artifact.text_source == "param":
        new_src = _rewrite_param(tree, src, artifact, new_text)
    elif artifact.text_source == "return_value":
        new_src = _rewrite_return_value(tree, src, artifact, new_text)
    elif artifact.text_source == "docstring":
        new_src = _rewrite_docstring(tree, src, artifact, new_text)
    else:
        raise AstRewriteError(f"unknown text_source: {artifact.text_source!r}")

    return new_src


def generate_unified_diff(
    path: Path, *, original_text: str, new_text: str
) -> str:
    """Generate a standard unified diff string (writable as a .patch file)."""
    rel = path.name
    return "".join(difflib.unified_diff(
        original_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
    ))


# ── Rewrite implementations ─────────────────────────────────────────────


def _rewrite_param(tree: ast.AST, src: str, artifact: EvolvableArtifact,
                   new_text: str) -> str:
    """Rewrite the text= keyword arg on the matching @evolvable_prompt/tool call."""
    target_call = _find_decorator_call(tree, artifact)
    text_kw = next(
        (kw for kw in target_call.keywords if kw.arg == "text"
         and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)),
        None,
    )
    if text_kw is None:
        raise AstRewriteError(
            f"could not find text= kwarg on decorator at {artifact.source_file}:"
            f"{artifact.decorator_lineno}"
        )
    return _replace_node_value(src, text_kw.value, new_text)


def _rewrite_return_value(tree: ast.AST, src: str, artifact: EvolvableArtifact,
                          new_text: str) -> str:
    """Rewrite the unique string literal in the function body."""
    fn = _find_target_function(tree, artifact)
    # Walk only fn.body (not fn itself which includes decorator_list).
    body_nodes: list[ast.AST] = []
    for stmt in fn.body:
        body_nodes.extend(ast.walk(stmt))
    # Collect all string literal constants in the body.
    literals = [
        node for node in body_nodes
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    # Exclude docstring explicitly (first stmt Expr with a Constant str).
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)
            and isinstance(fn.body[0].value.value, str)):
        doc_node = fn.body[0].value
        literals = [n for n in literals if n is not doc_node]

    if len(literals) == 0:
        raise AstRewriteError(
            f"no string literal found in {fn.name} body for return-value rewrite"
        )
    if len(literals) > 1:
        raise AstRewriteError(
            f"multiple string literals in {fn.name} body — "
            "switch to text= parameter for patch mode"
        )
    return _replace_node_value(src, literals[0], new_text)


def _rewrite_docstring(tree: ast.AST, src: str, artifact: EvolvableArtifact,
                       new_text: str) -> str:
    fn = _find_target_function(tree, artifact)
    if not (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)
            and isinstance(fn.body[0].value.value, str)):
        raise AstRewriteError(f"{fn.name} has no docstring to rewrite")
    return _replace_node_value(src, fn.body[0].value, new_text)


# ── AST navigation helpers ──────────────────────────────────────────────


def _find_target_function(tree: ast.AST, artifact: EvolvableArtifact) -> ast.FunctionDef:
    """Locate the function decorated with @evolvable_prompt/tool(id=artifact.artifact_id)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                call = dec if isinstance(dec, ast.Call) else None
                if call and _decorator_matches(call, artifact):
                    return node
    raise AstRewriteError(
        f"could not find function for artifact {artifact.global_id}"
    )


def _find_decorator_call(tree: ast.AST, artifact: EvolvableArtifact) -> ast.Call:
    fn = _find_target_function(tree, artifact)
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call) and _decorator_matches(dec, artifact):
            return dec
    raise AstRewriteError(
        f"decorator call not found for {artifact.global_id}"
    )


def _decorator_matches(call: ast.Call, artifact: EvolvableArtifact) -> bool:
    # Decorator name check.
    fn_name = None
    if isinstance(call.func, ast.Name):
        fn_name = call.func.id
    elif isinstance(call.func, ast.Attribute):
        fn_name = call.func.attr
    if fn_name not in ("evolvable_prompt", "evolvable_tool"):
        return False
    # id= kwarg check.
    for kw in call.keywords:
        if kw.arg == "id" and isinstance(kw.value, ast.Constant):
            return kw.value.value == artifact.artifact_id
    return False


def _replace_node_value(src: str, node: ast.Constant, new_text: str) -> str:
    """Replace the source slice for a Constant node with a properly-quoted new value."""
    # Compute byte offsets in the source.
    lines = src.splitlines(keepends=True)
    start_line = node.lineno - 1
    start_col = node.col_offset
    end_line = node.end_lineno - 1
    end_col = node.end_col_offset

    # Build prefix + replacement + suffix.
    # Compute absolute offsets.
    start_off = sum(len(l) for l in lines[:start_line]) + start_col
    end_off = sum(len(l) for l in lines[:end_line]) + end_col

    # Choose quote style: prefer triple-double if new_text has newlines or both quote types.
    if "\n" in new_text:
        quoted = '"""' + new_text.replace('"""', '\\"""') + '"""'
    elif '"' in new_text and "'" not in new_text:
        quoted = "'" + new_text + "'"
    else:
        quoted = '"' + new_text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    return src[:start_off] + quoted + src[end_off:]
