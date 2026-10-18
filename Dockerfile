# Harbor in one image: Bun builds the website, the Python server serves it next to the API.
#
#   docker build -t harbor .
#   docker run -p 3000:3000 --env-file .env harbor   # NESSIE_API_KEY and the rest: see .env.example
#
# Then open http://localhost:3000, and run ./seed.sh to replay Hurricane Milton for a demo household.

FROM oven/bun:1 AS web
WORKDIR /app
COPY app/package.json app/bun.lock ./
RUN bun install --frozen-lockfile
COPY app/ ./
RUN bun run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PATH=/srv/server/.venv/bin:$PATH \
    SITE_DIR=/srv/site PORT=3000

WORKDIR /srv/server
COPY server/pyproject.toml server/uv.lock ./
RUN uv sync --frozen --no-dev
COPY server/harbor ./harbor
COPY server/data ./data
COPY --from=web /app/dist /srv/site

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health',timeout=4)"
# One worker: the demo clock and the scheduler live in the process
CMD ["sh", "-c", "uvicorn harbor.main:app --host 0.0.0.0 --port $PORT --workers 1"]
