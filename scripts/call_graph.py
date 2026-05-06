#!/usr/bin/env python3
"""
Call Graph Builder - Build caller→callee relationships from AST data.

Takes ast_data.json and builds forward and reverse call graphs.

Usage:
    python call_graph.py .okahu/ast_data.json
    python call_graph.py .okahu/ast_data.json --output .okahu/call_graph.json

Output: JSON with forward and reverse call mappings
"""

import argparse
import json
import re
from pathlib import Path


class CallGraphBuilder:
    """Build call graph from AST data."""

    def __init__(self, ast_data: dict):
        self.ast_data = ast_data
        self.forward = {}  # caller -> [callees]
        self.reverse = {}  # callee -> [callers]
        self.methods = {}  # fully qualified name -> method info
        self.modules = {}  # module name -> file path

    def build(self) -> dict:
        """Build the call graph."""
        # First pass: index all methods and build module map
        self._index_methods()

        # Second pass: resolve calls
        self._resolve_calls()

        return {
            "root": self.ast_data.get("root", ""),
            "forward": self.forward,
            "reverse": self.reverse,
            "methods": self.methods,
            "summary": self._get_summary()
        }

    def _index_methods(self):
        """Index all methods with their fully qualified names."""
        for file_path, module_data in self.ast_data.get("modules", {}).items():
            # Derive module name from file path
            module_name = self._path_to_module(file_path)
            self.modules[module_name] = file_path

            # Index functions
            for func_name, func_data in module_data.get("functions", {}).items():
                fqn = f"{module_name}:{func_name}"
                self.methods[fqn] = {
                    "type": "function",
                    "module": module_name,
                    "file": file_path,
                    "name": func_name,
                    "lineno": func_data.get("lineno"),
                    "calls": func_data.get("calls", []),
                    "is_async": func_data.get("is_async", False)
                }

            # Index class methods
            for class_name, class_data in module_data.get("classes", {}).items():
                for method_name, method_data in class_data.get("methods", {}).items():
                    fqn = f"{module_name}:{class_name}.{method_name}"
                    self.methods[fqn] = {
                        "type": "method",
                        "module": module_name,
                        "file": file_path,
                        "class": class_name,
                        "name": method_name,
                        "lineno": method_data.get("lineno"),
                        "calls": method_data.get("calls", []),
                        "is_async": method_data.get("is_async", False)
                    }

    def _path_to_module(self, file_path: str) -> str:
        """Convert file path to module name."""
        # Remove .py extension and convert path separators
        module = file_path.replace('.py', '').replace('/', '.').replace('\\', '.')
        # Remove leading dots
        module = module.lstrip('.')
        return module

    def _resolve_calls(self):
        """Resolve call references to actual method FQNs."""
        for caller_fqn, method_info in self.methods.items():
            if caller_fqn not in self.forward:
                self.forward[caller_fqn] = []

            for call in method_info.get("calls", []):
                resolved = self._resolve_call(call, method_info)
                if resolved:
                    for callee_fqn in resolved:
                        # Add to forward graph
                        if callee_fqn not in self.forward[caller_fqn]:
                            self.forward[caller_fqn].append(callee_fqn)

                        # Add to reverse graph
                        if callee_fqn not in self.reverse:
                            self.reverse[callee_fqn] = []
                        if caller_fqn not in self.reverse[callee_fqn]:
                            self.reverse[callee_fqn].append(caller_fqn)

    def _resolve_call(self, call: str, context: dict) -> list:
        """
        Resolve a call string to possible method FQNs.

        Args:
            call: The call string (e.g., "self.method", "ClassName.method", "func")
            context: The calling method's info (module, class, etc.)

        Returns:
            List of possible FQNs this call could refer to
        """
        resolved = []
        caller_module = context.get("module", "")
        caller_class = context.get("class")

        # Handle self.method calls
        if call.startswith("self."):
            method_name = call[5:]  # Remove "self."
            if caller_class:
                fqn = f"{caller_module}:{caller_class}.{method_name}"
                if fqn in self.methods:
                    resolved.append(fqn)
            return resolved

        # Handle cls.method calls (class methods)
        if call.startswith("cls."):
            method_name = call[4:]
            if caller_class:
                fqn = f"{caller_module}:{caller_class}.{method_name}"
                if fqn in self.methods:
                    resolved.append(fqn)
            return resolved

        # Handle ClassName.method calls
        if "." in call:
            parts = call.split(".")
            # Try as Class.method in same module
            if len(parts) == 2:
                class_name, method_name = parts
                fqn = f"{caller_module}:{class_name}.{method_name}"
                if fqn in self.methods:
                    resolved.append(fqn)

            # Try as module.function or module.Class.method
            for i in range(1, len(parts)):
                module_part = ".".join(parts[:i])
                rest = ".".join(parts[i:])

                # Check if it's a known module
                if module_part in self.modules:
                    # Try as function
                    fqn = f"{module_part}:{rest}"
                    if fqn in self.methods:
                        resolved.append(fqn)

                    # Try as Class.method
                    if "." in rest:
                        fqn = f"{module_part}:{rest}"
                        if fqn in self.methods:
                            resolved.append(fqn)

        else:
            # Simple function name - check same module first
            fqn = f"{caller_module}:{call}"
            if fqn in self.methods:
                resolved.append(fqn)

            # Check all modules for matching function
            for module_name in self.modules:
                fqn = f"{module_name}:{call}"
                if fqn in self.methods and fqn not in resolved:
                    resolved.append(fqn)

        return resolved

    def _get_summary(self) -> dict:
        """Generate summary statistics."""
        # Find most called methods
        call_counts = {}
        for callee, callers in self.reverse.items():
            call_counts[callee] = len(callers)

        most_called = sorted(call_counts.items(), key=lambda x: -x[1])[:10]

        # Find methods with most calls
        out_counts = {}
        for caller, callees in self.forward.items():
            out_counts[caller] = len(callees)

        most_calling = sorted(out_counts.items(), key=lambda x: -x[1])[:10]

        # Find leaf methods (no outgoing calls)
        leaves = [m for m, calls in self.forward.items() if not calls]

        # Find entry points (no incoming calls)
        all_callees = set()
        for callees in self.forward.values():
            all_callees.update(callees)

        entry_points = [m for m in self.methods if m not in all_callees]

        return {
            "total_methods": len(self.methods),
            "total_edges": sum(len(v) for v in self.forward.values()),
            "most_called": most_called,
            "most_calling": most_calling,
            "leaf_count": len(leaves),
            "entry_point_count": len(entry_points)
        }


