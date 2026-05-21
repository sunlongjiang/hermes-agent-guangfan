---
phase: 22-continuous-evolution-loop
plan: 02
status: complete
completed: 2026-05-21
key-files:
  created:
    - evolution.yaml.example
    - tests/test_loop_config.py
  modified:
    - evolution/core/config.py
---

# Plan 22-02 Summary — loop_cli_config schema (D-06 / D-08)

## Outcome

`EvolutionConfig.loop_cli_config` is the single source of truth that Plan 22-03's
`run_loop.py` will read to decide which `evolve_*` CLIs to dispatch and what
`--max-cost` to pass each one. Operators edit `evolution.yaml`'s `loop:` block
(or omit it entirely for safe defaults); no Python or GH Actions yaml change is
required to toggle a CLI.

## Schema

```python
LOOP_CLI_NAMES = (
    "skill",
    "tool_descriptions",
    "tool_params",
    "tool_reasoning",
    "prompt_sections",
    "code",
)  # D-07 canonical serial dispatch order — Plan 03 must preserve it

LOOP_DEFAULT_MAX_COST_USD = 5.0  # default cap when yaml omits the field

@dataclass
class EvolutionConfig:
    ...
    loop_cli_config: dict = field(default_factory=lambda: {
        name: {"enabled": True, "max_cost_usd": 5.0}
        for name in LOOP_CLI_NAMES
    })
```

Yaml shape:

```yaml
loop:
  cli:
    <cli_name>:
      enabled: true | false
      max_cost_usd: <float>
```

## Behavior contract (Plan 03 will consume)

| Scenario | Result |
|----------|--------|
| `loop:` section absent | All 6 CLIs enabled, each capped at $5.0 |
| `loop.cli.skill.max_cost_usd: 3.0` only | skill cap = 3.0, skill enabled still True, other 5 CLIs untouched |
| `loop.cli.tool_reasoning.enabled: false` | tool_reasoning skipped; everyone else stays default |
| `loop.cli.<unknown>: ...` | stderr warning, entry kept in dict (Plan 03 will skip it) |
| `enabled: "yes"` (non-bool) | stderr warning, falls back to True |
| `max_cost_usd: "five"` (non-float) | stderr warning, falls back to 5.0 |
| Whole `loop.cli` non-dict | stderr warning, entire loop section ignored |

## How Plan 03 consumes this

`run_loop.py` will iterate `LOOP_CLI_NAMES` (preserving D-07 order) and for each:

```python
for cli_name in LOOP_CLI_NAMES:
    cfg = config.loop_cli_config.get(cli_name, {"enabled": True, "max_cost_usd": 5.0})
    if not cfg.get("enabled", True):
        continue  # D-06 subset switch
    max_cost = cfg.get("max_cost_usd", 5.0)
    subprocess.run([
        "python", "-m", f"evolution.{<pkg-for-cli>}.evolve_{cli_name}",
        "--max-cost", str(max_cost),
        ...
    ])
```

## evolution.yaml gitignore deviation

The plan originally instructed appending a commented `loop:` block directly to
`evolution.yaml`. That file is gitignored (it carries the actual API key), so
the commit would silently drop the documentation. Resolution: created
**`evolution.yaml.example`** as the committed schema reference, with the same
commented `loop:` block plus a `${OPENAI_API_KEY}` placeholder. The real
`evolution.yaml` may still contain the same block for local use; it just isn't
the source of truth for the schema documentation.

## Verification

- 8/8 `tests/test_loop_config.py` PASS
- Full suite: **770 passed, 1 skipped, 1 xfailed in 58.56s** (no regression; +8 over Wave 1 merge baseline of 762)
- `grep -c "LOOP_CLI_NAMES" evolution/core/config.py` = 3 (constant + dataclass default-factory + load parse) ✓
- `grep -c "loop_cli_config" evolution/core/config.py` = 4 ✓
- `python -c "from evolution.core.config import LOOP_CLI_NAMES; assert LOOP_CLI_NAMES == ('skill','tool_descriptions','tool_params','tool_reasoning','prompt_sections','code')"` exits 0 ✓
- Default config exposes all 6 CLIs with enabled=True, max_cost_usd=5.0 ✓
- Partial yaml override only touches specified fields ✓
- `grep -c "^#.*max_cost_usd" evolution.yaml.example` = 6 (one per CLI) ✓

## Commits

- `e3e1400` feat(22-02): loop_cli_config schema + 8 unit tests + yaml template

## Unblocks

- **22-03** (Wave 3): `run_loop.py` imports `LOOP_CLI_NAMES` and reads
  `config.loop_cli_config` for dispatch decisions.

## Self-Check: PASSED

8/8 plan tests green. Full suite 770/770 green. Schema additive (no Phase 12+
yaml key collision). One documented deviation: evolution.yaml.example carries
the schema doc because evolution.yaml is gitignored.
