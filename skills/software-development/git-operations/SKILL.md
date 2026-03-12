---
name: git-operations
description: Safe git workflow procedures for branching, committing, rebasing, and PR management
version: 1.0.0
author: Lycaon Solutions
license: MIT
metadata:
  hermes:
    tags: [Development, Git, Version Control]
    requires_toolsets: [terminal]
---

# Git Operations — Safe Workflow Procedures

Standard git workflows with safety guardrails. Prevents common mistakes like force-pushing to main, committing secrets, or losing work.

## When to Use

- Creating branches, commits, or PRs
- Rebasing, merging, or resolving conflicts
- Any git operation that modifies history or pushes to remote

## Safety Rules (Always Follow)

1. **Never force-push to main/master** — always create a branch
2. **Never commit secrets** — check for API keys, tokens, passwords before staging
3. **Prefer new commits over amend** — amending rewrites history and can lose work
4. **Always check `git status` before destructive operations**
5. **Use `git stash` before switching branches with uncommitted work**

## Common Workflows

### Create a feature branch and commit

```bash
# 1. Ensure clean state
git status

# 2. Create and switch to feature branch
git checkout -b feat/description

# 3. Make changes, then stage specific files (not git add .)
git add src/changed_file.py tests/test_changed.py

# 4. Check for secrets before committing
git diff --cached | grep -iE '(api.key|secret|password|token|sk-|OPENAI)' && echo "WARNING: possible secrets!"

# 5. Commit with conventional message
git commit -m "feat(scope): description of change"

# 6. Push with upstream tracking
git push -u origin feat/description
```

### Rebase onto updated main

```bash
# 1. Stash any uncommitted work
git stash

# 2. Update main
git checkout main
git pull origin main

# 3. Rebase feature branch
git checkout feat/description
git rebase main

# 4. If conflicts, resolve each file then:
git add <resolved-file>
git rebase --continue

# 5. Pop stash if needed
git stash pop
```

### Create a PR (requires gh CLI)

```bash
gh pr create --title "feat(scope): short title" --body "## Summary
- What changed and why

## Test Plan
- [ ] How to verify"
```

### Undo last commit (keep changes)

```bash
# Soft reset — changes stay staged
git reset --soft HEAD~1

# Mixed reset — changes stay unstaged
git reset HEAD~1
```

### Interactive rebase (squash commits)

```bash
# Squash last N commits
git rebase -i HEAD~N
# In editor: change 'pick' to 'squash' for commits to combine
```

## Secret Detection Patterns

Before any commit, scan for:

```bash
git diff --cached | grep -inE '(sk-[a-zA-Z0-9]{20,}|AKIA[A-Z0-9]{16}|ghp_[a-zA-Z0-9]{36}|password\s*=\s*["\x27][^"\x27]+|api.key|secret|token\s*=)' || echo "Clean"
```

## Pitfalls

- **Detached HEAD**: If you see "HEAD detached", run `git checkout main` or create a branch with `git checkout -b branch-name`
- **Merge conflicts during rebase**: Resolve one commit at a time, `git add`, then `git rebase --continue`
- **Accidentally committed to main**: Create a branch from current state, then reset main: `git branch fix-branch && git reset --hard origin/main`
- **Large files**: Use `.gitignore` for build artifacts, models, datasets. Check with `git diff --cached --stat` before committing

## Verification

- `git log --oneline -5` — verify commit history looks correct
- `git status` — should be clean after operations
- `git diff origin/main...HEAD` — verify what will be in the PR
