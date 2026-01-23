# Alive Food Database - Data Engine

## Quick Start

### Option 1: Einfach (Windows)
1. Doppelklick auf `START_HIER.bat`
2. Menu folgen

### Option 2: Terminal
```bash
cd "C:\Users\marli\Restaurant Datenbank"
python data_engine_v2.py meine_studie.pdf
```

---

## PDF/Studie verarbeiten

### Schritt 1: Datei vorbereiten
- PDF oder TXT Datei mit Studiendaten
- Muss Naehrstoffdaten oder Health Claims enthalten

### Schritt 2: Data Engine starten
```bash
python data_engine_v2.py pfad/zur/studie.pdf
```

Oder mit kleinerem Modell (guenstiger):
```bash
python data_engine_v2.py pfad/zur/studie.pdf --model gpt-4o-mini
```

### Schritt 3: Ergebnis pruefen
- Oeffne Airtable: https://airtable.com/appOFvKsPdHQQBOQ9
- Neue Eintraege erscheinen in allen relevanten Tabellen

---

## KI Query - Zutaten finden

### Gesundheitsziel → Zutaten
```bash
python query_demo.py "Gut Health"
python query_demo.py "Heart Health"
python query_demo.py "Brain Health"
```

### Interaktiver Modus
```bash
python query_demo.py
```
Dann:
- `health Gut Health` - Zutaten fuer Darmgesundheit
- `food Flaxseed` - Alle Infos zu Leinsamen
- `list` - Alle Foods anzeigen
- `quit` - Beenden

---

## Was wird automatisch extrahiert?

| Aus der Studie | In Airtable |
|----------------|-------------|
| Titel, Autor, Jahr | Sources |
| Lebensmittel | Interventions |
| Health Claims | Claims + Outcomes |
| Naehrstoffwerte | Nutrients + Food-Nutrient Profile |

---

## Beispiel-Studien zum Testen

### Kostenlose Studien (Open Access):
1. **PubMed Central**: https://www.ncbi.nlm.nih.gov/pmc/
   - Suche: "flaxseed cardiovascular" oder "plant-based nutrition"
   - Filter: "Free full text"

2. **NutritionFacts.org**: https://nutritionfacts.org/topics/
   - Zusammenfassungen von Studien

3. **Examine.com**: https://examine.com/
   - Naehrstoff-Datenbank

---

## Troubleshooting

### "pdfplumber not found"
```bash
pip install pdfplumber
```

### "openai not found"
```bash
pip install openai
```

### API Key Fehler
OpenAI API Key ist bereits im Script hinterlegt.

---

## Dateien in diesem Ordner

| Datei | Funktion |
|-------|----------|
| `START_HIER.bat` | Einfaches Menu (Windows) |
| `data_engine_v2.py` | Haupt-Script fuer PDF-Verarbeitung |
| `query_demo.py` | KI Query fuer Zutaten-Empfehlungen |
| `fix_serving_sizes.py` | Einmalig: Serving Sizes nachtragen |
| `test_studie.txt` | Test-Datei zum Ausprobieren |

---

## Airtable Struktur

```
Sources (Quellen)
    ↓
Interventions (Foods/Habits)
    ↓
Claims (Health Claims) ←→ Outcomes (Health Goals)
    ↓
Food-Nutrient Profile ←→ Nutrients
```

---

## Kontakt

Bei Fragen: [Dein Kontakt hier]
