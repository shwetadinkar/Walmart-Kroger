FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY marianos_collector ./marianos_collector
COPY config ./config
COPY azure/container_entrypoint.py ./azure/container_entrypoint.py
RUN pip install --no-cache-dir . "azure-storage-blob>=12.19,<13"

# Fail the BUILD if the store mapping is absent or still a placeholder.
#
# config/stores_live.json is gitignored on purpose, because it holds the
# verified location id, and azure/README.md says to copy it from
# stores_live.template.json before building. Nothing checked. So a build that
# skipped that step produced a perfectly good image whose first act, at 06:00
# UTC with nobody watching, was to fail on a missing file. A misconfigured job
# is the failure most likely to recur unattended, and this is the cheapest
# possible place to catch it: at build time, on the operator's screen.
#
# The placeholder check matters as much as the existence check. A copied
# template still containing DEMO or REPLACE would otherwise deploy, and this
# repository has already published one store's data under another store's name
# once.
RUN python - <<'PY'
import json, sys
path = "/app/config/stores_live.json"
try:
    with open(path, encoding="utf-8") as fh:
        stores = json.load(fh)
except FileNotFoundError:
    sys.exit(f"BUILD REFUSED: {path} is missing. It is gitignored by design; "
             "copy config/stores_live.template.json to config/stores_live.json "
             "and fill in the location id verified against Kroger's Locations "
             "API before building. See azure/README.md step 2.")
except json.JSONDecodeError as exc:
    sys.exit(f"BUILD REFUSED: {path} is not valid JSON: {exc}")

text = json.dumps(stores)
bad = [marker for marker in ("DEMO", "REPLACE", "UNRESOLVED", "EXAMPLE")
       if marker in text.upper()]
if bad:
    sys.exit(f"BUILD REFUSED: {path} still contains placeholder markers "
             f"{bad}. A scheduled job must not publish under an unverified "
             "store identity.")
if not stores:
    sys.exit(f"BUILD REFUSED: {path} is empty.")
print(f"stores_live.json present and free of placeholders: "
      f"{len(stores)} entr{'y' if len(stores) == 1 else 'ies'}")
PY

# No fixtures, README-only guides or developer secrets are included in production image.
ENTRYPOINT ["python", "/app/azure/container_entrypoint.py"]
