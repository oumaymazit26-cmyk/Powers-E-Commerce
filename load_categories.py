#!/usr/bin/env python3
"""
load_categories.py — Charge les catégories POWERS via l'API Railway
"""

import requests
import sys

BASE_URL = "https://powers-e-commerce-production.up.railway.app"
TOKEN = "fake-jwt-token-1"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

CATEGORIES_TREE = [
    {
        "name": "Climatisation", "slug": "climatisation",
        "description": "Produits de climatisation", "sort_order": 1,
        "children": [
            {
                "name": "Split système Inverter", "slug": "split-systeme-inverter",
                "sort_order": 1,
                "children": [
                    {
                        "name": "Mural inverter", "slug": "mural-inverter", "sort_order": 1,
                        "children": [
                            {"name": "smart inverter ART COOL", "slug": "smart-inverter-art-cool", "description": "Design ART COOL", "sort_order": 1},
                            {"name": "Normal inverter", "slug": "normal-inverter", "description": "Standard", "sort_order": 2},
                        ]
                    },
                    {"name": "Mobile", "slug": "mobile", "sort_order": 2},
                    {"name": "Armoire", "slug": "armoire", "sort_order": 3},
                    {"name": "Cassette", "slug": "cassette-split", "sort_order": 4},
                    {"name": "Console", "slug": "console", "sort_order": 5},
                    {"name": "Gainable inverter", "slug": "gainable-inverter", "sort_order": 6},
                ]
            },
            {"name": "Multi split", "slug": "multi-split", "description": "Systèmes multi-split", "sort_order": 2},
            {
                "name": "VRF", "slug": "vrf", "description": "Variable Refrigerant Flow", "sort_order": 3,
                "children": [
                    {
                        "name": "Unité extérieure", "slug": "unite-exterieure-vrf", "sort_order": 1,
                        "children": [
                            {"name": "Min", "slug": "unite-ext-min", "description": "Mini VRF", "sort_order": 1},
                            {"name": "Modulaire/Non modulaire", "slug": "unite-ext-modulaire", "description": "Modulaire", "sort_order": 2},
                        ]
                    },
                    {
                        "name": "Unité intérieure", "slug": "unite-interieure-vrf", "sort_order": 2,
                        "children": [
                            {"name": "Cassette VRF", "slug": "cassette-vrf", "sort_order": 1},
                            {"name": "Gainable VRF", "slug": "gainable-vrf", "sort_order": 2},
                            {"name": "Mural VRF", "slug": "mural-vrf", "sort_order": 3},
                        ]
                    },
                ]
            },
            {
                "name": "Atome", "slug": "atome", "description": "Systèmes Atome", "sort_order": 4,
                "children": [
                    {"name": "Unité intérieure", "slug": "unite-interieure-atome", "sort_order": 1},
                    {"name": "Unité extérieure", "slug": "unite-exterieure-atome", "sort_order": 2},
                ]
            },
            {
                "name": "Pompe à chaleur", "slug": "pompe-a-chaleur", "description": "Pompes à chaleur", "sort_order": 5,
                "children": [
                    {"name": "Air/Air", "slug": "pompe-air-air", "description": "PAC Air/Air", "sort_order": 1},
                    {"name": "Air/Eau", "slug": "pompe-air-eau", "description": "PAC Air/Eau", "sort_order": 2},
                ]
            },
            {"name": "Rafraîchisseur", "slug": "rafraichisseur", "description": "Rafraîchisseurs d'air", "sort_order": 6},
        ]
    },
    {
        "name": "Désenfumage", "slug": "desenfumage", "sort_order": 2,
        "children": [
            {"name": "Caisson", "slug": "caisson-desenfumage", "description": "Caissons", "sort_order": 1},
            {"name": "Clapet", "slug": "clapet", "description": "Clapets", "sort_order": 2},
            {"name": "Volet", "slug": "volet", "description": "Volets", "sort_order": 3},
            {"name": "Autre", "slug": "autre-desenfumage", "description": "Autres", "sort_order": 4},
        ]
    },
    {
        "name": "Ventilation", "slug": "ventilation", "sort_order": 3,
        "children": [
            {"name": "Caisson", "slug": "caisson-ventilation", "description": "Caissons", "sort_order": 1},
            {"name": "Ventilateur", "slug": "ventilateur", "description": "Ventilateurs", "sort_order": 2},
            {"name": "Rideau d'Air", "slug": "rideau-d-air", "description": "Rideaux d'air", "sort_order": 3},
            {"name": "Autres", "slug": "autres-ventilation", "description": "Autres", "sort_order": 4},
        ]
    },
    {
        "name": "Accessoires", "slug": "accessoires", "sort_order": 4,
        "children": [
            {"name": "Chauffe Eau Solaire", "slug": "chauffe-eau-solaire", "description": "Solaire", "sort_order": 1},
            {
                "name": "Diffusion", "slug": "diffusion", "description": "Diffusion", "sort_order": 2,
                "children": [
                    {"name": "Diffuseur", "slug": "diffuseur", "sort_order": 1},
                    {"name": "Grille", "slug": "grille", "sort_order": 2},
                    {"name": "Ventouse", "slug": "ventouse", "sort_order": 3},
                ]
            },
            {"name": "Autre", "slug": "autre-accessoire", "description": "Autres", "sort_order": 3},
        ]
    },
]


def create_category(data, parent_id=None):
    payload = {
        "name": data["name"],
        "slug": data["slug"],
        "description": data.get("description", ""),
        "parent_id": parent_id,
        "sort_order": data.get("sort_order", 0)
    }
    try:
        resp = requests.post(
            f"{BASE_URL}/api/categories",
            headers=HEADERS, json=payload, timeout=15
        )
        if resp.status_code == 201:
            cat_id = resp.json()["data"]["id"]
            print(f"  ✅ {data['name']} (ID: {cat_id})")
            return cat_id
        elif resp.status_code == 400 and "already exists" in resp.text:
            r = requests.get(f"{BASE_URL}/api/categories", headers=HEADERS, timeout=10)
            if r.status_code == 200:
                for cat in r.json().get("data", []):
                    if cat["slug"] == data["slug"]:
                        print(f"  ⚠️  {data['name']} existe déjà (ID: {cat['id']})")
                        return cat["id"]
            print(f"  ⚠️  {data['name']} existe déjà")
            return None
        else:
            print(f"  ❌ {data['name']} — Erreur {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  ❌ {data['name']} — Exception: {e}")
        return None


def create_tree(nodes, parent_id=None):
    for node in nodes:
        cat_id = create_category(node, parent_id)
        if cat_id and "children" in node:
            create_tree(node["children"], cat_id)


def main():
    print(f"🚀 Connexion à {BASE_URL}...")
    try:
        r = requests.get(f"{BASE_URL}/healthz", timeout=10)
        print(f"💚 Health check: HTTP {r.status_code}\n")
    except Exception as e:
        print(f"❌ App injoignable: {e}")
        sys.exit(1)

    print("📂 Création des catégories...\n")
    create_tree(CATEGORIES_TREE)
    print("\n🎉 Terminé ! Vérifie avec :")
    print(f"curl -s {BASE_URL}/api/categories?tree=true -H \"Authorization: Bearer {TOKEN}\"")


if __name__ == "__main__":
    main()