FROM denoland/deno:bin-2.6.8 AS deno
FROM python:3.12-slim
COPY --from=deno /deno /usr/local/bin/deno
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py engine.py ./
RUN useradd --create-home appuser && mkdir -p /tmp/linkcatch && chown -R appuser:appuser /app /tmp/linkcatch
USER appuser
ENV PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
