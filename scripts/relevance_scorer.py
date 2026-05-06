#!/usr/bin/env python3
"""
Relevance Scorer - Score module/method importance for tracing.

Uses call graph to determine which modules are most important to trace.

Usage:
    python relevance_scorer.py .okahu/call_graph.json
    python relevance_scorer.py .okahu/call_graph.json --entry main:main
    python relevance_scorer.py .okahu/call_graph.json --output .okahu/relevance.json

Output: JSON with modules/methods ranked by importance
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


class RelevanceScorer:
    """Score module/method relevance for tracing."""

    # Module patterns that indicate lower relevance
    LOW_RELEVANCE_PATTERNS = [
        r"^test", r"tests?/", r"_test$", r"test_",
        r"conftest", r"fixtures?",
        r"migrations?/", r"alembic/",
        r"constants?$", r"config$", r"settings$",
        r"types$", r"enums?$", r"exceptions?$", r"errors?$"
    ]

    # Method patterns that indicate lower relevance
    LOW_RELEVANCE_METHODS = {
        "__init__", "__str__", "__repr__", "__eq__", "__hash__",
        "__len__", "__iter__", "__next__", "__enter__", "__exit__",
        "__getattr__", "__setattr__", "__delattr__"
    }

    # Patterns that indicate high importance
    HIGH_RELEVANCE_PATTERNS = [
        r"service", r"handler", r"processor", r"manager",
        r"controller", r"api", r"route", r"view",
        r"repository", r"repo", r"store", r"client"
    ]

    def __init__(self, call_graph: dict, entry_points: list = None):
        self.call_graph = call_graph
        self.entry_points = entry_points or []
        self.scores = {}
        self.modules = defaultdict(list)

    def score(self) -> dict:
        """Score all methods and modules."""
        methods = self.call_graph.get("methods", {})
        forward = self.call_graph.get("forward", {})
        reverse = self.call_graph.get("reverse", {})

        # Group methods by module
        for fqn, info in methods.items():
            module = info.get("module", "")
            self.modules[module].append(fqn)

        # Score each method
        for fqn, info in methods.items():
            score = self._score_method(fqn, info, forward, reverse)
            self.scores[fqn] = score

        # Aggregate module scores
        module_scores = self._aggregate_module_scores()

        # Categorize
        high, medium, low = self._categorize(module_scores)

        return {
            "root": self.call_graph.get("root", ""),
            "methods": self.scores,
            "modules": module_scores,
            "high": high,
            "medium": medium,
            "low": low,
            "summary": self._get_summary(high, medium, low)
        }

    def _score_method(self, fqn: str, info: dict, forward: dict, reverse: dict) -> dict:
        """Score a single method."""
        score = 0.5  # Base score
        reasons = []

        # Factor 1: Number of callers (incoming edges)
        callers = reverse.get(fqn, [])
        caller_count = len(callers)
        if caller_count > 10:
            score += 0.2
            reasons.append(f"High call count: {caller_count} callers")
        elif caller_count > 5:
            score += 0.1
            reasons.append(f"Medium call count: {caller_count} callers")
        elif caller_count == 0:
            score -= 0.1
            reasons.append("No callers (orphan or entry)")

        # Factor 2: Number of outgoing calls
        callees = forward.get(fqn, [])
        callee_count = len(callees)
        if callee_count > 10:
            score += 0.1
            reasons.append(f"High fan-out: {callee_count} calls")
        elif callee_count == 0:
            score -= 0.05
            reasons.append("Leaf method (no calls)")

        # Factor 3: On path from entry point
        if self.entry_points:
            for entry in self.entry_points:
                if self._on_path_from(entry, fqn, forward):
                    score += 0.2
                    reasons.append(f"On path from entry: {entry}")
                    break

        # Factor 4: Module name patterns
        module = info.get("module", "")
        for pattern in self.HIGH_RELEVANCE_PATTERNS:
            if re.search(pattern, module, re.IGNORECASE):
                score += 0.15
                reasons.append(f"High-value module pattern: {pattern}")
                break

        for pattern in self.LOW_RELEVANCE_PATTERNS:
            if re.search(pattern, module, re.IGNORECASE):
                score -= 0.2
                reasons.append(f"Low-value module pattern: {pattern}")
                break

        # Factor 5: Method name
        method_name = info.get("name", "")
        if method_name in self.LOW_RELEVANCE_METHODS:
            score -= 0.3
            reasons.append(f"Dunder method: {method_name}")
        elif method_name.startswith("_"):
            score -= 0.1
            reasons.append("Private method")

        # Factor 6: Is entry point
        if fqn in self.entry_points:
            score += 0.3
            reasons.append("Entry point")

        # Clamp score
        score = max(0.0, min(1.0, score))

        return {
            "fqn": fqn,
            "score": round(score, 2),
            "reasons": reasons,
            "caller_count": caller_count,
            "callee_count": callee_count
        }

    def _on_path_from(self, start: str, target: str, forward: dict,
                      visited: set = None, depth: int = 10) -> bool:
        """Check if target is reachable from start."""
        if visited is None:
            visited = set()

        if start == target:
            return True
        if start in visited or depth <= 0:
            return False

        visited.add(start)
        for callee in forward.get(start, []):
            if self._on_path_from(callee, target, forward, visited, depth - 1):
                return True
        return False

    def _aggregate_module_scores(self) -> dict:
        """Aggregate method scores to module level."""
        module_scores = {}

        for module, methods in self.modules.items():
            if not methods:
                continue

            method_scores = [self.scores[m]["score"] for m in methods if m in self.scores]
            if not method_scores:
                continue

            # Use max score and average
            max_score = max(method_scores)
            avg_score = sum(method_scores) / len(method_scores)
            combined = (max_score * 0.7) + (avg_score * 0.3)

            module_scores[module] = {
                "module": module,
                "score": round(combined, 2),
                "method_count": len(methods),
                "max_score": round(max_score, 2),
                "avg_score": round(avg_score, 2),
                "methods": methods
            }

        return module_scores

    def _categorize(self, module_scores: dict) -> tuple:
        """Categorize modules into high/medium/low."""
        high = []
        medium = []
        low = []

        for module, data in module_scores.items():
            score = data["score"]
            entry = {
                "module": module,
                "score": score,
                "method_count": data["method_count"],
                "reasons": self._get_module_reasons(module, data)
            }

            if score >= 0.7:
                high.append(entry)
            elif score >= 0.4:
                medium.append(entry)
            else:
                low.append(entry)

        # Sort by score descending
        high.sort(key=lambda x: -x["score"])
        medium.sort(key=lambda x: -x["score"])
        low.sort(key=lambda x: -x["score"])

        return high, medium, low

    def _get_module_reasons(self, module: str, data: dict) -> list:
        """Get reasons for module's score."""
        reasons = []

        if data["score"] >= 0.7:
            reasons.append("High method scores")
        if data["method_count"] > 10:
            reasons.append(f"Large module ({data['method_count']} methods)")

        for pattern in self.HIGH_RELEVANCE_PATTERNS:
            if re.search(pattern, module, re.IGNORECASE):
                reasons.append(f"Important module type: {pattern}")
                break

        for pattern in self.LOW_RELEVANCE_PATTERNS:
            if re.search(pattern, module, re.IGNORECASE):
                reasons.append(f"Utility/config module")
                break

        return reasons

    def _get_summary(self, high: list, medium: list, low: list) -> dict:
        """Generate summary statistics."""
        return {
            "total_modules": len(high) + len(medium) + len(low),
            "total_methods": len(self.scores),
            "high_count": len(high),
            "medium_count": len(medium),
            "low_count": len(low),
            "recommended_trace": len(high) + len(medium)
        }


