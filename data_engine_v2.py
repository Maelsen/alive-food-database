"""
Alive Food Database - Data Engine v2.0
======================================
Vollstaendige, skalierbare Extraktion aus Studien/PDFs.

Features:
- Liest ALLE Felder dynamisch aus Airtable Schema
- Extrahiert Health Claims UND Naehrstoffdaten
- Fuellt ALLE relevanten Felder intelligent aus
- Erkennt neue Felder automatisch

Usage:
    python data_engine_v2.py study.pdf
    python data_engine_v2.py notes.txt --model gpt-4o-mini
"""

import os
import json
import requests
from pathlib import Path
from typing import Optional, Dict, List, Any
import time

# .env Datei laden
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv nicht installiert, nutze Umgebungsvariablen

# PDF Support
try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

# OpenAI Support
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

# Table IDs
TABLES = {
    "Interventions": "tblccYj8xSOtfMAL2",
    "Outcomes": "tblSAOa5AVZLaFqjR",
    "Claims": "tblqHCZ4d3ttrkhQh",
    "Sources": "tblcTzmqLRbvs0wAK",
    "Nutrients": "tblQo626zmoWlyZzW",
    "Food-Nutrient Profile": "tbl8HbmIrNpNHhrYH"
}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}


# =============================================================================
# SCHEMA READER - Liest alle Felder dynamisch aus Airtable
# =============================================================================

class SchemaReader:
    """Liest das aktuelle Airtable Schema dynamisch"""

    def __init__(self):
        self.schema = {}
        self.field_options = {}  # Speichert gueltige Optionen fuer Single/Multi Select
        self._load_schema()

    def _load_schema(self):
        """Laedt das komplette Schema von Airtable"""
        resp = requests.get(
            f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables",
            headers=HEADERS
        )

        if resp.status_code != 200:
            print(f"Warnung: Konnte Schema nicht laden ({resp.status_code})")
            return

        for table in resp.json().get('tables', []):
            table_name = table['name']
            self.schema[table_name] = {
                'id': table['id'],
                'fields': {}
            }

            for field in table.get('fields', []):
                field_name = field['name']
                field_type = field['type']

                self.schema[table_name]['fields'][field_name] = {
                    'id': field['id'],
                    'type': field_type
                }

                # Speichere gueltige Optionen fuer Select-Felder
                if field_type in ['singleSelect', 'multipleSelects']:
                    options = field.get('options', {}).get('choices', [])
                    self.field_options[f"{table_name}.{field_name}"] = [
                        opt.get('name') for opt in options
                    ]

        print(f"Schema geladen: {len(self.schema)} Tabellen")

    def get_valid_options(self, table_name: str, field_name: str) -> List[str]:
        """Gibt gueltige Optionen fuer ein Select-Feld zurueck"""
        key = f"{table_name}.{field_name}"
        return self.field_options.get(key, [])

    def get_fields(self, table_name: str) -> Dict:
        """Gibt alle Felder einer Tabelle zurueck"""
        return self.schema.get(table_name, {}).get('fields', {})


# =============================================================================
# AIRTABLE DATABASE CLASS
# =============================================================================

def normalize_name(name: str) -> str:
    """
    Normalisiert einen Namen für bessere Duplicate Detection.
    z.B. "Omega-3 ALA" == "Omega-3 (ALA)" == "omega 3 ala"
    """
    if not name:
        return ""
    # Lowercase
    normalized = name.lower()
    # Entferne Klammern und deren Inhalt wird behalten
    normalized = normalized.replace('(', ' ').replace(')', ' ')
    # Ersetze Bindestriche und Unterstriche durch Leerzeichen
    normalized = normalized.replace('-', ' ').replace('_', ' ')
    # Entferne mehrfache Leerzeichen
    normalized = ' '.join(normalized.split())
    # Entferne führende/trailing Leerzeichen
    normalized = normalized.strip()
    return normalized


# Standard Serving Sizes für verschiedene Food-Kategorien
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

# Spezifische Serving Sizes für bekannte Foods
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
    "turmeric": {"serving": "1 tsp", "grams": 3},
}


