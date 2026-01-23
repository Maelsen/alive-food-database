"""
Alive Food Database - KI Query Demo
====================================
Frage nach einem Gesundheitsziel und bekomme passende Zutaten.

Beispiele:
    python query_demo.py "Gut Health"
    python query_demo.py "Brain Health"
    python query_demo.py "Heart Health"
"""

import os
import json
import requests
from typing import Dict, List, Any

# .env Datei laden
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# OpenAI
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# =============================================================================
# CONFIGURATION - Keys aus .env Datei laden
# =============================================================================

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appOFvKsPdHQQBOQ9")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

TABLES = {
    "Interventions": "tblccYj8xSOtfMAL2",
    "Outcomes": "tblSAOa5AVZLaFqjR",
    "Claims": "tblqHCZ4d3ttrkhQh",
    "Nutrients": "tblQo626zmoWlyZzW",
    "Food-Nutrient Profile": "tbl8HbmIrNpNHhrYH"
}

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}


# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================

def get_all_records(table_id: str) -> List[Dict]:
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
            break

        data = resp.json()
        all_records.extend(data.get('records', []))
        offset = data.get('offset')

        if not offset:
            break

    return all_records


def load_database() -> Dict[str, Any]:
    """Laedt die komplette Datenbank"""
    print("Lade Datenbank...")

    # Interventions (Foods)
    interventions = get_all_records(TABLES["Interventions"])
    foods = {}
    for r in interventions:
        foods[r['id']] = {
            'name': r['fields'].get('Name', ''),
            'type': r['fields'].get('Type (STRICT)', ''),
            'category': r['fields'].get('Category', ''),
            'nutritional_roles': r['fields'].get('Nutritional role (high-level)', []),
            'summary': r['fields'].get('Short summary (human-readable)', ''),
            'example_serving': r['fields'].get('Example serving', ''),
            'is_plant_based': r['fields'].get('Is plant-based?', False),
            'is_whole_food': r['fields'].get('Is whole food?', False)
        }

    # Claims
    claims = get_all_records(TABLES["Claims"])
    claims_data = []
    for r in claims:
        intervention_ids = r['fields'].get('Intervention', [])
        outcome_ids = r['fields'].get('Health Outcome', [])
        claims_data.append({
            'claim_text': r['fields'].get('Claim Text', ''),
            'evidence': r['fields'].get('Evidence Strength', ''),
            'intervention_ids': intervention_ids,
            'outcome_ids': outcome_ids
        })

    # Outcomes
    outcomes = get_all_records(TABLES["Outcomes"])
    outcomes_data = {}
    for r in outcomes:
        outcomes_data[r['id']] = {
            'name': r['fields'].get('Name', ''),
            'category': r['fields'].get('Health Category', '')
        }

    # Nutrients
    nutrients = get_all_records(TABLES["Nutrients"])
    nutrients_data = {}
    for r in nutrients:
        nutrients_data[r['id']] = {
            'name': r['fields'].get('Name', ''),
            'category': r['fields'].get('Category', ''),
            'unit': r['fields'].get('Unit', '')
        }

    # Food-Nutrient Profiles
    profiles = get_all_records(TABLES["Food-Nutrient Profile"])
    profiles_data = []
    for r in profiles:
        food_ids = r['fields'].get('Food', [])
        nutrient_ids = r['fields'].get('Nutrient', [])
        if food_ids and nutrient_ids:
            profiles_data.append({
                'food_id': food_ids[0],
                'nutrient_id': nutrient_ids[0],
                'amount_per_100g': r['fields'].get('Amount per 100g', 0),
                'serving_size': r['fields'].get('Serving Size', ''),
                'amount_per_serving': r['fields'].get('Amount per Serving', 0)
            })

    print(f"  {len(foods)} Foods, {len(claims_data)} Claims, {len(outcomes_data)} Outcomes, {len(nutrients_data)} Nutrients")

    return {
        'foods': foods,
        'claims': claims_data,
        'outcomes': outcomes_data,
        'nutrients': nutrients_data,
        'profiles': profiles_data
    }


