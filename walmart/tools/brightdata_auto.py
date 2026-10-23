"""Run: python tools/brightdata_auto.py --dry-run --inputs-csv config/brightdata_category_inputs.csv"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walmart_collector.brightdata_automatic import main
if __name__ == "__main__":
    raise SystemExit(main())
