from dataclasses import dataclass, field
from typing import Optional, Any, TextIO

from .submissions import Submission


@dataclass
class TestResultNode:
    label: str
    passed: Optional[bool] = None
    weight: float = 1.0
    message: Optional[str] = None
    children: list['TestResultNode'] = field(default_factory=list)
    score: float = 0.0
    num_tests: int = 0

    def calculate_score(self) -> float:
        if self.children:
            self.score = sum(child.calculate_score() * child.weight for child in self.children)
            return self.score
        else:
            self.score = 1.0 if self.passed else 0.0
            return self.score

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "passed": self.passed,
            "weight": self.weight,
            "message": self.message,
            "score": round(self.score, 2),
            "children": [child.to_dict() for child in self.children] if self.children else []
        }

    def clone(self):
        return TestResultNode(
            label=self.label,
            passed=self.passed,
            weight=self.weight,
            message=self.message,
            children=[child.clone() for child in self.children],
            score=self.score
        )

    def generate_mermaid_diagram(self, max_depth: int = 2) -> str:
        lines = ["```mermaid", "graph TD"]
        node_ids = {}

        def escape(label: str) -> str:
            return label.replace('"', '\\"').replace("\n", " ")

        def get_node_id(node: TestResultNode, count: int) -> str:
            return f"node{count}"

        def traverse(node: TestResultNode, depth: int, parent_id: Optional[str], count: list[int]):
            if depth > max_depth:
                return

            node_id = get_node_id(node, count[0])
            node_ids[id(node)] = node_id

            status = "✅" if node.passed else ("❌" if node.passed is False else "⏳")
            label = escape(node.label)
            node_text = f"{label}<br/>{status} | Score: {node.score:.2f} | Weight: {node.weight:.2f}"

            lines.append(f'{node_id}["{node_text}"]')

            if parent_id:
                lines.append(f"{parent_id} --> {node_id}")

            count[0] += 1

            for child in node.children:
                traverse(child, depth + 1, node_id, count)

        traverse(self, 1, None, [0])
        lines.append("```")
        return "\n".join(lines)


@dataclass
class ExecutionReport:
    success: bool
    stdout: str
    stderr: str
    return_code: Optional[int]
    timeout: bool
    results_path: Optional[str]
    test_tree: Optional[TestResultNode] = None
    final_score: Optional[float] = None
    total_tests: Optional[int] = None
    analysis: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    submission: Optional[Submission] = None

    def clone(self):
        return ExecutionReport(
            success=self.success,
            stdout=self.stdout,
            stderr=self.stderr,
            return_code=self.return_code,
            timeout=self.timeout,
            results_path=self.results_path,
            test_tree=self.test_tree.clone() if self.test_tree else None,
            final_score=self.final_score,
            total_tests=self.total_tests,
            analysis=self.analysis,
            metadata=self.metadata.copy(),
        )
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "timeout": self.timeout,
            "results_path": self.results_path,
            "test_tree": self.test_tree.to_dict() if self.test_tree else None,
            "final_score": round(self.final_score, 2) if self.final_score is not None else None,
            "total_tests": self.total_tests,
            "analysis": self.analysis,
            "metadata": self.metadata
        }

    def to_markdown(self):
        md_report = ""
        md_report += f'\n# Estudiant\n'
        md_report += f'- Nom: {self.submission._student_fullname}\n'
        md_report += f'- Grups: {self.submission._student_groups}\n'

        md_report += f'\n# Execució del codi\n'
        md_report += f'- Success: {self.success}\n'
        md_report += f'- Timeout: {self.timeout}\n'
        md_report += f'- Stdout: {self.stdout}\n'
        md_report += f'- Stderr: {self.stderr}\n'
        md_report += f'- Return Code: {self.return_code}\n'

        md_report += f'\n## Proves\n'
        md_report += f'- Total Tests: {self.total_tests}\n'
        md_report += f'- Final Score: {self.final_score}\n'
        if self.test_tree is not None:
            md_report += self.test_tree.generate_mermaid_diagram(3)

        if 'coverage' in self.metadata:
            md_report += f'\n## Cobertura\n'
            md_report += '| Mòdul | Percentage | Covered | Missed | Total | Error |\n'
            md_report += '|--------|------------|---------|--------|--------|--------|\n'
            for module, report in self.metadata['coverage'].items():
                percent = report.get("coverage_percent")
                if percent is not None:
                    percent_str = f'{percent:.2f}%'
                else:
                    percent_str = 'N/A'
                md_report += f'| {module} | {percent_str} | {report.get("coverage_covered")} | {report.get("coverage_missed")} | {report.get("coverage_total")} | {report.get("coverage_error")} |\n'

        if 'checkstyle' in self.metadata:
            md_report += f'\n## Estil de codi\n'
            md_report += '| Mòdul | Violations | Error |\n'
            md_report += '|--------|------------|--------|\n'
            for module, report in self.metadata['checkstyle'].items():
                md_report += f'| {module} | {report.get("checkstyle_violations")} | {report.get("checkstyle_error")} |\n'

        if self.analysis is not None:
            md_report += f'\n# Anàlisis\n'


        return md_report
        
        
        
