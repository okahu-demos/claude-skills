---
name: ok:generate-tests
description: Generate monocle test_tools tests for an agent app
argument-hint: [app_folder]
allowed-tools:
  - Read
  - Bash
  - Write
  - Edit
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
---

# ok:generate-tests [app_folder]

Generate comprehensive monocle test_tools tests for an agent application. Discovers the app's agents, tools, entry points, and framework — then generates test files covering all applicable assertion categories.

## Prerequisites

- The target app must be a Python agent application (LangGraph, Google ADK, CrewAI, LlamaIndex, etc.)
- `monocle_test_tools` must be installed in the app's environment
- The app must have at least one agent with tools

## Step 1: Discover the App

If no app folder provided, **USE AskUserQuestion** to ask:

```json
{
  "questions": [{
    "question": "Which app folder should I generate tests for?",
    "header": "App Folder",
    "multiSelect": false,
    "options": []
  }]
}
```

Then analyze the app to extract:

1. **Framework**: Detect which agent framework is used (LangGraph, Google ADK, CrewAI, LlamaIndex, Strands, etc.) by scanning imports
2. **Agent type string**: The `agent_type` parameter for `run_agent_async()`:
   - `from langgraph` → `"langgraph"`
   - `from google.adk` or `google.genai` → `"google_adk"`
   - `from crewai` → `"crewai"`
   - `from llama_index` → `"llamaindex"`
   - `from strands` → `"strands"`
3. **Agents**: All agent names (the `name=` parameter in agent creation)
4. **Tools**: All tool names (the `name` in `@tool()` decorator or tool definition)
5. **Agent-tool mapping**: Which agent uses which tools
6. **Agent hierarchy**: Supervisor/coordinator → sub-agents (if multi-agent)
7. **Entry point**: The main agent or supervisor to invoke, and any individual agents available
8. **Setup function**: How agents are created (async? returns what?)
9. **Python environment**: Find the venv (`<app>/.venv/bin/python` or system python)
10. **Existing tests**: Check `tests/` for existing `okahu_*` files to avoid overwriting

## Step 2: Present Discovery and Choose Directives

Show the user what was discovered:

```
Discovered app structure:
  Framework:   LangGraph
  Supervisor:  travel_supervisor
  Agents:      flight_assistant, hotel_assistant
  Tools:       book_flight (→ flight_assistant), book_hotel (→ hotel_assistant)
  Entry point: setup_agents() → supervisor
  Python:      .venv/bin/python
```

Then **USE AskUserQuestion** to let user select test categories:

```json
{
  "questions": [{
    "question": "Which test categories should I generate?",
    "header": "Test Directives",
    "multiSelect": true,
    "options": [
      {"label": "1. Agent & Tool Routing (Recommended)", "description": "Verify correct agents/tools are called for each request type — positive AND negative cases"},
      {"label": "2. Input Validation", "description": "Verify inputs are forwarded correctly — has_input, contains_input, does_not_contain_input, etc."},
      {"label": "3. Output Validation", "description": "Verify outputs contain expected content — contains_output, does_not_contain_output, etc."},
      {"label": "4. Performance", "description": "Token limits and duration checks for single/multi-agent scenarios"},
      {"label": "5. Quality Assessment (requires OKAHU_API_KEY)", "description": "Sentiment, bias, hallucination, frustration, toxicity, etc. via Okahu assessor"},
      {"label": "6. Multi-task Orchestration", "description": "Complex requests involving multiple agents — verify routing, output, and performance together"},
      {"label": "7. Individual Agent Testing", "description": "Test each sub-agent in isolation (bypassing supervisor)"},
      {"label": "All", "description": "Generate all test categories"}
    ]
  }]
}
```

## Step 3: Generate Tests

For each selected directive, generate a test file prefixed with `okahu_` in the app's `tests/` directory.

