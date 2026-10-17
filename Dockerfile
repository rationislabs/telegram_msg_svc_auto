FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /bin/uv
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
