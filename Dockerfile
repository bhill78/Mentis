# Linux development image: pinned Python and Mentis's pinned dependencies only.
# The source is not copied in: compose bind-mounts the host checkout at /work, so files
# and Git stay host-owned and the same tree is tested natively and here.
FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /deps
COPY pyproject.toml ./
# Install the dependencies of `mentis[dev]`, then remove the stub package itself:
# tests import mentis from the bind-mounted /work (pyproject `pythonpath`).
RUN mkdir mentis && touch mentis/__init__.py \
    && pip install ".[dev]" && pip uninstall -y mentis && pip check

WORKDIR /work
CMD ["python", "-m", "pytest", "-q"]
