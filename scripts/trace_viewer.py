#!/usr/bin/env python3
"""
Interactive terminal trace viewer for .monocle/ local trace files.

Reads monocle trace JSON, builds a span tree, and renders an interactive
curses-based waterfall with arrow-key navigation and detail panels.

Usage:
    python trace_viewer.py                        # Pick from latest traces in pwd/.monocle
    python trace_viewer.py --last 5m              # Traces from last 5 minutes
    python trace_viewer.py --trace-id abc123      # Specific trace
    python trace_viewer.py --dir /test/           # Looks in /test/.monocle/
    python trace_viewer.py --dir /test/.monocle   # Same — direct path works too
    python trace_viewer.py --print                # Non-interactive (no TTY)

Keys:
    ↑/↓ or j/k    Navigate spans
    ←/→ or h/l    Collapse/expand children
    Enter          Toggle detail panel
    t              Cycle through traces (when multiple loaded)
    q / Esc        Quit
"""

import argparse
import curses
import json
import os
import sys
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Path resolution ───────────────────────────────────────────────

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


# ── Trace file loading ──────────────────────────────────────────────

def parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def get_trace_files(
    monocle_dir: Path,
    last_minutes: Optional[int] = None,
    trace_id: Optional[str] = None,
    limit: int = 0,
) -> List[Path]:
    if not monocle_dir.exists():
        return []
    files = list(monocle_dir.glob("monocle_trace_*.json"))
    if trace_id:
        files = [f for f in files if trace_id in f.name]
    if last_minutes:
        cutoff = datetime.now() - timedelta(minutes=last_minutes)
        files = [f for f in files if datetime.fromtimestamp(f.stat().st_mtime) > cutoff]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:limit] if limit else files


def load_trace(file_path: Path) -> List[Dict]:
    content = file_path.read_text().strip()
    if not content:
        return []
    try:
        data = json.loads(content)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        pass
    # File may be a partial/live array missing the trailing ']',
    # or concatenated JSON objects.  Try fixups:
    if content.startswith("[") and not content.endswith("]"):
        # Truncated array — strip any trailing comma and close it
        fixed = content.rstrip().rstrip(",") + "]"
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
    # JSONL: one JSON object per line
    spans = []
    for line in content.splitlines():
        line = line.strip().rstrip(",")
        if not line or line in ("[", "]"):
            continue
        try:
            spans.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return spans


# ── Span model ──────────────────────────────────────────────────────

class Span:
    def __init__(self, raw: Dict):
        ctx = raw.get("context", {})
        attrs = raw.get("attributes", {})
        self.name: str = raw.get("name", "unknown")
        self.span_id: str = ctx.get("span_id", "")
        self.trace_id: str = ctx.get("trace_id", "")
        self.parent_id: Optional[str] = raw.get("parent_id")
        self.span_type: str = attrs.get("span.type", "")

        # Friendly display name for skill spans: "Skill: <name>"
        if "skill" in self.span_type:
            skill_name = ""
            for k, v in attrs.items():
                if k.startswith("entity.") and k.endswith(".skill_name"):
                    skill_name = v
                    break
                if k.startswith("entity.") and k.endswith(".name"):
                    skill_name = v
            self.display_name = f"Skill: {skill_name}" if skill_name else self.name
        else:
            self.display_name = self.name
        self.status: str = raw.get("status", {}).get("status_code", "")

        start = parse_ts(raw.get("start_time", ""))
        end = parse_ts(raw.get("end_time", ""))
        if start != datetime.min and end != datetime.min:
            self.duration_ms = (end - start).total_seconds() * 1000
            self.start_time = start
        else:
            self.duration_ms = 0
            self.start_time = datetime.min

        self.attributes: Dict[str, Any] = {
            k: v for k, v in attrs.items()
            if not k.startswith("entity.") and k != "turn.number"
        }
        # Entity info
        for k, v in attrs.items():
            if k.startswith("entity.") and ".name" in k:
                self.attributes["entity.name"] = v
            if k.startswith("entity.") and ".type" in k and "entity.type" not in self.attributes:
                self.attributes["entity.type"] = v

        self.events: List[Dict] = []
        self.tokens: Dict[str, int] = {}
        for ev in raw.get("events", []):
            ev_name = ev.get("name", "")
            ev_attrs = ev.get("attributes", {})
            if ev_name == "metadata":
                for k, v in ev_attrs.items():
                    if "token" in k:
                        self.tokens[k] = v
            else:
                val = ev_attrs.get("input") or ev_attrs.get("response") or ev_attrs.get("output") or ""
                if val:
                    self.events.append({"name": ev_name, "value": str(val)})

        self.children: List["Span"] = []
        self.depth: int = 0
        self.collapsed: bool = False
        self.is_last_child: bool = False
        self._ancestor_is_last: List[bool] = []

    def flat_visible(self) -> List["Span"]:
        result = [self]
        if not self.collapsed:
            for c in self.children:
                result.extend(c.flat_visible())
        return result


