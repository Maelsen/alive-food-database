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
# CONFIGURATION - Supports both environment variables AND Streamlit secrets
# =============================================================================

def get_secret(key, default=None):
    """Gets a secret from environment variable OR Streamlit secrets"""
    # First try environment variable
    value = os.getenv(key)
    if value:
        return value

    # Then try Streamlit secrets (for Streamlit Cloud deployment)
    try:
        import streamlit as st
        if hasattr(st, 'secrets'):
            # Try exact key first
            if key in st.secrets:
                return st.secrets[key]
            # WORKAROUND: Check for typo "aAIRTABLE_TOKEN" -> "AIRTABLE_TOKEN"
            if key == "AIRTABLE_TOKEN" and "aAIRTABLE_TOKEN" in st.secrets:
                return st.secrets["aAIRTABLE_TOKEN"]
    except Exception:
        pass

    return default

AIRTABLE_TOKEN = get_secret("AIRTABLE_TOKEN")
BASE_ID = get_secret("AIRTABLE_BASE_ID", "appOFvKsPdHQQBOQ9")
OPENAI_API_KEY = get_secret("OPENAI_API_KEY")

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

# Valid options for select fields.
# WICHTIG: Diese Listen muessen mit den echten Airtable-Choices uebereinstimmen,
# sonst lehnt Airtable den Wert mit 422 ab (stiller Fehler). Stand: 2026-06-04,
# abgeglichen mit der Meta-API der Base. _validate_option() faellt immer auf einen
# gueltigen Wert zurueck, und beim Cache-Load werden diese Listen zusaetzlich mit
# den live vorhandenen Choices ueberschrieben (refresh_valid_options), damit sie
# auch bei kuenftigen Schema-Aenderungen aktuell bleiben.
VALID_OPTIONS = {
    "source_type": ["Book", "Study", "Article", "Website", "Video", "Podcast"],
    "intervention_type": ["Food", "Food group", "Food pattern", "Lifestyle", "Supplement (optional, future)"],
    "category": ["Fruit", "Vegetable", "Legume", "Whole grain", "Nuts & seeds",
                 "Herbs & spices", "Beverage", "Animal product", "Dietary pattern",
                 "Sleep", "Physical activity", "Other"],
    "intervention_scope": ["Ingredient", "Food group", "Dietary pattern", "Lifestyle factor"],
    "risk_framing": ["Actively encourage", "Neutral", "Context-dependent", "Limit", "Avoid"],
    "evidence_strength": ["Strong (RCT/Meta-analysis)", "Moderate (Cohort studies)",
                          "Preliminary (Observational)", "Mechanistic (In-vitro)"],
    # Mental Health -> Brain/Cognitive (Mapping in _validate_option)
    "health_category": ["Cardiovascular", "Brain/Cognitive", "Gut/Digestive",
                        "Metabolic", "Immune", "Inflammation", "Longevity", "Other"],
    "nutrient_category": ["Macronutrient", "Micronutrient", "Phytonutrient", "Other"],
    "nutrient_subcategory": ["Vitamin", "Mineral", "Amino Acid", "Fatty Acid",
                             "Fiber", "Polyphenol", "Carbohydrate", "Other"],
    "unit": ["g", "mg", "mcg", "IU"],
    "confidence": ["High", "Medium", "Low"],
    # Multi-Select: kuratierte, kanonische Choices (kein Junk anlegen).
    "nutritional_role": ["Protein source", "Fiber source", "Healthy fat source",
                         "Carbohydrate source", "Micronutrient-dense", "Antioxidant-rich"],
    "culinary_role": ["Base ingredient", "Topping", "Seasoning", "Beverage", "Snack", "Pattern / Habit"],
}