def find_foods_for_health_goal(db: Dict, health_goal: str) -> List[Dict]:
    """Findet Foods die zu einem Gesundheitsziel passen"""
    goal_lower = health_goal.lower()
    matching_foods = []

    # Finde Outcomes die zum Ziel passen
    matching_outcome_ids = []
    for oid, outcome in db['outcomes'].items():
        if goal_lower in outcome['name'].lower() or goal_lower in outcome.get('category', '').lower():
            matching_outcome_ids.append(oid)

    # Finde Claims mit diesen Outcomes
    for claim in db['claims']:
        for oid in claim['outcome_ids']:
            if oid in matching_outcome_ids:
                # Finde das Food
                for fid in claim['intervention_ids']:
                    if fid in db['foods']:
                        food = db['foods'][fid]
                        # Hole Naehrstoffe
                        nutrients = []
                        for profile in db['profiles']:
                            if profile['food_id'] == fid:
                                nid = profile['nutrient_id']
                                if nid in db['nutrients']:
                                    nutrients.append({
                                        'name': db['nutrients'][nid]['name'],
                                        'amount': profile['amount_per_100g'],
                                        'unit': db['nutrients'][nid].get('unit', 'g'),
                                        'per_serving': profile['amount_per_serving']
                                    })

                        matching_foods.append({
                            'name': food['name'],
                            'category': food['category'],
                            'claim': claim['claim_text'],
                            'evidence': claim['evidence'],
                            'nutritional_roles': food['nutritional_roles'],
                            'summary': food['summary'],
                            'serving': food['example_serving'],
                            'nutrients': nutrients[:5],  # Top 5 Nutrients
                            'is_plant_based': food['is_plant_based'],
                            'is_whole_food': food['is_whole_food']
                        })

    # Dedupliziere
    seen = set()
    unique_foods = []
    for f in matching_foods:
        if f['name'] not in seen:
            seen.add(f['name'])
            unique_foods.append(f)

    return unique_foods


def generate_recommendation(foods: List[Dict], health_goal: str) -> str:
    """Generiert eine KI-Empfehlung basierend auf den gefundenen Foods"""
    if not HAS_OPENAI or not OPENAI_API_KEY:
        # Einfache Empfehlung ohne KI
        if not foods:
            return f"Keine spezifischen Foods fuer '{health_goal}' in der Datenbank gefunden."

        result = f"\n{'='*60}\n"
        result += f"EMPFOHLENE ZUTATEN FUER: {health_goal.upper()}\n"
        result += f"{'='*60}\n\n"

        for i, food in enumerate(foods[:5], 1):
            result += f"{i}. {food['name']}\n"
            result += f"   Kategorie: {food['category']}\n"
            result += f"   Portion: {food['serving']}\n"
            if food['claim']:
                result += f"   Begruendung: {food['claim'][:100]}...\n"
            if food['evidence']:
                result += f"   Evidenz: {food['evidence']}\n"
            if food['nutrients']:
                nutrients_str = ", ".join([f"{n['name']}: {n['amount']}{n['unit']}/100g" for n in food['nutrients'][:3]])
                result += f"   Naehrstoffe: {nutrients_str}\n"
            result += "\n"

        return result

    # Mit KI
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Baue Kontext
    foods_context = json.dumps(foods[:10], indent=2, ensure_ascii=False)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": """Du bist ein Ernaehrungsberater fuer ein Restaurant.
Basierend auf der Datenbank, empfiehlst du Zutaten fuer ein Gericht.
Antworte auf Deutsch, praktisch und kulinarisch inspirierend.
Nenne konkrete Portionsgroessen und warum jede Zutat gut ist."""},
            {"role": "user", "content": f"""Der Gast moechte ein Gericht fuer: {health_goal}

Verfuegbare Zutaten aus unserer Datenbank:
{foods_context}

