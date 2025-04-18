import logging
import os
import shutil
import subprocess
import uuid
import json

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional, Any

from debugpy.common.log import reraise_exception
from docutils.parsers.rst.directives.misc import Class

from teaching_utils import ghrepos, config, testing
from .submissions import Submission, SubmissionSet

logger = logging.getLogger(__name__)

@dataclass
class TestResultNode:
    label: str
    passed: Optional[bool] = None
    weight: float = 1.0
    message: Optional[str] = None
    children: list['TestResultNode'] = field(default_factory=list)
    score: float = 0.0

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

@dataclass
class ExecutionReport:
    success: bool
    stdout: str
    stderr: str
    return_code: Optional[int]
    timeout: bool
    results_path: str
    test_tree: Optional[TestResultNode] = None
    final_score: Optional[float] = None
    total_tests: Optional[int] = None
    analysis: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    submission: Optional[Submission] = None

class RunSubmissionTest:
    def __init__(self, submission_path: str, config: dict):
        """
        Test runner using Docker and hierarchical test results.

        Args:
            submission_path (str): Path to student's submission.
            config (dict): Includes:
                - image (str): Docker image name
                - max_time (int): Timeout in seconds
                - run_cmd (str): Command inside container
                - result_path (str): Folder where results.json is generated (inside container)
                - grading_file (str): JSON file containing test results
        """
        self.submission_path = submission_path
        self.image = config.get("image")
        self.max_time = config.get("max_time", 10)
        self.run_cmd = config.get("run_cmd")
        self.additional_mounts = config.get("additional_mounts", [])

        self.result_path = config.get("result_path")
        self.grading_file = config.get("grading_file", "results.json")

        self.execution_id = config.get("execution_id", uuid.uuid4().hex)
        self.host_tmp_basepath = config.get("host_tmp_basepath", "/tmp")
        self.host_tmp_prefix = config.get("host_tmp_prefix", "submission_")
        self.host_tmp = config.get("host_tmp", os.path.join(self.host_tmp_basepath, f"{self.host_tmp_prefix}{self.execution_id}", ''))
        self.container_mount = config.get("container_mount", "/mnt/code")

        self.file_code_extensions = config.get("file_code_extensions", ['.py', '.java', '.c', '.h', '.cpp', '.hpp', '.hcc'])
        self.line_comment_symbol = config.get("line_comment_symbol", "#")

        self.perform_analysis = config.get("perform_analysis", True)
        self.analysis_custom_prompt = config.get("analysis_custom_prompt")
        self.code_extraction_max_char = config.get("code_extraction_max_char", 12000)
        self.analysis_model = config.get("analysis_model", "codellama")

        self.total_tests = 0

    def _prepare_environment(self):
        os.makedirs(self.host_tmp, exist_ok=True)
        shutil.copytree(self.submission_path, os.path.join(self.host_tmp, "code"), dirs_exist_ok=True)

    def _load_result_tree(self, result_file_path: str) -> Optional[TestResultNode]:
        if not os.path.exists(result_file_path):
            return None
        try:
            with open(result_file_path, "r") as f:
                raw = json.load(f)
            return self._parse_node(raw)
        except Exception as e:
            return TestResultNode(label="Error parsing results", weight=1.0, passed=False, message=str(e))

    def _collect_additional_metrics(self, result_dir: str, report: ExecutionReport):
        pass

    def _parse_node(self, data: dict) -> TestResultNode:
        node = TestResultNode(
            label=data.get("label", "Unnamed"),
            weight=float(data.get("weight", 1.0)),
            passed=data.get("passed"),
            message=data.get("message")
        )
        children_data = data.get("children", [])
        node.children = [self._parse_node(child) for child in children_data]
        return node

    def _execute_in_container(self) -> ExecutionReport:
        host_code_path = os.path.join(self.host_tmp, "code")
        host_results_path = os.path.join(host_code_path, os.path.basename(self.result_path))
        if self.grading_file is not None:
            results_file_path = os.path.join(host_results_path, self.grading_file)
        else:
            results_file_path = host_results_path

        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_code_path}:{self.container_mount}",
            "-w", self.container_mount,
        ]

        for additional_mount in self.additional_mounts:
            docker_cmd.extend(["-v", additional_mount])
        docker_cmd.extend([
            self.image,
            "bash", "-c", self.run_cmd
        ])

        try:
            result = subprocess.run(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.max_time,
                text=True
            )

            try:
                tree = self._load_result_tree(results_file_path)
            except FileNotFoundError:
                # If there are errors doing the tests, the final testing path is not created
                tree = None
            final_score = tree.calculate_score() if tree else 0.0

            report = ExecutionReport(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
                timeout=False,
                results_path=host_results_path,
                test_tree=tree,
                final_score=final_score,
                total_tests=self.total_tests,
                analysis=None,
            )

            if self.perform_analysis:
                source_code = self._extract_source_code(self.code_extraction_max_char)
                report.analysis = self.analyze_code(source_code, self.analysis_model)

            self._collect_additional_metrics(results_file_path, report)

            return report

        except subprocess.TimeoutExpired as e:
            return ExecutionReport(
                success=False,
                stdout=e.stdout or "",
                stderr=e.stderr or f"Execution timed out after {self.max_time}s",
                return_code=None,
                timeout=True,
                results_path=host_results_path,
                final_score=0.0,
                total_tests=0,
            )

    def run(self) -> ExecutionReport:
        self._prepare_environment()
        report = self._execute_in_container()
        shutil.rmtree(self.host_tmp, ignore_errors=True)
        return report

    def _extract_source_code(self, max_chars: int = 10000):
        """
        Extract source code from the given project directory, limited by total character count.

        Args:
            project_path (str): Root path of the project.
            max_chars (int): Maximum number of characters to extract.
            extensions (List[str]): List of file extensions to include.

        Returns:
            str: Combined source code as a single string, annotated with file paths.
        """
        collected_code = []
        total_chars = 0

        for root, _, files in os.walk(self.submission_path):
            for file in files:
                if any(file.endswith(ext) for ext in self.file_code_extensions):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            code = f.read()
                            if total_chars + len(code) > max_chars:
                                continue
                            collected_code.append(f"\n{self.line_comment_symbol} --- START FILE: {file_path} ---\n{code}\n{self.line_comment_symbol} --- END FILE: {file_path} ---\n")
                            total_chars += len(code)
                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")

        return "\n".join(collected_code)

    def analyze_code(self, code: str, model: str = 'codellama') -> str:
        """
        Analyze the given source code using an Ollama language model.

        Args:
            code (str): The combined source code string.
            model (str): The Ollama model name to use.

        Returns:
            str: The analysis result from the LLM.
        """
        import ollama
        if self.analysis_custom_prompt is not None:
            prompt = self.analysis_custom_prompt
        else:
            prompt = (
                "You are a senior software engineer reviewing a multi-language project.\n"
                "Please analyze the following source code files. Comment on design, structure, best practices, "
                "potential improvements, and any technical debt you notice.\n\n"
                f"{code}"
            )

        response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        return response['message']['content']

