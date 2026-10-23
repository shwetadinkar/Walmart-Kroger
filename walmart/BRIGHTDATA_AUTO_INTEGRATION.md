# Walmart Bright Data API and Azure pipeline — v0.7.0

**Status:** Offline validated integration. Does not yet establish compliant store-local prices, direct PPM, live Azure execution or full-category proof.

## No manual collection/upload after setup

`Bright Data /trigger → snapshot ID → /progress → /snapshot → existing v0.6 importer → private Azure Blob history + exact 22-field JSON + sidecars`.

Entrypoint: `tools/brightdata_start.py` for Azure, `tools/brightdata_auto.py` for one-off or snapshot runs.

**Safe mode by default:** `BRIGHTDATA_JOB_MODE=dry-run`. No network call in `--dry-run` mode. `snapshot` mode downloads a real existing snapshot, no new trigger. `trigger` mode requires both `WALMART_DATA_AUTHORIZED=yes` and `BRIGHTDATA_COLLECTION_APPROVED=yes`, an approved category URL manifest, an approved positive `BRIGHTDATA_RECORD_CAP`, and the provider API token. It does not remove paid usage concerns; record-cap enforcement must be confirmed in the provider account.

Download prior snapshot, in an authorized environment:

```bash
export BRIGHTDATA_API_KEY='(provided securely by account owner)'
export AZURE_STORAGE_CONNECTION_STRING='(provided securely by account owner)'
python tools/brightdata_auto.py --snapshot-id s_THE_REAL_SNAPSHOT_ID
```

Preview the 11-category inputs without making calls:

```bash
python tools/brightdata_auto.py --trigger --inputs-csv config/brightdata_category_inputs.csv --max-records 10 --dry-run
```

Process/store from a new billed collection only with explicit authorization and provider spending cap:

```bash
export WALMART_DATA_AUTHORIZED=yes
export BRIGHTDATA_COLLECTION_APPROVED=yes
python tools/brightdata_auto.py --trigger --inputs-csv config/brightdata_category_inputs.csv --max-records 10
```

This is **a bounded pilot command**. A client-approved complete category/subcategory/page manifest and cost-estimated production collection are still outstanding. Avoid using the 11 broad URLs as proof of full-category coverage; some `/cp/` inputs have already failed to parse.

Please see `azure/BRIGHTDATA_AZURE_SETUP.md` and `azure/create_brightdata_manual_job.sh` for the manual-before-scheduled Azure rollout.

Historical retention: the Azure Blob `brightdata-trials/<store>/history.json` persists between container executions, and unobserved products remain stored with their original observed timestamps. Snapshot outputs are versioned. The production `published/<store>/latest.json` is NOT updated by this importer; only `brightdata-trials/<store>/latest-trial.json` is maintained.

**Network, billing and Azure not tested:** local tests mock Bright Data and Blob; genuine source response replay proves offline normalization, not that the client environment works.

To seed the initial 381 candidate products once in Azure, use `tools/seed_azure_history.py` and the **private** `processed_latest/history.json` from the earlier 381-product evidence archive. The uploader refuses to overwrite existing remote history. Never commit the evidence archive to public GitHub.
