"""AST search tool — structural code search using ast-grep.

Finds syntax patterns across codebases using AST matching rather than
text-based regex. Supports Python, JavaScript, TypeScript, C/C++, and Rust.
Requires the ast-grep binary on PATH (install: npm i -g @ast-grep/cli or
cargo install ast-grep).
"""

import json
import logging
import shutil
import subprocess

from tools.registry import registry

logger = logging.getLogger(__name__)


# Language aliases and ast-grep language names
_LANG_ALIASES = {
    "py": "python", "python": "python",
    "js": "javascript", "jsx": "javascript", "javascript": "javascript",
    "ts": "typescript", "tsx": "typescript", "typescript": "typescript",
    "c": "cpp", "cc": "cpp", "cpp": "cpp", "cxx": "cpp", "h": "cpp", "hpp": "cpp",
    "rs": "rust", "rust": "rust",
    "go": "go", "java": "java", "rb": "ruby", "ruby": "ruby",
    "swift": "swift", "kotlin": "kotlin", "kt": "kotlin",
}


def _find_ast_grep_binary():
    """Return an ast-grep executable path, if available."""
    for candidate in ("ast-grep", "sg"):
        path = shutil.which(candidate)
        if not path:
            continue
        try:
            check = subprocess.run(
                [path, "--version"],
                capture_output=True, text=True, timeout=2,
            )
        except Exception:
            continue
        text = ((check.stdout or "") + (check.stderr or "")).lower()
        if "ast-grep" in text:
            return path
    return None


def _check_ast_grep() -> bool:
    """Return True if ast-grep is available on PATH."""
    return _find_ast_grep_binary() is not None


def _ast_search(args, **kw):
    pattern = str(args.get("pattern", "")).strip()
    lang = args.get("lang", "").strip().lower()
    path = str(args.get("path", "."))

    if not pattern:
        return json.dumps({"error": "pattern is required"})
    if not lang:
        return json.dumps({"error": "lang is required"})

    ast_lang = _LANG_ALIASES.get(lang, lang)

    binary = _find_ast_grep_binary()
    if not binary:
        return json.dumps({"error": "ast-grep is not installed. Install with: npm i -g @ast-grep/cli"})

    cmd = [
        binary, "run",
        "--pattern", pattern,
        "--lang", ast_lang,
        path,
        "--json=stream",
        "--color=never",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "ast-grep timed out after 30s"})
    except Exception as e:
        return json.dumps({"error": f"ast-grep failed: {e}"})

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0 and not stdout:
        return json.dumps({"error": stderr or f"ast-grep exited with code {result.returncode}"})
    if not stdout:
        return f"No matches for pattern '{pattern}' in {ast_lang} files under {path}"

    matches = []
    for raw in stdout.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            matches.append(json.loads(raw))
        except json.JSONDecodeError:
            continue

    output = []
    for m in matches[:100]:
        file_path = m.get("file", "?")
        line_no = m.get("range", {}).get("start", {}).get("line", "?")
        text = m.get("lines") or m.get("text") or ""
        snippet = (text.strip().splitlines()[0] if text.strip() else "")[:180]
        output.append(f"{file_path}:{line_no}: {snippet}")

    if len(matches) > 100:
        output.append(f"... ({len(matches)} total matches, showing first 100)")
    return "\n".join(output)


AST_SEARCH_SCHEMA = {
    "name": "ast_search",
    "description": (
        "Structural code search using ast-grep. Finds syntax patterns with "
        "$VAR (single node) and $$$VAR (multiple nodes) wildcards. "
        "Examples: 'def $NAME($$$ARGS): $$$BODY' finds Python functions, "
        "'console.log($$$ARGS)' finds console.log calls in JS/TS. "
        "Requires ast-grep on PATH."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "ast-grep pattern (e.g. 'def $NAME($$$ARGS): $$$BODY')",
            },
            "path": {
                "type": "string",
                "description": "File or directory to search (default: current directory)",
            },
            "lang": {
                "type": "string",
                "description": "Language: python, javascript, typescript, cpp, rust, go, java, ruby, swift, kotlin",
            },
        },
        "required": ["pattern", "lang"],
    },
}

registry.register(
    name="ast_search",
    toolset="file",
    schema=AST_SEARCH_SCHEMA,
    handler=lambda args, **kw: _ast_search(args, **kw),
    check_fn=_check_ast_grep,
)
