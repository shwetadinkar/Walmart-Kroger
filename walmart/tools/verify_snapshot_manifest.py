"""Verify archived provider snapshots against a recorded SHA-256 manifest.

Offline only. Makes no retailer, provider or cloud request. Run this before
rebuilding any ledger from the snapshots, so a ledger is never built on inputs
that have been altered since they were archived.

Manifest formats accepted
-------------------------
Distributed packages redact unrelated customer-review content from the provider
responses, so a package records two hashes per file: ``original_sha256`` for the
untouched download and ``redacted_sha256`` for the copy actually shipped. This
tool verifies the files it is given, so it prefers ``redacted_sha256`` when the
manifest carries one and falls back to ``sha256``.

  {"files":     [{"file": ..., "redacted_sha256": ..., "original_sha256": ...}]}
  {"originals": [{"file": ..., "sha256": ...}]}
  [{"file": ..., "sha256": ...}]

An empty or unrecognised manifest is an error, not a pass.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

HASH_KEYS = ("redacted_sha256", "sha256", "original_sha256")


class ManifestError(Exception):
    """The manifest cannot be interpreted, so nothing can be verified."""


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_entries(manifest):
    """Return (entries, hash_key, declared_count).

    Raises ManifestError rather than verifying nothing, or verifying only the
    part of a manifest it happens to understand.
    """
    if isinstance(manifest, list):
        entries = manifest
    elif isinstance(manifest, dict):
        for container in ("files", "originals", "entries"):
            if isinstance(manifest.get(container), list):
                entries = manifest[container]
                break
        else:
            raise ManifestError(
                "Unrecognised manifest: expected a list, or an object with a "
                "'files' or 'originals' list. Found keys: "
                + (", ".join(sorted(manifest)) or "none"))
    else:
        raise ManifestError(f"Unrecognised manifest of type {type(manifest).__name__}")

    # Every declared entry must be checkable. Filtering the bad ones out and
    # verifying the remainder let a manifest containing one good entry and one
    # malformed entry exit 0, reporting a clean pass over a file set that was
    # never fully examined. A manifest that declares something this tool cannot
    # check is a manifest this tool cannot vouch for.
    declared = len(entries)
    malformed = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            malformed.append(f"entry {index}: expected an object, found {type(entry).__name__}")
        elif not entry.get("file"):
            malformed.append(f"entry {index}: no file name")
        elif not isinstance(entry["file"], str):
            # Without this the entry survived the scan and then raised TypeError
            # on `snapshots / entry["file"]`, surfacing as exit 1 ("files were
            # altered") rather than exit 2 ("this manifest is unverifiable").
            malformed.append(
                f"entry {index}: file name must be text, found "
                f"{type(entry['file']).__name__}")
        elif ".." in Path(str(entry["file"])).parts or Path(str(entry["file"])).is_absolute():
            malformed.append(f"entry {index}: file name escapes the snapshot directory")
    if malformed:
        raise ManifestError(
            f"Manifest declares {declared} entries and {len(malformed)} cannot be "
            "verified, so no clean result can be reported: " + "; ".join(malformed[:10])
            + ("; ..." if len(malformed) > 10 else ""))
    if not entries:
        raise ManifestError("Manifest lists no files, so there is nothing to verify")

    for key in HASH_KEYS:
        if all(e.get(key) for e in entries):
            # The file NAME was type-checked above but the hash VALUE was not,
            # so {"sha256": 12345} reached the comparison and raised TypeError,
            # surfacing as exit 1 ("files were altered") rather than exit 2
            # ("this manifest is unverifiable"). {"sha256": ["x"]} was worse: it
            # compared cleanly against nothing and was reported as ALTERED.
            bad = [f"entry {i}: {key} must be text, found {type(e[key]).__name__}"
                   for i, e in enumerate(entries) if not isinstance(e[key], str)]
            if bad:
                raise ManifestError(
                    f"Manifest declares {declared} entries and {len(bad)} carry an "
                    "unusable hash value: " + "; ".join(bad[:10])
                    + ("; ..." if len(bad) > 10 else ""))
            return entries, key, declared
    without = [str(e.get("file")) for e in entries if not any(e.get(k) for k in HASH_KEYS)]
    present = sorted({k for e in entries for k in e if k.endswith("sha256")})
    raise ManifestError(
        "No hash field is present on every entry. Looked for "
        + ", ".join(HASH_KEYS) + "; entries carry: " + (", ".join(present) or "none")
        + ("; entries with no hash at all: " + ", ".join(without[:5]) if without else ""))


def verify(snapshots: Path, manifest_path: Path):
    if not manifest_path.is_file():
        raise ManifestError(f"Manifest not found: {manifest_path}")
    if not snapshots.is_dir():
        raise ManifestError(f"Snapshot directory not found: {snapshots}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ManifestError(f"Manifest is not valid JSON: {exc}") from exc

    entries, key, declared = load_entries(manifest)
    ok, altered, missing = [], [], []
    for entry in entries:
        target = snapshots / entry["file"]
        if not target.is_file():
            missing.append(entry["file"])
            continue
        actual = digest(target)
        if actual == entry[key]:
            ok.append(entry["file"])
        else:
            altered.append({"file": entry["file"], "recorded": entry[key], "actual": actual})
    checked = len(ok) + len(altered) + len(missing)
    if checked != declared:
        # Cannot happen once malformed entries are rejected above, but a
        # verifier that silently checks fewer files than were declared is the
        # exact failure this tool already shipped once.
        raise ManifestError(
            f"Manifest declared {declared} entries but {checked} were examined")
    return ok, altered, missing, key, declared


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--snapshots", type=Path, required=True,
                   help="Directory holding the archived snapshots")
    p.add_argument("--manifest", type=Path, required=True,
                   help="MANIFEST_SHA256.json recorded when they were archived")
    p.add_argument("--quiet", action="store_true", help="Print only the summary and failures")
    args = p.parse_args(argv)

    try:
        ok, altered, missing, key, declared = verify(args.snapshots, args.manifest)
    except ManifestError as exc:
        print(f"MANIFEST ERROR: {exc}", file=sys.stderr)
        print("Nothing was verified. This is a failure, not a pass.", file=sys.stderr)
        return 2

    print(f"Verifying against '{key}'.")
    print(f"Manifest declares {declared} entries; all {declared} were examined.\n")
    if not args.quiet:
        for name in ok:
            print(f"OK       {name}")
    for item in altered:
        print(f"ALTERED  {item['file']}  recorded={item['recorded'][:16]}... "
              f"actual={item['actual'][:16]}...")
    for name in missing:
        print(f"MISSING  {name}")

    print(f"\n{declared} declared, {len(ok)} verified, {len(altered)} altered, "
          f"{len(missing)} missing")
    if altered or missing:
        print("Do not rebuild a ledger from this directory until it matches the manifest.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
