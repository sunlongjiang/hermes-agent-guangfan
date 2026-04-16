---
phase: 4
slug: tool-dataset-evaluation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-16
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/tools/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/tools/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | TOOL-05 | — | N/A | unit | `python -m pytest tests/tools/test_tool_metric.py -q` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | TOOL-06 | — | N/A | unit | `python -m pytest tests/tools/test_tool_dataset.py -q` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | TOOL-07 | — | N/A | unit | `python -m pytest tests/tools/test_tool_dataset.py::test_confuser -q` | ❌ W0 | ⬜ pending |
| 04-01-04 | 01 | 1 | TOOL-08 | — | N/A | unit | `python -m pytest tests/tools/test_tool_metric.py::test_regression -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/tools/test_tool_metric.py` — stubs for TOOL-05, TOOL-08
- [ ] `tests/tools/test_tool_dataset.py` — stubs for TOOL-06, TOOL-07

*Existing infrastructure covers pytest framework requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
