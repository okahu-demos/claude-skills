"""
Minify monocle trace JSON files into readable debug output for Claude CLI.

Usage:
    python trace_minify.py                    # Latest trace files
    python trace_minify.py --last 5m          # Files from last 5 minutes
    python trace_minify.py --trace-id abc123  # Specific trace
    python trace_minify.py --all              # All traces from last run

Output format:
    [span_name] file.py:line
      IN:  {"param": "value"}
      OUT: result
      CALLS:
        └─ [child_span] file.py:line
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def resolve_monocle_dir(dir_arg: str) -> Path:
    """Resolve the .monocle directory from a path argument.

    Accepts:
      - ".monocle" (default) → pwd/.monocle
      - "/test/" → /test/.monocle
      - "/test/.monocle" → /test/.monocle (as-is)
      - "examples/test1" → examples/test1/.monocle
    """
    p = Path(dir_arg).resolve()
    if p.name == ".monocle":
        return p
    candidate = p / ".monocle"
    if candidate.is_dir():
        return candidate
    return p


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp from trace."""
    try:
        # Handle Z suffix
        ts_str = ts_str.replace('Z', '+00:00')
        return datetime.fromisoformat(ts_str)
    except:
        return datetime.min


def get_trace_files(monocle_dir: Path, last_minutes: Optional[int] = None,
                    trace_id: Optional[str] = None) -> list[Path]:
    """Get trace files based on filters."""
    if not monocle_dir.exists():
        return []

    files = list(monocle_dir.glob("monocle_trace_*.json"))

    if trace_id:
        files = [f for f in files if trace_id in f.name]

    if last_minutes:
        cutoff = datetime.now() - timedelta(minutes=last_minutes)
        files = [f for f in files if datetime.fromtimestamp(f.stat().st_mtime) > cutoff]

    # Sort by modification time, newest first
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files


def extract_span_info(span: dict) -> dict:
    """Extract relevant info from a span."""
    info = {
        "name": span.get("name", "unknown"),
        "span_id": span.get("context", {}).get("span_id", ""),
        "trace_id": span.get("context", {}).get("trace_id", ""),
        "parent_id": span.get("parent_id"),
        "source": span.get("attributes", {}).get("span_source", ""),
        "status": span.get("status", {}).get("status_code", ""),
        "span_type": span.get("attributes", {}).get("span.type", ""),
        "input": None,
        "output": None,
        "error": None,
        "duration_ms": None,
        "children": []
    }

    # Calculate duration
    try:
        start = parse_timestamp(span.get("start_time", ""))
        end = parse_timestamp(span.get("end_time", ""))
        if start != datetime.min and end != datetime.min:
            info["duration_ms"] = (end - start).total_seconds() * 1000
    except:
        pass

    # Extract events
    for event in span.get("events", []):
        event_name = event.get("name", "")
        attrs = event.get("attributes", {})

        if event_name == "data.input":
            # Try to parse JSON input
            input_str = attrs.get("input") or attrs.get("params", "")
            if input_str:
                try:
                    info["input"] = json.loads(input_str) if isinstance(input_str, str) else input_str
                except:
                    info["input"] = input_str

        elif event_name == "data.output":
            output_str = attrs.get("output") or attrs.get("response", "")
            error_code = attrs.get("error_code")
            if error_code and error_code not in ["success", "200"]:
                info["error"] = error_code
            if output_str:
                try:
                    info["output"] = json.loads(output_str) if isinstance(output_str, str) else output_str
                except:
                    info["output"] = output_str

    # Check status for errors
    if info["status"] == "ERROR" or span.get("status", {}).get("description"):
        info["error"] = span.get("status", {}).get("description", "ERROR")

    return info


def build_call_tree(spans: list[dict]) -> list[dict]:
    """Build hierarchical call tree from flat span list."""
    span_map = {s["span_id"]: s for s in spans}
    roots = []

    for span in spans:
        parent_id = span["parent_id"]
        if parent_id and parent_id in span_map:
            span_map[parent_id]["children"].append(span)
        else:
            roots.append(span)

    return roots


def format_value(value, max_len: int = 100) -> str:
    """Format a value for display, truncating if needed."""
    if value is None:
        return "null"

    if isinstance(value, dict):
        # Format dict compactly
        s = json.dumps(value, separators=(',', ':'))
    elif isinstance(value, (list, tuple)):
        s = json.dumps(value, separators=(',', ':'))
    else:
        s = str(value)

    if len(s) > max_len:
        return s[:max_len-3] + "..."
    return s


