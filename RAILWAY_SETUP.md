# 🚀 Complete Railway Deployment Guide
# Free, no credit card, 24/7, everything on server

---

## What you need before starting (15 min)

Get these free accounts and keys first — open each link, sign up with Google or GitHub:

| Service | Link | What you get |
|---|---|---|
| Telegram | t.me/BotFather | Your bot token |
| Groq | console.groq.com | Free AI (Llama 3.3 70B) |
| OpenRouter | openrouter.ai | Backup AI (Mistral Large) |
| Gemini | aistudio.google.com | Best AI (Gemini 1.5 Pro) |
| Supabase | supabase.com | Free database |
| Turso | turso.tech | Free long-term memory |
| GitHub | github.com | Code storage |
| Railway | railway.app | Free server |
| UptimeRobot | uptimerobot.com | Keep alive |

---

## STEP 1 — Create Telegram Bot (2 min)

1. Open Telegram → search **@BotFather** → open it
2. Send: `/newbot`
3. Bot name: type anything e.g. `My AI Agent`
4. Bot username: must end in 'bot' e.g. `myaiagent_bot`
5. Copy the token → looks like: `7123456789:AAFxxxxx`
6. Save it as: `TELEGRAM_TOKEN`

Get your User ID:
1. Search **@userinfobot** on Telegram → send `/start`
2. Copy the number it shows
3. Save it as: `ADMIN_USER_ID`

---

## STEP 2 — Get Groq API Key (2 min)

1. Go to → **console.groq.com**
2. Sign up with Google (no card)
3. Click **API Keys** in left menu
4. Click **Create API Key**
5. Copy the key → starts with `gsk_`
6. Save as: `GROQ_API_KEY`

---

## STEP 3 — Get OpenRouter Key (2 min)

1. Go to → **openrouter.ai**
2. Click **Sign In** → Sign up with Google
3. Click your profile → **Keys**
4. Click **Create Key**
5. Copy the key → starts with `sk-or-`
6. Save as: `OPENROUTER_API_KEY`

---

## STEP 4 — Get Gemini Key (2 min)

1. Go to → **aistudio.google.com**
2. Sign in with Google
3. Click **Get API Key** → **Create API key**
4. Copy the key → starts with `AIza`
5. Save as: `GEMINI_API_KEY`

---

## STEP 5 — Set up Supabase (5 min)

1. Go to → **supabase.com**
2. Sign up with GitHub
3. Click **New Project**
4. Name: `agent-system` → choose any password → Create
5. Wait 1-2 min for setup
6. Go to **Settings** (gear icon) → **API**
7. Copy **Project URL** → save as: `SUPABASE_URL`
8. Copy **anon public** key → save as: `SUPABASE_KEY`

Create tables:
1. Click **SQL Editor** in left menu
2. Paste this entire SQL and click **Run**:

```sql
CREATE TABLE IF NOT EXISTS memory (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    agent_id TEXT DEFAULT 'general',
    task_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_memory_user ON memory(user_id);

CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL,
    description TEXT NOT NULL,
    agent_id TEXT DEFAULT 'research',
    status TEXT DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    result TEXT,
    steps JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_logs (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT,
    success BOOLEAN DEFAULT true,
    error TEXT,
    tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION get_memory_size_mb()
RETURNS NUMERIC AS $$
    SELECT ROUND(pg_total_relation_size('memory') / 1024.0 / 1024.0, 2);
$$ LANGUAGE SQL;
```

3. You should see: **Success. No rows returned** ✅

---

## STEP 6 — Set up Turso (3 min)

1. Go to → **turso.tech**
2. Sign up with GitHub
3. Click **Create Database**
4. Name: `agent-memory` → choose closest region → Create
5. Click your database → click **Generate Token**
6. Copy **Database URL** → save as: `TURSO_URL`
   Format: `libsql://agent-memory-xxx.turso.io`
7. Copy **Token** → save as: `TURSO_TOKEN`

---

## STEP 7 — Push code to GitHub (5 min)

1. Go to → **github.com** → sign up free
2. Click **+** → **New repository**
3. Name: `my-agent-system` → **Public** → Create
4. Download and extract `agent-system.zip`
5. Open terminal/command prompt inside the extracted folder

