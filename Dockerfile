FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY toolfuzz ./toolfuzz
COPY examples ./examples

RUN python -m pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 toolfuzz
USER toolfuzz

ENTRYPOINT ["toolfuzz"]
