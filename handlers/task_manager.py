"""
handlers/task_manager.py — Long-running task system.
Assign tasks, agents keep working 24/7.
You check status from any device anytime.
Tasks persist in Supabase — survive server restarts.
"""
import os, asyncio, uuid, json
from datetime import datetime
from db_clients import sb
from api_router import call_ai
from memory import short_save, long_remember, working_set, working_get

# ── Task status constants ──────────────────────────────────────────────────
STATUS_PENDING   = "pending"
STATUS_RUNNING   = "running"
STATUS_DONE      = "done"
STATUS_FAILED    = "failed"
STATUS_PAUSED    = "paused"

def create_task(user_id: str, description: str, agent_id: str = "research") -> str:
    task_id = str(uuid.uuid4())[:8].upper()
    try:
        sb.table("tasks").insert({
            "task_id": task_id,
            "user_id": str(user_id),
            "description": description,
            "agent_id": agent_id,
            "status": STATUS_PENDING,
            "progress": 0,
            "result": None,
            "steps": json.dumps([]),
        }).execute()
    except Exception as e:
        print(f"create_task error: {e}")
    return task_id

def update_task(task_id: str, status: str = None, progress: int = None,
                result: str = None, step: str = None):
    update = {}
    if status:
        update["status"] = status
    if progress is not None:
        update["progress"] = progress
    if result:
        update["result"] = result
    if step:
        try:
            r = sb.table("tasks").select("steps").eq("task_id", task_id).execute()
            steps = json.loads(r.data[0]["steps"]) if r.data else []
            steps.append({"time": datetime.now().isoformat(), "step": step})
            update["steps"] = json.dumps(steps[-20:])  # keep last 20 steps
        except:
            pass
    try:
        if update:
            sb.table("tasks").update(update).eq("task_id", task_id).execute()
    except Exception as e:
        print(f"update_task error: {e}")

def get_task(task_id: str) -> dict | None:
    try:
        r = sb.table("tasks").select("*").eq("task_id", task_id).execute()
        return r.data[0] if r.data else None
    except:
        return None

def get_all_tasks(user_id: str, status: str = None) -> list:
    try:
        q = sb.table("tasks").select("task_id,description,agent_id,status,progress,created_at")\
            .eq("user_id", str(user_id))
        if status:
            q = q.eq("status", status)
        r = q.order("created_at", desc=True).limit(20).execute()
        return r.data or []
    except:
        return []

def delete_task(task_id: str):
    try:
        sb.table("tasks").delete().eq("task_id", task_id).execute()
    except:
        pass

async def run_task_async(task_id: str, user_id: str, send_fn=None):
    """
    Execute a long-running task with step-by-step progress.
    Sends Telegram updates as it progresses.
    """
    task = get_task(task_id)
    if not task:
        return

    description = task["description"]
    agent_id = task.get("agent_id", "research")

    update_task(task_id, status=STATUS_RUNNING, progress=5, step="Task started")

    try:
        # Step 1: Plan the task
        if send_fn:
            await send_fn(f"📋 Task #{task_id} started\n🔄 Planning steps...")

        plan = call_ai(
            messages=[{"role": "user", "content": description}],
            system="""Break this task into 3-5 clear numbered steps.
Return ONLY a JSON array of step strings.
Example: ["Step 1: Research X", "Step 2: Analyse Y", "Step 3: Write summary"]"""
        )
        try:
            steps = json.loads(plan.strip())
        except:
            steps = [f"Step 1: {description}"]

        update_task(task_id, progress=15, step=f"Plan created: {len(steps)} steps")

        # Step 2: Execute each step
        all_results = []
        for i, step in enumerate(steps):
            pct = 20 + int((i / len(steps)) * 60)
            update_task(task_id, progress=pct, step=f"Executing: {step}")

            if send_fn:
                await send_fn(f"⚙️ Task #{task_id} — Step {i+1}/{len(steps)}\n{step}")

            step_result = call_ai(
                messages=[{"role": "user", "content": f"Task: {description}\n\nExecute this step: {step}"}],
                system=f"You are completing step {i+1} of a multi-step task. Be thorough and specific."
            )
            all_results.append(f"### {step}\n{step_result}")
            working_set(task_id, f"step_{i+1}", step_result[:300])

        # Step 3: Synthesise final result
        update_task(task_id, progress=85, step="Synthesising final result")

        combined = "\n\n".join(all_results)
        final = call_ai(
            messages=[{"role": "user", "content": f"Task: {description}\n\nAll step results:\n{combined}"}],
            system="Synthesise all step results into one clear, comprehensive final answer."
        )

        # Step 4: Save to memory
        long_remember(user_id, "task_results", f"task_{task_id}", final[:500])
        short_save(user_id, "assistant", f"[Task #{task_id} completed]\n{final}", agent_id, task_id)

        update_task(task_id, status=STATUS_DONE, progress=100,
                   result=final, step="Task completed successfully")

        if send_fn:
            await send_fn(
                f"✅ Task #{task_id} COMPLETE!\n\n"
                f"📋 {description[:100]}...\n\n"
                f"{final[:1500]}"
                + ("\n\n[Truncated — use /task {task_id} for full result]"
                   if len(final) > 1500 else "")
            )

    except Exception as e:
        update_task(task_id, status=STATUS_FAILED, step=f"Error: {str(e)}")
        if send_fn:
            await send_fn(f"❌ Task #{task_id} failed: {str(e)}")

def format_task_status(tasks: list) -> str:
    if not tasks:
        return "No tasks found."

    status_emoji = {
        STATUS_PENDING: "⏳",
        STATUS_RUNNING: "🔄",
        STATUS_DONE:    "✅",
        STATUS_FAILED:  "❌",
        STATUS_PAUSED:  "⏸️",
    }

    lines = ["📋 Your Tasks:\n"]
    for t in tasks:
        emoji = status_emoji.get(t["status"], "❓")
        pct = t.get("progress", 0)
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        lines.append(
            f"{emoji} #{t['task_id']} [{bar}] {pct}%\n"
            f"   {t['description'][:60]}...\n"
            f"   Agent: {t['agent_id']} | Status: {t['status']}\n"
        )
    return "\n".join(lines)