def print_span(span: dict, indent: int = 0, show_tree: bool = True):
    """Print a span in minified format."""
    prefix = "  " * indent
    tree_char = "└─ " if indent > 0 else ""

    # Header: [name] source
    name = span["name"]
    source = span["source"] or "unknown"
    duration = f" ({span['duration_ms']:.1f}ms)" if span["duration_ms"] else ""

    print(f"{prefix}{tree_char}[{name}] {source}{duration}")

    detail_prefix = prefix + ("   " if indent > 0 else "") + "  "

    # Input
    if span["input"]:
        print(f"{detail_prefix}IN:  {format_value(span['input'], 120)}")

    # Output
    if span["output"]:
        print(f"{detail_prefix}OUT: {format_value(span['output'], 120)}")

    # Error
    if span["error"]:
        print(f"{detail_prefix}ERR: {span['error']}")

    # Children
    if span["children"]:
        if show_tree:
            for child in span["children"]:
                print_span(child, indent + 1, show_tree)
        else:
            # Flat mode: print children at same level
            for child in span["children"]:
                print_span(child, 0, show_tree)


def process_trace_file(file_path: Path, show_tree: bool = True) -> dict:
    """Process a single trace file and return summary."""
    try:
        with open(file_path) as f:
            content = f.read().strip()
            # Handle files that start with [ or just contain objects
            if content.startswith('['):
                spans_raw = json.loads(content)
            else:
                spans_raw = [json.loads(content)]
    except json.JSONDecodeError as e:
        print(f"Error parsing {file_path}: {e}", file=sys.stderr)
        return {"error": str(e)}
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return {"error": str(e)}

    if not spans_raw:
        return {"spans": 0}

    # Extract span info
    spans = [extract_span_info(s) for s in spans_raw]

    # Get trace ID from first span
    trace_id = spans[0]["trace_id"] if spans else "unknown"

    # Build call tree
    roots = build_call_tree(spans)

    # Count errors
    errors = [s for s in spans if s["error"]]

    return {
        "trace_id": trace_id,
        "spans": len(spans),
        "errors": len(errors),
        "roots": roots
    }


def main():
    parser = argparse.ArgumentParser(description="Minify monocle traces for debugging")
    parser.add_argument("--dir", "-d", default=".monocle", help="Monocle trace directory")
    parser.add_argument("--last", "-l", help="Show traces from last N minutes (e.g., 5m, 1h)")
    parser.add_argument("--trace-id", "-t", help="Filter by trace ID (partial match)")
    parser.add_argument("--all", "-a", action="store_true", help="Show all matching traces")
    parser.add_argument("--flat", "-f", action="store_true", help="Flat output (no call tree)")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Max trace files to show")
    parser.add_argument("--errors-only", "-e", action="store_true", help="Only show spans with errors")

    args = parser.parse_args()

    # Parse time filter
    last_minutes = None
    if args.last:
        try:
            if args.last.endswith('m'):
                last_minutes = int(args.last[:-1])
            elif args.last.endswith('h'):
                last_minutes = int(args.last[:-1]) * 60
            else:
                last_minutes = int(args.last)
        except ValueError:
            print(f"Invalid time format: {args.last}", file=sys.stderr)
            sys.exit(1)

    monocle_dir = resolve_monocle_dir(args.dir)
    files = get_trace_files(monocle_dir, last_minutes, args.trace_id)

    if not files:
        print(f"No trace files found in {monocle_dir}/", file=sys.stderr)
        sys.exit(1)

    # Group files by trace_id (multiple files can have same trace)
    if not args.all:
        files = files[:args.limit]

    print(f"=== Monocle Traces ({len(files)} files) ===\n")

    seen_traces = set()
    total_spans = 0
    total_errors = 0

    for file_path in files:
        result = process_trace_file(file_path, show_tree=not args.flat)

        if "error" in result:
            continue

        trace_id = result.get("trace_id", "")
        if trace_id in seen_traces:
            continue
        seen_traces.add(trace_id)

        total_spans += result["spans"]
        total_errors += result["errors"]

        # Print trace header
        print(f"--- trace: {trace_id[:16]}... ({result['spans']} spans, {result['errors']} errors) ---")

        # Print spans
        for root in result["roots"]:
            if args.errors_only and not root["error"]:
                # Check children for errors
                def has_error(span):
                    if span["error"]:
                        return True
                    return any(has_error(c) for c in span["children"])
                if not has_error(root):
                    continue
            print_span(root, show_tree=not args.flat)

        print()

    # Summary
    print(f"=== Summary: {len(seen_traces)} traces, {total_spans} spans, {total_errors} errors ===")


if __name__ == "__main__":
    main()
