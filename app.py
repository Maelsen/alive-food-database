"""
Alive Food Database - Web Interface
====================================
Einfache Web-Oberfläche für Matthias zum Testen.

Starten mit: streamlit run app.py
"""

import streamlit as st
import os
import json
import requests
import tempfile
from pathlib import Path

# .env laden
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

# PDF Support
try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

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
    page_title="Alive Food Database",
    page_icon="🥗",
    layout="wide"
)

# =============================================================================
# PASSWORD PROTECTION
# =============================================================================

# Passwort für Matthias
CORRECT_PASSWORD = "AliveFoodDB2024!"

def check_password():
    """Einfache Passwort-Abfrage"""

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.title("🔐 Login")
    st.markdown("Bitte Passwort eingeben um fortzufahren.")

    password = st.text_input("Passwort:", type="password")

    if st.button("Einloggen", type="primary"):
        if password == CORRECT_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Falsches Passwort!")

    st.markdown("---")
    st.markdown("*Passwort vergessen? Kontaktiere den Administrator.*")

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
    """Generiert KI-Empfehlung"""
    if not HAS_OPENAI or not OPENAI_API_KEY:
        return "OpenAI API Key nicht konfiguriert."

    if not foods:
        return f"Keine Foods für '{health_goal}' in der Datenbank gefunden."

    client = OpenAI(api_key=OPENAI_API_KEY)

    foods_context = json.dumps(foods[:8], indent=2, ensure_ascii=False)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": """Du bist ein Ernährungsberater für ein Restaurant.
Basierend auf der Datenbank, empfiehlst du Zutaten für ein Gericht.
Antworte auf Deutsch, praktisch und kulinarisch inspirierend.
Nenne konkrete Portionsgrößen und warum jede Zutat gut ist."""},
            {"role": "user", "content": f"""Der Gast möchte ein Gericht für: {health_goal}

Verfügbare Zutaten aus unserer Datenbank:
{foods_context}

Erstelle eine Empfehlung mit:
1. Top 3-5 empfohlene Zutaten mit Begründung
2. Eine konkrete Gerichtidee
3. Nährstoff-Highlights"""}
        ],
        temperature=0.7
    )

    return response.choices[0].message.content


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
    resp = requests.post(
        f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
        headers=HEADERS,
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
    existing_id = find_existing_record(TABLES["Sources"], "Title", title)
    if existing_id:
        return existing_id, False

    fields = {
        "Title": title,
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


def process_pdf_with_ai(text, model="gpt-4o-mini"):
    """Verarbeitet Text mit KI"""
    if not HAS_OPENAI or not OPENAI_API_KEY:
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Kürzen wenn zu lang
    if len(text) > 50000:
        text = text[:50000]

    prompt = """Analysiere den folgenden Text und extrahiere ALLE Health Claims und Nährstoffdaten.

Antworte NUR mit validem JSON in diesem Format:
{
    "source_title": "Titel des Dokuments",
    "source_type": "Study/Book/Article",
    "foods": [
        {
            "name": "Food Name",
            "category": "Fruit/Vegetable/Nuts & seeds/etc.",
            "summary": "Kurze Beschreibung"
        }
    ],
    "claims": [
        {
            "food_name": "Food Name",
            "health_outcomes": ["Heart Health", "Brain Health"],
            "claim_text": "Der eigentliche Health Claim",
            "evidence_strength": "Strong (RCT/Meta-analysis)"
        }
    ],
    "nutrient_data": [
        {
            "food_name": "Food Name",
            "nutrients": [
                {"name": "Protein", "amount_per_100g": 18.3, "unit": "g"}
            ]
        }
    ]
}

TEXT ZUM ANALYSIEREN:
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Du bist ein Ernährungswissenschaftler. Antworte immer mit validem JSON."},
            {"role": "user", "content": prompt + text}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )

    return json.loads(response.choices[0].message.content)


# =============================================================================
# MAIN APP
# =============================================================================

st.title("🥗 Alive Food Database")
st.markdown("*Data Engine für Health Claims und Nährstoffdaten*")

# Sidebar
st.sidebar.title("Navigation")
page = st.sidebar.radio("Wähle eine Funktion:", [
    "🔍 KI Query",
    "📄 PDF hochladen",
    "📊 Datenbank ansehen"
])

# =============================================================================
# PAGE: KI QUERY
# =============================================================================

