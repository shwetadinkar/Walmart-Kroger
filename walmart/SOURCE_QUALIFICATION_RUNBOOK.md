# Source qualification probe

A bounded, single-request probe that answers one question about a candidate data
source before any production work or spending decision: **does it return a price
bound to the store we asked for, together with a displayed price per measure and
offer terms?**

This is not a collector and not a contest demonstration. The probe imports nothing
from `walmart_collector`, writes nothing the collector reads, and never touches a
release, a latest pointer or any existing dataset. Its output is a receipt and a
findings file.

## Bounds

One request. No retries. A hard cap of 25 items regardless of what is asked for.
A wall-clock timeout. The probe refuses to run outside these rather than widening
them silently.

## Secrets

The provider token is read from `APIFY_TOKEN` in the environment and is never
written to any output file. `RECEIPT.json` records `secrets_in_output: false`.

## Offline dry check first, no network and no spend

Audit any saved response to see exactly what the probe measures:

```bash
cd walmart
python tools/source_qualification_probe.py \
  --audit /path/to/saved_response.json \
  --store-id 100 --item-ids 111 \
  --output /private/qualification
```

## Live bounded probe

```bash
export APIFY_TOKEN='...'            # not echoed, not stored
cd walmart
python tools/source_qualification_probe.py \
  --store-id 100 --zipcode 72712 \
  --item-ids 20877373221 1446707820 \
  --max-items 5 --timeout 600 \
  --plan-tier trial \
  --output /private/qualification
```

Set `--plan-tier` to whichever tier actually produced the run. A trial gives full
features for a limited period, so a trial result shows what the source *can* do
but is not an ongoing entitlement. The receipt records the tier and sets
`result_reproducible_without_payment` accordingly, because the brief requires
every paid API or service to be disclosed with a running cost.

Use `--search` instead of `--item-ids` only if specific items are not known.
Named item IDs make the run deterministic and repeatable.

## What a run leaves behind

| File | Contents |
|---|---|
| `INPUT.json` | the exact request body sent |
| `RAW_RESPONSE.json` | the provider response, unmodified |
| `RAW_SHA256.txt` | hash of that response as received |
| `RECEIPT.json` | run id, UTC start and end, endpoint, counts, bounds, isolation flags |
| `ACCEPTANCE.json` | per-field presence and the store-binding judgement |
| `FINDINGS.md` | the same, readable |

Every statement in `FINDINGS.md` can be checked against `RAW_RESPONSE.json`, whose
hash is recorded, so none of it has to be taken on trust.

## How to read the result

**Store binding** is judged separately from field presence. A response can carry a
`storeLocation.storeId` on every row and still be `NOT_BOUND`, if the store it
reports is not the store that was requested. That distinction is the whole point:
a provider that silently substitutes a default store fails the brief regardless of
how rich its price fields are.

**A numeric `unitPrice` is not a displayed price per measure.** The probe records
both separately and will not let one stand in for the other.

**Absence is a result.** A field that does not come back is reported absent rather
than inferred from a neighbouring value. Offer keys are probed and recorded either
way, because Walmart's promotional model is not Kroger's and the shared field
schema may not map onto it.

## What a pass does and does not mean

A pass means the fields exist and are collectable at this store for these items.
It does not establish category coverage, unattended operation, recovery, scheduled
execution, running cost at full volume, or the provider's terms of use. Those
remain separate questions.
