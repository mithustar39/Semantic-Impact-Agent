from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GitCommandResult:
    files: list[Path] = field(default_factory=list)
    warning: str | None = None


class GitClient:
    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()

    def changed_files(self, base: str | None = None) -> GitCommandResult:
        args = ["git", "diff", "--name-only"]
        if base:
            args.append(f"{base}...HEAD")

        try:
            result = self._run(args)
        except RuntimeError as exc:
            return GitCommandResult(warning=str(exc))

        files = [
            (self.repo_root / line.strip()).resolve()
            for line in result.splitlines()
            if line.strip()
        ]
        return GitCommandResult(files=files)

    def diff_for_file(self, file_path: str | Path, base: str | None = None) -> str:
        relative = self._relative(file_path)
        args = ["git", "diff"]
        if base:
            args.append(f"{base}...HEAD")
        args.extend(["--", relative])

        try:
            return self._run(args)
        except RuntimeError as exc:
            return f"<git diff unavailable: {exc}>"

    def _relative(self, file_path: str | Path) -> str:
        path = Path(file_path).resolve()
        try:
            return path.relative_to(self.repo_root).as_posix()
        except ValueError:
            return str(file_path)

    def _run(self, args: list[str]) -> str:
        completed = subprocess.run(
            args,
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(detail or f"{' '.join(args)} failed")
        return completed.stdout
