from __future__ import annotations

from pathlib import Path

import networkx as nx

from impactagent.scanner import FileAnalysis, resolve_imports


class DependencyGraph:
    """File-level dependency graph backed by networkx.

    Edge direction is importer -> imported file. With this direction, networkx
    ancestors(changed_file) gives every transitive dependent affected by a
    change in changed_file.
    """

    def __init__(self) -> None:
        self.graph = nx.DiGraph()

    def build(self, analyses: dict[Path, FileAnalysis]) -> "DependencyGraph":
        module_to_path = {analysis.module: path for path, analysis in analyses.items()}

        for path, analysis in analyses.items():
            self.graph.add_node(path, analysis=analysis, module=analysis.module)

        for path, analysis in analyses.items():
            for dependency in resolve_imports(analysis, module_to_path):
                self.graph.add_edge(path, dependency)

        return self

    def get_affected_path(self, changed_file: str | Path) -> list[Path]:
        changed_path = Path(changed_file).resolve()
        if changed_path not in self.graph:
            return []
        affected = nx.ancestors(self.graph, changed_path)
        return sorted(affected, key=lambda path: str(path))

    def direct_dependents(self, changed_file: str | Path) -> list[Path]:
        changed_path = Path(changed_file).resolve()
        if changed_path not in self.graph:
            return []
        return sorted(self.graph.predecessors(changed_path), key=lambda path: str(path))

    def dependencies_for(self, file_path: str | Path) -> list[Path]:
        path = Path(file_path).resolve()
        if path not in self.graph:
            return []
        return sorted(self.graph.successors(path), key=lambda item: str(item))

    def analysis_for(self, file_path: str | Path) -> FileAnalysis | None:
        path = Path(file_path).resolve()
        if path not in self.graph:
            return None
        return self.graph.nodes[path].get("analysis")
