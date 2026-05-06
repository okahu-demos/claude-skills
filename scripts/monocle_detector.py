#!/usr/bin/env python3
"""
Monocle Framework Detector - Detect monocle-supported frameworks in a codebase.

Scans Python files for imports of frameworks that monocle auto-instruments.

Usage:
    python monocle_detector.py /path/to/app
    python monocle_detector.py /path/to/app --output .okahu/monocle_support.json

Output: JSON with detected frameworks and recommendations
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


# Frameworks that monocle auto-instruments
AUTO_INSTRUMENTED = {
    # LLM Inference
    "openai": {
        "category": "LLM Inference",
        "name": "OpenAI",
        "imports": ["openai"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    "anthropic": {
        "category": "LLM Inference",
        "name": "Anthropic Claude",
        "imports": ["anthropic"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    "azure_openai": {
        "category": "LLM Inference",
        "name": "Azure OpenAI",
        "imports": ["azure.ai.openai", "openai.lib.azure"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    "bedrock": {
        "category": "LLM Inference",
        "name": "AWS Bedrock",
        "imports": ["boto3"],
        "pattern": r"client\s*\(\s*['\"]bedrock",
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    "gemini": {
        "category": "LLM Inference",
        "name": "Google Gemini",
        "imports": ["google.generativeai", "vertexai"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    "litellm": {
        "category": "LLM Inference",
        "name": "LiteLLM",
        "imports": ["litellm"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    "mistral": {
        "category": "LLM Inference",
        "name": "Mistral AI",
        "imports": ["mistralai"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    "huggingface": {
        "category": "LLM Inference",
        "name": "HuggingFace",
        "imports": ["transformers", "huggingface_hub"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    # Agent Frameworks
    "langchain": {
        "category": "Agent Framework",
        "name": "LangChain",
        "imports": ["langchain", "langchain_core", "langchain_community", "langchain_openai"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    "llamaindex": {
        "category": "Agent Framework",
        "name": "LlamaIndex",
        "imports": ["llama_index"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    "langgraph": {
        "category": "Agent Framework",
        "name": "LangGraph",
        "imports": ["langgraph"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    "crewai": {
        "category": "Agent Framework",
        "name": "CrewAI",
        "imports": ["crewai"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    "haystack": {
        "category": "Agent Framework",
        "name": "Haystack",
        "imports": ["haystack"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    "autogen": {
        "category": "Agent Framework",
        "name": "AutoGen",
        "imports": ["autogen", "pyautogen"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
    # HTTP Frameworks
    "flask": {
        "category": "HTTP Framework",
        "name": "Flask",
        "imports": ["flask"],
        "action": "Auto-instrumented, use @monocle_trace_http_route for routes"
    },
    "fastapi": {
        "category": "HTTP Framework",
        "name": "FastAPI",
        "imports": ["fastapi"],
        "action": "Auto-instrumented, use @monocle_trace_http_route for routes"
    },
    "aiohttp": {
        "category": "HTTP Framework",
        "name": "AIOHTTP",
        "imports": ["aiohttp"],
        "action": "Auto-instrumented, use @monocle_trace_http_route for routes"
    },
    # MCP
    "mcp": {
        "category": "MCP",
        "name": "Model Context Protocol",
        "imports": ["fastmcp", "mcp"],
        "action": "Auto-instrumented with setup_monocle_telemetry()"
    },
}

# Frameworks that need decorators
DECORATOR_REQUIRED = {
    "azure_functions": {
        "category": "Cloud Function",
        "name": "Azure Functions",
        "imports": ["azure.functions"],
        "decorator": "monocle_trace_azure_function_route",
        "import_from": "monocle_apptrace",
        "action": "Add @monocle_trace_azure_function_route to each function"
    },
    "aws_lambda": {
        "category": "Cloud Function",
        "name": "AWS Lambda",
        "imports": ["aws_lambda_powertools"],
        "pattern": r"def\s+\w+\s*\(\s*event\s*,\s*context",
        "decorator": "monocle_trace_lambda_function_route",
        "import_from": "monocle_apptrace.instrumentation.metamodel.lambdafunc.wrapper",
        "action": "Add @monocle_trace_lambda_function_route to handler"
    },
}


class MonocleDetector:
    """Detect monocle-supported frameworks in a codebase."""

    SKIP_DIRS = {
        '__pycache__', '.git', 'venv', 'env', '.venv',
        'node_modules', '.tox', 'dist', 'build', '.okahu', '.monocle'
    }

    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()
        self.detected = {}
        self.custom_code = []
        self.all_imports = {}

    def scan(self) -> dict:
        """Scan codebase for frameworks."""
        if self.root_path.is_file():
            self._scan_file(self.root_path)
        else:
            self._scan_directory(self.root_path)

        return self._build_result()

    def _scan_directory(self, path: Path):
        """Recursively scan directory."""
        for item in path.iterdir():
            if item.is_dir():
                if item.name not in self.SKIP_DIRS and not item.name.startswith('.'):
                    self._scan_directory(item)
            elif item.suffix == '.py':
                self._scan_file(item)

    def _scan_file(self, file_path: Path):
        """Scan a single file for imports."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            rel_path = str(file_path.relative_to(self.root_path)) if file_path.is_relative_to(self.root_path) else str(file_path)

            # Extract imports
            imports = self._extract_imports(content)
            if imports:
                self.all_imports[rel_path] = imports

            # Check for auto-instrumented frameworks
            for key, framework in AUTO_INSTRUMENTED.items():
                for imp in framework["imports"]:
                    if any(i.startswith(imp) for i in imports):
                        # Check pattern if exists
                        if "pattern" in framework:
                            if not re.search(framework["pattern"], content):
                                continue

                        if key not in self.detected:
                            self.detected[key] = {
                                "type": "auto",
                                **framework,
                                "files": []
                            }
                        self.detected[key]["files"].append(rel_path)
                        break

            # Check for decorator-required frameworks
            for key, framework in DECORATOR_REQUIRED.items():
                for imp in framework["imports"]:
                    if any(i.startswith(imp) for i in imports):
                        # Check pattern if exists
                        if "pattern" in framework:
                            if not re.search(framework["pattern"], content):
                                continue

                        if key not in self.detected:
                            self.detected[key] = {
                                "type": "decorator",
                                **framework,
                                "files": []
                            }
                        self.detected[key]["files"].append(rel_path)
                        break

            # Check if file has no detected frameworks (custom code)
            file_has_framework = False
            for det in self.detected.values():
                if rel_path in det.get("files", []):
                    file_has_framework = True
                    break

            if not file_has_framework and self._has_traceable_code(content):
                self.custom_code.append(rel_path)

        except Exception as e:
            print(f"[WARN] Failed to scan {file_path}: {e}", file=sys.stderr)

    def _extract_imports(self, content: str) -> list:
        """Extract import statements from content."""
        imports = []

        # Match: import x, from x import y
        import_pattern = r'^(?:from\s+([\w.]+)|import\s+([\w.]+(?:\s*,\s*[\w.]+)*))'

        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                continue

            match = re.match(import_pattern, line)
            if match:
                if match.group(1):  # from x import
                    imports.append(match.group(1))
                elif match.group(2):  # import x, y, z
                    for imp in match.group(2).split(','):
                        imports.append(imp.strip().split()[0])

        return imports

    def _has_traceable_code(self, content: str) -> bool:
        """Check if file has traceable code (classes/functions)."""
        # Simple heuristic: has class or def
        return bool(re.search(r'^(class|def|async\s+def)\s+\w+', content, re.MULTILINE))

    def _build_result(self) -> dict:
        """Build result dictionary."""
        auto_frameworks = []
        decorator_frameworks = []

        for key, det in self.detected.items():
            info = {
                "id": key,
                "name": det["name"],
                "category": det["category"],
                "files": det["files"],
                "action": det["action"]
            }

            if det["type"] == "auto":
                auto_frameworks.append(info)
            else:
                info["decorator"] = det.get("decorator")
                info["import_from"] = det.get("import_from")
                decorator_frameworks.append(info)

        return {
            "root": str(self.root_path),
            "auto_instrumented": auto_frameworks,
            "decorator_required": decorator_frameworks,
            "custom_code": self.custom_code,
            "summary": {
                "auto_count": len(auto_frameworks),
                "decorator_count": len(decorator_frameworks),
                "custom_count": len(self.custom_code),
                "needs_yaml": len(self.custom_code) > 0
            },
            "setup_code": self._generate_setup_code(auto_frameworks, decorator_frameworks)
        }

    def _generate_setup_code(self, auto_frameworks: list, decorator_frameworks: list) -> str:
        """Generate suggested setup code."""
        lines = []

        # Base import
        imports = ["setup_monocle_telemetry"]

        # Add decorator imports
        for fw in decorator_frameworks:
            imports.append(fw["decorator"])

        lines.append(f"from monocle_apptrace import {', '.join(imports)}")

        # Special imports
        for fw in decorator_frameworks:
            if fw["import_from"] != "monocle_apptrace":
                lines.append(f"from {fw['import_from']} import {fw['decorator']}")

        lines.append("")
        lines.append("# Initialize monocle")
        lines.append('setup_monocle_telemetry(workflow_name="my_app")')

        # Decorator examples
        if decorator_frameworks:
            lines.append("")
            lines.append("# Example decorator usage:")
            for fw in decorator_frameworks:
                lines.append(f"# @{fw['decorator']}")
                lines.append(f"# def my_{fw['id'].replace('_', '')}(...):")
                lines.append("#     ...")

        return "\n".join(lines)


