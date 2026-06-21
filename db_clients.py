"""
db_clients.py — Lightweight Supabase REST client using plain httpx.

Why not the official `supabase` package: its `gotrue` auth dependency has a
known version-conflict bug (TypeError: Client.__init__() got an unexpected
keyword argument 'proxy') that triggers depending on exactly which httpx
version gets resolved — and python-telegram-bot also pins httpx, so the two
fight each other. We don't need auth, realtime, or storage here — only
simple table reads/writes — so this talks to Supabase's PostgREST HTTP API
directly. No gotrue, no proxy bug possible, far fewer moving parts.

Supports the exact subset of the query-builder chain this project uses:
.select() .insert() .update() .upsert() .delete() .eq() .order() .limit()
.execute() .rpc()

Import `sb` from here everywhere instead of creating a client inline.
"""
import os, json
import httpx

_REQUEST_TIMEOUT = 15.0


class _Result:
    """Mimics supabase-py's execute() result shape: .data and .count"""
    def __init__(self, data=None, count=0):
        self.data = data or []
        self.count = count


class _NullQuery:
    """No-op query — used when Supabase isn't configured. Never raises."""
    def __getattr__(self, name):
        def _method(*a, **kw):
            return self
        return _method

    def execute(self):
        return _Result()


class _Query:
    """Minimal PostgREST query builder — chainable, matches supabase-py's shape."""

    def __init__(self, base_url: str, headers: dict, table: str):
        self._base_url = base_url
        self._headers = dict(headers)
        self._table = table
        self._method = "GET"
        self._params = {}
        self._body = None
        self._select_count = None

    def select(self, columns: str = "*", count: str = None):
        self._method = "GET"
        self._params["select"] = columns
        if count:
            self._select_count = count
            self._headers["Prefer"] = f"count={count}"
        return self

    def insert(self, row):
        self._method = "POST"
        self._body = row
        self._headers["Prefer"] = "return=representation"
        return self

    def update(self, row):
        self._method = "PATCH"
        self._body = row
        self._headers["Prefer"] = "return=representation"
        return self

    def upsert(self, row):
        self._method = "POST"
        self._body = row
        self._headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        return self

    def delete(self):
        self._method = "DELETE"
        self._headers["Prefer"] = "return=representation"
        return self

    def eq(self, column: str, value):
        self._params[column] = f"eq.{value}"
        return self

    def order(self, column: str, desc: bool = False):
        self._params["order"] = f"{column}.{'desc' if desc else 'asc'}"
        return self

    def limit(self, n: int):
        self._params["limit"] = str(n)
        return self

    def execute(self):
        url = f"{self._base_url}/rest/v1/{self._table}"
        try:
            with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
                if self._method == "GET":
                    resp = client.get(url, headers=self._headers, params=self._params)
                elif self._method == "POST":
                    resp = client.post(url, headers=self._headers, params=self._params,
                                        content=json.dumps(self._body))
                elif self._method == "PATCH":
                    resp = client.patch(url, headers=self._headers, params=self._params,
                                         content=json.dumps(self._body))
                elif self._method == "DELETE":
                    resp = client.delete(url, headers=self._headers, params=self._params)
                else:
                    return _Result()

            if resp.status_code >= 400:
                print(f"⚠️  Supabase REST error ({self._table}, {self._method}): "
                      f"{resp.status_code} {resp.text[:200]}")
                return _Result()

            count = 0
            if self._select_count:
                content_range = resp.headers.get("content-range", "")
                if "/" in content_range:
                    total = content_range.split("/")[-1]
                    count = int(total) if total.isdigit() else 0

            data = resp.json() if resp.content else []
            if not isinstance(data, list):
                data = [data] if data else []
            return _Result(data=data, count=count)

        except Exception as e:
            print(f"⚠️  Supabase REST request failed ({self._table}): {e}")
            return _Result()


class _RpcCall:
    """Chainable RPC call — supports .execute() to match supabase-py's shape."""
    def __init__(self, base_url: str, headers: dict, fn_name: str, params: dict):
        self._base_url = base_url
        self._headers = headers
        self._fn_name = fn_name
        self._params = params

    def execute(self):
        url = f"{self._base_url}/rest/v1/rpc/{self._fn_name}"
        try:
            with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
                resp = client.post(url, headers=self._headers, content=json.dumps(self._params))
            if resp.status_code >= 400:
                print(f"⚠️  Supabase RPC error ({self._fn_name}): {resp.status_code} {resp.text[:200]}")
                return _Result()
            data = resp.json() if resp.content else None
            return _Result(data=data)
        except Exception as e:
            print(f"⚠️  Supabase RPC request failed ({self._fn_name}): {e}")
            return _Result()


class _SupabaseRestClient:
    """Drop-in replacement for the bits of supabase-py's Client this project uses."""

    def __init__(self, url: str, key: str):
        self._base_url = url.rstrip("/")
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def table(self, name: str) -> _Query:
        return _Query(self._base_url, self._headers, name)

    def rpc(self, fn_name: str, params: dict = None):
        return _RpcCall(self._base_url, self._headers, fn_name, params or {})


_sb_instance = None

def get_supabase():
    """Returns the REST client, or None if not configured. Never raises."""
    global _sb_instance
    if _sb_instance is not None:
        return _sb_instance
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("⚠️  SUPABASE_URL or SUPABASE_KEY not set — memory/dashboard features disabled.")
        return None
    try:
        _sb_instance = _SupabaseRestClient(url, key)
        return _sb_instance
    except Exception as e:
        print(f"⚠️  Supabase connection failed: {e}")
        return None


class _SafeSupabaseProxy:
    """Lets code call sb.table(...) safely even if not configured — no-ops instead of crashing."""
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

sb = _SafeSupabaseProxy()
