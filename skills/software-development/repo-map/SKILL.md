---
name: repo-map
description: Generate a structural overview of a codebase showing classes, functions, and key symbols
version: 1.0.0
author: Lycaon Solutions
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Development, Code Analysis, Navigation]
    requires_toolsets: [terminal]
---

# Repo Map — Codebase Structure Overview

Generate a bird's-eye view of a project's code structure: classes, functions, interfaces, and key exports.

## When to Use

- Starting work on an unfamiliar codebase
- Need to understand project architecture before making changes
- Looking for where specific functionality is implemented
- Planning a refactor or major feature addition

## Quick Reference

| Language | Command |
|----------|---------|
| Python | `python3 scripts/repo_map.py <path>` |
| JS/TS | `ast-grep run --pattern 'function $NAME($$$ARGS) { $$$BODY }' --lang javascript <path> --json=stream` |
| Multiple | Run the script with auto-detection |

## Procedure

### Option A: Python projects (stdlib, no deps)

Run the helper script to extract all classes and functions:

```bash
python3 "$(hermes skills path repo-map)/scripts/repo_map.py" /path/to/project
```

This uses Python's `ast` module to parse source files and extract:
- Top-level functions with signatures
- Classes with their methods and base classes
- Nested class methods with proper indentation

### Option B: Multi-language projects (requires ast-grep)

If `ast-grep` is available, use it for JS/TS/Rust/Go/C++:

```bash
# Find all function definitions
ast-grep run --pattern 'function $NAME($$$ARGS) { $$$BODY }' --lang javascript /path --json=stream

# Find all class definitions
ast-grep run --pattern 'class $NAME { $$$BODY }' --lang typescript /path --json=stream

# Find Rust structs and impls
ast-grep run --pattern 'struct $NAME { $$$FIELDS }' --lang rust /path --json=stream
```

### Option C: Quick approximation (no tools needed)

For a rough overview when no tools are available:

```bash
# Find Python classes and functions
grep -rn "^class \|^def \|^async def " --include="*.py" /path/to/project | head -100

# Find JS/TS exports
grep -rn "^export " --include="*.ts" --include="*.js" /path/to/project | head -100
```

## Output Format

The script outputs one symbol per line with file path and line number:

```
src/auth.py
  class AuthManager(BaseManager)
    def authenticate(self, token)
    def refresh(self, session_id)
    async def validate(self, credentials)
  def create_token(user_id, expiry)

src/models.py
  class User
    def __init__(self, email, role)
    def to_dict(self)
```

## Pitfalls

- **Large monorepos**: Limit scope to specific directories. The script skips `node_modules`, `.git`, `__pycache__`, `venv`, `build`, `dist`.
- **Generated code**: Proto-generated, vendor, or bundled files may pollute results. Filter by directory.
- **Binary/non-UTF8 files**: Gracefully skipped.

## Verification

- Output should list files with their symbols
- Each symbol should have a line number for navigation
- No crash on binary files or encoding errors
