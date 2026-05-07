---
created: 2026-05-07T07:53:18Z
title: Expand SECRET_PATTERNS coverage for Phase 14 mining
area: security
files:
  - evolution/core/external_importers.py:45-70
  - evolution/core/external_importers.py:78-80
---

## Problem

Current `SECRET_PATTERNS` coverage is regex-only and pattern-shallow. Gaps verified against v2 research Pitfall 2:

- **JWT regex missing**: no `eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+` pattern — `Bearer\s+\S{20,}` only catches JWTs preceded by literal `Bearer `.
- **OAuth bearer with non-standard prefix** not caught.
- **Internal hostnames, employee names, customer IDs** (PII per Pitfall 2) not detected at all.
- **Generic high-entropy tokens** (32+ char base64) not detected.
- **NER-based PII** (PERSON, ORG, EMAIL, PHONE, IP) requires `spacy`/Presidio — not in deps.

Phase 14 SessionDB mining (TOOL-V2-01) drastically expands the surface. Today's gate is sufficient for skill mining (small surface) but undersized for v2 behavioral mining.

## Solution

Layered defense per Pitfall 2 prevention strategy:
- **Layer 1:** Add JWT pattern, AWS-secret pattern (`[a-zA-Z0-9/+=]{40}` adjacent to `aws`), and Shannon entropy heuristic (> 4.0 over 24+ char tokens).
- **Layer 2 (NER):** Introduce `evolution/core/privacy.py` with optional `spacy` / Presidio dependency. Gate behind `[project.optional-dependencies].privacy`.
- **Layer 3:** Add `--i-have-consent` flag to importers (BEFORE any read).
- **Layer 4:** Sanitization audit step — LLM check "does this dataset contain PII or secrets?" as part of Phase 14 build pipeline.

**Priority:** MED. **Phase 14 blocker.** Source: `.planning/codebase/CONCERNS.md` M5.
