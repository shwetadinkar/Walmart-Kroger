# Mariano's Vernon Hills, addendum of 2 November 2026

This is not a new dataset. It is the material requested in the review of
2 November, added to the package of 1 November, which is unchanged and still
stands. Store 53100502, 1720 N Milwaukee Ave, Vernon Hills, IL 60061, pickup.

Three things were asked for by name, and they are the first three below.

| Path | What it is |
|---|---|
| `coverage-reconciliation/` | All 28 required roots, the Kroger labels that produced each, the five empty roots with the reason, and the page limits that bound the whole thing |
| `sold-by-weight/` | Every product the retailer itself prices by weight or variably, with the API observation and the page observation side by side for review |
| `provenance/` | Which source supplied each field after the merge, the merge counts, and the store resolved against Kroger's Locations API |
| `PRODUCTION_ROUTE.md` | Which route is actually executable, what it depends on, and the exact commands |
| `separated-evidence/` | The five evidence claims kept apart rather than mixed |

Every figure in these was recomputed from the data before being written. None
was carried over from an earlier document.

## The two findings in here that are against us

**The approximate-weight exclusion cannot see a whole class of product.** Of 34
delivered products the retailer prices by weight or variably, it catches none.
The rule is not broken: it reads the title and the weight field, which is the
right test. The Kroger API reports a clean `1 lb` on 31 of them while the page
says `about $1.45 each`, so there is nothing to match. All 34 are listed with
both observations. Nothing has been removed, because removing delivered rows
is your decision and not ours to take on our own reading of the rule.

**Interruption and recovery is narrower than earlier notes implied.** The
observed Azure trial of 28 October was at West Loop, on a five-product
selection of the single term `milk`. It is not evidence of recovery at
26,166-record scale or at this store. Separating the five claims is what made
that visible, which is why it was worth doing.

## What none of this changes

Coverage is still bounded: 69 of 301 terms hit the 300-result ceiling the
public API imposes, so there were more products behind those terms than were
fetched. Term-filtered search still cannot attest complete category discovery.
`publication_eligible` is still false, and the acceptable-use question in
`ACCEPTABLE_USE_POSITION.md`, shipped with the 1 November package, is still
open.

## Verifying

```bash
python3 verify.py
```

Needs Python and this folder. It rechecks every file against
`MANIFEST_SHA256.json` and fails if anything has changed, is missing, or is
present without being listed.
