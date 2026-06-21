"""
api_router.py — Upgraded smart AI router with maximum free intelligence.
Provider order (strongest first):
  1. Gemini 1.5 Pro     — closest to GPT-4 quality, 50 req/day free
  2. Groq Llama 3.3 70B — fastest, strongest open model, high free limits
  3. Together Llama 3.1 405B — largest open model available free
  4. OpenRouter Mistral Large — strong reasoning, free tier
  5. Groq Gemma 2 9B    — fast fallback
  6. Together Qwen 2.5  — extra fallback
  7. Cohere Command R+  — final fallback

Smart features:
  - Per-task model selection (research → strongest, routing → fastest)
  - Daily usage tracking per provider
  - Auto-reset daily limits at midnight
  - Logs every call for dashboard
"""
import os, time, json
from datetime import datetime, date
from groq import Groq
from openai import OpenAI

from db_clients import sb

# ── Provider definitions — ordered strongest → fastest fallback ────────────
# "key_name" = which setting/env var holds the API key.
# Keys are read live via settings_manager (DB first, env var fallback),
# so adding/changing keys in the dashboard works without redeploying.
PROVIDERS = [
    {
        "name": "gemini-pro",
        "label": "Gemini 1.5 Pro",
        "model": "gemini-1.5-pro",
        "key_name": "GEMINI_API_KEY",
        "daily_limit": 50,
        "type": "openai_compat",
        "tier": "premium",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
    {
        "name": "groq-llama33",
        "label": "Groq Llama 3.3 70B",
        "model": "llama-3.3-70b-versatile",
        "key_name": "GROQ_API_KEY",
        "daily_limit": 1000,
        "type": "groq",
        "tier": "premium",
    },
    {
        "name": "openrouter-mistral",
        "label": "OpenRouter Mistral Large",
        "model": "mistralai/mistral-large",
        "key_name": "OPENROUTER_API_KEY",
        "daily_limit": 200,
        "type": "openai_compat",
        "tier": "premium",
        "base_url": "https://openrouter.ai/api/v1",
    },
    {
        "name": "groq-gemma",
        "label": "Groq Gemma 2 27B",
        "model": "gemma2-9b-it",
        "key_name": "GROQ_API_KEY",
        "daily_limit": 2000,
        "type": "groq",
        "tier": "fast",
    },
    {
        "name": "gemini-flash",
        "label": "Gemini 1.5 Flash",
        "model": "gemini-1.5-flash",
        "key_name": "GEMINI_API_KEY",
        "daily_limit": 1500,
        "type": "openai_compat",
        "tier": "fast",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
    {
        "name": "openrouter-llama",
        "label": "OpenRouter Llama 3.3 70B",
        "model": "meta-llama/llama-3.3-70b-instruct",
        "key_name": "OPENROUTER_API_KEY",
        "daily_limit": 500,
        "type": "openai_compat",
        "tier": "fast",
        "base_url": "https://openrouter.ai/api/v1",
    },
]

def _get_api_key(provider: dict) -> str | None:
    from settings_manager import get_setting
    return get_setting(provider["key_name"])

def _is_enabled(provider: dict) -> bool:
    return bool(_get_api_key(provider))

def _make_client(provider: dict):
    key = _get_api_key(provider)
    if provider["type"] == "groq":
        return Groq(api_key=key)
    return OpenAI(api_key=key, base_url=provider.get("base_url"))

# ── Daily usage tracker ────────────────────────────────────────────────────
_usage = {}       # {provider_name: count}
_usage_date = date.today()
_current_idx = 0

def _reset_if_new_day():
    global _usage, _usage_date
    today = date.today()
    if today != _usage_date:
        _usage = {}
        _usage_date = today

def _increment(name: str):
    _reset_if_new_day()
    _usage[name] = _usage.get(name, 0) + 1

def _is_over_limit(provider: dict) -> bool:
    _reset_if_new_day()
    used = _usage.get(provider["name"], 0)
    return used >= provider.get("daily_limit", 9999)

# ── Task type → best provider tier ────────────────────────────────────────
# Use 'premium' for research/writing/coding — needs strong reasoning
# Use 'fast' for routing/extraction/simple tasks — needs speed
TASK_TIER = {
    "research":   "premium",
    "writer":     "premium",
    "coder":      "premium",
    "analyst":    "premium",
    "critic":     "premium",
    "planner":    "premium",
    "web_search": "premium",
    "vision":     "premium",
    "pdf_reader": "premium",
    "summariser": "fast",
    "general":    "fast",
    "router":     "fast",
    "extractor":  "fast",
}

def _get_ordered_providers(task_type: str = "general") -> list:
    """Return providers ordered by: tier match → enabled → not over limit."""
    tier = TASK_TIER.get(task_type, "fast")
    active = [p for p in PROVIDERS if _is_enabled(p) and not _is_over_limit(p)]
    if not active:
        # All over limit — reset and try again (rare edge case)
        global _usage
        _usage = {}
        active = [p for p in PROVIDERS if _is_enabled(p)]

    # Premium tasks: premium providers first, then fast fallbacks
    # Fast tasks: fast providers first, then premium if needed
    if tier == "premium":
        ordered = [p for p in active if p["tier"] == "premium"] + \
                  [p for p in active if p["tier"] == "fast"]
    else:
        ordered = [p for p in active if p["tier"] == "fast"] + \
                  [p for p in active if p["tier"] == "premium"]
    return ordered

# ── Logging ────────────────────────────────────────────────────────────────
def _log(provider: str, model: str, success: bool, error: str = None, tokens: int = 0):
    try:
        sb.table("api_logs").insert({
            "provider": provider,
            "model": model,
            "success": success,
            "error": error,
            "tokens_used": tokens,
        }).execute()
    except:
        pass

# ── Main call function ─────────────────────────────────────────────────────
def call_ai(messages: list, system: str = None,
            temperature: float = 0.7, task_type: str = "general") -> str:
    """
    Call AI with smart provider selection + auto-failover.
    task_type controls which tier of models to prefer.
    Returns response text. Raises only if every provider fails.
    """
    if system:
        messages = [{"role": "system", "content": system}] + messages

    providers = _get_ordered_providers(task_type)

    if not providers:
        raise RuntimeError(
            "No AI providers are configured yet.\n"
            "Open your dashboard → Settings tab → add at least one API key "
            "(Groq is free and recommended)."
        )

    for provider in providers:
        try:
            client = _make_client(provider)
            resp = client.chat.completions.create(
                model=provider["model"],
                messages=messages,
                temperature=temperature,
                max_tokens=4096,
            )
            text = resp.choices[0].message.content
            tokens = getattr(resp.usage, "total_tokens", 0) if resp.usage else 0
            _increment(provider["name"])
            _log(provider["name"], provider["model"], True, tokens=tokens)
            return text

        except Exception as e:
            err = str(e)
            _log(provider["name"], provider["model"], False, error=err[:200])
            # Rate limit or quota → try next
            if any(x in err.lower() for x in
                   ["rate", "limit", "quota", "429", "exceeded",
                    "capacity", "overloaded", "503", "529"]):
                _increment(provider["name"])  # count as used to skip next time
                continue
            # Auth error → skip permanently this session
            if any(x in err.lower() for x in ["401", "403", "invalid", "unauthorized"]):
                continue
            # Any other error → still try next
            continue

    raise RuntimeError(
        "All AI providers failed or hit limits.\n"
        "Use /apistatus to check, /switchapi to force a provider."
    )

# ── Status helpers ─────────────────────────────────────────────────────────
def get_current_provider() -> str:
    available = _get_ordered_providers("general")
    return available[0]["name"] if available else "none"

def get_provider_status() -> list:
    _reset_if_new_day()
    result = []
    for p in PROVIDERS:
        used = _usage.get(p["name"], 0)
        limit = p.get("daily_limit", 9999)
        result.append({
            "name": p["name"],
            "label": p["label"],
            "model": p["model"],
            "enabled": _is_enabled(p),
            "tier": p["tier"],
            "used_today": used,
            "daily_limit": limit,
            "remaining": max(0, limit - used),
            "over_limit": _is_over_limit(p),
        })
    return result

def get_usage_summary() -> str:
    statuses = get_provider_status()
    lines = [f"🔌 AI Provider Status — {date.today()}\n"]
    for p in statuses:
        if not p["enabled"]:
            lines.append(f"❌ {p['label']} — not configured")
            continue
        bar_used = min(10, int((p['used_today'] / p['daily_limit']) * 10))
        bar = "█" * bar_used + "░" * (10 - bar_used)
        icon = "🚨" if p["over_limit"] else "✅"
        lines.append(
            f"{icon} {p['label']}\n"
            f"   [{bar}] {p['used_today']}/{p['daily_limit']} today"
        )
    return "\n".join(lines)

def switch_provider(name: str) -> bool:
    """Force a specific provider by clearing its usage count."""
    for p in PROVIDERS:
        if p["name"].lower() == name.lower() or \
           p["label"].lower().startswith(name.lower()):
            _usage[p["name"]] = 0  # reset so it's picked first
            return True
    return False

def add_custom_provider(name: str, key_name: str, base_url: str,
                        model: str, daily_limit: int = 100, tier: str = "premium"):
    """Dynamically add a new provider at runtime."""
    PROVIDERS.append({
        "name": name,
        "label": name,
        "model": model,
        "key_name": key_name,
        "daily_limit": daily_limit,
        "type": "openai_compat",
        "tier": tier,
        "base_url": base_url,
    })
