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
import textwrap
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Why each column that is blank is blank. Written out rather than summarised,
# because "unobtainable" and "unobtainable through every route open to us" are
# different sentences and only the second one is true.
# What each column is, NOT whether it is blank. The first version asserted
# blankness in the text while printing a populated count beside it, so the
# enriched build read "589 populated: blank on every record here". The count
# is the fact; the note explains the column.
COLUMN_NOTES = {
    "ppm": "The displayed price per measure, read from the retailer page. "
           "Never the API estimate.",
    "volume_deals_description": "Retailer volume offer wording, verbatim.",
    "volume_deals_price": "Never computed from a description.",
    "digital_deals_description": "Retailer digital coupon wording, verbatim.",
    "digital_deals_price": "Never computed.",
    "gupc": "Always empty by the brief.",
    "unit_price": "Always empty; the client's pipeline computes it.",
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


def P(text: str) -> str:
    """One paragraph, wrapped. This file is read by a client, so it is wrapped
    like prose rather than wherever the f-strings happened to break."""
    return textwrap.fill(text, width=79)


def B(text: str) -> str:
    """One bullet, wrapped with a hanging indent so the continuation lines sit
    under the text rather than under the dash."""
    return textwrap.fill(text, width=79, initial_indent="- ",
                         subsequent_indent="  ")


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
    p.add_argument("--enriched-from", type=Path, default=None,
                   help="A merge_page_enrichment output directory. Its enriched "
                        "data replaces the release data.json, and its merge "
                        "report and provenance ship beside it. The release "
                        "report and retention are still copied unchanged, "
                        "because they describe the collection that produced the "
                        "spine.")
    p.add_argument("--page-read-evidence", type=Path, default=None,
                   help="Optional. A file of page-read records from ANOTHER "
                        "store to ship BESIDE the release, never merged in.")
    p.add_argument("--include", action="append", default=[], type=Path,
                   help="A file or directory to ship in the package alongside "
                        "the release, copied under its own basename. Repeatable. "
                        "Used for artefacts that are not produced by the merge: "
                        "the out-of-scope reconciliation, the revision manifest "
                        "and change-to-test map, and the acquisition proposal. "
                        "Everything copied is picked up by MANIFEST_SHA256.json, "
                        "which is built by walking the output directory, so an "
                        "included file cannot ship unhashed.")
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

    merge_report = {}
    if a.enriched_from:
        enriched = next((a.enriched_from / n for n in
                         ("data_22_fields_enriched.json", "data_22_fields.json",
                          "data.json") if (a.enriched_from / n).is_file()), None)
        if enriched is None:
            raise SystemExit(f"No enriched data file under {a.enriched_from}")
        shutil.copy2(enriched, a.out / "data.json")
        for name in ("merge_report.json", "provenance.json"):
            if (a.enriched_from / name).is_file():
                shutil.copy2(a.enriched_from / name, a.out / name)
        # provenance.json is a summary with a capped preview; it names the file
        # that holds the complete per-field observations and refused
        # contributions. Shipping the summary without that file would leave the
        # package pointing at an artefact it does not contain.
        if (a.out / "provenance.json").is_file():
            named = json.loads((a.out / "provenance.json").read_text()).get(
                "complete_evidence_artifact")
            if named:
                if Path(named).name != named:
                    raise SystemExit(f"complete_evidence_artifact is not a bare file name: {named!r}")
                if not (a.enriched_from / named).is_file():
                    raise SystemExit(
                        f"provenance.json names {named} as its complete evidence, "
                        f"but {a.enriched_from} does not contain it")
                shutil.copy2(a.enriched_from / named, a.out / named)
        if (a.out / "merge_report.json").is_file():
            merge_report = json.loads((a.out / "merge_report.json").read_text())

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

    included = []
    for item in a.include:
        if item.is_dir():
            shutil.copytree(item, a.out / item.name, dirs_exist_ok=True)
            included.append(item.name + "/")
        elif item.is_file():
            shutil.copy2(item, a.out / item.name)
            included.append(item.name)
        else:
            raise SystemExit(f"--include path does not exist: {item}")

    enriched_note = []
    matched = merge_report.get("page_upcs_matched_in_api", 0) if merge_report else 0
    rated = (merge_report.get("fields_populated_after_merge", {}) or {}).get("ppm", 0)
    if merge_report:
        by_source = merge_report.get("values_by_field_and_source", {})
        # The read dates are taken from the merge report, never written here.
        # This said "on 1 November" as a literal, which was true of the first
        # merge and false the moment a second read was added: 202 of the
        # delivered values were observed on 3 November. A date in a
        # client-facing file is a claim, and it is read from the data.
        reads = merge_report.get("page_reads") or []
        if reads:
            when = [str(r.get("observed_at", ""))[:10] for r in reads]
            from_counts = merge_report.get(
                "products_whose_values_came_from_each_read") or {}
            read_phrase = (
                "on " + " and ".join(when) if len(when) > 1
                else "on " + when[0])
            per_read = "; ".join(
                f"{n:,} observed {str(k)[:10]}"
                for k, n in sorted(from_counts.items())) if from_counts else ""
        else:
            read_phrase = "in an attended page read"
            per_read = ""
        enriched_note = [
            "## Three columns came from a page read, not from the API",
            "",
            P("`ppm`, `volume_deals_description` and "
              "`digital_deals_description` are not in the Kroger public "
              f"Products API at any tier. They were read from the rendered "
              f"retailer pages at this store {read_phrase} and merged onto the "
              "API spine through the composition layer, which binds every "
              "contribution to the product, store, fulfilment and time it was "
              "observed at, and records per field which source supplied it."
              + (f" Values per read: {per_read}." if per_read else "")),
            "",
            f"- `ppm`: **{merge_report.get('fields_populated_after_merge', {}).get('ppm', 0)}** "
            f"records, all from the page read",
            f"- `volume_deals_description`: "
            f"**{merge_report.get('fields_populated_after_merge', {}).get('volume_deals_description', 0)}**",
            f"- `digital_deals_description`: "
            f"**{merge_report.get('fields_populated_after_merge', {}).get('digital_deals_description', 0)}**",
            "",
            P(f"**{matched - rated} of the matched products carry no rate.** "
              f"{matched:,} products on the pages read are in this dataset, and "
              f"{rated:,} of them have a price per measure, because not every "
              f"page displayed one. A product whose page showed no rate gets an "
              f"empty `ppm`; nothing is derived from its price and size."
              ) if matched and rated and matched > rated else "",
            "" if matched and rated and matched > rated else None,
            P(f"Of {merge_report.get('page_distinct_upcs', 0):,} distinct products "
              f"on the pages read, {merge_report.get('page_upcs_matched_in_api', 0):,} "
              f"are in this dataset and {merge_report.get('page_upcs_not_in_api', 0)} "
              f"are not, so those contributions were not used rather than being "
              f"attached to anything. Conflicts between the two sources: "
              f"**{merge_report.get('conflicts', 0)}**. Contributions refused as "
              f"unbindable: "
              f"**{sum((merge_report.get('refused_as_unbound') or {}).values()) or 0}**."),
            "",
            P("`provenance.json` carries the per-field record. "
              "`merge_report.json` carries the counts above. Neither is a "
              "summary written by hand."),
            "",
            P("**The remaining records have these three columns empty**, and "
              "the reasons are below. The page route covers what one attended "
              "session reached, not the assortment."),
            "",
        ]

    readme = [
        "# Mariano's submission, Vernon Hills",
        "",
        f"Release `{a.release}`, store `{a.store}`, "
        f"{len(records):,} records, {len(records[0]) if records else 0} fields.",
        "",
        "## What this is",
        "",
        P("A live collection from the Kroger public Products API at the "
          "assigned store, produced through the collector: it passed the "
          "publication gate, retention reconciliation and the store-usability "
          "gate, and the store columns were read from Kroger's own /locations "
          "response rather than from a config file."),
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
    ] + ([
        "- Nothing here has been merged with any earlier run or any other store.",
    ] if not merge_report else [
        B("The three page-read columns below come from a separate observation "
          "on a different date, at this same store. Nothing from any OTHER "
          "store has been merged in, and no earlier API run has been merged "
          "in."),
    ]) + [
        "",
    ] + enriched_note + [
        "## Column population, counted from the delivered file",
        "",
    ]
    for column, why in COLUMN_NOTES.items():
        count = populated.get(column, 0)
        state = f"**{count:,}** populated" if count else "empty on every record"
        readme.append(B(f"**`{column}`**, {state}. {why}"))
    readme += [
        "",
        (f"## Why the other {len(records) - populated.get('ppm', 0):,} records have no rate: "
         f"four routes, four reasons") if populated.get("ppm") else
        "## Why `ppm` and the deal columns are empty: four routes, four reasons",
        "",
        P("Not \"unobtainable\". Unobtainable through every route open to us, "
          "which is a different sentence."),
        "",
    ]
    for route, why in ROUTES_CLOSED.items():
        readme += [f"**{route}**", "", P(why), ""]
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
    if included:
        readme += ["## Also in this package", "",
                   P("Artefacts that are not output of the collection or the "
                     "merge, shipped alongside it. Each is covered by "
                     "`MANIFEST_SHA256.json` like everything else here."), ""]
        readme += [f"- `{name}`" for name in included]
        readme += [""]

    readme += ["## The two manifests", "",
               B("`manifest.json` is the release manifest the collector wrote: "
                 "the release id, the store, the record count and the storage "
                 "keys of the run that produced this."),
               B("`MANIFEST_SHA256.json` is the checksum of every file in this "
                 "folder, including the README, so the package can be verified "
                 "byte for byte."),
               "",
               "## Verifying", "",
               "```bash", "python3 -c \"",
               "import hashlib, json, pathlib",
               "m = json.load(open('MANIFEST_SHA256.json'))",
               "bad = [k for k, v in m.items() if not pathlib.Path(k).is_file()",
               "       or hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest() != v['sha256']]",
               "print('OK' if not bad else 'CHANGED: ' + ', '.join(bad))\"",
               "```", ""]
    (a.out / "README.md").write_text(
        "\n".join(line for line in readme if line is not None))

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
        "populated_counts": {k: v for k, v in populated.items() if k in COLUMN_NOTES},
        "built_utc": datetime.now(timezone.utc).isoformat(),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
