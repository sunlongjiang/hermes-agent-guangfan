---
phase: 07
slug: prompt-loading
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-16
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest tests/prompts/ -x -q` |
| **Full suite command** | `.venv/bin/python -m pytest tests/prompts/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/prompts/ -x -q`
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/prompts/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | PMPT-01 | — | N/A | unit | `.venv/bin/python -m pytest tests/prompts/test_prompt_loader.py -v` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | PMPT-02 | — | N/A | unit | `.venv/bin/python -m pytest tests/prompts/test_prompt_loader.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/prompts/__init__.py` — package init
- [ ] `tests/prompts/test_prompt_loader.py` — stubs for PMPT-01, PMPT-02

*Existing pytest infrastructure covers framework requirements.*

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
