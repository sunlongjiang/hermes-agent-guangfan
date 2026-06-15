"""Tests for AST-based source rewriting for patch/pr apply modes."""

from pathlib import Path
from textwrap import dedent

import pytest

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.ast_writer import (
    rewrite_artifact_text,
    AstRewriteError,
    generate_unified_diff,
)


def _write_src(tmp_path: Path, content: str) -> Path:
    f = tmp_path / "bot.py"
    f.write_text(dedent(content))
    return f


def test_rewrite_param_form(tmp_path):
    src = _write_src(tmp_path, '''
        from evolution.sdk.decorators import evolvable_agent, evolvable_prompt

        @evolvable_agent(name="bot", schedule=None, auto_optimize=False, min_samples=1, max_cost_usd=1.0)
        class Bot:
            @evolvable_prompt(id="sys", text="OLD TEXT")
            def sys_prompt(self):
                return "x"

            def run(self, q):
                return q
    ''')
    artifact = EvolvableArtifact(
        agent_name="bot", artifact_id="sys", kind="prompt",
        baseline_text="OLD TEXT", text_source="param",
        source_file=src, decorator_lineno=5,
    )
    new_text = rewrite_artifact_text(artifact, new_text="NEW TEXT")
    assert "OLD TEXT" not in new_text
    assert 'text="NEW TEXT"' in new_text or "text='NEW TEXT'" in new_text


def test_rewrite_return_value_form(tmp_path):
    src = _write_src(tmp_path, '''
        from evolution.sdk.decorators import evolvable_prompt

        class Bot:
            @evolvable_prompt(id="p")
            def planner(self):
                return "old plan"
    ''')
    artifact = EvolvableArtifact(
        agent_name="bot", artifact_id="p", kind="prompt",
        baseline_text="old plan", text_source="return_value",
        source_file=src, decorator_lineno=4,
    )
    new_text = rewrite_artifact_text(artifact, new_text="NEW PLAN")
    assert "old plan" not in new_text
    assert "NEW PLAN" in new_text


def test_rewrite_docstring_form(tmp_path):
    src = _write_src(tmp_path, '''
        from evolution.sdk.decorators import evolvable_tool

        class Bot:
            @evolvable_tool(id="s")
            def search(self, q):
                """OLD DOC"""
                return q
    ''')
    artifact = EvolvableArtifact(
        agent_name="bot", artifact_id="s", kind="tool",
        baseline_text="OLD DOC", text_source="docstring",
        source_file=src, decorator_lineno=4,
    )
    new_text = rewrite_artifact_text(artifact, new_text="NEW DOC")
    assert "OLD DOC" not in new_text
    assert "NEW DOC" in new_text


def test_rewrite_return_form_ambiguous_multiple_literals_raises(tmp_path):
    src = _write_src(tmp_path, '''
        from evolution.sdk.decorators import evolvable_prompt

        class Bot:
            @evolvable_prompt(id="p")
            def planner(self):
                helper = "ignore"
                return "the plan"
    ''')
    artifact = EvolvableArtifact(
        agent_name="bot", artifact_id="p", kind="prompt",
        baseline_text="the plan", text_source="return_value",
        source_file=src, decorator_lineno=4,
    )
    with pytest.raises(AstRewriteError, match="multiple string literals"):
        rewrite_artifact_text(artifact, new_text="new")


def test_generate_unified_diff_format(tmp_path):
    original = "line1\nold text\nline3\n"
    new = "line1\nNEW TEXT\nline3\n"
    path = tmp_path / "bot.py"
    path.write_text(original)
    diff = generate_unified_diff(path, original_text=original, new_text=new)
    assert "--- a/" in diff and "+++ b/" in diff
    assert "-old text" in diff
    assert "+NEW TEXT" in diff
