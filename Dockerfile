FROM python:3.12-slim AS base

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY bot/ bot/

RUN useradd --create-home --shell /bin/bash botuser
USER botuser

CMD ["python", "-m", "bot"]