# Felder die als Select an Airtable gehen -> Field-Name in Airtable.
# Wird von refresh_valid_options() genutzt um VALID_OPTIONS live abzugleichen.
SELECT_FIELD_MAP = {
    "Sources": {"Source Type": "source_type"},
    "Interventions": {
        "Type (STRICT)": "intervention_type",
        "Category": "category",
        "Intervention scope": "intervention_scope",
        "Risk framing (editorial)": "risk_framing",
    },
    "Outcomes": {"Health Category": "health_category"},
    "Claims": {"Evidence Strength": "evidence_strength"},
    "Nutrients": {"Category": "nutrient_category", "Subcategory": "nutrient_subcategory", "Unit": "unit"},
    "Food-Nutrient Profile": {"Confidence Level": "confidence", "Unit": "unit"},
}

# Mapping: KI-Werte -> kanonische Multi-Select-Choices (sonst Junk-Optionen).
NUTRITIONAL_ROLE_MAP = {
    "protein": "Protein source", "protein source": "Protein source",
    "fiber": "Fiber source", "fibre": "Fiber source", "dietary fiber": "Fiber source",
    "soluble fiber": "Fiber source", "fiber source": "Fiber source",
    "omega-3": "Healthy fat source", "omega 3": "Healthy fat source",
    "healthy fat": "Healthy fat source", "healthy fats": "Healthy fat source",
    "fat": "Healthy fat source", "fatty acid": "Healthy fat source",
    "monounsaturated": "Healthy fat source", "polyunsaturated": "Healthy fat source",
    "carbohydrate": "Carbohydrate source", "carbohydrates": "Carbohydrate source",
    "complex carbohydrates": "Carbohydrate source", "carbs": "Carbohydrate source",
    "vitamin": "Micronutrient-dense", "vitamins": "Micronutrient-dense",
    "mineral": "Micronutrient-dense", "minerals": "Micronutrient-dense",
    "micronutrient": "Micronutrient-dense", "micronutrients": "Micronutrient-dense",
    "vitamin c": "Micronutrient-dense", "potassium": "Micronutrient-dense",
    "calcium": "Micronutrient-dense", "iron": "Micronutrient-dense",
    "antioxidant": "Antioxidant-rich", "antioxidants": "Antioxidant-rich",
    "polyphenol": "Antioxidant-rich", "polyphenols": "Antioxidant-rich",
    "anthocyanin": "Antioxidant-rich", "anthocyanins": "Antioxidant-rich",
    "flavonoid": "Antioxidant-rich", "flavonoids": "Antioxidant-rich",
    "carotenoid": "Antioxidant-rich",
}
CULINARY_ROLE_MAP = {
    "base ingredient": "Base ingredient", "main dish": "Base ingredient",
    "main": "Base ingredient", "side dish": "Base ingredient", "base": "Base ingredient",
    "topping": "Topping", "garnish": "Topping",
    "seasoning": "Seasoning", "spice": "Seasoning", "herb": "Seasoning",
    "beverage": "Beverage", "drink": "Beverage", "smoothie ingredient": "Beverage",
    "smoothie": "Beverage",
    "snack": "Snack",
    "pattern": "Pattern / Habit", "habit": "Pattern / Habit", "lifestyle": "Pattern / Habit",
}

# Platzhalter-Strings die die KI manchmal liefert - sollen NICHT geschrieben werden.
PLACEHOLDER_VALUES = {
    "", "n/a", "na", "none", "null", "unknown", "unbekannt", "nicht angegeben",
    "not available", "not specified", "keine angabe", "k.a.", "-", "--", "tbd", "?",
}


