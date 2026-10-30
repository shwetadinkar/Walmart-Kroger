FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY walmart_collector/ ./walmart_collector/
RUN pip install --no-cache-dir '.[azure]' && useradd -r -u 10001 collector
COPY config/ ./config/
COPY azure/container_entrypoint.py ./azure/container_entrypoint.py
USER 10001
# The route is chosen at run time by WALMART_SOURCE, not baked into the image,
# so one immutable image serves the provider, OPD and composite routes.
ENTRYPOINT ["python", "/app/azure/container_entrypoint.py"]