def compute_minimal_instrumentation(call_graph: dict, selected_methods: list) -> dict:
    """
    Given a set of selected methods, return only the entry points.

    If A calls B and both are selected, only instrument A (the entry point).
    B will still be traced as a child span of A.

    Args:
        call_graph: The call graph data with 'forward' and 'reverse' keys
        selected_methods: List of method FQNs to consider

    Returns:
        dict with 'instrument' (entry points) and 'covered' (reachable from entry points)
    """
    selected_set = set(selected_methods)
    forward = call_graph.get("forward", {})

    # Find which selected methods are called by other selected methods
    called_by_selected = set()
    for method in selected_methods:
        for callee in forward.get(method, []):
            if callee in selected_set:
                called_by_selected.add(callee)

    # Entry points are selected methods NOT called by other selected methods
    entry_points = [m for m in selected_methods if m not in called_by_selected]

    # Compute what's reachable from entry points (covered by instrumentation)
    covered = set()
    def walk(method, visited):
        if method in visited:
            return
        visited.add(method)
        covered.add(method)
        for callee in forward.get(method, []):
            if callee in selected_set:
                walk(callee, visited)

    for ep in entry_points:
        walk(ep, set())

    # Methods that won't be covered (not reachable from any entry point)
    uncovered = selected_set - covered

    return {
        "instrument": entry_points,
        "covered": list(covered),
        "removed": list(called_by_selected),
        "uncovered": list(uncovered),
        "summary": {
            "selected": len(selected_methods),
            "instrument": len(entry_points),
            "removed": len(called_by_selected),
            "reduction": f"{(1 - len(entry_points)/len(selected_methods))*100:.0f}%" if selected_methods else "0%"
        }
    }


def print_summary(result: dict):
    """Print human-readable summary."""
    summary = result["summary"]

    print("=" * 60)
    print("CALL GRAPH SUMMARY")
    print("=" * 60)
    print()
    print(f"Total methods: {summary['total_methods']}")
    print(f"Total call edges: {summary['total_edges']}")
    print(f"Entry points (no callers): {summary['entry_point_count']}")
    print(f"Leaf methods (no calls): {summary['leaf_count']}")
    print()

    if summary["most_called"]:
        print("Most called methods:")
        for method, count in summary["most_called"][:5]:
            print(f"  {method}: {count} callers")
        print()

    if summary["most_calling"]:
        print("Methods with most calls:")
        for method, count in summary["most_calling"][:5]:
            print(f"  {method}: {count} calls")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Build call graph from AST data"
    )
    parser.add_argument("ast_file", help="Path to ast_data.json or call_graph.json (for --minimize)")
    parser.add_argument(
        "--output", "-o",
        default=".okahu/call_graph.json",
        help="Output JSON file path"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress summary output"
    )
    parser.add_argument(
        "--minimize",
        metavar="METHODS_FILE",
        help="Compute minimal instrumentation set from selected methods (JSON list or choices.json)"
    )

    args = parser.parse_args()

    # Minimize mode: compute minimal instrumentation set
    if args.minimize:
        with open(args.ast_file, 'r', encoding='utf-8') as f:
            call_graph = json.load(f)

        with open(args.minimize, 'r', encoding='utf-8') as f:
            methods_data = json.load(f)

        # Support both plain list and choices.json format
        if isinstance(methods_data, list):
            selected = methods_data
        elif isinstance(methods_data, dict) and "selected" in methods_data:
            selected = methods_data["selected"]
        else:
            print("Error: methods file must be a JSON list or have 'selected' key")
            return

        result = compute_minimal_instrumentation(call_graph, selected)

        if not args.quiet:
            print("=" * 60)
            print("MINIMAL INSTRUMENTATION SET")
            print("=" * 60)
            print(f"Selected methods: {result['summary']['selected']}")
            print(f"Methods to instrument: {result['summary']['instrument']}")
            print(f"Removed (covered by parents): {result['summary']['removed']}")
            print(f"Reduction: {result['summary']['reduction']}")
            print()
            print("Instrument these methods:")
            for m in result["instrument"]:
                print(f"  {m}")
            if result["removed"]:
                print()
                print("Skipped (already covered):")
                for m in result["removed"]:
                    print(f"  {m}")

        # Write output if specified
        if args.output != ".okahu/call_graph.json":
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)
            if not args.quiet:
                print(f"\nOutput: {output_path}")

        return

    # Normal mode: build call graph from AST
    with open(args.ast_file, 'r', encoding='utf-8') as f:
        ast_data = json.load(f)

    # Build call graph
    builder = CallGraphBuilder(ast_data)
    result = builder.build()

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
