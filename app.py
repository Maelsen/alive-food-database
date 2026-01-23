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

                    # JSON Download
                    st.download_button(
                        "📥 Ergebnis als JSON herunterladen",
                        data=json.dumps(result, indent=2, ensure_ascii=False),
                        file_name=f"extracted_{uploaded_file.name}.json",
                        mime="application/json"
                    )

                    st.info("💡 Die Daten können jetzt in Airtable importiert werden.")
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