def build_tree(raw_spans: List[Dict]) -> Tuple[List[Span], float]:
    spans = [Span(s) for s in raw_spans]
    by_id = {s.span_id: s for s in spans}
    roots = []
    for s in spans:
        if s.parent_id and s.parent_id in by_id:
            by_id[s.parent_id].children.append(s)
        else:
            roots.append(s)

    total_ms = max((s.duration_ms for s in spans), default=1) or 1

    def set_depth(span, d, ancestor_last):
        span.depth = d
        span._ancestor_is_last = list(ancestor_last)
        for i, c in enumerate(span.children):
            c.is_last_child = (i == len(span.children) - 1)
            set_depth(c, d + 1, ancestor_last + [c.is_last_child])

    for r in roots:
        r.is_last_child = True
        set_depth(r, 0, [])

    return roots, total_ms


def tree_prefix(span: "Span") -> str:
    """Build tree connector lines like: │ ├─ or │ └─"""
    if span.depth == 0:
        return ""
    parts = []
    for is_last in span._ancestor_is_last[:-1]:
        parts.append("  " if is_last else "│ ")
    parts.append("└─" if span.is_last_child else "├─")
    return "".join(parts)


# ── Word-aware text wrapping ───────────────────────────────────────

def word_wrap(text: str, width: int, indent: int = 4) -> List[str]:
    """Wrap text at word boundaries, never splitting a word."""
    if width <= indent + 5:
        return [text[:width]]
    lines = textwrap.wrap(text, width=width - indent,
                          break_long_words=True,
                          break_on_hyphens=False)
    if not lines:
        return [""]
    result = [" " * indent + lines[0]]
    for line in lines[1:]:
        result.append(" " * indent + line)
    return result


# ── Color setup ─────────────────────────────────────────────────────