**CRITICAL RULES:**
- Never overwrite existing files. If `okahu_test_routing.py` exists, warn and skip or ask.
- All test files must use the `monocle_trace_asserter` pytest fixture (provided by monocle_test_tools)
- Use `@pytest.mark.asyncio` for all tests
- Use the correct `agent_type` string for the detected framework
- Use the actual agent/tool names discovered from the app
- Add `pytestmark = pytest.mark.skipif(not os.getenv("OKAHU_API_KEY"), reason="OKAHU_API_KEY not set")` to assessment test files
- Generate realistic, diverse user prompts appropriate to the app's domain
- Each test function should test ONE clear behavior

### Conftest

If `tests/conftest.py` doesn't exist, create it:

```python
import os
import sys
import pytest
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def pytest_configure(config):
    env_test_path = Path(__file__).parent.parent / '.env.test'
    if env_test_path.exists():
        load_dotenv(env_test_path)
    monocle_env_path = Path(__file__).parent.parent / '.env.monocle'
    if monocle_env_path.exists():
        load_dotenv(monocle_env_path)
```

If it already exists, leave it alone.

### File Structure

Each test file follows this pattern:

```python
import pytest
import pytest_asyncio
from monocle_test_tools import TraceAssertion
from <app_module> import <setup_function>

# Global agent references
supervisor = None
# ... other agents if available for individual testing

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_agents_fixture():
    global supervisor  # and other agents
    supervisor = await <setup_function>()  # adapt to app's actual setup

# ... test functions ...

if __name__ == "__main__":
    pytest.main([__file__])
```

---

## Directive Details — Assertion Reference

Use the following assertion methods from the `TraceAssertion` fluent API. Each directive section shows WHICH assertions to use and HOW to combine them.

### Directive 1: Agent & Tool Routing

**File**: `okahu_test_routing.py`

Tests that the correct agents and tools are invoked (positive) and that unrelated agents/tools are NOT invoked (negative).

**Assertions used:**
- `called_tool(tool_name, agent_name)` — tool was called by the expected agent
- `does_not_call_tool(tool_name)` — tool was NOT called
- `called_agent(agent_name)` — agent was invoked
- `does_not_call_agent(agent_name)` — agent was NOT invoked

**Test patterns — generate BOTH positive and negative for each agent/tool pair:**

```python
# POSITIVE: When request matches agent's domain, it IS called
async def test_<domain>_request_calls_<agent>(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<domain-specific request>")
    monocle_trace_asserter.called_tool("<tool_name>", "<agent_name>")
    monocle_trace_asserter.called_agent("<agent_name>")

# NEGATIVE: When request does NOT match agent's domain, it is NOT called
async def test_<other_domain>_request_does_not_call_<agent>(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<other-domain request>")
    monocle_trace_asserter.does_not_call_tool("<tool_name>")
    monocle_trace_asserter.does_not_call_agent("<agent_name>")
```

Generate at least:
- 1 positive routing test per agent/tool
- 1 negative routing test per agent/tool (request goes to a DIFFERENT agent)
- For multi-agent apps: 1 test where ALL agents are called together

### Directive 2: Input Validation

**File**: `okahu_test_input_validation.py`

Verify that user inputs are correctly forwarded to agents and tools.

**Assertions used:**
- `has_input(expected)` — exact input match
- `has_any_input(*inputs)` — any of several inputs match
- `does_not_have_input(unexpected)` — input does NOT match
- `does_not_have_any_input(*inputs)` — NONE of the inputs match
- `contains_input(substring)` — input contains substring (most common)
- `contains_any_input(*substrings)` — input contains any of these substrings
- `does_not_contain_input(substring)` — input does NOT contain substring
- `does_not_contain_any_input(*substrings)` — input contains NONE of these

**Test patterns:**

