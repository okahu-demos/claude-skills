#!/usr/bin/env python3
"""
YAML Generator - Generate okahu.yaml from analysis data.

Takes analysis JSON files and user choices to generate okahu.yaml config.

Usage:
    python yaml_generator.py .okahu/
    python yaml_generator.py .okahu/ --output okahu.yaml
    python yaml_generator.py .okahu/ --choices .okahu/choices.json

Output: okahu.yaml configuration file
"""

import argparse
import json
from pathlib import Path
from typing import Any

# Try to use PyYAML if available, otherwise generate manually
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class YamlGenerator:
    """Generate okahu.yaml from analysis data."""

    def __init__(self, analyze_dir: str, choices: dict = None):
        self.okahu_dir = Path(analyze_dir)
        self.choices = choices or {}
        self.ast_data = None
        self.call_graph = None
        self.entry_points = None
        self.arg_analysis = None

    def load_data(self):
        """Load analysis JSON files."""
        ast_file = self.okahu_dir / "ast_data.json"
        if ast_file.exists():
            with open(ast_file, 'r') as f:
                self.ast_data = json.load(f)

        call_graph_file = self.okahu_dir / "call_graph.json"
        if call_graph_file.exists():
            with open(call_graph_file, 'r') as f:
                self.call_graph = json.load(f)

        entry_file = self.okahu_dir / "entry_points.json"
        if entry_file.exists():
            with open(entry_file, 'r') as f:
                self.entry_points = json.load(f)

        arg_file = self.okahu_dir / "arg_analysis.json"
        if arg_file.exists():
            with open(arg_file, 'r') as f:
                self.arg_analysis = json.load(f)

    def generate(self, workflow_name: str = "my_app") -> dict:
        """Generate okahu.yaml config."""
        self.load_data()

        config = {
            "workflow_name": workflow_name,
            "instrument": []
        }

        # Get methods to instrument
        methods = self._get_methods_to_instrument()

        for method_fqn in methods:
            method_config = self._generate_method_config(method_fqn)
            if method_config:
                config["instrument"].append(method_config)

        return config

    def _get_methods_to_instrument(self) -> list:
        """Get list of methods to instrument based on choices."""
        methods = []

        # If specific methods chosen
        if "methods" in self.choices:
            return self.choices["methods"]

        # If entry points chosen
        if "entry_points" in self.choices:
            selected = self.choices["entry_points"]
            if self.entry_points:
                for entry in self.entry_points.get("entry_points", []):
                    if entry["location"] in selected or "all" in selected:
                        methods.append(entry["location"])
                        # Add reachable methods
                        if self.call_graph:
                            reachable = self._get_reachable(entry["location"])
                            methods.extend(reachable)
            return list(set(methods))

        # Default: use entry points + their calls
        if self.entry_points:
            for entry in self.entry_points.get("entry_points", []):
                methods.append(entry["location"])
                if self.call_graph:
                    reachable = self._get_reachable(entry["location"])
                    methods.extend(reachable)

        return list(set(methods))

    def _get_reachable(self, method: str, depth: int = 3) -> list:
        """Get methods reachable from a given method up to depth."""
        if not self.call_graph or depth <= 0:
            return []

        forward = self.call_graph.get("forward", {})
        reachable = []
        visited = set()

        def visit(m, d):
            if m in visited or d <= 0:
                return
            visited.add(m)
            callees = forward.get(m, [])
            for callee in callees:
                reachable.append(callee)
                visit(callee, d - 1)

        visit(method, depth)
        return reachable

    def _generate_method_config(self, method_fqn: str) -> dict | None:
        """Generate config for a single method."""
        # Parse FQN: module:Class.method or module:function
        if ":" not in method_fqn:
            return None

        module, rest = method_fqn.split(":", 1)

        if "." in rest:
            class_name, method_name = rest.rsplit(".", 1)
        else:
            class_name = None
            method_name = rest

        # Convert module to package name
        package = module

        # Build config
        config = {
            "package": package,
            "method": method_name,
            "span_name": method_fqn.replace(":", ".").replace(".", "_")
        }

        if class_name:
            config["class"] = class_name
            config["span_name"] = f"{class_name}.{method_name}"

        # Add async flag if needed
        if self.call_graph:
            method_info = self.call_graph.get("methods", {}).get(method_fqn, {})
            if method_info.get("is_async"):
                config["async"] = True

        # Add input/output config based on arg analysis
        if self.arg_analysis:
            method_analysis = self.arg_analysis.get("methods", {}).get(method_fqn)
            if method_analysis:
                io_config = self._generate_io_config(method_analysis)
                if io_config.get("inputs"):
                    config["inputs"] = io_config["inputs"]
                if io_config.get("output"):
                    config["output"] = io_config["output"]

        return config

    def _generate_io_config(self, method_analysis: dict) -> dict:
        """Generate input/output config based on arg analysis."""
        config = {}
        recommendations = method_analysis.get("recommendations", {})

        # Input config
        inputs = {}

        if recommendations.get("include"):
            inputs["include"] = recommendations["include"]

        if recommendations.get("exclude"):
            inputs["exclude"] = recommendations["exclude"]

        if recommendations.get("truncate"):
            inputs["truncate"] = {arg: 200 for arg in recommendations["truncate"]}

        if recommendations.get("sensitive"):
            inputs["mask"] = recommendations["sensitive"]

        if inputs:
            config["inputs"] = inputs

        # Output config
        output = method_analysis.get("output", {})
        if output.get("recommendation") == "extract_or_truncate":
            config["output"] = {"max_size": 500}

        return config

    def to_yaml(self, config: dict) -> str:
        """Convert config dict to YAML string."""
        if HAS_YAML:
            return yaml.dump(config, default_flow_style=False, sort_keys=False)
        else:
            return self._manual_yaml(config)

    def _manual_yaml(self, config: dict, indent: int = 0) -> str:
        """Manually generate YAML without PyYAML."""
        lines = []
        prefix = "  " * indent

        for key, value in config.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(self._manual_yaml(value, indent + 1))
            elif isinstance(value, list):
                if not value:
                    lines.append(f"{prefix}{key}: []")
                elif isinstance(value[0], dict):
                    lines.append(f"{prefix}{key}:")
                    for item in value:
                        # First key with dash
                        first = True
                        for k, v in item.items():
                            if first:
                                lines.append(f"{prefix}  - {k}: {self._format_value(v)}")
                                first = False
                            else:
                                lines.append(f"{prefix}    {k}: {self._format_value(v)}")
                else:
                    lines.append(f"{prefix}{key}: [{', '.join(str(v) for v in value)}]")
            else:
                lines.append(f"{prefix}{key}: {self._format_value(value)}")

        return "\n".join(lines)

    def _format_value(self, value: Any) -> str:
        """Format a value for YAML."""
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, str):
            if any(c in value for c in ":#{}[]!|>&*?"):
                return f'"{value}"'
            return value
        elif value is None:
            return "null"
        else:
            return str(value)


