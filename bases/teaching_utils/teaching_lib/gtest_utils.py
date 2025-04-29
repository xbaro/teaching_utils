import os
import json

from .test_utils import TestResultNode

def _gtest_create_testcase_node(testcase, weight: float = 1.0):
    """
    Creates a TestResultNode for a single testcase.
    """
    passed = testcase['status'] == 'RUN' and testcase['result'] == 'COMPLETED' and 'failures' not in testcase
    message = None
    if 'failures' in testcase:
        message = f'==> {testcase['name']}:\n' + '\n'.join(failure['failure'] for failure in testcase['failures'])

    return TestResultNode(
        label=testcase['name'],
        passed=passed,
        message=message,
        weight=weight,
        num_tests=1
    )

def _gtest_create_testsuite_node(testsuite_name, testsuite_data):
    """
    Creates a TestResultNode for a testsuite, including all its testcases.
    """
    weight = 1.0 / len(testsuite_data['testsuite'])
    children = [_gtest_create_testcase_node(testcase, weight=weight) for testcase in testsuite_data['testsuite']]
    passed = True

    messages = []
    num_tests = 0
    for child in children:
        passed = passed and child.passed == True
        num_tests += child.num_tests
        if child.message is not None:
            messages.append(child.message)
    message = None
    if len(messages) > 0:
        message = f'--------------\n    {testsuite_name}\n--------------\n' + '\n'.join(
            messages) + '--------------\n\n'

    return TestResultNode(
        label=testsuite_name,
        children=children,
        passed=passed,
        message=message,
        num_tests=num_tests,
    )

def _gtest_create_suite_node(suite_name, suite_data):
    """
    Creates a TestResultNode for a full suite, including all testsuites.
    """
    children = [
        _gtest_create_testsuite_node(testsuite_name, testsuite_data)
        for testsuite_name, testsuite_data in suite_data['testsuites'].items()
    ]

    passed = True
    messages = []
    num_tests = 0
    for child in children:
        passed = passed and child.passed == True
        num_tests += child.num_tests
        if child.message is not None:
            messages.append(child.message)

    message = None
    if len(messages) > 0:
        message = f'========================================================\n    {suite_name}\n========================================================\n' + '\n'.join(messages) + '========================================================\n\n'

    return TestResultNode(
        label=suite_name,
        children=children,
        passed=passed,
        message=message,
        num_tests=num_tests,
    )

def parse_gtest_results(test_results):
    """
    Top-level parser for all aggregated GTest results.
    """
    if not test_results:
        return None

    if len(test_results) == 1:
        # Only one root node needed
        suite_name, suite_data = next(iter(test_results.items()))
        root = _gtest_create_suite_node(suite_name, suite_data)
    else:
        # Multiple top-level suites; create a summary root node
        children = [
            _gtest_create_suite_node(suite_name, suite_data)
            for suite_name, suite_data in test_results.items()
        ]

        root = TestResultNode(
            label="GTest Summary",
            children=children
        )

    root.num_tests = 0
    for child in root.children:
        root.num_tests += child.num_tests

    return root

def load_gtest_results(result_path):
    """
    Loads and aggregates GTest JSON results from the given directory and returns a TestResultNode tree.
    """
    aggregated_results = {}

    for filename in os.listdir(result_path):
        if filename.endswith(".json"):
            with open(os.path.join(result_path, filename), 'r') as json_file:
                raw_data = json.load(json_file)
                test_name = raw_data.get("name", "Unknown")

                if 'testsuites' not in raw_data:
                    continue

                if test_name not in aggregated_results:
                    aggregated_results[test_name] = {
                        "tests": 0,
                        "failures": 0,
                        "disabled": 0,
                        "errors": 0,
                        "testsuites": {}
                    }

                # Aggregate top-level metrics
                aggregated_results[test_name]["tests"] += raw_data.get("tests", 0)
                aggregated_results[test_name]["failures"] += raw_data.get("failures", 0)
                aggregated_results[test_name]["disabled"] += raw_data.get("disabled", 0)
                aggregated_results[test_name]["errors"] += raw_data.get("errors", 0)

                for testsuite in raw_data["testsuites"]:
                    suite_name = testsuite['name']
                    if suite_name not in aggregated_results[test_name]["testsuites"]:
                        aggregated_results[test_name]["testsuites"][suite_name] = {
                            "tests": 0,
                            "failures": 0,
                            "disabled": 0,
                            "errors": 0,
                            "testsuite": []
                        }

                    suite_data = aggregated_results[test_name]["testsuites"][suite_name]
                    suite_data["tests"] += testsuite.get("tests", 0)
                    suite_data["failures"] += testsuite.get("failures", 0)
                    suite_data["disabled"] += testsuite.get("disabled", 0)
                    suite_data["errors"] += testsuite.get("errors", 0)
                    suite_data["testsuite"].extend(testsuite.get('testsuite', []))

    return parse_gtest_results(aggregated_results)