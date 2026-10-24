# Direct Mariano's website feasibility — 24 October 2026

A different source route worked: the normal Mariano's website in a browser, without Bright Data collection calls or Kroger API credentials. On the official Lakeshore East store page, clicking Shop Pickup selected **Marianos Lakeshore East, 333 E Benton Pl**. The selected-store header remained visible on all five inspected PDPs. Official store page confirms ZIP 60601: https://www.marianos.com/stores/grocery/il/chicago/marianos-lakeshore-east/531/00503 . Website path codes are not asserted to be verified API location IDs.

## Five distinct fixed-size product pages checked
| Product | UPC displayed on PDP | Price observed (USD) | Other source evidence |
| --- | --- | --- | --- |
| Fresh Strawberries – 1 LB Clamshell, 1 lb | 0003338320027 | sale 2.99; regular 3.99 | Weekly Digital Deal, $2.49 Strawberries; complete coupon conditions not yet captured |
| Fresh Red Raspberries - 6 OZ Clamshell | 0003338321000 | 3.79 | Pickup Available |
| Fresh Blueberries - 1 PT Clamshell | 0003338322101 | 5.49 | Pickup Available |
| Seedless Mandarin Clementine Oranges in 3lb Bag | 0003338314616 | 4.99 | Pickup Available |
| Kroger Grade A Large White Eggs, 18 ct | 0001111060933 | 2.98 | **Displayed PPM $0.17/each**, AISLE 15, Pickup Available |

Each page used marianos.com and fulfillment=PICKUP. Product links were obtained from the store-selected listing/recommendation links, not generated. No cart changes, coupon clipping, checkout or account sign-in was performed. Exactly five distinct PDPs were inspected; listing recommendations are not counted as collected products.

## Evidence and limits
DOM text excerpts with timestamps and source URLs, plus screenshots, retained locally. No third-party contest entry data is used in this sample. The sample proves direct browser access to product/store/price/UPC and at least one displayed PPM. It is **not** a complete 22-field submission, API integration, unattended scraper, full category audit, Azure deployment or 500-product collection. Coupon terms and source PPM absent from an inspected page remain unverified. Nothing was calculated to fill missing PPM.

Existing official API client requires KROGER_CLIENT_ID and KROGER_CLIENT_SECRET; neither is present in this process environment. No API credentials were requested or exposed.

## Next work
Use the direct selected-store website route for a bounded category/pagination test, retaining selected-store evidence for every page. Implement only after mapping the visible page fields to the existing strict schema and confirming restart/failure handling. Retrieve exact coupon details separately without clipping. Keep variable-weight estimates excluded and do not replace source PPM with arithmetic. Scale toward 500+ only after these additional checks succeed.

Walmart unchanged. No Bright Data scrape, vendor purchase, paid custom scraper, Azure execution or support message was launched in this direct-site experiment.
