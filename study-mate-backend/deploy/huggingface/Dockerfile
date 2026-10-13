# Hugging Face Space wrapper around the image CI publishes to GHCR.
# Spaces run containers as uid 1000, so the writable dirs are re-owned here.
FROM ghcr.io/sahilijaz/studymate-api:main

USER root
RUN useradd --create-home --uid 1000 user \
 && chown -R 1000:1000 /data /models
USER user

ENV DATA_DIR=/data \
    EMBEDDING_CACHE_DIR=/models \
    ENVIRONMENT=production

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
