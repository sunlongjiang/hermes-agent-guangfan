"""Seed high-quality traces for the commit-msg-bot dogfood.

The default `bot.run()` produces dumb pattern-matched output that gives
the judge no signal to distinguish good vs bad prompts. This script
writes traces directly with hand-crafted "ideal" commit messages as the
expected_output, so the judge can score candidate prompts against
genuine targets.

Usage:
    EVOLUTION_HOME=/tmp/dogfood_evolution_home \
    PYTHONPATH=. python examples/commit_msg_bot/seed_traces.py
"""

import hashlib
from evolution.sdk.trace_sink import LocalJsonlSink, TraceRecord


# (diff, ideal_commit_message) pairs spanning feat / fix / docs / refactor / test / chore.
SEED_PAIRS = [
    (
        "diff --git a/auth/sdk.py b/auth/sdk.py\n+++ b/auth/sdk.py\n+def login(user, password):\n+    return authenticate(user, password)",
        "feat(auth): add login helper wrapping authenticate()",
    ),
    (
        "diff --git a/tests/test_auth.py b/tests/test_auth.py\n+++ b/tests/test_auth.py\n+def test_login_rejects_bad_password():\n+    assert not login('u', 'wrong')",
        "test(auth): cover rejection of bad password",
    ),
    (
        "diff --git a/README.md b/README.md\n+++ b/README.md\n+## Authentication\n+Use login() to authenticate users.",
        "docs(readme): document authentication usage",
    ),
    (
        "diff --git a/src/parser.py b/src/parser.py\n-    return tokens[0]\n+    return tokens[0] if tokens else None",
        "fix(parser): handle empty tokens list",
    ),
    (
        "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n+      - run: pytest -v",
        "chore(ci): add verbose pytest run",
    ),
    (
        "diff --git a/src/api.py b/src/api.py\n+def list_users(limit=20, offset=0):\n+    return db.query(User).limit(limit).offset(offset).all()",
        "feat(api): add paginated list_users endpoint",
    ),
    (
        "diff --git a/src/db.py b/src/db.py\n-    conn = sqlite3.connect(path)\n+    conn = sqlite3.connect(path, timeout=30)",
        "fix(db): add 30s timeout to prevent lock errors",
    ),
    (
        "diff --git a/docs/setup.md b/docs/setup.md\n+## Quick start\n+Run python -m myapp init.",
        "docs(setup): add quick start instructions",
    ),
    (
        "diff --git a/src/cache.py b/src/cache.py\n+@lru_cache(maxsize=128)\n+def get_user(uid):\n+    return User.objects.get(id=uid)",
        "perf(cache): memoize get_user with lru_cache",
    ),
    (
        "diff --git a/src/utils.py b/src/utils.py\n-def slugify(text): return text.lower().replace(' ', '-')\n+def slugify(text):\n+    return re.sub(r'[^a-z0-9-]', '', text.lower().replace(' ', '-'))",
        "refactor(utils): strip non-alphanumerics in slugify",
    ),
    (
        "diff --git a/src/email.py b/src/email.py\n+def send_welcome(user):\n+    return mailer.send(user.email, template='welcome')",
        "feat(email): add welcome email sender",
    ),
    (
        "diff --git a/src/payment.py b/src/payment.py\n-    amount = float(req.amount)\n+    amount = Decimal(req.amount)",
        "fix(payment): use Decimal to avoid float precision loss",
    ),
    (
        "diff --git a/.gitignore b/.gitignore\n+.venv/\n+__pycache__/",
        "chore(gitignore): ignore venv and pycache",
    ),
    (
        "diff --git a/src/logger.py b/src/logger.py\n-import logging\n-logger = logging.getLogger('app')\n+import structlog\n+logger = structlog.get_logger()",
        "refactor(logger): migrate to structlog",
    ),
    (
        "diff --git a/tests/test_payment.py b/tests/test_payment.py\n+def test_decimal_precision():\n+    assert process(Decimal('0.1') + Decimal('0.2')) == Decimal('0.3')",
        "test(payment): verify Decimal precision in process()",
    ),
    (
        "diff --git a/src/server.py b/src/server.py\n-app.run(host='0.0.0.0')\n+app.run(host='127.0.0.1')",
        "fix(server): bind to localhost instead of all interfaces",
    ),
    (
        "diff --git a/CHANGELOG.md b/CHANGELOG.md\n+## 1.2.0\n+- Added pagination to list_users",
        "docs(changelog): note pagination addition for 1.2.0",
    ),
    (
        "diff --git a/src/cli.py b/src/cli.py\n+@click.option('--verbose', is_flag=True)\n+def main(verbose):\n+    pass",
        "feat(cli): add --verbose flag to main command",
    ),
    (
        "diff --git a/src/auth.py b/src/auth.py\n-def authenticate(u, p):\n+def authenticate(username: str, password: str) -> bool:",
        "refactor(auth): add type hints to authenticate()",
    ),
    (
        "diff --git a/pyproject.toml b/pyproject.toml\n-version = '1.1.0'\n+version = '1.2.0'",
        "chore(release): bump version to 1.2.0",
    ),
]


def main() -> None:
    sink = LocalJsonlSink()
    baseline_hashes = {
        "system": "sha256:" + hashlib.sha256(
            "You are an expert engineer. Read the diff and produce ONE conventional commit message line. Format: <type>(<scope>): <subject>. Subject must be imperative mood and under 72 chars.".encode()
        ).hexdigest(),
        "few_shot_header": "sha256:" + hashlib.sha256(
            "Here are example commits in this codebase. Match their style.".encode()
        ).hexdigest(),
        "diff_classifier": "sha256:" + hashlib.sha256(
            "Classify the diff into one of: feat, fix, docs, refactor, test, chore.\nInspect the file paths and the nature of the changes.".encode()
        ).hexdigest(),
    }
    artifacts = [
        {"id": "system", "kind": "prompt", "text_hash": baseline_hashes["system"]},
        {"id": "few_shot_header", "kind": "prompt", "text_hash": baseline_hashes["few_shot_header"]},
        {"id": "diff_classifier", "kind": "tool", "text_hash": baseline_hashes["diff_classifier"]},
    ]
    for diff, ideal in SEED_PAIRS:
        rec = TraceRecord(
            agent="commit-msg-bot",
            agent_version="0.1.0",
            input={"q": diff},
            output=ideal,
            artifacts=artifacts,
            tool_calls=[],
        )
        sink.write(rec)
    print(f"wrote {len(SEED_PAIRS)} high-quality traces")


if __name__ == "__main__":
    main()