class PythonSubmissionTest(RunSubmissionTest):
    def __init__(self, submission_path: str, image: str = "python-grader:latest", max_time: int = 20):
        super().__init__(submission_path, {
            "image": image,
            "max_time": max_time,
            "run_cmd": (
                "cd /mnt/code && "
                "mkdir -p results && "
                "pytest --json-report --json-report-file=results/test_report.json > results/pytest.out 2>&1; "
                "coverage run -m pytest > /dev/null 2>&1; "
                "coverage json -o results/coverage.json; "
                "flake8 . --format=json --output-file results/flake8.json"
            ),
            "result_path": "/mnt/code/results",
            "grading_file": "test_report.json"
        })

    def _load_result_tree(self, result_file_path: str) -> TestResultNode:
        results_dir = os.path.dirname(result_file_path)
        root = TestResultNode(label="Python Grading", weight=1.0, children=[])

        # Load pytest test results
        try:
            with open(os.path.join(results_dir, "test_report.json")) as f:
                test_json = json.load(f)
            test_results = [
                TestResultNode(
                    label=t["nodeid"],
                    passed=t["outcome"] == "passed",
                    weight=1.0 / len(test_json["tests"]),
                    message=t.get("longrepr", "")
                )
                for t in test_json["tests"]
            ]
            root.children.append(TestResultNode(label="Tests", weight=0.6, children=test_results))
        except Exception as e:
            root.children.append(TestResultNode(label="Tests", weight=0.6, passed=False, message=f"Test error: {e}"))

        # Load coverage results
        try:
            with open(os.path.join(results_dir, "coverage.json")) as f:
                coverage_data = json.load(f)
            percent = coverage_data.get("meta", {}).get("coverage_percent", 0)
            passed = percent >= 80
            root.children.append(TestResultNode(
                label="Coverage",
                weight=0.2,
                passed=passed,
                message=f"{percent:.1f}% coverage"
            ))
        except Exception as e:
            root.children.append(TestResultNode(label="Coverage", weight=0.2, passed=False, message=f"Coverage error: {e}"))

        # Load linting results
        try:
            with open(os.path.join(results_dir, "flake8.json")) as f:
                lint_data = json.load(f)
            issues = sum(len(file_issues) for file_issues in lint_data.values())
            passed = issues == 0
            msg = f"{issues} issue(s) found"
            root.children.append(TestResultNode(label="Linting", weight=0.2, passed=passed, message=msg))
        except Exception as e:
            root.children.append(TestResultNode(label="Linting", weight=0.2, passed=False, message=f"Linting error: {e}"))

        root.calculate_score()
        return root

