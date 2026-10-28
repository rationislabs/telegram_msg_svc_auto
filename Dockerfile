# uv as a stage of its own: Dependabot's docker updates read FROM lines.
FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv
FROM python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2
COPY --from=uv /uv /bin/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --create-home app
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY tgforecast ./tgforecast
ENV PATH=/app/.venv/bin:$PATH MPLCONFIGDIR=/tmp/matplotlib
USER app
CMD ["python", "-m", "tgforecast"]
