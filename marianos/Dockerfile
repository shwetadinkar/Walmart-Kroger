FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY marianos_collector ./marianos_collector
COPY config ./config
COPY azure/container_entrypoint.py ./azure/container_entrypoint.py
RUN pip install --no-cache-dir . "azure-storage-blob>=12.19,<13"
# No fixtures, README-only guides or developer secrets are included in production image.
ENTRYPOINT ["python", "/app/azure/container_entrypoint.py"]
