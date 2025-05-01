import logging
import os
import pickle
import shutil
import subprocess
import uuid
import json
import re
import valparse

import xml.etree.ElementTree as ET
import teaching_utils.teaching_lib.text_utils

from typing import Optional, Any, TextIO
from .test_utils import TestResultNode, ExecutionReport
from teaching_utils.config.core import Config


from .submissions import SubmissionSet
from .gtest_utils import load_gtest_results


logger = logging.getLogger(__name__)


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
        self.run_tests = config.get("run_tests", True)
        self.run_cmd = config.get("run_cmd")
        self.additional_mounts = config.get("additional_mounts", [])

        self.data_path = config.get("data_path")
        self.data_mount = config.get("data_mount", "/mnt/data")
        self.result_path = config.get("result_path")
        self.grading_file = config.get("grading_file")
        self.remove_tmp = config.get("remove_tmp", True)

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
        self.analysis_engine = config.get("analysis_engine", "ollama")

        self.multi_project = config.get("multi_project", False)
        self.multi_project_structure = config.get("multi_project_structure", "directory")
        self.multi_project_module_regex = config.get("multi_project_module_regex", [])
        self._multi_project_modules = None

        self.total_tests = 0

    def _prepare_environment(self):
        os.makedirs(self.host_tmp, exist_ok=True)
        shutil.copytree(self.submission_path, os.path.join(self.host_tmp, "code"), dirs_exist_ok=True)

        # Apply any extra action to the code before execution
        self._prepare_code_execution()

    def _prepare_code_execution(self):
        pass

    def _compute_working_directory(self):
        return None

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


    def _fix_path(self, path: str) -> str:
        if os.name == 'nt':
            path = path.replace("\\", "/")
            if path[1:3] == ":/":
                path = '/' + path[0] + path[2:]
        return path

    def _execute_in_container(self) -> ExecutionReport:
        host_code_path = os.path.abspath(os.path.join(self.host_tmp, "code"))
        host_results_path = os.path.join(host_code_path, os.path.basename(self.result_path))
        if self.grading_file is not None:
            results_file_path = os.path.join(host_results_path, self.grading_file)
        else:
            results_file_path = host_results_path

        work_path = self._compute_working_directory()
        if work_path is None or len(work_path) == 0:
            work_path = self.container_mount
        else:
            work_path = os.path.join(self.container_mount, os.path.relpath(os.path.abspath(work_path), host_code_path))


        docker_cmd = [
            "docker", "run", "--rm",
            "-w", self._fix_path(work_path),
            "-v", f"{self._fix_path(host_code_path)}:{self.container_mount}",
        ]

        if self.data_path is not None:
            docker_cmd.extend(["-v", f"{self._fix_path(os.path.abspath(self.data_path))}:{self.data_mount}"])

        for additional_mount in self.additional_mounts:
            docker_cmd.extend(["-v", additional_mount])
        docker_cmd.extend([
            self.image,
            "bash", "-c", self.run_cmd
        ])

        try:
            # Run the command in the Docker container
            if self.run_tests:
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
            else:
                report = ExecutionReport(
                    success=True,
                    stdout='',
                    stderr='',
                    return_code=None,
                    timeout=False,
                    results_path=host_results_path,
                    test_tree=None,
                    final_score=None,
                    total_tests=0,
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
        if self.remove_tmp:
            # Remove the temporary directory after execution
            logger.debug(f"Removing temporary directory {self.host_tmp}")
            shutil.rmtree(self.host_tmp, ignore_errors=True)
        return report

    def _extract_source_code(self, max_chars: int = 10000, source_path: str = None) -> str | dict:
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

        if source_path is None:
            source_path = self.submission_path

        for root, _, files in os.walk(source_path):
            for file in files:
                if any(file.endswith(ext) for ext in self.file_code_extensions):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            code = f.read()
                            # Limit the total number of characters
                            if max_chars is not None and max_chars > 0 and total_chars + len(code) > max_chars:
                                continue
                            collected_code.append(f"\n{self.line_comment_symbol} --- START FILE: {file_path} ---\n{code}\n{self.line_comment_symbol} --- END FILE: {file_path} ---\n")
                            total_chars += len(code)
                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")

        return "\n".join(collected_code)

    def _perform_analysis(self, prompt, model, role: str = 'user') -> dict:

        if self.analysis_engine == 'codellama':
            import ollama
            req_response = ollama.chat(model=model, messages=[{"role": role, "content": prompt}])
            response = {
                "success": True,
                "duration": req_response.total_duration,
                "message": req_response.message['content'],
            }

        elif self.analysis_engine == 'openai':
            from openai import OpenAI

            config = Config()

            client = OpenAI(
                # This is the default and can be omitted
                api_key=config.OPENAI_API_KEY,
            )


            req_response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": role, "content": prompt},
                ],
                temperature=0.5
            )

            response = {
                "success": len(req_response.choices) > 0,
                "duration": 0.0,
                "message": json.loads(req_response.choices[0].message.content.replace('```json', '').replace('```', ''))['feedback'],
                "extra_info": json.loads(req_response.choices[0].message.content.replace('```json', '').replace('```', ''))
            }

        else:
            raise NotImplementedError(f"Unknown analysis engine: {self.analysis_engine}")

        return response

    def analyze_code(self, code: str | dict, model: str = 'codellama') -> dict:
        """
        Analyze the given source code using an Ollama language model.

        Args:
            code (str): The combined source code string.
            model (str): The Ollama model name to use.

        Returns:
            str: The analysis result from the LLM.
        """
        if self.analysis_custom_prompt is not None:
            prompt = self.analysis_custom_prompt
        else:
            """prompt = (
                "You are a senior software engineer reviewing a multi-language project.\n"
                "Please analyze the following source code files. Comment on design, structure, best practices, "
                "potential improvements, and any technical debt you notice.\n\n"                
            )"""
            """prompt = (
                "Ets un professor de programació corregint el codi lliurat per un estudiant.\n"
                "Analitza amb un llenguatge amable i constructiu aquest codi, tenint en compte criteris de qualitat i bones pràctiques."
                "Finalment, qualifica amb una nota de 0 a 100 el codi, explicant els criteris seguits. El codi:\n\n"
            )"""
            prompt = (
                "You are a programming teacher assessing the code submitted by a student.\n"
                "Analyze this code in a friendly and constructive manner, taking into account quality criteria and good practices."
                "Finally, rate the code with a score from 0 to 100, explaining the followed criteria. The code:\n\n"
            )
        if isinstance(code, str):
            prompt += code
            response = self._perform_analysis(prompt, model)
            result = {
                'message': response['message'],
                'info': None,
            }
        elif isinstance(code, dict):
            analysis = {}
            for k, v in code.items():
                if isinstance(prompt, dict):
                    k_prompt = prompt.get(k, prompt)
                else:
                    k_prompt = prompt
                k_prompt += v
                k_response = self._perform_analysis(k_prompt, model)
                analysis[k] = {
                    'message': k_response['message'],
                    'info': k_response,
                }

            result = {
                'message': '',
                'info': analysis
            }
            for k, v in analysis.items():
                result['message'] += f"{k}:\n\n {v['message']}\n\n"
        else:
            raise RuntimeError(f"Unsupported code type: {type(code)}")
        return result

    def _find_first(self, base_path: str, filename: str) -> str | None:
        for root, dirs, files in os.walk(base_path):
            if filename in files:
                return os.path.join(root, filename)
        return None

