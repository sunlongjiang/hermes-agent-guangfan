---
phase: 5
slug: tool-constraints-cli
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-16
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/tools/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/tools/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | TOOL-09 | — | LLM factual check rejects false capabilities | unit | `python -m pytest tests/tools/test_tool_constraints.py -x -q` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | TOOL-10 | — | Size constraints reject oversized descriptions | unit | `python -m pytest tests/tools/test_tool_constraints.py -x -q` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | TOOL-11 | — | CLI runs end-to-end with all options | integration | `python -m pytest tests/tools/test_evolve_tool_descriptions.py -x -q` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 2 | TOOL-11 | — | Dry-run shows changes without writing | unit | `python -m pytest tests/tools/test_evolve_tool_descriptions.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/tools/test_tool_constraints.py` — stubs for TOOL-09, TOOL-10
- [ ] `tests/tools/test_evolve_tool_descriptions.py` — stubs for TOOL-11

*Existing infrastructure covers pytest setup and conftest.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GEPA optimization produces better descriptions | TOOL-11 | Requires LLM API calls and real hermes-agent repo | Run `python -m evolution.tools.evolve_tool_descriptions --dry-run` and verify output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
