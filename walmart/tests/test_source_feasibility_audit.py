import unittest
from tools.source_feasibility_audit import audit, get_path

MAPPING = {
    "product_id": "id", "product_title": "title", "upc": "upc",
    "price_display": "price", "ppm_display": "ppm",
    "store_id": "store.id", "zipcode": "store.zip",
    "fulfillment": "fulfillment", "seller": "seller",
    "availability": "availability", "volume_deals_description": "volume",
    "digital_deals_description": "digital"
}

class SourceAuditTest(unittest.TestCase):
    def example(self):
        return dict(
            id="ABC123", title="Synthetic test product", upc="012345678905",
            price="4.25", ppm="$0.42/oz",
            store={"id": "100", "zip": "72712"},
            fulfillment="pickup", seller="Walmart", availability="NOT_AVAILABLE",
            volume="", digital=""
        )
    def test_nested_source_values(self):
        self.assertEqual(get_path({"a": [{"b": 1}]}, "a.0.b"), 1)
    def test_reports_store_mismatch(self):
        rows = [self.example(), dict(self.example(), store={"id": "5959", "zip": "77007"})]
        report = audit(rows, MAPPING, "100", "72712", "synthetic", synthetic=True)
        self.assertIn("STORE_OR_ZIP_MISMATCH", report["blockers"])
        self.assertFalse(report["contest_ready"])
    def test_no_invented_usage_count(self):
        report = audit([self.example()], MAPPING, "100", "72712", "synthetic", synthetic=True)
        self.assertIsNone(report["requests_observed"])
        self.assertEqual(report["unavailable_records_present"], 1)
        self.assertEqual(report["field_coverage"]["ppm_display"]["observed"], 1)
    def test_no_reconstructed_ppm(self):
        row = self.example()
        row.pop("ppm")
        report = audit([row], MAPPING, "100", "72712", "synthetic", requests_observed=3, synthetic=True)
        self.assertEqual(report["field_coverage"]["ppm_display"]["observed"], 0)
        self.assertIn("NO_DIRECTLY_DISPLAYED_PPM", report["blockers"])
        self.assertEqual(report["requests_per_product_observed"], 3)

if __name__ == "__main__":
    unittest.main()
