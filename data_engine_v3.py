"""
Alive Food Database - Data Engine v3
=====================================
Komplett neue, intelligente Data Engine die:
- ALLE Felder aus PDFs extrahiert
- ALLE Tabellen korrekt befuellt und verknuepft
- Intelligent Duplikate erkennt und erweitert
- Brick by brick die Datenbank aufbaut

Jede PDF fuegt Wissen hinzu - die Datenbank wird schlauer!
"""

import os
import json
import requests
import time
from typing import Dict, List, Any, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# =============================================================================
# CONFIGURATION
# =============================================================================

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appOFvKsPdHQQBOQ9")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

# Table IDs
TABLES = {
    "Sources": "tblcTzmqLRbvs0wAK",
    "Interventions": "tblccYj8xSOtfMAL2",
    "Outcomes": "tblSAOa5AVZLaFqjR",
    "Claims": "tblqHCZ4d3ttrkhQh",
    "Nutrients": "tblQo626zmoWlyZzW",
    "Food-Nutrient Profile": "tbl8HbmIrNpNHhrYH"
}

# Valid options for select fields - ALLE AIRTABLE OPTIONEN
VALID_OPTIONS = {
    "source_type": ["Book", "Study", "Article", "Website", "Video"],
    "intervention_type": ["Food", "Food group", "Food pattern", "Lifestyle", "Supplement (optional, future)"],
    "category": ["Fruit", "Vegetable", "Legume", "Whole grain", "Nuts & seeds",
                 "Herbs & spices", "Beverage", "Animal product", "Dietary pattern",
                 "Sleep", "Physical activity"],
    "intervention_scope": ["Ingredient", "Food group", "Dietary pattern", "Lifestyle factor"],
    "risk_framing": ["Actively encourage", "Neutral", "Context-dependent", "Limit", "Avoid"],
    "evidence_strength": ["Strong (RCT/Meta-analysis)", "Moderate (Cohort studies)",
                          "Preliminary (Observational)", "Mechanistic (In-vitro)"],
    # Nur existierende Airtable-Optionen! Mental Health -> Brain/Cognitive
    "health_category": ["Cardiovascular", "Brain/Cognitive", "Gut/Digestive",
                        "Metabolic", "Immune", "Inflammation", "Other"],
    "nutrient_category": ["Macronutrient", "Micronutrient", "Phytonutrient", "Other"],
    "nutrient_subcategory": ["Vitamin", "Mineral", "Amino Acid", "Fatty Acid",
                             "Fiber", "Polyphenol", "Carotenoid"],
    "unit": ["g", "mg", "mcg", "IU"],
    "confidence": ["High", "Medium", "Low"]
}


# =============================================================================
# AIRTABLE HELPER FUNCTIONS
# =============================================================================

def get_all_records(table_id: str) -> List[Dict]:
    """Holt alle Records einer Tabelle mit Pagination"""
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
            print(f"Error fetching records: {resp.status_code}")
            break

        data = resp.json()
        all_records.extend(data.get('records', []))
        offset = data.get('offset')

        if not offset:
            break

    return all_records


def create_record(table_id: str, fields: Dict) -> Optional[str]:
    """Erstellt einen neuen Record und gibt die ID zurueck"""
    resp = requests.post(
        f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
        headers=HEADERS,
        json={"fields": fields}
    )

    if resp.status_code == 200:
        return resp.json().get('id')
    else:
        print(f"Error creating record: {resp.status_code} - {resp.text[:200]}")
        return None


def update_record(table_id: str, record_id: str, fields: Dict) -> bool:
    """Aktualisiert einen bestehenden Record"""
    resp = requests.patch(
        f"https://api.airtable.com/v0/{BASE_ID}/{table_id}/{record_id}",
        headers=HEADERS,
        json={"fields": fields}
    )
    return resp.status_code == 200


def normalize_name(name: str) -> str:
    """Normalisiert Namen fuer Duplikat-Erkennung"""
    if not name:
        return ""
    normalized = name.lower().strip()
    # Entferne Sonderzeichen
    for char in ['(', ')', '-', '_', ',', '.']:
        normalized = normalized.replace(char, ' ')
    # Mehrere Leerzeichen zu einem
    normalized = ' '.join(normalized.split())
    return normalized


