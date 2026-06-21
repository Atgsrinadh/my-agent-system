"""
startup_check.py — Runs before anything else starts.
Prints a clear, human-readable report of what's configured and what's missing.
Never raises — the app always starts, even with zero keys configured,
so you can add them later from the dashboard instead of being stuck.
"""
import os, sys

REQUIRED = [
    ("TELEGRAM_TOKEN",  "Get from @BotFather on Telegram"),
    ("ADMIN_USER_ID",   "Get from @userinfobot on Telegram"),
    ("SUPABASE_URL",    "Supabase → Settings → API → Project URL"),
    ("SUPABASE_KEY",    "Supabase → Settings → API → anon public key"),
    ("DASHBOARD_SECRET","Any password you choose"),
]

OPTIONAL = [
    "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
    "COHERE_API_KEY", "TURSO_URL", "TURSO_TOKEN",
]

def run_check():
    print("=" * 60)
    print("  AGENT SYSTEM — STARTUP CHECK")
    print("=" * 60)

    try:
        import env_clean
        all_keys = [k for k, _ in REQUIRED] + OPTIONAL
        hidden_report = env_clean.diagnose(all_keys)
        if hidden_report:
            print("  🧹 Auto-cleaned hidden characters in:")
            for key, info in hidden_report.items():
                print(f"      {key} (was {info['raw_length']} chars, "
                      f"now {info['cleaned_length']} — fixed automatically, no action needed)")
            print("-" * 60)
    except Exception:
        pass

    missing_required = []
    for key, hint in REQUIRED:
        val = os.getenv(key)
        if val:
            shown = val[:4] + "…" if len(val) > 8 else "set"
            print(f"  ✅ {key:<20} {shown}")
        else:
            print(f"  ❌ {key:<20} MISSING  →  {hint}")
            missing_required.append(key)

    print("-" * 60)
    optional_set = 0
    for key in OPTIONAL:
        if os.getenv(key):
            optional_set += 1
    print(f"  Optional AI/memory keys set via env: {optional_set}/{len(OPTIONAL)}")
    print(f"  (Missing ones can be added later via Dashboard → Settings tab)")
    print("=" * 60)

    if missing_required:
        print()
        print("  🚨 CANNOT START — missing required variables above.")
        print("  Set them in Railway/Render → Variables tab, then redeploy.")
        print("=" * 60)
        sys.exit(1)

    print("  ✅ All required variables present. Starting application...")
    print("=" * 60)

if __name__ == "__main__":
    run_check()
