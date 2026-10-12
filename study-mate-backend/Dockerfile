# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EMBEDDING_CACHE_DIR=/models \
    DATA_DIR=/data

WORKDIR /srv

# Build deps are only needed to compile wheels that lack binaries on this platform.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# Optional: bake the local embedding model into the image so cold starts don't
# hit the network. Off by default because the Gemini embedding API needs no
# model and Hugging Face downloads can be rate-limited during builds.
ARG PREFETCH_EMBEDDING_MODEL=false
RUN if [ "$PREFETCH_EMBEDDING_MODEL" = "true" ]; then \
      python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/models')"; \
    fi

COPY app ./app

RUN useradd --create-home --uid 10001 app \
 && mkdir -p /data /models \
 && chown -R app:app /data /models /srv
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
