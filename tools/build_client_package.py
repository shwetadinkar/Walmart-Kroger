"""Build a client package from files already in this repository.

Everything is copied byte for byte. Nothing is edited, reformatted or
regenerated on the way in, because a package whose contents differ from the
repository is not evidence of what the repository holds.

Every file is hashed into `MANIFEST_SHA256.json`, and `verify.py` ships inside
the package so the recipient can recheck every hash with no network, no
dependencies and no access to this repository.

Identity scanning follows the convention already used by
`marianos/tools/build_evidence_package.py`: the deny-list of strings that must
never leave this machine is itself private, so it is passed in rather than
committed. Without one the manifest records the scan as `not run` rather than
claiming a clean result it did not establish.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

VERIFY = '''#!/usr/bin/env python3
"""Recheck every file in this package against MANIFEST_SHA256.json.

Needs Python and this folder. Exits non-zero if anything disagrees.
"""
import hashlib, json, sys
from pathlib import Path

here = Path(__file__).resolve().parent
manifest = json.loads((here / "MANIFEST_SHA256.json").read_text(encoding="utf-8"))

bad, checked = [], 0
for entry in manifest["files"]:
    path = here / entry["path"]
    if not path.exists():
        bad.append(f"MISSING  {entry['path']}")
        continue
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        bad.append(f"CHANGED  {entry['path']}")
    elif len(data) != entry["bytes"]:
        bad.append(f"SIZE     {entry['path']}")
    else:
        checked += 1

extra = sorted(
    str(p.relative_to(here)) for p in here.rglob("*")
    if p.is_file() and str(p.relative_to(here)) not in
    {e["path"] for e in manifest["files"]} | {"MANIFEST_SHA256.json", "verify.py"}
)
for name in extra:
    bad.append(f"EXTRA    {name}")

print(f"{checked} of {len(manifest['files'])} files match their recorded hash")
if bad:
    print("\\nFAILED:")
    for line in bad:
        print("  " + line)
    sys.exit(1)
print("OK: every file matches, and there is nothing here that the manifest "
      "does not list.")
'''


class PackageRefused(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_identity(root: Path, denylist: Path | None) -> dict:
    """Refuse to publish a package containing a denied string."""
    if denylist is None:
        return {"status": "not run",
                "why": "No deny-list was supplied, so no claim is made about "
                       "identity strings in this package."}
    terms = [t.strip() for t in denylist.read_text(encoding="utf-8").splitlines()
             if t.strip() and not t.startswith("#")]
    if not terms:
        raise PackageRefused("The deny-list is empty")
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        blob = path.read_bytes().lower()
        for term in terms:
            if term.lower().encode() in blob:
                found.append(str(path.relative_to(root)))
                break
    if found:
        raise PackageRefused(f"Denied strings appear in: {sorted(set(found))}")
    return {"status": "clean", "terms_checked": len(terms)}


def build(entries, out: Path, title: str, denylist: Path | None) -> dict:
    if out.exists():
        raise PackageRefused(f"{out} already exists; build into a fresh folder")
    out.mkdir(parents=True)

    files = []
    for source, inside in entries:
        src = Path(source)
        if not src.is_file():
            raise PackageRefused(f"Not a file, so not packaged: {source}")
        dest = out / inside
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if sha256(src) != sha256(dest):
            raise PackageRefused(f"Copy of {source} does not match its source")
        files.append({"path": inside, "bytes": dest.stat().st_size,
                      "sha256": sha256(dest), "from": str(src)})

    identity = scan_identity(out, denylist)

    manifest = {
        "title": title,
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "total_bytes": sum(f["bytes"] for f in files),
        "identity_scan": identity,
        "verify": "python3 verify.py",
        "note": "Every file is a byte-for-byte copy of a file in the source "
                "repository. Nothing here was regenerated for this package.",
        "files": sorted(files, key=lambda f: f["path"]),
    }
    (out / "MANIFEST_SHA256.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "verify.py").write_text(VERIFY, encoding="utf-8")
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", required=True,
                   help="JSON: {title, files: [[source, path_in_package], ...]}")
    p.add_argument("--out", required=True)
    p.add_argument("--identity-denylist")
    args = p.parse_args(argv)

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    deny = Path(args.identity_denylist) if args.identity_denylist else None
    try:
        manifest = build(spec["files"], Path(args.out), spec["title"], deny)
    except PackageRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({k: v for k, v in manifest.items() if k != "files"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