def clean_text(value):
    """Gibt einen sauberen String zurueck oder None, wenn es ein Platzhalter/leer ist."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in PLACEHOLDER_VALUES:
        return None
    return text


def map_multiselect(values, mapping):
    """Mappt eine KI-Werteliste auf kanonische Multi-Select-Choices.

    Nicht zuordenbare Werte werden verworfen (kein Junk in Airtable). Reihenfolge
    bleibt erhalten, Duplikate werden entfernt. Gibt eine Liste gueltiger Choices.
    """
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    result = []
    for v in values:
        cleaned = clean_text(v)
        if not cleaned:
            continue
        key = cleaned.lower()
        canonical = mapping.get(key)
        if not canonical:
            # Teilstring-Treffer als Fallback (z.B. "high in fiber" -> "fiber")
            for mk, mv in mapping.items():
                if mk in key:
                    canonical = mv
                    break
        if canonical and canonical not in result:
            result.append(canonical)
    return result


# =============================================================================
# AIRTABLE HELPER FUNCTIONS
# =============================================================================

def get_all_records(table_id: str) -> List[Dict]:
    """Holt alle Records einer Tabelle mit Pagination"""
    all_records = []
    offset = None

    # Refresh headers in case token was loaded later (Streamlit secrets)
    current_token = get_secret("AIRTABLE_TOKEN")
    current_headers = {
        "Authorization": f"Bearer {current_token}",
        "Content-Type": "application/json"
    }

    if not current_token:
        print("ERROR: AIRTABLE_TOKEN is not set!")
        return []

    while True:
        params = {}
        if offset:
            params['offset'] = offset

        resp = requests.get(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=current_headers,
            params=params
        )

        if resp.status_code != 200:
            print(f"Error fetching records: {resp.status_code} - {resp.text[:200]}")
            break

        data = resp.json()
        all_records.extend(data.get('records', []))
        offset = data.get('offset')

        if not offset:
            break

    return all_records


# Optionaler Fehler-Sink: eine Liste, in die detaillierte API-Fehler wandern,
# damit sie in der UI sichtbar werden statt nur auf stderr zu landen.
_ERROR_SINK = None


def _record_error(msg: str):
    """Loggt einen Fehler nach stderr UND in den optionalen Sink (fuer die UI)."""
    print(msg)
    if _ERROR_SINK is not None:
        _ERROR_SINK.append(msg)


def _short_api_error(resp) -> str:
    """Extrahiert eine knappe, lesbare Fehlermeldung aus einer Airtable-Antwort."""
    try:
        err = resp.json().get("error", {})
        if isinstance(err, dict):
            etype = err.get("type", "")
            emsg = err.get("message", "")
            detail = f"{etype}: {emsg}".strip(": ").strip()
        else:
            detail = str(err)
    except Exception:
        detail = resp.text[:200]
    return f"HTTP {resp.status_code} - {detail}"


def create_record(table_id: str, fields: Dict) -> Optional[str]:
    """Erstellt einen neuen Record und gibt die ID zurueck"""
    # Refresh headers in case token was loaded later (Streamlit secrets)
    current_token = get_secret("AIRTABLE_TOKEN")
    current_headers = {
        "Authorization": f"Bearer {current_token}",
        "Content-Type": "application/json"
    }

    if not current_token:
        _record_error("AIRTABLE_TOKEN ist nicht gesetzt - keine Verbindung zu Airtable moeglich.")
        return None

    try:
        resp = requests.post(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=current_headers,
            json={"fields": fields},
            timeout=30,
        )
    except requests.RequestException as e:
        _record_error(f"Netzwerkfehler beim Schreiben: {e}")
        return None

    if resp.status_code == 200:
        return resp.json().get('id')
    else:
        _record_error(_short_api_error(resp))
        return None


def update_record(table_id: str, record_id: str, fields: Dict) -> bool:
    """Aktualisiert einen bestehenden Record"""
    # Refresh headers in case token was loaded later (Streamlit secrets)
    current_token = get_secret("AIRTABLE_TOKEN")
    current_headers = {
        "Authorization": f"Bearer {current_token}",
        "Content-Type": "application/json"
    }

    if not current_token:
        _record_error("AIRTABLE_TOKEN ist nicht gesetzt - keine Verbindung zu Airtable moeglich.")
        return False

    try:
        resp = requests.patch(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}/{record_id}",
            headers=current_headers,
            json={"fields": fields},
            timeout=30,
        )
    except requests.RequestException as e:
        _record_error(f"Netzwerkfehler beim Aktualisieren: {e}")
        return False

    if resp.status_code != 200:
        _record_error(_short_api_error(resp))

    return resp.status_code == 200


def normalize_name(name: str) -> str:
    """Normalisiert Namen fuer Duplikat-Erkennung (inkl. Singular/Plural)"""
    if not name:
        return ""
    normalized = name.lower().strip()
    # Entferne Sonderzeichen
    for char in ['(', ')', '-', '_', ',', '.']:
        normalized = normalized.replace(char, ' ')
    # Mehrere Leerzeichen zu einem
    normalized = ' '.join(normalized.split())

    # Singular/Plural Normalisierung - konvertiere zu Singular
    # Behandle spezielle Faelle zuerst
    word_mappings = {
        'blueberries': 'blueberry',
        'strawberries': 'strawberry',
        'raspberries': 'raspberry',
        'blackberries': 'blackberry',
        'cranberries': 'cranberry',
        'cherries': 'cherry',
        'berries': 'berry',
        'tomatoes': 'tomato',
        'potatoes': 'potato',
        'leaves': 'leaf',
        'leafy greens': 'leafy green',
    }

    for plural, singular in word_mappings.items():
        normalized = normalized.replace(plural, singular)

    # Allgemeine Plural-Endungen (nur am Wortende)
    words = normalized.split()
    normalized_words = []
    for word in words:
        # -ies -> -y (bereits oben behandelt fuer bekannte Woerter)
        # -es -> (nur wenn nicht bereits behandelt)
        if word.endswith('es') and word not in word_mappings.values():
            # seeds -> seed, vegetables -> vegetable
            if word.endswith('ies'):
                pass  # bereits behandelt
            elif word.endswith('ves'):
                word = word[:-3] + 'f'  # leaves -> leaf
            elif word.endswith('oes'):
                pass  # bereits behandelt (tomatoes, potatoes)
            elif word.endswith('ses') or word.endswith('xes') or word.endswith('zes'):
                word = word[:-2]  # glasses -> glass
            else:
                word = word[:-1]  # vegetables -> vegetable
        elif word.endswith('s') and len(word) > 3 and not word.endswith('ss'):
            # Einfaches -s entfernen: walnuts -> walnut, seeds -> seed
            word = word[:-1]
        normalized_words.append(word)

    return ' '.join(normalized_words)


def refresh_valid_options():
    """Gleicht VALID_OPTIONS mit den echten Airtable-Choices ab (Meta-API).

    Verhindert stille 422er, wenn sich das Schema aendert. Multi-Select-Rollen
    (kuratiert) werden bewusst NICHT ueberschrieben - dort wollen wir keinen Junk.
    Schlaegt der Call fehl, behalten wir die hartkodierten Defaults.
    """
    token = get_secret("AIRTABLE_TOKEN")
    if not token:
        return
    try:
        resp = requests.get(
            f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"  (Schema-Abgleich uebersprungen: HTTP {resp.status_code})")
            return
        by_name = {t["name"]: t for t in resp.json().get("tables", [])}
        for table_id_name, fields_map in SELECT_FIELD_MAP.items():
            # SELECT_FIELD_MAP nutzt die Klartext-Tabellennamen aus TABLES-Keys
            table = by_name.get(table_id_name) or by_name.get(table_id_name.replace("-", "–"))
            if not table:
                continue
            field_choices = {}
            for f in table.get("fields", []):
                choices = f.get("options", {}).get("choices")
                if choices:
                    field_choices[f["name"]] = [c["name"] for c in choices]
            for field_name, opt_key in fields_map.items():
                if field_name in field_choices and field_choices[field_name]:
                    VALID_OPTIONS[opt_key] = field_choices[field_name]
        print("  Schema-Optionen mit Airtable abgeglichen.")
    except requests.RequestException as e:
        print(f"  (Schema-Abgleich fehlgeschlagen: {e})")


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

        # Select-Optionen mit dem echten Schema abgleichen (verhindert stille 422er)
        refresh_valid_options()

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
            "study_details": "Details zur Studie: n=245, 12 Wochen, doppelblind etc.",
            "quantified_effect": "NUR AUSFUELLEN wenn die Studie quantifizierbare Ergebnisse nennt! Format: '[Dosis] for [Dauer] -> [X]% [Verbesserung/Reduktion] in [Outcome]'. Beispiele: '30g blueberries/day for 8 weeks -> 25% reduction in inflammation markers' oder '7g fiber daily -> 20% lower all-cause mortality'. LEER LASSEN wenn keine quantifizierbaren Daten vorhanden!"
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
11. quantified_effect: NUR ausfuellen wenn die Studie KONKRETE ZAHLEN nennt (z.B. "25% reduction", "30g/day for 8 weeks"). Wenn keine quantifizierbaren Daten -> leerer String ""

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

    try:
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
    except Exception as e:
        print(f"OpenAI API Fehler: {e}")
        return None

    try:
        return json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, AttributeError, IndexError) as e:
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
            "profiles_skipped": 0,
            "errors": []
        }
        self.source_id = None
        self.source_title = None  # Titel der Source fuer Referenzen
        self.food_ids = {}  # name -> id
        self.outcome_ids = {}  # name -> id
        self.nutrient_ids = {}  # name -> id
        # Track Food+Nutrient combinations created in this session to prevent duplicates
        self.created_profiles = set()  # (food_id, nutrient_id)

    def import_all(self, data: Dict) -> Dict:
        """Importiert alle extrahierten Daten"""
        global _ERROR_SINK
        # Detaillierte API-Fehler landen ab jetzt in den Stats (sichtbar in der UI)
        _ERROR_SINK = self.stats["errors"]
        print("\n" + "="*60)
        print("STARTE IMPORT")
        print("="*60)

        try:
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
        finally:
            _ERROR_SINK = None

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
            self.source_title = title
            print(f"  -> Existiert bereits (ID: {self.source_id[:10]}...)")

            # Aktualisiere fehlende Felder (nur echte Werte, keine Platzhalter)
            updates = {}
            existing_fields = existing['fields']

            authors = clean_text(source_data.get('authors'))
            journal = clean_text(source_data.get('journal'))
            notes = clean_text(source_data.get('notes'))
            if not existing_fields.get('Author(s)') and authors:
                updates['Author(s)'] = authors
            if not existing_fields.get('Year') and source_data.get('year'):
                updates['Year'] = source_data['year']
            if not existing_fields.get('Publisher/Journal') and journal:
                updates['Publisher/Journal'] = journal
            if not existing_fields.get('Notes') and notes:
                updates['Notes'] = notes

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

        # Optionale Felder (nur echte Werte, keine Platzhalter wie "Unbekannt")
        if clean_text(source_data.get('authors')):
            fields['Author(s)'] = clean_text(source_data['authors'])
        if source_data.get('year'):
            try:
                fields['Year'] = int(source_data['year'])
            except (ValueError, TypeError):
                pass
        if clean_text(source_data.get('journal')):
            fields['Publisher/Journal'] = clean_text(source_data['journal'])
        if clean_text(source_data.get('doi')):
            fields['ISBN/DOI'] = clean_text(source_data['doi'])
        if clean_text(source_data.get('url')):
            fields['URL'] = clean_text(source_data['url'])
        if source_data.get('total_pages'):
            try:
                fields['Total Pages'] = int(source_data['total_pages'])
            except (ValueError, TypeError):
                pass
        if clean_text(source_data.get('notes')):
            fields['Notes'] = clean_text(source_data['notes'])

        self.source_id = create_record(TABLES["Sources"], fields)
        if self.source_id:
            self.source_title = title
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
        if clean_text(outcome_data.get('notes')):
            fields['Notes'] = clean_text(outcome_data['notes'])

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

            # Ergaenze fehlende Felder (nur echte Werte, keine Platzhalter)
            summary = clean_text(food_data.get('summary'))
            serving = clean_text(food_data.get('example_serving'))
            uses = clean_text(food_data.get('typical_uses'))
            prep = clean_text(food_data.get('preparation_notes'))
            if not existing_fields.get('Short summary (human-readable)') and summary:
                updates['Short summary (human-readable)'] = summary
            if not existing_fields.get('Example serving') and serving:
                updates['Example serving'] = serving
            if not existing_fields.get('Typical use cases') and uses:
                updates['Typical use cases'] = uses
            if not existing_fields.get('Preparation notes') and prep:
                updates['Preparation notes'] = prep

            # Rollen-Felder nachfuellen wenn noch leer (macht bestehende Foods reicher)
            if not existing_fields.get('Nutritional role (high-level)'):
                nutri_roles = map_multiselect(food_data.get('nutritional_roles'), NUTRITIONAL_ROLE_MAP)
                if nutri_roles:
                    updates['Nutritional role (high-level)'] = nutri_roles
            if not existing_fields.get('Culinary role'):
                culinary = map_multiselect(food_data.get('culinary_roles'), CULINARY_ROLE_MAP)
                if culinary:
                    updates['Culinary role'] = culinary

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
        # Generiere Interventions ID automatisch (INT-XXXX)
        next_id = len(self.cache.interventions) + 1
        intervention_id_str = f"INT-{next_id:04d}"

        fields = {
            "Name": name,
            "Interventions ID": intervention_id_str,
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

        # Text Felder (nur echte Werte, keine Platzhalter)
        if clean_text(food_data.get('example_serving')):
            fields['Example serving'] = clean_text(food_data['example_serving'])
        if clean_text(food_data.get('typical_uses')):
            fields['Typical use cases'] = clean_text(food_data['typical_uses'])
        if clean_text(food_data.get('preparation_notes')):
            fields['Preparation notes'] = clean_text(food_data['preparation_notes'])
        if clean_text(food_data.get('summary')):
            fields['Short summary (human-readable)'] = clean_text(food_data['summary'])
        if clean_text(food_data.get('internal_notes')):
            fields['Internal notes'] = clean_text(food_data['internal_notes'])
        if clean_text(food_data.get('discovery_pages')):
            fields['Discovery pages'] = clean_text(food_data['discovery_pages'])

        # Multi-Select Felder - KI-Werte auf kanonische Choices mappen (kein Junk).
        nutri_roles = map_multiselect(food_data.get('nutritional_roles'), NUTRITIONAL_ROLE_MAP)
        if nutri_roles:
            fields['Nutritional role (high-level)'] = nutri_roles
        culinary = map_multiselect(food_data.get('culinary_roles'), CULINARY_ROLE_MAP)
        if culinary:
            fields['Culinary role'] = culinary

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

        # Duplikat-Erkennung: gleiches Food UND (gleicher Text ODER gleiche
        # Outcome-Menge + gleiche Quelle). Letzteres faengt Re-Uploads ab, auch
        # wenn die KI den Claim-Text minimal anders formuliert.
        new_outcome_set = set(outcome_ids)
        for existing in self.cache.claims:
            ef = existing['fields']
            if food_id not in ef.get('Intervention', []):
                continue
            if ef.get('Claim Text') == claim_text:
                print(f"  -> Existiert bereits (gleicher Text)")
                return
            existing_outcomes = set(ef.get('Health Outcome', []))
            same_source = bool(self.source_id) and self.source_id in ef.get('Source', [])
            if new_outcome_set and existing_outcomes == new_outcome_set and same_source:
                print(f"  -> Existiert bereits (gleiche Food+Outcome+Quelle)")
                return

        # Claim erstellen
        # Name-Feld: "Food: Claim (gekuerzt)"
        outcome_names = claim_data.get('outcome_names', [])
        if outcome_names:
            claim_name = f"{food_name}: {outcome_names[0]}"
        else:
            # Kuerze Claim Text auf 50 Zeichen
            short_claim = claim_text[:50] + "..." if len(claim_text) > 50 else claim_text
            claim_name = f"{food_name}: {short_claim}"

        fields = {
            "Name": claim_name,
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
        if clean_text(claim_data.get('page_reference')):
            fields["Page Reference"] = clean_text(claim_data['page_reference'])
        # Quantified Effect - nur wenn vorhanden (z.B. "30g/day for 8 weeks -> 25% reduction")
        if clean_text(claim_data.get('quantified_effect')):
            fields["Quantified Effect"] = clean_text(claim_data['quantified_effect'])

        claim_id = create_record(TABLES["Claims"], fields)
        if claim_id:
            self.stats["claims_created"] += 1
            self.cache.claims.append({'id': claim_id, 'fields': fields})
            print(f"  -> NEU erstellt")

            # BIDIREKTIONALE VERKNUEPFUNGEN erstellen
            # 1. Update Intervention mit Outcomes
            if outcome_ids:
                existing_intervention = self.cache.interventions.get(normalize_name(food_name), {})
                existing_outcomes = existing_intervention.get('fields', {}).get('Outcomes', [])
                new_outcomes = list(set(existing_outcomes + outcome_ids))
                if new_outcomes != existing_outcomes:
                    update_record(TABLES["Interventions"], food_id, {"Outcomes": new_outcomes})
                    print(f"    -> Intervention mit {len(outcome_ids)} Outcomes verknuepft")

            # 2. Update Outcomes mit Related Interventions
            for outcome_id in outcome_ids:
                # Finde das Outcome im Cache
                for norm_name, outcome_data in self.cache.outcomes.items():
                    if outcome_data['id'] == outcome_id:
                        existing_interventions = outcome_data.get('fields', {}).get('Related Interventions', [])
                        if food_id not in existing_interventions:
                            new_interventions = existing_interventions + [food_id]
                            update_record(TABLES["Outcomes"], outcome_id, {"Related Interventions": new_interventions})
                            print(f"    -> Outcome mit Intervention verknuepft")
                        break
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
                # Generiere Nutrient ID automatisch (NUT-XXX)
                next_id = len(self.cache.nutrients) + 1
                nutrient_id_str = f"NUT-{next_id:03d}"

                fields = {
                    "Name": nutrient_name,
                    "Nutrient Name": nutrient_name,
                    "Nutrient ID": nutrient_id_str,
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
                if clean_text(nutrient_data.get('health_benefits')):
                    fields['Health Benefits'] = clean_text(nutrient_data['health_benefits'])

                nutrient_id = create_record(TABLES["Nutrients"], fields)
                if nutrient_id:
                    self.stats["nutrients_created"] += 1
                    self.cache.nutrients[normalized] = {'id': nutrient_id, 'fields': fields}
                else:
                    continue

            # Pruefe ob Profile schon existiert (in DB oder in dieser Session)
            profile_key = (food_id, nutrient_id)

            # Check 1: Bereits in dieser Session erstellt?
            if profile_key in self.created_profiles:
                self.stats["profiles_skipped"] += 1
                continue

            # Check 2: Bereits in der Datenbank?
            profile_exists = False
            for p in self.cache.profiles:
                p_foods = p['fields'].get('Food', [])
                p_nutrients = p['fields'].get('Nutrient', [])
                if food_id in p_foods and nutrient_id in p_nutrients:
                    profile_exists = True
                    break

            if profile_exists:
                self.stats["profiles_skipped"] += 1
                continue

            # Food-Nutrient Profile erstellen - ALLE FELDER
            # Name-Feld: "Food - Nutrient"
            profile_name = f"{food_name} - {nutrient_name}"

            profile_fields = {
                "Name": profile_name,
                "Food": [food_id],
                "Nutrient": [nutrient_id],
            }

            # Amount per 100g - sauber gerundet
            if nutrient_data.get('amount_per_100g') is not None:
                amount_100g = float(nutrient_data['amount_per_100g'])
                # Runde intelligent: ganze Zahlen fuer grosse Werte, 1 Dezimale fuer kleine
                if amount_100g >= 10:
                    profile_fields['Amount per 100g'] = round(amount_100g)
                else:
                    profile_fields['Amount per 100g'] = round(amount_100g, 1)

            # Serving Size (aus nutrient_set, nicht nutrient_data)
            serving_size = nutrient_set.get('serving_size', '')
            serving_grams = nutrient_set.get('serving_size_grams', 0)

            # Serving Size mit Gramm-Angabe wenn nicht vorhanden
            if serving_size:
                # Fuege Gramm hinzu wenn nicht schon enthalten
                if serving_grams and 'g' not in serving_size.lower():
                    profile_fields['Serving Size'] = f"{serving_size} ({int(serving_grams)}g)"
                else:
                    profile_fields['Serving Size'] = serving_size
            elif serving_grams:
                profile_fields['Serving Size'] = f"{int(serving_grams)}g"

            if serving_grams and serving_grams > 0:
                profile_fields['Serving Size Grams'] = int(serving_grams)

            # Amount per Serving (berechnen oder aus Daten) - sauber gerundet
            if nutrient_data.get('amount_per_serving') is not None:
                amount_serving = float(nutrient_data['amount_per_serving'])
                if amount_serving >= 10:
                    profile_fields['Amount per Serving'] = round(amount_serving)
                else:
                    profile_fields['Amount per Serving'] = round(amount_serving, 1)
            elif nutrient_data.get('amount_per_100g') and serving_grams:
                # Berechne Amount per Serving
                amount_per_serving = (float(nutrient_data['amount_per_100g']) * float(serving_grams)) / 100
                if amount_per_serving >= 10:
                    profile_fields['Amount per Serving'] = round(amount_per_serving)
                else:
                    profile_fields['Amount per Serving'] = round(amount_per_serving, 1)

            # Confidence Level
            if nutrient_data.get('confidence'):
                profile_fields['Confidence Level'] = self._validate_option(nutrient_data['confidence'], 'confidence')

            # Source Reference - Titel der Quelle statt ID
            if self.source_title:
                profile_fields['Source Reference'] = self.source_title

            # Unit - von Nutrient uebernehmen
            if nutrient_data.get('unit'):
                profile_fields['Unit'] = self._validate_option(nutrient_data['unit'], 'unit')

            profile_id = create_record(TABLES["Food-Nutrient Profile"], profile_fields)
            if profile_id:
                self.stats["profiles_created"] += 1
                self.cache.profiles.append({'id': profile_id, 'fields': profile_fields})
                # Markiere als erstellt um Duplikate in dieser Session zu verhindern
                self.created_profiles.add(profile_key)

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
        print(f"  Profiles:      {self.stats['profiles_created']} neu, {self.stats['profiles_skipped']} uebersprungen (Duplikate)")

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
        progress_callback("Loading database (reading existing records)...")

    # Cache laden
    cache = DatabaseCache()
    cache.load()

    if progress_callback:
        progress_callback("Extracting data with AI (this can take 30-60 sec)...")

    # Mit KI extrahieren
    extracted = extract_with_ai(text)

    if not extracted:
        return {"error": "AI extraction failed. The OpenAI request did not return valid data. "
                         "Please check the OpenAI API key/quota and try again."}

    # Pruefen ob ueberhaupt etwas Verwertbares drin ist
    n_foods = len(extracted.get('foods', []) or [])
    n_claims = len(extracted.get('claims', []) or [])
    n_nutrients = len(extracted.get('nutrients', []) or [])
    if n_foods == 0 and n_claims == 0 and n_nutrients == 0:
        return {"error": "No foods, health claims or nutrient data could be extracted from this document. "
                         "Make sure it actually contains nutrition/health content (not just a scan or images).",
                "extracted_data": extracted}

    if progress_callback:
        progress_callback("Importing into Airtable...")

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