if page == "🔍 KI Query":
    st.header("🔍 Gesundheitsziel → Zutaten")
    st.markdown("Gib ein Gesundheitsziel ein und bekomme passende Zutaten empfohlen.")

    col1, col2 = st.columns([3, 1])

    with col1:
        health_goal = st.text_input(
            "Gesundheitsziel eingeben:",
            placeholder="z.B. Gut Health, Heart Health, Brain Health..."
        )

    with col2:
        st.write("")
        st.write("")
        search_button = st.button("🔍 Suchen", type="primary")

    # Quick buttons
    st.markdown("**Schnellauswahl:**")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("🫀 Heart Health"):
            health_goal = "Heart Health"
            search_button = True
    with col2:
        if st.button("🧠 Brain Health"):
            health_goal = "Brain Health"
            search_button = True
    with col3:
        if st.button("🦠 Gut Health"):
            health_goal = "Gut Health"
            search_button = True
    with col4:
        if st.button("💪 Inflammation"):
            health_goal = "Inflammation"
            search_button = True

    if search_button and health_goal:
        with st.spinner("Lade Datenbank..."):
            db = load_database()

        with st.spinner(f"Suche nach '{health_goal}'..."):
            foods = find_foods_for_goal(db, health_goal)

        if foods:
            st.success(f"✅ {len(foods)} passende Zutaten gefunden!")

            # Zeige gefundene Foods
            st.subheader("📋 Gefundene Zutaten:")
            for i, food in enumerate(foods[:5], 1):
                with st.expander(f"{i}. {food['name']} ({food['category']})"):
                    st.write(f"**Zusammenfassung:** {food['summary']}")
                    st.write(f"**Portion:** {food['serving']}")
                    st.write(f"**Claim:** {food['claim']}")
                    st.write(f"**Evidenz:** {food['evidence']}")
                    if food['nutrients']:
                        st.write("**Nährstoffe (pro 100g):**")
                        for n in food['nutrients']:
                            st.write(f"- {n['name']}: {n['amount']} {n['unit']}")

            # KI Empfehlung
            st.subheader("🤖 KI Rezept-Empfehlung:")
            with st.spinner("Generiere Empfehlung..."):
                recommendation = generate_recipe_recommendation(foods, health_goal)
            st.markdown(recommendation)
        else:
            st.warning(f"Keine Zutaten für '{health_goal}' gefunden. Versuche einen anderen Begriff.")

# =============================================================================
# PAGE: PDF UPLOAD
# =============================================================================