C_HEADER = 1
C_SELECTED = 2
C_WORKFLOW = 3
C_TURN = 4
C_INFERENCE = 5
C_TOOL = 6
C_DIM = 7
C_KEY = 8
C_VAL = 9
C_EVENT = 10
C_BORDER = 11
C_OK = 12
C_ERR = 13
C_AGENT = 14
C_MCP = 15
C_NEW_BRIGHT = 16
C_NEW_MID = 17
C_NEW_DIM = 18
C_TREE = 19


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_HEADER, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(C_SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(C_WORKFLOW, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(C_TURN, curses.COLOR_BLACK, curses.COLOR_GREEN)
    curses.init_pair(C_INFERENCE, curses.COLOR_WHITE, curses.COLOR_MAGENTA)
    curses.init_pair(C_TOOL, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(C_DIM, 8, -1)
    curses.init_pair(C_KEY, curses.COLOR_CYAN, -1)
    curses.init_pair(C_VAL, curses.COLOR_WHITE, -1)
    curses.init_pair(C_EVENT, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_BORDER, 8, -1)
    curses.init_pair(C_OK, curses.COLOR_GREEN, -1)
    curses.init_pair(C_ERR, curses.COLOR_RED, -1)
    curses.init_pair(C_AGENT, curses.COLOR_WHITE, curses.COLOR_RED)
    curses.init_pair(C_MCP, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(C_NEW_BRIGHT, curses.COLOR_BLACK, curses.COLOR_GREEN)
    curses.init_pair(C_NEW_MID, curses.COLOR_GREEN, -1)
    curses.init_pair(C_NEW_DIM, 8, -1)
    curses.init_pair(C_TREE, 8, -1)


def bar_color(span_type: str) -> int:
    if "workflow" in span_type:
        return C_WORKFLOW
    if "turn" in span_type or "agentic.turn" in span_type:
        return C_TURN
    if "inference" in span_type:
        return C_INFERENCE
    if "mcp" in span_type:
        return C_MCP
    if "invocation" in span_type and "tool" not in span_type:
        return C_AGENT
    if "tool" in span_type:
        return C_TOOL
    return C_DIM


def type_badge(span_type: str) -> str:
    if "workflow" in span_type:
        return "WF"
    if "agentic.turn" in span_type:
        return "TN"
    if "inference" in span_type:
        return "LM"
    if "mcp" in span_type:
        return "MC"
    if "skill" in span_type:
        return "SK"
    if "invocation" in span_type and "tool" not in span_type:
        return "AG"
    if "tool" in span_type:
        return "TL"
    return "??"


# ── Drawing helpers ─────────────────────────────────────────────────

def safe(win, y, x, text, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    try:
        win.addstr(y, x, text[: w - x - 1], attr)
    except curses.error:
        pass


def draw_bar(win, y, x, length, color):
    try:
        win.addstr(y, x, "█" * max(1, length), curses.color_pair(color))
    except curses.error:
        pass


# ── Main UI ─────────────────────────────────────────────────────────

class TraceViewer:
    def __init__(self, traces: List[Tuple[str, List[Span], float]],
                 monocle_dir: Optional[Path] = None,
                 last_minutes: Optional[int] = None,
                 trace_id_filter: Optional[str] = None,
                 limit: int = 0):
        self.traces = traces  # [(filename, roots, total_ms), ...]
        self.trace_idx = 0
        self.selected = 0
        self.detail_open = True
        self.scroll_offset = 0
        # Picker position memory
        self.pick_sel = 0
        self.pick_scroll = 0
        # Per-trace position memory: trace_idx -> (selected, scroll_offset)
        self._trace_positions: Dict[int, Tuple[int, int]] = {}
        # Live-reload state
        self.monocle_dir = monocle_dir
        self.last_minutes = last_minutes
        self.trace_id_filter = trace_id_filter
        self.limit = limit
        self._known_files: set = {t[0] for t in traces}
        self._file_mtimes: Dict[str, float] = {}  # fname -> last known mtime
        if monocle_dir:
            for t in traces:
                p = monocle_dir / t[0]
                if p.exists():
                    self._file_mtimes[t[0]] = p.stat().st_mtime
        self._new_trace_ids: Dict[str, int] = {}  # trace_id -> fade ticks remaining
        self._fade_ticks = 8  # number of render cycles for fade

    def _check_new_traces(self):
        """Poll monocle_dir for new/modified trace files."""
        if not self.monocle_dir:
            return
        files = get_trace_files(self.monocle_dir, self.last_minutes,
                                self.trace_id_filter, self.limit)

        # Reload modified known files (file exporter appends spans across turns)
        for f in files:
            if f.name not in self._known_files:
                continue
            cur_mtime = f.stat().st_mtime
            prev_mtime = self._file_mtimes.get(f.name, 0)
            if cur_mtime <= prev_mtime:
                continue
            self._file_mtimes[f.name] = cur_mtime
            try:
                raw = load_trace(f)
            except Exception:
                continue
            roots, total_ms = build_tree(raw)
            if not roots:
                continue
            # Replace in-place
            for i, (fname, _, _) in enumerate(self.traces):
                if fname == f.name:
                    self.traces[i] = (f.name, roots, total_ms)
                    break

        # Discover new files
        seen_tids = {roots[0].trace_id for _, roots, _ in self.traces if roots}
        new_entries = []
        for f in files:
            if f.name in self._known_files:
                continue
            try:
                raw = load_trace(f)
            except Exception:
                continue
            roots, total_ms = build_tree(raw)
            if not roots:
                continue
            tid = roots[0].trace_id
            if tid in seen_tids:
                continue
            self._known_files.add(f.name)
            self._file_mtimes[f.name] = f.stat().st_mtime
            seen_tids.add(tid)
            self._new_trace_ids[tid] = self._fade_ticks
            new_entries.append((f.name, roots, total_ms))
        if new_entries:
            n = len(new_entries)
            self.pick_sel += n
            self.pick_scroll = 0
            shifted = {}
            for idx, pos in self._trace_positions.items():
                shifted[idx + n] = pos
            self._trace_positions = shifted
            self.traces = new_entries + self.traces

    def _fade_attr(self, trace_roots) -> Optional[int]:
        """Return a fade color attribute if this trace is newly appeared, else None."""
        if not trace_roots:
            return None
        tid = trace_roots[0].trace_id
        ticks = self._new_trace_ids.get(tid)
        if ticks is None:
            return None
        if ticks > 5:
            return curses.color_pair(C_NEW_BRIGHT) | curses.A_BOLD
        elif ticks > 2:
            return curses.color_pair(C_NEW_MID) | curses.A_BOLD
        elif ticks > 0:
            return curses.color_pair(C_NEW_MID)
        else:
            return None

    def _tick_fades(self):
        """Decrement fade counters and remove expired ones."""
        expired = []
        for tid in self._new_trace_ids:
            self._new_trace_ids[tid] -= 1
            if self._new_trace_ids[tid] <= 0:
                expired.append(tid)
        for tid in expired:
            del self._new_trace_ids[tid]

    @property
    def current(self):
        return self.traces[self.trace_idx]

    @property
    def visible_spans(self) -> List[Span]:
        _, roots, _ = self.current
        result = []
        for r in roots:
            result.extend(r.flat_visible())
        return result

    def trace_picker(self, stdscr) -> Optional[int]:
        """Show a trace selection screen with live-reload. Returns selected index or None to quit."""
        # Use halfdelay for ~2s polling (20 tenths of a second)
        curses.halfdelay(20)

        while True:
            # Poll for new trace files
            self._check_new_traces()

            stdscr.erase()
            h, w = stdscr.getmaxyx()

            # Header
            safe(stdscr, 0, 0, " " * w, curses.color_pair(C_HEADER))
            safe(stdscr, 0, 1, "OKAHU TRACE VIEWER", curses.color_pair(C_HEADER) | curses.A_BOLD)
            live_indicator = " LIVE" if self.monocle_dir else ""
            count_str = f"{live_indicator}  {len(self.traces)} traces "
            safe(stdscr, 0, max(0, w - len(count_str) - 1), count_str, curses.color_pair(C_HEADER))

            # Column headers
            y = 2
            safe(stdscr, y, 2, "#", curses.color_pair(C_DIM) | curses.A_BOLD)
            safe(stdscr, y, 5, "DATETIME", curses.color_pair(C_DIM) | curses.A_BOLD)
            safe(stdscr, y, 24, "TRACE ID", curses.color_pair(C_DIM) | curses.A_BOLD)
            safe(stdscr, y, 59, "SPANS", curses.color_pair(C_DIM) | curses.A_BOLD)
            safe(stdscr, y, 66, "DURATION", curses.color_pair(C_DIM) | curses.A_BOLD)
            safe(stdscr, y, 77, "WORKFLOW", curses.color_pair(C_DIM) | curses.A_BOLD)
            y += 1
            safe(stdscr, y, 0, "─" * w, curses.color_pair(C_BORDER))
            y += 1

            max_rows = h - y - 3  # room for footer

            # Scroll
            if self.pick_sel < self.pick_scroll:
                self.pick_scroll = self.pick_sel
            if self.pick_sel >= self.pick_scroll + max_rows:
                self.pick_scroll = self.pick_sel - max_rows + 1

            for idx in range(self.pick_scroll, min(len(self.traces), self.pick_scroll + max_rows)):
                fname, roots, total_ms = self.traces[idx]
                is_sel = idx == self.pick_sel

                # Determine base attr: selected, fade-in, or normal
                fade = self._fade_attr(roots)
                if is_sel:
                    safe(stdscr, y, 0, " " * w, curses.color_pair(C_SELECTED))
                    attr = curses.color_pair(C_SELECTED) | curses.A_BOLD
                elif fade is not None:
                    safe(stdscr, y, 0, " " * w, fade)
                    attr = fade
                else:
                    attr = curses.A_NORMAL

                # Count all spans
                all_spans = []
                for r in roots:
                    all_spans.extend(r.flat_visible())

                tid = roots[0].trace_id.removeprefix("0x") if roots else "unknown"
                # Find workflow.name from any span (usually root)
                wf_name = ""
                for r in roots:
                    wf_name = r.attributes.get("workflow.name", "")
                    if wf_name:
                        break
                num = f"{idx + 1}"
                dur = f"{total_ms:.0f}ms"
                span_count = str(len(all_spans))

                # Extract datetime from root span start_time
                start_dt = ""
                if roots and roots[0].start_time != datetime.min:
                    start_dt = roots[0].start_time.astimezone().strftime("%Y-%m-%d %H:%M")

                # NEW marker for fresh traces
                if fade is not None:
                    safe(stdscr, y, 2, "●", attr)
                else:
                    safe(stdscr, y, 2, num, attr)
                safe(stdscr, y, 5, start_dt, attr)
                safe(stdscr, y, 24, tid, attr)
                safe(stdscr, y, 59, span_count, attr)
                safe(stdscr, y, 66, dur, attr)
                safe(stdscr, y, 77, wf_name[:w - 79], attr)
                y += 1

            # Detail preview for selected trace
            if self.traces:
                fname, roots, total_ms = self.traces[self.pick_sel]
                fy = h - 3
                safe(stdscr, fy, 0, "─" * w, curses.color_pair(C_BORDER))
                safe(stdscr, fy + 1, 2, f"File: {fname}", curses.color_pair(C_DIM))

            # Footer
            fy = h - 1
            safe(stdscr, fy, 0, " " * w, curses.color_pair(C_HEADER))
            keys = "↑↓ Navigate  Enter Select  q Quit"
            safe(stdscr, fy, 1, keys, curses.color_pair(C_HEADER))

            stdscr.refresh()

            # Tick fade animations
            self._tick_fades()

            key = stdscr.getch()
            if key == curses.ERR:
                continue  # halfdelay timeout — just re-render
            if key == ord("q") or key == ord("Q") or key == 27:
                # Restore normal blocking input before returning
                curses.cbreak()
                return None
            elif key == curses.KEY_UP or key == ord("k"):
                self.pick_sel = max(0, self.pick_sel - 1)
            elif key == curses.KEY_DOWN or key == ord("j"):
                self.pick_sel = min(len(self.traces) - 1, self.pick_sel + 1)
            elif key == ord("\n") or key == ord(" "):
                # Restore normal blocking input before returning
                curses.cbreak()
                return self.pick_sel

    def run(self, stdscr):
        curses.curs_set(0)
        init_colors()

        while True:
            # Show trace picker if multiple traces loaded
            if len(self.traces) > 1:
                picked = self.trace_picker(stdscr)
                if picked is None:
                    return  # user quit from picker
                self.trace_idx = picked
                # Restore per-trace position or reset
                if picked in self._trace_positions:
                    self.selected, self.scroll_offset = self._trace_positions[picked]
                else:
                    self.selected = 0
                    self.scroll_offset = 0

            back_to_picker = self._view_trace(stdscr)
            if not back_to_picker:
                return

    def _span_detail_screen(self, stdscr, span: "Span"):
        """Full-screen scrollable detail view for a span."""
        curses.cbreak()
        scroll = 0

        # Build all lines as (text, color_pair) tuples
        lines: List[Tuple[str, int]] = []
        lines.append((f"● {span.display_name}", C_VAL))
        lines.append((f"  type: {span.span_type}", C_DIM))
        lines.append((f"  span_id: {span.span_id}", C_DIM))
        if span.parent_id:
            lines.append((f"  parent:  {span.parent_id}", C_DIM))
        dur = f"{span.duration_ms:.0f}ms" if span.duration_ms >= 1 else "<1ms"
        lines.append((f"  duration: {dur}", C_DIM))
        lines.append(("", 0))

        h_hint, w_hint = stdscr.getmaxyx()
        wrap_width = max(40, w_hint - 4)

        # Attributes
        if span.attributes:
            lines.append((" ── Attributes ──", C_KEY))
            for k, v in span.attributes.items():
                if k in ("span.type", "span.subtype"):
                    continue
                val = str(v)
                key_prefix = f"  {k}: "
                first_line_width = wrap_width - len(key_prefix)
                if first_line_width > 10 and len(val) <= first_line_width:
                    lines.append((f"{key_prefix}{val}", C_VAL))
                else:
                    lines.append((key_prefix, C_KEY))
                    for wl in word_wrap(val, wrap_width):
                        lines.append((wl, C_VAL))
            lines.append(("", 0))

        # Events (full content with word wrap)
        if span.events:
            lines.append((" ── Events ──", C_EVENT))
            for ev in span.events:
                lines.append((f"  {ev['name']}:", C_EVENT))
                val = ev["value"]
                for wl in word_wrap(val, wrap_width):
                    lines.append((wl, C_VAL))
                lines.append(("", 0))

        # Tokens
        if span.tokens:
            lines.append((" ── Tokens ──", C_KEY))
            for k, v in span.tokens.items():
                lines.append((f"  {k}: {v:,}", C_VAL))

        while True:
            stdscr.clear()
            h, w = stdscr.getmaxyx()

            # Header
            safe(stdscr, 0, 0, " " * w, curses.color_pair(C_HEADER))
            safe(stdscr, 0, 1, "SPAN DETAIL", curses.color_pair(C_HEADER) | curses.A_BOLD)
            safe(stdscr, 0, 14, span.display_name[:w - 30], curses.color_pair(C_HEADER))
            pos = f" {scroll+1}-{min(scroll+h-2, len(lines))}/{len(lines)} "
            safe(stdscr, 0, max(0, w - len(pos) - 1), pos, curses.color_pair(C_HEADER))

            # Content
            for i in range(scroll, min(len(lines), scroll + h - 2)):
                text, color = lines[i]
                attr = curses.color_pair(color) if color else curses.A_NORMAL
                safe(stdscr, 1 + i - scroll, 1, text[:w - 2], attr)

            # Footer
            fy = h - 1
            safe(stdscr, fy, 0, " " * w, curses.color_pair(C_HEADER))
            keys = "↑↓/j/k Scroll  PgUp/PgDn Page  q/Esc Back"
            safe(stdscr, fy, 1, keys, curses.color_pair(C_HEADER))

            stdscr.refresh()

            key = stdscr.getch()
            if key == ord("q") or key == ord("Q") or key == 27:
                curses.halfdelay(20)
                return
            elif key == curses.KEY_UP or key == ord("k"):
                scroll = max(0, scroll - 1)
            elif key == curses.KEY_DOWN or key == ord("j"):
                scroll = min(max(0, len(lines) - (h - 2)), scroll + 1)
            elif key == curses.KEY_PPAGE:  # Page Up
                scroll = max(0, scroll - (h - 3))
            elif key == curses.KEY_NPAGE:  # Page Down
                scroll = min(max(0, len(lines) - (h - 2)), scroll + (h - 3))
            elif key == ord("g"):  # top
                scroll = 0
            elif key == ord("G"):  # bottom
                scroll = max(0, len(lines) - (h - 2))
            elif key == curses.KEY_RESIZE:
                continue

    def _view_trace(self, stdscr) -> bool:
        """View a single trace. Returns True to go back to picker, False to quit."""
        curses.cbreak()
        while True:
            stdscr.erase()
            h, w = stdscr.getmaxyx()
            fname, roots, total_ms = self.current
            visible = self.visible_spans

            # Clamp selection
            if self.selected >= len(visible):
                self.selected = max(0, len(visible) - 1)

            # ── Header ──
            safe(stdscr, 0, 0, " " * w, curses.color_pair(C_HEADER))
            safe(stdscr, 0, 1, "OKAHU TRACE VIEWER", curses.color_pair(C_HEADER) | curses.A_BOLD)
            if visible:
                tid = visible[0].trace_id
                safe(stdscr, 0, 21, tid, curses.color_pair(C_HEADER))
            trace_nav = f" [{self.trace_idx+1}/{len(self.traces)}] "
            status_str = f"OK" if all(s.status != "ERROR" for s in visible) else "ERR"
            sc = C_OK if status_str == "OK" else C_ERR
            right = f"{status_str} | {total_ms:.0f}ms | {len(visible)} spans{trace_nav}"
            safe(stdscr, 0, max(0, w - len(right) - 1), right, curses.color_pair(C_HEADER))

            # ── Span list (waterfall) ──
            name_col = min(36, w // 3)
            bar_area = max(15, w - name_col - 15)
            y = 2

            # Column headers
            safe(stdscr, y, 1, "SPAN", curses.color_pair(C_DIM) | curses.A_BOLD)
            safe(stdscr, y, name_col, "TIMELINE", curses.color_pair(C_DIM) | curses.A_BOLD)
            safe(stdscr, y, name_col + bar_area + 1, "DURATION", curses.color_pair(C_DIM) | curses.A_BOLD)
            y += 1
            safe(stdscr, y, 0, "─" * w, curses.color_pair(C_BORDER))
            y += 1

            # Calculate how many span rows fit
            detail_height = min(h // 2, 30) if self.detail_open else 0
            max_span_rows = h - y - detail_height - 2  # 2 for footer

            # Scroll if needed
            if self.selected < self.scroll_offset:
                self.scroll_offset = self.selected
            if self.selected >= self.scroll_offset + max_span_rows:
                self.scroll_offset = self.selected - max_span_rows + 1

            for idx in range(self.scroll_offset, min(len(visible), self.scroll_offset + max_span_rows)):
                span = visible[idx]
                is_sel = idx == self.selected

                # Build tree prefix with connector lines
                prefix = tree_prefix(span)
                collapse_marker = ""
                if span.children:
                    collapse_marker = "▸" if span.collapsed else "▾"
                label = f"{prefix}{collapse_marker}{span.display_name}"
                label = label[:name_col - 1]

                if is_sel:
                    safe(stdscr, y, 0, " " * w, curses.color_pair(C_SELECTED))
                    attr = curses.color_pair(C_SELECTED) | curses.A_BOLD
                else:
                    attr = curses.A_NORMAL

                # Draw tree connectors in dim color, then the name
                if not is_sel and prefix:
                    safe(stdscr, y, 1, prefix, curses.color_pair(C_TREE))
                    rest = f"{collapse_marker}{span.display_name}"
                    rest = rest[:name_col - 1 - len(prefix)]
                    safe(stdscr, y, 1 + len(prefix), rest, attr)
                else:
                    safe(stdscr, y, 1, label, attr)

                # Bar
                frac = span.duration_ms / total_ms if total_ms > 0 else 0
                bar_len = max(1, int(bar_area * frac))
                bc = bar_color(span.span_type)
                draw_bar(stdscr, y, name_col, bar_len, bc)

                # Show span_id overlapping the bar when highlighted
                if is_sel:
                    sid = span.span_id
                    if len(sid) > bar_area - 1:
                        sid = sid[:bar_area - 1]
                    safe(stdscr, y, name_col + 1, sid, curses.color_pair(bc) | curses.A_BOLD)

                # Duration
                dur = f"{span.duration_ms:.0f}ms" if span.duration_ms >= 1 else "<1ms"
                dur_attr = attr if is_sel else curses.A_NORMAL
                safe(stdscr, y, name_col + bar_area + 1, dur, dur_attr)

                y += 1

            # ── Detail panel ──
            if self.detail_open and visible:
                span = visible[self.selected]
                dy = h - detail_height - 1
                safe(stdscr, dy, 0, "─" * w, curses.color_pair(C_BORDER))
                dy += 1

                # Title row
                safe(stdscr, dy, 1, f"● {span.display_name}", curses.A_BOLD)
                safe(stdscr, dy, 3 + len(span.display_name), f"  {span.span_type}", curses.color_pair(C_DIM))
                dy += 1
                safe(stdscr, dy, 1, f"span_id: {span.span_id}", curses.color_pair(C_DIM))
                dy += 1
                if span.parent_id:
                    safe(stdscr, dy, 1, f"parent:  {span.parent_id}", curses.color_pair(C_DIM))
                    dy += 1
                dy += 1

                # Attributes (single column, full width)
                attr_items = [(k, str(v)) for k, v in span.attributes.items()
                              if k not in ("span.type", "span.subtype")]
                for k, v in attr_items:
                    if dy >= h - 2:
                        break
                    safe(stdscr, dy, 2, f"{k}:", curses.color_pair(C_KEY))
                    val_x = 4 + len(k)
                    max_val_w = w - val_x - 1
                    safe(stdscr, dy, val_x, v[:max_val_w], curses.color_pair(C_VAL))
                    remaining = v[max_val_w:]
                    dy += 1
                    while remaining and dy < h - 2:
                        safe(stdscr, dy, val_x, remaining[:max_val_w], curses.color_pair(C_VAL))
                        remaining = remaining[max_val_w:]
                        dy += 1

                # Events
                if span.events and dy < h - 2:
                    dy += 1
                    for ev in span.events:
                        if dy >= h - 2:
                            break
                        val = ev["value"]
                        val_x = 4 + len(ev["name"])
                        max_val_w = w - val_x - 1
                        safe(stdscr, dy, 2, ev["name"], curses.color_pair(C_EVENT))
                        safe(stdscr, dy, val_x, val[:max_val_w], curses.color_pair(C_VAL))
                        dy += 1
                        # Wrap remaining text onto continuation lines
                        remaining = val[max_val_w:]
                        wrap_x = val_x
                        wrap_w = w - wrap_x - 1
                        while remaining and dy < h - 2:
                            safe(stdscr, dy, wrap_x, remaining[:wrap_w], curses.color_pair(C_VAL))
                            remaining = remaining[wrap_w:]
                            dy += 1

                # Tokens
                if span.tokens and dy < h - 1:
                    tok_str = "  ".join(f"{k}={v:,}" for k, v in span.tokens.items())
                    safe(stdscr, dy, 2, "tokens:", curses.color_pair(C_KEY))
                    safe(stdscr, dy, 10, tok_str, curses.color_pair(C_VAL))

            # ── Footer ──
            fy = h - 1
            safe(stdscr, fy, 0, " " * w, curses.color_pair(C_HEADER))
            keys = "↑↓ Navigate  ←→ Collapse  Enter Open  Space Detail  r Refresh  t Trace  Esc Back  q Quit"
            safe(stdscr, fy, 1, keys, curses.color_pair(C_HEADER))
            safe(stdscr, fy, max(0, w - len(fname) - 2), fname[:w - 2], curses.color_pair(C_HEADER))

            stdscr.refresh()

            # ── Input ──
            key = stdscr.getch()
            if key == ord("q") or key == ord("Q"):
                curses.cbreak()
                return False
            elif key == 27 or key == ord("b") or key == ord("B"):
                # Esc or b → back to trace picker (or quit if single trace)
                # Save position for this trace before leaving
                self._trace_positions[self.trace_idx] = (self.selected, self.scroll_offset)
                if len(self.traces) > 1:
                    curses.halfdelay(20)
                    return True
                else:
                    return False
            elif key == curses.KEY_UP or key == ord("k"):
                self.selected = max(0, self.selected - 1)
            elif key == curses.KEY_DOWN or key == ord("j"):
                self.selected = min(len(visible) - 1, self.selected + 1)
            elif key == curses.KEY_LEFT or key == ord("h"):
                s = visible[self.selected]
                if s.children:
                    s.collapsed = True
            elif key == curses.KEY_RIGHT or key == ord("l"):
                s = visible[self.selected]
                if s.children:
                    s.collapsed = False
            elif key == ord("\n") or key == ord("o") or key == ord("O"):
                # Enter or o → open full-screen span detail
                if visible:
                    self._span_detail_screen(stdscr, visible[self.selected])
            elif key == ord(" "):
                self.detail_open = not self.detail_open
            elif key == ord("r") or key == ord("R"):
                self._check_new_traces()
            elif key == ord("t") or key == ord("T"):
                self._trace_positions[self.trace_idx] = (self.selected, self.scroll_offset)
                self.trace_idx = (self.trace_idx + 1) % len(self.traces)
                if self.trace_idx in self._trace_positions:
                    self.selected, self.scroll_offset = self._trace_positions[self.trace_idx]
                else:
                    self.selected = 0
                    self.scroll_offset = 0


# ── Non-interactive (print) mode ────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RED = "\033[31m"
GRAY = "\033[90m"
WHITE = "\033[97m"
ULINE = "\033[4m"

BAR_COLORS = {
    "workflow": "\033[44;97m",
    "turn": "\033[42;30m",
    "inference": "\033[45;97m",
    "tool": "\033[43;30m",
    "agent": "\033[41;97m",
    "mcp": "\033[47;30m",
}


def get_bar_color(span_type: str) -> str:
    for k, v in BAR_COLORS.items():
        if k in span_type:
            return v
    return GRAY


def print_trace(fname: str, roots: List[Span], total_ms: float):
    tid = roots[0].trace_id if roots else "unknown"

    # Collect all visible spans
    all_spans = []
    for r in roots:
        all_spans.extend(r.flat_visible())

    print()
    print(f"{BOLD}{CYAN}{'━' * 72}{RESET}")
    print(f"  {BOLD}Trace{RESET}     {GRAY}{tid}{RESET}")
    print(f"  {BOLD}Duration{RESET}  {total_ms:.0f}ms")
    print(f"  {BOLD}Spans{RESET}     {len(all_spans)}")
    print(f"  {BOLD}File{RESET}      {GRAY}{fname}{RESET}")
    print()

    # Waterfall
    bar_w = 30
    print(f"  {GRAY}{'SPAN':<30}{'TIMELINE':<{bar_w+2}} DURATION{RESET}")
    print(f"  {GRAY}{'─' * 68}{RESET}")

    for span in all_spans:
        prefix = tree_prefix(span)
        label = f"{prefix}{span.display_name}"[:30]
        frac = span.duration_ms / total_ms if total_ms > 0 else 0
        filled = max(1, int(bar_w * frac))
        empty = bar_w - filled
        bc = get_bar_color(span.span_type)
        bar = f"{bc}{' ' * filled}{RESET}{GRAY}{'░' * empty}{RESET}"
        dur = f"{span.duration_ms:.0f}ms" if span.duration_ms >= 1 else "<1ms"
        print(f"  {WHITE}{label:<30}{RESET} {bar} {BOLD}{dur}{RESET}")

    print()

    # Span details
    for i, span in enumerate(all_spans):
        print(f"  {BOLD}{CYAN}── Span {i+1}/{len(all_spans)}: {span.display_name}{RESET} {GRAY}{span.span_type}{RESET}")
        print(f"    {GRAY}id: {span.span_id}{RESET}")
        dur = f"{span.duration_ms:.0f}ms" if span.duration_ms >= 1 else "<1ms"
        print(f"    {GRAY}duration: {dur}{RESET}")

        for k, v in span.attributes.items():
            if k in ("span.type", "span.subtype"):
                continue
            print(f"    {CYAN}{k}{RESET}: {v}")

        for ev in span.events:
            val = ev["value"]
            print(f"    {YELLOW}{ev['name']}{RESET}  {val}")

        if span.tokens:
            tok_str = "  ".join(f"{k}={v:,}" for k, v in span.tokens.items())
            print(f"    {CYAN}tokens{RESET}: {tok_str}")
        print()

    print(f"{BOLD}{CYAN}{'━' * 72}{RESET}")


# ── CLI ─────────────────────────────────────────────────────────────

def parse_time(s: str) -> Optional[int]:
    if not s:
        return None
    try:
        if s.endswith("m"):
            return int(s[:-1])
        if s.endswith("h"):
            return int(s[:-1]) * 60
        return int(s)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description="Interactive monocle trace viewer")
    parser.add_argument("--dir", "-d", default=".monocle", help="Monocle trace directory")
    parser.add_argument("--last", "-l", help="Traces from last N minutes (e.g. 5m, 1h)")
    parser.add_argument("--trace-id", "-t", help="Filter by trace ID (partial match)")
    parser.add_argument("--limit", "-n", type=int, default=0, help="Max trace files (0=unlimited)")
    parser.add_argument("--print", "-p", action="store_true", help="Non-interactive print mode")
    args = parser.parse_args()

    monocle_dir = resolve_monocle_dir(args.dir)
    last_min = parse_time(args.last)
    files = get_trace_files(monocle_dir, last_min, args.trace_id, args.limit)

    if not files:
        print(f"No trace files found in {monocle_dir}/", file=sys.stderr)
        sys.exit(1)

    # Load and deduplicate by trace_id
    traces = []
    seen = set()
    for f in files:
        try:
            raw = load_trace(f)
        except Exception as e:
            print(f"Error loading {f}: {e}", file=sys.stderr)
            continue
        roots, total_ms = build_tree(raw)
        if not roots:
            continue
        tid = roots[0].trace_id
        if tid in seen:
            continue
        seen.add(tid)
        traces.append((f.name, roots, total_ms))

    if not traces:
        print("No valid traces found.", file=sys.stderr)
        sys.exit(1)

    if args.print or not sys.stdout.isatty():
        for fname, roots, total_ms in traces:
            print_trace(fname, roots, total_ms)
    else:
        viewer = TraceViewer(traces, monocle_dir=monocle_dir,
                             last_minutes=last_min,
                             trace_id_filter=args.trace_id,
                             limit=args.limit)
        curses.wrapper(viewer.run)


if __name__ == "__main__":
    main()
