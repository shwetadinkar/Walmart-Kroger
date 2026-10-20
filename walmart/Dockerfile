FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY walmart_collector/ ./walmart_collector/
RUN pip install --no-cache-dir '.[azure]' && useradd -r -u 10001 collector
COPY config/ ./config/
USER 10001
ENTRYPOINT ["walmart-collector"]
CMD ["run", "--source", "provider", "--authorized-source", "--backend", "azure"]
