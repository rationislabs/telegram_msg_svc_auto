FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /bin/uv
RUN useradd --uid 10001 --create-home app
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY tgforecast ./tgforecast
RUN mkdir /data && chown app:app /data
ENV PATH=/app/.venv/bin:$PATH DATA_DIR=/data MPLCONFIGDIR=/tmp/matplotlib
USER app
VOLUME ["/data"]
CMD ["python", "-m", "tgforecast"]