```python
# POSITIVE: Key parameters appear in tool input
async def test_<tool>_receives_<param>(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request with specific params>")
    monocle_trace_asserter.called_tool("<tool>", "<agent>") \
        .contains_input("<param_value_1>") \
        .contains_input("<param_value_2>")

# POSITIVE: Agent receives the full user request
async def test_<agent>_receives_user_request(monocle_trace_asserter):
    request = "<user request>"
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", request)
    monocle_trace_asserter.called_agent("<agent>") \
        .contains_input("<key phrase from request>")

# NEGATIVE: Unrelated params do NOT appear
async def test_<tool>_does_not_receive_<wrong_param>(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request>")
    monocle_trace_asserter.called_tool("<tool>", "<agent>") \
        .does_not_contain_input("<unrelated param>")
```

### Directive 3: Output Validation

**File**: `okahu_test_output_validation.py`

Verify that agent/tool outputs contain expected content.

**Assertions used:**
- `has_output(expected)` — exact output match
- `has_any_output(*outputs)` — output matches any of these
- `does_not_have_output(unexpected)` — output does NOT match
- `does_not_have_any_output(*outputs)` — output matches NONE of these
- `contains_output(substring)` — output contains substring (most common)
- `contains_any_output(*substrings)` — output contains any of these
- `does_not_contain_output(substring)` — output does NOT contain substring
- `does_not_contain_any_output(*substrings)` — output contains NONE of these

**Test patterns:**

```python
# POSITIVE: Tool output has confirmation keywords
async def test_<tool>_output_confirms_action(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request>")
    monocle_trace_asserter.called_tool("<tool>", "<agent>") \
        .contains_output("<confirmation keyword>") \
        .contains_output("<key entity from request>")

# POSITIVE: Output matches at least one expected phrase
async def test_<agent>_output_has_any_confirmation(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request>")
    monocle_trace_asserter.called_agent("<agent>") \
        .contains_any_output("<phrase1>", "<phrase2>", "<phrase3>")

# NEGATIVE: Tool output does not leak unrelated domain terms
async def test_<tool>_output_excludes_<other_domain>_terms(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<single-domain request>")
    monocle_trace_asserter.called_tool("<tool>", "<agent>") \
        .does_not_contain_output("<other domain term 1>") \
        .does_not_contain_output("<other domain term 2>")

# NEGATIVE: Output does not contain error indicators
async def test_output_has_no_error_indicators(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request>")
    monocle_trace_asserter.does_not_have_any_output("ERROR", "FAILED", "REJECTED")
```

### Directive 4: Performance

**File**: `okahu_test_performance.py`

Verify token usage and execution duration stay within bounds.

**Assertions used:**
- `under_token_limit(limit)` — total tokens under limit
- `under_duration(limit, units="seconds", span_type="workflow")` — execution time under limit
  - `units`: `"seconds"` (default), `"ms"`, `"minutes"`
  - `span_type`: `"workflow"` (default), `"inference"`, `"agent_invocation"`, `"tool_invocation"`, `"agent_turn"`

**IMPORTANT**: `under_duration` checks `span_type="workflow"` by default. When chained after `called_tool()`, the filtered spans are tool spans, not workflow spans — so `under_duration` will fail. Always call `under_duration` on a fresh asserter or specify the correct `span_type`.

**Test patterns:**

```python
# Single-agent token limit
async def test_single_<agent>_token_limit(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<single-agent request>")
    monocle_trace_asserter.under_token_limit(3000)

# Multi-agent token limit (higher budget)
async def test_multi_agent_token_limit(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<multi-agent request>")
    monocle_trace_asserter.under_token_limit(8000)

# Duration limit — workflow level
async def test_<scenario>_duration_limit(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request>")
    monocle_trace_asserter.under_duration(60)

# Duration limit — per span type
async def test_inference_duration_limit(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request>")
    monocle_trace_asserter.under_duration(5000, units="ms", span_type="inference")

# Chained on filtered agent
async def test_<agent>_invocation_duration(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request>")
    monocle_trace_asserter.called_agent("<agent>") \
        .under_duration(0.2, units="minutes", span_type="agent_invocation")

# Individual agent performance (if sub-agents accessible)
async def test_individual_<agent>_performance(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(<sub_agent>, "<framework>", "<request>")
    monocle_trace_asserter.called_tool("<tool>", "<agent>") \
        .contains_output("<confirmation>")
    monocle_trace_asserter.under_token_limit(2000) \
        .under_duration(30)
```