class CSubmissionTest(RunSubmissionTest):
    def __init__(self, submission_path: str, image: str = "cpp-gtest-grader:latest", max_time: int = 20):
        super().__init__(submission_path, {
            "image": image,
            "max_time": max_time,
            "run_cmd": (
                "cd /mnt/code && "
                "mkdir -p build results && "
                "(cmake . && make || make) > results/build.log 2>&1 && "
                "./test_suite --gtest_output=json:results/test_report.json > results/test_output.log 2>&1"
            ),
            "result_path": "/mnt/code/results",
            "grading_file": "test_report.json"
        })

    def _load_result_tree(self, result_file_path: str) -> TestResultNode:
        try:
            with open(result_file_path, "r") as f:
                raw = json.load(f)
        except Exception as e:
            return TestResultNode(label="C Tests", weight=1.0, passed=False, message=str(e))

        root = TestResultNode(label="C++ Tests", weight=1.0, children=[])
        test_cases = raw.get("testsuites", {}).get("testsuite", [])
        if not isinstance(test_cases, list):
            test_cases = [test_cases]

        total_tests = sum(int(ts["tests"]) for ts in test_cases)
        for suite in test_cases:
            suite_name = suite.get("name", "Unnamed Suite")
            children = []
            for case in suite.get("testcase", []):
                if isinstance(case, dict):
                    children.append(TestResultNode(
                        label=case.get("name", "Unnamed Test"),
                        weight=1.0 / total_tests,
                        passed="failure" not in case,
                        message=case.get("failure", {}).get("#text") if isinstance(case.get("failure"), dict) else None
                    ))
            root.children.append(TestResultNode(label=suite_name, weight=1.0 / len(test_cases), children=children))

        root.calculate_score()
        return root


