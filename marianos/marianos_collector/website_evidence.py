"""Read literal product fields from saved rendered Mariano's DOM snapshots."""
import argparse
import json
from pathlib import Path
import re

def parse(evidence):
    result = dict(evidence)
    text = evidence['observed_text']
    upc = evidence['upc']
    if 'UPC: '+upc not in text:
        raise ValueError('UPC_NOT_DISPLAYED')
    # Exclude recommendations and site navigation: their deals are other products' offers.
    product = text.split('UPC: '+upc,1)[1]
    product = product.split('  - heading "Discover More Options"')[0].split('  - heading "Product Information"')[0]
    price_region = product.split('  - heading "Item Availability"')[0]
    ppms = re.findall(r'^  - generic: (\$[\d,.]+/(?:fl oz|oz|lb|ct|each|gal|qt|pt|100 ct|100 g|g|kg|l|L))\s*$',price_region,re.M)
    result['ppm'] = ppms[0] if len(ppms)==1 else ''
    prices = re.findall(r'^  - generic: \$(\d+\.\d{2})\s*$',price_region,re.M)
    sale = re.search(r'Sale: \$(\d+\.\d{2}) discounted from \$(\d+\.\d{2})',price_region)
    result['displayed_regular_price'] = sale.group(2) if sale else (prices[0] if prices else '')
    result['displayed_sale_price'] = sale.group(1) if sale else ''
    result['pickup_available'] = bool(re.search(r'generic: Pickup\s*\n  - generic: Available\s*(?:\n|$)',product))
    breadcrumb_region = text.split('  - navigation "Breadcrumbs":',1)[-1].split('  - generic "Images for',1)[0]
    result['breadcrumbs'] = [x for x in re.findall(r'^      - link "([^"]+)":',breadcrumb_region,re.M) if x!='Home']
    result['sub_category'] = result['breadcrumbs'][-1] if len(result['breadcrumbs'])>1 else ''
    result['volume_deals_description'] = ''
    result['volume_deals_price'] = ''
    result['digital_deals_description'] = ''
    result['digital_deals_price'] = ''
    result['digital_details_required'] = False
    if '  - heading "Savings"' in product:
        savings = product.split('  - heading "Savings"',1)[1]
        result['savings_text'] = savings
        if re.search(r'digital|clip|activat',savings,re.I):
            result['digital_details_required'] = True
        else:
            offers = re.findall(r'^    - generic: (.+)$',savings,re.M)
            verified = [x for x in offers if re.search(r'when you buy|buy \d|\d+ for \$|mix.or.match|must buy',x,re.I)]
            if len(verified)==1:
                result['volume_deals_description'] = verified[0]
            elif verified:
                result['multiple_volume_offers_require_review'] = verified
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('destination',type=Path)
    args=p.parse_args()
    records=[parse(e) for e in json.loads(args.source.read_text(encoding='utf-8'))]
    args.destination.parent.mkdir(parents=True,exist_ok=True)
    args.destination.write_text(json.dumps(records,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'pages':len(records),'ppm':sum(bool(e['ppm']) for e in records),
                      'volume_offers':sum(bool(e['volume_deals_description']) for e in records),
                      'digital_details_required':sum(e['digital_details_required'] for e in records)}))

if __name__=='__main__':main()
