# Walmart contest #63 — reviewer quick start
**Submission date:** 24 October 2026  
**Scope:** Walmart Supercenter #100, 406 S Walton Blvd, Bentonville, AR 72712 (ZIP 72712)  
**Status:** **reviewable, partial/trial submission** — **not** a store-priced, fully acceptance-compliant production feed.

## Open these first

| Item | What it proves / contains |
|---|---|
| [615-product demonstration (JSON)](Walmart_Store100_615_Trial_22Field.json) | Genuine Bright Data source-derived **candidate** products; exactly ordered 22-string-field records, unique item URLs. Pricing / deal fields intentionally blank when unverified |
| [No-network offline validator](validate_submission.py) | Deterministic schema/order, store/ZIP, distinct URL and category representation checks |
| [Azure exported verification report](azure_blob_verification_20261023T215838Z.json) | Actual user-observed, **manual** Azure Container Apps Job invoked Python with system-assigned Managed Identity; fetched pre-uploaded JSON from private Blob, checked 615 rows, wrote a separate report. Result: `blob-smoke-no-provider`, `provider_api_called=false`; includes Azure-observed SHA-256 |
| [Filtering and source count audit](../../reports/WALMART_STORE100_20261024_FILTER_AUDIT.md) | Rejections, errors, duplicate policy, category counts, retained pickup-unavailable records; original provider data held privately |
| [Implementation and exact Azure reproduction steps](../../README.md) · [Managed Identity runbook](../../azure/MANAGED_IDENTITY_BLOB_TEST.md) | Current code, GHCR container build, cloud config and manual verification procedure; no secrets in the repository |

### Offline verification (from cloned repository root)
```bash
python walmart/submission/2026-10-24/validate_submission.py
cd walmart
python -m unittest discover -v tests
python tools/preflight.py
```
These tests do **not** call Bright Data or prove live category traversal.

## Acceptance requirement checklist

| Requirement | What actually happened |
|---|---|
| 500 genuine distinct assortment candidates | **615**, from 46 Bright Data JSON snapshots; 615 distinct URLs |
| Exact 22 fields | Verified both offline and by Azure Blob test |
| Correct target store, seller, category | Validated against **source response fields** by importer; no independent current-site store/price audit |
| Eleven required category roots | All eleven represented; exhaustive descendants/pages **unproven** |
| Out-of-stock retention | 144 last seen pickup-unavailable candidates retained, 471 pickup-available |
| Per-row provenance/rejection reasons | Available in private evidence archive; a public aggregate audit is provided |
| Local pickup regular/sale prices | **0 independently verified** — price fields blank |
| Directly displayed PPM | **0 independently verified** — PPM blank |
| Complete digital/volume deal evidence | **0 verified** — terms and prices blank |
| Actual Azure execution | **Yes:** Walmart Python image ran in a manual Container Apps Job, with console logs |
| Real Azure Blob programmatic read/write | **Yes:** Managed Identity read uploaded 615-row JSON, wrote timestamped verification report; see linked report |
| Provider API triggered in Azure | **No** — the Azure run was explicitly no-provider/no-network to Bright Data |
| Automatic future import and historical retention in Azure | Components implemented/offline tested; genuine provider-to-Azure run and original history migration **not performed** |
| Twice-weekly schedule and interruption recovery | **Not live-tested or enabled** |

## How the reviewer can evaluate the source evidence

The complete original Bright Data JSON snapshots, individual source-row hashes, detailed rejection ledger, observed pickup-availability history and collection manifests are **not checked into this public repository**. They are retained separately as private evidence, for access by arrangement under the provider's data-use permissions. The public JSON and aggregate counts **alone cannot prove every pickup price**.

**Azure proof location:** South India personal Free Trial, manual job `walmart63-collector` within `env-walmart63`, resource group `rg-walmart63-trial`, private storage `stwalmart63trial1024` / `retail-collection`. The actual evidence report in Azure is `brightdata-trials/100/azure-verification/runs/20261023T215838Z_610df5e2.json`. The exported copy is linked above. It has `checked_at_utc=2026-10-23T21:58:38.973778Z`.

**No secrets, cloud storage keys, or paid provider collection are exposed or enabled by this submission.** Outstanding source capability, complete category traversal and end-to-end production execution cannot be claimed complete or responsibly assigned an unconditional finish time without confirmed provider evidence/access, permissions and budget.