class PythonSubmissionTest(RunSubmissionTest):
    def __init__(self, submission_path: str, image: str = "python-grader:latest", max_time: int = 30,
                 config: Optional[dict] = None):
        if config is None:
            config = {}
        config.update(
             {
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
            }
        )
        super().__init__(submission_path, config)

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
    def __init__(self, submission_path: str, image: str = "xbaro/gcc-gtest:latest", max_time: int = 30,
                 config: Optional[dict] = None):
        if config is None:
            config = {
                'max_time': max_time,
            }
        elif 'max_time' not in config:
            config['max_time'] = max_time
        config.update(
             {
                "image": image,
                "run_cmd": (
                    "mkdir -p /mnt/code/results && "
                    "mkdir -p build && cd build && "
                    "cmake .. > /mnt/code/results/cmake.log 2>&1 && "
                    "make > /mnt/code/results/build.log 2>&1 && "
                    "make test > /mnt/code/results/test.log 2>&1 ; "
                    "cp *.json /mnt/code/results/ > /mnt/code/results/result_copy.log 2>&1 || :"
                    #"./test_suite --gtest_output=json:results/test_report.json > results/test_output.log 2>&1"
                ),
                "result_path": "/mnt/code/results",
            }
        )
        super().__init__(submission_path, config)
        self.total_tests = 0

    def _load_result_tree(self, result_file_path: str) -> TestResultNode:
        if not os.path.exists(result_file_path):
            self.total_tests = 0
            return TestResultNode(label="C Tests", weight=1.0, passed=False, message="No results file found.")

        root = load_gtest_results(os.path.join(result_file_path, 'json', ''))

        self.total_tests = root.num_tests

        root.calculate_score()
        return root

    def _prepare_code_execution(self):
        # Copy external files if provided
        base_path = self._compute_working_directory()
        dict = {
            'SOURCE_PATH': base_path,
            'RESULT_PATH': self.result_path,
        }
        if not self.multi_project:
            pass
        elif self.multi_project_structure == 'folder':
            if base_path is not None and self.data_path is not None:
                modules = os.listdir(base_path)
                if len(modules) == 0 and self.multi_project_structure:
                    logger.error(f"No modules found in base_path: {base_path}")
                    raise Exception(f"No modules found in base_path: {base_path}")
                self._multi_project_modules = {}
                for module in self.multi_project_module_regex:
                    mod_found = False
                    for folder in modules:
                        if re.search(self.multi_project_module_regex[module], folder):
                            self._multi_project_modules[module] = os.path.join(base_path, folder)
                            dict[f'{module.upper()}_PATH'] = folder
                            mod_found = True
                            continue
                    if not mod_found:
                        logger.error(f"Module {module} not found")
            shutil.copytree(self.data_path, base_path, dirs_exist_ok=True)
            teaching_utils.teaching_lib.text_utils.replace_file_keys(os.path.join(base_path, 'CMakeLists.txt'), dict, '$!-', '-!$')

    def _compute_working_directory(self):
        # Locate the first path with a "main.cpp".
        base_path = self._find_first(os.path.join(self.host_tmp, "code"), 'main.cpp')
        if base_path is not None:
            return os.path.dirname(os.path.dirname(base_path))

        return None

    def _extract_source_code(self, max_chars: int = 10000, source_path: str = None) -> str | dict:
        if source_path is None:
            source_path = self._compute_working_directory()

        src_code = {}
        if self._multi_project_modules is not None:
            for module in self._multi_project_modules:
                code = super()._extract_source_code(max_chars, self._multi_project_modules[module])
                if code is not None and len(code) > 0:
                    src_code[module] = code
        else:
            src_code = super()._extract_source_code(max_chars, source_path)

        return src_code


    def _collect_additional_metrics(self, result_dir: str, report: ExecutionReport):
        report.metadata['memcheck'] = {}
        if not os.path.exists(result_dir):
            return

        for mem_file in os.listdir(result_dir):
            if mem_file.endswith('.xml'):
                xml_file = valparse.Parser(os.path.join(result_dir, mem_file))
                report.metadata['memcheck'][mem_file] = {
                    'has_leaks': xml_file.hasLeaks(),
                    'has_errors': xml_file.hasErrors(),
                    'total_bytes_leaked': xml_file.totalBytesLeaked(),
                    'total_errors': xml_file.errcount,
                    'total_leaks': xml_file.leakcount,
                    'errors': [],
                    'leaks': []
                }
                for err in xml_file.errs:
                    err_json = {
                        'kind': err.kind.value,
                        'msg': err.msg,
                        'msg_secondary': err.msg_secondary,
                        'blocks_leaked': err.blocks_leaked,
                        'bytes_leaked': err.bytes_leaked,
                        'stack': []
                    }
                    for stacktrace in err.stack:
                        err_json['stack'].append({
                            'dir': stacktrace.dir,
                            'line': stacktrace.line,
                            'file': stacktrace.file,
                            'fn': stacktrace.fn,
                            'ip': stacktrace.ip,
                            'obj': stacktrace.obj,
                        })
                    report.metadata['memcheck'][mem_file]['errors'].append(err_json)