Erstelle eine Empfehlung mit:
1. Top 3-5 empfohlene Zutaten mit Begruendung
2. Eine konkrete Gerichtidee
3. Naehrstoff-Highlights"""}
        ],
        temperature=0.7
    )

    return response.choices[0].message.content


def query_food_info(db: Dict, food_name: str) -> Dict:
    """Sucht alle Infos zu einem bestimmten Food"""
    food_lower = food_name.lower()

    for fid, food in db['foods'].items():
        if food_lower in food['name'].lower():
            # Sammle alle Infos
            info = {
                'name': food['name'],
                'type': food['type'],
                'category': food['category'],
                'is_plant_based': food['is_plant_based'],
                'is_whole_food': food['is_whole_food'],
                'nutritional_roles': food['nutritional_roles'],
                'summary': food['summary'],
                'example_serving': food['example_serving'],
                'nutrients': [],
                'health_claims': []
            }

            # Naehrstoffe
            for profile in db['profiles']:
                if profile['food_id'] == fid:
                    nid = profile['nutrient_id']
                    if nid in db['nutrients']:
                        info['nutrients'].append({
                            'name': db['nutrients'][nid]['name'],
                            'amount_per_100g': profile['amount_per_100g'],
                            'unit': db['nutrients'][nid].get('unit', 'g'),
                            'serving_size': profile['serving_size'],
                            'amount_per_serving': profile['amount_per_serving']
                        })

            # Claims
            for claim in db['claims']:
                if fid in claim['intervention_ids']:
                    outcomes = [db['outcomes'].get(oid, {}).get('name', '') for oid in claim['outcome_ids']]
                    info['health_claims'].append({
                        'claim': claim['claim_text'],
                        'evidence': claim['evidence'],
                        'outcomes': outcomes
                    })

            return info

    return None


# =============================================================================
# MAIN
# =============================================================================

def main():
    import sys

    print("=" * 60)
    print("ALIVE FOOD DATABASE - KI QUERY DEMO")
    print("=" * 60)

    # Lade Datenbank
    db = load_database()

    if len(sys.argv) < 2:
        # Interaktiver Modus
        print("\nVerfuegbare Befehle:")
        print("  health <ziel>  - Finde Foods fuer Gesundheitsziel")
        print("  food <name>    - Zeige alle Infos zu einem Food")
        print("  list           - Liste alle Foods")
        print("  quit           - Beenden")
        print()

        while True:
            try:
                user_input = input("Query> ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            if user_input.lower() == 'quit':
                break

            if user_input.lower() == 'list':
                print("\nVerfuegbare Foods:")
                for fid, food in db['foods'].items():
                    if food['type'] in ['Food', 'Food group']:
                        print(f"  - {food['name']} ({food['category']})")
                print()
                continue

            if user_input.lower().startswith('health '):
                goal = user_input[7:].strip()
                foods = find_foods_for_health_goal(db, goal)
                recommendation = generate_recommendation(foods, goal)
                print(recommendation)
                continue

            if user_input.lower().startswith('food '):
                food_name = user_input[5:].strip()
                info = query_food_info(db, food_name)
                if info:
                    print(f"\n{'='*60}")
                    print(f"FOOD INFO: {info['name']}")
                    print(f"{'='*60}")
                    print(f"Typ: {info['type']}")
                    print(f"Kategorie: {info['category']}")
                    print(f"Plant-based: {'Ja' if info['is_plant_based'] else 'Nein'}")
                    print(f"Whole food: {'Ja' if info['is_whole_food'] else 'Nein'}")
                    print(f"Portion: {info['example_serving']}")
                    print(f"\nZusammenfassung: {info['summary']}")

                    if info['nutrients']:
                        print(f"\nNaehrstoffe (pro 100g):")
                        for n in info['nutrients']:
                            print(f"  - {n['name']}: {n['amount_per_100g']} {n['unit']}")
                            if n['amount_per_serving']:
                                print(f"    Pro Portion ({n['serving_size']}): {n['amount_per_serving']} {n['unit']}")

                    if info['health_claims']:
                        print(f"\nHealth Claims:")
                        for c in info['health_claims']:
                            print(f"  - {c['claim'][:80]}...")
                            print(f"    Evidenz: {c['evidence']}")
                            print(f"    Outcomes: {', '.join(c['outcomes'])}")
                    print()
                else:
                    print(f"Food '{food_name}' nicht gefunden.")
                continue

            # Direktes Gesundheitsziel
            foods = find_foods_for_health_goal(db, user_input)
            recommendation = generate_recommendation(foods, user_input)
            print(recommendation)

    else:
        # Kommandozeilen-Modus
        query = " ".join(sys.argv[1:])
        foods = find_foods_for_health_goal(db, query)
        recommendation = generate_recommendation(foods, query)
        print(recommendation)


if __name__ == "__main__":
    main()
