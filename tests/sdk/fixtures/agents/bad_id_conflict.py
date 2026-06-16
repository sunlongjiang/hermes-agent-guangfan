"""Agent fixture demonstrating duplicate artifact id (must raise at import)."""
from evolution.sdk.decorators import evolvable_agent, evolvable_prompt


@evolvable_agent(name="bad-id-bot", version="0.1.0", min_samples=3,
                 schedule=None, auto_optimize=False, max_cost_usd=1.0)
class BadIdBot:
    @evolvable_prompt(id="same", text="A")
    def a(self) -> str:
        return "A"

    @evolvable_prompt(id="same", text="B")  # duplicate id within same agent
    def b(self) -> str:
        return "B"

    def run(self, q):
        return q