# =============================================================================
# DATABASE CACHE - Haelt alle existierenden Records im Speicher
# =============================================================================

class DatabaseCache:
    """Cache fuer alle existierenden Records um API-Calls zu minimieren"""

    def __init__(self):
        self.sources = {}          # normalized_name -> {id, fields}
        self.interventions = {}    # normalized_name -> {id, fields}
        self.outcomes = {}         # normalized_name -> {id, fields}
        self.nutrients = {}        # normalized_name -> {id, fields}
        self.claims = []           # Liste von {id, fields}
        self.profiles = []         # Liste von {id, fields}
        self.loaded = False

    def load(self):
        """Laedt alle existierenden Records"""
        print("Lade Datenbank-Cache...")

        # Sources
        for r in get_all_records(TABLES["Sources"]):
            name = r['fields'].get('Source (canonical name)', '')
            self.sources[normalize_name(name)] = {'id': r['id'], 'fields': r['fields']}

        # Interventions
        for r in get_all_records(TABLES["Interventions"]):
            name = r['fields'].get('Name', '')
            self.interventions[normalize_name(name)] = {'id': r['id'], 'fields': r['fields']}

        # Outcomes
        for r in get_all_records(TABLES["Outcomes"]):
            name = r['fields'].get('Name', '')
            self.outcomes[normalize_name(name)] = {'id': r['id'], 'fields': r['fields']}

        # Nutrients
        for r in get_all_records(TABLES["Nutrients"]):
            name = r['fields'].get('Name', '') or r['fields'].get('Nutrient Name', '')
            self.nutrients[normalize_name(name)] = {'id': r['id'], 'fields': r['fields']}

        # Claims
        for r in get_all_records(TABLES["Claims"]):
            self.claims.append({'id': r['id'], 'fields': r['fields']})

        # Profiles
        for r in get_all_records(TABLES["Food-Nutrient Profile"]):
            self.profiles.append({'id': r['id'], 'fields': r['fields']})

        self.loaded = True
        print(f"  Sources: {len(self.sources)}")
        print(f"  Interventions: {len(self.interventions)}")
        print(f"  Outcomes: {len(self.outcomes)}")
        print(f"  Nutrients: {len(self.nutrients)}")
        print(f"  Claims: {len(self.claims)}")
        print(f"  Profiles: {len(self.profiles)}")


# =============================================================================
# INTELLIGENT EXTRACTION - KI extrahiert ALLE relevanten Daten
# =============================================================================

