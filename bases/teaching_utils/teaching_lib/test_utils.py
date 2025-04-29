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
