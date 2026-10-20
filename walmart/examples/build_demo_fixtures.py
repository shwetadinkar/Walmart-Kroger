"""Generate obviously SYNTHETIC fixtures. NEVER upload these as real product evidence."""
import hashlib
import json
from pathlib import Path
from walmart_collector.config import categories_from_csv, stores_from_json

ROOT = Path(__file__).resolve().parent.parent

def save(store, category, url, cursor, products, children=None, next_cursor=""):
    key = hashlib.sha256(url.encode()).hexdigest()[:14]
    path = ROOT / "fixtures" / store.store_id / category.slug / f"{key}_{cursor or 'start'}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"store_id":store.store_id,"zipcode":store.zipcode,"store_context_verified":True,
            "source_url":url,"products":products,"children":children or [],"next_cursor":next_cursor,
            "subcategories_complete":True}
    path.write_text(json.dumps(body,indent=2)+"\n",encoding="utf-8")

def product(store, category, id_suffix, *, deal=False, digital=False, fulfillment="pickup", weight="12 oz"):
    v = {
        "product_id":f"SYN-{store.store_id}-{category.slug}-{id_suffix}",
        "store_id":store.store_id, "zipcode":store.zipcode,"store_context_verified":True,
        "seller_type":"walmart", "fulfillment":fulfillment,
        "product_title":f"SYNTHETIC TEST PRODUCT: {category.name} {id_suffix}",
        "weight":weight,"regular_price":"3.99","sale_price":"3.49",
        "brand":"Great Value","image_url":"https://example.invalid/fixture-image.jpg",
        "url":f"https://www.walmart.com/ip/SYNTHETIC-NOT-REAL-{store.store_id}-{category.slug}-{id_suffix}",
        "upc":f"SYNTHETIC-UPC-{store.store_id}-{id_suffix}","ppm":"$0.29/oz",
        "volume_deals_description":"2 for $5 (synthetic example)" if deal else "",
        "volume_deals_price":"5.00" if deal else "",
        "digital_deals_description":"Clip Coupon: Save $2 (synthetic example)" if digital else "",
        "digital_deals_price":""}
    return v

def main():
    cats = categories_from_csv(ROOT / "config/categories.csv")
    for store in stores_from_json(ROOT / "config/stores.json"):
        for idx,cat in enumerate(cats):
            children = []
            cursor = ""
            if cat.name == "Food":
                children = [
                    {"name":"Canned Foods","url":"https://www.walmart.com/browse/synthetic-canned-foods/99991"},
                    {"name":"Recipes","url":"https://www.walmart.com/browse/synthetic-recipes/99992"},
                    {"name":"Shop All Foods","url":"https://www.walmart.com/browse/synthetic-all-foods/99993"}]
            if cat.name == "Pets":
                children = [{"name":"Farm Animals","url":"https://www.walmart.com/browse/synthetic-farm/99994"}]
            if cat.name == "Household Essentials":
                cursor = "second"
            page_products = [product(store,cat,str(idx),deal=(idx%3==0),digital=(idx%4==0))]
            # Prove the ineligible fulfillment / approximate weight records get filtered.
            if cat.name == "Beauty":
                page_products += [product(store,cat,"shipping",fulfillment="shipping")]
            if cat.name == "Food":
                page_products += [product(store,cat,"approx",weight="approx. 2 lb")]
            save(store,cat,cat.url,"",page_products,children=children,next_cursor=cursor)
            if cat.name == "Household Essentials":
                save(store,cat,cat.url,"second",[product(store,cat,"extra")])
            if cat.name == "Food":
                save(store,cat,children[0]["url"],"",[product(store,cat,"canned")])
    print("Synthetic fixtures generated for 2 stores, 11 categories, pagination and exclusions")

if __name__ == "__main__": main()
