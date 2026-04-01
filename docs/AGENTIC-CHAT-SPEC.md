# Hephaestus Agentic Chat Mode — Specification

## Overview

After generating an invention, pressing [7] enters an **agentic chat** where the model has tools — not just conversational ability. The agent can research, write code, search the web, save files, and iterate on the invention with real-world grounding.

## Current State (v1 — Conversational Only)
- User presses [7] → enters chat with invention context loaded
- Model can discuss the invention but cannot take actions
- No memory between chat turns beyond the conversation itself

## Target State (v2 — Fully Agentic)
- User presses [7] → enters agentic session with tools
- Agent has full invention context PLUS ability to act
- Agent can proactively suggest actions ("Want me to prototype this?")

---

## Tool Registry

### 1. `web_search` — Perplexity Deep Research
```
Purpose: Research feasibility, find prior art, validate claims
Trigger: "search for...", "is there anything like...", "find papers on..."
Implementation: Call Perplexity API with sonar model
Returns: Structured search results with citations
```

### 2. `write_code` — Generate Implementation
```
Purpose: Write a proof-of-concept, prototype, or simulation
Trigger: "write code for...", "implement...", "prototype..."
Implementation: Generate code using the current model, save to ~/.hephaestus/prototypes/
Returns: File path + code preview
```

### 3. `save_note` — Persist Insights
```
Purpose: Save observations, refinements, or decisions to disk
Trigger: "remember that...", "note that...", "save this..."
Implementation: Append to ~/.hephaestus/notes/<invention-slug>.md
Returns: Confirmation with file path
```

### 4. `refine_invention` — Re-run Translation
```
Purpose: Re-run Stage 4 with new constraints from the conversation
Trigger: "refine this with...", "what if we changed...", "try a different approach"
Implementation: Call translator with updated constraints, display new result
Returns: New invention inline in chat
```

### 5. `calculate` — Math Validation
```
Purpose: Validate equations, compute thresholds, run numerical checks
Trigger: "calculate...", "what's the math on...", "verify this equation"
Implementation: Python eval in sandboxed environment (ast.literal_eval for safety)
Returns: Computation result
```

### 6. `read_file` — Access Local Files
```
Purpose: Read invention reports, prototypes, or notes
Trigger: "show me the...", "what did we save...", "read the prototype"
Implementation: Read from ~/.hephaestus/ directory tree
Returns: File contents
```

### 7. `compare_inventions` — Side-by-Side Analysis
```
Purpose: Compare current invention with a previous one
Trigger: "compare this with...", "how does this differ from..."
Implementation: Load two InventionReports, generate structured comparison
Returns: Comparison table
```

### 8. `export` — Generate Deliverables
```
Purpose: Export invention as markdown, PDF, JSON, or presentation
Trigger: "export as...", "create a PDF...", "make a slide deck"
Implementation: Use existing formatter + weasyprint
Returns: File path
```

---

## Agent Architecture

### Tool Dispatch
The agent doesn't parse tool calls from raw text. Instead, it uses **Claude's native tool_use** via the Anthropic API:

```python
tools = [
    {
        "name": "web_search",
        "description": "Search the web for prior art, feasibility data, or related work",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    },
    # ... other tools
]

response = client.messages.create(
    model="claude-opus-4-6",
    system=agent_system_prompt,
    messages=conversation_history,
    tools=tools,
    max_tokens=4096,
)
```

When Claude returns a `tool_use` content block, the agent:
1. Extracts the tool name and input
2. Executes the tool function
3. Returns the result as a `tool_result` message
4. Continues the conversation

### Agent Loop
```
while True:
    user_input = get_input()
    messages.append({"role": "user", "content": user_input})
    
    while True:  # tool loop
        response = call_api(messages, tools)
        
        if response has tool_use blocks:
            for tool_call in response.tool_use_blocks:
                result = execute_tool(tool_call)
                messages.append(tool_result)
            continue  # let model process results
        
        else:
            display(response.text)
            break  # back to user input
```

### System Prompt for Agent Mode
```
You are Hephaestus in agent mode. You have just generated an invention and the user 
wants to explore, validate, refine, or implement it. You have tools available.

USE TOOLS PROACTIVELY when they would help:
- If the user asks about feasibility → search for related work
- If the user asks "can this be built?" → write a prototype
- If the user says "remember this" → save a note
- If the user wants changes → refine the invention

Do NOT ask permission to use tools. Just use them. Then explain what you found/did.

INVENTION CONTEXT:
{full_invention_context}
```

---

## Implementation Plan

### File: `src/hephaestus/cli/agent_chat.py`

New module, ~300-400 lines:
- `AgentChat` class with tool registry
- Tool functions (web_search, write_code, save_note, etc.)
- Agent loop with tool dispatch
- Integration with ClaudeMaxAdapter (tool_use requires passing tools to API)

### Changes to existing files:
- `claude_max.py` — add `generate_with_tools()` method that passes `tools` param
- `repl.py` — update option [7] to call `AgentChat` instead of simple chat

### Dependencies:
- No new dependencies (Perplexity API already available, file I/O is stdlib)

### Estimated Build Time:
- Agent loop + tool dispatch: ~2 hours
- Tool implementations: ~2 hours
- Integration + testing: ~1 hour
- Total: ~5 hours

---

## Open Questions

1. **Tool approval**: Should tools auto-execute or ask user first? (Recommend: auto-execute with confirmation for destructive actions like file writes)
2. **Cost tracking**: Each tool call that hits an API (web_search, refine) costs subscription tokens. Show running cost?
3. **Session persistence**: Should agent chat history persist across heph restarts? (Recommend: yes, save to session JSON)
4. **Code execution**: Should `write_code` also RUN the code? (Recommend: write only, user runs manually for safety)
5. **Multi-agent**: Should the agent be able to spawn sub-agents (e.g., "research this in depth" spawns a Perplexity deep research agent)? (Recommend: v3 feature)
