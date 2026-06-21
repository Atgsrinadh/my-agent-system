"""
env_clean.py — Bulletproof environment variable sanitizer.

WHY THIS EXISTS:
Copy-pasting tokens/keys into Render, Railway, or any host's web UI
frequently introduces invisible characters: trailing newlines, tabs,
zero-width spaces, non-breaking spaces, or leading/trailing whitespace.
These are invisible when you look at the value, but break libraries like
httpx that validate URLs/headers strictly — causing cryptic crashes like
"Invalid non-printable ASCII character in URL".

WHAT THIS DOES:
Monkey-patches os.getenv and os.environ.get at import time so EVERY
environment variable read ANYWHERE in this codebase — now and in any
future code — is automatically stripped of whitespace and non-printable
characters. This is a single chokepoint fix: no need to remember to
sanitize each variable individually in every file.

This must be imported FIRST, before any other project module, so the
patch is active before anything else reads an env var.
"""
import os
import unicodedata

_original_getenv = os.getenv
_original_environ_get = os.environ.get
_raw_snapshot = {}  # captured once, before apply() overwrites os.environ in place


def _clean(value):
    """Strip whitespace and non-printable/invisible Unicode characters."""
    if value is None:
        return value
    if not isinstance(value, str):
        return value
    cleaned = "".join(
        ch for ch in value
        if ch.isprintable() or ch in (" ",)
    )
    cleaned = cleaned.strip().strip("\u200b\u200c\u200d\ufeff\xa0")
    return cleaned


def _patched_getenv(key, default=None):
    raw = _original_getenv(key, default)
    return _clean(raw) if raw is not default else raw


def _patched_environ_get(key, default=None):
    raw = _original_environ_get(key, default)
    return _clean(raw) if raw is not default else raw


def apply():
    """Call once, as early as possible — patches os.getenv globally."""
    global _raw_snapshot
    if not _raw_snapshot:
        _raw_snapshot = dict(os.environ)
    os.getenv = _patched_getenv
    os.environ.get = _patched_environ_get
    for k in list(os.environ.keys()):
        os.environ[k] = _clean(os.environ[k])


def diagnose(keys: list) -> dict:
    """
    Returns a report of any variable that had invisible characters removed —
    useful for printing in startup_check so you can SEE if this saved you.
    """
    report = {}
    for key in keys:
        raw = _raw_snapshot.get(key)
        if raw is None:
            continue
        cleaned = _clean(raw)
        if raw != cleaned:
            report[key] = {
                "had_hidden_chars": True,
                "raw_length": len(raw),
                "cleaned_length": len(cleaned),
            }
    return report


apply()
