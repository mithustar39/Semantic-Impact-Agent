from __future__ import annotations

import argparse
from pathlib import Path

from impactagent.agent import AnalysisAgent
from impactagent.git import GitClient
from impactagent.graph import DependencyGraph
from impactagent.scanner import FileAnalysis, StaticAnalysisEngine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="impactagent",
        description="Find Python dependency ripple effects and print a risk report.",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository root to scan. Defaults to the current directory.",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="Optional Git base ref, for example origin/main.",
    )
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Manually include a changed file. May be passed multiple times.",
    )
    parser.add_argument(
        "--no-prompts",
        action="store_true",
        help="Show affected files without printing generated LLM prompts.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo).resolve()
    scanner = StaticAnalysisEngine(repo_root)
    analyses = scanner.scan()
    graph = DependencyGraph().build(analyses)

    git = GitClient(repo_root)
    git_result = git.changed_files(base=args.base)
    changed_files = [path for path in git_result.files if path.suffix == ".py"]
    changed_files.extend(_manual_changed_files(repo_root, args.changed_file))
    changed_files = _dedupe_paths(changed_files)

    print("Risk Report")
    print("=" * 72)
    print(f"Repository: {repo_root}")
    print(f"Python files scanned: {len(analyses)}")
    print(f"Graph edges: {graph.graph.number_of_edges()}")

    if git_result.warning:
        print(f"Git warning: {git_result.warning}")

    if not changed_files:
        print("\nNo changed Python files detected.")
        return 0

    agent = AnalysisAgent()

    for changed_file in changed_files:
        print_changed_file_report(
            changed_file=changed_file,
            graph=graph,
            analyses=analyses,
            git=git,
            agent=agent,
            base=args.base,
            include_prompts=not args.no_prompts,
        )

    return 0


def print_changed_file_report(
    changed_file: Path,
    graph: DependencyGraph,
    analyses: dict[Path, FileAnalysis],
    git: GitClient,
    agent: AnalysisAgent,
    base: str | None,
    include_prompts: bool,
) -> None:
    print("\nChanged File")
    print("-" * 72)
    print(_display(changed_file))

    analysis = analyses.get(changed_file)
    if analysis is None:
        print("Status: changed file was not found in the scanned Python graph.")
        return

    affected = graph.get_affected_path(changed_file)
    direct = graph.direct_dependents(changed_file)

    print(f"Module: {analysis.module}")
    print(f"Direct dependents: {len(direct)}")
    print(f"Transitively affected files: {len(affected)}")

    if not affected:
        print("Risk: no file-level Python import dependents detected.")
        return

    print("\nAffected downstream files:")
    for path in affected:
        marker = "direct" if path in direct else "transitive"
        print(f"- {_display(path)} ({marker})")

    if not include_prompts:
        return

    diff = git.diff_for_file(changed_file, base=base)
    print("\nLLM impact prompts:")
    for downstream in affected:
        downstream_source = _read_text(downstream)
        prompt = agent.analyze(
            changed_file=changed_file,
            code_diff=diff,
            downstream_file=downstream,
            downstream_source=downstream_source,
            downstream_analysis=analyses.get(downstream),
        )
        print(f"\n--- Prompt for {_display(downstream)} ---")
        print(agent.format_prompt_for_console(prompt))


def _manual_changed_files(repo_root: Path, paths: list[str]) -> list[Path]:
    result: list[Path] = []
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = repo_root / path
        if path.suffix == ".py":
            result.append(path.resolve())
    return result


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"<unable to read file: {exc}>"


def _display(path: Path) -> str:
    return str(path)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            result.append(resolved)
            seen.add(resolved)
    return result
