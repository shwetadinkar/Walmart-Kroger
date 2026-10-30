# Egress region probe

Tests whether the egress address changes what the retailer edge returns. One
request per run, no retries, no proxy, no header or TLS manipulation, no
challenge solving. A refusal is the result, not an obstacle to work around.

The probe imports nothing from `walmart_collector` and writes nothing the
collector reads.

## Why the client method matters more than the region

Early measurements made the design point for us. A bare HTTPS GET was dropped
from every location tried, so it can never settle a question about geography.
A real browser reached the edge and was answered. **Only runs using the same
method are comparable**, and the probe records the method in every artifact and
refuses to present a cross-method comparison as controlled.

Default is `--method browser`, which drives real Chromium through Playwright
and is the only method comparable with the existing 403 evidence.

## Measurements so far

| Client | Egress | Address type | Result |
|---|---|---|---|
| Headed Chrome | India (Airtel) | residential | HTTP 403 with rendered challenge |
| python-urllib | India (Airtel) | residential | silent timeout, no response |
| python-urllib | US (GCP Ohio) | datacenter | silent timeout, no response |
| Chromium | US (GCP Ohio) | datacenter | no response, gateway error after 30s |

The only case where the edge responded at all was a residential address. Both
datacenter attempts got nothing, browser or not. That is the opposite of what a
country filter would produce, so address reputation explains the observations
better than geography does.

The cell still missing is **Azure specifically**. Azure is a different range
from GCP, and it is the environment the brief requires, so it has to be measured
rather than assumed.

## Local baseline

```bash
cd walmart
python tools/egress_region_probe.py \
  --target "https://www.marianos.com/pl/batteries/26003" \
  --region-label "local-india-residential" \
  --method browser \
  --output /private/egress
```

Keep the `RECEIPT.json` path. The Azure run compares against it.

## Azure US run

The point is a controlled comparison, so change **only** the egress. Same target
URL, same method, same single navigation.

Build a minimal image carrying this one tool, on the Microsoft Playwright base
so the browser is present:

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble
WORKDIR /probe
COPY walmart/tools/egress_region_probe.py /probe/
ENTRYPOINT ["python","/probe/egress_region_probe.py"]
```

Push it to the registry already used by this repository, then create a manual
job in a **US** region:

```bash
RG=rg-egress-probe
LOC=eastus                      # any US region; the point is non-India egress
az group create -n $RG -l $LOC
az containerapp env create -n env-egress -g $RG -l $LOC

az containerapp job create \
  -n marianos-egress-probe -g $RG --environment env-egress \
  --trigger-type Manual --replica-timeout 600 \
  --replica-retry-limit 0 \
  --cpu 1 --memory 2Gi \
  --image <registry>/egress-probe:latest \
  --args "--target","https://www.marianos.com/pl/batteries/26003",\
"--region-label","azure-eastus","--method","browser","--output","/tmp/out"

az containerapp job start -n marianos-egress-probe -g $RG
az containerapp job execution list -n marianos-egress-probe -g $RG -o table
```

`--replica-retry-limit 0` matters: the bound is one request, and a platform
retry would silently break that.

Read the result from the execution logs, then record it against the baseline
with `--compare /private/egress/.../RECEIPT.json`.

## Reading the outcome

**Served.** The edge answers an Azure address. That changes the whole position:
the collector was never the problem and unattended operation becomes a question
of coverage rather than access.

**Refused or dropped.** Geography is ruled out, since the same method from a
residential Indian line did get an answer. The blocker is address reputation,
and that is a finding worth delivering: it says unattended collection from a
major cloud is blocked at the network layer, which is exactly the acceptance
criterion the brief demands. It also explains why a complete Azure collector can
exist and still never produce data.

Either way the run is cheap, bounded, and answers a question that has been
assumed rather than measured since the start.

## What it does not establish

Category coverage, behaviour at volume, whether a served address keeps being
served, or the retailer's terms. One request answers one question.
