#!/usr/bin/env python3
"""
AST Parser - Extract code structure from Python files.

Extracts classes, methods, arguments, return types, docstrings, and calls.

Usage:
    python ast_parser.py /path/to/app
    python ast_parser.py /path/to/app --output .okahu/ast_data.json

Output: JSON with structure:
{
  "modules": {
    "path/to/file.py": {
      "classes": {...},
      "functions": {...},
      "imports": [...]
    }
  }
}
"""

import argparse
import ast
import json
import os
import sys
from pathlib import Path
from typing import Any


class CallVisitor(ast.NodeVisitor):
    """Extract function/method calls from an AST node."""

    def __init__(self):
        self.calls = []

    def visit_Call(self, node: ast.Call):
        call_name = self._get_call_name(node.func)
        if call_name:
            self.calls.append(call_name)
        self.generic_visit(node)

    def _get_call_name(self, node) -> str | None:
        """Extract the name of a call target."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value = self._get_call_name(node.value)
            if value:
                return f"{value}.{node.attr}"
            return node.attr
        elif isinstance(node, ast.Subscript):
            return self._get_call_name(node.value)
        return None


class ASTParser:
    """Parse Python files and extract code structure."""

    # Directories to skip
    SKIP_DIRS = {
        '__pycache__', '.git', '.svn', '.hg',
        'node_modules', 'venv', 'env', '.env',
        '.venv', '.tox', '.pytest_cache', '.mypy_cache',
        'dist', 'build', 'egg-info', '.eggs',
        '.okahu', '.monocle'
    }

    # Files to skip
    SKIP_FILES = {
        'setup.py', 'conftest.py', '__init__.py'
    }

    # Methods to skip (dunder/magic methods)
    SKIP_METHODS = {
        '__init__', '__new__', '__del__',
        '__str__', '__repr__', '__format__',
        '__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__',
        '__hash__', '__bool__',
        '__getattr__', '__setattr__', '__delattr__', '__getattribute__',
        '__get__', '__set__', '__delete__',
        '__call__', '__len__', '__iter__', '__next__', '__contains__',
        '__getitem__', '__setitem__', '__delitem__',
        '__enter__', '__exit__', '__aenter__', '__aexit__',
        '__await__', '__aiter__', '__anext__',
        '__add__', '__sub__', '__mul__', '__truediv__', '__floordiv__',
        '__mod__', '__pow__', '__and__', '__or__', '__xor__',
        '__radd__', '__rsub__', '__rmul__', '__rtruediv__',
        '__iadd__', '__isub__', '__imul__', '__itruediv__',
        '__neg__', '__pos__', '__abs__', '__invert__',
        '__copy__', '__deepcopy__', '__reduce__', '__reduce_ex__',
        '__sizeof__', '__class_getitem__',
    }

    # Safe constant name mapping
    CONSTANT_VALUES = {
        'None': None,
        'True': True,
        'False': False
    }

    def __init__(self, root_path: str, include_init: bool = False, include_dunder: bool = False):
        self.root_path = Path(root_path).resolve()
        self.include_init = include_init
        self.include_dunder = include_dunder
        self.modules = {}

    def parse(self) -> dict:
        """Parse all Python files in the root path."""
        if self.root_path.is_file():
            self._parse_file(self.root_path)
        else:
            self._parse_directory(self.root_path)

        return {
            "root": str(self.root_path),
            "modules": self.modules,
            "summary": self._get_summary()
        }

    def _parse_directory(self, path: Path):
        """Recursively parse Python files in directory."""
        for item in path.iterdir():
            if item.is_dir():
                if item.name not in self.SKIP_DIRS and not item.name.startswith('.'):
                    self._parse_directory(item)
            elif item.suffix == '.py':
                if item.name not in self.SKIP_FILES or (item.name == '__init__.py' and self.include_init):
                    self._parse_file(item)

    def _parse_file(self, file_path: Path):
        """Parse a single Python file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()

            tree = ast.parse(source, filename=str(file_path))
            rel_path = str(file_path.relative_to(self.root_path)) if file_path.is_relative_to(self.root_path) else str(file_path)

            module_data = {
                "path": str(file_path),
                "classes": {},
                "functions": {},
                "imports": self._extract_imports(tree),
                "module_docstring": ast.get_docstring(tree)
            }

            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    class_data = self._parse_class(node)
                    module_data["classes"][node.name] = class_data
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    func_data = self._parse_function(node)
                    module_data["functions"][node.name] = func_data

            self.modules[rel_path] = module_data

        except SyntaxError as e:
            print(f"[WARN] Syntax error in {file_path}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Failed to parse {file_path}: {e}", file=sys.stderr)

    def _extract_imports(self, tree: ast.Module) -> list[dict]:
        """Extract import statements."""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        "type": "import",
                        "module": alias.name,
                        "alias": alias.asname,
                        "lineno": node.lineno
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append({
                        "type": "from",
                        "module": module,
                        "name": alias.name,
                        "alias": alias.asname,
                        "lineno": node.lineno
                    })
        return imports

    def _parse_class(self, node: ast.ClassDef) -> dict:
        """Parse a class definition."""
        methods = {}
        class_vars = []

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip dunder methods unless explicitly included
                if not self.include_dunder and item.name in self.SKIP_METHODS:
                    continue
                methods[item.name] = self._parse_function(item, is_method=True)
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                class_vars.append({
                    "name": item.target.id,
                    "type": self._get_annotation(item.annotation),
                    "lineno": item.lineno
                })

        return {
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "docstring": ast.get_docstring(node),
            "bases": [self._get_name(base) for base in node.bases],
            "decorators": [self._get_decorator(d) for d in node.decorator_list],
            "methods": methods,
            "class_variables": class_vars
        }

    def _parse_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool = False) -> dict:
        """Parse a function or method definition."""
        args = self._parse_arguments(node.args, is_method)
        calls = self._extract_calls(node)

        return {
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "docstring": ast.get_docstring(node),
            "decorators": [self._get_decorator(d) for d in node.decorator_list],
            "args": args,
            "returns": self._get_annotation(node.returns),
            "calls": calls
        }

    def _parse_arguments(self, args: ast.arguments, is_method: bool = False) -> list[dict]:
        """Parse function arguments."""
        result = []

        # Calculate defaults offset
        num_args = len(args.args)
        num_defaults = len(args.defaults)
        defaults_offset = num_args - num_defaults

        for i, arg in enumerate(args.args):
            # Skip 'self' and 'cls' for methods
            if is_method and i == 0 and arg.arg in ('self', 'cls'):
                continue

            default = None
            if i >= defaults_offset:
                default_node = args.defaults[i - defaults_offset]
                default = self._get_default_value(default_node)

            result.append({
                "name": arg.arg,
                "type": self._get_annotation(arg.annotation),
                "default": default,
                "has_default": i >= defaults_offset
            })

        # Handle *args
        if args.vararg:
            result.append({
                "name": f"*{args.vararg.arg}",
                "type": self._get_annotation(args.vararg.annotation),
                "default": None,
                "has_default": False
            })

        # Handle keyword-only args
        for i, arg in enumerate(args.kwonlyargs):
            default = None
            if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
                default = self._get_default_value(args.kw_defaults[i])

            result.append({
                "name": arg.arg,
                "type": self._get_annotation(arg.annotation),
                "default": default,
                "has_default": args.kw_defaults[i] is not None if i < len(args.kw_defaults) else False
            })

        # Handle **kwargs
        if args.kwarg:
            result.append({
                "name": f"**{args.kwarg.arg}",
                "type": self._get_annotation(args.kwarg.annotation),
                "default": None,
                "has_default": False
            })

        return result

    def _extract_calls(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """Extract all function/method calls within a function body."""
        visitor = CallVisitor()
        for child in node.body:
            visitor.visit(child)
        # Deduplicate while preserving order
        seen = set()
        unique_calls = []
        for call in visitor.calls:
            if call not in seen:
                seen.add(call)
                unique_calls.append(call)
        return unique_calls

    def _get_annotation(self, node) -> str | None:
        """Convert annotation node to string."""
        if node is None:
            return None
        return self._get_name(node)

    def _get_name(self, node) -> str:
        """Get string representation of a name/attribute node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value = self._get_name(node.value)
            return f"{value}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            value = self._get_name(node.value)
            slice_str = self._get_name(node.slice)
            return f"{value}[{slice_str}]"
        elif isinstance(node, ast.Tuple):
            elements = ", ".join(self._get_name(e) for e in node.elts)
            return elements
        elif isinstance(node, ast.List):
            elements = ", ".join(self._get_name(e) for e in node.elts)
            return f"[{elements}]"
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.BinOp):
            left = self._get_name(node.left)
            right = self._get_name(node.right)
            if isinstance(node.op, ast.BitOr):
                return f"{left} | {right}"
            return f"{left} ? {right}"
        elif isinstance(node, ast.Call):
            return self._get_name(node.func) + "(...)"
        else:
            return ast.unparse(node) if hasattr(ast, 'unparse') else str(type(node).__name__)

    def _get_default_value(self, node) -> Any:
        """Get the default value from an AST node."""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.List):
            return []
        elif isinstance(node, ast.Dict):
            return {}
        elif isinstance(node, ast.Set):
            return set()
        elif isinstance(node, ast.Tuple):
            return ()
        elif isinstance(node, ast.Name):
            # Safe lookup for known constants
            if node.id in self.CONSTANT_VALUES:
                return self.CONSTANT_VALUES[node.id]
            return f"<{node.id}>"
        else:
            return f"<{type(node).__name__}>"

    def _get_decorator(self, node) -> str:
        """Get decorator as string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_name(node)
        elif isinstance(node, ast.Call):
            name = self._get_name(node.func)
            args = []
            for arg in node.args:
                args.append(self._get_name(arg))
            for kw in node.keywords:
                args.append(f"{kw.arg}={self._get_name(kw.value)}")
            return f"{name}({', '.join(args)})"
        return str(node)

    def _get_summary(self) -> dict:
        """Generate summary statistics."""
        total_classes = 0
        total_methods = 0
        total_functions = 0

        for module in self.modules.values():
            total_functions += len(module["functions"])
            for cls in module["classes"].values():
                total_classes += 1
                total_methods += len(cls["methods"])

        return {
            "total_modules": len(self.modules),
            "total_classes": total_classes,
            "total_methods": total_methods,
            "total_functions": total_functions
        }


def main():
    parser = argparse.ArgumentParser(
        description="Parse Python files and extract code structure"
    )
    parser.add_argument("path", help="Path to Python file or directory")
    parser.add_argument(
        "--output", "-o",
        default=".okahu/ast_data.json",
        help="Output JSON file path (default: .okahu/ast_data.json)"
    )
    parser.add_argument(
        "--include-init",
        action="store_true",
        help="Include __init__.py files"
    )
    parser.add_argument(
        "--include-dunder",
        action="store_true",
        help="Include dunder methods (__init__, __str__, etc.)"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output"
    )

    args = parser.parse_args()

    # Parse
    ast_parser = ASTParser(args.path, include_init=args.include_init, include_dunder=args.include_dunder)
    result = ast_parser.parse()

    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        if args.pretty:
            json.dump(result, f, indent=2, default=str)
        else:
            json.dump(result, f, default=str)

    # Print summary
    summary = result["summary"]
    print(f"Parsed {summary['total_modules']} modules:")
    print(f"  - {summary['total_classes']} classes")
    print(f"  - {summary['total_methods']} methods")
    print(f"  - {summary['total_functions']} functions")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