EXTRACTION_PROMPT = """Du bist ein Ernaehrungswissenschaftler und Datenbank-Experte.
Analysiere den folgenden wissenschaftlichen Text und extrahiere ALLE relevanten Informationen.

WICHTIG:
- Extrahiere SO VIELE Details wie moeglich!
- Jedes Feld das du fuellen kannst, fuellst du.
- Lass KEIN Feld leer wenn du Informationen dazu findest!

Antworte NUR mit validem JSON in diesem EXAKTEN Format:

{
    "source": {
        "title": "Vollstaendiger Titel der Studie/des Buches",
        "type": "Study|Book|Article|Website|Video",
        "authors": "Autor1, Autor2, ...",
        "year": 2024,
        "journal": "Name des Journals oder Verlags",
        "doi": "DOI wenn vorhanden (z.B. 10.3390/nu123456)",
        "isbn": "ISBN wenn es ein Buch ist",
        "url": "URL wenn vorhanden",
        "total_pages": 14,
        "notes": "Zusammenfassung: Was ist das Hauptthema dieser Quelle?"
    },

    "foods": [
        {
            "name": "Name des Foods (z.B. Blueberries, Flaxseed)",
            "type": "Food|Food group|Food pattern|Lifestyle",
            "category": "Fruit|Vegetable|Legume|Whole grain|Nuts & seeds|Herbs & spices|Beverage|Animal product",
            "intervention_scope": "Ingredient|Food group|Dietary pattern|Lifestyle factor",
            "is_plant_based": true,
            "is_whole_food": true,
            "is_negative_risk": false,
            "risk_framing": "Actively encourage|Neutral|Context-dependent|Limit|Avoid",
            "nutritional_roles": ["Antioxidants", "Fiber", "Polyphenols", "Omega-3", "Protein"],
            "culinary_roles": ["Topping", "Snack", "Smoothie ingredient", "Main dish", "Side dish"],
            "example_serving": "1 cup (148g)",
            "serving_size_grams": 148,
            "typical_uses": "Breakfast bowls, Smoothies, Snacks, Baking",
            "preparation_notes": "Fresh or frozen, no added sugar. Best consumed raw.",
            "summary": "2-3 Saetze die erklaeren WARUM dieses Food gesund ist und was es besonders macht",
            "internal_notes": "Zusaetzliche Notizen fuer interne Verwendung",
            "discovery_pages": "pp. 3-5, 12"
        }
    ],

    "health_outcomes": [
        {
            "name": "Name des Health Outcomes (z.B. Heart Health, Brain Function, Anxiety Reduction)",
            "category": "Brain/Cognitive|Cardiovascular|Gut/Digestive|Metabolic|Immune|Inflammation|Other",
            "notes": "Detaillierte Beschreibung was dieser Outcome bedeutet und wie er gemessen wird"
        }
    ],

    "claims": [
        {
            "food_name": "Name des Foods (muss mit einem Food oben uebereinstimmen)",
            "outcome_names": ["Health Outcome 1", "Health Outcome 2"],
            "claim_text": "Der vollstaendige Health Claim - was GENAU wurde herausgefunden? Sei spezifisch!",
            "evidence_strength": "Strong (RCT/Meta-analysis)|Moderate (Cohort studies)|Preliminary (Observational)|Mechanistic (In-vitro)",
            "page_reference": "p. 5, pp. 12-15",
            "study_details": "Details zur Studie: n=245, 12 Wochen, doppelblind etc."
        }
    ],

    "nutrients": [
        {
            "food_name": "Name des Foods",
            "serving_size": "1 cup",
            "serving_size_grams": 148,
            "nutrients": [
                {
                    "name": "Anthocyanins",
                    "amount_per_100g": 164.0,
                    "amount_per_serving": 242.7,
                    "unit": "mg|g|mcg|IU",
                    "daily_value_percent": 0,
                    "category": "Macronutrient|Micronutrient|Phytonutrient|Other",
                    "subcategory": "Vitamin|Mineral|Amino Acid|Fatty Acid|Fiber|Polyphenol|Carotenoid",
                    "health_benefits": "Beschreibung der gesundheitlichen Vorteile dieses Naehrstoffs",
                    "confidence": "High|Medium|Low"
                }
            ]
        }
    ]
}

WICHTIGE REGELN:
1. Extrahiere JEDEN Food der erwaehnt wird - auch wenn nur kurz
2. Extrahiere JEDEN Health Claim - auch subtile Aussagen wie "may support" oder "associated with"
3. Extrahiere ALLE Naehrstoffdaten mit Mengenangaben
4. Bei Portionsgroessen: Berechne auch die Gramm-Angabe wenn moeglich
5. Bei Nutrients: Berechne amount_per_serving aus amount_per_100g und serving_size_grams
6. Verwende die EXAKTEN Kategorien aus den Optionen (vor dem |)
7. Bei Health Outcomes: Erstelle spezifische Outcomes (z.B. "Anxiety Reduction" statt nur "Mental Health")
8. Die Zusammenfassung (summary) sollte erklaeren WARUM dieses Food gesund ist
9. Bei evidence_strength: Waehle basierend auf Studientyp (RCT > Cohort > Observational > In-vitro)
10. Wenn du dir nicht sicher bist, verwende "Medium" als Confidence

TEXT ZUM ANALYSIEREN:
"""


def extract_with_ai(text: str, model: str = "gpt-4o-mini") -> Optional[Dict]:
    """Extrahiert alle Daten aus Text mit KI"""
    if not HAS_OPENAI or not OPENAI_API_KEY:
        print("OpenAI nicht verfuegbar")
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Text kuerzen wenn zu lang
    if len(text) > 60000:
        text = text[:60000]

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Du bist ein Ernaehrungswissenschaftler. Extrahiere ALLE Daten praezise. Antworte NUR mit validem JSON."
            },
            {"role": "user", "content": EXTRACTION_PROMPT + text}
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=4000
    )

    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError as e:
        print(f"JSON Parse Error: {e}")
        return None


# =============================================================================
# INTELLIGENT IMPORT - Baut die Datenbank brick by brick auf
# =============================================================================

