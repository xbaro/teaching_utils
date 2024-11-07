import os
import logging
import signal
import subprocess
import sys

# from teaching_utils.config import settings

logger = logging.getLogger(__name__)


def run_tests(language: str, code_path: str):

    if language.lower() == 'python':
        return run_pytest(code_path)


def run_pytest(code_path: str):
    _run_shell_cmd(['poetry', 'install'], code_path)
    _run_shell_cmd(['poetry', 'run', 'test'], code_path)
    return None


def _run_shell_cmd(cmd: list[str], working_path: str, timeout_s: int = 30):
    try:
        p = subprocess.Popen(cmd, start_new_session=True, cwd=working_path, shell=True, env={
            'POETRY_VIRTUALENVS_IN_PROJECT': 'true',
            'POETRY_VIRTUALENVS_CREATE': 'true',
            'POETRY_VIRTUALENVS_PATH': '.venv'
        })
        p.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        print(f'Timeout for {cmd} ({timeout_s}s) expired', file=sys.stderr)
        print('Terminating the whole process group...', file=sys.stderr)
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    return None
