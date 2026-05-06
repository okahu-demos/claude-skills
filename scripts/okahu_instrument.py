#!/usr/bin/env python3
"""
okahu-instrument: Zero-code instrumentation CLI for monocle.

Similar to `opentelemetry-instrument`, this wraps any Python command
with monocle tracing enabled via okahu.yaml config.

Usage:
    okahu-instrument python app.py
    okahu-instrument flask run
    okahu-instrument uvicorn app:app --reload
    okahu-instrument celery -A app worker

Options:
    --config FILE    Path to okahu.yaml config (default: okahu.yaml)
    --help           Show this help message

Environment Variables:
    MONOCLE_STRICT=true    Fail if instrumentation breaks (default: fail-open)
    MONOCLE_SILENT=true    Suppress warnings on failure
    OKAHU_INGESTION_ENDPOINT   Okahu cloud endpoint
    OKAHU_API_KEY              Okahu API key
"""

import argparse
import importlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path


def mask_key(key: str) -> str:
    """Mask API key showing first 8 and last 4 chars."""
    if not key or len(key) < 12:
        return "***"
    return f"{key[:8]}...{key[-4:]}"


def print_config(config_path: str, workflow_name: str):
    """Print configuration for debugging."""
    endpoint = os.environ.get("OKAHU_INGESTION_ENDPOINT", "(not set)")
    api_key = os.environ.get("OKAHU_API_KEY", "")

    print(f"[okahu-instrument] Config: {config_path}")
    print(f"[okahu-instrument] Workflow: {workflow_name}")
    print(f"[okahu-instrument] Endpoint: {endpoint}")
    print(f"[okahu-instrument] API Key: {mask_key(api_key)}")


def load_config(config_path: str) -> dict:
    """Load YAML config file."""
    try:
        import yaml
    except ImportError:
        print("[okahu-instrument] ERROR: PyYAML not installed. Run: pip install pyyaml")
        sys.exit(1)

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def create_input_output_processor(span_name: str, package: str = None,
                                   class_name: str = None, method: str = None):
    """Create an output processor that captures input args and return values."""
    _param_names_cache = {}

    def _get_param_names(instance):
        """Get parameter names for the wrapped function."""
        cache_key = (package, class_name, method)
        if cache_key in _param_names_cache:
            return _param_names_cache[cache_key]

        param_names = []
        try:
            if instance is not None and method:
                func = getattr(instance, method, None)
                if func:
                    sig = inspect.signature(func)
                    param_names = list(sig.parameters.keys())
            elif package and method:
                mod = importlib.import_module(package)
                if class_name:
                    cls = getattr(mod, class_name, None)
                    func = getattr(cls, method, None) if cls else None
                else:
                    func = getattr(mod, method, None)
                if func:
                    sig = inspect.signature(func)
                    param_names = list(sig.parameters.keys())
                    if param_names and param_names[0] == 'self':
                        param_names = param_names[1:]
        except Exception:
            pass

        _param_names_cache[cache_key] = param_names
        return param_names

    def get_input_args(arguments):
        """Extract input arguments as JSON string."""
        args = arguments.get('args', ())
        kwargs = arguments.get('kwargs', {})
        instance = arguments.get('instance')

        param_names = _get_param_names(instance)
        input_data = {}

        for i, arg in enumerate(args):
            key = param_names[i] if i < len(param_names) else f"arg_{i}"
            try:
                if hasattr(arg, '__dict__') and not isinstance(arg, (str, int, float, bool, list, dict)):
                    input_data[key] = f"<{type(arg).__name__}>"
                else:
                    input_data[key] = arg
            except:
                input_data[key] = str(arg)[:200]

        for k, v in kwargs.items():
            try:
                if hasattr(v, '__dict__') and not isinstance(v, (str, int, float, bool, list, dict)):
                    input_data[k] = f"<{type(v).__name__}>"
                else:
                    input_data[k] = v
            except:
                input_data[k] = str(v)[:200]

        return json.dumps(input_data)[:1000]

    def get_output_result(arguments):
        """Extract return value as string."""
        result = arguments.get('result')
        if result is None:
            return "None"
        try:
            if hasattr(result, '__dict__') and not isinstance(result, (str, int, float, bool, list, dict)):
                return f"<{type(result).__name__}>: {str(result)[:200]}"
            return json.dumps(result)[:500]
        except:
            return str(result)[:500]

    def get_function_name(arguments):
        return span_name

    return {
        "type": "custom",
        "attributes": [
            [
                {"attribute": "name", "accessor": get_function_name},
                {"attribute": "type", "accessor": lambda args: "function.custom"},
            ],
        ],
        "events": [
            {
                "name": "data.input",
                "attributes": [
                    {"attribute": "input", "accessor": get_input_args},
                ]
            },
            {
                "name": "data.output",
                "attributes": [
                    {"attribute": "output", "accessor": get_output_result, "phase": "post_execution"},
                ]
            }
        ]
    }


def build_wrapper_methods(config: dict) -> list:
    """Build WrapperMethod list from config."""
    try:
        from monocle_apptrace.instrumentation.common.wrapper_method import WrapperMethod
        from monocle_apptrace.instrumentation.common.wrapper import task_wrapper, atask_wrapper
    except ImportError:
        print("[okahu-instrument] ERROR: monocle_apptrace not installed.")
        print("[okahu-instrument] Run: pip install monocle_apptrace")
        sys.exit(1)

    wrapper_methods = []
    for item in config.get('instrument', []):
        package = item.get('package')
        class_name = item.get('class')
        method = item.get('method')
        span_name = item.get('span_name',
            f"{package}.{class_name}.{method}" if class_name else f"{package}.{method}")
        is_async = item.get('async', False)

        wrapper_methods.append(
            WrapperMethod(
                package=package,
                object_name=class_name,
                method=method,
                span_name=span_name,
                wrapper_method=atask_wrapper if is_async else task_wrapper,
                output_processor=create_input_output_processor(span_name, package, class_name, method)
            )
        )
    return wrapper_methods


