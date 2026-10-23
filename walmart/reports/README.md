# Walmart audit reports

This folder may contain **sanitized review ledgers** only: source file/row IDs, normalized exclusion codes, public product identifiers and input hashes. It must not contain Bright Data credentials, complete provider payloads, store-local pricing, customer data, or the complete client dataset.

All rejected products remain archived in authorized private trial evidence; source errors are not proof of out-of-stock status. For production, store source responses and historical records in private Azure Blob Storage. Audit CSVs are *not* acceptance-certified product datasets.
