#!/usr/bin/env python3
"""Assemble the Mariano's submission from a release the runner produced.

Reads a release out of the collector's own output tree and copies it, with its
report and its retention record, into a dated submission folder with a SHA-256
manifest. It composes nothing, recomputes nothing and merges nothing.

Three things it will not do, each because doing it would misrepresent the work:

- **It will not relabel the release.** `coverage_scope: subset_trial` and
  `source_coverage_attested: false` are the runner refusing to call a
  term-swept dataset a complete catalogue. That refusal is correct and travels
  into the submission unchanged. A package that looks finished because the
  honest labels were edited out is worse than a package with blanks in it.
- **It will not merge the page-read evidence into the release.** The 604 West
  Loop records with page-read `ppm`, and the 34 Batteries products, are a
  different store on a different date. They ship beside the release, labelled,
  or not at all. This repository has already published one store's data under
  another store's name once.
- **It will not fill a blank column.** `ppm` and the four deal columns are
  empty in this release because no route open to us returns them, and the
  README says which four routes and why each is closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Why each column that is blank is blank. Written out rather than summarised,
# because "unobtainable" and "unobtainable through every route open to us" are
# different sentences and only the second one is true.
BLANK_COLUMNS = {
    "ppm": "The displayed price per measure. Blank on every record here.",
    "volume_deals_description": "Retailer volume offer wording. Blank.",
    "volume_deals_price": "Blank; never computed from a description.",
    "digital_deals_description": "Retailer digital coupon wording. Blank.",
    "digital_deals_price": "Blank; never computed.",
    "gupc": "Always blank by the brief.",
    "unit_price": "Always blank; the client's pipeline computes it.",
    "store_logo": "Kroger's /locations response does not supply one.",
}

ROUTES_CLOSED = {
    "kroger_public_products_api": (
        "Carries no displayed rate at all. It has regularPerUnitEstimate, "
        "which is an estimate, and the brief forbids writing an estimate into "
        "ppm. This is the route the 28,549 records came from."),
    "retailer_pages_direct": (
        "Our datacenter egress is refused. Measured from two Azure regions and "
        "a second cloud provider on 30 October, and a plain curl of the "
        "sitemap on 2 November, all refused before any HTTP exchange."),
    "oxylabs": (
        "Reaches the fields. Not used: its dedicated Marianos endpoint has no "
        "vendor parser (OPTIONS returns html, markdown, screenshot and an "
        "LLM-parsed json against a schema we supply), so it delivers the same "
        "page our egress is refused. That is a decision for the client with "
        "his own counsel, not one to take here."),
    "bright_data": (
        "The provider states in writing on ticket #754403 that displayed price "
        "per measure and digital coupon fields are returned when publicly "
        "shown for the product and the selected store. It cannot resolve the "
        "store: zip_code 60061 returns bad_input, 'No Kroger pickup store "
        "found for zip code 60061', retested 3 November. Open with their R&D."),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_release(output_root: Path, namespace: str, store: str, release: str):
    base = output_root / namespace / store / "runs" / release
    if not base.is_dir():
        raise SystemExit(
            f"{base} not found. Pass --output-root, --namespace, --store and "
            f"--release to match the run. The release id is in the manifest the "
            f"run printed.")
    return base


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--output-root", type=Path,
                   default=ROOT / "out/sweep-vernon-hills-2026-11-03")
    p.add_argument("--namespace", default="trials/977820156bbc")
    p.add_argument("--store", default="53100502")
    p.add_argument("--release", required=True,
                   help="Release id, e.g. 20261103T175940Z_426c12e8")
    p.add_argument("--out", type=Path,
                   default=ROOT / "submission/2026-11-04-vernon-hills")
    p.add_argument("--page-read-evidence", type=Path, default=None,
                   help="Optional. A file of West Loop page-read records to "
                        "ship BESIDE the release, never merged into it.")
    a = p.parse_args(argv)

    base = find_release(a.output_root, a.namespace, a.store, a.release)
    a.out.mkdir(parents=True, exist_ok=True)

    copied = {}
    for name in ("data.json", "report.json", "retention.json", "manifest.json"):
        source = base / name
        if source.is_file():
            shutil.copy2(source, a.out / name)
            copied[name] = source
    if "data.json" not in copied:
        raise SystemExit(f"No data.json under {base}")

    records = json.loads((a.out / "data.json").read_text())
    report = json.loads((a.out / "report.json").read_text()) if (
        a.out / "report.json").is_file() else {}

    # Counted from the delivered file itself, never carried from the run log.
    populated = {}
    if records:
        for column in records[0]:
            populated[column] = sum(1 for r in records if str(r.get(column, "")).strip())

    beside = ""
    if a.page_read_evidence and a.page_read_evidence.is_file():
        beside = "page-read-evidence-west-loop.json"
        shutil.copy2(a.page_read_evidence, a.out / beside)

    readme = [
        "# Mariano's submission, Vernon Hills",
        "",
        f"Release `{a.release}`, store `{a.store}`, "
        f"{len(records)} records, {len(records[0]) if records else 0} fields.",
        "",
        "## What this is",
        "",
        "A live collection from the Kroger public Products API at the assigned",
        "store, produced through the collector: it passed the publication gate,",
        "retention reconciliation and the store-usability gate, and the store",
        "columns were read from Kroger's own /locations response rather than",
        "from a config file.",
        "",
        "## What this is not",
        "",
        f"- `coverage_scope` is **{report.get('coverage_scope', 'subset_trial')}** and",
        f"  `source_coverage_attested` is **{report.get('source_coverage_attested', False)}**.",
        "  Those labels are the collector refusing to call this a complete",
        "  catalogue, and they are left exactly as it set them. Term-filtered",
        "  search cannot enumerate a category: `filter.start` is a skip count",
        "  Kroger refuses past 250, so one term reaches at most 300 products.",
        "- Splitting capped terms into narrower ones was tried on 3 November. It",
        "  added 10.3 percent more products and the count of terms hitting the",
        "  ceiling went from 68 to 114, so the ceiling is structural rather than",
        "  something more terms reach past.",
        "- Nothing here has been merged with any earlier run or any other store.",
        "",
        "## Columns that are blank, and why",
        "",
    ]
    for column, why in BLANK_COLUMNS.items():
        readme.append(f"- **`{column}`** ({populated.get(column, 0)} populated): {why}")
    readme += [
        "",
        "## Why `ppm` and the deal columns are blank: four routes, four reasons",
        "",
        "Not \"unobtainable\". Unobtainable through every route open to us, which",
        "is a different sentence.",
        "",
    ]
    for route, why in ROUTES_CLOSED.items():
        readme += [f"**{route}**", "", why, ""]
    if beside:
        readme += [
            "## The page-read evidence beside this",
            "",
            f"`{beside}` holds records with a real page-read `ppm`, observed on the",
            "retailer's own rendered pages. **They are West Loop `53100508`, a",
            "different store on a different date, and they are not merged into the",
            "release.** They are included because they are the only records in this",
            "engagement where the displayed rate was actually observed, and they",
            "show what the field looks like when the route to it is open.",
            "",
        ]
    readme += ["## Verifying", "",
               "```bash", "python3 -c \"",
               "import hashlib, json, pathlib",
               "m = json.load(open('MANIFEST_SHA256.json'))",
               "bad = [k for k, v in m.items() if not pathlib.Path(k).is_file()",
               "       or hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest() != v['sha256']]",
               "print('OK' if not bad else 'CHANGED: ' + ', '.join(bad))\"",
               "```", ""]
    (a.out / "README.md").write_text("\n".join(readme))

    manifest = {}
    for path in sorted(a.out.rglob("*")):
        if path.is_file() and path.name != "MANIFEST_SHA256.json":
            manifest[str(path.relative_to(a.out))] = {
                "sha256": sha256(path), "bytes": path.stat().st_size}
    (a.out / "MANIFEST_SHA256.json").write_text(json.dumps(manifest, indent=1) + "\n")

    print(json.dumps({
        "submission": str(a.out),
        "release": a.release,
        "records": len(records),
        "files": sorted(manifest),
        "populated_counts": {k: v for k, v in populated.items() if k in BLANK_COLUMNS},
        "built_utc": datetime.now(timezone.utc).isoformat(),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
