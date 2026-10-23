"""Azure Container Apps Job entry point. Defaults to zero-cost dry-run."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walmart_collector.brightdata_automatic import main


def run():
    mode = os.getenv("BRIGHTDATA_JOB_MODE", "dry-run")
    args = ["--store-id", os.getenv("WALMART_STORE_ID", "100"),
            "--zipcode", os.getenv("WALMART_ZIPCODE", "72712"),
            "--inputs-csv", os.getenv("BRIGHTDATA_INPUT_CSV", "config/brightdata_category_inputs.csv")]
    if mode == "dry-run":
        args += ["--dry-run", "--trigger", "--max-records", "10"]
    elif mode == "blob-smoke":
        # Verifies the manually uploaded 615-row trial JSON using Managed Identity.
        # No Bright Data API key or provider request is needed.
        args += ["--blob-smoke"]
    elif mode == "snapshot":
        sid = os.getenv("BRIGHTDATA_SNAPSHOT_ID")
        if not sid:
            raise RuntimeError("BRIGHTDATA_SNAPSHOT_ID required in snapshot mode")
        args += ["--snapshot-id", sid]
    elif mode == "trigger":
        cap = os.getenv("BRIGHTDATA_RECORD_CAP")
        if not cap or not cap.isdecimal() or int(cap) < 1:
            raise RuntimeError("BRIGHTDATA_RECORD_CAP must be set to an approved positive value")
        args += ["--trigger", "--max-records", cap]
    else:
        raise RuntimeError("Unsupported BRIGHTDATA_JOB_MODE; use dry-run, snapshot, trigger")
    return main(args)


if __name__ == "__main__":
    raise SystemExit(run())