class AirtableDB:
    """Verwaltet alle Airtable Operationen"""

    def __init__(self, schema: SchemaReader):
        self.schema = schema
        self.cache = {
            'interventions': {},
            'outcomes': {},
            'sources': {},
            'nutrients': {}
        }
        # Normalisierte Namen für Duplicate Detection
        self.normalized_cache = {
            'interventions': {},
            'outcomes': {},
            'sources': {},
            'nutrients': {}
        }
        self._load_existing()

    def _load_existing(self):
        """Laedt existierende Records in den Cache mit normalisierter Duplikaterkennung"""
        # Interventions
        records = self._get_all_records(TABLES["Interventions"])
        for r in records:
            name = r['fields'].get('Name', '')
            if name:
                key = name.lower()
                self.cache['interventions'][key] = r['id']
                # Auch normalisierte Version speichern
                normalized = normalize_name(name)
                self.normalized_cache['interventions'][normalized] = r['id']

        # Outcomes
        records = self._get_all_records(TABLES["Outcomes"])
        for r in records:
            name = r['fields'].get('Name', '')
            if name:
                key = name.lower()
                self.cache['outcomes'][key] = r['id']
                normalized = normalize_name(name)
                self.normalized_cache['outcomes'][normalized] = r['id']

        # Sources
        records = self._get_all_records(TABLES["Sources"])
        for r in records:
            name = r['fields'].get('Source (canonical name)', '')
            if name:
                key = name.lower()
                self.cache['sources'][key] = r['id']
                normalized = normalize_name(name)
                self.normalized_cache['sources'][normalized] = r['id']

        # Nutrients - mit erweiterter Duplikaterkennung
        records = self._get_all_records(TABLES["Nutrients"])
        for r in records:
            name = r['fields'].get('Name', '')
            if name:
                key = name.lower()
                self.cache['nutrients'][key] = r['id']
                normalized = normalize_name(name)
                self.normalized_cache['nutrients'][normalized] = r['id']

        print(f"Cache geladen: {len(self.cache['interventions'])} Interventions, "
              f"{len(self.cache['outcomes'])} Outcomes, "
              f"{len(self.cache['sources'])} Sources, "
              f"{len(self.cache['nutrients'])} Nutrients")

    def _get_all_records(self, table_id: str) -> List[Dict]:
        """Holt alle Records einer Tabelle (mit Pagination)"""
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
                print(f"Fehler beim Laden: {resp.status_code}")
                break

            data = resp.json()
            all_records.extend(data.get('records', []))
            offset = data.get('offset')

            if not offset:
                break

        return all_records

    def _create_record(self, table_id: str, fields: Dict) -> Optional[str]:
        """Erstellt einen neuen Record"""
        resp = requests.post(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=HEADERS,
            json={"records": [{"fields": fields}]}
        )

        if resp.status_code == 200:
            return resp.json()['records'][0]['id']
        else:
            print(f"  Fehler: {resp.text[:200]}")
            return None

    def _validate_select_value(self, table_name: str, field_name: str, value: Any) -> Any:
        """Validiert und filtert Select-Werte"""
        valid_options = self.schema.get_valid_options(table_name, field_name)

        if not valid_options:
            return value

        if isinstance(value, list):
            return [v for v in value if v in valid_options]
        else:
            return value if value in valid_options else None

    def get_or_create_source(self, data: Dict) -> str:
        """Holt oder erstellt eine Source mit ALLEN Feldern"""
        title = data.get('title', 'Unknown Source')
        key = title.lower()

        if key in self.cache['sources']:
            return self.cache['sources'][key]

        fields = {"Source (canonical name)": title}

        # Alle Source-Felder mappen
        field_mapping = {
            'source_type': 'Source Type',
            'authors': 'Author(s)',
            'year': 'Year',
            'publisher': 'Publisher/Journal',
            'isbn_doi': 'ISBN/DOI',
            'url': 'URL',
            'total_pages': 'Total Pages',
            'notes': 'Notes',
            'file_path': 'Notes'  # Lokaler Pfad wird in Notes gespeichert
        }

        for data_key, field_name in field_mapping.items():
            if data_key in data and data[data_key]:
                value = data[data_key]
                # Source Type validieren
                if field_name == 'Source Type':
                    value = self._validate_select_value("Sources", field_name, value)
                if value:
                    if field_name == 'Notes' and data_key == 'file_path':
                        # Append file path to notes
                        existing_notes = fields.get('Notes', '')
                        fields['Notes'] = f"{existing_notes}\nFile: {value}".strip()
                    else:
                        fields[field_name] = value

        record_id = self._create_record(TABLES["Sources"], fields)
        if record_id:
            self.cache['sources'][key] = record_id
            print(f"  + Source: {title}")
        return record_id

    def get_or_create_intervention(self, data: Dict) -> str:
        """Holt oder erstellt eine Intervention mit ALLEN Feldern und Duplikaterkennung"""
        name = data.get('name', 'Unknown')
        key = name.lower()
        normalized = normalize_name(name)

        # Pruefe exakten Cache
        if key in self.cache['interventions']:
            return self.cache['interventions'][key]

        # Pruefe normalisierten Cache
        if normalized in self.normalized_cache['interventions']:
            existing_id = self.normalized_cache['interventions'][normalized]
            print(f"  ~ Intervention existiert bereits (normalisiert): {name}")
            self.cache['interventions'][key] = existing_id
            return existing_id

        # Baue Felder basierend auf Schema
        fields = {"Name": name}

        # Mapping von extrahierten Daten zu Airtable-Feldern
        field_mapping = {
            'type': 'Type (STRICT)',
            'category': 'Category',
            'intervention_scope': 'Intervention scope',
            'is_plant_based': 'Is plant-based?',
            'is_whole_food': 'Is whole food?',
            'is_negative': 'Is negative / risk factor?',
            'culinary_role': 'Culinary role',
            'nutritional_roles': 'Nutritional role (high-level)',
            'example_serving': 'Example serving',
            'typical_use_cases': 'Typical use cases',
            'preparation_notes': 'Preparation notes',
            'summary': 'Short summary (human-readable)',
            'internal_notes': 'Internal notes',
            'discovery_pages': 'Discovery pages'
        }

        for data_key, field_name in field_mapping.items():
            if data_key in data and data[data_key]:
                value = data[data_key]

                # Validiere Select-Felder
                value = self._validate_select_value("Interventions", field_name, value)

                if value:
                    fields[field_name] = value

        # Generiere Interventions ID
        existing_count = len(self.cache['interventions'])
        fields['Interventions ID'] = f"INT-{existing_count + 1:04d}"

        record_id = self._create_record(TABLES["Interventions"], fields)
        if record_id:
            self.cache['interventions'][key] = record_id
            self.normalized_cache['interventions'][normalized] = record_id
            print(f"  + Intervention: {name}")
        return record_id

    def get_or_create_outcome(self, name: str, category: str = None) -> str:
        """Holt oder erstellt ein Outcome"""
        key = name.lower()
        if key in self.cache['outcomes']:
            return self.cache['outcomes'][key]

        fields = {"Name": name}
        if category:
            category = self._validate_select_value("Outcomes", "Health Category", category)
            if category:
                fields["Health Category"] = category

        record_id = self._create_record(TABLES["Outcomes"], fields)
        if record_id:
            self.cache['outcomes'][key] = record_id
            print(f"  + Outcome: {name}")
        return record_id

    def get_or_create_nutrient(self, data: Dict) -> str:
        """Holt oder erstellt einen Nutrient mit verbesserter Duplikaterkennung"""
        name = data.get('name', 'Unknown')
        key = name.lower()
        normalized = normalize_name(name)

        # Pruefe zuerst den exakten Cache
        if key in self.cache['nutrients']:
            return self.cache['nutrients'][key]

        # Pruefe den normalisierten Cache (findet "Omega-3 ALA" wenn "Omega-3 (ALA)" existiert)
        if normalized in self.normalized_cache['nutrients']:
            existing_id = self.normalized_cache['nutrients'][normalized]
            print(f"  ~ Nutrient existiert bereits (normalisiert): {name}")
            # Auch im regulaeren Cache speichern fuer schnelleren Zugriff
            self.cache['nutrients'][key] = existing_id
            return existing_id

        fields = {"Name": name}

        field_mapping = {
            'nutrient_id': 'Nutrient ID',
            'category': 'Category',
            'subcategory': 'Subcategory',
            'unit': 'Unit',
            'daily_value': 'Daily Value',
            'health_benefits': 'Health Benefits'
        }

        for data_key, field_name in field_mapping.items():
            if data_key in data and data[data_key]:
                value = data[data_key]
                value = self._validate_select_value("Nutrients", field_name, value)
                if value:
                    fields[field_name] = value

        # Generiere Nutrient ID
        if 'Nutrient ID' not in fields:
            existing_count = len(self.cache['nutrients'])
            fields['Nutrient ID'] = f"NUT-{existing_count + 1:04d}"

        record_id = self._create_record(TABLES["Nutrients"], fields)
        if record_id:
            self.cache['nutrients'][key] = record_id
            self.normalized_cache['nutrients'][normalized] = record_id
            print(f"  + Nutrient: {name}")
        return record_id

    def create_claim(self, data: Dict) -> bool:
        """Erstellt einen Claim mit allen Verlinkungen"""
        fields = {
            "Name": data.get('name', 'Unnamed claim'),
            "Claim Text": data.get('claim_text', ''),
        }

        if data.get('intervention_id'):
            fields['Intervention'] = [data['intervention_id']]
        if data.get('outcome_ids'):
            fields['Health Outcome'] = data['outcome_ids']
        if data.get('source_id'):
            fields['Source'] = [data['source_id']]
        if data.get('evidence_strength'):
            value = self._validate_select_value("Claims", "Evidence Strength", data['evidence_strength'])
            if value:
                fields['Evidence Strength'] = value
        if data.get('page_reference'):
            fields['Page Reference'] = data['page_reference']

        record_id = self._create_record(TABLES["Claims"], fields)
        if record_id:
            print(f"  + Claim: {data.get('name', 'Unknown')[:50]}")
            return True
        return False

    def _get_serving_size(self, food_name: str, category: str = None) -> Dict:
        """Ermittelt die Standard-Portionsgroesse fuer ein Food"""
        # Pruefe spezifische Serving Sizes zuerst
        food_lower = food_name.lower()
        for key, serving in SPECIFIC_SERVING_SIZES.items():
            if key in food_lower:
                return serving

        # Fallback auf Kategorie-basierte Serving Size
        if category and category in STANDARD_SERVING_SIZES:
            return STANDARD_SERVING_SIZES[category]

        # Default
        return {"serving": "1 serving", "grams": 100}

    def create_nutrient_profile(self, data: Dict) -> bool:
        """Erstellt ein Food-Nutrient Profile mit Duplikaterkennung und Serving Size"""
        food_id = data.get('food_id')
        nutrient_id = data.get('nutrient_id')

        if not food_id or not nutrient_id:
            return False

        # Generiere aussagekraeftigen Namen
        food_name = data.get('food_name', 'Unknown')
        nutrient_name = data.get('nutrient_name', 'Unknown')
        profile_name = f"{food_name} - {nutrient_name}"[:100]

        # Pruefe auf Duplikate (Food + Nutrient Kombination)
        profile_key = normalize_name(f"{food_name} {nutrient_name}")
        if not hasattr(self, '_profile_cache'):
            self._profile_cache = set()
            # Lade existierende Profile
            records = self._get_all_records(TABLES["Food-Nutrient Profile"])
            for r in records:
                name = r['fields'].get('Name', '')
                if name:
                    self._profile_cache.add(normalize_name(name))

        if profile_key in self._profile_cache:
            print(f"  ~ Profile existiert bereits: {profile_name}")
            return False

        # Serving Size ermitteln
        serving_info = self._get_serving_size(food_name, data.get('category'))
        amount_per_100g = data.get('amount_per_100g', 0)

        # Berechne Amount per Serving
        serving_grams = serving_info.get('grams', 100)
        amount_per_serving = (amount_per_100g * serving_grams / 100) if serving_grams > 0 else 0

        fields = {
            "Name": profile_name,
            "Food": [food_id],
            "Nutrient": [nutrient_id],
            "Amount per 100g": amount_per_100g,
            "Source Reference": data.get('source', 'Extracted from study'),
            "Confidence Level": "High",
            "Serving Size": serving_info.get('serving', '1 serving'),
            "Serving Size Grams": serving_grams,
            "Amount per Serving": round(amount_per_serving, 2)
        }

        record_id = self._create_record(TABLES["Food-Nutrient Profile"], fields)
        if record_id:
            self._profile_cache.add(profile_key)
        return record_id is not None