### Directive 5: Quality Assessment

**File**: `okahu_test_assessment.py`

Run LLM-based quality assessments on traces using the Okahu service.

**Assertions used:**
- `with_evaluation("okahu")` — configure the Okahu assessor (required before check_eval)
- `check_eval(eval_name, expected, not_expected, fact_name)` — run assessment and assert result
  - `eval_name`: the assessment template — see list below
  - `expected`: string or list of acceptable values (positive assertion)
  - `not_expected`: string or list of unacceptable values (negative assertion)
  - `fact_name`: what to assess — `"traces"` (default), `"inferences"`, `"conversations"`, `"agent_sessions"`

**Available assessment templates and expected values:**

| Template | Fact Names | Positive Values | Negative Values |
|----------|-----------|-----------------|-----------------|
| `sentiment` | traces, inferences, conversations | `"positive"`, `"neutral"` | `"negative"` |
| `bias` | traces, agent_sessions | `"unbiased"` | `"biased"` |
| `hallucination` | traces, agent_sessions | `"no_hallucination"` | `"hallucination"` |
| `frustration` | traces, conversations | `"ok"` | `"frustrated"` |
| `toxicity` | traces, agent_sessions | `"non_toxic"` | `"highly_toxic"`, `"moderately_toxic"`, `"mildly_toxic"` |
| `contextual_precision` | traces | `"high_precision"` | `"low_precision"` |
| `contextual_relevancy` | traces, agent_sessions | `"highly_relevant"` | `"not_relevant"` |
| `conversation_completeness` | traces, agent_sessions | `"complete"` | `"incomplete"` |
| `summarization` | traces | `"excellent"` | `"poor"` |
| `offtopic` | conversations | `"on_topic"` | `"off_topic"` |
| `role_adherence` | agent_sessions | `"excellent_adherence"`, `"good_adherence"` | `"poor_adherence"`, `"no_adherence"` |
| `misuse` | agent_sessions | — | `"clear_misuse"`, `"potential_misuse"` |
| `pii_leakage` | agent_sessions | — | `"pii_leakage"` |

**Test patterns:**

```python
# POSITIVE: Expect good sentiment
async def test_<scenario>_sentiment(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request>")
    monocle_trace_asserter.with_evaluation("okahu") \
        .check_eval("sentiment", "positive")

# NEGATIVE: Should NOT be toxic
async def test_<scenario>_not_toxic(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request>")
    monocle_trace_asserter.with_evaluation("okahu") \
        .check_eval("toxicity", not_expected=["highly_toxic", "moderately_toxic", "mildly_toxic"])

# Chained multi-assessment
async def test_<scenario>_quality_suite(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request>")
    monocle_trace_asserter.with_evaluation("okahu") \
        .check_eval("sentiment", "positive") \
        .check_eval("bias", "unbiased") \
        .check_eval("hallucination", "no_hallucination") \
        .check_eval("frustration", "ok")

# Assessment on filtered agent spans
async def test_<agent>_quality(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request>")
    monocle_trace_asserter.called_agent("<agent>")
    monocle_trace_asserter.with_evaluation("okahu") \
        .check_eval("conversation_completeness", "complete")

# Assessment with specific fact_name
async def test_agent_sessions_safety(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>", "<request>")
    monocle_trace_asserter.with_evaluation("okahu") \
        .check_eval(fact_name="agent_sessions", eval_name="misuse", not_expected=["clear_misuse", "potential_misuse"]) \
        .check_eval(fact_name="agent_sessions", eval_name="pii_leakage", not_expected="pii_leakage") \
        .check_eval(fact_name="agent_sessions", eval_name="role_adherence", expected=["excellent_adherence", "good_adherence"])
```

### Directive 6: Multi-task Orchestration

**File**: `okahu_test_multi_task.py`