def main():
    parser = argparse.ArgumentParser(
        description="Generate okahu.yaml from analysis data"
    )
    parser.add_argument("analyze_dir", help="Path to .okahu/ directory")
    parser.add_argument(
        "--output", "-o",
        default="okahu.yaml",
        help="Output YAML file path"
    )
    parser.add_argument(
        "--choices", "-c",
        help="Path to choices.json file"
    )
    parser.add_argument(
        "--workflow", "-w",
        default="my_app",
        help="Workflow name"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview only, don't write file"
    )

    args = parser.parse_args()

    # Load choices if provided
    choices = {}
    if args.choices:
        with open(args.choices, 'r') as f:
            choices = json.load(f)

    # Generate
    generator = YamlGenerator(args.okahu_dir, choices)
    config = generator.generate(workflow_name=args.workflow)

    # Convert to YAML
    yaml_content = generator.to_yaml(config)

    # Preview or write
    if args.preview:
        print("=" * 60)
        print("GENERATED okahu.yaml (preview)")
        print("=" * 60)
        print()
        print(yaml_content)
    else:
        output_path = Path(args.output)
        with open(output_path, 'w') as f:
            f.write(yaml_content)
        print(f"Generated: {output_path}")
        print(f"Methods configured: {len(config.get('instrument', []))}")


if __name__ == "__main__":
    main()
