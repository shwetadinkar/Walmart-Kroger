# Promotion identity correction — October 28, 2026

Retained UPCs: 0002100061223, 0002100065893, 0007457001310

The historical client README incorrectly identified chocolate ice cream 0007457001400 as retained and bars 0007457001310 as withheld. The historical retained output and reconciliation index establish the opposite: bars were retained; chocolate and vanilla 0007457000400 were withheld for API/PDP regular and sale price conflicts. The original evidence and baseline remain unchanged.

The expanded coupon source was the chocolate PDP (0007457001400), while its qualifying-product card also identified retained bars (0007457001310). Source PDP identity must not be relabelled as retained-product identity. The terms' November 3 redemption end and displayed Nov. 04 expiry remain unresolved; no date or final coupon price was inferred.

This public correction contains compact identity/disposition/timestamp/hash metadata only. Full original observations, retained 22-field output, quarantine, provenance, literal terms, corrected detailed README/index/audit and source hashes remain in the private outputs/Marianos_Client_Corrections_2026-10-28/B_PROMOTION_CORRECTION package. IDENTITY_FIXTURE.json records identity sets derived from that package, not a replacement product delivery. Stored API-original hashes describe original response provenance; packaged redacted-copy hashes are separately recorded in DISCREPANCY_AUDIT.json.

Validation: python -m unittest marianos.tests.test_promotion_identity_correction. Compact consistency checks run everywhere; private raw/hash/price checks additionally run when the private package is available. The identity regression failed on the historical reversed README identity before correction.
