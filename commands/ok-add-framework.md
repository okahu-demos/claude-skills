---
name: ok:add-framework
description: Add instrumentation for a new AI/ML framework to monocle
argument-hint: <framework_name>
allowed-tools:
  - Read
  - Bash
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
  - Agent
  - WebSearch
---

# ok:add-framework

Add instrumentation support for a new AI/ML framework to monocle_apptrace.

## Overview

This skill creates the complete instrumentation package for a new framework following monocle's metamodel pattern. It generates:

1. `metamodel/<framework>/` folder structure
2. Helper functions for data extraction (`_helper.py`)
3. Method instrumentation definitions (`methods.py`)
4. Entity span definitions (`entities/*.py`)
5. Optional custom span handler (`<framework>_handler.py`)
6. Registration in `wrapper_method.py`

---

## Step 1: Gather Framework Information

**USE AskUserQuestion** to collect framework details:

```json
{
  "questions": [
    {
      "question": "What is the framework name?",
      "header": "Framework Name",
      "multiSelect": false,
      "options": []
    },
    {
      "question": "What is the pip package name?",
      "header": "Package Name",
      "multiSelect": false,
      "options": []
    },
    {
      "question": "What entity types does this framework have?",
      "header": "Entity Types",
      "multiSelect": true,
      "options": [
        {"label": "Agent", "description": "Autonomous agent that processes requests"},
        {"label": "Team/Crew", "description": "Multi-agent orchestration"},
        {"label": "Tool", "description": "Functions/tools invoked by agents"},
        {"label": "Inference", "description": "Direct LLM/model calls"},
        {"label": "Retrieval", "description": "Vector/RAG retrieval operations"}
      ]
    },
    {
      "question": "Create a new workspace at examples/<framework>_workspace?",
      "header": "Setup Workspace",
      "multiSelect": false,
      "options": [
        {"label": "Yes", "description": "Create isolated workspace with venv and install framework"},
        {"label": "No", "description": "Skip - framework already installed elsewhere"}
      ]
    },
    {
      "question": "Download runnable example code for this framework?",
      "header": "Example Code",
      "multiSelect": false,
      "options": [
        {"label": "Yes", "description": "Research and create working sample code"},
        {"label": "No", "description": "Skip - I'll provide my own test code"}
      ]
    }
  ]
}
```

---

## Step 2: Setup Workspace (if selected)

If user selected "Yes" to create workspace:

### 2.1 Create Workspace Directory

```bash
# Create workspace folder
mkdir -p examples/<framework>_workspace
cd examples/<framework>_workspace

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2.2 Install Framework

```bash
# Install the framework package
pip install <package>

