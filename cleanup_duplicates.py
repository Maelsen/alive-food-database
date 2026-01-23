"""
Cleanup Duplicates - Findet und entfernt Duplikate in Food-Nutrient Profile
"""

import os
import requests
import time
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appOFvKsPdHQQBOQ9")
FOOD_NUTRIENT_TABLE = "tbl8HbmIrNpNHhrYH"
INTERVENTIONS_TABLE = "tblccYj8xSOtfMAL2"
NUTRIENTS_TABLE = "tblQo626zmoWlyZzW"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
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


def delete_record(table_id, record_id):
    """Loescht einen Record"""
    resp = requests.delete(
        f"https://api.airtable.com/v0/{BASE_ID}/{table_id}/{record_id}",
        headers=HEADERS
    )
    return resp.status_code == 200


def count_filled_fields(fields):
    """Zaehlt wie viele Felder einen Wert haben"""
    count = 0
    for key, value in fields.items():
        if value is not None and value != "" and value != [] and value != 0:
            count += 1
    return count


def main():
    print("=" * 60)
    print("DUPLIKAT CLEANUP - Food-Nutrient Profile")
    print("=" * 60)

    # Lade alle Daten
    print("\n[1/4] Lade Daten...")

    profiles = get_all_records(FOOD_NUTRIENT_TABLE)
    print(f"  {len(profiles)} Profiles geladen")

    interventions = get_all_records(INTERVENTIONS_TABLE)
    intervention_names = {r['id']: r['fields'].get('Name', 'Unknown') for r in interventions}
    print(f"  {len(interventions)} Interventions geladen")

    nutrients = get_all_records(NUTRIENTS_TABLE)
    nutrient_names = {r['id']: r['fields'].get('Name', '') or r['fields'].get('Nutrient Name', 'Unknown') for r in nutrients}
    print(f"  {len(nutrients)} Nutrients geladen")

    # Finde Duplikate
    print("\n[2/4] Suche Duplikate...")

    # Gruppiere nach Food+Nutrient Kombination
    combinations = defaultdict(list)

    for p in profiles:
        food_ids = p['fields'].get('Food', [])
        nutrient_ids = p['fields'].get('Nutrient', [])

        if food_ids and nutrient_ids:
            # Erstelle einen Key aus Food+Nutrient ID
            key = (tuple(sorted(food_ids)), tuple(sorted(nutrient_ids)))
            combinations[key].append(p)

    # Finde Kombinationen mit mehr als einem Eintrag
    duplicates = {k: v for k, v in combinations.items() if len(v) > 1}

    if not duplicates:
        print("  Keine Duplikate gefunden!")
        return

    print(f"  {len(duplicates)} Duplikat-Gruppen gefunden")

    # Zeige Details
    print("\n[3/4] Duplikat-Details:")
    records_to_delete = []

    for (food_ids, nutrient_ids), records in duplicates.items():
        food_name = intervention_names.get(food_ids[0], 'Unknown') if food_ids else 'Unknown'
        nutrient_name = nutrient_names.get(nutrient_ids[0], 'Unknown') if nutrient_ids else 'Unknown'

        print(f"\n  {food_name} + {nutrient_name}: {len(records)} Eintraege")

        # Sortiere nach Anzahl gefuellter Felder (mehr = behalten)
        records_sorted = sorted(records, key=lambda r: count_filled_fields(r['fields']), reverse=True)

        # Ersten behalten, Rest loeschen
        keep = records_sorted[0]
        delete = records_sorted[1:]

        print(f"    BEHALTEN: {keep['id'][:10]}... ({count_filled_fields(keep['fields'])} Felder)")
        for d in delete:
            print(f"    LOESCHEN: {d['id'][:10]}... ({count_filled_fields(d['fields'])} Felder)")
            records_to_delete.append(d['id'])

    if not records_to_delete:
        print("\n  Nichts zu loeschen!")
        return

    # Bestaetigung
    print(f"\n[4/4] Loesche {len(records_to_delete)} Duplikate...")

    deleted = 0
    errors = 0

    for record_id in records_to_delete:
        success = delete_record(FOOD_NUTRIENT_TABLE, record_id)
        if success:
            deleted += 1
            print(f"  Geloescht: {record_id[:10]}...")
        else:
            errors += 1
            print(f"  FEHLER bei: {record_id[:10]}...")

        # Rate limiting
        time.sleep(0.2)

    print("\n" + "=" * 60)
    print("FERTIG!")
    print("=" * 60)
    print(f"  Geloescht: {deleted}")
    print(f"  Fehler: {errors}")


if __name__ == "__main__":
    main()
