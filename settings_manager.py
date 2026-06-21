"""
settings_manager.py — Runtime settings stored in Supabase.
Lets you add/change API keys from the Dashboard — no redeploy needed.

Falls back to environment variables if a setting isn't in the database yet,
so existing env-var based deployments keep working unchanged.
"""
import os, time
from db_clients import sb

_cache = {}
_cache_time = 0
_CACHE_TTL = 30  # seconds — dashboard changes apply within 30s, no restart needed

def _load_all() -> dict:
    global _cache, _cache_time
    now = time.time()
    if now - _cache_time < _CACHE_TTL and _cache:
        return _cache
    try:
        r = sb.table("app_settings").select("key,value").execute()
        rows = r.data or []
        _cache = {row["key"]: row["value"] for row in rows}
        _cache_time = now
    except Exception as e:
        print(f"settings_manager: could not load settings ({e})")
    return _cache

def get_setting(key: str, default=None):
    """Check database first, then environment variable, then default."""
    settings = _load_all()
    if key in settings and settings[key]:
        return settings[key]
    env_val = os.getenv(key)
    if env_val:
        return env_val
    return default

def set_setting(key: str, value: str):
    global _cache, _cache_time
    try:
        sb.table("app_settings").upsert({"key": key, "value": value}).execute()
        _cache[key] = value  # update cache immediately
        return True
    except Exception as e:
        print(f"settings_manager: could not save {key} ({e})")
        return False

def delete_setting(key: str):
    global _cache
    try:
        sb.table("app_settings").delete().eq("key", key).execute()
        _cache.pop(key, None)
        return True
    except Exception as e:
        print(f"settings_manager: could not delete {key} ({e})")
        return False

def get_all_settings() -> dict:
    """Returns all settings with values masked for display."""
    settings = _load_all()
    result = {}
    for key, value in settings.items():
        if value and len(value) > 8:
            result[key] = value[:4] + "••••" + value[-4:]
        elif value:
            result[key] = "••••"
        else:
            result[key] = ""
    return result

# Keys that can be configured from the dashboard
CONFIGURABLE_KEYS = [
    {"key": "GROQ_API_KEY",       "label": "Groq API Key",        "group": "AI Providers", "help": "console.groq.com → API Keys"},
    {"key": "GEMINI_API_KEY",     "label": "Gemini API Key",      "group": "AI Providers", "help": "aistudio.google.com → Get API Key"},
    {"key": "OPENROUTER_API_KEY", "label": "OpenRouter API Key",  "group": "AI Providers", "help": "openrouter.ai → Keys"},
    {"key": "COHERE_API_KEY",     "label": "Cohere API Key",      "group": "AI Providers", "help": "dashboard.cohere.com → API Keys"},
    {"key": "TURSO_URL",          "label": "Turso Database URL",  "group": "Long-term Memory", "help": "turso.tech → your database → URL"},
    {"key": "TURSO_TOKEN",        "label": "Turso Auth Token",    "group": "Long-term Memory", "help": "turso.tech → your database → Generate Token"},
    {"key": "SUPABASE_MAX_MB",    "label": "Memory Alert Threshold (MB)", "group": "Memory Settings", "help": "Default: 450"},
    {"key": "MEMORY_WARN_PERCENT",   "label": "Warning Alert %",  "group": "Memory Settings", "help": "Default: 80"},
    {"key": "MEMORY_URGENT_PERCENT", "label": "Urgent Alert %",   "group": "Memory Settings", "help": "Default: 95"},
]
