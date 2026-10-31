# Requirement 8: architecture, technologies and paid services

**No paid service was used for this collection.** It used the free Kroger public API. The
sweep's imports reach no storage, provider or cloud module, and the builder checks that. The output
is held on the operator's workstation, and nothing in the run records Azure execution.

## This collection

```
config/sweep_terms.json  301 terms across 28 roots
        |
tools/kroger_full_sweep.py
        |  OAuth client credentials, read from the environment
marianos_collector/kroger.py  ->  Kroger /locations, then /products
        |  raw response written first
marianos_collector/api_trial.py  observe: picks the qualifying pickup offer, classifies the rest
marianos_collector/schema.py  22 fields, brief's exclusions
config/category_map.json  the product's own label to a client root
marianos_collector/retention.py  reconcile, identity, carry-forward
        |
output folder: data, report, context, provenance, raw
```

A product's category comes only from its own Kroger label. The term that found it is recorded
in `data/discovery_provenance.json` and never decides the category.

## The production framework, not used here

`marianos_collector/runner.py` with `storage.py` publishes to local disk or Azure Blob Storage.
`azure/deploy_jobs.sh` creates one Azure Container Apps scheduled job per store, default Monday and
Thursday 06:00 UTC, and defaults to a dry run. Bounded API runs on Azure were carried out at another
store on earlier dates. **That is not evidence for this collection.**

`Dockerfile` copies `marianos_collector`, `config` and the entrypoint. It does not copy `tools/`, so the
sweep that made this data is not in the image and cannot run on Azure as it stands.

## Technologies

Python 3.12 in the image, standard library for collection; `azure-storage-blob` for Azure only;
Docker; Azure Container Apps Jobs; Azure Blob Storage; Kroger Products and Locations APIs (OAuth2).
Playwright is an optional tool for the page probe and is not used in collection.

## All services

| Service | Paid? | Used for this collection |
|---|---|---|
| Kroger public API | Free | Yes |
| Azure Container Apps | Metered, in the existing environment | No |
| Azure Blob Storage | Metered, in the existing environment | No |
| Azure logs, if enabled | Metered | No |
| Container registry | Depends on the registry | No |
| Bright Data | Paid, tried on earlier dates for other routes | No |
| Kroger Catalog V2 partner API | Unknown; access not granted | No |

The public tier is not the production route under Kroger's policy, as `README.md` records. A production
route for displayed PPM and deal wording does not exist yet, so its service cost is unknown.
