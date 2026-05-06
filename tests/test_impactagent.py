from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from impactagent.agent import AnalysisAgent
from impactagent.git import GitClient
from impactagent.graph import DependencyGraph
from impactagent.scanner import StaticAnalysisEngine


class ImpactAgentTests(unittest.TestCase):
    def test_scanner_extracts_symbols_attributes_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "service.py"
            target.write_text(
                "\n".join(
                    [
                        "import os",
                        "from pkg.models import User",
                        "",
                        "class Service:",
                        "    def run(self):",
                        "        return self.client.session.get(User.name)",
                    ]
                ),
                encoding="utf-8",
            )

            analysis = StaticAnalysisEngine(root).analyze_file(target)

            self.assertIn("Service", analysis.classes)
            self.assertIn("run", analysis.functions)
            self.assertIn("self.client.session.get", analysis.attributes)
            self.assertEqual(
                ["os", "pkg.models.User"],
                [item.display for item in analysis.imports],
            )

    def test_graph_returns_dependents_as_affected_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models.py").write_text("class User: pass\n", encoding="utf-8")
            (root / "service.py").write_text("from models import User\n", encoding="utf-8")
            (root / "api.py").write_text("import service\n", encoding="utf-8")

            analyses = StaticAnalysisEngine(root).scan()
            graph = DependencyGraph().build(analyses)

            affected = graph.get_affected_path(root / "models.py")

            self.assertEqual(
                [root / "api.py", root / "service.py"],
                affected,
            )

    def test_relative_package_imports_resolve_from_init_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("from . import models\n", encoding="utf-8")
            (pkg / "models.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "consumer.py").write_text("import pkg\n", encoding="utf-8")

            analyses = StaticAnalysisEngine(root).scan()
            graph = DependencyGraph().build(analyses)

            self.assertEqual(
                [pkg / "__init__.py"],
                graph.direct_dependents(pkg / "models.py"),
            )

    def test_git_client_reports_warning_outside_git_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = GitClient(tmp).changed_files()

            self.assertEqual([], result.files)
            self.assertIsNotNone(result.warning)

    def test_analysis_agent_builds_required_prompt(self) -> None:
        prompt = AnalysisAgent().build_prompt(
            changed_file="models.py",
            code_diff="- old\n+ new",
            downstream_file="service.py",
            downstream_source="from models import User\n",
        )

        self.assertIn("The following change was made in [models.py]", prompt)
        self.assertIn("which depends on [models.py]", prompt)
        self.assertIn("Direct Contract Risks", prompt)
        self.assertIn("```diff", prompt)
        self.assertIn("```python", prompt)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
