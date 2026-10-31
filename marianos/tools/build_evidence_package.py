"""Build the corrected Mariano's evidence package from the 28 October originals.

Originals are copied byte for byte and never edited. Every statement the notes
make about them is recomputed here, and a build that cannot establish one is
refused rather than written. The output belongs in a gitignored folder: the page
files carry Kroger cid tracking parameters.

Identity strings come from a gitignored deny-list, so that the check does not
publish what it refuses. It reads bytes, so it cannot see text inside an image:
the screenshots known to show an account are refused unless withheld by name.
`--verify` recomputes everything from a built package alone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote_to_bytes

AZURE, BATTERIES, PROMOTION = "azure_recovery", "batteries_reference", "promotion_correction"
COUPON = "coupon_source"
COUPON_SAMPLE = "EXACT_UPC_TWO_PRODUCT_SAMPLE.json"
CHECKPOINT = "RESUMED_PAGE_ORIGINAL.json"
FRESH_PAGE = "FRESH_PAGE_ORIGINAL.json"
SELECTED = ("EARLIER_SELECTED_5.json", "FRESH_SELECTED_5.json")
NOTES = ("README.md", "RESULTS.md", "C0_PROMOTION_IDENTITY.md", "C2_COUPON_SOURCE.md",
         "C4_BLOCKED_SOURCE_CHRONOLOGY.md",
         "C5_RESULT_SEPARATION.md")
WITHHOLD_REASON = "portal screenshot showing account-identifying details"
ACCOUNT_IDENTITY = ("RESTORED_CONTAINER.png", "RESTORED_OVERVIEW.png",
                    "TEMPORARY_CONFIG_PENDING_ROLLBACK.png")
SUPERSEDED = {
    f"{COUPON}/EXACT_UPC_22_FIELD_SAMPLE.json": "superseded by EXACT_UPC_TWO_PRODUCT_SAMPLE.json",
    f"{COUPON}/LOCAL_NORMALIZER_FIX.patch": "historical; the fix is in release 16a6f03",
    f"{COUPON}/VALIDATION.json": "historical; figures of 28 October",
    f"{AZURE}/RESULTS.md": "superseded by RESULTS.md at the package root",
    f"{AZURE}/MANIFEST_SHA256.json": "unchanged 28 October manifest; the files it lists "
                                     "that are absent are the ones declared under withheld",
    f"{BATTERIES}/PRODUCTS_34_PARTIAL.json": "superseded by PRODUCTS_34_PARTIAL_V2.json",
    f"{BATTERIES}/PROVENANCE_34.json": "superseded by PROVENANCE_34_V2.json",
    f"{BATTERIES}/VALIDATION.json": "superseded by V2_VALIDATION.json",
}
DERIVED = {f"{AZURE}/{name}": "derived; the independent evidence is the two page files"
           for name in SELECTED}
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:json|md|txt|png|csv|zip)\b")
_ADDRESS = re.compile(r"(?:https?://|www\.)[^\s\"')]+")
_TEXT = (".md", ".txt", ".json")


class PackageRefused(RuntimeError):
    pass


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_folder(folder):
    """The folder must be exactly what its own manifest declares."""
    declared = json.loads((folder / "MANIFEST_SHA256.json").read_text(encoding="utf-8"))
    present = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    present.discard("MANIFEST_SHA256.json")
    if set(declared) != present:
        raise PackageRefused(f"{folder.name}: manifest and files disagree: "
                             f"{sorted(set(declared) ^ present)}")
    for name, digest in declared.items():
        if sha256(folder / name) != digest:
            raise PackageRefused(f"{folder.name}: {name} does not match its manifest hash")
    return sorted(present) + ["MANIFEST_SHA256.json"]


def _value_changes(earlier, fresh, path=""):
    if isinstance(earlier, dict) and isinstance(fresh, dict) and set(earlier) == set(fresh):
        for key in earlier:
            yield from _value_changes(earlier[key], fresh[key], f"{path}/{key}")
    elif isinstance(earlier, list) and isinstance(fresh, list) and len(earlier) == len(fresh):
        for a, b in zip(earlier, fresh):
            yield from _value_changes(a, b, f"{path}[]")
    elif earlier != fresh:
        yield path, len(json.dumps(earlier)), len(json.dumps(fresh))


def compare_pages(azure):
    earlier_raw = (azure / CHECKPOINT).read_bytes()
    fresh_raw = (azure / FRESH_PAGE).read_bytes()
    earlier, fresh = json.loads(earlier_raw), json.loads(fresh_raw)
    if earlier["observed_at"] == fresh["observed_at"]:
        raise PackageRefused("The two page files are not independent observations")
    ids = [[row["productId"] for row in page["response"]["data"]] for page in (earlier, fresh)]
    by_id = {row["productId"]: row for row in fresh["response"]["data"]}
    changes = [change for row in earlier["response"]["data"]
               for change in _value_changes(row, by_id.get(row["productId"]))]
    changes += list(_value_changes(earlier["response"]["meta"], fresh["response"]["meta"]))
    width_preserved = all(a == b for _, a, b in changes)
    same_size = len(earlier_raw) == len(fresh_raw)
    if same_size and not (set(ids[0]) == set(ids[1]) and width_preserved):
        raise PackageRefused("Equal size is not explained by the page contents")
    fields = {}
    for path, _, _ in changes:
        fields[path] = fields.get(path, 0) + 1
    return {"same_size_bytes": len(earlier_raw) if same_size else None,
            "earlier_observed_at": earlier["observed_at"],
            "fresh_observed_at": fresh["observed_at"],
            "bytes_identical": earlier_raw == fresh_raw, "same_product_set": set(ids[0]) == set(ids[1]),
            "same_product_order": ids[0] == ids[1], "products": len(ids[0]),
            "earlier_total": earlier["response"]["meta"]["pagination"]["total"],
            "fresh_total": fresh["response"]["meta"]["pagination"]["total"],
            "changed_values_by_field": fields,
            "every_changed_value_keeps_its_width": width_preserved}


def compare_selected(azure):
    a, b = (azure / SELECTED[0]).read_bytes(), (azure / SELECTED[1]).read_bytes()
    if a != b:
        raise PackageRefused("The selected files are no longer byte-identical")
    return {"byte_identical": True, "sha256": hashlib.sha256(a).hexdigest()}


def check_azure(azure):
    status = json.loads((azure / "STATUS.json").read_text(encoding="utf-8"))
    digest = sha256(azure / CHECKPOINT)
    if status["checkpoint_sha256"] != digest:
        raise PackageRefused("The checkpoint does not match the hash in STATUS.json")
    return {"bytes": (azure / CHECKPOINT).stat().st_size, "sha256": digest}


def check_batteries(batteries):
    blocked = json.loads((batteries / "BLOCKED_SOURCE.json").read_text(encoding="utf-8"))
    products = list((batteries / "products").glob("*.json"))
    pending = json.loads((batteries / "PENDING_61_URLS.json").read_text(encoding="utf-8"))
    stated = blocked["last_successful_product_count"] + blocked["remaining_discovered_urls"]
    if stated != len(products) + len(pending):
        raise PackageRefused("The refusal record and the final set cover different URLs")
    blocked_id = blocked["url"].split("?")[0].rsplit("/", 1)[-1]
    if not any(blocked_id in str(url) for url in pending):
        raise PackageRefused("The blocked product is not among the pending URLs")
    provenance = json.loads((batteries / "PROVENANCE_34_V2.json").read_text(encoding="utf-8"))
    entries = provenance if isinstance(provenance, list) else list(provenance.values())
    recovered = [e for e in entries
                 if isinstance(e, dict) and e.get("weight_reference") == "LISTING_03.txt"]
    return {"products_captured": len(products), "urls_pending": len(pending),
            "refusal_record_products": blocked["last_successful_product_count"],
            "refusal_record_remaining": blocked["remaining_discovered_urls"],
            "sizes_recovered_from_listing_03": len(recovered),
            "listing_03_bytes": (batteries / "LISTING_03.txt").stat().st_size,
            "listing_03_sha256": sha256(batteries / "LISTING_03.txt")}


def check_coupon(coupon, batteries):
    """The sample stays West Loop, computes no price, and is compared where it
    overlaps the Batteries set, so a disagreement is recorded, not resolved."""
    sample = json.loads((coupon / COUPON_SAMPLE).read_text(encoding="utf-8"))
    if not sample or any("West Loop" not in row["store_name"] for row in sample):
        raise PackageRefused("The coupon sample must stay labelled West Loop")
    if any(row["digital_deals_price"] for row in sample):
        raise PackageRefused("The coupon sample states a digital price nobody displayed")
    others = {row["upc"]: row for row in json.loads(
        (batteries / "PRODUCTS_34_PARTIAL_V2.json").read_text(encoding="utf-8"))}
    disagreements = []
    for row in sample:
        other = others.get(row["upc"])
        for field in sorted(row) if other else ():
            if row[field] != other[field]:
                disagreements.append({
                    "upc": row["upc"], "field": field,
                    "whitespace_only": row[field].split() == other[field].split()})
    return {"sample_records": len(sample), "sample_upcs": sorted(r["upc"] for r in sample),
            "shared_with_batteries": sorted(set(others) & {r["upc"] for r in sample}),
            "field_disagreements": disagreements}


def check_fixture(path):
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    if fixture.get("expiry_discrepancy_resolved") is not False:
        raise PackageRefused("The expiry discrepancy must stay unresolved")
    if fixture.get("coupon_source_upc") in fixture.get("retained_output_upcs", ()):
        raise PackageRefused("The coupon source must not be a retained product")
    return fixture


def read_denylist(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    strings = [line.strip().lower() for line in lines
               if line.strip() and not line.lstrip().startswith("#")]
    if not strings:
        raise PackageRefused("The identity deny-list is empty, so it would check nothing")
    return strings


def identity_hits(paths, denylist):
    """Names of files holding a denied string, plain, URL-encoded or UTF-16."""
    hits = []
    for path in paths:
        decoded = unquote_to_bytes(Path(path).read_bytes()).lower()
        needles = [text.encode("utf-8") for text in denylist]
        needles += [text.encode("utf-16-le") for text in denylist]
        if any(needle in decoded for needle in needles):
            hits.append(Path(path).name)
    return sorted(hits)


def absent_references(root, withheld=()):
    """File names in any text file that no file in the package has.

    A nested 28 October manifest is an unchanged original, so it still names what
    has been withheld. There only, and only for files the root manifest declares
    withheld, that is a labelled gap rather than a dangling reference.
    """
    names = {p.name for p in root.rglob("*") if p.is_file()}
    names.add("MANIFEST_SHA256.json")
    declared = {Path(name).name for name in withheld}
    absent = {}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in _TEXT:
            name = path.relative_to(root).as_posix()
            if name == "MANIFEST_SHA256.json":
                continue
            text = _ADDRESS.sub(" ", path.read_text(encoding="utf-8", errors="replace"))
            missing = set(_REFERENCE.findall(text)) - names
            if name.endswith("/MANIFEST_SHA256.json"):
                missing -= declared
            if missing:
                absent[name] = sorted(missing)
    return absent


def _flat(text):
    return " ".join(text.split())


def note_requirements(facts):
    """Values each note must state, taken from the bytes, not from memory."""
    pages, checkpoint, batteries = facts["page_files"], facts["checkpoint"], facts["batteries"]
    date_changes = pages["changed_values_by_field"].get(
        "/items[]/price/effectiveDate/value", 0)
    return {
        "RESULTS.md": [
            f"{checkpoint['bytes']:,} bytes", checkpoint["sha256"],
            pages["earlier_observed_at"][11:26], pages["fresh_observed_at"][11:26],
            f"same {pages['products']} products", f"{date_changes} `effectiveDate` values",
            f"({pages['earlier_total']}, then {pages['fresh_total']})",
            f"{batteries['listing_03_bytes']:,} bytes", batteries["listing_03_sha256"],
            "byte-identical", "withheld because they show account-identifying details"],
        "C4_BLOCKED_SOURCE_CHRONOLOGY.md": [
            f"{batteries['refusal_record_products']} successful products and "
            f"{batteries['refusal_record_remaining']} remaining",
            f"{batteries['products_captured']} products and "
            f"{batteries['urls_pending']} pending",
            f"{batteries['products_captured'] + batteries['urls_pending']} discovered URLs"],
        "C0_PROMOTION_IDENTITY.md": ["`expiry_discrepancy_resolved` is `false`"],
        "C2_COUPON_SOURCE.md": facts["coupon"]["sample_upcs"]
        + [f"{facts['coupon']['sample_records']} records"]
        + [f"`{d['upc']}` differs in `{d['field']}`"
           + (", in whitespace only" if d["whitespace_only"] else "")
           for d in facts["coupon"]["field_disagreements"]],
        "README.md": ["cid"],
    }


def check_notes(notes, facts):
    for name, required in note_requirements(facts).items():
        text = _flat((Path(notes) / name).read_text(encoding="utf-8"))
        missing = [item for item in required if _flat(item) not in text]
        if missing:
            raise PackageRefused(f"{name} does not state: {missing}")


def recompute(azure, batteries, coupon, fixture):
    return {"checkpoint": check_azure(azure), "page_files": compare_pages(azure),
            "selected_files": compare_selected(azure),
            "batteries": check_batteries(batteries),
            "coupon": check_coupon(coupon, batteries),
            "promotion": {"expiry_discrepancy_resolved":
                          check_fixture(fixture)["expiry_discrepancy_resolved"]}}


def describe(root, statements, withheld):
    entries = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        name = path.relative_to(root).as_posix()
        if name == "MANIFEST_SHA256.json":
            continue
        raw = path.read_bytes()
        cids = raw.count(b"cid=")
        entries.append({
            "path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "origin": "written 2026-10-31" if name in NOTES else "original, unchanged",
            "status": SUPERSEDED.get(name) or DERIVED.get(name) or "current",
            **({"cid_parameters": cids} if cids else {}),
        })
    return {"package": "marianos-evidence-2026-10-31", "files": len(entries),
            "self": "MANIFEST_SHA256.json lists every other file and cannot hash itself",
            "statements_recomputed_from_the_bytes": statements,
            "withheld": withheld, "entries": entries}


def build(azure, batteries, coupon, fixture, notes, output, denylist, withhold=()):
    azure, batteries, coupon, notes, output = map(Path, (azure, batteries, coupon, notes, output))
    if output.exists() and any(output.iterdir()):
        raise PackageRefused(f"{output} is not empty")
    denied = read_denylist(denylist)
    withhold = set(withhold)
    folders = {AZURE: azure, BATTERIES: batteries, COUPON: coupon}
    files = {target: verify_folder(folder) for target, folder in folders.items()}
    every = {name for names in files.values() for name in names}
    unknown = withhold - every
    if unknown:
        raise PackageRefused(f"Asked to withhold files that do not exist: {sorted(unknown)}")
    exposed = set(ACCOUNT_IDENTITY) & every - withhold
    if exposed:
        raise PackageRefused(f"Must be withheld, they show an account: {sorted(exposed)}")
    plan = [(folders[target] / n, output / target / n)
            for target, names in files.items() for n in names if n not in withhold]
    plan.append((Path(fixture), output / PROMOTION / "IDENTITY_FIXTURE.json"))
    plan += [(notes / n, output / n) for n in NOTES]
    # Before anything is written, so a refusal leaves no copy behind.
    hits = identity_hits([source for source, _ in plan], denied)
    if hits:
        raise PackageRefused(f"Files containing identity strings: {hits}")
    statements = recompute(azure, batteries, coupon, fixture)
    check_notes(notes, statements)
    for source, destination in plan:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if sha256(destination) != sha256(source):
            raise PackageRefused(f"{destination.name} did not copy exactly")
    held = [{"path": f"{target}/{name}", "bytes": (folders[target] / name).stat().st_size,
             "sha256": sha256(folders[target] / name), "reason": WITHHOLD_REASON}
            for target, names in files.items() for name in names if name in withhold]
    absent = absent_references(output, [item["path"] for item in held])
    if absent:
        shutil.rmtree(output)
        raise PackageRefused(f"References to absent files: {absent}")
    manifest = describe(output, statements, held)
    (output / "MANIFEST_SHA256.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                                 encoding="utf-8")
    return manifest


def verify(output, denylist):
    """Recompute everything from the package alone. Returns the facts checked."""
    output = Path(output)
    manifest = json.loads((output / "MANIFEST_SHA256.json").read_text(encoding="utf-8"))
    listed = {entry["path"]: entry for entry in manifest["entries"]}
    present = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    present.discard("MANIFEST_SHA256.json")
    if set(listed) != present:
        raise PackageRefused(f"Manifest and files disagree: {sorted(set(listed) ^ present)}")
    for name, entry in listed.items():
        if sha256(output / name) != entry["sha256"]:
            raise PackageRefused(f"{name} does not match the manifest")
        if (output / name).stat().st_size != entry["bytes"]:
            raise PackageRefused(f"{name} is not the size the manifest states")
    held = [item["path"] for item in manifest["withheld"]]
    if any(name in present for name in held):
        raise PackageRefused("A withheld file is present")
    if set(ACCOUNT_IDENTITY) & {Path(name).name for name in present}:
        raise PackageRefused("A screenshot showing an account is present")
    hits = identity_hits([output / name for name in present] + [output / "MANIFEST_SHA256.json"],
                         read_denylist(denylist))
    if hits:
        raise PackageRefused(f"Files containing identity strings: {hits}")
    azure, batteries, coupon = output / AZURE, output / BATTERIES, output / COUPON
    for folder in (azure, batteries, coupon):
        declared = json.loads((folder / "MANIFEST_SHA256.json").read_text(encoding="utf-8"))
        for name, digest in declared.items():
            if f"{folder.name}/{name}" in held:
                continue
            if sha256(folder / name) != digest:
                raise PackageRefused(f"{name} no longer matches its 28 October hash")
    facts = recompute(azure, batteries, coupon, output / PROMOTION / "IDENTITY_FIXTURE.json")
    if facts != manifest["statements_recomputed_from_the_bytes"]:
        raise PackageRefused("The manifest's statements do not recompute from the bytes")
    check_notes(output, facts)
    absent = absent_references(output, held)
    if absent:
        raise PackageRefused(f"References to absent files: {absent}")
    return {"files_verified": len(present), "withheld": len(held), "statements": facts}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--identity-denylist", required=True)
    p.add_argument("--verify", help="Check a built package and build nothing")
    for name in ("--azure", "--batteries", "--coupon", "--identity-fixture", "--notes",
                 "--output"):
        p.add_argument(name)
    p.add_argument("--withhold", action="append", default=[],
                   help="File name to leave out, recorded in the manifest. Repeatable.")
    args = p.parse_args(argv)
    try:
        if args.verify:
            result = verify(args.verify, args.identity_denylist)
        else:
            sources = (args.azure, args.batteries, args.coupon, args.identity_fixture,
                       args.notes, args.output)
            if not all(sources):
                p.error("A build needs --azure --batteries --coupon --identity-fixture "
                        "--notes --output")
            manifest = build(*sources, args.identity_denylist, args.withhold)
            result = {"files": manifest["files"], "withheld": len(manifest["withheld"]),
                      "statements": manifest["statements_recomputed_from_the_bytes"]}
    except PackageRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
