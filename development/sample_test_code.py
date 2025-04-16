from teaching_utils.teaching_lib.code_tester import RunSubmissionTest

config = {
    "image": "my-docker-image:latest",
    "max_time": 30,
    "run_cmd": "cd /mnt/code && ./run_tests.sh",
    "result_path": "/mnt/code/results",
    "grading_file": "results.json"
}

runner = RunSubmissionTest("/home/user/submissions/student01/", config)
report = runner.run()

print(f"Final Score: {report.final_score:.2f}")
print(f"Tree Root: {report.test_tree.label}")

