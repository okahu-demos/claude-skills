#!/usr/bin/env python3
"""
Entry Point Detector - Find application entry points.

Detects CLI mains, web routes, workers, and other entry points.

Usage:
    python entry_detector.py .okahu/ast_data.json
    python entry_detector.py .okahu/ast_data.json --output .okahu/entry_points.json

Output: JSON with detected entry points and their types
"""

import argparse
import json
import re
from pathlib import Path


class EntryPointDetector:
    """Detect entry points in Python code."""

    # Decorator patterns that indicate entry points
    ROUTE_DECORATORS = {
        "app.route", "app.get", "app.post", "app.put", "app.delete", "app.patch",
        "router.route", "router.get", "router.post", "router.put", "router.delete",
        "blueprint.route", "bp.route",
        "api.route", "api.get", "api.post",
        "route", "get", "post", "put", "delete", "patch"
    }

    WORKER_DECORATORS = {
        "celery.task", "app.task", "task",
        "dramatiq.actor", "actor",
        "rq.job", "job"
    }

    LAMBDA_PATTERNS = {
        "azure.functions", "aws_lambda_powertools"
    }

    def __init__(self, ast_data: dict, call_graph: dict = None):
        self.ast_data = ast_data
        self.call_graph = call_graph
        self.entry_points = []

    def detect(self) -> dict:
        """Detect all entry points."""
        for file_path, module_data in self.ast_data.get("modules", {}).items():
            module_name = self._path_to_module(file_path)

            # Check for CLI entry points
            self._detect_cli_main(file_path, module_name, module_data)

            # Check functions for route/worker decorators
            for func_name, func_data in module_data.get("functions", {}).items():
                self._check_function_entry(file_path, module_name, func_name, func_data)

            # Check class methods for route decorators
            for class_name, class_data in module_data.get("classes", {}).items():
                for method_name, method_data in class_data.get("methods", {}).items():
                    self._check_method_entry(
                        file_path, module_name, class_name, method_name, method_data
                    )

            # Check for Flask/FastAPI app creation
            self._detect_web_app(file_path, module_name, module_data)

        # Add reachability info if call graph available
        if self.call_graph:
            self._add_reachability()

        return {
            "root": self.ast_data.get("root", ""),
            "entry_points": self.entry_points,
            "summary": self._get_summary()
        }

    def _path_to_module(self, file_path: str) -> str:
        """Convert file path to module name."""
        return file_path.replace('.py', '').replace('/', '.').replace('\\', '.').lstrip('.')

    def _detect_cli_main(self, file_path: str, module_name: str, module_data: dict):
        """Detect CLI main entry points."""
        # Check for main function
        functions = module_data.get("functions", {})

        if "main" in functions:
            main_data = functions["main"]
            self.entry_points.append({
                "type": "cli",
                "location": f"{module_name}:main",
                "file": file_path,
                "lineno": main_data.get("lineno"),
                "detection": "__main__ pattern",
                "description": "CLI entry point (main function)"
            })

        # Check for if __name__ == "__main__" pattern in module docstring
        # This is a heuristic - we assume main.py or *_cli.py files are CLI
        if file_path.endswith("main.py") or "_cli.py" in file_path or "cli_" in file_path:
            if "main" not in functions:
                # Look for any likely entry function
                for func_name, func_data in functions.items():
                    if func_name in ("run", "start", "execute", "cli", "app"):
                        self.entry_points.append({
                            "type": "cli",
                            "location": f"{module_name}:{func_name}",
                            "file": file_path,
                            "lineno": func_data.get("lineno"),
                            "detection": f"CLI file pattern ({file_path})",
                            "description": f"Likely CLI entry point ({func_name})"
                        })
                        break

    def _check_function_entry(self, file_path: str, module_name: str,
                              func_name: str, func_data: dict):
        """Check if a function is an entry point."""
        decorators = func_data.get("decorators", [])

        for dec in decorators:
            dec_lower = dec.lower()

            # Check for route decorators
            for pattern in self.ROUTE_DECORATORS:
                if pattern in dec_lower or dec_lower.startswith(pattern.split('.')[-1]):
                    route_info = self._extract_route_info(dec)
                    self.entry_points.append({
                        "type": "http_route",
                        "location": f"{module_name}:{func_name}",
                        "file": file_path,
                        "lineno": func_data.get("lineno"),
                        "detection": f"@{dec}",
                        "description": f"HTTP route: {route_info}",
                        "route": route_info,
                        "is_async": func_data.get("is_async", False)
                    })
                    return

            # Check for worker decorators
            for pattern in self.WORKER_DECORATORS:
                if pattern in dec_lower:
                    self.entry_points.append({
                        "type": "worker",
                        "location": f"{module_name}:{func_name}",
                        "file": file_path,
                        "lineno": func_data.get("lineno"),
                        "detection": f"@{dec}",
                        "description": f"Background worker task",
                        "is_async": func_data.get("is_async", False)
                    })
                    return

        # Check for Lambda/Azure function patterns
        args = func_data.get("args", [])
        arg_names = [a.get("name", "") for a in args]

        # Lambda pattern: def handler(event, context)
        if set(arg_names) >= {"event", "context"}:
            self.entry_points.append({
                "type": "lambda",
                "location": f"{module_name}:{func_name}",
                "file": file_path,
                "lineno": func_data.get("lineno"),
                "detection": "Lambda signature (event, context)",
                "description": "AWS Lambda handler"
            })

        # Azure Function pattern: def func(req: func.HttpRequest)
        arg_types = [a.get("type", "") for a in args]
        if any("HttpRequest" in t or "HttpTrigger" in t for t in arg_types if t):
            self.entry_points.append({
                "type": "azure_function",
                "location": f"{module_name}:{func_name}",
                "file": file_path,
                "lineno": func_data.get("lineno"),
                "detection": "Azure Function signature",
                "description": "Azure Function handler"
            })

    def _check_method_entry(self, file_path: str, module_name: str,
                            class_name: str, method_name: str, method_data: dict):
        """Check if a class method is an entry point."""
        decorators = method_data.get("decorators", [])

        for dec in decorators:
            dec_lower = dec.lower()

            # Check for route decorators
            for pattern in self.ROUTE_DECORATORS:
                if pattern in dec_lower or dec_lower.startswith(pattern.split('.')[-1]):
                    route_info = self._extract_route_info(dec)
                    self.entry_points.append({
                        "type": "http_route",
                        "location": f"{module_name}:{class_name}.{method_name}",
                        "file": file_path,
                        "lineno": method_data.get("lineno"),
                        "detection": f"@{dec}",
                        "description": f"HTTP route: {route_info}",
                        "route": route_info,
                        "is_async": method_data.get("is_async", False)
                    })
                    return

    def _detect_web_app(self, file_path: str, module_name: str, module_data: dict):
        """Detect web application factory patterns."""
        imports = module_data.get("imports", [])
        import_names = [i.get("name", "") or i.get("module", "") for i in imports]

        # Flask app factory
        if any("flask" in i.lower() for i in import_names):
            for func_name, func_data in module_data.get("functions", {}).items():
                if func_name in ("create_app", "make_app", "get_app"):
                    self.entry_points.append({
                        "type": "flask_factory",
                        "location": f"{module_name}:{func_name}",
                        "file": file_path,
                        "lineno": func_data.get("lineno"),
                        "detection": "Flask app factory pattern",
                        "description": "Flask application factory"
                    })

        # FastAPI app
        if any("fastapi" in i.lower() for i in import_names):
            for func_name, func_data in module_data.get("functions", {}).items():
                if func_name in ("create_app", "get_application", "app"):
                    self.entry_points.append({
                        "type": "fastapi_factory",
                        "location": f"{module_name}:{func_name}",
                        "file": file_path,
                        "lineno": func_data.get("lineno"),
                        "detection": "FastAPI app factory pattern",
                        "description": "FastAPI application factory"
                    })

    def _extract_route_info(self, decorator: str) -> str:
        """Extract route path from decorator string."""
        # Try to extract path from decorator like @app.route('/users')
        match = re.search(r"['\"]([^'\"]+)['\"]", decorator)
        if match:
            return match.group(1)
        return "/"

    def _add_reachability(self):
        """Add reachability info using call graph."""
        forward = self.call_graph.get("forward", {})

        for entry in self.entry_points:
            location = entry["location"]
            reachable = self._count_reachable(location, forward, set())
            entry["reachable_methods"] = reachable

    def _count_reachable(self, method: str, forward: dict, visited: set) -> int:
        """Count methods reachable from a given method."""
        if method in visited:
            return 0
        visited.add(method)

        callees = forward.get(method, [])
        count = len(callees)

        for callee in callees:
            count += self._count_reachable(callee, forward, visited)

        return count

    def _get_summary(self) -> dict:
        """Generate summary statistics."""
        by_type = {}
        for entry in self.entry_points:
            t = entry["type"]
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "total": len(self.entry_points),
            "by_type": by_type
        }


