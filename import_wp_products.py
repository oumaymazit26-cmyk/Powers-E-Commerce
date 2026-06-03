#!/usr/bin/env python3
"""
import_wp_products.py — Importe les produits WooCommerce → App Flask Railway
Prêt à l'emploi, credentials déjà configurés.
"""

import requests
import os
import sys
from io import BytesIO
from urllib.parse import urlparse

# ─── CONFIG FLASK (ton app Railway) ───
FLASK_URL = "https://powers-e-commerce-production.up.railway.app"
FLASK_TOKEN = "fake-jwt-token-1"
FLASK_HEADERS = {"Authorization": f"Bearer {FLASK_TOKEN}"}

# ─── CONFIG WOOCOMMERCE (technoclim.ma) ───
WP_URL = "https://www.technoclim.ma"
WP_CK = "ck_617397aada9b97cca8b1c43700153eb50fd99bef"
WP_CS = "cs_9146d6d117005a5677ebcc2e53a760ef0edaba63"


def get_wcapi():
    from woocommerce import API
    return API(
        url=WP_URL,
        consumer_key=WP_CK,
        consumer_secret=WP_CS,
        version="wc/v3",
        timeout=20
    )


def get_flask_categories():
    """Mapping nom/slug Flask → ID"""
    r = requests.get(f"{FLASK_URL}/api/categories", headers=FLASK_HEADERS, timeout=15)
    if r.status_code != 200:
        print(f"⚠️  Erreur catégories Flask: {r.status_code}")
        return {}
    mapping = {}
    for c in r.json().get("data", []):
        mapping[c["name"].lower()] = c["id"]
        mapping[c["slug"].lower()] = c["id"]
    return mapping


def get_existing_flask_products():
    """Évite les doublons par SKU ou WP ID"""
    existing = {}
    page = 1
    while True:
        r = requests.get(
            f"{FLASK_URL}/api/products",
            headers=FLASK_HEADERS,
            params={"per_page": 100, "page": page},
            timeout=15
        )
        if r.status_code != 200:
            break
        items = r.json().get("data", [])
        if not items:
            break
        for p in items:
            if p.get("sku"):
                existing[p["sku"]] = p["id"]
            if p.get("wp_product_id"):
                existing[f"wp_{p['wp_product_id']}"] = p["id"]
        if len(items) < 100:
            break
        page += 1
    return existing


def download_image(url):
    if not url:
        return None
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            ext = os.path.splitext(urlparse(url).path)[1] or ".jpg"
            if ext.lower() not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                ext = ".jpg"
            content_type = r.headers.get("Content-Type", "image/jpeg")
            return (f"image{ext}", BytesIO(r.content), content_type)
    except Exception as e:
        print(f"   ⚠️ Image: {e}")
    return None


def import_product(product, cat_mapping, existing):
    sku = product.get("sku", "")
    wp_id = product.get("id")
    name = product.get("name", "Sans nom")

    if sku and sku in existing:
        print(f"  ⚠️  {name} — déjà importé (SKU: {sku})")
        return
    if f"wp_{wp_id}" in existing:
        print(f"  ⚠️  {name} — déjà importé (WP ID: {wp_id})")
        return

    # Catégorie
    category_id = ""
    for wc_cat in product.get("categories", []):
        key = wc_cat.get("name", "").lower()
        if key in cat_mapping:
            category_id = str(cat_mapping[key])
            break

    # Stock
    stock = product.get("stock_status", "instock")
    stock = "in_stock" if stock == "instock" else "out_of_stock"

    # Status
    status = "active" if product.get("status") == "publish" else "draft"

    # Dimensions
    d = product.get("dimensions", {})
    dims = f"{d.get('length','')}x{d.get('width','')}x{d.get('height','')}".strip("x") or ""

    # Images
    files = {}
    if product.get("images"):
        img = download_image(product["images"][0].get("src"))
        if img:
            files["image"] = img
        for idx, g in enumerate(product["images"][1:], 1):
            gi = download_image(g.get("src"))
            if gi:
                files[f"gallery_{idx}"] = gi

    data = {
        "name": product.get("name", ""),
        "slug": product.get("slug", ""),
        "sku": sku or f"WP-{wp_id}",
        "description": product.get("description", ""),
        "short_description": product.get("short_description", ""),
        "price": str(product.get("regular_price") or 0),
        "sale_price": str(product.get("sale_price") or 0),
        "stock_quantity": str(product.get("stock_quantity", 0)),
        "stock_status": stock,
        "weight": str(product.get("weight") or 0),
        "dimensions": dims,
        "category_id": category_id,
        "tags": ",".join([t["name"] for t in product.get("tags", [])]),
        "status": status,
        "product_type": product.get("type", "simple"),
        "featured": "true" if product.get("featured") else "false",
        "meta_title": product.get("name", ""),
        "meta_description": product.get("short_description", ""),
        "publish_to_wp": "false",
    }

    try:
        if files:
            r = requests.post(
                f"{FLASK_URL}/api/products",
                headers=FLASK_HEADERS,
                data=data,
                files=files,
                timeout=60
            )
        else:
            r = requests.post(
                f"{FLASK_URL}/api/products",
                headers=FLASK_HEADERS,
                data=data,
                timeout=30
            )

        if r.status_code == 201:
            pid = r.json()["data"]["id"]
            print(f"  ✅ {name} (Flask ID: {pid})")
        else:
            print(f"  ❌ {name} — HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  ❌ {name} — {e}")


def main():
    print("🚀 Import WooCommerce → Flask")
    print(f"🔗 WordPress: {WP_URL}")
    print(f"🔗 Flask: {FLASK_URL}")

    # Test connexion Flask
    try:
        r = requests.get(f"{FLASK_URL}/healthz", timeout=10)
        print(f"💚 Flask health: {r.status_code}")
    except Exception as e:
        print(f"❌ Flask injoignable: {e}")
        sys.exit(1)

    # Test connexion WooCommerce
    wcapi = get_wcapi()
    try:
        t = wcapi.get("products", params={"per_page": 1})
        print(f"💚 WooCommerce: {t.status_code}")
    except Exception as e:
        print(f"❌ WooCommerce: {e}")
        sys.exit(1)

    cat_map = get_flask_categories()
    print(f"📂 {len(cat_map)//2} catégories dans Flask")

    existing = get_existing_flask_products()
    print(f"📦 {len(existing)} produits déjà dans Flask")

    # Import paginé
    page = 1
    imported = 0
    while True:
        print(f" Page {page} ---")
        r = wcapi.get("products", params={"per_page": 100, "page": page})
        products = r.json() if r.status_code == 200 else []
        if not products:
            break

        for p in products:
            import_product(p, cat_map, existing)
            imported += 1

        if len(products) < 100:
            break
        page += 1

  
    print(f"Vérifie : curl -s {FLASK_URL}/api/products -H 'Authorization: Bearer {FLASK_TOKEN}'")


if __name__ == "__main__":
    main()