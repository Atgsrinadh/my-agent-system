"""
agents/registry.py — All built-in specialist agents.
Each agent has a system prompt, name, and description.
Custom agents are loaded from Turso database at runtime.
"""
from api_router import call_ai
from memory import build_full_context, short_save, long_remember, working_set
import json, time

# ── Built-in agent definitions ─────────────────────────────────────────────
BUILTIN_AGENTS = {
    "research": {
        "name": "Research Agent",
        "emoji": "🔬",
        "description": "Deep topic research, fact finding, academic papers",
        "system": """You are an expert research agent. Your job is to:
- Research topics deeply and thoroughly
- Find relevant facts, data, and insights  
- Reference key sources and explain concepts clearly
- Save important findings to memory
- Structure your response with clear sections
Always be thorough, accurate, and cite the basis of your knowledge."""
    },
    "writer": {
        "name": "Writer Agent",
        "emoji": "✍️",
        "description": "Essays, reports, summaries, emails, papers",
        "system": """You are a professional writer agent. You:
- Write clear, well-structured documents
- Adapt tone to purpose (academic, casual, professional)
- Create summaries, essays, reports, emails, research papers
- Edit and improve existing text
- Format output clearly with proper structure"""
    },
    "coder": {
        "name": "Coder Agent",
        "emoji": "💻",
        "description": "Write, debug, review, explain code in any language",
        "system": """You are an expert software engineer. You:
- Write clean, efficient, well-commented code
- Debug and fix errors with clear explanations
- Support all major languages (Python, JS, Go, Rust, etc.)
- Review code for bugs, security issues, and best practices
- Explain technical concepts clearly
Always provide working code with explanations."""
    },
    "analyst": {
        "name": "Data Analyst Agent",
        "emoji": "📊",
        "description": "Analyse data, Excel, CSV, numbers, find patterns",
        "system": """You are a data analyst agent. You:
- Analyse structured data (tables, CSVs, Excel files)
- Find patterns, trends, and anomalies
- Provide statistical insights and summaries
- Suggest visualisations and interpretations
- Answer specific data questions clearly
Always provide actionable insights from the data."""
    },
    "vision": {
        "name": "Vision Agent",
        "emoji": "👁️",
        "description": "Read images, diagrams, screenshots, charts",
        "system": """You are a vision analysis agent. You:
- Describe images in detail
- Extract text from images and screenshots
- Analyse charts, graphs, and diagrams
- Identify objects, people, scenes, and context
- Answer questions about visual content"""
    },
    "pdf_reader": {
        "name": "PDF Reader Agent",
        "emoji": "📄",
        "description": "Extract, analyse, and answer questions from PDFs",
        "system": """You are a document analysis agent. You:
- Extract and summarise content from documents
- Answer specific questions about document content
- Find key information, dates, names, figures
- Compare multiple documents
- Identify important sections and structure"""
    },
    "web_search": {
        "name": "Web Search Agent",
        "emoji": "🌐",
        "description": "Search live internet for current information",
        "system": """You are a web research agent. You:
- Search for current, up-to-date information
- Synthesise information from multiple sources
- Find news, events, prices, and recent data
- Verify facts and check current status
- Provide source references for all claims"""
    },
    "summariser": {
        "name": "Summariser Agent",
        "emoji": "📝",
        "description": "Compress long content into clear summaries",
        "system": """You are a summarisation specialist. You:
- Condense long documents, articles, and conversations
- Extract the most important points
- Create structured bullet summaries
- Preserve all key facts and figures
- Adjust detail level based on request"""
    },
    "planner": {
        "name": "Planner Agent",
        "emoji": "🗓️",
        "description": "Break big goals into actionable task plans",
        "system": """You are a strategic planning agent. You:
- Break complex goals into clear action steps
- Create timelines and priorities
- Identify dependencies and blockers
- Assign tasks to appropriate specialist agents
- Track progress and adjust plans
Always create numbered, actionable plans."""
    },
    "critic": {
        "name": "Critic Agent",
        "emoji": "🔍",
        "description": "Review and critique any content, plan, or code",
        "system": """You are a critical review agent. You:
- Identify weaknesses, gaps, and errors
- Provide constructive, specific feedback
- Check logic, consistency, and accuracy
- Suggest concrete improvements
- Evaluate quality objectively
Be specific and actionable in all feedback."""
    },
    "memory_agent": {
        "name": "Memory Agent",
        "emoji": "🧠",
        "description": "Organise and retrieve your stored knowledge",
        "system": """You are the memory management agent. You:
- Organise and categorise stored information
- Retrieve specific facts on request
- Identify what should be remembered long-term
- Clean and deduplicate stored data
- Answer questions from memory store"""
    },
    "general": {
        "name": "General Agent",
        "emoji": "🤖",
        "description": "General assistant — handles anything",
        "system": """You are a highly capable general AI assistant. You:
- Answer any question clearly and helpfully
- Adapt to any task or topic
- Provide thoughtful, accurate responses
- Ask for clarification when needed
- Be conversational and friendly"""
    }
}

