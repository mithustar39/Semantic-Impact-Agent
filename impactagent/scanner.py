from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


IGNORED_DIR_NAMES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}


@dataclass(frozen=True)
class ImportReference:
    """An import statement normalized enough for file-level resolution."""

    module: str
    name: str | None = None
    level: int = 0
    lineno: int = 0

    @property
    def display(self) -> str:
        if self.name:
            return f"{'.' * self.level}{self.module}.{self.name}"
        return f"{'.' * self.level}{self.module}"


@dataclass
class FileAnalysis:
    path: Path
    module: str
    is_package_init: bool = False
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    imports: list[ImportReference] = field(default_factory=list)
    parse_error: str | None = None


class PythonAstVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.functions: list[str] = []
        self.classes: list[str] = []
        self.attributes: list[str] = []
        self.imports: list[ImportReference] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.attributes.append(_attribute_name(node))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ImportReference(module=alias.name, lineno=node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            self.imports.append(
                ImportReference(
                    module=module,
                    name=alias.name,
                    level=node.level,
                    lineno=node.lineno,
                )
            )
        self.generic_visit(node)


def _attribute_name(node: ast.Attribute) -> str:
    parts: list[str] = []
    current: ast.AST = node

    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value

    if isinstance(current, ast.Name):
        parts.append(current.id)
    elif isinstance(current, ast.Call):
        parts.append("<call>")
    else:
        parts.append(type(current).__name__)

    return ".".join(reversed(parts))


class StaticAnalysisEngine:
    def __init__(
        self,
        root: str | Path,
        ignored_dirs: Iterable[str] | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.ignored_dirs = set(ignored_dirs or IGNORED_DIR_NAMES)

    def scan(self) -> dict[Path, FileAnalysis]:
        analyses: dict[Path, FileAnalysis] = {}

        for file_path in self.iter_python_files():
            analyses[file_path] = self.analyze_file(file_path)

        return analyses

    def iter_python_files(self) -> Iterable[Path]:
        if self.root.is_file() and self.root.suffix == ".py":
            yield self.root.resolve()
            return

        for path in self.root.rglob("*.py"):
            if self._is_ignored(path):
                continue
            yield path.resolve()

    def analyze_file(self, file_path: str | Path) -> FileAnalysis:
        path = Path(file_path).resolve()
        analysis = FileAnalysis(
            path=path,
            module=module_name_for_path(path, self.root),
            is_package_init=path.name == "__init__.py",
        )

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            analysis.parse_error = str(exc)
            return analysis

        visitor = PythonAstVisitor()
        visitor.visit(tree)

        analysis.functions = sorted(set(visitor.functions))
        analysis.classes = sorted(set(visitor.classes))
        analysis.attributes = sorted(set(visitor.attributes))
        analysis.imports = visitor.imports
        return analysis

    def _is_ignored(self, path: Path) -> bool:
        try:
            relative = path.resolve().relative_to(self.root)
        except ValueError:
            return True
        return any(part in self.ignored_dirs for part in relative.parts)


def module_name_for_path(path: Path, root: Path) -> str:
    relative = path.resolve().relative_to(root.resolve()).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def resolve_imports(
    analysis: FileAnalysis,
    module_to_path: dict[str, Path],
) -> set[Path]:
    dependencies: set[Path] = set()

    for import_ref in analysis.imports:
        candidates = _candidate_modules(
            analysis.module,
            import_ref,
            is_package_init=analysis.is_package_init,
        )
        for candidate in candidates:
            if candidate in module_to_path:
                dependency = module_to_path[candidate]
                if dependency != analysis.path:
                    dependencies.add(dependency)
                break

    return dependencies


def _candidate_modules(
    current_module: str,
    import_ref: ImportReference,
    is_package_init: bool = False,
) -> list[str]:
    if import_ref.level:
        base = _relative_base(current_module, import_ref.level, is_package_init)
        module = ".".join(part for part in [base, import_ref.module] if part)
    else:
        module = import_ref.module

    candidates: list[str] = []

    if import_ref.name and import_ref.name != "*":
        candidates.append(".".join(part for part in [module, import_ref.name] if part))

    if module:
        candidates.append(module)
        parts = module.split(".")
        while len(parts) > 1:
            parts.pop()
            candidates.append(".".join(parts))

    return _dedupe(candidates)


def _relative_base(current_module: str, level: int, is_package_init: bool = False) -> str:
    parts = current_module.split(".") if current_module else []
    if parts and not is_package_init:
        parts = parts[:-1]
    levels_up = max(level - 1, 0)
    if levels_up:
        parts = parts[:-levels_up] if levels_up <= len(parts) else []
    return ".".join(parts)


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
