FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/
COPY data/ data/

EXPOSE 5050

CMD ["python", "-m", "content_guard.api.app"]
