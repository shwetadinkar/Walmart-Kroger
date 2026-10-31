# Mariano's Vernon Hills collection, 31 October 2026

Store 53100502, 1720 N Milwaukee Ave, Vernon Hills, IL 60061, PICKUP. Collected
from the Kroger public Products API on 31 October 2026 by
`source/tools/kroger_full_sweep.py`.

24,683 products, 24,683 distinct UPCs, 0 duplicate UPCs,
23 of the 28 client roots populated. `ppm`, `volume_deals_description` and
`digital_deals_description` are blank on every row.

**Status: a partial dataset.** It is real, store-verified API data. It has no
displayed PPM and no deal wording, and it does not attest category completeness.
It was not produced through the publication gate, and it was not run on Azure.
`DOES_NOT_ESTABLISH.md` states the limits; read it before using any count here.

**Acceptable use.** Kroger's Acceptable Use of Public APIs prohibits systematically
gathering response data to create a database, and prohibits comparing prices among
other retailers. This run was made with that policy known;
`data/run_report.json` records that decision. The position stated in
`source/marianos_collector/kroger.py` is that the public tier is not the production
route. Nothing in this package changes that position or settles what the policy permits.

## Contents

| Path | What it is |
|---|---|
| `CHECKLIST.md` | Each proof item in the brief, with the result or the gap |
| `DOES_NOT_ESTABLISH.md` | What this data cannot show |
| `R6_COMPLETENESS_AND_BLOCKING.md` | How completeness and silent blocking are detected |
| `R7_FAILED_RUN_PROTECTION.md` | How a failed run is kept from replacing good data |
| `R8_ARCHITECTURE_AND_SERVICES.md` | Architecture, technologies, paid services |
| `R9_OPERATING_COST.md` | Estimated monthly operating cost |
| `R10_EVIDENCE_OF_GENERATION.md` | What shows the collector produced this data |
| `data/` | The 22-field data and the run's records, byte for byte |
| `raw_index.json` | All 888 captures, 336,572,613 bytes in total, with hashes |
| `raw_sample/` | A rule-selected sample of those captures, `cid` masked |
| `source/` | The code and configuration the notes describe |
| `tools/` | The builder, which verifies this package from its own bytes |
| `MANIFEST_SHA256.json` | Every file's hash, the recomputed facts, and what was left out |

## Verifying

```bash
python3 tools/build_vernon_hills_package.py --verify .
```

This needs Python and this folder only. It rechecks every hash, recomputes every
stated figure from the bytes, reselects the sample and checks it, and fails if
anything disagrees. The identity scan needs a private deny-list, so without one
it reports `not run`.
