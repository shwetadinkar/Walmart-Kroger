FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY pyproject.toml ./
COPY marianos_collector ./marianos_collector
COPY config ./config
COPY azure/container_entrypoint.py ./azure/container_entrypoint.py
COPY tools/browser_runtime_smoke.py ./tools/browser_runtime_smoke.py
RUN pip install --no-cache-dir ".[azure,browser]" \
    && python -m playwright install --with-deps chromium \
    && groupadd --gid 10001 collector \
    && useradd --uid 10001 --gid collector --create-home collector \
    && python -c "from azure.identity import ManagedIdentityCredential; from azure.storage.blob import BlobServiceClient"
# No fixtures, README-only guides or developer secrets are included in production image.
USER collector
RUN python tools/browser_runtime_smoke.py
ENTRYPOINT ["python", "/app/azure/container_entrypoint.py"]
