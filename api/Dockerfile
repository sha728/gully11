# The Gully XI API (FastAPI + simulator). Built by Render from render.yaml; the same
# image runs locally: docker build -t gully11-api api && docker run -p 8000:8000 ...
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1

WORKDIR /app
# Dependencies first (cached between builds), then the code.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY db ./db
RUN uv sync --frozen --no-dev

# Render sets $PORT; default 8000 elsewhere. One process: live auction rooms are
# held in memory, so more workers would split them (see docs/auction.md).
CMD ["sh", "-c", "/app/.venv/bin/uvicorn gully_api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
