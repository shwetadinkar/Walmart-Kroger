"""Execute from the Walmart project root: python tools/import_brightdata.py ..."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walmart_collector.brightdata_import import main
if __name__ == "__main__":
    raise SystemExit(main())