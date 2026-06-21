"""
db_clients.py — Safe, shared database client creation.
Prevents crash-on-startup if env vars are missing/wrong.
Import sb from here everywhere instead of creating it inline.
"""
import os
from supabase import create_client

_sb = None

def get_supabase():
    """Returns Supabase client, or None if not configured. Never raises."""
    global _sb
    if _sb is not None:
        return _sb
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("⚠️  SUPABASE_URL or SUPABASE_KEY not set — memory/dashboard features disabled.")
        return None
    try:
        _sb = create_client(url, key)
        return _sb
    except Exception as e:
        print(f"⚠️  Supabase connection failed: {e}")
        return None

class _SafeSupabaseProxy:
    """Lets code call sb.table(...) safely even if sb is None — returns dummy that no-ops."""
    def table(self, *a, **kw):
        client = get_supabase()
        if client is None:
            return _NullQuery()
        return client.table(*a, **kw)

    def rpc(self, *a, **kw):
        client = get_supabase()
        if client is None:
            return _NullQuery()
        return client.rpc(*a, **kw)

class _NullQuery:
    """No-op query object — every chained call returns self, execute() returns empty."""
    def __getattr__(self, name):
        def _method(*a, **kw):
            return self
        return _method

    def execute(self):
        class _Result:
            data = []
            count = 0
        return _Result()

sb = _SafeSupabaseProxy()