class DataImporter:
    """Importiert extrahierte Daten intelligent in Airtable"""

    def __init__(self, cache: DatabaseCache):
        self.cache = cache
        self.stats = {
            "sources_created": 0,
            "sources_updated": 0,
            "interventions_created": 0,
            "interventions_updated": 0,
            "outcomes_created": 0,
            "outcomes_updated": 0,
            "claims_created": 0,
            "nutrients_created": 0,
            "profiles_created": 0,
            "errors": []
        }
        self.source_id = None
        self.food_ids = {}  # name -> id
        self.outcome_ids = {}  # name -> id
        self.nutrient_ids = {}  # name -> id

    def import_all(self, data: Dict) -> Dict:
        """Importiert alle extrahierten Daten"""
        print("\n" + "="*60)
        print("STARTE IMPORT")
        print("="*60)

        # 1. Source erstellen/finden
        self._import_source(data.get('source', {}))

        # 2. Health Outcomes erstellen/finden
        for outcome in data.get('health_outcomes', []):
            self._import_outcome(outcome)

        # 3. Foods (Interventions) erstellen/aktualisieren
        for food in data.get('foods', []):
            self._import_food(food)

        # 4. Claims erstellen
        for claim in data.get('claims', []):
            self._import_claim(claim)

        # 5. Nutrients und Profiles erstellen
        for nutrient_set in data.get('nutrients', []):
            self._import_nutrients(nutrient_set)

        print("\n" + "="*60)
        print("IMPORT ABGESCHLOSSEN")
        print("="*60)
        self._print_stats()

        return self.stats

    def _import_source(self, source_data: Dict):
        """Erstellt oder findet eine Source"""
        title = source_data.get('title', 'Unknown Source')
        normalized = normalize_name(title)

        print(f"\n[SOURCE] {title[:50]}...")

        # Existiert bereits?
        if normalized in self.cache.sources:
            existing = self.cache.sources[normalized]
            self.source_id = existing['id']
            print(f"  -> Existiert bereits (ID: {self.source_id[:10]}...)")

            # Aktualisiere fehlende Felder
            updates = {}
            existing_fields = existing['fields']

            if not existing_fields.get('Author(s)') and source_data.get('authors'):
                updates['Author(s)'] = source_data['authors']
            if not existing_fields.get('Year') and source_data.get('year'):
                updates['Year'] = source_data['year']
            if not existing_fields.get('Publisher/Journal') and source_data.get('journal'):
                updates['Publisher/Journal'] = source_data['journal']
            if not existing_fields.get('Notes') and source_data.get('notes'):
                updates['Notes'] = source_data['notes']

            if updates:
                update_record(TABLES["Sources"], self.source_id, updates)
                self.stats["sources_updated"] += 1
                print(f"  -> Aktualisiert: {list(updates.keys())}")
            return

        # Neu erstellen
        fields = {
            "Source (canonical name)": title,
            "Source Type": self._validate_option(source_data.get('type', 'Study'), 'source_type'),
        }

        # Optionale Felder
        if source_data.get('authors'):
            fields['Author(s)'] = source_data['authors']
        if source_data.get('year'):
            fields['Year'] = int(source_data['year'])
        if source_data.get('journal'):
            fields['Publisher/Journal'] = source_data['journal']
        if source_data.get('doi'):
            fields['ISBN/DOI'] = source_data['doi']
        if source_data.get('url'):
            fields['URL'] = source_data['url']
        if source_data.get('total_pages'):
            fields['Total Pages'] = int(source_data['total_pages'])
        if source_data.get('notes'):
            fields['Notes'] = source_data['notes']

        self.source_id = create_record(TABLES["Sources"], fields)
        if self.source_id:
            self.stats["sources_created"] += 1
            self.cache.sources[normalized] = {'id': self.source_id, 'fields': fields}
            print(f"  -> NEU erstellt (ID: {self.source_id[:10]}...)")
        else:
            self.stats["errors"].append(f"Konnte Source nicht erstellen: {title}")

    def _import_outcome(self, outcome_data: Dict):
        """Erstellt oder findet ein Health Outcome"""
        name = outcome_data.get('name', '')
        if not name:
            return

        normalized = normalize_name(name)

        # Existiert bereits?
        if normalized in self.cache.outcomes:
            self.outcome_ids[name.lower()] = self.cache.outcomes[normalized]['id']
            return

        print(f"\n[OUTCOME] {name}")

        fields = {
            "Name": name,
        }

        if outcome_data.get('category'):
            fields['Health Category'] = self._validate_option(outcome_data['category'], 'health_category')
        if outcome_data.get('notes'):
            fields['Notes'] = outcome_data['notes']

        outcome_id = create_record(TABLES["Outcomes"], fields)
        if outcome_id:
            self.stats["outcomes_created"] += 1
            self.outcome_ids[name.lower()] = outcome_id
            self.cache.outcomes[normalized] = {'id': outcome_id, 'fields': fields}
            print(f"  -> NEU erstellt")
        else:
            self.stats["errors"].append(f"Konnte Outcome nicht erstellen: {name}")

    def _import_food(self, food_data: Dict):
        """Erstellt oder aktualisiert ein Food (Intervention)"""
        name = food_data.get('name', '')
        if not name:
            return

        normalized = normalize_name(name)
        print(f"\n[FOOD] {name}")

        # Existiert bereits?
        if normalized in self.cache.interventions:
            existing = self.cache.interventions[normalized]
            food_id = existing['id']
            self.food_ids[name.lower()] = food_id
            print(f"  -> Existiert bereits (ID: {food_id[:10]}...)")

            # Aktualisiere/Erweitere fehlende Felder
            updates = {}
            existing_fields = existing['fields']

            # Fuege Source hinzu wenn noch nicht verknuepft
            if self.source_id:
                existing_sources = existing_fields.get('Discovery source (book / resource)', [])
                if self.source_id not in existing_sources:
                    updates['Discovery source (book / resource)'] = existing_sources + [self.source_id]

            # Ergaenze fehlende Felder
            if not existing_fields.get('Short summary (human-readable)') and food_data.get('summary'):
                updates['Short summary (human-readable)'] = food_data['summary']
            if not existing_fields.get('Example serving') and food_data.get('example_serving'):
                updates['Example serving'] = food_data['example_serving']
            if not existing_fields.get('Typical use cases') and food_data.get('typical_uses'):
                updates['Typical use cases'] = food_data['typical_uses']
            if not existing_fields.get('Preparation notes') and food_data.get('preparation_notes'):
                updates['Preparation notes'] = food_data['preparation_notes']

            # Ergaenze Discovery Pages
            existing_pages = existing_fields.get('Discovery pages', '')
            new_pages = food_data.get('discovery_pages', '')
            if new_pages and new_pages not in existing_pages:
                if existing_pages:
                    updates['Discovery pages'] = f"{existing_pages}; {new_pages}"
                else:
                    updates['Discovery pages'] = new_pages

            if updates:
                update_record(TABLES["Interventions"], food_id, updates)
                self.stats["interventions_updated"] += 1
                print(f"  -> Aktualisiert: {list(updates.keys())}")
            return

        # Neu erstellen - ALLE FELDER
        fields = {
            "Name": name,
            "Type (STRICT)": self._validate_option(food_data.get('type', 'Food'), 'intervention_type'),
            "Category": self._validate_option(food_data.get('category', 'Fruit'), 'category'),
        }

        # Intervention Scope
        if food_data.get('intervention_scope'):
            fields['Intervention scope'] = self._validate_option(food_data['intervention_scope'], 'intervention_scope')

        # Checkboxen
        if food_data.get('is_plant_based') is not None:
            fields['Is plant-based?'] = bool(food_data['is_plant_based'])
        if food_data.get('is_whole_food') is not None:
            fields['Is whole food?'] = bool(food_data['is_whole_food'])
        if food_data.get('is_negative_risk') is not None:
            fields['Is negative / risk factor?'] = bool(food_data['is_negative_risk'])

        # Risk Framing
        if food_data.get('risk_framing'):
            fields['Risk framing (editorial)'] = self._validate_option(food_data['risk_framing'], 'risk_framing')

        # Text Felder
        if food_data.get('example_serving'):
            fields['Example serving'] = food_data['example_serving']
        if food_data.get('typical_uses'):
            fields['Typical use cases'] = food_data['typical_uses']
        if food_data.get('preparation_notes'):
            fields['Preparation notes'] = food_data['preparation_notes']
        if food_data.get('summary'):
            fields['Short summary (human-readable)'] = food_data['summary']
        if food_data.get('internal_notes'):
            fields['Internal notes'] = food_data['internal_notes']
        if food_data.get('discovery_pages'):
            fields['Discovery pages'] = food_data['discovery_pages']

        # Multi-Select Felder
        if food_data.get('nutritional_roles'):
            fields['Nutritional role (high-level)'] = food_data['nutritional_roles'][:5]
        if food_data.get('culinary_roles'):
            fields['Culinary role'] = food_data['culinary_roles'][:5]

        # Source verknuepfen
        if self.source_id:
            fields['Discovery source (book / resource)'] = [self.source_id]

        food_id = create_record(TABLES["Interventions"], fields)
        if food_id:
            self.stats["interventions_created"] += 1
            self.food_ids[name.lower()] = food_id
            self.cache.interventions[normalized] = {'id': food_id, 'fields': fields}
            print(f"  -> NEU erstellt (ID: {food_id[:10]}...)")
        else:
            self.stats["errors"].append(f"Konnte Food nicht erstellen: {name}")

    def _import_claim(self, claim_data: Dict):
        """Erstellt einen neuen Claim mit allen Verknuepfungen"""
        food_name = claim_data.get('food_name', '')
        claim_text = claim_data.get('claim_text', '')

        if not food_name or not claim_text:
            return

        print(f"\n[CLAIM] {food_name}: {claim_text[:50]}...")

        # Food ID holen
        food_id = self.food_ids.get(food_name.lower())
        if not food_id:
            # Versuche in Cache zu finden
            normalized = normalize_name(food_name)
            if normalized in self.cache.interventions:
                food_id = self.cache.interventions[normalized]['id']
                self.food_ids[food_name.lower()] = food_id

        if not food_id:
            print(f"  -> FEHLER: Food '{food_name}' nicht gefunden")
            self.stats["errors"].append(f"Food nicht gefunden fuer Claim: {food_name}")
            return

        # Outcome IDs sammeln
        outcome_ids = []
        for outcome_name in claim_data.get('outcome_names', []):
            # Erst in unseren neuen IDs suchen
            outcome_id = self.outcome_ids.get(outcome_name.lower())
            if not outcome_id:
                # Dann im Cache
                normalized = normalize_name(outcome_name)
                if normalized in self.cache.outcomes:
                    outcome_id = self.cache.outcomes[normalized]['id']
                else:
                    # Outcome erstellen wenn nicht vorhanden
                    # Versuche Kategorie aus dem Namen abzuleiten
                    default_cat = 'Brain/Cognitive'  # Default fuer Mental Health Outcomes
                    if 'heart' in outcome_name.lower() or 'cardio' in outcome_name.lower():
                        default_cat = 'Cardiovascular'
                    elif 'gut' in outcome_name.lower() or 'digest' in outcome_name.lower():
                        default_cat = 'Gut/Digestive'
                    elif 'inflam' in outcome_name.lower():
                        default_cat = 'Inflammation'
                    self._import_outcome({'name': outcome_name, 'category': default_cat})
                    outcome_id = self.outcome_ids.get(outcome_name.lower())

            if outcome_id:
                outcome_ids.append(outcome_id)

        if not outcome_ids:
            print(f"  -> WARNUNG: Keine Outcomes gefunden")

        # Pruefe ob Claim schon existiert (gleicher Text + Food)
        for existing in self.cache.claims:
            if existing['fields'].get('Claim Text') == claim_text:
                existing_foods = existing['fields'].get('Intervention', [])
                if food_id in existing_foods:
                    print(f"  -> Existiert bereits")
                    return

        # Claim erstellen
        fields = {
            "Intervention": [food_id],
            "Claim Text": claim_text,
            "Evidence Strength": self._validate_option(
                claim_data.get('evidence_strength', 'Moderate (Cohort studies)'),
                'evidence_strength'
            ),
        }

        if outcome_ids:
            fields["Health Outcome"] = outcome_ids
        if self.source_id:
            fields["Source"] = [self.source_id]
        if claim_data.get('page_reference'):
            fields["Page Reference"] = claim_data['page_reference']

        claim_id = create_record(TABLES["Claims"], fields)
        if claim_id:
            self.stats["claims_created"] += 1
            self.cache.claims.append({'id': claim_id, 'fields': fields})
            print(f"  -> NEU erstellt")
        else:
            self.stats["errors"].append(f"Konnte Claim nicht erstellen")

    def _import_nutrients(self, nutrient_set: Dict):
        """Erstellt Nutrients und Food-Nutrient Profiles"""
        food_name = nutrient_set.get('food_name', '')
        if not food_name:
            return

        # Food ID holen
        food_id = self.food_ids.get(food_name.lower())
        if not food_id:
            normalized = normalize_name(food_name)
            if normalized in self.cache.interventions:
                food_id = self.cache.interventions[normalized]['id']

        if not food_id:
            return

        for nutrient_data in nutrient_set.get('nutrients', []):
            nutrient_name = nutrient_data.get('name', '')
            if not nutrient_name:
                continue

            # Nutrient erstellen/finden
            normalized = normalize_name(nutrient_name)

            if normalized in self.cache.nutrients:
                nutrient_id = self.cache.nutrients[normalized]['id']
            else:
                # Neu erstellen - ALLE FELDER
                fields = {
                    "Name": nutrient_name,
                    "Nutrient Name": nutrient_name,
                }

                # Kategorie
                if nutrient_data.get('category'):
                    fields['Category'] = self._validate_option(nutrient_data['category'], 'nutrient_category')

                # Subkategorie
                if nutrient_data.get('subcategory'):
                    fields['Subcategory'] = self._validate_option(nutrient_data['subcategory'], 'nutrient_subcategory')

                # Unit
                if nutrient_data.get('unit'):
                    fields['Unit'] = self._validate_option(nutrient_data['unit'], 'unit')

                # Daily Value
                if nutrient_data.get('daily_value_percent') and nutrient_data['daily_value_percent'] > 0:
                    fields['Daily Value'] = float(nutrient_data['daily_value_percent'])

                # Health Benefits
                if nutrient_data.get('health_benefits'):
                    fields['Health Benefits'] = nutrient_data['health_benefits']

                nutrient_id = create_record(TABLES["Nutrients"], fields)
                if nutrient_id:
                    self.stats["nutrients_created"] += 1
                    self.cache.nutrients[normalized] = {'id': nutrient_id, 'fields': fields}
                else:
                    continue

            # Pruefe ob Profile schon existiert
            profile_exists = False
            for p in self.cache.profiles:
                p_foods = p['fields'].get('Food', [])
                p_nutrients = p['fields'].get('Nutrient', [])
                if food_id in p_foods and nutrient_id in p_nutrients:
                    profile_exists = True
                    break

            if profile_exists:
                continue

            # Food-Nutrient Profile erstellen - ALLE FELDER
            profile_fields = {
                "Food": [food_id],
                "Nutrient": [nutrient_id],
            }

            # Amount per 100g
            if nutrient_data.get('amount_per_100g') is not None:
                profile_fields['Amount per 100g'] = float(nutrient_data['amount_per_100g'])

            # Serving Size (aus nutrient_set, nicht nutrient_data)
            serving_size = nutrient_set.get('serving_size', '')
            serving_grams = nutrient_set.get('serving_size_grams', 0)

            if serving_size:
                profile_fields['Serving Size'] = serving_size
            if serving_grams and serving_grams > 0:
                profile_fields['Serving Size Grams'] = float(serving_grams)

            # Amount per Serving (berechnen oder aus Daten)
            if nutrient_data.get('amount_per_serving') is not None:
                profile_fields['Amount per Serving'] = float(nutrient_data['amount_per_serving'])
            elif nutrient_data.get('amount_per_100g') and serving_grams:
                # Berechne Amount per Serving
                amount_per_serving = (float(nutrient_data['amount_per_100g']) * float(serving_grams)) / 100
                profile_fields['Amount per Serving'] = round(amount_per_serving, 2)

            # Confidence Level
            if nutrient_data.get('confidence'):
                profile_fields['Confidence Level'] = self._validate_option(nutrient_data['confidence'], 'confidence')

            # Source Reference
            if self.source_id:
                profile_fields['Source Reference'] = f"Source ID: {self.source_id}"

            profile_id = create_record(TABLES["Food-Nutrient Profile"], profile_fields)
            if profile_id:
                self.stats["profiles_created"] += 1
                self.cache.profiles.append({'id': profile_id, 'fields': profile_fields})

    def _validate_option(self, value: str, option_type: str) -> str:
        """Validiert und korrigiert Select-Optionen"""
        if not value:
            return VALID_OPTIONS[option_type][0]

        # Spezielle Mappings fuer nicht-existierende Optionen
        CATEGORY_MAPPINGS = {
            "mental health": "Brain/Cognitive",
            "mental": "Brain/Cognitive",
            "anxiety": "Brain/Cognitive",
            "depression": "Brain/Cognitive",
            "mood": "Brain/Cognitive",
            "cognitive": "Brain/Cognitive",
            "brain": "Brain/Cognitive",
            "heart": "Cardiovascular",
            "cardiac": "Cardiovascular",
            "cancer": "Immune",
            "longevity": "Metabolic",
            "bone": "Other",
        }

        valid = VALID_OPTIONS.get(option_type, [])
        value_lower = value.lower().strip()

        # Spezielle Mappings pruefen
        if option_type == 'health_category':
            for key, mapped in CATEGORY_MAPPINGS.items():
                if key in value_lower:
                    return mapped

        # Exakter Match
        if value in valid:
            return value

        # Case-insensitive Match
        for opt in valid:
            if opt.lower() == value_lower:
                return opt

        # Partial Match
        for opt in valid:
            if value_lower in opt.lower() or opt.lower() in value_lower:
                return opt

        # Default
        return valid[0] if valid else value

    def _print_stats(self):
        """Gibt Statistiken aus"""
        print(f"\nStatistiken:")
        print(f"  Sources:       {self.stats['sources_created']} neu, {self.stats['sources_updated']} aktualisiert")
        print(f"  Foods:         {self.stats['interventions_created']} neu, {self.stats['interventions_updated']} aktualisiert")
        print(f"  Outcomes:      {self.stats['outcomes_created']} neu")
        print(f"  Claims:        {self.stats['claims_created']} neu")
        print(f"  Nutrients:     {self.stats['nutrients_created']} neu")
        print(f"  Profiles:      {self.stats['profiles_created']} neu")

        if self.stats['errors']:
            print(f"\n  Fehler ({len(self.stats['errors'])}):")
            for err in self.stats['errors'][:5]:
                print(f"    - {err}")


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def process_and_import(text: str, progress_callback=None) -> Dict:
    """
    Hauptfunktion: Extrahiert Daten aus Text und importiert sie in Airtable

    Args:
        text: Der zu analysierende Text (aus PDF etc.)
        progress_callback: Optional callback fuer Progress Updates

    Returns:
        Dict mit Statistiken
    """
    if progress_callback:
        progress_callback("Lade Datenbank-Cache...")

    # Cache laden
    cache = DatabaseCache()
    cache.load()

    if progress_callback:
        progress_callback("Extrahiere Daten mit KI...")

    # Mit KI extrahieren
    extracted = extract_with_ai(text)

    if not extracted:
        return {"error": "KI-Extraktion fehlgeschlagen"}

    if progress_callback:
        progress_callback("Importiere in Airtable...")

    # Importieren
    importer = DataImporter(cache)
    stats = importer.import_all(extracted)

    # Extrahierte Daten fuer Anzeige hinzufuegen
    stats['extracted_data'] = extracted

    return stats


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    # Test mit Beispieltext
    test_text = """
    Blueberry Supplementation and Mental Health

    This narrative review examines the effects of blueberry supplementation on mental health outcomes.

    Blueberries are rich in anthocyanins (164mg/100g), which have been shown to have neuroprotective effects.
    They also contain Vitamin C (9.7mg/100g) and dietary fiber (2.4g/100g).

    Key findings:
    - Blueberry supplementation can ameliorate behavioral symptoms of both anxiety and depression
    - The anthocyanins in blueberries cross the blood-brain barrier
    - Regular consumption (1 cup daily) is associated with improved cognitive function

    Recommended serving: 1 cup (148g) fresh or frozen blueberries
    Best consumed: In smoothies, breakfast bowls, or as a snack
    """

    result = process_and_import(test_text)
    print("\n" + "="*60)
    print("ERGEBNIS:")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
