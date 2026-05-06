#!/usr/bin/env python3
"""
Argument Analyzer - Analyze function arguments for size/risk.

Flags arguments that might be large or should be excluded from tracing.

Usage:
    python arg_analyzer.py .okahu/ast_data.json
    python arg_analyzer.py .okahu/ast_data.json --output .okahu/arg_analysis.json

Output: JSON with argument risk analysis and recommendations
"""

import argparse
import json
import re
from pathlib import Path


class ArgAnalyzer:
    """Analyze function arguments for tracing recommendations."""

    # Arguments to always skip
    SKIP_NAMES = {
        "self", "cls", "logger", "log", "config", "settings",
        "conn", "connection", "session", "db", "cursor",
        "ctx", "context", "request", "req", "response", "res",
        "app", "client", "pool", "engine", "lock", "event",
        "callback", "handler", "func", "fn", "_"
    }

    # Types that indicate skip
    SKIP_TYPES = {
        "Logger", "Connection", "Session", "Callable", "Type",
        "Engine", "Pool", "Lock", "Event", "Request", "Response",
        "Context", "AsyncGenerator", "Generator", "Iterator"
    }

    # Types that indicate large values
    LARGE_TYPES = {
        "str", "bytes", "bytearray", "List", "Dict", "Set",
        "list", "dict", "set", "Any", "Sequence", "Mapping",
        "Iterable", "Collection"
    }

    # Name patterns that indicate large values
    LARGE_PATTERNS = [
        r"content$", r"body$", r"text$", r"prompt$", r"document$",
        r"payload$", r"data$", r"response$", r"result$", r"output$",
        r"input$", r"message$", r"messages$", r"html$", r"json$",
        r"xml$", r"raw$", r"buffer$", r"chunk$", r"chunks$",
        r"batch$", r"items$", r"records$", r"rows$"
    ]

    # Name patterns that indicate sensitive data
    SENSITIVE_PATTERNS = [
        r"password", r"passwd", r"secret", r"token", r"key",
        r"api_key", r"apikey", r"auth", r"credential", r"private",
        r"ssn", r"social_security", r"credit_card", r"card_number",
        r"cvv", r"pin"
    ]

    def __init__(self, ast_data: dict):
        self.ast_data = ast_data
        self.analysis = {}

    def analyze(self) -> dict:
        """Analyze all methods."""
        for file_path, module_data in self.ast_data.get("modules", {}).items():
            module_name = self._path_to_module(file_path)

            # Analyze functions
            for func_name, func_data in module_data.get("functions", {}).items():
                fqn = f"{module_name}:{func_name}"
                self.analysis[fqn] = self._analyze_method(func_data)

            # Analyze class methods
            for class_name, class_data in module_data.get("classes", {}).items():
                for method_name, method_data in class_data.get("methods", {}).items():
                    fqn = f"{module_name}:{class_name}.{method_name}"
                    self.analysis[fqn] = self._analyze_method(method_data)

        return {
            "root": self.ast_data.get("root", ""),
            "methods": self.analysis,
            "summary": self._get_summary()
        }

    def _path_to_module(self, file_path: str) -> str:
        """Convert file path to module name."""
        return file_path.replace('.py', '').replace('/', '.').replace('\\', '.').lstrip('.')

    def _analyze_method(self, method_data: dict) -> dict:
        """Analyze a single method's arguments and return type."""
        args_analysis = {}
        recommendations = {
            "include": [],
            "exclude": [],
            "truncate": [],
            "sensitive": []
        }

        for arg in method_data.get("args", []):
            name = arg.get("name", "")
            arg_type = arg.get("type")

            analysis = self._analyze_arg(name, arg_type)
            args_analysis[name] = analysis

            # Add to recommendation lists
            rec = analysis["recommendation"]
            if rec == "exclude":
                recommendations["exclude"].append(name)
            elif rec == "truncate":
                recommendations["truncate"].append(name)
            elif rec == "mask":
                recommendations["sensitive"].append(name)
            else:
                recommendations["include"].append(name)

        # Analyze return type
        returns = method_data.get("returns")
        output_analysis = self._analyze_output(returns)

        return {
            "args": args_analysis,
            "output": output_analysis,
            "recommendations": recommendations
        }

    def _analyze_arg(self, name: str, arg_type: str | None) -> dict:
        """Analyze a single argument."""
        risk = "low"
        reasons = []
        recommendation = "include"

        # Check if should skip
        if name in self.SKIP_NAMES:
            risk = "skip"
            reasons.append(f"Standard skip name: {name}")
            recommendation = "exclude"

        # Check type for skip
        if arg_type:
            for skip_type in self.SKIP_TYPES:
                if skip_type in arg_type:
                    risk = "skip"
                    reasons.append(f"Skip type: {arg_type}")
                    recommendation = "exclude"
                    break

        # Check for large types
        if risk != "skip" and arg_type:
            for large_type in self.LARGE_TYPES:
                if large_type in arg_type:
                    risk = "high"
                    reasons.append(f"Potentially large type: {arg_type}")
                    recommendation = "truncate"
                    break

        # Check name patterns for large values
        if risk not in ("skip", "high"):
            for pattern in self.LARGE_PATTERNS:
                if re.search(pattern, name, re.IGNORECASE):
                    risk = "high"
                    reasons.append(f"Large value name pattern: {name}")
                    recommendation = "truncate"
                    break

        # Check for sensitive patterns
        for pattern in self.SENSITIVE_PATTERNS:
            if re.search(pattern, name, re.IGNORECASE):
                risk = "sensitive"
                reasons.append(f"Sensitive data pattern: {name}")
                recommendation = "mask"
                break

        # Medium risk for untyped args with ambiguous names
        if risk == "low" and not arg_type and len(name) <= 3:
            risk = "medium"
            reasons.append("Short name, no type hint")

        return {
            "name": name,
            "type": arg_type,
            "risk": risk,
            "reasons": reasons,
            "recommendation": recommendation
        }

    def _analyze_output(self, return_type: str | None) -> dict:
        """Analyze return type."""
        if not return_type:
            return {
                "type": None,
                "risk": "unknown",
                "recommendation": "include"
            }

        risk = "low"
        reasons = []
        recommendation = "include"

        # Check for large types
        for large_type in self.LARGE_TYPES:
            if large_type in return_type:
                risk = "high"
                reasons.append(f"Potentially large return type: {return_type}")
                recommendation = "extract_or_truncate"
                break

        # Check for None return
        if return_type == "None":
            risk = "none"
            recommendation = "skip"

        return {
            "type": return_type,
            "risk": risk,
            "reasons": reasons,
            "recommendation": recommendation
        }

    def _get_summary(self) -> dict:
        """Generate summary statistics."""
        high_risk_methods = []
        sensitive_methods = []
        total_args = 0
        total_high_risk_args = 0
        total_sensitive_args = 0

        for fqn, method_analysis in self.analysis.items():
            args = method_analysis.get("args", {})
            total_args += len(args)

            has_high_risk = False
            has_sensitive = False

            for arg_name, arg_info in args.items():
                risk = arg_info.get("risk", "low")
                if risk == "high":
                    total_high_risk_args += 1
                    has_high_risk = True
                elif risk == "sensitive":
                    total_sensitive_args += 1
                    has_sensitive = True

            if has_high_risk:
                high_risk_methods.append(fqn)
            if has_sensitive:
                sensitive_methods.append(fqn)

        return {
            "total_methods": len(self.analysis),
            "total_args": total_args,
            "high_risk_args": total_high_risk_args,
            "sensitive_args": total_sensitive_args,
            "high_risk_methods": high_risk_methods[:20],
            "sensitive_methods": sensitive_methods[:20]
        }


