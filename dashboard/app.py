"""
dashboard/app.py — Web dashboard for your agent system.
Shows: live agent status, memory usage, API health, task progress, logs.
Accessible from any device via browser.
Protected by secret password.
"""
import os, json
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from db_clients import sb
import secrets

app = FastAPI(title="Agent System Dashboard")
security = HTTPBasic()
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "changeme")

def verify(creds: HTTPBasicCredentials = Depends(security)):
    if not secrets.compare_digest(creds.password, DASHBOARD_SECRET):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    return creds.username

@app.get("/", response_class=HTMLResponse)
async def dashboard(username: str = Depends(verify)):
    return HTMLResponse(DASHBOARD_HTML)

@app.get("/api/stats")
async def stats(username: str = Depends(verify)):
    try:
        # Recent tasks
        tasks = sb.table("tasks").select("task_id,description,status,progress,agent_id,created_at")\
            .order("created_at", desc=True).limit(10).execute().data or []

        # Recent API logs
        api_logs = sb.table("api_logs").select("provider,success,tokens_used,created_at")\
            .order("created_at", desc=True).limit(50).execute().data or []

        # API provider summary
        provider_stats = {}
        for log in api_logs:
            p = log["provider"]
            if p not in provider_stats:
                provider_stats[p] = {"calls": 0, "success": 0, "tokens": 0}
            provider_stats[p]["calls"] += 1
            if log["success"]:
                provider_stats[p]["success"] += 1
            provider_stats[p]["tokens"] += log.get("tokens_used") or 0

        # Memory size estimate
        mem_count = sb.table("memory").select("id", count="exact").execute()
        mem_rows = mem_count.count or 0

        # Recent messages
        recent_msgs = sb.table("memory").select("user_id,role,content,agent_id,created_at")\
            .order("created_at", desc=True).limit(20).execute().data or []

        return {
            "tasks": tasks,
            "api_providers": provider_stats,
            "memory_rows": mem_rows,
            "memory_mb_estimate": round(mem_rows * 0.001, 2),
            "recent_messages": recent_msgs,
            "total_api_calls": len(api_logs),
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/health")
async def health():
    return {"status": "running", "service": "Agent System"}

# ── Settings endpoints — add/view/delete API keys from the dashboard ───────
@app.get("/api/settings")
async def get_settings(username: str = Depends(verify)):
    from settings_manager import get_all_settings, CONFIGURABLE_KEYS
    masked = get_all_settings()
    fields = []
    for item in CONFIGURABLE_KEYS:
        fields.append({
            **item,
            "current_masked": masked.get(item["key"], ""),
            "is_set": bool(masked.get(item["key"])),
        })
    return {"fields": fields}

@app.post("/api/settings")
async def save_settings(request: Request, username: str = Depends(verify)):
    from settings_manager import set_setting, delete_setting, CONFIGURABLE_KEYS
    body = await request.json()
    valid_keys = {item["key"] for item in CONFIGURABLE_KEYS}
    saved = []
    for key, value in body.items():
        if key not in valid_keys:
            continue
        value = (value or "").strip()
        if value == "":
            continue  # leave unchanged if left blank
        if value == "__CLEAR__":
            delete_setting(key)
            saved.append(f"{key} cleared")
        else:
            set_setting(key, value)
            saved.append(key)
    return {"saved": saved}

# ── Dashboard HTML ─────────────────────────────────────────────────────────
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent System Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f1117; color: #e0e0e0; }
  .header { background: #1a1d27; padding: 1rem 2rem; border-bottom: 1px solid #2a2d3a;
            display: flex; align-items: center; justify-content: space-between; }
  .header h1 { font-size: 1.2rem; color: #fff; }
  .status-dot { width: 10px; height: 10px; border-radius: 50%; background: #4ade80;
                display: inline-block; margin-right: 6px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 1rem; padding: 1.5rem; }
  .card { background: #1a1d27; border-radius: 12px; padding: 1.25rem;
          border: 1px solid #2a2d3a; }
  .card h3 { font-size: 0.75rem; color: #888; text-transform: uppercase;
              letter-spacing: 0.05em; margin-bottom: 0.5rem; }
  .card .value { font-size: 2rem; font-weight: 600; color: #fff; }
  .card .sub { font-size: 0.8rem; color: #666; margin-top: 4px; }
  .section { padding: 0 1.5rem 1.5rem; }
  .section h2 { font-size: 1rem; margin-bottom: 1rem; color: #aaa; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { background: #1a1d27; padding: 0.75rem; text-align: left; color: #888;
       border-bottom: 1px solid #2a2d3a; font-weight: 500; }
  td { padding: 0.75rem; border-bottom: 1px solid #1e2130; }
  tr:hover td { background: #1e2130; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.75rem; }
  .badge.done { background: #1a3a2a; color: #4ade80; }
  .badge.running { background: #1a2a3a; color: #60a5fa; }
  .badge.failed { background: #3a1a1a; color: #f87171; }
  .badge.pending { background: #2a2a1a; color: #fbbf24; }
  .progress-bar { background: #2a2d3a; border-radius: 4px; height: 6px; margin-top: 4px; }
  .progress-fill { height: 100%; border-radius: 4px; background: #60a5fa; }
  .api-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px,1fr));
              gap: 0.75rem; margin-bottom: 1.5rem; }
  .api-card { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 10px;
              padding: 1rem; text-align: center; }
  .api-card .name { font-size: 0.9rem; font-weight: 600; margin-bottom: 4px; }
  .api-card .calls { font-size: 1.5rem; font-weight: 700; color: #60a5fa; }
  .api-card .rate { font-size: 0.75rem; color: #888; margin-top: 2px; }
  .refresh-btn { background: #2a3a5a; color: #60a5fa; border: none; border-radius: 8px;
                 padding: 6px 16px; cursor: pointer; font-size: 0.85rem; }
  .refresh-btn:hover { background: #3a4a6a; }
  .msg-row { display: flex; gap: 0.5rem; align-items: flex-start; padding: 0.5rem 0;
             border-bottom: 1px solid #1e2130; font-size: 0.82rem; }
  .msg-role { font-weight: 600; min-width: 70px; }
  .msg-role.user { color: #fbbf24; }
  .msg-role.assistant { color: #60a5fa; }
  .msg-agent { color: #888; font-size: 0.75rem; }
  .msg-content { color: #ccc; flex: 1; }
  #last-updated { font-size: 0.75rem; color: #555; }
  .tabs { display: flex; gap: 0.5rem; padding: 1rem 1.5rem 0; border-bottom: 1px solid #2a2d3a; }
  .tab-btn { background: transparent; border: none; color: #888; padding: 0.6rem 1.2rem;
             font-size: 0.9rem; cursor: pointer; border-radius: 8px 8px 0 0; }
  .tab-btn.active { color: #fff; background: #1a1d27; }
  .tab-btn:hover { color: #ccc; }
  .settings-group { margin-bottom: 1.5rem; }
  .settings-group h3 { font-size: 0.85rem; color: #60a5fa; margin-bottom: 0.75rem;
                        text-transform: uppercase; letter-spacing: 0.05em; }
  .setting-row { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 10px;
                 padding: 1rem; margin-bottom: 0.75rem; display: flex;
                 flex-wrap: wrap; align-items: center; gap: 0.75rem; }
  .setting-row label { flex: 1 1 200px; }
  .setting-row .label-text { font-weight: 500; font-size: 0.9rem; color: #fff; }
  .setting-row .help-text { font-size: 0.75rem; color: #666; margin-top: 2px; }
  .setting-row input { flex: 1 1 240px; background: #0f1117; border: 1px solid #2a2d3a;
                        border-radius: 6px; padding: 0.5rem 0.75rem; color: #e0e0e0;
                        font-size: 0.85rem; font-family: monospace; }
  .setting-row input:focus { outline: none; border-color: #60a5fa; }
  .status-pill { font-size: 0.7rem; padding: 2px 8px; border-radius: 12px; flex-shrink: 0; }
  .status-pill.set { background: #1a3a2a; color: #4ade80; }
  .status-pill.unset { background: #3a1a1a; color: #f87171; }
  .clear-btn { background: #3a1a1a; color: #f87171; border: none; border-radius: 6px;
               padding: 4px 10px; font-size: 0.75rem; cursor: pointer; flex-shrink: 0; }
</style>
</head>
<body>
<div class="header">
  <h1><span class="status-dot"></span>Agent System Dashboard</h1>
  <div style="display:flex;gap:1rem;align-items:center">
    <span id="last-updated">Loading...</span>
    <button class="refresh-btn" onclick="loadStats()">↻ Refresh</button>
  </div>
</div>

<div class="tabs">
  <button class="tab-btn active" onclick="showTab('overview', this)">📊 Overview</button>
  <button class="tab-btn" onclick="showTab('settings', this)">⚙️ Settings / API Keys</button>
</div>

<div id="tab-overview" class="tab-content">
<div class="grid" id="stat-cards">
  <div class="card"><h3>Status</h3><div class="value">🟢 Live</div><div class="sub">Running 24/7</div></div>
  <div class="card"><h3>Tasks</h3><div class="value" id="task-count">—</div><div class="sub">Total tasks</div></div>
  <div class="card"><h3>Memory</h3><div class="value" id="mem-size">—</div><div class="sub">Short-term rows</div></div>
  <div class="card"><h3>API Calls</h3><div class="value" id="api-calls">—</div><div class="sub">Last 50 logged</div></div>
</div>

<div class="section">
  <h2>AI Provider Stats</h2>
  <div class="api-grid" id="api-grid">Loading...</div>
</div>

<div class="section">
  <h2>Recent Tasks</h2>
  <table>
    <thead><tr><th>ID</th><th>Description</th><th>Agent</th><th>Status</th><th>Progress</th></tr></thead>
    <tbody id="tasks-tbody"><tr><td colspan="5" style="color:#555">Loading...</td></tr></tbody>
  </table>
</div>

<div class="section">
  <h2>Recent Activity</h2>
  <div id="recent-msgs">Loading...</div>
</div>
</div><!-- end tab-overview -->

<div id="tab-settings" class="tab-content" style="display:none">
  <div class="section">
    <div style="background:#1a2a3a;border:1px solid #2a3a5a;border-radius:10px;padding:1rem;margin-bottom:1.5rem;font-size:0.85rem;color:#aaa">
      💡 Paste your API keys here and click Save. No redeploy needed —
      changes apply within ~30 seconds. Keys are stored in your database, never shown in full again.
    </div>
    <div id="settings-groups"></div>
    <button class="refresh-btn" id="save-settings-btn" onclick="saveSettings()" style="margin-top:1rem">💾 Save Settings</button>
    <span id="save-status" style="margin-left:1rem;font-size:0.85rem;color:#4ade80"></span>
  </div>
</div>

<script>
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();

    document.getElementById('task-count').textContent = data.tasks?.length || 0;
    document.getElementById('mem-size').textContent = data.memory_rows || 0;
    document.getElementById('api-calls').textContent = data.total_api_calls || 0;
    document.getElementById('last-updated').textContent = 'Updated ' + new Date().toLocaleTimeString();

    // API providers
    const apiGrid = document.getElementById('api-grid');
    const providers = data.api_providers || {};
    if (Object.keys(providers).length === 0) {
      apiGrid.innerHTML = '<div style="color:#555;font-size:0.85rem">No API calls logged yet.</div>';
    } else {
      apiGrid.innerHTML = Object.entries(providers).map(([name, stats]) => {
        const rate = stats.calls > 0 ? Math.round((stats.success / stats.calls) * 100) : 0;
        return `<div class="api-card">
          <div class="name">${name}</div>
          <div class="calls">${stats.calls}</div>
          <div class="rate">${rate}% success · ${stats.tokens} tokens</div>
        </div>`;
      }).join('');
    }

    // Tasks
    const tbody = document.getElementById('tasks-tbody');
    const tasks = data.tasks || [];
    if (tasks.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" style="color:#555">No tasks yet. Use /task in Telegram.</td></tr>';
    } else {
      tbody.innerHTML = tasks.map(t => `
        <tr>
          <td style="font-family:monospace;color:#888">#${t.task_id}</td>
          <td>${(t.description||'').slice(0,60)}...</td>
          <td style="color:#888">${t.agent_id}</td>
          <td><span class="badge ${t.status}">${t.status}</span></td>
          <td>
            <div>${t.progress}%</div>
            <div class="progress-bar"><div class="progress-fill" style="width:${t.progress}%"></div></div>
          </td>
        </tr>
      `).join('');
    }

    // Recent messages
    const msgsEl = document.getElementById('recent-msgs');
    const msgs = data.recent_messages || [];
    if (msgs.length === 0) {
      msgsEl.innerHTML = '<div style="color:#555;font-size:0.85rem">No messages yet.</div>';
    } else {
      msgsEl.innerHTML = msgs.map(m => `
        <div class="msg-row">
          <span class="msg-role ${m.role}">${m.role}</span>
          <span class="msg-agent">[${m.agent_id||'?'}]</span>
          <span class="msg-content">${(m.content||'').slice(0,120)}${m.content?.length>120?'...':''}</span>
        </div>
      `).join('');
    }

  } catch(e) {
    console.error(e);
    document.getElementById('last-updated').textContent = 'Error loading data';
  }
}

loadStats();
setInterval(loadStats, 30000); // auto-refresh every 30 seconds

// ── Tabs ─────────────────────────────────────────────────────────────────
function showTab(name, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
  document.getElementById('tab-' + name).style.display = 'block';
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (name === 'settings') loadSettings();
}

// ── Settings / API Keys ──────────────────────────────────────────────────
async function loadSettings() {
  const container = document.getElementById('settings-groups');
  container.innerHTML = 'Loading...';
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    const groups = {};
    (data.fields || []).forEach(f => {
      groups[f.group] = groups[f.group] || [];
      groups[f.group].push(f);
    });

    container.innerHTML = Object.entries(groups).map(([groupName, fields]) => `
      <div class="settings-group">
        <h3>${groupName}</h3>
        ${fields.map(f => `
          <div class="setting-row">
            <label>
              <div class="label-text">${f.label}</div>
              <div class="help-text">${f.help}</div>
            </label>
            <input type="text" id="set_${f.key}" placeholder="${f.is_set ? f.current_masked : 'Not set — paste value here'}" autocomplete="off">
            <span class="status-pill ${f.is_set ? 'set':'unset'}">${f.is_set ? '✓ Set' : 'Not set'}</span>
            ${f.is_set ? `<button class="clear-btn" onclick="clearSetting('${f.key}')">Clear</button>` : ''}
          </div>
        `).join('')}
      </div>
    `).join('');
  } catch(e) {
    container.innerHTML = '<div style="color:#f87171">Failed to load settings: ' + e + '</div>';
  }
}

async function saveSettings() {
  const inputs = document.querySelectorAll('#settings-groups input');
  const payload = {};
  inputs.forEach(inp => {
    const key = inp.id.replace('set_', '');
    if (inp.value.trim() !== '') payload[key] = inp.value.trim();
  });

  const statusEl = document.getElementById('save-status');
  if (Object.keys(payload).length === 0) {
    statusEl.style.color = '#888';
    statusEl.textContent = 'Nothing to save — fields are empty.';
    return;
  }

  statusEl.style.color = '#60a5fa';
  statusEl.textContent = 'Saving...';
  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    statusEl.style.color = '#4ade80';
    statusEl.textContent = '✓ Saved: ' + (data.saved || []).join(', ') + ' — takes effect within 30s, no restart needed.';
    loadSettings();
  } catch(e) {
    statusEl.style.color = '#f87171';
    statusEl.textContent = 'Failed to save: ' + e;
  }
}

async function clearSetting(key) {
  if (!confirm('Clear ' + key + '? This will disable that provider/setting.')) return;
  await fetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({[key]: '__CLEAR__'})
  });
  loadSettings();
}
</script>
</body>
</html>
"""
