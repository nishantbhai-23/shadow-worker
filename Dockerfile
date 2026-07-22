FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY app app
COPY alembic alembic

RUN pip install --no-cache-dir .

CMD ["python", "-m", "app.bot.main"]
