FROM python:3.12-slim

WORKDIR /work

COPY pyproject.toml /work/
RUN mkdir -p /work/mentis && \
    touch /work/mentis/__init__.py && \
    pip install --no-cache-dir ".[dev]" && \
    rm -rf /work/mentis /work/pyproject.toml