def print_summary(result: dict):
    """Print human-readable summary."""
    print("=" * 60)
    print("ENTRY POINTS DETECTED")
    print("=" * 60)
    print()

    entries = result["entry_points"]
    if not entries:
        print("No entry points detected.")
        print()
        return

    # Group by type
    by_type = {}
    for entry in entries:
        t = entry["type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(entry)

    for entry_type, entries_list in by_type.items():
        print(f"{entry_type.upper()} ({len(entries_list)}):")
        print()
        for i, entry in enumerate(entries_list, 1):
            reach = entry.get("reachable_methods", "?")
            print(f"  [{i}] {entry['location']}")
            print(f"      File: {entry['file']}:{entry.get('lineno', '?')}")
            print(f"      Detection: {entry['detection']}")
            if reach != "?":
                print(f"      Reaches: {reach} methods")
            print()

    summary = result["summary"]
    print("-" * 60)
    print(f"Total: {summary['total']} entry points")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Detect entry points in Python code"
    )
    parser.add_argument("ast_file", help="Path to ast_data.json")
    parser.add_argument(
        "--call-graph", "-g",
        help="Path to call_graph.json (for reachability info)"
    )
    parser.add_argument(
        "--output", "-o",
        default=".okahu/entry_points.json",
        help="Output JSON file path"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress summary output"
    )

    args = parser.parse_args()

    # Load AST data
    with open(args.ast_file, 'r', encoding='utf-8') as f:
        ast_data = json.load(f)

    # Load call graph if provided
    call_graph = None
    if args.call_graph:
        with open(args.call_graph, 'r', encoding='utf-8') as f:
            call_graph = json.load(f)

    # Detect entry points
    detector = EntryPointDetector(ast_data, call_graph)
    result = detector.detect()

    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)

    # Print summary
    if not args.quiet:
        print_summary(result)
        print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
