"""
memory/manager.py — 3-layer memory system.
Layer 1: Working memory  — fast JSON, in-server (rebuilt on restart)
Layer 2: Short-term      — Supabase Postgres, recent chats
Layer 3: Long-term       — Turso SQLite, permanent research findings

Smart alerts: notifies you on Telegram when memory exceeds threshold.
You decide when to clean — system never auto-deletes your data.
"""
import os, json, time
from db_clients import sb
from api_router import call_ai
from settings_manager import get_setting

# ── Clients ────────────────────────────────────────────────────────────────
WORKING_FILE = "/tmp/working_memory.json"

def _supabase_max_mb():
    return float(get_setting("SUPABASE_MAX_MB", 450))

def _warn_pct():
    return float(get_setting("MEMORY_WARN_PERCENT", 80))

def _urgent_pct():
    return float(get_setting("MEMORY_URGENT_PERCENT", 95))

# ── Turso setup ────────────────────────────────────────────────────────────
_turso_conn = None

def _get_turso():
    global _turso_conn
    if _turso_conn is None:
        from settings_manager import get_setting
        turso_url = get_setting("TURSO_URL")
        turso_token = get_setting("TURSO_TOKEN")
        if not turso_url or not turso_token:
            return None  # not configured yet — long-term memory disabled
        try:
            import libsql_experimental as libsql
            _turso_conn = libsql.connect(
                database=turso_url,
                auth_token=turso_token
            )
            _turso_conn.execute("""
                CREATE TABLE IF NOT EXISTS long_term (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    agent_id TEXT,
                    category TEXT,
                    key TEXT UNIQUE,
                    value TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            _turso_conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    name TEXT UNIQUE,
                    system_prompt TEXT,
                    has_memory INTEGER DEFAULT 1,
                    memory_limit_mb REAL DEFAULT 50,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            _turso_conn.commit()
        except Exception as e:
            print(f"Turso connection failed: {e}. Long-term memory unavailable.")
    return _turso_conn

# ══════════════════════════════════════════════════════════════════════════
# LAYER 1 — WORKING MEMORY (instant, in-server JSON)
# ══════════════════════════════════════════════════════════════════════════

def _load_working():
    if os.path.exists(WORKING_FILE):
        try:
            with open(WORKING_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}

def _save_working(data):
    with open(WORKING_FILE, "w") as f:
        json.dump(data, f)

def working_set(agent_id: str, key: str, value):
    data = _load_working()
    data.setdefault(agent_id, {})[key] = value
    _save_working(data)

def working_get(agent_id: str, key: str = None):
    data = _load_working()
    if key:
        return data.get(agent_id, {}).get(key)
    return data.get(agent_id, {})

def working_clear(agent_id: str = None):
    if agent_id:
        data = _load_working()
        data.pop(agent_id, None)
        _save_working(data)
    else:
        _save_working({})

# ══════════════════════════════════════════════════════════════════════════
# LAYER 2 — SHORT-TERM MEMORY (Supabase, recent chats)
# ══════════════════════════════════════════════════════════════════════════

def short_save(user_id: str, role: str, content: str, agent_id: str = None, task_id: str = None):
    try:
        sb.table("memory").insert({
            "user_id": str(user_id),
            "role": role,
            "content": content,
            "agent_id": agent_id or "general",
            "task_id": task_id,
        }).execute()
    except Exception as e:
        print(f"short_save error: {e}")

def short_get(user_id: str, agent_id: str = None, limit: int = 30) -> list:
    try:
        q = sb.table("memory").select("role,content,agent_id,created_at")\
            .eq("user_id", str(user_id))
        if agent_id:
            q = q.eq("agent_id", agent_id)
        r = q.order("created_at", desc=False).limit(limit).execute()
        return r.data or []
    except:
        return []

def short_clear(user_id: str, agent_id: str = None):
    try:
        q = sb.table("memory").delete().eq("user_id", str(user_id))
        if agent_id:
            q = q.eq("agent_id", agent_id)
        q.execute()
    except Exception as e:
        print(f"short_clear error: {e}")

def short_get_size_mb() -> float:
    try:
        r = sb.rpc("get_memory_size_mb", {}).execute()
        return float(r.data or 0)
    except:
        # Fallback: count rows × avg size
        try:
            r = sb.table("memory").select("id", count="exact").execute()
            count = r.count or 0
            return round(count * 0.001, 2)  # ~1KB per row estimate
        except:
            return 0.0

# ══════════════════════════════════════════════════════════════════════════
# LAYER 3 — LONG-TERM MEMORY (Turso, permanent)
# ══════════════════════════════════════════════════════════════════════════

def long_remember(user_id: str, category: str, key: str, value, agent_id: str = None):
    conn = _get_turso()
    if not conn:
        return
    try:
        conn.execute(
            """INSERT OR REPLACE INTO long_term
               (user_id, agent_id, category, key, value)
               VALUES (?, ?, ?, ?, ?)""",
            (str(user_id), agent_id or "general", category, key, json.dumps(value))
        )
        conn.commit()
    except Exception as e:
        print(f"long_remember error: {e}")

def long_recall(user_id: str, category: str = None, agent_id: str = None) -> list:
    conn = _get_turso()
    if not conn:
        return []
    try:
        if category and agent_id:
            rows = conn.execute(
                "SELECT category,key,value FROM long_term WHERE user_id=? AND category=? AND agent_id=?",
                (str(user_id), category, agent_id)
            ).fetchall()
        elif category:
            rows = conn.execute(
                "SELECT category,key,value FROM long_term WHERE user_id=? AND category=?",
                (str(user_id), category)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT category,key,value FROM long_term WHERE user_id=?",
                (str(user_id),)
            ).fetchall()
        return [{"category": r[0], "key": r[1], "value": json.loads(r[2])} for r in rows]
    except:
        return []

def long_forget(user_id: str, key: str):
    conn = _get_turso()
    if not conn:
        return
    try:
        conn.execute("DELETE FROM long_term WHERE user_id=? AND key=?", (str(user_id), key))
        conn.commit()
    except Exception as e:
        print(f"long_forget error: {e}")

def long_clear(user_id: str, agent_id: str = None):
    conn = _get_turso()
    if not conn:
        return
    try:
        if agent_id:
            conn.execute("DELETE FROM long_term WHERE user_id=? AND agent_id=?", (str(user_id), agent_id))
        else:
            conn.execute("DELETE FROM long_term WHERE user_id=?", (str(user_id),))
        conn.commit()
    except Exception as e:
        print(f"long_clear error: {e}")

# ══════════════════════════════════════════════════════════════════════════
# SMART MEMORY MANAGER
# ══════════════════════════════════════════════════════════════════════════

def get_memory_status(user_id: str) -> dict:
    short_mb = short_get_size_mb()
    short_pct = round((short_mb / _supabase_max_mb()) * 100, 1)

    long_facts = long_recall(user_id)
    long_count = len(long_facts)

    working = _load_working()
    working_agents = list(working.keys())

    return {
        "short_term": {"used_mb": short_mb, "max_mb": _supabase_max_mb(), "percent": short_pct},
        "long_term": {"facts_count": long_count, "max_gb": 9},
        "working": {"agents": working_agents, "count": len(working_agents)},
        "alert": short_pct >= _urgent_pct() and "urgent" or short_pct >= _warn_pct() and "warn" or "ok"
    }

def check_and_alert(user_id: str, bot_send_fn) -> str | None:
    """
    Call this periodically. Returns alert level if threshold hit.
    bot_send_fn is called to send Telegram alert.
    """
    status = get_memory_status(user_id)
    pct = status["short_term"]["percent"]

    if pct >= _urgent_pct():
        msg = (
            f"🚨 URGENT: Memory at {pct}% ({status['short_term']['used_mb']} MB used)\n\n"
            f"You need to clean memory now!\n"
            f"Options:\n"
            f"• /clearmem short — clear recent chats\n"
            f"• /archive short — compress old chats to long-term\n"
            f"• /clearmem all — full reset (asks confirmation)\n"
            f"• /memstatus — see full breakdown"
        )
        if bot_send_fn:
            import asyncio
            asyncio.create_task(bot_send_fn(msg))
        return "urgent"

    elif pct >= _warn_pct():
        msg = (
            f"⚠️ Memory Warning: {pct}% used ({status['short_term']['used_mb']} MB)\n"
            f"No action needed yet. Use /memstatus to monitor.\n"
            f"Use /clearmem short to free space when ready."
        )
        if bot_send_fn:
            import asyncio
            asyncio.create_task(bot_send_fn(msg))
        return "warn"

    return "ok"

def archive_short_to_long(user_id: str) -> str:
    """Compress old short-term messages into long-term summary."""
    recent = short_get(user_id, limit=200)
    if not recent:
        return "Nothing to archive."

    text = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
    summary = call_ai(
        messages=[{"role": "user", "content": f"Summarize the key facts and findings from these conversations:\n\n{text}"}],
        system="You are a memory archiver. Extract and summarize only the most important facts, findings, and decisions. Be concise."
    )

    long_remember(user_id, "archive", f"archive_{int(time.time())}", summary)
    short_clear(user_id)
    return f"✅ Archived {len(recent)} messages into long-term memory. Short-term cleared."

def build_full_context(user_id: str, agent_id: str = None) -> tuple[str, list]:
    """Build complete context string + message history for an agent call."""
    facts = long_recall(user_id)
    work = working_get(agent_id or "general")
    recent = short_get(user_id, agent_id=agent_id, limit=25)

    context_parts = []

    if facts:
        context_parts.append("=== Long-term memory (permanent facts) ===")
        for f in facts[:20]:  # cap to avoid token overflow
            context_parts.append(f"[{f['category']}] {f['key']}: {f['value']}")

    if work:
        context_parts.append("\n=== Working memory (current task state) ===")
        for k, v in work.items():
            context_parts.append(f"{k}: {v}")

    context = "\n".join(context_parts)
    messages = [{"role": m["role"], "content": m["content"]} for m in recent]

    return context, messages

# ══════════════════════════════════════════════════════════════════════════
# CUSTOM AGENT REGISTRY
# ══════════════════════════════════════════════════════════════════════════

def save_custom_agent(user_id: str, name: str, system_prompt: str,
                      has_memory: bool = True, memory_limit_mb: float = 50):
    conn = _get_turso()
    if not conn:
        return False
    try:
        conn.execute(
            """INSERT OR REPLACE INTO custom_agents
               (user_id, name, system_prompt, has_memory, memory_limit_mb)
               VALUES (?, ?, ?, ?, ?)""",
            (str(user_id), name, system_prompt, int(has_memory), memory_limit_mb)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"save_custom_agent error: {e}")
        return False

def get_custom_agent(name: str) -> dict | None:
    conn = _get_turso()
    if not conn:
        return None
    try:
        rows = conn.execute(
            "SELECT name, system_prompt, has_memory, memory_limit_mb, user_id FROM custom_agents WHERE name=?",
            (name,)
        ).fetchall()
        if rows:
            r = rows[0]
            return {"name": r[0], "system_prompt": r[1], "has_memory": bool(r[2]),
                    "memory_limit_mb": r[3], "user_id": r[4]}
        return None
    except:
        return None

def list_custom_agents(user_id: str) -> list:
    conn = _get_turso()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT name, system_prompt, has_memory, memory_limit_mb FROM custom_agents WHERE user_id=?",
            (str(user_id),)
        ).fetchall()
        return [{"name": r[0], "preview": r[1][:60]+"...", "has_memory": bool(r[2]),
                 "memory_limit_mb": r[3]} for r in rows]
    except:
        return []

def delete_custom_agent(user_id: str, name: str) -> bool:
    conn = _get_turso()
    if not conn:
        return False
    try:
        conn.execute("DELETE FROM custom_agents WHERE user_id=? AND name=?", (str(user_id), name))
        conn.commit()
        return True
    except:
        return False

# ── Keep Supabase alive (ping every 5 min) ────────────────────────────────
import threading

def _keepalive():
    while True:
        try:
            sb.table("memory").select("id").limit(1).execute()
        except:
            pass
        time.sleep(290)

threading.Thread(target=_keepalive, daemon=True).start()