# =============================================================================
# FILE READING
# =============================================================================

def read_source(file_path: str) -> str:
    """Liest Text aus PDF oder Textdatei"""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {file_path}")

    if path.suffix.lower() == '.pdf':
        if not HAS_PDF:
            raise ImportError("pdfplumber erforderlich: pip install pdfplumber")

        text_parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        return "\n\n".join(text_parts)

    else:
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("Konnte Datei nicht dekodieren")


# =============================================================================
# AI EXTRACTION - Dynamischer Prompt basierend auf Schema
# =============================================================================

def build_extraction_prompt(schema: SchemaReader) -> str:
    """Baut den Extraction Prompt dynamisch basierend auf dem Schema"""

    # Hole gueltige Optionen aus dem Schema
    type_options = schema.get_valid_options("Interventions", "Type (STRICT)")
    category_options = schema.get_valid_options("Interventions", "Category")
    health_categories = schema.get_valid_options("Outcomes", "Health Category")
    evidence_options = schema.get_valid_options("Claims", "Evidence Strength")
    nutrient_categories = schema.get_valid_options("Nutrients", "Category")
    unit_options = schema.get_valid_options("Nutrients", "Unit")
    culinary_options = schema.get_valid_options("Interventions", "Culinary role")
    nutritional_role_options = schema.get_valid_options("Interventions", "Nutritional role (high-level)")

    prompt = f'''Du bist ein Ernaehrungswissenschaftler. Analysiere den Text und extrahiere ALLE Informationen.

WICHTIG: Extrahiere sowohl HEALTH CLAIMS als auch NAEHRSTOFFDATEN.

=== TEIL 1: FOODS/INTERVENTIONS ===
Fuer jedes Lebensmittel/Intervention extrahiere:

- name: Name des Foods (z.B. "Flaxseed", "Berries", "Walnuts")
- type: MUSS einer dieser Werte sein: {type_options}
- category: MUSS einer dieser Werte sein: {category_options}
- intervention_scope: "Ingredient", "Food group", "Dietary pattern", oder "Lifestyle factor"
- is_plant_based: true/false
- is_whole_food: true/false
- is_negative: true wenn Risikofaktor, sonst false
- culinary_role: Array aus: {culinary_options}
- nutritional_roles: Array aus: {nutritional_role_options}
- example_serving: Typische Portionsgroesse (z.B. "2 tablespoons (20g)")
- typical_use_cases: Wofuer verwendet (z.B. "Smoothies; Oatmeal; Baking")
- preparation_notes: Zubereitungshinweise
- summary: Kurze Zusammenfassung der Vorteile

=== TEIL 2: HEALTH CLAIMS ===
Fuer jeden Health Claim extrahiere:

- food_name: Welches Food (muss mit einem Food oben uebereinstimmen)
- health_outcomes: Array von Gesundheitszielen (z.B. ["Heart Health", "Brain Health"])
- health_category: MUSS einer dieser Werte sein: {health_categories}
- claim_text: Der eigentliche Claim als Satz
- evidence_strength: MUSS einer dieser Werte sein: {evidence_options}
- page_reference: Seitenzahl wenn vorhanden

=== TEIL 3: NAEHRSTOFFDATEN ===
Fuer JEDES Food, extrahiere die Naehrstoffwerte pro 100g:

- food_name: Welches Food
- nutrients: Array von:
  - name: Naehrstoffname (z.B. "Protein", "Fiber", "Omega-3")
  - amount_per_100g: Wert als Zahl
  - unit: MUSS einer dieser Werte sein: {unit_options}
  - category: MUSS einer dieser Werte sein: {nutrient_categories}

=== TEIL 4: QUELLENANGABEN ===
Extrahiere Metadaten ueber das Dokument selbst:
- source_title: Titel des Dokuments
- source_type: MUSS einer dieser Werte sein: Book, Study, Article, Website, Video, Podcast
- authors: Autoren (z.B. "Dr. Michael Greger, Gene Stone")
- year: Erscheinungsjahr als Zahl (z.B. 2024)
- publisher: Verlag oder Journal (z.B. "Journal of Nutrition Research")
- isbn_doi: ISBN oder DOI wenn vorhanden
- total_pages: Seitenanzahl wenn erkennbar

=== OUTPUT FORMAT ===
Antworte NUR mit validem JSON:

{{
    "source_title": "Titel des Dokuments",
    "source_type": "Study",
    "authors": "Autor Name",
    "year": 2024,
    "publisher": "Journal Name",
    "isbn_doi": "",
    "total_pages": 14,
    "foods": [
        {{
            "name": "Flaxseed",
            "type": "Food",
            "category": "Nuts & seeds",
            "intervention_scope": "Ingredient",
            "is_plant_based": true,
            "is_whole_food": true,
            "is_negative": false,
            "culinary_role": ["Base ingredient"],
            "nutritional_roles": ["Fiber", "Protein"],
            "example_serving": "2 tablespoons (20g)",
            "typical_use_cases": "Smoothies; Oatmeal; Baking",
            "preparation_notes": "Best consumed ground",
            "summary": "Rich source of omega-3 and fiber"
        }}
    ],
    "claims": [
        {{
            "food_name": "Flaxseed",
            "health_outcomes": ["Heart Health", "Gut Health"],
            "health_category": "Cardiovascular",
            "claim_text": "Flaxseed consumption reduces LDL cholesterol by 15%",
            "evidence_strength": "Strong (RCT/Meta-analysis)",
            "page_reference": "p. 147"
        }}
    ],
    "nutrient_data": [
        {{
            "food_name": "Flaxseed",
            "nutrients": [
                {{"name": "Protein", "amount_per_100g": 18.3, "unit": "g", "category": "Macronutrient"}},
                {{"name": "Fiber", "amount_per_100g": 27.3, "unit": "g", "category": "Macronutrient"}}
            ]
        }}
    ]
}}

TEXT ZUM ANALYSIEREN:
'''
    return prompt


