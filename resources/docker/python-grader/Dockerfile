FROM python:3.12-slim

LABEL maintainer="Xavier Baro <https://github.com/xbaro>"

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        build-essential \
        ca-certificates \
        curl \
        git \
        pkg-config \
        libmariadb-dev \
        libmariadb-dev-compat \
        libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install uv plus baseline grader tools used by PythonSubmissionTest.
RUN python -m pip install --no-cache-dir uv && \
    uv pip install --system --no-cache \
        pytest \
        pytest-json-report \
        coverage \
        flake8 \
        ruff

WORKDIR /mnt/code

CMD ["bash"]

