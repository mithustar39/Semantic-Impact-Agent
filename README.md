# ImpactAgent

ImpactAgent is a Python static analysis tool for finding code-change ripple effects.
It scans Python files, builds a file-level dependency graph, detects changed files
with Git, and prints a risk report with structured LLM prompts for affected files.

## Install

```powershell
pip install -e .
```

## Run

```powershell
impactagent --repo C:\path\to\repo
```

Or run the local wrapper:

```powershell
python impact_agent.py --repo C:\path\to\repo
```

## What It Analyzes

- `FunctionDef` and `AsyncFunctionDef`
- `ClassDef`
- Attribute access expressions such as `client.session.get`
- `import x` and `from x import y` statements

The graph direction is `importer -> imported file`. For example, if `service.py`
imports `models.py`, the edge is `service.py -> models.py`. Calling
`get_affected_path("models.py")` returns all files that transitively depend on
`models.py`.

## Git Behavior

By default, ImpactAgent runs:

```powershell
git diff --name-only
```

Pass `--base origin/main` to compare against a base ref:

```powershell
impactagent --repo . --base origin/main
```

Outside a Git repository, the tool prints a warning and continues with an empty
changed-file set.