def print_report(result: dict):
    """Print human-readable report."""
    print("=" * 60)
    print("MONOCLE FRAMEWORK DETECTION")
    print("=" * 60)
    print()

    # Auto-instrumented
    if result["auto_instrumented"]:
        print("AUTO-INSTRUMENTED (just call setup_monocle_telemetry()):")
        print()
        for fw in result["auto_instrumented"]:
            print(f"  ✅ {fw['name']} ({fw['category']})")
            for f in fw["files"][:3]:  # Show max 3 files
                print(f"     Found in: {f}")
            if len(fw["files"]) > 3:
                print(f"     ... and {len(fw['files']) - 3} more files")
        print()

    # Decorator required
    if result["decorator_required"]:
        print("DECORATOR REQUIRED:")
        print()
        for fw in result["decorator_required"]:
            print(f"  🏷️  {fw['name']} ({fw['category']})")
            print(f"     Use: @{fw['decorator']}")
            for f in fw["files"][:3]:
                print(f"     Found in: {f}")
            if len(fw["files"]) > 3:
                print(f"     ... and {len(fw['files']) - 3} more files")
        print()

    # Custom code
    if result["custom_code"]:
        print("CUSTOM CODE (needs okahu.yaml):")
        print()
        for f in result["custom_code"][:10]:
            print(f"  ⚠️  {f}")
        if len(result["custom_code"]) > 10:
            print(f"  ... and {len(result['custom_code']) - 10} more files")
        print()

    # Summary
    print("-" * 60)
    summary = result["summary"]
    print(f"Summary: {summary['auto_count']} auto-instrumented, "
          f"{summary['decorator_count']} need decorators, "
          f"{summary['custom_count']} need custom YAML")

    if summary["needs_yaml"]:
        print()
        print("Next step: Run /ok-scan to analyze custom code")
    else:
        print()
        print("All frameworks supported! Just add setup code.")

    print()
    print("-" * 60)
    print("SUGGESTED SETUP CODE:")
    print("-" * 60)
    print()
    print(result["setup_code"])
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Detect monocle-supported frameworks in a codebase"
    )
    parser.add_argument("path", help="Path to Python file or directory")
    parser.add_argument(
        "--output", "-o",
        default=".okahu/monocle_support.json",
        help="Output JSON file path"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON only (no report)"
    )

    args = parser.parse_args()

    detector = MonocleDetector(args.path)
    result = detector.scan()

    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)

    # Print report
    if not args.json:
        print_report(result)
        print(f"JSON output: {output_path}")


if __name__ == "__main__":
    main()