Complex requests that exercise multiple agents together. Combines routing, output, and performance assertions.

**Test patterns:**

```python
# All agents called + correct outputs
async def test_combined_request_routes_all_agents(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>",
        "<complex request touching all agents>")
    # Verify each agent's tool was called with correct input/output
    monocle_trace_asserter.called_tool("<tool_1>", "<agent_1>") \
        .contains_input("<param>") \
        .contains_output("<confirmation>")
    monocle_trace_asserter.called_tool("<tool_2>", "<agent_2>") \
        .contains_input("<param>") \
        .contains_output("<confirmation>")

# Combined with performance bounds
async def test_combined_request_within_budget(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(supervisor, "<framework>",
        "<multi-agent request>")
    monocle_trace_asserter.called_tool("<tool_1>", "<agent_1>").contains_output("<confirmation>")
    monocle_trace_asserter.called_tool("<tool_2>", "<agent_2>").contains_output("<confirmation>")
    monocle_trace_asserter.under_token_limit(8000) \
        .under_duration(120)
```

### Directive 7: Individual Agent Testing

**File**: `okahu_test_individual_agents.py`

Test each sub-agent directly (bypassing the supervisor). Only possible if the setup function exposes individual agents.

**Test patterns:**

```python
# Direct agent invocation
async def test_<agent>_direct_invocation(monocle_trace_asserter):
    await monocle_trace_asserter.run_agent_async(<agent_var>, "<framework>",
        "<domain-specific request>")
    monocle_trace_asserter.called_tool("<tool>", "<agent>") \
        .contains_output("<confirmation>")
    monocle_trace_asserter.under_token_limit(2000) \
        .under_duration(30)
```

## Step 4: Run Tests

After generating all files, run the test suite:

```bash
cd <app_folder> && <python> -m pytest tests/okahu_*.py -v 2>&1
```

If any tests fail:
1. Analyze the failure — is it a test bug or an app bug?
2. Fix test bugs (wrong tool name, wrong span_type chain, etc.)
3. Report app bugs to the user without auto-fixing

## Step 5: Show Summary

After all tests pass, show a summary:

```
Test generation complete.

  Files created:
    tests/okahu_test_routing.py              — 6 tests (3 positive, 3 negative)
    tests/okahu_test_input_validation.py     — 5 tests (3 positive, 2 negative)
    tests/okahu_test_output_validation.py    — 7 tests (4 positive, 3 negative)
    tests/okahu_test_performance.py          — 7 tests (token + duration)
    tests/okahu_test_assessment.py           — 8 tests (skipped without OKAHU_API_KEY)
    tests/okahu_test_multi_task.py           — 4 tests (combined scenarios)
    tests/okahu_test_individual_agents.py    — 3 tests (per-agent isolation)

  Total: 40 tests — 38 passed, 0 failed, 2 skipped

  Next steps:
    Set OKAHU_API_KEY to enable assessment tests
    Run: <python> -m pytest tests/okahu_*.py -v
```

## Important Notes

- **Prompt variety**: Generate diverse, realistic user prompts. Don't reuse the same city/entity across tests — use a wide variety appropriate to the app's domain.
- **Assertion chaining**: The fluent API returns a new `TraceAssertion` scoped to matching spans. Chain assertions that operate on the SAME spans. Start a new chain from `monocle_trace_asserter` for assertions on DIFFERENT spans.
- **under_duration gotcha**: `under_duration` defaults to `span_type="workflow"`. After `called_tool()`, the filtered spans are tool spans — use `span_type="tool_invocation"` or start a new chain.
- **Assessment cleanup**: The assessor is set once with `with_evaluation("okahu")` and persists for subsequent `check_eval` calls on the same asserter instance.
- **File safety**: NEVER overwrite existing files. Check first.

## Related Commands

- `/ok-scan` — Scan codebase for instrumentation
- `/ok-instrument` — Add tracing to app
- `/ok-run` — Run app with tracing
- `/ok-local-trace` — View traces