def setup_instrumentation(config_path: str) -> tuple:
    """
    Setup instrumentation from config file.
    Returns (success: bool, workflow_name: str, error_message: str)
    """
    try:
        from monocle_apptrace import setup_monocle_telemetry

        config = load_config(config_path)
        workflow_name = config.get('workflow_name', 'unknown')
        wrapper_methods = build_wrapper_methods(config)

        setup_monocle_telemetry(
            workflow_name=workflow_name,
            wrapper_methods=wrapper_methods,
            union_with_default_methods=True  # Also use default instrumentation
        )

        return True, workflow_name, None

    except ImportError as e:
        return False, None, f"Missing dependency: {e}"
    except Exception as e:
        return False, None, str(e)


def run_command(command: list):
    """Run the target command as a subprocess."""
    try:
        # Use subprocess to run the command
        # This allows wrapping any command, not just python scripts
        process = subprocess.run(command, env=os.environ)
        return process.returncode
    except KeyboardInterrupt:
        print("\n[okahu-instrument] Interrupted")
        return 130
    except Exception as e:
        print(f"[okahu-instrument] Error running command: {e}")
        return 1


def run_python_inline(script: str, args: list, packages: list = None):
    """Run a Python script in the same process (for python commands)."""
    import runpy
    import importlib

    script_dir = os.path.dirname(os.path.abspath(script))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    # wrapt defers patches via post-import hooks. Import each target package
    # so the patches land on the real module objects before execution.
    module_name = os.path.splitext(os.path.basename(script))[0]
    for pkg in (packages or []):
        try:
            importlib.import_module(pkg)
        except Exception:
            pass

    # If the script's own module was patched, import it and call its __main__
    # guard via the patched module. runpy re-executes source from disk, which
    # bypasses wrapt patches entirely.
    target_module = sys.modules.get(module_name)
    sys.argv = [os.path.abspath(script)] + args
    try:
        if target_module and hasattr(target_module, 'main'):
            target_module.main()
        else:
            runpy.run_path(path_name=script, run_name="__main__")
    except SystemExit as e:
        return e.code if e.code else 0
    except Exception as e:
        print(f"[okahu-instrument] Error: {e}")
        return 1
    finally:
        # Flush spans
        try:
            from monocle_apptrace.instrumentation.common.instrumentor import get_monocle_span_processor
            processor = get_monocle_span_processor()
            if processor:
                processor.force_flush(timeout_millis=5000)
                print("[okahu-instrument] Spans flushed")
        except Exception:
            pass
    return 0


def main():
    # Custom argument parsing to handle arbitrary commands
    args = sys.argv[1:]

    # Handle help
    if not args or args[0] in ['-h', '--help']:
        print(__doc__)
        sys.exit(0)

    # Parse --config option
    config_path = 'okahu.yaml'
    if '--config' in args:
        idx = args.index('--config')
        if idx + 1 < len(args):
            config_path = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
        else:
            print("[okahu-instrument] ERROR: --config requires a path")
            sys.exit(1)

    if not args:
        print("[okahu-instrument] ERROR: No command specified")
        print("[okahu-instrument] Usage: okahu-instrument [--config FILE] <command...>")
        sys.exit(1)

    # Check config exists
    if not Path(config_path).exists():
        print(f"[okahu-instrument] ERROR: Config not found: {config_path}")
        print(f"[okahu-instrument] Run /ok-instrument first to generate okahu.yaml")
        sys.exit(1)

    # Environment flags
    strict_mode = os.environ.get('MONOCLE_STRICT', '').lower() == 'true'
    silent_mode = os.environ.get('MONOCLE_SILENT', '').lower() == 'true'

    # Setup instrumentation
    success, workflow_name, error = setup_instrumentation(config_path)

    if success:
        print_config(config_path, workflow_name)
        print(f"[okahu-instrument] Instrumentation: ENABLED")
    else:
        if strict_mode:
            print(f"[okahu-instrument] ERROR: {error}")
            print(f"[okahu-instrument] MONOCLE_STRICT=true, exiting.")
            sys.exit(1)
        else:
            if not silent_mode:
                print(f"[okahu-instrument] WARNING: {error}")
                print(f"[okahu-instrument] Continuing without instrumentation (fail-open)")
            print(f"[okahu-instrument] Instrumentation: DISABLED")

    print(f"[okahu-instrument] Running: {' '.join(args)}")
    print("-" * 60)

    # Determine how to run the command
    command = args[0]

    if command == 'python' or command == 'python3':
        # For python commands, run inline to keep instrumentation in same process
        if len(args) < 2:
            print("[okahu-instrument] ERROR: No script specified")
            sys.exit(1)
        script = args[1]
        script_args = args[2:]
        # Extract unique package names from config for pre-import
        config = load_config(config_path)
        packages = list({item['package'] for item in config.get('instrument', []) if 'package' in item})
        exit_code = run_python_inline(script, script_args, packages=packages)
    else:
        # For other commands (flask, uvicorn, etc.), we need to inject via env
        # Set up environment for subprocess to pick up instrumentation
        os.environ['MONOCLE_CONFIG'] = config_path
        os.environ['MONOCLE_WORKFLOW'] = workflow_name or 'unknown'

        # For non-python commands, run as subprocess
        # Note: This requires the target app to also have monocle setup
        # or we use sitecustomize approach
        exit_code = run_command(args)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
