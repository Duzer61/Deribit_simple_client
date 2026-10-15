# syntax=docker/dockerfile:1

# Один образ приложения используется сервисами api, worker, beat и разовой задачей migrate.
# Секреты в образ не запекаются: все параметры приходят через переменные окружения.
FROM python:3.14-slim

# uv ставится из официального образа, чтобы установка зависимостей была воспроизводимой.
COPY --from=ghcr.io/astral-sh/uv:0.9.21 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Слой зависимостей кэшируется отдельно от исходников.
COPY pyproject.toml uv.lock ./
COPY README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# alembic.ini и alembic/ нужны сервису migrate (env.py читает DATABASE_URL из Settings).
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN uv sync --frozen --no-dev

# Непривилегированный пользователь владеет рабочим каталогом (celery beat пишет здесь schedule-файл).
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "deribit_tracker.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