elif page == "📄 PDF hochladen":
    st.header("📄 PDF/Studie verarbeiten")
    st.markdown("Lade eine PDF oder Textdatei hoch und die KI extrahiert automatisch alle Health Claims und Nährstoffdaten.")

    uploaded_file = st.file_uploader(
        "Datei hochladen (PDF oder TXT):",
        type=["pdf", "txt"],
        help="Die KI analysiert die Datei und extrahiert Foods, Health Claims und Nährstoffdaten."
    )

    if uploaded_file:
        st.info(f"📁 Datei: {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")

        # Text extrahieren
        text = ""

        if uploaded_file.name.endswith('.pdf'):
            if not HAS_PDF:
                st.error("PDF-Support nicht installiert. Bitte pdfplumber installieren.")
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = tmp.name

                with pdfplumber.open(tmp_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n\n"

                os.unlink(tmp_path)
        else:
            text = uploaded_file.getvalue().decode('utf-8')

        if text:
            st.success(f"✅ {len(text)} Zeichen extrahiert")

            # Vorschau
            with st.expander("📖 Text-Vorschau"):
                st.text(text[:2000] + "..." if len(text) > 2000 else text)

            # Verarbeiten Button
            if st.button("🚀 Mit KI verarbeiten", type="primary"):
                with st.spinner("KI analysiert... (kann 30-60 Sekunden dauern)"):
                    result = process_pdf_with_ai(text)

                if result:
                    st.success("✅ Analyse abgeschlossen!")

                    # Ergebnisse anzeigen
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.metric("Foods gefunden", len(result.get('foods', [])))
                    with col2:
                        st.metric("Claims gefunden", len(result.get('claims', [])))
                    with col3:
                        st.metric("Nutrient-Sets", len(result.get('nutrient_data', [])))

                    # Details
                    st.subheader("📊 Extrahierte Daten:")

                    if result.get('foods'):
                        st.write("**Foods:**")
                        for food in result['foods']:
                            st.write(f"- {food.get('name')} ({food.get('category', 'N/A')})")

                    if result.get('claims'):
                        st.write("**Health Claims:**")
                        for claim in result['claims']:
                            st.write(f"- {claim.get('food_name')}: {claim.get('claim_text', '')[:100]}...")

                    # In Session speichern für Import
                    st.session_state['extracted_data'] = result

                    # JSON Download
                    st.download_button(
                        "📥 Ergebnis als JSON herunterladen",
                        data=json.dumps(result, indent=2, ensure_ascii=False),
                        file_name=f"extracted_{uploaded_file.name}.json",
                        mime="application/json"
                    )

                    st.divider()

                    # AIRTABLE IMPORT BUTTON
                    st.subheader("💾 In Airtable speichern")
                    st.markdown("Klicke um die extrahierten Daten direkt in die Airtable-Datenbank zu importieren.")

                    if st.button("🚀 Jetzt in Airtable speichern", type="primary"):
                        with st.spinner("Speichere in Airtable..."):
                            import_stats = save_to_airtable(result)

                        # Ergebnis anzeigen
                        if import_stats["errors"]:
                            st.warning(f"Import mit {len(import_stats['errors'])} Fehlern abgeschlossen")
                        else:
                            st.success("✅ Import erfolgreich!")

                        # Stats anzeigen
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Sources", import_stats["sources_created"], delta="neu")
                        with col2:
                            foods_new = import_stats["foods_created"]
                            foods_exist = import_stats["foods_existing"]
                            st.metric("Foods", f"{foods_new} neu", delta=f"{foods_exist} existierten")
                        with col3:
                            st.metric("Claims", import_stats["claims_created"], delta="neu")
                        with col4:
                            st.metric("Nutrients", import_stats["nutrients_created"], delta="neu")

                        if import_stats["profiles_created"]:
                            st.info(f"📊 {import_stats['profiles_created']} Nutrient-Profile erstellt")

                        if import_stats["errors"]:
                            with st.expander("⚠️ Fehler anzeigen"):
                                for err in import_stats["errors"]:
                                    st.error(err)

                        st.balloons()
                        st.success("🎉 Daten wurden in Airtable gespeichert! Du kannst die Datenbank jetzt ansehen.")
                else:
                    st.error("Fehler bei der Analyse. Bitte später erneut versuchen.")

# =============================================================================
# PAGE: DATABASE VIEW
# =============================================================================

elif page == "📊 Datenbank ansehen":
    st.header("📊 Datenbank-Übersicht")

    with st.spinner("Lade Datenbank..."):
        # Lade Stats
        interventions = get_all_records(TABLES["Interventions"])
        outcomes = get_all_records(TABLES["Outcomes"])
        claims = get_all_records(TABLES["Claims"])
        nutrients = get_all_records(TABLES["Nutrients"])
        profiles = get_all_records(TABLES["Food-Nutrient Profile"])
        sources = get_all_records(TABLES["Sources"])

    # Stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("🥗 Foods/Interventions", len(interventions))
        st.metric("📚 Sources", len(sources))
    with col2:
        st.metric("🎯 Health Outcomes", len(outcomes))
        st.metric("📝 Claims", len(claims))
    with col3:
        st.metric("🧪 Nutrients", len(nutrients))
        st.metric("📊 Nutrient Profiles", len(profiles))

    st.divider()

    # Foods Liste
    st.subheader("🥗 Foods in der Datenbank:")

    for intv in interventions:
        f = intv['fields']
        food_type = f.get('Type (STRICT)', '')
        if food_type in ['Food', 'Food group']:
            with st.expander(f"{f.get('Name', 'Unknown')} ({f.get('Category', 'N/A')})"):
                st.write(f"**Typ:** {food_type}")
                st.write(f"**Portion:** {f.get('Example serving', 'N/A')}")
                st.write(f"**Zusammenfassung:** {f.get('Short summary (human-readable)', 'N/A')}")

                roles = f.get('Nutritional role (high-level)', [])
                if roles:
                    st.write(f"**Nutritional Roles:** {', '.join(roles)}")

# =============================================================================
# FOOTER
# =============================================================================

st.divider()
st.markdown("---")
st.markdown("*Alive Food Database - Data Engine v2.0*")
st.markdown(f"[📊 Airtable öffnen](https://airtable.com/{BASE_ID})")