class JavaSubmissionTest(RunSubmissionTest):
    def __init__(self, submission_path: str, image: str = "maven:latest", max_time: int = 30):
        super().__init__(submission_path, {
            "image": image,
            "max_time": max_time,
            "run_cmd": (
                "PROJECTS=($(find . -name pom.xml -printf \"%d %p\n\" | sort -n | perl -pe 's/^\d+\s//;' | xargs dirname)) && "
                "PROJECT_DIR=${PROJECTS[0]} && "
                "cd $PROJECT_DIR && "
                "mkdir -p /mnt/code/results && "
                #"mvn test jacoco:report checkstyle:checkstyle > /mnt/code/results/maven_output.log 2>&1 && "
                #"mvn test checkstyle:checkstyle > /mnt/code/results/maven_output.log 2>&1 && "
                "mvn clean org.jacoco:jacoco-maven-plugin:0.8.13:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.13:report checkstyle:checkstyle > /mnt/code/results/maven_output.log 2>&1 && "
                "find . -type d -name surefire-reports | while read dir; do "
                "  MOD_NAME=$(basename $(dirname $(dirname \"$dir\"))); "
                "  MOD_PATH=$(dirname $(dirname \"$dir\")); "
                "  mkdir -p /mnt/code/results/surefire-reports/$MOD_NAME; "
                "  cp \"$dir\"/*.xml /mnt/code/results/surefire-reports/$MOD_NAME/. 2>/dev/null || true; "
                "  find \"$MOD_PATH\" -name jacoco.xml -exec cp {} /mnt/code/results/surefire-reports/$MOD_NAME/. \\; ; "
                "  find \"$MOD_PATH\" -name checkstyle-result.xml -exec cp {} /mnt/code/results/surefire-reports/$MOD_NAME/. \\; ;"
                "done"
            ),
            "result_path": "/mnt/code/results",
            "grading_file": None,
            "file_code_extensions": ['.java',],
            "line_comment_symbol": "//",
            "additional_mounts": ["/tmp/maven_cache:/root/.m2/repository"]
        })
        os.makedirs('/tmp/maven_cache', exist_ok=True)
        self.total_tests = 0

    def _load_result_tree(self, result_path: str) -> TestResultNode:
        root = TestResultNode(label="JUnit Multi-Module Tests", weight=1.0, children=[])
        total_suites = 0
        total_tests = 0

        for module_dir in os.listdir(os.path.join(result_path, "surefire-reports")):
            mod_path = os.path.join(result_path, "surefire-reports", module_dir)
            if not os.path.isdir(mod_path):
                continue

            suite_nodes = []
            for filename in os.listdir(mod_path):
                if filename.startswith("TEST-") and filename.endswith(".xml"):
                    file_path = os.path.join(mod_path, filename)
                    try:
                        tree = ET.parse(file_path)
                        xml_root = tree.getroot()
                        suite_name = xml_root.attrib.get("name", filename)
                        for case in xml_root.findall("testcase"):
                            name = case.attrib.get("name", "Unnamed")
                            passed = case.find("failure") is None
                            message = None if passed else case.find("failure").text.strip()
                            suite_nodes.append(TestResultNode(
                                label=f"{suite_name}::{name}",
                                passed=passed,
                                weight=1.0,
                                message=message
                            ))
                            total_tests += 1
                    except Exception as e:
                        suite_nodes.append(TestResultNode(
                            label=filename,
                            passed=False,
                            weight=1.0,
                            message=f"Parse error: {e}"
                        ))

            # Normalize weights within this module
            for node in suite_nodes:
                node.weight = 1.0 / len(suite_nodes) if suite_nodes else 1.0

            if suite_nodes:
                root.children.append(TestResultNode(
                    label=module_dir,
                    weight=1.0,  # Will normalize later
                    children=suite_nodes
                ))
                total_suites += 1

        # Normalize top-level module weights
        for child in root.children:
            child.weight = 1.0 / total_suites if total_suites else 1.0

        root.calculate_score()
        self.total_tests = total_tests
        return root

    def get_total_tests_executed(self) -> int:
        return self.total_tests

    def _collect_additional_metrics(self, result_dir: str, report: ExecutionReport):
        report.metadata['coverage'] = {}
        report.metadata['checkstyle'] = {}
        if not os.path.exists(os.path.join(result_dir, "surefire-reports")):
            return

        for module_dir in os.listdir(os.path.join(result_dir, "surefire-reports")):
            # Jacoco Code Coverage
            jacoco_path = self._find_first(result_dir, "jacoco.xml")
            if jacoco_path:
                try:
                    tree = ET.parse(jacoco_path)
                    counter = tree.find(".//counter[@type='INSTRUCTION']")
                    covered = int(counter.attrib["covered"])
                    missed = int(counter.attrib["missed"])
                    total = covered + missed
                    coverage = 100.0 * covered / total if total > 0 else 0.0
                    report.metadata["coverage"][module_dir] = {
                        "coverage_percent": round(coverage, 2),
                        "coverage_error": None
                    }
                except Exception as e:
                    report.metadata["coverage"][module_dir] = {
                        "coverage_percent": None,
                        "coverage_error": str(e)
                    }

            # Checkstyle Report
            checkstyle_path = self._find_first(result_dir, "checkstyle-result.xml")
            if checkstyle_path:
                try:
                    tree = ET.parse(checkstyle_path)
                    violations = len(tree.findall(".//error"))
                    report.metadata["checkstyle"][module_dir] = {
                        "checkstyle_violations": violations,
                        "checkstyle_error": None
                    }
                except Exception as e:
                    report.metadata["checkstyle"][module_dir] = {
                        "checkstyle_violations": None,
                        "checkstyle_error": str(e)
                    }

    def _find_first(self, base_path: str, filename: str) -> str | None:
        for root, dirs, files in os.walk(base_path):
            if filename in files:
                return os.path.join(root, filename)
        return None


class CodeActivityTester:
    def __init__(self, submissions: SubmissionSet, tester_class: str, options: Optional[dict] = None):
        self._submissions = submissions
        self._options = options
        self._tester_class = CodeActivityTester._get_class(tester_class)

    @staticmethod
    def _get_class(class_name: str) -> type:
        parts = class_name.split('.')
        module = ".".join(parts[:-1])
        m = __import__(module)
        for comp in parts[1:]:
            m = getattr(m, comp)
        return m

    def run_tests(self):
        self._reports = {}
        i = 0
        for submission in self._submissions:
            i+=1
            if i > 2:
                break
            try:
                sub_test = self._tester_class(submission.get_local_path())
                report = sub_test.run()
                report.submission = submission
            except Exception as e:
                logger.error(e)
                reraise_exception(e)
                report = ExecutionReport(success=False, stderr=str(e))

            self._reports[submission.get_key()] = report

    def export_results(self, remove_groups: list[str] = None, format: str = 'csv'):
        if remove_groups is None:
            remove_groups = []
        for result in self._reports.values():
            print(f"{result.submission.get_key()} => {result.success}" )
