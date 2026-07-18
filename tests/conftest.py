"""Shared test setup.

Provides synthetic (non-secret) values for the configuration fields that
have no default — FPE_KEY, SESSION_TTL, FAIL_MODE — before any test
module is collected. app/main.py constructs Settings at import time, so
these must exist before the *first* import of app.main in this process,
not inside a fixture that runs later. Using `setdefault` means a
developer's real `.env` (if present) is never overridden.

These are placeholder strings for satisfying required-field validation
in tests, not secrets — the same reasoning that lets `.env.example`
itself be committed (CLAUDE.md, "Secrets only in .env").
"""

import os

os.environ.setdefault("FPE_KEY", "test-fpe-key-not-a-real-secret")
os.environ.setdefault("SESSION_TTL", "1800")
os.environ.setdefault("FAIL_MODE", "closed")
