from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import indent
from typing import Callable

from impactagent.scanner import FileAnalysis


LlmCallable = Callable[[str], str]


@dataclass
class ImpactPrompt:
    changed_file: Path
    downstream_file: Path
    prompt: str
    llm_response: str | None = None


class AnalysisAgent:
    """Builds structured prompts and optionally invokes an LLM callable."""

    def __init__(self, llm: LlmCallable | None = None) -> None:
        self.llm = llm

    def analyze(
        self,
        changed_file: str | Path,
        code_diff: str,
        downstream_file: str | Path,
        downstream_source: str,
        downstream_analysis: FileAnalysis | None = None,
    ) -> ImpactPrompt:
        prompt = self.build_prompt(
            changed_file=changed_file,
            code_diff=code_diff,
            downstream_file=downstream_file,
            downstream_source=downstream_source,
            downstream_analysis=downstream_analysis,
        )
        response = self.llm(prompt) if self.llm else None
        return ImpactPrompt(
            changed_file=Path(changed_file),
            downstream_file=Path(downstream_file),
            prompt=prompt,
            llm_response=response,
        )

    def build_prompt(
        self,
        changed_file: str | Path,
        code_diff: str,
        downstream_file: str | Path,
        downstream_source: str,
        downstream_analysis: FileAnalysis | None = None,
    ) -> str:
        metadata = ""
        if downstream_analysis:
            metadata = "\n".join(
                [
                    f"- Module: {downstream_analysis.module}",
                    f"- Classes: {', '.join(downstream_analysis.classes) or 'None'}",
                    f"- Functions: {', '.join(downstream_analysis.functions) or 'None'}",
                    f"- Attribute accesses: "
                    f"{', '.join(downstream_analysis.attributes[:50]) or 'None'}",
                ]
            )

        return "\n".join(
            [
                "You are a senior Python reviewer performing dependency impact analysis.",
                "",
                f"The following change was made in [{Path(changed_file).as_posix()}].",
                f"Based on the logic in [{Path(downstream_file).as_posix()}], which depends on "
                f"[{Path(changed_file).as_posix()}], identify specific breaking changes or logic regressions.",
                "",
                "Return a concise structured assessment with these sections:",
                "1. Direct Contract Risks",
                "2. Behavioral Regression Risks",
                "3. Tests To Add Or Update",
                "4. Confidence And Unknowns",
                "",
                "Downstream static-analysis metadata:",
                metadata or "- No metadata available",
                "",
                "Code diff from the changed file:",
                "```diff",
                code_diff.strip() or "<no diff available>",
                "```",
                "",
                "Downstream source code:",
                "```python",
                downstream_source.strip() or "<empty file>",
                "```",
            ]
        )

    def format_prompt_for_console(self, impact_prompt: ImpactPrompt) -> str:
        body = impact_prompt.llm_response or impact_prompt.prompt
        return indent(body, "    ")