class JavaSubmissionTest(RunSubmissionTest):
    def __init__(self, submission_path: str, image: str = "maven:latest", max_time: int = 30,
                 config: Optional[dict] = None):
        if config is None:
            config = {}
        config.update(
            {
                "image": image,
                "max_time": max_time,
                "run_cmd": (
                    "PROJECTS=($(find . -name pom.xml -printf \"%d %p\n\" | sort -n | perl -pe 's/^\d+\s//;' | xargs dirname)) && "
                    "PROJECT_DIR=${PROJECTS[0]} && "
                    "cd $PROJECT_DIR && "
                    "mkdir -p /mnt/code/results && "
                    # "mvn test jacoco:report checkstyle:checkstyle > /mnt/code/results/maven_output.log 2>&1 && "
                    # "mvn test checkstyle:checkstyle > /mnt/code/results/maven_output.log 2>&1 && "
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
                "file_code_extensions": ['.java', ],
                "line_comment_symbol": "//",
                "additional_mounts": ["/tmp/maven_cache:/root/.m2/repository"]
            }
        )
        super().__init__(submission_path, config)
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
            suit_passed = True
            for node in suite_nodes:
                node.weight = 1.0 / len(suite_nodes) if suite_nodes else 1.0
                suit_passed = suit_passed and node.passed

            if suite_nodes:
                root.children.append(TestResultNode(
                    label=module_dir,
                    weight=1.0,  # Will normalize later
                    children=suite_nodes,
                    passed=suit_passed,
                ))
                total_suites += 1

        # Normalize top-level module weights
        root.passed = True
        for child in root.children:
            child.weight = 1.0 / total_suites if total_suites else 1.0
            root.passed = root.passed and child.passed

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
            jacoco_path = self._find_first(os.path.join(result_dir, "surefire-reports", module_dir), "jacoco.xml")
            if jacoco_path:
                try:
                    tree = ET.parse(jacoco_path)
                    counter = tree.find(".//counter[@type='INSTRUCTION']")
                    covered = int(counter.attrib["covered"])
                    missed = int(counter.attrib["missed"])
                    total = covered + missed
                    coverage = 100.0 * covered / total if total > 0 else 0.0
                    report.metadata["coverage"][module_dir] = {
                        "coverage_covered": covered,
                        "coverage_missed": missed,
                        "coverage_total": total,
                        "coverage_percent": round(coverage, 2),
                        "coverage_error": None
                    }
                except Exception as e:
                    report.metadata["coverage"][module_dir] = {
                        "coverage_percent": None,
                        "coverage_error": str(e)
                    }

            # Checkstyle Report
            checkstyle_path = self._find_first(os.path.join(result_dir, "surefire-reports", module_dir), "checkstyle-result.xml")
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


class CodeActivityTester:
    def __init__(self, submissions: SubmissionSet, tester_class: str, options: Optional[dict] = None):
        self._submissions = submissions
        self._options = options
        self._tester_class = CodeActivityTester._get_class(tester_class)
        self._reports: dict[str, ExecutionReport] = {}

    @staticmethod
    def _get_class(class_name: str) -> type:
        parts = class_name.split('.')
        module = ".".join(parts[:-1])
        m = __import__(module)
        for comp in parts[1:]:
            m = getattr(m, comp)
        return m

    def run_tests(self, start: int = 0, limit: int = None, cache_file: str = None ):
        cache = {}
        if cache_file is not None and os.path.exists(cache_file):
            logger.info(f"Loading cached results from {cache_file}")
            cache = pickle.load(open(cache_file, "rb"))

        self._reports = {}
        i = 0
        for submission in self._submissions:
            if i < start:
                logger.debug("Skipped submission %d", i)
                i += 1
                continue
            i += 1
            if limit is not None and i > limit:
                logger.debug("Breaking test at submission %d", i)
                break
            if submission.get_key() in cache:
                logger.info(f"Found cached result for submission {submission.get_key()}")
                report = cache[submission.get_key()]
            else:
                try:
                    sub_test = self._tester_class(submission.get_local_path(), config=self._options)
                    report = sub_test.run()
                    report.submission = submission
                except Exception as e:
                    logger.error(e)
                    report = ExecutionReport(return_code=-1, results_path=None, success=False, stderr=str(e), stdout='', timeout=False)
                cache[submission.get_key()] = report
                if cache_file is not None:
                    with open(cache_file, "wb") as f:
                        pickle.dump(cache, f)

            self._reports[submission.get_key()] = report
            logger.info("Submission %s: %s", submission.get_key(), str(report))


    def export_results(self, out_file: str, remove_groups: list[str] = None, format: str = 'csv', override=False):
        if os.path.exists(out_file) and not override:
            raise FileExistsError(f"Output file {out_file} already exists. Use override=True to overwrite.")
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        if remove_groups is None:
            remove_groups = []
        remove_groups = set(remove_groups)
        with open(out_file, 'w') as fout:
            if format == 'csv':
                fout.write(f"Nom,Cognoms,\"Número ID\",Grups,\"Grups Filtrats\",Qualificació,\"Feedback\"\n")
            elif format == 'json':
                fout.write("{\n\"results\": [\n")
            else:
                raise NotImplementedError(f"Format {format} not supported")
            for result in self._reports.values():
                self._export_row(fout, result, format, remove_groups)
            if format == 'json':
                fout.write("]}\n")

    def _export_row(self, fout: TextIO, result: ExecutionReport, format: str, remove_groups: set[str] = None):
        if result.submission is None:
            logger.error("Submission result not available. Row skipped.")
            return
        info = result.submission.get_info()
        if format == 'csv':
            fout.write(f"\"{info.get('student_name')}\",\"{info.get('student_surname')}\",{info.get('student_id')},\"{','.join(info.get('student_groups', []))}\"")
            fout.write(",\"" + ','.join([g for g in info.get('student_groups', []) if g not in remove_groups]) + "\"")
            fout.write(f",{result.final_score:.2f},\"{self._build_feedback(result)}\"\n")
        elif format == 'json':
            res_json = result.to_dict()
            res_json["score"] = round(res_json["final_score"], 2)
            res_json["feedback"] = self._build_feedback(result)
            fout.write(json.dumps(res_json, indent=4))
        else:
            raise NotImplementedError

    def _build_feedback(self, report: ExecutionReport) -> str:
        feedback = []
        if report.test_tree:
            feedback.append(f"Test Results: {report.test_tree.label}")
            feedback.append(f"  => {report.total_tests} tests found.")
            for child in report.test_tree.children:
                feedback.append(f"    - {child.label}: {'Passed' if child.passed else 'Failed'}")
        if report.analysis:
            feedback.append(f"Code Analysis: {report.analysis}")
        return "\n".join(feedback).replace("\"", "'")