# Verify installation - this MUST succeed before proceeding
python -c "import <package>; print(f'Installed: {<package>.__file__}')"
```

If verification fails, troubleshoot:
- Check package name spelling
- Try `pip install <package> --upgrade`
- Check for Python version requirements

### 2.3 Record Framework Location

Store the framework path for later analysis:
```bash
FRAMEWORK_PATH=$(python -c "import <package>; import os; print(os.path.dirname(<package>.__file__))")
echo "Framework source at: $FRAMEWORK_PATH"
```

---

## Step 3: Download Example Code (if selected)

If user selected "Yes" to download examples:

### 3.1 Research Framework Examples

**USE WebSearch** to find official examples:
- Search: `"<framework>" python example code tutorial`
- Search: `"<framework>" quickstart getting started`
- Check official docs, GitHub repos, blog posts

### 3.2 Create Example Script

Create `examples/<framework>_workspace/example_<use_case>.py`:

```python
"""
<Framework> example - <use_case description>
Auto-generated for monocle instrumentation testing.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Framework imports
from <package> import <classes>

# Example code here...
```

### 3.3 Handle Environment Variables

If the framework requires API keys or other env vars:

**USE AskUserQuestion** to prompt for required variables:

```json
{
  "questions": [
    {
      "question": "The framework requires environment variables. Please add them to examples/<framework>_workspace/.env file.\n\nRequired variables detected:\n- <VAR_NAME>: <description>\n\nHave you added the variables to .env?",
      "header": "Environment Setup",
      "multiSelect": false,
      "options": [
        {"label": "Yes, I've added the .env file", "description": "Continue to run the example"},
        {"label": "Skip for now", "description": "I'll add them later"}
      ]
    }
  ]
}
```

Create `.env.example` template:
```bash
# examples/<framework>_workspace/.env.example
# Copy this to .env and fill in your values

# Required for <framework>
OPENAI_API_KEY=your-api-key-here
# Add other required vars...
```

### 3.4 Run and Verify Example

```bash
cd examples/<framework>_workspace
source venv/bin/activate

# Source environment variables
set -a && source .env && set +a

# Run the example
python example_<use_case>.py
```

**Success criteria:**
- Script runs without import errors
- Framework initializes correctly
- If API calls are made, they return valid responses

If errors occur:
1. Check .env variables are set correctly
2. Verify package installation
3. Check API key permissions/quotas
4. Review error message and fix code

---

## Step 4: Analyze Framework Source

Explore the framework to identify instrumentable methods.

**If workspace was created**, the framework is at:
```bash
cd examples/<framework>_workspace
source venv/bin/activate
FRAMEWORK_PATH=$(python -c "import <package>; import os; print(os.path.dirname(<package>.__file__))")
```

**Otherwise**, find the framework's installed location:
```bash
python -c "import <package>; print(<package>.__file__)"

# Or search in common locations
find ~/.local/lib -name "<package>" -type d 2>/dev/null
find ./venv -name "<package>" -type d 2>/dev/null
```

### Key Classes to Find

| Entity Type | Look For | Common Method Names |
|-------------|----------|---------------------|
| Agent | `Agent`, `BaseAgent`, `Assistant` | `run`, `arun`, `invoke`, `ainvoke`, `execute` |
| Team | `Team`, `Crew`, `Swarm`, `Agency` | `run`, `kickoff`, `execute`, `orchestrate` |
| Tool | `Tool`, `BaseTool`, `Function` | `run`, `invoke`, `execute`, `_run`, `call` |
| Model/LLM | `Model`, `LLM`, `Chat`, `Client` | `invoke`, `generate`, `complete`, `chat` |
| Retrieval | `Retriever`, `VectorStore`, `Index` | `retrieve`, `search`, `query`, `get_relevant` |

### Identify Method Signatures

For each class, determine:
- **Package path**: e.g., `agno.agent`, `crewai.crew`
- **Class name**: e.g., `Agent`, `Crew`
- **Method name**: e.g., `run`, `arun`
- **Sync vs Async**: affects wrapper choice

---

## Step 5: Create Folder Structure

```
apptrace/src/monocle_apptrace/instrumentation/metamodel/<framework>/
├── __init__.py
├── _helper.py
├── methods.py
├── <framework>_handler.py  (optional)
└── entities/
    ├── __init__.py
    ├── agent.py      (if has agents)
    ├── team.py       (if has teams)
    ├── tool.py       (if has tools)
    └── inference.py  (if has LLM calls)
```

---

## Step 6: Create `__init__.py`

```python
# <framework> framework instrumentation
```

---

## Step 7: Create `_helper.py`

Template for helper functions:

```python
"""
Helper functions for <Framework> framework instrumentation.
Extracts relevant data from <Framework> Agent, Model, and Tool executions.
"""

import logging
from typing import Any, Dict, List, Optional

from monocle_apptrace.instrumentation.metamodel.finish_types import (
    FinishType,
    # Import provider-specific mapping if applicable:
    # OPENAI_FINISH_REASON_MAPPING,
    # ANTHROPIC_FINISH_REASON_MAPPING,
    # GEMINI_FINISH_REASON_MAPPING,
)

logger = logging.getLogger(__name__)

# Entity type keys - follow pattern: <entity>.<framework>
<FRAMEWORK>_AGENT_TYPE_KEY = "agent.<framework>"
<FRAMEWORK>_TEAM_TYPE_KEY = "team.<framework>"
<FRAMEWORK>_TOOL_TYPE_KEY = "tool.<framework>"


# =============================================================================
# AGENT HELPERS
# =============================================================================

def get_agent_name(instance) -> Optional[str]:
    """Extract agent name from Agent instance."""
    try:
        if hasattr(instance, 'name') and instance.name:
            return instance.name
        if hasattr(instance, 'id') and instance.id:
            return instance.id
        return type(instance).__name__
    except Exception as e:
        logger.debug(f"Error extracting agent name: {e}")
        return None


def get_agent_description(instance) -> Optional[str]:
    """Extract agent description from Agent instance."""
    try:
        if hasattr(instance, 'description') and instance.description:
            return instance.description
        return None
    except Exception as e:
        logger.debug(f"Error extracting agent description: {e}")
        return None


def get_agent_instructions(instance) -> Optional[str]:
    """Extract agent instructions/system prompt from Agent instance."""
    try:
        # Check common attribute names
        for attr in ['instructions', 'system_prompt', 'backstory', 'role']:
            if hasattr(instance, attr):
                val = getattr(instance, attr)
                if val:
                    if isinstance(val, list):
                        return " | ".join(str(i) for i in val[:3])  # Limit to 3
                    return str(val)[:500]  # Truncate to 500 chars
        return None
    except Exception as e:
        logger.debug(f"Error extracting agent instructions: {e}")
        return None


def extract_agent_input(arguments: Dict[str, Any]) -> Optional[str]:
    """Extract input from agent run arguments."""
    try:
        args = arguments.get('args', ())
        kwargs = arguments.get('kwargs', {})

        # Check positional args first
        if args and len(args) > 0:
            input_val = args[0]
            if isinstance(input_val, str):
                return input_val
            if hasattr(input_val, 'content'):
                return str(input_val.content)
            return str(input_val)[:1000]

        # Check kwargs for common input keys
        for key in ['input', 'message', 'query', 'prompt', 'task']:
            if key in kwargs:
                val = kwargs[key]
                if isinstance(val, str):
                    return val
                return str(val)[:1000]

        return None
    except Exception as e:
        logger.debug(f"Error extracting agent input: {e}")
        return None


def extract_agent_response(result) -> Optional[str]:
    """Extract response from agent run result."""
    try:
        if result is None:
            return None

        # Check for content attribute (common pattern)
        if hasattr(result, 'content'):
            content = result.content
            if isinstance(content, str):
                return content
            return str(content)[:2000]

        # Check for output/raw attributes
        for attr in ['output', 'raw', 'text', 'response']:
            if hasattr(result, attr):
                val = getattr(result, attr)
                if val:
                    return str(val)[:2000]

        # Direct string
        if isinstance(result, str):
            return result

        # Iterator/generator
        if hasattr(result, '__iter__') and hasattr(result, '__next__'):
            return "[streaming response]"

        return str(result)[:2000]
    except Exception as e:
        logger.debug(f"Error extracting agent response: {e}")
        return None


# =============================================================================
# INFERENCE/MODEL HELPERS
# =============================================================================

def get_model_name(instance) -> Optional[str]:
    """Extract model name from Model/LLM instance."""
    try:
        for attr in ['model', 'model_name', 'id', 'model_id']:
            if hasattr(instance, attr):
                val = getattr(instance, attr)
                if val:
                    return str(val)
        return type(instance).__name__
    except Exception as e:
        logger.debug(f"Error extracting model name: {e}")
        return None


def get_model_provider(instance) -> str:
    """Extract model provider from Model instance."""
    try:
        class_name = type(instance).__name__.lower()
        module_name = type(instance).__module__.lower()

        # Map class/module names to providers
        provider_patterns = {
            'openai': ['openai', 'gpt', 'chatgpt'],
            'anthropic': ['anthropic', 'claude'],
            'google': ['gemini', 'google', 'palm'],
            'aws_bedrock': ['bedrock', 'aws'],
            'azure_openai': ['azure'],
            'mistral': ['mistral'],
            'cohere': ['cohere'],
        }

        for provider, patterns in provider_patterns.items():
            if any(p in class_name or p in module_name for p in patterns):
                return provider

        return '<framework>'
    except Exception as e:
        logger.debug(f"Error extracting model provider: {e}")
        return '<framework>'


def extract_inference_input(arguments: Dict[str, Any]) -> Optional[str]:
    """Extract input messages from model invoke arguments."""
    try:
        args = arguments.get('args', ())
        kwargs = arguments.get('kwargs', {})
        messages = []

        # Check for messages in args
        if args:
            for arg in args:
                if isinstance(arg, list):
                    for msg in arg[:5]:  # Limit to first 5 messages
                        if hasattr(msg, 'content'):
                            messages.append(str(msg.content)[:500])
                        elif isinstance(msg, dict) and 'content' in msg:
                            messages.append(str(msg['content'])[:500])
                elif hasattr(arg, 'content'):
                    messages.append(str(arg.content)[:500])

        # Check kwargs
        for key in ['messages', 'input', 'prompt']:
            if key in kwargs:
                val = kwargs[key]
                if isinstance(val, list):
                    for msg in val[:5]:
                        if hasattr(msg, 'content'):
                            messages.append(str(msg.content)[:500])
                        elif isinstance(msg, dict) and 'content' in msg:
                            messages.append(str(msg['content'])[:500])
                elif isinstance(val, str):
                    messages.append(val[:500])

        return " | ".join(messages) if messages else None
    except Exception as e:
        logger.debug(f"Error extracting inference input: {e}")
        return None


def extract_inference_response(arguments: Dict[str, Any]) -> Optional[str]:
    """Extract response from model invoke result."""
    try:
        result = arguments.get('result')
        if result is None:
            return None

        # ModelResponse with content
        if hasattr(result, 'content'):
            content = result.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for item in content[:5]:
                    if hasattr(item, 'text'):
                        parts.append(item.text)
                    elif isinstance(item, str):
                        parts.append(item)
                return " ".join(parts)[:2000]
            return str(content)[:2000]

        if isinstance(result, str):
            return result

        return str(result)[:2000]
    except Exception as e:
        logger.debug(f"Error extracting inference response: {e}")
        return None


def extract_token_usage(result) -> Optional[Dict[str, Any]]:
    """Extract token usage from model response."""
    try:
        usage = {}

        # Check metrics attribute
        if hasattr(result, 'metrics'):
            metrics = result.metrics
            if hasattr(metrics, 'input_tokens'):
                usage['input_tokens'] = metrics.input_tokens
            if hasattr(metrics, 'output_tokens'):
                usage['output_tokens'] = metrics.output_tokens
            if hasattr(metrics, 'total_tokens'):
                usage['total_tokens'] = metrics.total_tokens

        # Check usage attribute (OpenAI style)
        if hasattr(result, 'usage'):
            u = result.usage
            if hasattr(u, 'prompt_tokens'):
                usage['input_tokens'] = u.prompt_tokens
            if hasattr(u, 'completion_tokens'):
                usage['output_tokens'] = u.completion_tokens
            if hasattr(u, 'total_tokens'):
                usage['total_tokens'] = u.total_tokens

        return usage if usage else None
    except Exception as e:
        logger.debug(f"Error extracting token usage: {e}")
        return None


def update_span_from_llm_response(result) -> Optional[Dict[str, Any]]:
    """Extract metadata from LLM response for span."""
    try:
        metadata = {}
        usage = extract_token_usage(result)
        if usage:
            metadata.update(usage)
        return metadata if metadata else None
    except Exception as e:
        logger.debug(f"Error updating span from LLM response: {e}")
        return None


def extract_finish_reason(arguments: Dict[str, Any]) -> Optional[str]:
    """Extract finish reason from model response."""
    try:
        result = arguments.get('result')
        if result is None:
            return None

        for attr in ['finish_reason', 'stop_reason', 'stop_message']:
            if hasattr(result, attr):
                return str(getattr(result, attr))

        # Check in metrics
        if hasattr(result, 'metrics') and hasattr(result.metrics, 'finish_reason'):
            return str(result.metrics.finish_reason)

        return None
    except Exception as e:
        logger.debug(f"Error extracting finish reason: {e}")
        return None


def map_finish_reason_to_finish_type(finish_reason: Optional[str]) -> Optional[str]:
    """Map framework finish reason to standardized finish type."""
    if not finish_reason:
        return None

    finish_reason_lower = finish_reason.lower()

    # Common mappings
    if any(kw in finish_reason_lower for kw in ['stop', 'end', 'complete', 'done']):
        return FinishType.SUCCESS.value
    if any(kw in finish_reason_lower for kw in ['length', 'token', 'max']):
        return FinishType.TRUNCATED.value
    if any(kw in finish_reason_lower for kw in ['tool', 'function']):
        return FinishType.TOOL_CALL.value
    if any(kw in finish_reason_lower for kw in ['filter', 'safety', 'block']):
        return FinishType.CONTENT_FILTER.value

    return None


# =============================================================================
# TOOL HELPERS
# =============================================================================

def get_tool_name(instance_or_call) -> Optional[str]:
    """Extract tool name from tool instance or function call."""
    try:
        # Direct name attribute
        if hasattr(instance_or_call, 'name') and instance_or_call.name:
            return instance_or_call.name

        # Function attribute with name
        if hasattr(instance_or_call, 'function') and instance_or_call.function:
            func = instance_or_call.function
            if hasattr(func, 'name') and func.name:
                return func.name

        return None
    except Exception as e:
        logger.debug(f"Error extracting tool name: {e}")
        return None


def get_tool_description(instance_or_call) -> Optional[str]:
    """Extract tool description from tool instance."""
    try:
        if hasattr(instance_or_call, 'description') and instance_or_call.description:
            return str(instance_or_call.description)[:500]

        if hasattr(instance_or_call, 'function') and instance_or_call.function:
            func = instance_or_call.function
            if hasattr(func, 'description') and func.description:
                return str(func.description)[:500]

        return None
    except Exception as e:
        logger.debug(f"Error extracting tool description: {e}")
        return None


def extract_tool_input(arguments: Dict[str, Any]) -> Optional[str]:
    """Extract tool input arguments."""
    try:
        args = arguments.get('args', ())
        kwargs = arguments.get('kwargs', {})

        # Check for arguments in function call
        if args and len(args) > 0:
            first_arg = args[0]
            if hasattr(first_arg, 'arguments') and first_arg.arguments:
                return str(first_arg.arguments)

        # Check kwargs for function_call
        function_call = kwargs.get('function_call')
        if function_call and hasattr(function_call, 'arguments'):
            return str(function_call.arguments)

        # Return all kwargs as input
        if kwargs:
            return str(kwargs)[:1000]

        return None
    except Exception as e:
        logger.debug(f"Error extracting tool input: {e}")
        return None


def extract_tool_response(result) -> Optional[str]:
    """Extract tool execution response."""
    try:
        if result is None:
            return None

        if hasattr(result, '__iter__') and hasattr(result, '__next__'):
            return "[streaming tool response]"

        if isinstance(result, str):
            return result[:2000]

        if hasattr(result, 'content'):
            return str(result.content)[:2000]

        return str(result)[:2000]
    except Exception as e:
        logger.debug(f"Error extracting tool response: {e}")
        return None


# =============================================================================
# TEAM HELPERS (if applicable)
# =============================================================================

def get_team_name(instance) -> Optional[str]:
    """Extract team name from Team instance."""
    try:
        if hasattr(instance, 'name') and instance.name:
            return instance.name
        if hasattr(instance, 'id') and instance.id:
            return instance.id
        return type(instance).__name__
    except Exception as e:
        logger.debug(f"Error extracting team name: {e}")
        return None


def get_team_mode(instance) -> Optional[str]:
    """Extract team orchestration mode."""
    try:
        if hasattr(instance, 'mode') and instance.mode:
            if hasattr(instance.mode, 'value'):
                return str(instance.mode.value)
            return str(instance.mode)
        return None
    except Exception as e:
        logger.debug(f"Error extracting team mode: {e}")
        return None


def get_team_members(instance) -> Optional[List[str]]:
    """Extract team member names."""
    try:
        for attr in ['members', 'agents', 'workers']:
            if hasattr(instance, attr):
                members = getattr(instance, attr)
                if callable(members):
                    return None
                member_names = []
                for member in list(members)[:10]:  # Limit to 10
                    name = getattr(member, 'name', None) or getattr(member, 'id', None)
                    if name:
                        member_names.append(str(name))
                return member_names if member_names else None
        return None
    except Exception as e:
        logger.debug(f"Error extracting team members: {e}")
        return None
```

---

## Step 8: Create Entity Definitions

### `entities/__init__.py`

```python
# <Framework> entity span definitions
```

### `entities/agent.py`

**IMPORTANT:** Agent instrumentation MUST define both `AGENT_REQUEST` (the `agentic.turn` parent) and `AGENT` (the `agentic.invocation` child). The `agentic.invocation` span is always a direct child of `agentic.turn` — this hierarchy is enforced via `output_processor_list` in `methods.py`.

```python
"""
<Framework> Agent entity processor for span creation.

