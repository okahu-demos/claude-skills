---
name: ok:pause
description: Save conversation context to SESSION.md for cross-session continuity
argument-hint: [app_folder]
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - AskUserQuestion
---

# ok:pause [app_folder]

Create a handoff in `.okahu/SESSION.md` to preserve work state across sessions.

**Use this when:**
- Ending a session mid-work
- Before running `/clear`
- Switching to a different task
- Any time you want to save conversation progress

## Process

### Step 1: Locate Session

```bash
# Find .okahu directories
find . -type d -name ".okahu" 2>/dev/null | head -5
```

If app_folder provided, use `{app_folder}/.okahu/`.
If multiple found, **USE AskUserQuestion** to select which session.

### Step 2: Read Current State

1. Read existing `.okahu/SESSION.md` if it exists
2. Read `.okahu/entry_points.json` for detected entry points
3. Read `.okahu/monocle_support.json` for framework detection
4. Check git status for uncommitted files:
   ```bash
   git status --porcelain 2>/dev/null | head -20
   ```

### Step 3: Gather Conversation Context

**Review the conversation since last /ok-* command and collect:**

1. **Commands run**: Which /ok-* commands were executed
2. **Findings**: What was discovered about the codebase
3. **Decisions made**: Choices about instrumentation approach, frameworks, entry points
4. **Issues encountered**: Errors, blockers, workarounds
5. **Questions answered**: User clarifications that informed the work
6. **Current position**: Where in the workflow (scan → instrument → run → trace)

**If any section is unclear, USE AskUserQuestion:**
```json
{
  "questions": [{
    "question": "Before I save the session, what were the key decisions or findings from our conversation?",
    "header": "Session Context",
    "multiSelect": false,
    "options": [
      {"label": "I'll describe them", "description": "Let me explain what we discussed"},
      {"label": "Just save what you observed", "description": "Use your best judgment from our chat"},
      {"label": "Nothing notable", "description": "Standard workflow, no special context"}
    ]
  }]
}
```

### Step 4: Write SESSION.md

Append a new session block to `.okahu/SESSION.md`:

```markdown
## Session: {YYYY-MM-DD HH:MM}

### Position
- **Stage**: {scan|instrument|run|trace}
- **Entry point**: {if identified}
- **Framework**: {if detected}

### Completed This Session
- {command or action taken}
- {command or action taken}

### Findings
- {discovery about codebase}
- {discovery about frameworks}

### Decisions Made
- {decision}: {rationale}

### Issues / Blockers
- {issue}: {status or workaround}

### Next Steps
1. {immediate next action}
2. {follow-up action}

### Context Notes
{Mental state, approach, anything a fresh Claude should know}

---
```

### Step 5: Confirm

```
✓ Session saved to .okahu/SESSION.md

Current state:
- Stage: {scan|instrument|run|trace}
- Entry point: {entry_point or "not yet identified"}
- Last command: {last /ok-* command}

To resume: /ok-resume {app_folder}
```

## SESSION.md Structure

The file accumulates session blocks over time:

```markdown
# Monocle Instrumentation Session

## Session Info
- **App**: {app_name}
- **Started**: {first session date}
- **Path**: {app_folder}

## Session: 2024-03-16 14:30

### Position
- **Stage**: scan
- **Entry point**: my_app:main

### Completed This Session
- /ok-scan - Found 3 entry points
- Selected my_app:main as primary

### Findings
- Uses LangChain for orchestration
- Custom OpenAI wrapper in utils/llm.py

### Decisions Made
- Use zero-code instrumentation (simpler setup)
- Focus on my_app:main entry point first

### Next Steps
1. Run /ok-instrument to generate okahu.yaml
2. Test with /ok-run

---

## Session: 2024-03-17 10:00

### Position
- **Stage**: instrument
...
```

## Usage Examples

```
/ok-pause                     # Auto-find session, save context
/ok-pause examples/           # Save session in examples folder
```

## Related Commands

- `/ok-resume` - Resume from saved session
- `/ok-scan` - Start or continue codebase analysis
- `/ok-instrument` - Add tracing configuration
