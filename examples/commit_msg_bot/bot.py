"""Commit Message Bot — generates conventional commit messages from git diffs.

This is a dogfood example exercising all three text-source forms of
@evolvable_prompt / @evolvable_tool plus the standard agent decorator.

Usage:
    from examples.commit_msg_bot.bot import CommitMsgBot
    bot = CommitMsgBot()
    msg = bot.run(diff_text="diff --git a/foo.py ...")
"""

import re

from evolution.sdk import (
    evolvable_agent,
    evolvable_prompt,
    evolvable_tool,
)
from evolution.sdk import runtime


@evolvable_agent(
    name="commit-msg-bot",
    version="0.1.0",
    judge_dimensions=("correctness", "conciseness"),
    min_samples=20,
    schedule="weekly",
    auto_optimize=True,
    apply="patch",
    max_cost_usd=3.0,
)
class CommitMsgBot:
    """Generates conventional commits from staged diffs."""

    # Form 1: text= parameter (most explicit)
    @evolvable_prompt(
        id="system",
        text="You are an expert engineer. Read the diff and produce ONE conventional commit message line. Format: <type>(<scope>): <subject>. Subject must be imperative mood and under 72 chars.",
        max_chars=4000,
        max_growth=20.0,
    )
    def system_prompt(self) -> str:
        return runtime.resolve_text("commit-msg-bot", "system")

    # Form 2: function return value (clean syntax for short prompts)
    @evolvable_prompt(id="few_shot_header", max_chars=4000)
    def few_shot_header(self) -> str:
        return "Here are example commits in this codebase. Match their style."

    # Form 3: docstring (zero ceremony for tool descriptions)
    @evolvable_tool(id="diff_classifier", max_chars=4000)
    def classify_diff(self, diff: str) -> str:
        """Classify the diff into one of: feat, fix, docs, refactor, test, chore.
        Inspect the file paths and the nature of the changes."""
        if "test_" in diff or "/tests/" in diff:
            return "test"
        if "README" in diff or ".md" in diff:
            return "docs"
        if "+++" in diff and "fix" in diff.lower():
            return "fix"
        return "chore"

    def run(self, diff_text: str) -> str:
        """Generate a commit message for the given diff.

        Pure logic — no LLM call here for the dogfood; the SDK still captures
        traces so we can see what gets recorded.
        """
        commit_type = self.classify_diff(diff_text)
        scope = self._infer_scope(diff_text)
        subject = self._summarize(diff_text)
        prefix = f"{commit_type}({scope})" if scope else commit_type
        return f"{prefix}: {subject}"

    def _infer_scope(self, diff: str) -> str:
        match = re.search(r"\+\+\+ b/([^/\s]+)/", diff)
        return match.group(1) if match else ""

    def _summarize(self, diff: str) -> str:
        plus_lines = [l[1:].strip() for l in diff.splitlines()
                      if l.startswith("+") and not l.startswith("+++")]
        if not plus_lines:
            return "update files"
        first = plus_lines[0]
        return first[:60] if len(first) > 60 else first
