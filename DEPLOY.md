# 🚀 Agent System — Complete Deployment Guide
# Everything on server, 0 cost, no credit card, runs 24/7

---

## STEP 1 — Get All Free API Keys (15 mins)

### Telegram Bot Token
1. Open Telegram → search @BotFather
2. Send /newbot → follow instructions
3. Copy your token: `1234567890:ABCdef...`

### Your Telegram User ID
1. Search @userinfobot on Telegram
2. Send /start → it shows your ID number

### Groq API Key (free, no card)
1. Go to console.groq.com
2. Sign up with Google
3. API Keys → Create Key → copy it

### Together AI (free credits, no card)
1. Go to api.together.xyz
2. Sign up → API Keys → copy

### OpenRouter (free tier, no card)
1. Go to openrouter.ai
2. Sign up → Keys → Create Key → copy

### Gemini API Key (free, no card)
1. Go to aistudio.google.com
2. Get API Key → copy

### Supabase (free, no card)
1. Go to supabase.com
2. Sign up with GitHub
3. New Project → wait for setup
4. Settings → API → copy URL and anon key

### Turso (free 9GB, no card)
1. Go to turso.tech
2. Sign up with GitHub
3. Create database → copy URL and token
   turso db create my-agent-db
   turso db tokens create my-agent-db

---

## STEP 2 — Setup Supabase Tables (5 mins)

1. Go to your Supabase project
2. Click SQL Editor
3. Paste contents of supabase_setup.sql
4. Click Run

---

## STEP 3 — Push Code to GitHub (5 mins)

```bash
cd agent-system
git init
git add .
git commit -m "Complete AI Agent System"
# Create a repo on github.com first, then:
git remote add origin https://github.com/YOUR_USERNAME/agent-system.git
git push -u origin main
```

---

## STEP 4 — Deploy on Koyeb (10 mins, free, no card)

1. Go to koyeb.com
2. Sign up with GitHub (free)
3. Click Create App
4. Choose GitHub source
5. Select your repo
6. Add ALL environment variables (copy from .env.example):

   TELEGRAM_TOKEN         = your bot token
   ADMIN_USER_ID          = your telegram user id
   GROQ_API_KEY           = your groq key
   TOGETHER_API_KEY       = your together key
   OPENROUTER_API_KEY     = your openrouter key
   GEMINI_API_KEY         = your gemini key
   SUPABASE_URL           = your supabase url
   SUPABASE_KEY           = your supabase anon key
   TURSO_URL              = your turso url
   TURSO_TOKEN            = your turso token
   DASHBOARD_SECRET       = choose any password
   MEMORY_WARN_PERCENT    = 80
   MEMORY_URGENT_PERCENT  = 95
   SUPABASE_MAX_MB        = 450

7. Run command: python main.py
8. Click Deploy ✅

For dashboard: Create a second service in same app
   Run command: uvicorn dashboard.app:app --host 0.0.0.0 --port 8000

---

## STEP 5 — Keep Alive with UptimeRobot (5 mins, free)

1. Go to uptimerobot.com
2. Sign up free
3. Add New Monitor:
   - Type: HTTP
   - URL: your Koyeb dashboard URL
   - Interval: 5 minutes
4. Done — system stays alive forever ✅

---

## STEP 6 — Test Your System

Open Telegram and message your bot:

/start                          → welcome message
/research quantum computing     → research agent
/write an email to my team      → writer agent
/code fibonacci in Python       → coder agent
/team analyse AI trends 2024    → multi-agent team
/newagent                       → build custom agent
/task Research CRISPR papers    → background task
/memstatus                      → check memory
/apistatus                      → check AI providers

Upload any file → bot reads it automatically!

---

## Your System Features

✅ 12 built-in specialist agents
✅ Unlimited custom agents you build yourself  
✅ Multi-agent teams for complex tasks
✅ Background tasks (run while you sleep)
✅ 3-layer memory (working + short + long-term)
✅ Smart memory alerts (you decide when to clean)
✅ Auto API failover (Groq → Together → OpenRouter → Gemini)
✅ Upload PDF, Word, Excel, CSV, images, videos, code
✅ Dashboard website (accessible from any device)
✅ Runs 24/7 — PC can be off, formatted, or broken
✅ Total cost: $0 — no credit card ever

---

## Memory Commands Quick Reference

/memstatus              → see memory usage %
/clearmem short         → clear recent chats
/clearmem working       → clear working RAM
/clearmem long [key]    → delete one fact
/clearmem all           → full reset (confirms)
/archive                → compress chats → long-term
/memory                 → see all stored facts
/export                 → download memory as JSON

Alert thresholds:
- 80% → warning notification
- 95% → urgent notification with cleanup options
- You always decide what to delete — system never auto-deletes

---

## Troubleshooting

Bot not responding:
→ Check Koyeb logs for errors
→ Verify TELEGRAM_TOKEN is correct

Memory full alert:
→ Use /clearmem short first (safest)
→ Or /archive to compress before clearing

API rate limit:
→ /apistatus to see which provider is active
→ /switchapi groq to manually switch
→ System auto-switches anyway

Dashboard not loading:
→ Check dashboard service is running on Koyeb
→ Use password you set in DASHBOARD_SECRET