def extract_with_ai(text: str, schema: SchemaReader, model: str = "gpt-4o") -> Dict:
    """Extrahiert alle Daten mit KI"""
    if not HAS_OPENAI:
        raise ImportError("openai erforderlich: pip install openai")

    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY nicht gesetzt")

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Truncate if too long
    max_chars = 80000
    if len(text) > max_chars:
        print(f"  Text gekuerzt: {len(text)} -> {max_chars} Zeichen")
        text = text[:max_chars]

    prompt = build_extraction_prompt(schema)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Du bist ein praeziser Ernaehrungswissenschaftler. Antworte immer mit validem JSON."},
            {"role": "user", "content": prompt + text}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )

    return json.loads(response.choices[0].message.content)


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def process_document(file_path: str, model: str = "gpt-4o") -> Dict[str, int]:
    """
    Komplette Pipeline: Lesen -> Extrahieren -> In Airtable speichern
    """
    print("=" * 60)
    print("ALIVE FOOD DATABASE - DATA ENGINE v2.0")
    print("=" * 60)

    stats = {
        "interventions": 0,
        "outcomes": 0,
        "claims": 0,
        "nutrients": 0,
        "nutrient_profiles": 0,
        "errors": 0
    }

    # Schema laden
    print("\n[1/4] Schema laden...")
    schema = SchemaReader()

    # Datenbank initialisieren
    print("\n[2/4] Datenbank initialisieren...")
    db = AirtableDB(schema)

    # Datei lesen
    print(f"\n[3/4] Datei lesen: {file_path}")
    text = read_source(file_path)
    print(f"  {len(text)} Zeichen extrahiert")

    # Mit KI extrahieren
    print(f"\n[4/4] KI-Extraktion ({model})...")
    extracted = extract_with_ai(text, schema, model)

    foods = extracted.get('foods', [])
    claims = extracted.get('claims', [])
    nutrient_data = extracted.get('nutrient_data', [])

    print(f"  Gefunden: {len(foods)} Foods, {len(claims)} Claims, {len(nutrient_data)} Nutrient-Sets")

    # Source erstellen mit allen Metadaten
    print("\n[5/4] In Airtable speichern...")
    source_data = {
        'title': extracted.get('source_title', Path(file_path).name),
        'source_type': extracted.get('source_type', 'Article'),
        'authors': extracted.get('authors', ''),
        'year': extracted.get('year'),
        'publisher': extracted.get('publisher', ''),
        'isbn_doi': extracted.get('isbn_doi', ''),
        'total_pages': extracted.get('total_pages'),
        'file_path': str(Path(file_path).absolute()),  # Speichere den Dateipfad
        'notes': f"Automatisch extrahiert am {time.strftime('%Y-%m-%d %H:%M')}"
    }
    source_id = db.get_or_create_source(source_data)

    # Food ID Mapping fuer spaetere Referenz
    food_ids = {}

    # Foods/Interventions erstellen
    print("\n  --- Interventions ---")
    for food in foods:
        food['discovery_pages'] = extracted.get('page_reference', '')
        intervention_id = db.get_or_create_intervention(food)
        if intervention_id:
            food_ids[food['name'].lower()] = intervention_id
            stats["interventions"] += 1

    # Claims erstellen
    print("\n  --- Claims ---")
    for claim in claims:
        try:
            food_name = claim.get('food_name', '').lower()
            intervention_id = food_ids.get(food_name) or db.cache['interventions'].get(food_name)

            # Outcomes erstellen/holen
            outcome_ids = []
            for outcome_name in claim.get('health_outcomes', []):
                outcome_id = db.get_or_create_outcome(
                    outcome_name,
                    claim.get('health_category')
                )
                if outcome_id:
                    outcome_ids.append(outcome_id)
                    stats["outcomes"] += 1

            # Claim erstellen
            claim_name = f"{claim.get('food_name', 'Unknown')} - {', '.join(claim.get('health_outcomes', ['Health']))}"
            success = db.create_claim({
                'name': claim_name[:100],
                'claim_text': claim.get('claim_text', ''),
                'intervention_id': intervention_id,
                'outcome_ids': outcome_ids,
                'source_id': source_id,
                'evidence_strength': claim.get('evidence_strength'),
                'page_reference': claim.get('page_reference')
            })

            if success:
                stats["claims"] += 1
            else:
                stats["errors"] += 1

        except Exception as e:
            print(f"  Fehler bei Claim: {e}")
            stats["errors"] += 1

    # Nutrient Profiles erstellen
    print("\n  --- Nutrient Profiles ---")
    # Erstelle Mapping von food_name zu category
    food_categories = {f.get('name', '').lower(): f.get('category') for f in foods}

    for nd in nutrient_data:
        food_name_lower = nd.get('food_name', '').lower()
        food_id = food_ids.get(food_name_lower) or db.cache['interventions'].get(food_name_lower)

        if not food_id:
            # Versuche normalisierte Suche
            normalized = normalize_name(nd.get('food_name', ''))
            food_id = db.normalized_cache['interventions'].get(normalized)

        if not food_id:
            print(f"  Warnung: Food '{nd.get('food_name')}' nicht gefunden")
            continue

        # Hole Kategorie des Foods
        food_category = food_categories.get(food_name_lower)

        for nutrient in nd.get('nutrients', []):
            try:
                # Nutrient erstellen/holen
                nutrient_id = db.get_or_create_nutrient({
                    'name': nutrient.get('name'),
                    'category': nutrient.get('category'),
                    'unit': nutrient.get('unit')
                })

                if nutrient_id:
                    stats["nutrients"] += 1

                    # Profile erstellen mit Kategorie fuer Serving Size
                    success = db.create_nutrient_profile({
                        'food_id': food_id,
                        'food_name': nd.get('food_name'),
                        'nutrient_id': nutrient_id,
                        'nutrient_name': nutrient.get('name'),
                        'amount_per_100g': nutrient.get('amount_per_100g', 0),
                        'source': source_data.get('title', 'Unknown'),
                        'category': food_category  # Fuer Serving Size Berechnung
                    })

                    if success:
                        stats["nutrient_profiles"] += 1

            except Exception as e:
                print(f"  Fehler bei Nutrient: {e}")
                stats["errors"] += 1

    # Zusammenfassung
    print("\n" + "=" * 60)
    print("FERTIG!")
    print("=" * 60)
    print(f"  Neue Interventions: {stats['interventions']}")
    print(f"  Neue Outcomes: {stats['outcomes']}")
    print(f"  Neue Claims: {stats['claims']}")
    print(f"  Neue Nutrients: {stats['nutrients']}")
    print(f"  Neue Nutrient Profiles: {stats['nutrient_profiles']}")
    print(f"  Fehler: {stats['errors']}")

    return stats


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python data_engine_v2.py <file_path> [--model MODEL]")
        print()
        print("Beispiele:")
        print("  python data_engine_v2.py study.pdf")
        print("  python data_engine_v2.py notes.txt --model gpt-4o-mini")
        print()
        print("Unterstuetzte Formate: .pdf, .txt, .md")
        sys.exit(1)

    file_path = sys.argv[1]
    model = "gpt-4o"

    if "--model" in sys.argv:
        idx = sys.argv.index("--model")
        if idx + 1 < len(sys.argv):
            model = sys.argv[idx + 1]

    try:
        process_document(file_path, model)
    except Exception as e:
        print(f"Fehler: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
