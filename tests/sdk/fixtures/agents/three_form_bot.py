"""Agent fixture demonstrating all three text-source forms."""
from evolution.sdk.decorators import (
    evolvable_agent, evolvable_prompt, evolvable_tool,
)


@evolvable_agent(
    name="three-form-bot",
    version="0.1.0",
    judge_dimensions=("correctness",),
    min_samples=3,
    schedule=None,
    auto_optimize=False,
    max_cost_usd=1.0,
)
class ThreeFormBot:
    """Test bot covering param/return/docstring text sources."""

    # Form 1: text=... param wins
    @evolvable_prompt(id="system", text="You are FORM-1.", max_chars=2000)
    def system_prompt(self) -> str:
        return self._evolved_system or "fallback"

    # Form 2: function return value (no args, single literal)
    @evolvable_prompt(id="planner")
    def planner_prompt(self) -> str:
        return "Plan FORM-2 carefully."

    # Form 3: docstring
    @evolvable_tool(id="searcher", max_chars=500)
    def search(self, query: str):
        """FORM-3: search the web for the query."""
        return f"results({query})"

    def __init__(self):
        self._evolved_system = None

    def run(self, q: str) -> str:
        return f"echo: {q}"
