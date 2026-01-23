"""
Fix Serving Sizes - Fuellt alle leeren Serving Size Felder in Food-Nutrient Profile
"""

import os
import requests
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appOFvKsPdHQQBOQ9")
FOOD_NUTRIENT_TABLE = "tbl8HbmIrNpNHhrYH"
INTERVENTIONS_TABLE = "tblccYj8xSOtfMAL2"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

# Standard Serving Sizes nach Kategorie
STANDARD_SERVING_SIZES = {
    "Fruit": {"serving": "1 cup", "grams": 150},
    "Vegetable": {"serving": "1 cup raw", "grams": 100},
    "Legume": {"serving": "1 cup cooked", "grams": 177},
    "Whole grain": {"serving": "1 cup cooked", "grams": 195},
    "Nuts & seeds": {"serving": "1 oz (28g)", "grams": 28},
    "Herbs & spices": {"serving": "1 tsp", "grams": 3},
    "Beverage": {"serving": "1 cup", "grams": 240},
    "Animal product": {"serving": "3 oz", "grams": 85},
    "Dietary pattern": {"serving": "N/A", "grams": 0},
    "Sleep": {"serving": "N/A", "grams": 0},
    "Physical activity": {"serving": "N/A", "grams": 0},
}

# Spezifische Serving Sizes fuer bekannte Foods
SPECIFIC_SERVING_SIZES = {
    "flaxseed": {"serving": "2 tablespoons ground", "grams": 20},
    "chia seeds": {"serving": "2 tablespoons", "grams": 28},
    "walnuts": {"serving": "1 oz (14 halves)", "grams": 28},
    "berries": {"serving": "1 cup", "grams": 148},
    "blueberries": {"serving": "1 cup", "grams": 148},
    "oatmeal": {"serving": "1 cup cooked", "grams": 234},
    "leafy greens": {"serving": "2 cups raw", "grams": 60},
    "sweet potatoes": {"serving": "1 medium", "grams": 130},
    "beans": {"serving": "1 cup cooked", "grams": 177},
    "brown rice": {"serving": "1 cup cooked", "grams": 195},
    "whole grains": {"serving": "1 cup cooked", "grams": 195},
    "turmeric": {"serving": "1 tsp", "grams": 3},
    "citrus": {"serving": "1 medium fruit", "grams": 130},
    "herbs": {"serving": "1 tsp", "grams": 3},
}


def get_all_records(table_id):
    """Holt alle Records einer Tabelle"""
    all_records = []
    offset = None

    while True:
        params = {}
        if offset:
            params['offset'] = offset

        resp = requests.get(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=HEADERS,
            params=params
        )

        if resp.status_code != 200:
            print(f"Fehler: {resp.status_code}")
            break

        data = resp.json()
        all_records.extend(data.get('records', []))
        offset = data.get('offset')

        if not offset:
            break

    return all_records


def get_serving_size(food_name, category):
    """Ermittelt die Serving Size fuer ein Food"""
    food_lower = food_name.lower() if food_name else ""

    # Pruefe spezifische Sizes zuerst
    for key, serving in SPECIFIC_SERVING_SIZES.items():
        if key in food_lower:
            return serving

    # Fallback auf Kategorie
    if category and category in STANDARD_SERVING_SIZES:
        return STANDARD_SERVING_SIZES[category]

    # Default
    return {"serving": "1 serving", "grams": 100}


def update_record(table_id, record_id, fields):
    """Aktualisiert einen Record"""
    resp = requests.patch(
        f"https://api.airtable.com/v0/{BASE_ID}/{table_id}/{record_id}",
        headers=HEADERS,
        json={"fields": fields}
    )
    return resp.status_code == 200


def main():
    print("=" * 60)
    print("FIXING SERVING SIZES")
    print("=" * 60)

    # Lade Interventions um Kategorien zu bekommen
    print("\n[1/3] Lade Interventions...")
    interventions = get_all_records(INTERVENTIONS_TABLE)

    # Erstelle Mapping: intervention_id -> (name, category)
    intervention_info = {}
    for r in interventions:
        intervention_info[r['id']] = {
            'name': r['fields'].get('Name', ''),
            'category': r['fields'].get('Category', '')
        }
    print(f"  {len(intervention_info)} Interventions geladen")

    # Lade Food-Nutrient Profiles
    print("\n[2/3] Lade Food-Nutrient Profiles...")
    profiles = get_all_records(FOOD_NUTRIENT_TABLE)
    print(f"  {len(profiles)} Profiles geladen")

    # Finde Profiles ohne Serving Size
    profiles_to_fix = []
    for p in profiles:
        serving_size = p['fields'].get('Serving Size')
        serving_grams = p['fields'].get('Serving Size Grams')

        if not serving_size or not serving_grams:
            profiles_to_fix.append(p)

    print(f"  {len(profiles_to_fix)} Profiles ohne Serving Size gefunden")

    if not profiles_to_fix:
        print("\nKeine Profiles zu fixen!")
        return

    # Fixe die Profiles
    print(f"\n[3/3] Fixe {len(profiles_to_fix)} Profiles...")
    fixed = 0
    errors = 0

    for i, p in enumerate(profiles_to_fix):
        # Hole Food Info
        food_links = p['fields'].get('Food', [])
        food_id = food_links[0] if food_links else None

        if not food_id or food_id not in intervention_info:
            errors += 1
            continue

        food_info = intervention_info[food_id]
        food_name = food_info['name']
        category = food_info['category']

        # Ermittle Serving Size
        serving = get_serving_size(food_name, category)

        # Berechne Amount per Serving
        amount_per_100g = p['fields'].get('Amount per 100g', 0)
        serving_grams = serving.get('grams', 100)
        amount_per_serving = (amount_per_100g * serving_grams / 100) if serving_grams > 0 else 0

        # Update Record
        fields = {
            "Serving Size": serving.get('serving', '1 serving'),
            "Serving Size Grams": serving_grams,
            "Amount per Serving": round(amount_per_serving, 2)
        }

        success = update_record(FOOD_NUTRIENT_TABLE, p['id'], fields)

        if success:
            fixed += 1
            if fixed % 10 == 0:
                print(f"  {fixed}/{len(profiles_to_fix)} gefixt...")
        else:
            errors += 1

        # Rate limiting
        if (i + 1) % 5 == 0:
            time.sleep(0.2)

    print("\n" + "=" * 60)
    print("FERTIG!")
    print("=" * 60)
    print(f"  Gefixt: {fixed}")
    print(f"  Fehler: {errors}")


if __name__ == "__main__":
    main()
