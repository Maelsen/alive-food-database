# 🥗 Alive Food Database - Data Engine

Automatische Extraktion von Health Claims und Nährstoffdaten aus Studien/PDFs.

## 🚀 Quick Start

### 1. Installation

```bash
# Repository klonen
git clone https://github.com/DEIN_USERNAME/alive-food-database.git
cd alive-food-database

# Dependencies installieren
pip install -r requirements.txt
```

### 2. API Keys einrichten

```bash
# .env Datei erstellen
cp .env.example .env

# Keys eintragen (werden separat mitgeteilt)
```

### 3. Loslegen

**Windows:** Doppelklick auf `START_HIER.bat`

**Terminal:**
```bash
# PDF verarbeiten
python data_engine_v2.py studie.pdf

# KI Query
python query_demo.py "Gut Health"
```

---

## 📊 Was macht die Data Engine?

```
PDF/Studie hochladen
        ↓
   KI analysiert
        ↓
┌───────────────────────────────────────┐
│           AIRTABLE DATABASE           │
├───────────────────────────────────────┤
│ Sources      → Quelle mit Metadaten   │
│ Interventions → Foods/Habits          │
│ Outcomes     → Health Goals           │
│ Claims       → Evidence Links         │
│ Nutrients    → Nährstoff-Definitionen │
│ Food-Nutrient Profile → Gramm-Werte   │
└───────────────────────────────────────┘
```

---

## 🔍 KI Query

Frage nach einem Gesundheitsziel und bekomme passende Zutaten:

```bash
python query_demo.py "Gut Health"
```

**Output:**
- Top 3-5 empfohlene Zutaten
- Wissenschaftliche Begründung
- Konkrete Rezeptidee
- Nährstoff-Highlights

---

## 📁 Dateien

| Datei | Beschreibung |
|-------|--------------|
| `data_engine_v2.py` | Haupt-Script für PDF-Verarbeitung |
| `query_demo.py` | KI Query für Zutaten-Empfehlungen |
| `START_HIER.bat` | Einfaches Windows-Menu |
| `.env.example` | Vorlage für API Keys |

---

## 🔐 API Keys

Die `.env` Datei benötigt:
- `AIRTABLE_TOKEN` - Airtable Personal Access Token
- `AIRTABLE_BASE_ID` - ID der Airtable Base
- `OPENAI_API_KEY` - OpenAI API Key

**Keys werden separat mitgeteilt!**

---

## 📖 Unterstützte Formate

- PDF (Studien, Bücher)
- TXT (Notizen, Zusammenfassungen)
- MD (Markdown)

---

## 🏗️ Architektur

```
┌─────────────────┐
│    Sources      │ ← Bücher, Studien, Artikel
└────────┬────────┘
         │
┌────────▼────────┐
│  Interventions  │ ← Foods, Habits, Patterns
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼───┐ ┌───▼───┐
│Claims │ │Food-  │
│       │ │Nutrient│
└───┬───┘ │Profile│
    │     └───┬───┘
┌───▼───┐ ┌───▼───┐
│Outcomes│ │Nutrients│
└───────┘ └────────┘
```

---

## 🧪 Testen

```bash
# Test mit Beispieldatei
python data_engine_v2.py test_studie.txt

# KI Query testen
python query_demo.py "Heart Health"
```

---

Made with ❤️ for Alive Food
