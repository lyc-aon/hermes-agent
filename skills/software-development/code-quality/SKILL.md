---
name: code-quality
description: Syntax checking, linting, and code quality verification procedures
version: 1.0.0
author: Lycaon Solutions
license: MIT
metadata:
  hermes:
    tags: [Development, Linting, Code Quality]
    requires_toolsets: [terminal]
---

# Code Quality — Syntax & Lint Checks

Quick procedures for verifying code correctness before committing or submitting PRs.

## When to Use

- After writing or modifying code, before committing
- When debugging syntax errors or import issues
- Before submitting a PR to catch style/quality issues
- When the user asks to "check", "lint", or "verify" code

## Quick Reference

| Language | Syntax Check | Linter |
|----------|-------------|--------|
| Python | `python3 -c "import ast; ast.parse(open('file.py').read())"` | `ruff check file.py` or `flake8 file.py` |
| JavaScript | `node --check file.js` | `npx eslint file.js` |
| TypeScript | `npx tsc --noEmit file.ts` | `npx eslint file.ts` |
| Rust | `cargo check` | `cargo clippy` |
| Go | `go vet ./...` | `golangci-lint run` |
| Shell | `bash -n script.sh` | `shellcheck script.sh` |

## Procedure

### 1. Syntax check (fast, no deps needed)

#### Python
```bash
# Check single file
python3 -c "import ast; ast.parse(open('file.py').read()); print('OK')"

# Check all Python files in directory
find . -name '*.py' -not -path '*/venv/*' -not -path '*/__pycache__/*' | while read f; do
  python3 -c "import ast; ast.parse(open('$f').read())" 2>/dev/null || echo "SYNTAX ERROR: $f"
done
```

#### JavaScript/TypeScript
```bash
node --check file.js
npx tsc --noEmit --pretty  # TypeScript
```

### 2. Lint check (catches more issues)

Try tools in order of preference (use whichever is installed):

#### Python
```bash
# Ruff (fastest, modern)
ruff check file.py --select E,W,F,I

# Flake8 (widely available)
flake8 file.py --max-line-length 120

# Pylint (thorough but slow)
pylint file.py --disable=C,R  # skip convention/refactor warnings
```

#### JavaScript/TypeScript
```bash
npx eslint file.js --no-eslintrc --rule '{"no-unused-vars": "warn", "no-undef": "error"}'
```

### 3. Import check (Python-specific)

Verify all imports resolve without actually running the code:

```bash
python3 -c "
import importlib, sys
with open('file.py') as f:
    tree = __import__('ast').parse(f.read())
for node in __import__('ast').walk(tree):
    if isinstance(node, __import__('ast').Import):
        for alias in node.names:
            try:
                importlib.import_module(alias.name)
            except ImportError:
                print(f'Missing: {alias.name}')
    elif isinstance(node, __import__('ast').ImportFrom) and node.module:
        try:
            importlib.import_module(node.module)
        except ImportError:
            print(f'Missing: {node.module}')
"
```

### 4. Type checking (if configured)

```bash
# Python
mypy file.py --ignore-missing-imports

# TypeScript (already covered by tsc --noEmit)
```

## Decision Tree

1. **Just wrote code?** → Syntax check first (instant feedback)
2. **About to commit?** → Lint check on changed files
3. **CI failing?** → Run the same linter CI uses (check project config)
4. **Import errors?** → Import check to find missing deps

## Pitfalls

- **Virtual environments**: Ensure linters run in the project's venv, not system Python
- **Config files**: Projects may have `.flake8`, `ruff.toml`, `.eslintrc` — respect them
- **Pre-commit hooks**: Check `.pre-commit-config.yaml` — running `pre-commit run --all-files` may be the most authoritative check

## Verification

- Syntax check exits 0 with no output → clean
- Linter exits 0 or outputs only warnings (not errors) → acceptable
- All imports resolve → no missing dependencies