Defines two entities used together via output_processor_list:
  - AGENT_REQUEST: agentic.turn (outer span — the user-facing turn)
  - AGENT:         agentic.invocation (inner span — the agent's processing)

The turn→invocation parent-child relationship is enforced by
methods.py using: output_processor_list: [AGENT_REQUEST, AGENT]
"""

from monocle_apptrace.instrumentation.common.constants import SPAN_SUBTYPES, SPAN_TYPES
from monocle_apptrace.instrumentation.common.utils import get_error_message
from monocle_apptrace.instrumentation.metamodel.<framework> import _helper

# ---------------------------------------------------------------------------
# AGENT (agentic.invocation) — always a direct child of AGENT_REQUEST
# Subtype: content_processing — the agent processing/handling content
# ---------------------------------------------------------------------------
AGENT = {
    "type": SPAN_TYPES.AGENTIC_INVOCATION,
    "subtype": SPAN_SUBTYPES.CONTENT_PROCESSING,
    "attributes": [
        [
            {
                "_comment": "agent type",
                "attribute": "type",
                "accessor": lambda arguments: _helper.<FRAMEWORK>_AGENT_TYPE_KEY
            },
            {
                "_comment": "name of the agent",
                "attribute": "name",
                "accessor": lambda arguments: _helper.get_agent_name(arguments['instance'])
            },
            {
                "_comment": "agent description",
                "attribute": "description",
                "accessor": lambda arguments: _helper.get_agent_description(arguments['instance'])
            },
            {
                "_comment": "agent instructions",
                "attribute": "instructions",
                "accessor": lambda arguments: _helper.get_agent_instructions(arguments['instance'])
            },
        ]
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "_comment": "agent input",
                    "attribute": "input",
                    "accessor": lambda arguments: _helper.extract_agent_input(arguments)
                }
            ]
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "attribute": "error_code",
                    "accessor": lambda arguments: get_error_message(arguments)
                },
                {
                    "_comment": "agent response",
                    "attribute": "response",
                    "accessor": lambda arguments: _helper.extract_agent_response(arguments['result'])
                }
            ]
        }
    ]
}

# ---------------------------------------------------------------------------
# AGENT_REQUEST (agentic.turn) — the outer parent span
# Subtype: turn — represents an external request/turn to the agent
# ---------------------------------------------------------------------------
AGENT_REQUEST = {
    "type": SPAN_TYPES.AGENTIC_REQUEST,
    "subtype": SPAN_SUBTYPES.TURN,
    "attributes": [
        [
            {
                "_comment": "agent type",
                "attribute": "type",
                "accessor": lambda arguments: _helper.<FRAMEWORK>_AGENT_TYPE_KEY
            }
        ]
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "_comment": "agent input",
                    "attribute": "input",
                    "accessor": lambda arguments: _helper.extract_agent_input(arguments)
                }
            ]
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "attribute": "error_code",
                    "accessor": lambda arguments: get_error_message(arguments)
                },
                {
                    "_comment": "agent response",
                    "attribute": "response",
                    "accessor": lambda arguments: _helper.extract_agent_response(arguments['result'])
                }
            ]
        }
    ]
}
```

### `entities/inference.py`

```python
"""
<Framework> Model inference entity processor for span creation.
"""

from monocle_apptrace.instrumentation.common.constants import SPAN_TYPES
from monocle_apptrace.instrumentation.common.utils import get_error_message
from monocle_apptrace.instrumentation.metamodel.<framework> import _helper

INFERENCE = {
    "type": SPAN_TYPES.INFERENCE,
    "attributes": [
        [
            {
                "_comment": "provider type",
                "attribute": "type",
                "accessor": lambda arguments: 'inference.' + _helper.get_model_provider(arguments['instance'])
            },
            {
                "attribute": "provider_name",
                "accessor": lambda arguments: _helper.get_model_provider(arguments['instance'])
            },
        ],
        [
            {
                "_comment": "LLM Model",
                "attribute": "name",
                "accessor": lambda arguments: _helper.get_model_name(arguments['instance'])
            },
            {
                "attribute": "type",
                "accessor": lambda arguments: 'model.llm.' + (_helper.get_model_name(arguments['instance']) or 'unknown')
            }
        ],
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "_comment": "LLM input",
                    "attribute": "input",
                    "accessor": lambda arguments: _helper.extract_inference_input(arguments)
                }
            ]
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "attribute": "error_code",
                    "accessor": lambda arguments: get_error_message(arguments)
                },
                {
                    "_comment": "LLM response",
                    "attribute": "response",
                    "accessor": lambda arguments: _helper.extract_inference_response(arguments)
                }
            ]
        },
        {
            "name": "metadata",
            "attributes": [
                {
                    "_comment": "token usage",
                    "accessor": lambda arguments: _helper.update_span_from_llm_response(arguments['result'])
                },
                {
                    "attribute": "finish_reason",
                    "accessor": lambda arguments: _helper.extract_finish_reason(arguments)
                },
                {
                    "attribute": "finish_type",
                    "accessor": lambda arguments: _helper.map_finish_reason_to_finish_type(
                        _helper.extract_finish_reason(arguments)
                    )
                }
            ]
        }
    ]
}
```

### `entities/tool.py`

```python
"""
<Framework> Tool invocation entity processor for span creation.
"""

from monocle_apptrace.instrumentation.common.constants import SPAN_SUBTYPES, SPAN_TYPES
from monocle_apptrace.instrumentation.common.utils import get_error_message
from monocle_apptrace.instrumentation.metamodel.<framework> import _helper

TOOL = {
    "type": SPAN_TYPES.AGENTIC_TOOL_INVOCATION,
    "subtype": SPAN_SUBTYPES.CONTENT_GENERATION,
    "attributes": [
        [
            {
                "_comment": "tool type",
                "attribute": "type",
                "accessor": lambda arguments: _helper.<FRAMEWORK>_TOOL_TYPE_KEY
            },
            {
                "_comment": "name of the tool",
                "attribute": "name",
                "accessor": lambda arguments: _helper.get_tool_name(arguments.get('instance') or arguments.get('kwargs', {}).get('function_call'))
            },
            {
                "_comment": "tool description",
                "attribute": "description",
                "accessor": lambda arguments: _helper.get_tool_description(arguments.get('instance') or arguments.get('kwargs', {}).get('function_call'))
            }
        ]
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "_comment": "tool input",
                    "attribute": "input",
                    "accessor": lambda arguments: _helper.extract_tool_input(arguments)
                }
            ]
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "_comment": "tool response",
                    "attribute": "response",
                    "accessor": lambda arguments: _helper.extract_tool_response(arguments['result'])
                },
                {
                    "attribute": "error_code",
                    "accessor": lambda arguments: get_error_message(arguments)
                }
            ]
        }
    ]
}
```

### `entities/team.py` (if applicable)

Like agents, teams should also use `output_processor_list` in `methods.py` to create the turn→invocation hierarchy.

```python
"""
<Framework> Team entity processor for span creation.

Defines two entities used together via output_processor_list:
  - TEAM_REQUEST: agentic.turn (outer span)
  - TEAM:         agentic.invocation (inner span — routing subtype for orchestration)
"""

from monocle_apptrace.instrumentation.common.constants import SPAN_SUBTYPES, SPAN_TYPES
from monocle_apptrace.instrumentation.common.utils import get_error_message
from monocle_apptrace.instrumentation.metamodel.<framework> import _helper

# ---------------------------------------------------------------------------
# TEAM (agentic.invocation) — always a direct child of TEAM_REQUEST
# Subtype: routing — the team orchestrates/routes across agents
# ---------------------------------------------------------------------------
TEAM = {
    "type": SPAN_TYPES.AGENTIC_INVOCATION,
    "subtype": SPAN_SUBTYPES.ROUTING,
    "attributes": [
        [
            {
                "_comment": "team type",
                "attribute": "type",
                "accessor": lambda arguments: _helper.<FRAMEWORK>_TEAM_TYPE_KEY
            },
            {
                "_comment": "name of the team",
                "attribute": "name",
                "accessor": lambda arguments: _helper.get_team_name(arguments['instance'])
            },
            {
                "_comment": "team mode",
                "attribute": "mode",
                "accessor": lambda arguments: _helper.get_team_mode(arguments['instance'])
            },
        ]
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "_comment": "team input",
                    "attribute": "input",
                    "accessor": lambda arguments: _helper.extract_agent_input(arguments)
                }
            ]
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "attribute": "error_code",
                    "accessor": lambda arguments: get_error_message(arguments)
                },
                {
                    "_comment": "team response",
                    "attribute": "response",
                    "accessor": lambda arguments: _helper.extract_agent_response(arguments['result'])
                }
            ]
        }
    ]
}

# ---------------------------------------------------------------------------
# TEAM_REQUEST (agentic.turn) — the outer parent span
# ---------------------------------------------------------------------------
TEAM_REQUEST = {
    "type": SPAN_TYPES.AGENTIC_REQUEST,
    "subtype": SPAN_SUBTYPES.TURN,
    "attributes": [
        [
            {
                "_comment": "team type",
                "attribute": "type",
                "accessor": lambda arguments: _helper.<FRAMEWORK>_TEAM_TYPE_KEY
            }
        ]
    ],
    "events": [
        {
            "name": "data.input",
            "attributes": [
                {
                    "_comment": "team input",
                    "attribute": "input",
                    "accessor": lambda arguments: _helper.extract_agent_input(arguments)
                }
            ]
        },
        {
            "name": "data.output",
            "attributes": [
                {
                    "attribute": "error_code",
                    "accessor": lambda arguments: get_error_message(arguments)
                },
                {
                    "_comment": "team response",
                    "attribute": "response",
                    "accessor": lambda arguments: _helper.extract_agent_response(arguments['result'])
                }
            ]
        }
    ]
}
```

---

## Step 9: Create `methods.py`

```python
"""
<Framework> framework method instrumentation definitions.
"""

from monocle_apptrace.instrumentation.common.wrapper import (
    task_wrapper,
    atask_wrapper,
    atask_iter_wrapper,
)
from monocle_apptrace.instrumentation.metamodel.<framework>.entities.agent import AGENT, AGENT_REQUEST
from monocle_apptrace.instrumentation.metamodel.<framework>.entities.inference import INFERENCE
# Import other entities as needed:
# from monocle_apptrace.instrumentation.metamodel.<framework>.entities.team import TEAM
# from monocle_apptrace.instrumentation.metamodel.<framework>.entities.tool import TOOL

<FRAMEWORK>_METHODS = [
    # Agent execution (sync)
    # Uses output_processor_list to create agentic.turn → agentic.invocation hierarchy
    {
        "package": "<package.module>",
        "object": "Agent",
        "method": "run",
        "wrapper_method": task_wrapper,
        "span_handler": "<framework>_handler",  # or "default"
        "output_processor_list": [AGENT_REQUEST, AGENT],
    },
    # Agent execution (async)
    # Uses output_processor_list to create agentic.turn → agentic.invocation hierarchy
    {
        "package": "<package.module>",
        "object": "Agent",
        "method": "arun",
        "wrapper_method": atask_iter_wrapper,  # or atask_wrapper
        "span_handler": "<framework>_handler",
        "output_processor_list": [AGENT_REQUEST, AGENT],
    },
    # Model inference (sync)
    {
        "package": "<package.models>",
        "object": "Model",
        "method": "invoke",
        "wrapper_method": task_wrapper,
        "span_handler": "non_framework_handler",
        "output_processor": INFERENCE,
    },
    # Model inference (async)
    {
        "package": "<package.models>",
        "object": "Model",
        "method": "ainvoke",
        "wrapper_method": atask_wrapper,
        "span_handler": "non_framework_handler",
        "output_processor": INFERENCE,
    },
]
```

**IMPORTANT: `output_processor_list` vs `output_processor`**

| Key | Use When | Creates |
|-----|----------|---------|
| `output_processor_list` | Agent methods — need turn→invocation hierarchy | Nested spans: first item is parent, second is child |
| `output_processor` | Leaf spans (inference, tools) — no nesting needed | Single span |

Agent methods MUST use `output_processor_list: [AGENT_REQUEST, AGENT]` so that `agentic.invocation` is always a direct child of `agentic.turn`. The wrapper recursively processes the list, creating the parent-child hierarchy via OpenTelemetry's span context.

### Wrapper Method Selection Guide

| Method Type | Wrapper |
|-------------|---------|
| Sync, returns value | `task_wrapper` |
| Async, returns value | `atask_wrapper` |
| Async, yields/streams | `atask_iter_wrapper` |
| Sets scope only (no span) | `scope_wrapper` |

### Span Handler Selection Guide

| Handler | Use When |
|---------|----------|
| `"default"` | Standard span handling |
| `"non_framework_handler"` | Direct LLM calls (skips events if framework is wrapping) |
| `"<framework>_handler"` | Custom pre/post tracing logic needed |

---

## Step 10: Create Custom Handler (Optional)

Only create if you need custom pre/post tracing logic (e.g., session scope management):

```python
"""Custom span handler for <Framework> to maintain trace context."""

from monocle_apptrace.instrumentation.common.constants import AGENT_SESSION, AGENT_INVOCATION_SPAN_NAME
from monocle_apptrace.instrumentation.common.span_handler import SpanHandler
from monocle_apptrace.instrumentation.common.utils import set_scope


class <Framework>SpanHandler(SpanHandler):
    """Custom span handler for <Framework> instrumentation."""

    def pre_tracing(self, to_wrap, wrapped, instance, args, kwargs):
        """Set session scope before tracing begins."""
        session_token = None

        class_name = instance.__class__.__name__ if hasattr(instance, '__class__') else ''

        # Example: Set session scope for Team/multi-agent
        if class_name == 'Team':
            session_id = kwargs.get('session_id') or getattr(instance, 'session_id', None)
            if session_id:
                session_token = set_scope(AGENT_SESSION, session_id)
            else:
                team_id = getattr(instance, 'id', None) or getattr(instance, 'name', None) or str(id(instance))
                session_token = set_scope(AGENT_SESSION, f"team_{team_id}")

        elif class_name == 'Agent':
            session_id = kwargs.get('session_id')
            if session_id:
                session_token = set_scope(AGENT_SESSION, session_id)
            else:
                session_token = set_scope(AGENT_INVOCATION_SPAN_NAME, str(id(instance)))

        return session_token, None
```

---

## Step 11: Register in `wrapper_method.py`

Edit `apptrace/src/monocle_apptrace/instrumentation/common/wrapper_method.py`:

### Add Import (around line 50)

```python
from monocle_apptrace.instrumentation.metamodel.<framework>.methods import <FRAMEWORK>_METHODS
from monocle_apptrace.instrumentation.metamodel.<framework>.<framework>_handler import <Framework>SpanHandler  # if custom handler
```

### Add to DEFAULT_METHODS_LIST (around line 130)

```python
DEFAULT_METHODS_LIST = (
    LANGCHAIN_METHODS +
    # ... existing methods ...
    AGNO_METHODS +
    <FRAMEWORK>_METHODS  # Add here
)
```

### Register Handler (around line 163)

```python
MONOCLE_SPAN_HANDLERS: Dict[str, SpanHandler] = {
    # ... existing handlers ...
    "agno_handler": AgnoSpanHandler(),
    "<framework>_handler": <Framework>SpanHandler()  # Add here
}
```

---

## Step 12: Test the Instrumentation

Create a test script:

```python
from monocle_apptrace import setup_monocle_telemetry
from monocle_apptrace.exporters import ConsoleSpanExporter

# Setup with console exporter for testing
setup_monocle_telemetry(
    workflow_name="<framework>_test",
    span_processors=[ConsoleSpanExporter()]
)

# Import and use the framework
from <package> import Agent

agent = Agent(name="test_agent")
result = agent.run("Hello, world!")
print(result)
```

### Verify Spans

Check that spans are created with:
- Correct `span.type` values
- Correct `entity.N.type` keys
- `data.input` and `data.output` events
- Token usage in metadata (for inference spans)

---

## Span Naming Quick Reference

### SPAN_TYPES

| Constant | Value | Use For |
|----------|-------|---------|
| `AGENTIC_REQUEST` | `agentic.turn` | Agent turn (outer parent span) |
| `AGENTIC_INVOCATION` | `agentic.invocation` | Agent processing (always direct child of `agentic.turn`) |
| `AGENTIC_TOOL_INVOCATION` | `agentic.tool.invocation` | Tool invoked by agent |
| `AGENTIC_MCP_INVOCATION` | `agentic.mcp.invocation` | MCP tool execution |
| `INFERENCE` | `inference` | Direct LLM inference |
| `INFERENCE_FRAMEWORK` | `inference.framework` | LLM via orchestration |
| `RETRIEVAL` | `retrieval` | Vector retrieval |
| `HTTP_PROCESS` | `http.process` | HTTP route processing |
| `HTTP_SEND` | `http.send` | Client HTTP request |

### SPAN_SUBTYPES

| Constant | Value | Use For |
|----------|-------|---------|
| `TURN` | `turn` | External request/turn (`agentic.turn` spans) |
| `CONTENT_PROCESSING` | `content_processing` | Agent processing content (`agentic.invocation` spans) |
| `ROUTING` | `routing` | Routing/orchestration decisions (teams, delegation) |
| `CONTENT_GENERATION` | `content_generation` | Generating content (tool invocations) |
| `PLANNING` | `planning` | Agentic planning |
| `COMMUNICATION` | `communication` | Returning info |
| `GENERIC` | `generic` | Generic/unclassified |

### Entity Type Patterns

| Entity | Pattern | Examples |
|--------|---------|----------|
| Agent | `agent.<framework>` | `agent.agno`, `agent.crewai` |
| Team | `team.<framework>` | `team.agno` |
| Tool | `tool.<framework>` | `tool.agno`, `tool.function` |
| Inference | `inference.<provider>` | `inference.openai`, `inference.anthropic` |
| Model | `model.llm.<name>` | `model.llm.gpt-4` |

### Verbosity Limits

| Data Type | Limit |
|-----------|-------|
| Input strings | 1000 chars |
| Output strings | 2000 chars |
| Instructions | 500 chars, first 3 items if list |
| Messages | First 5 only |
| Team members | First 10 only |

---

## Step 13: Update SESSION.md

After completing framework instrumentation, **write/update `.okahu/SESSION.md`** — update the "Framework Support Added" section:

```markdown
## Framework Support Added
_Updated by: /ok-add-framework_
- **Framework**: <name> (<package>)
- **Entity types**: Agent, Tool, Inference, Team (as applicable)
- **Methods file**: metamodel/<framework>/methods.py
- **Handler**: <framework>_handler (custom) / default
- **Registered in**: wrapper_method.py
```

## Related Commands

- `/ok-scan` - Analyze codebase for instrumentation points
- `/ok-instrument` - Add tracing to your app
- `/ok-run` - Execute app with tracing enabled
- `/ok-local-trace` - View traces from `.monocle/` folder
- `/ok-pause` - Save session before stopping work
- `/ok-resume` - Resume from saved session
