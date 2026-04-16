---
phase: 2
slug: tool-loading
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-16
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/test_tool_loader.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_tool_loader.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | TOOL-01 | — | N/A | unit | `python -m pytest tests/test_tool_loader.py::test_extract_tool_descriptions -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | TOOL-01 | — | N/A | unit | `python -m pytest tests/test_tool_loader.py::test_extract_param_descriptions -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | TOOL-02 | — | N/A | unit | `python -m pytest tests/test_tool_loader.py::test_write_back_preserves_schema -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 1 | TOOL-01, TOOL-02 | — | N/A | integration | `python -m pytest tests/test_tool_loader.py::test_round_trip -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tool_loader.py` — stubs for TOOL-01, TOOL-02
- [ ] pytest installation verified in `.venv`

*Note: pytest is declared in pyproject.toml but may need installation verification in .venv*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Multi-format description parsing | TOOL-01 | Edge cases depend on actual hermes-agent file content | Visually inspect extracted descriptions for 3+ format types |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
