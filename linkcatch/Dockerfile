FROM denoland/deno:bin-2.9.5 AS deno
FROM brainicism/bgutil-ytdlp-pot-provider:2.0.2-deno AS pot
FROM python:3.12-slim
COPY --from=deno /deno /usr/local/bin/deno
COPY --from=pot /app /opt/bgutil/server
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libjpeg62-turbo libgif7 librsvg2-2 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ENV DENO_DIR=/opt/bgutil/server/.cache/deno DENO_NO_PROMPT=1 DENO_NO_UPDATE_CHECK=1
RUN cd /opt/bgutil/server && deno cache --frozen src/generate_once.ts
COPY app.py engine.py ./
RUN useradd --create-home appuser && mkdir -p /tmp/linkcatch && chown -R appuser:appuser /app /tmp/linkcatch /opt/bgutil
USER appuser
ENV PYTHONUNBUFFERED=1 BGUTIL_HOME=/opt/bgutil/server
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
