"""
Alive Food Database - Web Interface
====================================
Simple web interface for testing.

Start with: streamlit run app.py
"""

import streamlit as st
import os
import io
import json
import base64
import requests
import tempfile
import time
from pathlib import Path

# .env laden
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Claude (Anthropic)
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# Claude-Modell (Vision-faehig, schnell, guenstig)
CLAUDE_MODEL = "claude-haiku-4-5"

# PDF Support
try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

# PyMuPDF (fitz) - renders scanned PDFs to images so they can be OCR'd via vision
try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

# Data Engine v3 - Neue intelligente Import-Engine
try:
    from data_engine_v3 import (process_and_import, process_and_import_images,
                                DatabaseCache, extract_with_ai)
    HAS_ENGINE_V3 = True
except ImportError:
    HAS_ENGINE_V3 = False

# =============================================================================
# CONFIGURATION
# =============================================================================

def get_secret(key, default=None):
    """Gets a secret from environment variable OR Streamlit secrets"""
    # First try environment variable
    value = os.getenv(key)
    if value:
        return value
    # Then try Streamlit secrets
    try:
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
        # Workaround for typo
        if key == "AIRTABLE_TOKEN" and hasattr(st, 'secrets') and "aAIRTABLE_TOKEN" in st.secrets:
            return st.secrets["aAIRTABLE_TOKEN"]
    except:
        pass
    return default

BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appOFvKsPdHQQBOQ9")

