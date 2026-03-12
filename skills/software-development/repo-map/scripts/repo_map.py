#!/usr/bin/env python3
"""Generate a structural map of a Python codebase using stdlib ast module.

Usage: python3 repo_map.py /path/to/project [--max-files 200]

Outputs classes, functions, and methods with file paths and signatures.
No external dependencies — uses only Python standard library.
"""

import ast
import os
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".cache",
    "node_modules", "__pycache__", ".venv", "venv", "build",
    "dist", ".next", ".tox", ".mypy_cache", ".pytest_cache",
    "egg-info",
}


def format_args(args: ast.arguments) -> str:
    parts = []
    for arg in args.posonlyargs:
        parts.append(arg.arg)
    if args.posonlyargs:
        parts.append("/")
    for arg in args.args:
        parts.append(arg.arg)
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")
    for arg in args.kwonlyargs:
        parts.append(arg.arg)
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    return ", ".join(parts)


def format_bases(node: ast.ClassDef) -> str:
    bases = []
    for base in node.bases:
        try:
            bases.append(ast.unparse(base))
        except Exception:
            continue
    return f"({', '.join(bases)})" if bases else ""


def collect_symbols(filepath: Path) -> list[str]:
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    symbols = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            symbols.append(f"  class {node.name}{format_bases(node)}")
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async " if isinstance(child, ast.AsyncFunctionDef) else ""
                    symbols.append(f"    {prefix}def {child.name}({format_args(child.args)})")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            symbols.append(f"  {prefix}def {node.name}({format_args(node.args)})")
    return symbols


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path> [--max-files N]", file=sys.stderr)
        sys.exit(1)

    base = Path(sys.argv[1]).resolve()
    max_files = 200
    if "--max-files" in sys.argv:
        idx = sys.argv.index("--max-files")
        if idx + 1 < len(sys.argv):
            max_files = int(sys.argv[idx + 1])

    if base.is_file():
        files = [base] if base.suffix == ".py" else []
    else:
        files = []
        for root, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in sorted(names):
                if name.endswith(".py"):
                    files.append(Path(root) / name)
                    if len(files) >= max_files:
                        break
            if len(files) >= max_files:
                break
        files.sort()

    total_symbols = 0
    for filepath in files:
        symbols = collect_symbols(filepath)
        if symbols:
            rel = filepath.relative_to(base) if base.is_dir() else filepath.name
            print(str(rel))
            for sym in symbols:
                print(sym)
                total_symbols += 1
            print()

    print(f"# {len(files)} files, {total_symbols} symbols", file=sys.stderr)


if __name__ == "__main__":
    main()