def print_summary(result: dict):
    """Print human-readable summary."""
    print("=" * 60)
    print("RELEVANCE SCORING")
    print("=" * 60)
    print()

    summary = result["summary"]
    print(f"Total modules: {summary['total_modules']}")
    print(f"Total methods: {summary['total_methods']}")
    print()
    print(f"High relevance: {summary['high_count']} modules")
    print(f"Medium relevance: {summary['medium_count']} modules")
    print(f"Low relevance: {summary['low_count']} modules")
    print()

    if result["high"]:
        print("HIGH RELEVANCE (recommended to trace):")
        for item in result["high"][:10]:
            print(f"  [{item['score']:.2f}] {item['module']} ({item['method_count']} methods)")
            for reason in item.get("reasons", [])[:2]:
                print(f"         {reason}")
        print()

    if result["medium"]:
        print("MEDIUM RELEVANCE (consider tracing):")
        for item in result["medium"][:10]:
            print(f"  [{item['score']:.2f}] {item['module']} ({item['method_count']} methods)")
        print()

    if result["low"]:
        print("LOW RELEVANCE (skip):")
        for item in result["low"][:5]:
            print(f"  [{item['score']:.2f}] {item['module']}")
        if len(result["low"]) > 5:
            print(f"  ... and {len(result['low']) - 5} more")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Score module/method relevance for tracing"
    )
    parser.add_argument("call_graph_file", help="Path to call_graph.json")
    parser.add_argument(
        "--entry", "-e",
        action="append",
        help="Entry point(s) to score from (can specify multiple)"
    )
    parser.add_argument(
        "--output", "-o",
        default=".okahu/relevance.json",
        help="Output JSON file path"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress summary output"
    )

    args = parser.parse_args()

    # Load call graph
    with open(args.call_graph_file, 'r', encoding='utf-8') as f:
        call_graph = json.load(f)

    # Score
    entry_points = args.entry or []
    scorer = RelevanceScorer(call_graph, entry_points)
    result = scorer.score()

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
