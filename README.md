# Okahu — Claude Code Skills

Add observability to your Python apps using Claude Code slash commands. Scan your codebase, add tracing, run with telemetry, and view traces — all from the CLI.

Instrumentation is powered by [Monocle2AI](https://github.com/monocle2ai/monocle).

## Install

```
/plugin marketplace add okahu-demos/claude-skills
/plugin install okahu@claude-skills
```

## Commands

### Instrumentation workflow

| Command | Description |
|---------|-------------|
| `/ok-scan [path]` | Scan codebase to recommend what to trace. Detects frameworks (LangChain, OpenAI, Flask, etc.) and entry points. |
| `/ok-find [query]` | Find methods by search or exact name, then trace execution paths back to entry points. |
| `/ok-instrument [path]` | Add tracing — zero-code (generates `okahu.yaml`) or code-based (injects setup code). |
| `/ok-run [command]` | Run your app with tracing enabled. Auto-detects instrumentation approach. |
| `/ok-local-trace [query]` | View local traces from `.monocle/` folder. Supports natural language queries. |

### Session management

| Command | Description |
|---------|-------------|
| `/ok-pause [path]` | Save conversation context to `SESSION.md` for cross-session continuity. |
| `/ok-resume [path]` | Resume an instrumentation session from saved context. |

### Other

| Command | Description |
|---------|-------------|
| `/ok-login [env]` | Authenticate with Okahu Cloud via GitHub Device Flow. |
| `/ok-add-framework <name>` | Add instrumentation support for a new AI/ML framework. |
| `/kahu <query>` | Query the Okahu SRE Agent API (natural language). |

## Typical workflow

```
/ok-scan ./my-app          # Analyze codebase, pick entry points
/ok-instrument ./my-app    # Generate tracing config
/ok-run                    # Run with tracing enabled
/ok-local-trace            # View collected traces
```

## Supported frameworks (auto-instrumented)

| Category | Frameworks |
|----------|------------|
| LLM | OpenAI, Anthropic, Azure AI, Bedrock, Gemini, LiteLLM, Mistral, HuggingFace |
| Agents | LangChain, LlamaIndex, LangGraph, CrewAI, Haystack, OpenAI Agents, AutoGen |
| HTTP | Flask, FastAPI, AIOHTTP |
| Cloud | Azure Functions, AWS Lambda |
| MCP | FastMCP, MCP SDK |

## Requirements

- Python 3.9+
- `monocle_apptrace` package (`pip install monocle_apptrace`)
- For cloud tracing: Okahu API key (get one via `/ok-login`)

## License

Apache-2.0
