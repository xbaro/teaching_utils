# Python Grader Image

This image is used by `PythonSubmissionTest`.

It includes:
- `uv` for per-submission dependency resolution.
- Baseline grading tools preinstalled: `pytest`, `pytest-json-report`, `coverage`, `flake8`, `ruff`.

At runtime, each submission is evaluated as follows:
- Preferred path: if `pyproject.toml` exists, grader runs `uv sync` in the submission and executes tests with `uv run`.
- Legacy compatibility: if no `pyproject.toml` is present but `requirements.txt` exists, grader can still install dependencies with `pip`.
- Then grader runs tests, coverage, and linting, exporting JSON outputs in `results/`.

## Build with Podman

```zsh
podman build -t python-grader:latest -f resources/docker/python-grader/Dockerfile .
```

## Quick smoke test

```zsh
podman run --rm python-grader:latest python -m pytest --version
podman run --rm python-grader:latest uv --version
```

