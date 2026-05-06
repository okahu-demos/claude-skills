"""
CLI-style instrumentation using YAML config with fail-open behavior.

Usage:
    python -m instrument --config okahu.yaml my_app.py

Environment Variables:
    MONOCLE_STRICT=true    - Fail if instrumentation breaks (for dev/testing)
    MONOCLE_SILENT=true    - Suppress warnings on failure
    MONOCLE_EXPORTER       - Exporter(s) to use (e.g., "okahu,file")
    OKAHU_INGESTION_ENDPOINT - Okahu ingestion endpoint
    OKAHU_API_KEY          - Okahu API key
"""
import argparse
import importlib
import inspect
import json
import os
import sys
import traceback
import runpy

# Add examples dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def mask_key(key: str) -> str:
    """Mask API key showing first 8 and last 4 chars."""
    if not key or len(key) < 12:
        return "***"
    return f"{key[:8]}...{key[-4:]}"


def print_config():
    """Print configuration for debugging."""
    endpoint = os.environ.get("OKAHU_INGESTION_ENDPOINT", "(not set)")
    exporter = os.environ.get("MONOCLE_EXPORTER", "(not set)")
    api_key = os.environ.get("OKAHU_API_KEY", "")

    print(f"[Monocle] OKAHU_INGESTION_ENDPOINT: {endpoint}")
    print(f"[Monocle] MONOCLE_EXPORTER: {exporter}")
    print(f"[Monocle] OKAHU_API_KEY: {mask_key(api_key)}")


def create_input_output_processor(span_name: str, package: str = None, class_name: str = None, method: str = None):
    """
    Create an output processor that captures input args and return values.
    """
    _param_names_cache = {}

    def _get_param_names(instance):
        """Get parameter names for the wrapped function."""
        cache_key = (package, class_name, method)
        if cache_key in _param_names_cache:
            return _param_names_cache[cache_key]

        param_names = []
        try:
            # Try to get from instance method
            if instance is not None and method:
                func = getattr(instance, method, None)
                if func:
                    sig = inspect.signature(func)
                    param_names = list(sig.parameters.keys())
            # Try to import and get from module
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
                    # Skip 'self' for methods
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
            # Use actual param name if available, otherwise fall back to arg_i
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


def load_config(config_path: str) -> dict:
    """Load YAML config file."""
    import yaml
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def build_wrapper_methods(config: dict) -> list:
    """Build WrapperMethod list from config."""
    from monocle_apptrace.instrumentation.common.wrapper_method import WrapperMethod
    from monocle_apptrace.instrumentation.common.wrapper import task_wrapper, atask_wrapper

    wrapper_methods = []
    for item in config.get('instrument', []):
        package = item.get('package')
        class_name = item.get('class')
        method = item.get('method')
        span_name = item.get('span_name', f"{package}.{class_name}.{method}" if class_name else f"{package}.{method}")
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
            union_with_default_methods=False
        )

        return True, workflow_name, None

    except Exception as e:
        return False, None, str(e)


def run_app(script: str, args: list):
    """Run the target application and flush spans."""
    sys.argv = [script] + args
    try:
        runpy.run_path(path_name=script, run_name="__main__")
    except SystemExit:
        pass
    finally:
        # Flush spans to ensure export to Okahu
        try:
            from monocle_apptrace.instrumentation.common.instrumentor import get_monocle_span_processor
            processor = get_monocle_span_processor()
            if processor:
                processor.force_flush(timeout_millis=5000)
                print("[Monocle] Spans flushed to exporters")
        except Exception as e:
            print(f"[Monocle] Flush warning: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Instrument Python app with Monocle using YAML config (fail-open by default)'
    )
    parser.add_argument('--config', '-c', required=True, help='Path to okahu.yaml config file')
    parser.add_argument('script', help='Python script to run')
    parser.add_argument('args', nargs='*', help='Arguments for the script')

    args = parser.parse_args()

    # Environment flags
    strict_mode = os.environ.get('MONOCLE_STRICT', '').lower() == 'true'
    silent_mode = os.environ.get('MONOCLE_SILENT', '').lower() == 'true'

    # Print config
    print_config()

    # Try to setup instrumentation
    success, workflow_name, error = setup_instrumentation(args.config)

    if success:
        print(f"[Monocle] Workflow: {workflow_name}")
        print(f"[Monocle] Config: {args.config}")
        print(f"[Monocle] Instrumentation: ENABLED")
    else:
        if strict_mode:
            print(f"[Monocle] ERROR: Instrumentation failed: {error}")
            print(f"[Monocle] MONOCLE_STRICT=true, exiting.")
            sys.exit(1)
        else:
            if not silent_mode:
                print(f"[Monocle] WARNING: Instrumentation failed: {error}")
                print(f"[Monocle] Continuing without instrumentation (fail-open mode)")
            print(f"[Monocle] Instrumentation: DISABLED")

    print("-" * 60)

    # Always run the app
    run_app(args.script, args.args)


if __name__ == "__main__":
    main()