def print_summary(result: dict):
    """Print human-readable summary."""
    summary = result["summary"]

    print("=" * 60)
    print("ARGUMENT ANALYSIS")
    print("=" * 60)
    print()
    print(f"Total methods analyzed: {summary['total_methods']}")
    print(f"Total arguments: {summary['total_args']}")
    print(f"High-risk arguments: {summary['high_risk_args']}")
    print(f"Sensitive arguments: {summary['sensitive_args']}")
    print()

    if summary["high_risk_methods"]:
        print("Methods with high-risk arguments:")
        for method in summary["high_risk_methods"][:10]:
            print(f"  - {method}")
        if len(summary["high_risk_methods"]) > 10:
            print(f"  ... and {len(summary['high_risk_methods']) - 10} more")
        print()

    if summary["sensitive_methods"]:
        print("Methods with sensitive arguments:")
        for method in summary["sensitive_methods"][:10]:
            print(f"  - {method}")
        if len(summary["sensitive_methods"]) > 10:
            print(f"  ... and {len(summary['sensitive_methods']) - 10} more")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze function arguments for tracing risks"
    )
    parser.add_argument("ast_file", help="Path to ast_data.json")
    parser.add_argument(
        "--output", "-o",
        default=".okahu/arg_analysis.json",
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

    # Analyze
    analyzer = ArgAnalyzer(ast_data)
    result = analyzer.analyze()

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
