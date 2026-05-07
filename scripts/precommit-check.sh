#!/usr/bin/env bash
# Pre-commit guard — refuses to commit `evolution.yaml` since it may contain
# real API keys. Install as a git pre-commit hook:
#
#   ln -s ../../scripts/precommit-check.sh .git/hooks/pre-commit
#
# Or copy into your local hooks dir. Safe to run manually any time:
#
#   bash scripts/precommit-check.sh

set -euo pipefail

# Files staged for commit (cached index, name-only, no renames tracked)
STAGED=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null || true)

# Hard-refuse: evolution.yaml should NEVER be committed
if echo "$STAGED" | grep -Eq '^evolution\.yaml$'; then
    echo "❌ ERROR: Refusing to commit evolution.yaml"
    echo
    echo "   This file is .gitignored because it holds API keys."
    echo "   If you really need to commit it, unstage and force:"
    echo "     git restore --staged evolution.yaml"
    echo "     git add -f evolution.yaml    # ← explicit override, do not do this"
    echo
    echo "   Prefer: put secrets in env vars, reference them as \${VAR}"
    echo "   in evolution.yaml. See evolution.example.yaml for pattern."
    exit 1
fi

# Soft-warn: check for literal LLM keys in ANY staged file
LITERAL_KEY_RE='(sk-[A-Za-z0-9_-]{20,}|sk_(live|test)_[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})'
LEAKED=$(git diff --cached -U0 -- | grep -E "^\+" | grep -E "$LITERAL_KEY_RE" || true)

if [ -n "$LEAKED" ]; then
    echo "❌ ERROR: Staged diff contains literal API key patterns:"
    echo
    echo "$LEAKED" | head -5
    echo
    echo "   If this is a test fixture / docs placeholder, either:"
    echo "     - use a clearly-fake value (sk-FAKE-..., sk-XXXX...)"
    echo "     - add a '# pragma: allowlist secret' comment inline"
    echo "     - skip this hook: git commit --no-verify  (not recommended)"
    exit 1
fi

echo "✓ precommit-check.sh: no secrets detected in staged diff"