If you have Git installed:
```bash
git init
git add .
git commit -m "my agent system"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/my-agent-system.git
git push -u origin main
```

If you don't have Git:
1. Download Git from → **git-scm.com** → install
2. Then run the commands above

---

## STEP 8 — Deploy on Railway — ONE service only (5 min)

1. Go to → **railway.app**
2. Click **Login** → **Login with GitHub** → Authorize
3. Click **New Project**
4. Click **Deploy from GitHub repo**
5. Select **my-agent-system**
6. Railway starts building automatically (uses `railway.json` — no config needed)

Add environment variables:
1. Click your service (the box that appeared)
2. Click **Variables** tab
3. Click **RAW Editor**
4. Paste ALL of this (replace values with your actual keys):

```
TELEGRAM_TOKEN=paste_your_telegram_token_here
ADMIN_USER_ID=paste_your_user_id_here
GROQ_API_KEY=paste_your_groq_key_here
OPENROUTER_API_KEY=paste_your_openrouter_key_here
GEMINI_API_KEY=paste_your_gemini_key_here
SUPABASE_URL=paste_your_supabase_url_here
SUPABASE_KEY=paste_your_supabase_key_here
TURSO_URL=paste_your_turso_url_here
TURSO_TOKEN=paste_your_turso_token_here
DASHBOARD_SECRET=choose_any_password
MEMORY_WARN_PERCENT=80
MEMORY_URGENT_PERCENT=95
SUPABASE_MAX_MB=450
```

5. Click **Update Variables**
6. Railway redeploys automatically
7. Click **Deployments** tab → **View Logs**
8. When you see `✅ Web server (dashboard + health) on port ...` and
   `✅ Agent System running 24/7...` → it works!

Get your dashboard URL:
1. Click **Settings** tab on your service
2. Under **Networking** → click **Generate Domain**
3. Open that URL in browser → enter your `DASHBOARD_SECRET` as the password
4. You see live agent status, tasks, memory, API usage — all in one place ✅

This single service runs BOTH your Telegram bot AND your dashboard website
together. No second service needed.

---

## STEP 9 — Keep alive with UptimeRobot (3 min)

Railway free tier may sleep. Fix it permanently:

1. Go to → **uptimerobot.com** → Sign up free
2. Click **Add New Monitor**
3. Monitor type: **HTTP(s)**
4. Friendly name: `My Agent Bot`
5. URL: paste your Railway bot service URL + `/health`
   Example: `https://my-agent-system.railway.app/health`
6. Monitoring interval: **5 minutes**
7. Click **Create Monitor** ✅

Now your bot runs 24/7 forever — never sleeps!

---

## Test your bot (2 min)

Open Telegram → search your bot username → tap Start:

```
/start              → welcome message
/help               → all commands
/research AI trends → research agent answers
/code hello world   → coder agent writes code
/write an essay     → writer agent drafts it
/agents             → see all 12 agents
/apistatus          → see which AI is active
/memstatus          → check memory usage
```

Upload a file → bot reads it automatically!

---

## Your AI provider order (strongest → fastest fallback)

1. Gemini 1.5 Pro     — best reasoning (50/day free)
2. Groq Llama 3.3 70B — fastest strong model (1000/day free)
3. OpenRouter Mistral  — strong backup (200/day free)
4. Groq Gemma 2 27B   — fast fallback (2000/day free)
5. Gemini 1.5 Flash   — final fallback (1500/day free)
6. OpenRouter Llama    — last resort (500/day free)

When one hits its daily limit → automatically switches to next. You never notice.

---

## If something goes wrong

Bot not responding:
→ Click your Railway service → Deployments → View Logs
→ Look for red error messages
→ Most common: wrong TELEGRAM_TOKEN

Memory alert:
→ /clearmem short  (safest — clears recent chats)
→ /archive         (compresses chats to long-term)

API not working:
→ /apistatus       (see which providers are active)
→ /switchapi groq  (force switch to Groq)

Dashboard not loading:
→ Check second Railway service is running
→ Use your DASHBOARD_SECRET as password