# ── Orchestrator: pick best agent for a task ───────────────────────────────
def route_to_agent(message: str, available_custom: list = []) -> str:
    agent_names = list(BUILTIN_AGENTS.keys()) + [a["name"] for a in available_custom]
    names_str = ", ".join(agent_names)

    result = call_ai(
        messages=[{"role": "user", "content": message}],
        system=f"""You are a routing agent. Pick the best agent for this message.
Available agents: {names_str}
Reply with ONLY the agent key name (e.g. 'research', 'coder', 'writer').
For custom agents, reply with their exact name.
Default to 'general' if unsure."""
    )
    chosen = result.strip().lower().split()[0]
    if chosen in BUILTIN_AGENTS or any(a["name"] == chosen for a in available_custom):
        return chosen
    return "general"

# ── Run any agent (builtin or custom) ─────────────────────────────────────
def run_agent(agent_id: str, user_id: str, message: str,
              file_content: str = None, custom_agent: dict = None) -> tuple[str, str]:
    """
    Run an agent and return (response, agent_name).
    Handles memory context building and saving automatically.
    """
    # Build context from memory
    context, history = build_full_context(user_id, agent_id)

    # Get system prompt
    if custom_agent:
        system = custom_agent["system_prompt"]
        agent_name = custom_agent["name"]
        agent_emoji = "🛠️"
    elif agent_id in BUILTIN_AGENTS:
        agent_info = BUILTIN_AGENTS[agent_id]
        system = agent_info["system"]
        agent_name = agent_info["name"]
        agent_emoji = agent_info["emoji"]
    else:
        agent_info = BUILTIN_AGENTS["general"]
        system = agent_info["system"]
        agent_name = agent_info["name"]
        agent_emoji = agent_info["emoji"]

    # Inject memory context into system prompt
    if context:
        system = f"{system}\n\n{context}"

    # Build user message
    user_content = message
    if file_content:
        user_content = f"{message}\n\n--- File Content ---\n{file_content}"

    # Add to history
    history.append({"role": "user", "content": user_content})

    # Call AI
    response = call_ai(messages=history, system=system)

    # Save to short-term memory
    short_save(user_id, "user", message, agent_id)
    short_save(user_id, "assistant", response, agent_id)

    # Auto-extract facts for long-term memory
    _extract_facts_async(user_id, agent_id, message, response)

    return response, f"{agent_emoji} {agent_name}"

def _extract_facts_async(user_id: str, agent_id: str, user_msg: str, bot_msg: str):
    """Extract important facts and save to long-term memory."""
    try:
        combined = f"User: {user_msg}\nAgent: {bot_msg}"
        facts_json = call_ai(
            messages=[{"role": "user", "content": combined}],
            system="""Extract important facts worth remembering long-term.
Return ONLY a JSON array like: [{"category":"research","key":"topic_name","value":"key finding"}]
Return [] if nothing important. Keep each value under 200 chars."""
        )
        facts_json = facts_json.strip()
        if facts_json.startswith("["):
            facts = json.loads(facts_json)
            for f in facts[:5]:  # max 5 facts per message
                long_remember(user_id, f.get("category","general"),
                              f.get("key",""), f.get("value",""), agent_id)
    except:
        pass

# ── Multi-agent team ───────────────────────────────────────────────────────
def run_team(user_id: str, task: str) -> str:
    """
    Orchestrate multiple agents working together on a complex task.
    Research → Write → Critique → Final output.
    """
    results = {}

    # Step 1: Research
    research_response, _ = run_agent("research", user_id, f"Research this thoroughly: {task}")
    results["research"] = research_response
    working_set("team", "research_done", research_response[:500])

    # Step 2: Write based on research
    write_prompt = f"Write a comprehensive response about: {task}\n\nResearch findings:\n{research_response}"
    write_response, _ = run_agent("writer", user_id, write_prompt)
    results["written"] = write_response

    # Step 3: Critic reviews
    critic_prompt = f"Review this response for accuracy and completeness:\n\n{write_response}"
    critic_response, _ = run_agent("critic", user_id, critic_prompt)
    results["critique"] = critic_response

    # Step 4: Final refined output
    final_prompt = f"""Original task: {task}
Draft: {write_response}
Critique: {critic_response}
Now write the final, improved version addressing all critique points."""
    final_response, _ = run_agent("writer", user_id, final_prompt)

    return f"🔬 Research → ✍️ Written → 🔍 Reviewed → ✅ Final\n\n{final_response}"
