"""
main.py — Complete Telegram bot entry point.
Handles all messages, files, commands, agent routing.
Runs 24/7 on any Docker host (Railway, Render, Fly.io) — independent of your PC.
"""
# MUST be the very first import — patches os.getenv globally so every
# environment variable read anywhere (this file, every other module)
# is automatically stripped of hidden/invisible characters before use.
import env_clean

import os, asyncio, tempfile, json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
env_clean.apply()  # re-apply after dotenv loads .env file values too

# Run diagnostics FIRST — before any module that could crash on a bad/missing key.
# Prints a clear report to logs and exits cleanly with a readable reason
# if required variables are missing, instead of a cryptic stack trace.
from startup_check import run_check
run_check()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters, ContextTypes
)

from api_router import call_ai, get_provider_status, switch_provider, get_current_provider
from memory import (
    short_clear, long_clear, working_clear, get_memory_status,
    archive_short_to_long, build_full_context, short_get_size_mb,
    save_custom_agent, get_custom_agent, list_custom_agents, delete_custom_agent,
    long_recall, long_forget
)
from agents.registry import BUILTIN_AGENTS, run_agent, run_team, route_to_agent
from handlers.file_handler import extract_file_content, pick_agent_for_file
from handlers.task_manager import (
    create_task, get_task, get_all_tasks, run_task_async,
    format_task_status, delete_task
)

ADMIN_ID = int(os.getenv("ADMIN_USER_ID", 0))

# ── Conversation state for building custom agents ──────────────────────────
_building_agent = {}  # user_id → {step, data}

# ── Helper ─────────────────────────────────────────────────────────────────
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def send_long(update: Update, text: str, max_len: int = 4000):
    """Send long messages in chunks."""
    for i in range(0, len(text), max_len):
        await update.message.reply_text(text[i:i+max_len])

# ══════════════════════════════════════════════════════════════════════════
# COMMANDS
# ══════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Welcome {name}!\n\n"
        f"🤖 Your AI Agent System is running 24/7.\n\n"
        f"📌 Quick Commands:\n"
        f"/help — full command list\n"
        f"/agents — see all agents\n"
        f"/research [topic] — deep research\n"
        f"/write [request] — write anything\n"
        f"/code [request] — code help\n"
        f"/team [task] — multi-agent team\n"
        f"/task [description] — long background task\n"
        f"/newagent — build your own agent\n"
        f"/memstatus — check memory usage\n"
        f"\n📎 Upload any file — I'll read it automatically!"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 Complete Command List\n\n"
        "── Agents ──\n"
        "/research [topic] — Research agent\n"
        "/write [request] — Writer agent\n"
        "/code [request] — Coder agent\n"
        "/analyse [question] — Data analyst\n"
        "/search [query] — Web search agent\n"
        "/summarise [text] — Summariser agent\n"
        "/plan [goal] — Planner agent\n"
        "/review [content] — Critic agent\n"
        "/agent [name] [msg] — Use specific agent\n"
        "/team [task] — Multi-agent team\n\n"
        "── Custom Agents ──\n"
        "/newagent — Build your own agent\n"
        "/myagents — List your custom agents\n"
        "/delagent [name] — Delete custom agent\n\n"
        "── Tasks ──\n"
        "/task [description] — Start background task\n"
        "/tasks — See all your tasks\n"
        "/taskstatus [id] — Check one task\n"
        "/deltask [id] — Delete a task\n\n"
        "── Memory ──\n"
        "/memstatus — Full memory usage report\n"
        "/clearmem short — Clear recent chats\n"
        "/clearmem working — Clear working memory\n"
        "/clearmem long [key] — Delete one fact\n"
        "/clearmem all — Full reset (confirms first)\n"
        "/archive — Compress chats to long-term\n"
        "/memory — See what I remember about you\n"
        "/export — Download all memory as JSON\n\n"
        "── API ──\n"
        "/apistatus — See all AI providers + usage\n"
        "/switchapi [name] — Force switch provider\n"
        "/settings — How to add/change API keys\n\n"
        "── Files ──\n"
        "Just upload any file — I detect type automatically!\n"
        "Supports: PDF, Word, Excel, CSV, images, code, text"
    )

