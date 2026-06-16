"""Minimal real agent for end-to-end dogfood: covers trace capture + optimized loading."""

from evolution.sdk import runtime
from evolution.sdk.decorators import (
    evolvable_agent, evolvable_prompt, evolvable_tool,
)


@evolvable_agent(
    name="echo-bot-test",
    version="0.1.0",
    judge_dimensions=("relevance",),
    min_samples=3,
    schedule=None,
    auto_optimize=False,
    max_cost_usd=1.0,
)
class EchoBot:
    @evolvable_prompt(id="rewriter", text="Rewrite this concisely: {input}",
                      max_chars=200, max_growth=0.5)
    def rewriter_prompt(self) -> str:
        return runtime.resolve_text("echo-bot-test", "rewriter")

    @evolvable_tool(id="echo_tool", max_chars=300)
    def echo_tool(self, q: str) -> str:
        """Echo back the input verbatim."""
        return q

    def run(self, query: str) -> str:
        prompt = self.rewriter_prompt()
        echoed = self.echo_tool(query)
        return f"{prompt.replace('{input}', echoed)}"
