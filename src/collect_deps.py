#!/usr/bin/env python3
import ast
import importlib.util
import os
import sys
from pathlib import Path

# Add the project root to sys.path so we can find local modules
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def get_imports_from_file(filepath):
    """Return a set of module names imported in the given Python file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=filepath)
    except Exception as e:
        print(f"Warning: Could not parse {filepath}: {e}", file=sys.stderr)
        return set()

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])  # top-level package
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:  # absolute import
                if node.module:
                    imports.add(node.module.split(".")[0])
            # relative imports (node.level > 0) are ignored for simplicity
    return imports


def module_to_path(module_name):
    """Convert a module name to a file path if it's a local .py file."""
    # Skip built-in and standard library modules
    if (
        module_name in sys.builtin_module_names
        or module_name in sys.stdlib_module_names
    ):
        return None
    # Try to find the spec
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        return None
    # Only consider .py files (not built-in or extension modules)
    if spec.origin.endswith(".py") and os.path.exists(spec.origin):
        return os.path.relpath(spec.origin, PROJECT_ROOT)
    return None


def collect_dependencies(start_file):
    """Recursively collect all local .py file dependencies of start_file."""
    start_path = PROJECT_ROOT / start_file
    if not start_path.exists():
        print(f"Error: Start file {start_path} does not exist.", file=sys.stderr)
        return set()

    visited = set()
    to_visit = [str(start_path)]

    while to_visit:
        current = to_visit.pop()
        if current in visited:
            continue
        visited.add(current)

        # Get imports in this file
        imports = get_imports_from_file(current)
        for imp in imports:
            # Try to resolve the import to a file path
            path = module_to_path(imp)
            if path:
                abs_path = PROJECT_ROOT / path
                if abs_path.exists() and str(abs_path) not in visited:
                    to_visit.append(str(abs_path))
            # Also consider that the import might be a submodule (e.g., 'modules.notifier')
            # We'll try to find the file by replacing dots with slashes and adding .py
            # This is a fallback for when find_spec doesn't work (e.g., for packages)
            # But we already tried find_spec, so we can skip.
    return visited


if __name__ == "__main__":
    start_file = "bot.py"
    deps = collect_dependencies(start_file)
    # Sort for deterministic output
    for f in sorted(deps):
        print(f)