async def cmd_agents(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lines = ["🤖 Built-in Agents:\n"]
    for key, info in BUILTIN_AGENTS.items():
        lines.append(f"{info['emoji']} {info['name']} — {info['description']}")

    custom = list_custom_agents(str(uid))
    if custom:
        lines.append("\n🛠️ Your Custom Agents:")
        for a in custom:
            lines.append(f"• {a['name']} — {a['preview']}")

    await update.message.reply_text("\n".join(lines))

# ── Single agent commands ──────────────────────────────────────────────────
async def _run_single_agent(update: Update, agent_id: str, args: list):
    uid = update.effective_user.id
    if not args:
        await update.message.reply_text(f"Usage: /{agent_id} [your message]")
        return
    msg = " ".join(args)
    await update.message.reply_text(f"⏳ {BUILTIN_AGENTS.get(agent_id, {}).get('emoji','🤖')} Working...")
    response, agent_name = run_agent(agent_id, str(uid), msg)
    await send_long(update, f"{agent_name}\n\n{response}")

async def cmd_research(update, ctx): await _run_single_agent(update, "research", ctx.args)
async def cmd_write(update, ctx):    await _run_single_agent(update, "writer", ctx.args)
async def cmd_code(update, ctx):     await _run_single_agent(update, "coder", ctx.args)
async def cmd_analyse(update, ctx):  await _run_single_agent(update, "analyst", ctx.args)
async def cmd_search(update, ctx):   await _run_single_agent(update, "web_search", ctx.args)
async def cmd_summarise(update, ctx):await _run_single_agent(update, "summariser", ctx.args)
async def cmd_plan(update, ctx):     await _run_single_agent(update, "planner", ctx.args)
async def cmd_review(update, ctx):   await _run_single_agent(update, "critic", ctx.args)

async def cmd_agent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Use a specific agent by name: /agent BiologyResearcher tell me about DNA"""
    uid = update.effective_user.id
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text("Usage: /agent [agent_name] [message]")
        return
    agent_name = ctx.args[0]
    msg = " ".join(ctx.args[1:])

    # Check custom agents first
    custom = get_custom_agent(agent_name)
    if custom:
        await update.message.reply_text(f"⏳ 🛠️ {agent_name} working...")
        response, label = run_agent(agent_name, str(uid), msg, custom_agent=custom)
        await send_long(update, f"🛠️ {agent_name}\n\n{response}")
    elif agent_name.lower() in BUILTIN_AGENTS:
        await _run_single_agent(update, agent_name.lower(), ctx.args[1:])
    else:
        await update.message.reply_text(
            f"Agent '{agent_name}' not found.\n"
            f"Use /agents to see all available agents.\n"
            f"Use /newagent to create a custom agent."
        )

async def cmd_team(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text("Usage: /team [complex task description]")
        return
    task = " ".join(ctx.args)
    await update.message.reply_text("⏳ Multi-agent team starting...\n🔬 → ✍️ → 🔍 → ✅")
    result = run_team(str(uid), task)
    await send_long(update, result)

# ── Custom agent builder ───────────────────────────────────────────────────
async def cmd_newagent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    _building_agent[uid] = {"step": "name", "data": {}}
    await update.message.reply_text(
        "🛠️ Let's build your custom agent!\n\n"
        "Step 1/4: What is the agent's name?\n"
        "(e.g. BiologyResearcher, LegalAdvisor, MarketAnalyst)"
    )

async def cmd_myagents(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    agents = list_custom_agents(str(uid))
    if not agents:
        await update.message.reply_text(
            "You have no custom agents yet.\nUse /newagent to build one!"
        )
        return
    lines = ["🛠️ Your Custom Agents:\n"]
    for a in agents:
        mem = "🧠 Memory ON" if a["has_memory"] else "📭 No memory"
        lines.append(f"• {a['name']} [{mem}]\n  {a['preview']}\n")
    await update.message.reply_text("\n".join(lines))

async def cmd_delagent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text("Usage: /delagent [agent_name]")
        return
    name = ctx.args[0]
    if delete_custom_agent(str(uid), name):
        await update.message.reply_text(f"✅ Agent '{name}' deleted.")
    else:
        await update.message.reply_text(f"Agent '{name}' not found.")

# ── Task commands ──────────────────────────────────────────────────────────
async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text(
            "Usage: /task [description]\n"
            "Example: /task Research all papers on CRISPR published in 2024 and summarise findings"
        )
        return
    description = " ".join(ctx.args)
    task_id = create_task(str(uid), description, "research")

    send_fn = lambda msg: update.message.reply_text(msg)
    await update.message.reply_text(
        f"📋 Task #{task_id} created!\n"
        f"📝 {description[:100]}...\n\n"
        f"⏳ Starting now — I'll update you as it progresses.\n"
        f"You can check anytime: /taskstatus {task_id}"
    )
    asyncio.create_task(run_task_async(task_id, str(uid), send_fn))

async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    tasks = get_all_tasks(str(uid))
    await update.message.reply_text(format_task_status(tasks))

async def cmd_taskstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /taskstatus [task_id]")
        return
    task = get_task(ctx.args[0].upper())
    if not task:
        await update.message.reply_text("Task not found.")
        return
    result = task.get("result") or "In progress..."
    steps = json.loads(task.get("steps", "[]"))
    step_text = "\n".join([f"  • {s['step']}" for s in steps[-5:]])
    await send_long(update,
        f"📋 Task #{task['task_id']}\n"
        f"Status: {task['status']} ({task['progress']}%)\n"
        f"Description: {task['description']}\n\n"
        f"Recent steps:\n{step_text}\n\n"
        f"Result:\n{result[:2000]}"
    )

async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /deltask [task_id]")
        return
    delete_task(ctx.args[0].upper())
    await update.message.reply_text(f"✅ Task {ctx.args[0].upper()} deleted.")

# ── Memory commands ────────────────────────────────────────────────────────
async def cmd_memstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    status = get_memory_status(str(uid))
    st = status["short_term"]
    lt = status["long_term"]
    wk = status["working"]

    bar_len = int(st["percent"] / 10)
    bar = "█" * bar_len + "░" * (10 - bar_len)

    alert_icon = {"urgent": "🚨", "warn": "⚠️", "ok": "✅"}.get(status["alert"], "✅")

    await update.message.reply_text(
        f"🧠 Memory Status {alert_icon}\n\n"
        f"📬 Short-term (Supabase):\n"
        f"  [{bar}] {st['percent']}%\n"
        f"  {st['used_mb']} MB / {st['max_mb']} MB\n\n"
        f"📚 Long-term (Turso):\n"
        f"  {lt['facts_count']} facts stored\n"
        f"  Limit: {lt['max_gb']} GB\n\n"
        f"⚡ Working memory:\n"
        f"  {wk['count']} active agents: {', '.join(wk['agents']) or 'none'}\n\n"
        f"Commands:\n"
        f"/clearmem short — clear recent chats\n"
        f"/clearmem working — clear working RAM\n"
        f"/clearmem long [key] — delete one fact\n"
        f"/clearmem all — full reset\n"
        f"/archive — compress chats to long-term"
    )

async def cmd_clearmem(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not ctx.args:
        await update.message.reply_text(
            "Usage:\n"
            "/clearmem short — clear recent chats\n"
            "/clearmem working — clear working memory\n"
            "/clearmem long [key] — delete one long-term fact\n"
            "/clearmem all — full reset (asks confirmation)"
        )
        return

    layer = ctx.args[0].lower()

    if layer == "short":
        short_clear(str(uid))
        await update.message.reply_text("✅ Short-term memory cleared.")

    elif layer == "working":
        working_clear()
        await update.message.reply_text("✅ Working memory cleared.")

    elif layer == "long":
        if len(ctx.args) < 2:
            facts = long_recall(str(uid))
            if not facts:
                await update.message.reply_text("No long-term facts stored.")
                return
            keys = "\n".join([f"• {f['key']}" for f in facts[:20]])
            await update.message.reply_text(f"Stored facts:\n{keys}\n\nUse: /clearmem long [key]")
        else:
            key = " ".join(ctx.args[1:])
            long_forget(str(uid), key)
            await update.message.reply_text(f"✅ Deleted fact: {key}")

    elif layer == "all":
        keyboard = [[
            InlineKeyboardButton("✅ Yes, clear everything", callback_data="clear_all_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="clear_all_cancel"),
        ]]
        await update.message.reply_text(
            "⚠️ This will delete ALL your memory:\n"
            "• All chat history\n"
            "• All long-term facts\n"
            "• All working memory\n\n"
            "Are you sure?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def cmd_archive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text("⏳ Archiving short-term memory to long-term...")
    result = archive_short_to_long(str(uid))
    await update.message.reply_text(result)

async def cmd_memory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    facts = long_recall(str(uid))
    if not facts:
        await update.message.reply_text("No long-term facts stored yet.")
        return
    lines = ["📚 What I remember about you:\n"]
    for f in facts[:30]:
        lines.append(f"[{f['category']}] {f['key']}: {f['value']}")
    await send_long(update, "\n".join(lines))

async def cmd_export(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    facts = long_recall(str(uid))
    export = {"long_term": facts, "exported_at": str(__import__("datetime").datetime.now())}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(export, f, indent=2)
        tmp_path = f.name
    await update.message.reply_document(document=open(tmp_path, "rb"), filename="memory_export.json")
    os.unlink(tmp_path)

# ── API commands ───────────────────────────────────────────────────────────
async def cmd_apistatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from api_router import get_usage_summary
    summary = get_usage_summary()
    enabled_count = sum(1 for p in get_provider_status() if p["enabled"])
    if enabled_count == 0:
        await update.message.reply_text(
            "❌ No AI providers configured yet.\n\n"
            "Open your dashboard → Settings tab → paste at least one API key "
            "(Groq is free and recommended: console.groq.com)."
        )
        return
    await update.message.reply_text(summary)

async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚙️ To add or change API keys:\n\n"
        "1. Open your dashboard (the URL Railway gave you)\n"
        "2. Log in with your DASHBOARD_SECRET\n"
        "3. Click the ⚙️ Settings / API Keys tab\n"
        "4. Paste your keys and click Save\n\n"
        "Changes apply within ~30 seconds — no redeploy needed.\n"
        "Use /apistatus afterwards to confirm it's working."
    )

async def cmd_switchapi(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /switchapi [groq|together|openrouter|gemini|cohere]")
        return
    name = ctx.args[0].lower()
    if switch_provider(name):
        await update.message.reply_text(f"✅ Switched to {name}")
    else:
        await update.message.reply_text(f"❌ Provider '{name}' not found or not configured.")

# ── Callback query handler (inline buttons) ────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if query.data == "clear_all_confirm":
        short_clear(str(uid))
        long_clear(str(uid))
        working_clear()
        await query.edit_message_text("✅ All memory cleared successfully.")

    elif query.data == "clear_all_cancel":
        await query.edit_message_text("❌ Cancelled. Memory unchanged.")

# ══════════════════════════════════════════════════════════════════════════
# MESSAGE HANDLER — text + files + custom agent builder flow
# ══════════════════════════════════════════════════════════════════════════

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message

    # ── Custom agent builder flow ─────────────────────────────────────────
    if uid in _building_agent:
        state = _building_agent[uid]
        text = msg.text or ""

        if state["step"] == "name":
            state["data"]["name"] = text.strip()
            state["step"] = "prompt"
            await msg.reply_text(
                f"✅ Name: {text}\n\n"
                f"Step 2/4: Write the agent's instructions.\n"
                f"What should it do? What is its personality?\n"
                f"(Be as detailed as you want)"
            )

        elif state["step"] == "prompt":
            state["data"]["system_prompt"] = text.strip()
            state["step"] = "memory"
            keyboard = [[
                InlineKeyboardButton("🧠 Yes, give it memory", callback_data="agent_mem_yes"),
                InlineKeyboardButton("📭 No memory", callback_data="agent_mem_no"),
            ]]
            await msg.reply_text(
                "Step 3/4: Should this agent remember conversations?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif state["step"] == "memory_limit":
            try:
                limit = float(text.strip())
            except:
                limit = 50.0
            state["data"]["memory_limit_mb"] = limit
            state["step"] = "confirm"
            d = state["data"]
            await msg.reply_text(
                f"Step 4/4: Confirm your agent:\n\n"
                f"Name: {d['name']}\n"
                f"Memory: {'Yes' if d.get('has_memory') else 'No'}\n"
                f"Memory limit: {limit} MB\n"
                f"Instructions: {d['system_prompt'][:200]}...\n\n"
                f"Send /confirm to create or /cancel to abort."
            )
        return

    # ── File upload ───────────────────────────────────────────────────────
    if msg.document or msg.photo or msg.video or msg.audio:
        await msg.reply_text("📎 File received! Reading it...")

        with tempfile.TemporaryDirectory() as tmp_dir:
            if msg.document:
                file = await msg.document.get_file()
                file_path = os.path.join(tmp_dir, msg.document.file_name)
                mime = msg.document.mime_type
            elif msg.photo:
                file = await msg.photo[-1].get_file()
                file_path = os.path.join(tmp_dir, "image.jpg")
                mime = "image/jpeg"
            elif msg.video:
                file = await msg.video.get_file()
                file_path = os.path.join(tmp_dir, "video.mp4")
                mime = "video/mp4"
            else:
                file = await msg.audio.get_file()
                file_path = os.path.join(tmp_dir, "audio.mp3")
                mime = "audio/mpeg"

            await file.download_to_drive(file_path)
            content, file_type = await extract_file_content(file_path, mime)

        caption = msg.caption or "Please analyse this file and give me key insights."
        agent_id = pick_agent_for_file(file_type, caption)

        await msg.reply_text(f"🔍 Using {BUILTIN_AGENTS.get(agent_id, {}).get('name', agent_id)}...")
        response, agent_name = run_agent(agent_id, str(uid), caption, file_content=content)
        await send_long(update, f"{agent_name}\n\n{response}")
        return

    # ── Plain text — auto-route to best agent ─────────────────────────────
    if msg.text:
        text = msg.text.strip()
        if not text:
            return

        # Get custom agents for routing
        custom_agents = list_custom_agents(str(uid))

        # Route to best agent
        agent_id = route_to_agent(text, custom_agents)

        # Check if it's a custom agent
        custom = get_custom_agent(agent_id)

        await msg.reply_text("⏳ Thinking...")
        response, agent_name = run_agent(agent_id, str(uid), text, custom_agent=custom)
        await send_long(update, f"{agent_name}\n\n{response}")

async def handle_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in _building_agent:
        return
    d = _building_agent[uid]["data"]
    success = save_custom_agent(
        str(uid), d["name"], d["system_prompt"],
        d.get("has_memory", True), d.get("memory_limit_mb", 50)
    )
    del _building_agent[uid]
    if success:
        await update.message.reply_text(
            f"✅ Agent '{d['name']}' created!\n\n"
            f"Use it with:\n"
            f"/agent {d['name']} [your message]\n\n"
            f"Or just type your message — I'll auto-route to it when relevant."
        )
    else:
        await update.message.reply_text("❌ Failed to save agent. Try again.")

async def handle_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    _building_agent.pop(uid, None)
    await update.message.reply_text("❌ Cancelled.")

# Handle memory toggle buttons
async def handle_agent_memory_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if uid not in _building_agent:
        return

    state = _building_agent[uid]
    if query.data == "agent_mem_yes":
        state["data"]["has_memory"] = True
        state["step"] = "memory_limit"
        await query.edit_message_text(
            "Step 4/4: Memory alert limit (MB)?\n"
            "You'll get notified when this agent's memory exceeds this.\n"
            "(Default: 50 — just type a number)"
        )
    elif query.data == "agent_mem_no":
        state["data"]["has_memory"] = False
        state["data"]["memory_limit_mb"] = 0
        state["step"] = "confirm"
        d = state["data"]
        await query.edit_message_text(
            f"Step 4/4: Confirm your agent:\n\n"
            f"Name: {d['name']}\n"
            f"Memory: No\n"
            f"Instructions: {d['system_prompt'][:200]}...\n\n"
            f"Send /confirm to create or /cancel to abort."
        )

# ══════════════════════════════════════════════════════════════════════════
# APP STARTUP
# ══════════════════════════════════════════════════════════════════════════

def main():
    # os.getenv is already sanitized globally by env_clean (imported at top
    # of this file) — this is just a final format sanity-check, not a fix.
    token = os.getenv("TELEGRAM_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_TOKEN not set in environment!")
    if token.count(":") != 1 or not token.split(":")[0].isdigit():
        print(f"⚠️  TELEGRAM_TOKEN looks malformed (length {len(token)}). "
              f"Expected format: 1234567890:AAAbbbCCC... "
              f"Double-check you copied the FULL token from @BotFather.")

    app = ApplicationBuilder().token(token).build()

    # ── Register all commands ─────────────────────────────────────────────
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("help",        cmd_help))
    app.add_handler(CommandHandler("agents",      cmd_agents))
    app.add_handler(CommandHandler("research",    cmd_research))
    app.add_handler(CommandHandler("write",       cmd_write))
    app.add_handler(CommandHandler("code",        cmd_code))
    app.add_handler(CommandHandler("analyse",     cmd_analyse))
    app.add_handler(CommandHandler("search",      cmd_search))
    app.add_handler(CommandHandler("summarise",   cmd_summarise))
    app.add_handler(CommandHandler("plan",        cmd_plan))
    app.add_handler(CommandHandler("review",      cmd_review))
    app.add_handler(CommandHandler("agent",       cmd_agent))
    app.add_handler(CommandHandler("team",        cmd_team))
    app.add_handler(CommandHandler("newagent",    cmd_newagent))
    app.add_handler(CommandHandler("myagents",    cmd_myagents))
    app.add_handler(CommandHandler("delagent",    cmd_delagent))
    app.add_handler(CommandHandler("confirm",     handle_confirm))
    app.add_handler(CommandHandler("cancel",      handle_cancel))
    app.add_handler(CommandHandler("task",        cmd_task))
    app.add_handler(CommandHandler("tasks",       cmd_tasks))
    app.add_handler(CommandHandler("taskstatus",  cmd_taskstatus))
    app.add_handler(CommandHandler("deltask",     cmd_deltask))
    app.add_handler(CommandHandler("memstatus",   cmd_memstatus))
    app.add_handler(CommandHandler("clearmem",    cmd_clearmem))
    app.add_handler(CommandHandler("archive",     cmd_archive))
    app.add_handler(CommandHandler("memory",      cmd_memory))
    app.add_handler(CommandHandler("export",      cmd_export))
    app.add_handler(CommandHandler("apistatus",   cmd_apistatus))
    app.add_handler(CommandHandler("settings",    cmd_settings))
    app.add_handler(CommandHandler("switchapi",   cmd_switchapi))

    # ── Callback buttons ──────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(handle_agent_memory_callback, pattern="^agent_mem_"))
    app.add_handler(CallbackQueryHandler(handle_callback))

    # ── Messages + files ──────────────────────────────────────────────────
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message
    ))
    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO,
        handle_message
    ))

    print("✅ Agent System running 24/7...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    # Single web server: serves dashboard + health check.
    # Railway/Render require an open HTTP port — this satisfies that
    # AND gives you the dashboard, all in ONE service.
    import threading, uvicorn
    from dashboard.app import app as dashboard_app

    @dashboard_app.get("/health")
    def _health():
        return {"status": "ok", "service": "AI Agent Bot"}

    def _run_web():
        port = int(os.getenv("PORT", 8000))
        uvicorn.run(dashboard_app, host="0.0.0.0", port=port, log_level="error")

    threading.Thread(target=_run_web, daemon=True).start()
    print(f"✅ Web server (dashboard + health) on port {os.getenv('PORT', 8000)}")
    main()