def get_headers():
    """Gets headers with current token - call this at runtime, not import time"""
    token = get_secret("AIRTABLE_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

# Legacy - for backwards compatibility
AIRTABLE_TOKEN = None  # Will be loaded dynamically
HEADERS = None  # Will be loaded dynamically

TABLES = {
    "Interventions": "tblccYj8xSOtfMAL2",
    "Outcomes": "tblSAOa5AVZLaFqjR",
    "Claims": "tblqHCZ4d3ttrkhQh",
    "Sources": "tblcTzmqLRbvs0wAK",
    "Nutrients": "tblQo626zmoWlyZzW",
    "Food-Nutrient Profile": "tbl8HbmIrNpNHhrYH"
}

# =============================================================================
# PAGE CONFIG
# =============================================================================

st.set_page_config(
    page_title="Alive. Food Database",
    page_icon="▪",
    layout="wide"
)

# =============================================================================
# BRAND STYLING (Alive. — matches the scope-sheet aesthetic)
# =============================================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap');
:root{
  --bordeaux:#A03A2C; --bordeaux-deep:#8a3024; --olive:#6b7d5c; --ink:#2c2826;
  --muted:#6e6b66; --hairline:#e7e5e0; --cream:#ffffff; --cream-deep:#fafafa;
}
html, body, .stApp, button, input, textarea, [class^="st-"], [class*=" st-"]{
  font-family:'Figtree',-apple-system,BlinkMacSystemFont,sans-serif;
}
/* Material icons must keep their icon font, otherwise ligatures render as words
   (e.g. the file-uploader icon showing the text "upload"). */
[data-testid="stIconMaterial"], .material-icons, .material-icons-outlined,
[class*="material-symbols"]{
  font-family:'Material Symbols Rounded','Material Symbols Outlined','Material Icons' !important;
  font-feature-settings:'liga' !important;
}
.stApp{ background:var(--cream); color:var(--ink); }
.block-container{ padding-top:2.2rem; max-width:1080px; }
section[data-testid="stSidebar"]{ background:var(--cream-deep); border-right:1px solid var(--hairline); }
section[data-testid="stSidebar"] *{ color:var(--ink); }
h1,h2,h3,h4{ color:var(--ink); letter-spacing:-0.01em; font-weight:600; }
a, a:visited{ color:var(--bordeaux); }
hr{ border-color:var(--hairline); }

/* Brand header */
.alv-head{ border-bottom:2px solid var(--bordeaux); padding-bottom:10px; margin:0 0 24px;
  display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:6px; }
.alv-brand{ font-size:1.6rem; font-weight:700; color:var(--ink); letter-spacing:-0.02em; }
.alv-brand .dot{ color:var(--bordeaux); }
.alv-who{ font-size:0.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.1em; }
.alv-kicker{ font-size:0.72rem; font-weight:700; color:var(--bordeaux); text-transform:uppercase;
  letter-spacing:0.09em; margin-bottom:3px; }
.alv-title{ font-size:1.45rem; font-weight:600; color:var(--ink); margin:0 0 4px; letter-spacing:-0.01em; }
.alv-lead{ color:var(--muted); font-size:0.95rem; margin:0 0 6px; }

/* Buttons */
.stButton>button, .stDownloadButton>button, .stFormSubmitButton>button{
  background:var(--bordeaux); color:#fff !important; border:1px solid var(--bordeaux);
  border-radius:4px; font-weight:600; letter-spacing:0.01em; box-shadow:none; transition:background .15s ease;
}
.stButton>button:hover, .stDownloadButton>button:hover, .stFormSubmitButton>button:hover{
  background:var(--bordeaux-deep); border-color:var(--bordeaux-deep); color:#fff !important;
}
.stButton>button:focus, .stButton>button:active{ background:var(--bordeaux-deep); color:#fff !important; box-shadow:none; }

/* Inputs */
.stTextInput input{ background:#fff; color:var(--ink); border-radius:4px; }
.stTextInput div[data-baseweb="input"]{ border:1px solid var(--hairline); border-radius:4px; }

/* Metrics — editorial card with bordeaux rule */
[data-testid="stMetric"]{ background:#fff; border:1px solid var(--hairline); border-left:3px solid var(--bordeaux);
  border-radius:0 6px 6px 0; padding:10px 14px; }
[data-testid="stMetricValue"]{ font-family:'JetBrains Mono',monospace; color:var(--bordeaux); font-size:1.35rem; }
[data-testid="stMetricLabel"]{ color:var(--muted); text-transform:uppercase; letter-spacing:0.06em; font-size:0.72rem; }

/* File uploader */
[data-testid="stFileUploaderDropzone"]{ background:#fff; border:1px dashed #cdc9bf; }

/* Expanders */
[data-testid="stExpander"]{ border:1px solid var(--hairline); border-radius:6px; background:#fff; }
[data-testid="stExpander"] summary{ font-weight:600; color:var(--ink); }

/* Alerts */
[data-testid="stAlert"]{ border-radius:6px; }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# PASSWORD PROTECTION
# =============================================================================

# Passwort für Matthias
CORRECT_PASSWORD = "AliveFoodDB2026!"

def check_password():
    """Simple password check"""

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.markdown("""
    <div class="alv-head">
      <span class="alv-brand">Alive<span class="dot">.</span> Food Database</span>
      <span class="alv-who">Ezeyflow × Alive.</span>
    </div>
    <div class="alv-kicker">Sign in</div>
    <div class="alv-lead">Enter the password to continue.</div>
    """, unsafe_allow_html=True)

    password = st.text_input("Password", type="password", label_visibility="collapsed",
                             placeholder="Password")

    if st.button("Log in", type="primary"):
        if password == CORRECT_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Wrong password.")

    st.markdown("---")
    st.markdown("")

    return False

# Prüfe Passwort
if not check_password():
    st.stop()

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_all_records(table_id):
    """Holt alle Records einer Tabelle"""
    all_records = []
    offset = None
    headers = get_headers()  # Get headers at runtime

    while True:
        params = {}
        if offset:
            params['offset'] = offset

        resp = requests.get(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=headers,
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


def load_database():
    """Lädt die Datenbank für Queries"""
    foods = {}
    interventions = get_all_records(TABLES["Interventions"])
    for r in interventions:
        foods[r['id']] = {
            'name': r['fields'].get('Name', ''),
            'type': r['fields'].get('Type (STRICT)', ''),
            'category': r['fields'].get('Category', ''),
            'nutritional_roles': r['fields'].get('Nutritional role (high-level)', []),
            'summary': r['fields'].get('Short summary (human-readable)', ''),
            'example_serving': r['fields'].get('Example serving', ''),
        }

    claims = get_all_records(TABLES["Claims"])
    claims_data = []
    for r in claims:
        claims_data.append({
            'claim_text': r['fields'].get('Claim Text', ''),
            'evidence': r['fields'].get('Evidence Strength', ''),
            'intervention_ids': r['fields'].get('Intervention', []),
            'outcome_ids': r['fields'].get('Health Outcome', [])
        })

    outcomes = get_all_records(TABLES["Outcomes"])
    outcomes_data = {}
    for r in outcomes:
        outcomes_data[r['id']] = {
            'name': r['fields'].get('Name', ''),
            'category': r['fields'].get('Health Category', '')
        }

    nutrients = get_all_records(TABLES["Nutrients"])
    nutrients_data = {}
    for r in nutrients:
        nutrients_data[r['id']] = {
            'name': r['fields'].get('Name', ''),
            'unit': r['fields'].get('Unit', '')
        }

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

    return {
        'foods': foods,
        'claims': claims_data,
        'outcomes': outcomes_data,
        'nutrients': nutrients_data,
        'profiles': profiles_data
    }


def find_foods_for_goal(db, health_goal):
    """Findet Foods für ein Gesundheitsziel"""
    goal_lower = health_goal.lower()
    matching_foods = []

    # Finde passende Outcomes
    matching_outcome_ids = []
    for oid, outcome in db['outcomes'].items():
        if goal_lower in outcome['name'].lower():
            matching_outcome_ids.append(oid)

    # Finde Claims mit diesen Outcomes
    for claim in db['claims']:
        for oid in claim['outcome_ids']:
            if oid in matching_outcome_ids:
                for fid in claim['intervention_ids']:
                    if fid in db['foods']:
                        food = db['foods'][fid]
                        nutrients = []
                        for profile in db['profiles']:
                            if profile['food_id'] == fid:
                                nid = profile['nutrient_id']
                                if nid in db['nutrients']:
                                    nutrients.append({
                                        'name': db['nutrients'][nid]['name'],
                                        'amount': profile['amount_per_100g'],
                                        'unit': db['nutrients'][nid].get('unit', 'g')
                                    })

                        matching_foods.append({
                            'name': food['name'],
                            'category': food['category'],
                            'claim': claim['claim_text'],
                            'evidence': claim['evidence'],
                            'summary': food['summary'],
                            'serving': food['example_serving'],
                            'nutrients': nutrients[:5]
                        })

    # Deduplizieren
    seen = set()
    unique_foods = []
    for f in matching_foods:
        if f['name'] not in seen:
            seen.add(f['name'])
            unique_foods.append(f)

    return unique_foods


def generate_recipe_recommendation(foods, health_goal):
    """Generates a recipe recommendation with Claude."""
    key = get_secret("ANTHROPIC_API_KEY")
    if not HAS_ANTHROPIC or not key:
        return "Claude API key not configured."

    if not foods:
        return f"No foods found for '{health_goal}' in the database."

    client = anthropic.Anthropic(api_key=key)
    foods_context = json.dumps(foods[:8], indent=2, ensure_ascii=False)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            system=("You are a nutritionist for a restaurant. Based on the database, "
                    "you recommend ingredients for a dish. Answer in English, practical "
                    "and culinarily inspiring. Mention specific portion sizes and why each "
                    "ingredient is beneficial."),
            messages=[{"role": "user", "content": f"""The guest wants a dish for: {health_goal}

Available ingredients from our database:
{foods_context}

Create a recommendation with:
1. Top 3-5 recommended ingredients with reasoning
2. A concrete dish idea
3. Nutrient highlights"""}],
        )
    except Exception as e:
        return f"Could not generate a recommendation: {e}"

    return "".join(b.text for b in response.content if b.type == "text")


def normalize_name(name):
    """Normalisiert Namen für Duplikat-Erkennung"""
    if not name:
        return ""
    normalized = name.lower().strip()
    normalized = normalized.replace('(', ' ').replace(')', ' ')
    normalized = normalized.replace('-', ' ').replace('_', ' ')
    normalized = ' '.join(normalized.split())
    return normalized


def find_existing_record(table_id, field_name, value):
    """Sucht nach existierendem Record"""
    records = get_all_records(table_id)
    normalized_value = normalize_name(value)

    for r in records:
        record_value = r['fields'].get(field_name, '')
        if normalize_name(record_value) == normalized_value:
            return r['id']
    return None


def create_record(table_id, fields):
    """Erstellt einen neuen Record"""
    headers = get_headers()
    resp = requests.post(
        f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
        headers=headers,
        json={"fields": fields}
    )
    if resp.status_code == 200:
        return resp.json().get('id')
    return None


def get_or_create_intervention(name, category, summary=""):
    """Holt oder erstellt eine Intervention (Food)"""
    existing_id = find_existing_record(TABLES["Interventions"], "Name", name)
    if existing_id:
        return existing_id, False  # ID, wurde nicht neu erstellt

    fields = {
        "Name": name,
        "Type (STRICT)": "Food",
        "Category": category,
        "Is plant-based?": True,
        "Is whole food?": True
    }
    if summary:
        fields["Short summary (human-readable)"] = summary

    new_id = create_record(TABLES["Interventions"], fields)
    return new_id, True  # ID, wurde neu erstellt


def get_or_create_outcome(name, category="General"):
    """Holt oder erstellt ein Health Outcome"""
    existing_id = find_existing_record(TABLES["Outcomes"], "Name", name)
    if existing_id:
        return existing_id, False

    fields = {
        "Name": name,
        "Health Category": category
    }
    new_id = create_record(TABLES["Outcomes"], fields)
    return new_id, True


def get_or_create_nutrient(name, unit="g"):
    """Holt oder erstellt einen Nutrient"""
    existing_id = find_existing_record(TABLES["Nutrients"], "Name", name)
    if existing_id:
        return existing_id, False

    # Kategorie basierend auf Name
    category = "Other"
    name_lower = name.lower()
    if any(v in name_lower for v in ['vitamin', 'folate', 'niacin', 'riboflavin', 'thiamin']):
        category = "Micronutrient"
    elif any(m in name_lower for m in ['calcium', 'iron', 'magnesium', 'potassium', 'zinc', 'sodium']):
        category = "Micronutrient"
    elif any(p in name_lower for p in ['protein', 'carbohydrate', 'fat', 'fiber']):
        category = "Macronutrient"
    elif any(ph in name_lower for ph in ['polyphenol', 'anthocyanin', 'flavonoid', 'carotenoid']):
        category = "Phytonutrient"

    fields = {
        "Name": name,
        "Category": category,
        "Unit": unit
    }
    new_id = create_record(TABLES["Nutrients"], fields)
    return new_id, True


def create_source(title, source_type="Study"):
    """Erstellt eine neue Source"""
    # Richtiger Feldname in Airtable ist "Source (canonical name)"
    existing_id = find_existing_record(TABLES["Sources"], "Source (canonical name)", title)
    if existing_id:
        return existing_id, False

    fields = {
        "Source (canonical name)": title,
        "Source Type": source_type
    }
    new_id = create_record(TABLES["Sources"], fields)
    return new_id, True


def create_claim(intervention_id, outcome_ids, claim_text, evidence="Moderate", source_id=None):
    """Erstellt einen neuen Claim"""
    fields = {
        "Intervention": [intervention_id],
        "Health Outcome": outcome_ids,
        "Claim Text": claim_text,
        "Evidence Strength": evidence
    }
    if source_id:
        fields["Source"] = [source_id]

    return create_record(TABLES["Claims"], fields)


def create_food_nutrient_profile(food_id, nutrient_id, amount_per_100g, unit="g"):
    """Erstellt ein Food-Nutrient Profile"""
    # Prüfe ob schon existiert
    profiles = get_all_records(TABLES["Food-Nutrient Profile"])
    for p in profiles:
        food_links = p['fields'].get('Food', [])
        nutrient_links = p['fields'].get('Nutrient', [])
        if food_links and nutrient_links:
            if food_links[0] == food_id and nutrient_links[0] == nutrient_id:
                return p['id'], False  # Existiert bereits

    fields = {
        "Food": [food_id],
        "Nutrient": [nutrient_id],
        "Amount per 100g": amount_per_100g
    }
    new_id = create_record(TABLES["Food-Nutrient Profile"], fields)
    return new_id, True


def save_to_airtable(extracted_data):
    """Speichert extrahierte Daten in Airtable"""
    stats = {
        "sources_created": 0,
        "foods_created": 0,
        "foods_existing": 0,
        "outcomes_created": 0,
        "claims_created": 0,
        "nutrients_created": 0,
        "profiles_created": 0,
        "errors": []
    }

    # 1. Source erstellen
    source_id = None
    source_title = extracted_data.get('source_title', 'Unknown Source')
    source_type = extracted_data.get('source_type', 'Study')

    try:
        source_id, created = create_source(source_title, source_type)
        if created:
            stats["sources_created"] += 1
    except Exception as e:
        stats["errors"].append(f"Source error: {str(e)}")

    # 2. Foods erstellen und IDs merken
    food_ids = {}  # name -> id mapping
    for food in extracted_data.get('foods', []):
        try:
            food_name = food.get('name', '')
            if not food_name:
                continue

            food_id, created = get_or_create_intervention(
                name=food_name,
                category=food.get('category', 'Other'),
                summary=food.get('summary', '')
            )

            if food_id:
                food_ids[food_name.lower()] = food_id
                if created:
                    stats["foods_created"] += 1
                else:
                    stats["foods_existing"] += 1
        except Exception as e:
            stats["errors"].append(f"Food error ({food_name}): {str(e)}")

    # 3. Claims erstellen
    for claim in extracted_data.get('claims', []):
        try:
            food_name = claim.get('food_name', '')
            food_id = food_ids.get(food_name.lower())

            if not food_id:
                # Versuche Food zu finden/erstellen
                food_id, created = get_or_create_intervention(food_name, "Other")
                if food_id:
                    food_ids[food_name.lower()] = food_id
                    if created:
                        stats["foods_created"] += 1

            if not food_id:
                continue

            # Outcomes erstellen
            outcome_ids = []
            for outcome_name in claim.get('health_outcomes', []):
                outcome_id, created = get_or_create_outcome(outcome_name)
                if outcome_id:
                    outcome_ids.append(outcome_id)
                    if created:
                        stats["outcomes_created"] += 1

            if outcome_ids:
                claim_id = create_claim(
                    intervention_id=food_id,
                    outcome_ids=outcome_ids,
                    claim_text=claim.get('claim_text', ''),
                    evidence=claim.get('evidence_strength', 'Moderate'),
                    source_id=source_id
                )
                if claim_id:
                    stats["claims_created"] += 1
        except Exception as e:
            stats["errors"].append(f"Claim error: {str(e)}")

    # 4. Nutrient Data erstellen
    for nutrient_set in extracted_data.get('nutrient_data', []):
        try:
            food_name = nutrient_set.get('food_name', '')
            food_id = food_ids.get(food_name.lower())

            if not food_id:
                food_id, created = get_or_create_intervention(food_name, "Other")
                if food_id:
                    food_ids[food_name.lower()] = food_id

            if not food_id:
                continue

            for nutrient in nutrient_set.get('nutrients', []):
                nutrient_name = nutrient.get('name', '')
                if not nutrient_name:
                    continue

                nutrient_id, created = get_or_create_nutrient(
                    nutrient_name,
                    nutrient.get('unit', 'g')
                )
                if created:
                    stats["nutrients_created"] += 1

                if nutrient_id:
                    profile_id, created = create_food_nutrient_profile(
                        food_id,
                        nutrient_id,
                        nutrient.get('amount_per_100g', 0),
                        nutrient.get('unit', 'g')
                    )
                    if created:
                        stats["profiles_created"] += 1
        except Exception as e:
            stats["errors"].append(f"Nutrient error: {str(e)}")

    return stats


# =============================================================================
# SCANNED PDFs - render pages to images so Claude can read them directly
# =============================================================================

def render_pdf_to_images(pdf_bytes, max_pages=15):
    """Renders PDF pages to base64 PNGs.

    Used when a PDF has no extractable text layer (scanned or photographed pages):
    the page images are then sent to Claude vision for direct extraction.
    Returns a list of base64-encoded PNG strings (empty list on failure).
    """
    if not HAS_FITZ:
        return []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        print(f"Could not open PDF for rendering: {e}")
        return []

    images = []
    n_pages = min(len(doc), max_pages)
    for i in range(n_pages):
        try:
            pix = doc[i].get_pixmap(dpi=160)
            images.append(base64.b64encode(pix.tobytes("png")).decode())
        except Exception as e:
            print(f"Render error on page {i + 1}: {e}")
    try:
        doc.close()
    except Exception:
        pass
    return images


def _extract_file_content(uploaded_file):
    """Liest eine hochgeladene Datei und gibt (text, pdf_images, error) zurueck.

    - text: extrahierter Text (TXT oder PDF mit Textlayer)
    - pdf_images: Seitenbilder (gescannte / Bild-PDFs -> Vision-Pfad), sonst None
    - error: Fehlermeldung als String, sonst None
    """
    if uploaded_file.name.lower().endswith('.pdf'):
        if not HAS_PDF:
            return "", None, "PDF support is not installed (pdfplumber missing)."
        pdf_bytes = uploaded_file.getvalue()
        text = ""
        total_pages = 0
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            with pdfplumber.open(tmp_path) as pdf:
                total_pages = len(pdf.pages)
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n\n"
            os.unlink(tmp_path)
        except Exception as e:
            return "", None, f"Could not read this PDF: {e}"

        # No text layer -> render the pages so Claude vision can read them directly
        # (handles scanned or photographed / image-only PDFs).
        if not text.strip():
            pdf_images = None
            if HAS_FITZ and HAS_ANTHROPIC:
                pdf_images = render_pdf_to_images(pdf_bytes)
            if not pdf_images:
                return "", None, (
                    f"Could not read this PDF ({total_pages} page(s)). The pages may be blank "
                    "or unreadable. Try a clearer scan, a text-based PDF, or paste the text "
                    "into a .txt file."
                )
            return "", pdf_images, None
        return text, None, None

    # TXT (oder andere Textdatei)
    try:
        text = uploaded_file.getvalue().decode('utf-8')
    except UnicodeDecodeError:
        text = uploaded_file.getvalue().decode('utf-8', errors='replace')
    if not text.strip():
        return "", None, "This text file appears to be empty."
    return text, None, None


def _show_import_result(result, uploaded_file):
    """Zeigt das Import-Ergebnis einer einzelnen Datei (Statistiken + Details)."""
    extracted = result.get('extracted_data', {})

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        sources_info = f"{result.get('sources_created', 0)} new"
        if result.get('sources_updated', 0):
            sources_info += f", {result['sources_updated']} updated"
        st.metric("Sources", sources_info)
    with col2:
        foods_info = f"{result.get('interventions_created', 0)} new"
        if result.get('interventions_updated', 0):
            foods_info += f", {result['interventions_updated']} upd."
        st.metric("Foods", foods_info)
    with col3:
        st.metric("Claims", result.get('claims_created', 0))
    with col4:
        st.metric("Nutrients", result.get('nutrients_created', 0))

    if extracted.get('foods'):
        with st.expander(f"Foods ({len(extracted['foods'])})"):
            for food in extracted['foods']:
                st.markdown(f"**{food.get('name')}** ({food.get('category', 'N/A')})")
                if food.get('summary'):
                    st.write(f"  {food['summary'][:200]}...")

    if extracted.get('claims'):
        with st.expander(f"Health claims ({len(extracted['claims'])})"):
            for claim in extracted['claims']:
                st.markdown(f"**{claim.get('food_name')}** -> {', '.join(claim.get('outcome_names', []))}")
                st.write(f"  \"{claim.get('claim_text', '')[:150]}...\"")

    if extracted.get('nutrients'):
        with st.expander(f"Nutrients ({len(extracted['nutrients'])})"):
            for ns in extracted['nutrients']:
                st.write(f"**{ns.get('food_name')}:**")
                for n in ns.get('nutrients', []):
                    st.write(f"  - {n.get('name')}: {n.get('amount_per_100g')} {n.get('unit', 'g')}/100g")

    if result.get('errors'):
        with st.expander(f"Warnings ({len(result['errors'])})"):
            for err in result['errors']:
                st.warning(err)


# =============================================================================
# MAIN APP
# =============================================================================

st.markdown("""
<div class="alv-head">
  <span class="alv-brand">Alive<span class="dot">.</span> Food Database</span>
  <span class="alv-who">Data engine · health claims &amp; nutrient data</span>
</div>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.markdown('<div class="alv-kicker">Navigation</div>', unsafe_allow_html=True)
page = st.sidebar.radio("Navigation", [
    "AI Query",
    "Upload"
], label_visibility="collapsed")

# =============================================================================
# PAGE: KI QUERY
# =============================================================================

if page == "AI Query":
    st.markdown("""
    <div class="alv-kicker">Query</div>
    <div class="alv-title">Health goal → ingredients</div>
    <div class="alv-lead">Enter a health goal and get matching ingredients recommended.</div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])

    with col1:
        health_goal = st.text_input(
            "Enter health goal:",
            placeholder="e.g. Gut Health, Heart Health, Brain Health..."
        )

    with col2:
        st.write("")
        st.write("")
        search_button = st.button("Search", type="primary")

    # Quick buttons
    st.markdown('<div class="alv-kicker">Quick selection</div>', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("Heart Health"):
            health_goal = "Heart Health"
            search_button = True
    with col2:
        if st.button("Brain Health"):
            health_goal = "Brain Health"
            search_button = True
    with col3:
        if st.button("Gut Health"):
            health_goal = "Gut Health"
            search_button = True
    with col4:
        if st.button("Inflammation"):
            health_goal = "Inflammation"
            search_button = True

    if search_button and health_goal:
        with st.spinner("Loading database..."):
            db = load_database()

        with st.spinner(f"Searching for '{health_goal}'..."):
            foods = find_foods_for_goal(db, health_goal)

        if foods:
            st.success(f"{len(foods)} matching ingredients found.")

            # Show found foods
            st.markdown('<div class="alv-kicker" style="margin-top:8px">Found ingredients</div>', unsafe_allow_html=True)
            for i, food in enumerate(foods[:5], 1):
                with st.expander(f"{i}. {food['name']} ({food['category']})"):
                    st.write(f"**Summary:** {food['summary']}")
                    st.write(f"**Serving:** {food['serving']}")
                    st.write(f"**Claim:** {food['claim']}")
                    st.write(f"**Evidence:** {food['evidence']}")
                    if food['nutrients']:
                        st.write("**Nutrients (per 100g):**")
                        for n in food['nutrients']:
                            st.write(f"- {n['name']}: {n['amount']} {n['unit']}")

            # AI Recommendation
            st.markdown('<div class="alv-kicker" style="margin-top:8px">Recipe recommendation</div>', unsafe_allow_html=True)
            with st.spinner("Generating recommendation..."):
                recommendation = generate_recipe_recommendation(foods, health_goal)
            st.markdown(recommendation)
        else:
            st.warning(f"No ingredients found for '{health_goal}'. Try a different term.")

# =============================================================================
# PAGE: PDF UPLOAD
# =============================================================================

elif page == "Upload":
    st.markdown("""
    <div class="alv-kicker">Upload</div>
    <div class="alv-title">Process a study or document</div>
    <div class="alv-lead">Upload a PDF or text file. The AI extracts the foods, health claims and nutrient data and adds them to the database.</div>
    """, unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        "Upload files (PDF or TXT):",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        help="The AI analyzes each file and extracts foods, health claims and nutrient data. You can select several files at once for a bulk import."
    )

    if uploaded_files:
        st.info(
            f"{len(uploaded_files)} file(s) selected: "
            + ", ".join(f.name for f in uploaded_files)
        )

        if not HAS_ENGINE_V3:
            st.error("Data engine not available (data_engine_v3.py is missing).")
        elif st.button(f"Analyze & import {len(uploaded_files)} file(s) to Airtable", type="primary"):
            n_files = len(uploaded_files)
            # Gesamt-Fortschritt ueber alle Dateien + laufender Phasen-Text, damit man
            # bei einem Bulk-Import sieht wie weit es ist (nicht nur hoffend rumhocken).
            progress_bar = st.progress(0.0, text=f"Starting import of {n_files} file(s)...")
            totals = {"ok": 0, "failed": 0, "sources": 0, "foods": 0, "claims": 0, "nutrients": 0}

            for idx, uploaded_file in enumerate(uploaded_files, 1):
                base_frac = (idx - 1) / n_files
                prefix = f"File {idx} of {n_files}: {uploaded_file.name}"
                progress_bar.progress(base_frac, text=f"{prefix} — reading file...")

                def update_progress(message, _p=prefix, _f=base_frac):
                    progress_bar.progress(_f, text=f"{_p} — {message}")

                # 1. Inhalt lesen (Text-PDF, gescanntes PDF -> Bilder, oder TXT)
                text, pdf_images, err = _extract_file_content(uploaded_file)
                if err:
                    totals["failed"] += 1
                    with st.expander(f"{uploaded_file.name} - could not read", expanded=True):
                        st.error(err)
                    continue

                # 2. Extrahieren + importieren
                try:
                    update_progress("loading database...")
                    if pdf_images:
                        result = process_and_import_images(pdf_images, progress_callback=update_progress)
                    else:
                        result = process_and_import(text, progress_callback=update_progress)
                except Exception as e:
                    totals["failed"] += 1
                    with st.expander(f"{uploaded_file.name} - error", expanded=True):
                        st.error(f"Critical error: {e}")
                        import traceback
                        st.code(traceback.format_exc())
                    continue

                # 3. Ergebnis anzeigen
                if "error" in result:
                    totals["failed"] += 1
                    with st.expander(f"{uploaded_file.name} - {result['error'][:80]}", expanded=True):
                        st.error(result['error'])
                else:
                    totals["ok"] += 1
                    totals["sources"] += result.get('sources_created', 0)
                    totals["foods"] += result.get('interventions_created', 0)
                    totals["claims"] += result.get('claims_created', 0)
                    totals["nutrients"] += result.get('nutrients_created', 0)
                    with st.expander(f"{uploaded_file.name} - imported", expanded=(n_files == 1)):
                        _show_import_result(result, uploaded_file)

            progress_bar.progress(1.0, text=f"Done — processed {n_files} file(s).")

            # Gesamt-Zusammenfassung ueber alle Dateien
            st.divider()
            st.markdown('<div class="alv-kicker">Bulk import summary</div>', unsafe_allow_html=True)
            if totals["failed"] == 0:
                st.success(f"All {totals['ok']} file(s) imported. The database has been expanded.")
            elif totals["ok"] == 0:
                st.error(f"None of the {n_files} file(s) could be imported. See the messages above.")
            else:
                st.warning(f"{totals['ok']} of {n_files} file(s) imported, {totals['failed']} failed. See details above.")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sources", totals["sources"])
            c2.metric("Foods", totals["foods"])
            c3.metric("Claims", totals["claims"])
            c4.metric("Nutrients", totals["nutrients"])

# =============================================================================
# FOOTER
# =============================================================================

st.markdown(f"""
<div style="margin-top:36px; padding-top:10px; border-top:1px solid var(--hairline);
     display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;
     font-size:0.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em;">
  <span>Alive. Food Database · Version 1</span>
  <span><a href="https://airtable.com/{BASE_ID}" target="_blank" style="color:var(--bordeaux); text-decoration:none;">Open Airtable ›</a> &nbsp;·&nbsp; Ezeyflow × Alive.</span>
</div>
""", unsafe_allow_html=True)
