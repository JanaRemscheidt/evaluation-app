# Evaluation App

Eine kleine Flask-Anwendung zum Durchführen von Persona-basierten Event-Rankings.

**Kurzbeschreibung**
- Zeigt nacheinander Personas an und präsentiert zu jeder Persona 10 Events.
- Speichert die abgeschickten Ranglisten in einer SQLite-Datenbank (`data/evaluation.sqlite3`).

**Voraussetzungen**
- Python 3.10+ (oder kompatible 3.x-Version)
- Virtuelle Umgebung empfohlen

**Installation**
1. Klone das Repository oder lade die Dateien in ein Verzeichnis.
2. Wechsle in das Projektverzeichnis:

```bash
cd evaluation-app
```

3. Erstelle und aktiviere eine virtuelle Umgebung (Windows):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

4. Installiere die Abhängigkeiten:

```bash
pip install -r requirements.txt
```

**Starten der Anwendung**

```bash
python app.py
```

Die App läuft standardmäßig auf `http://0.0.0.0:5005`.

**Deployment (Wasmer / Wasix)**

Wenn du die App bei Wasmer/Wasix hosten willst, verwende folgende Einstellungen:

- Install-Command: `pip install -r requirements.txt`
- Start-Command: `uvicorn app:app --interface wsgi --host 0.0.0.0 --port ${PORT:-8080}`

Wichtig: das WSGI-Target muss auf `app:app` zeigen (nicht `a:app`), da die Flask-Instanz in `app.py` als `app` definiert ist.

**Projektstruktur (Kurzüberblick)**
- `app.py` – Haupt-Flask-Anwendung und Routen
- `requirements.txt` – Python-Abhängigkeiten
- `data/` – enthaltene JSON- und SQLite-Dateien (`personas.json`, `persona_rankings/`, `evaluation.sqlite3`)
- `static/` – CSS/JS Dateien
- `templates/` – Jinja2-Templates (`index.html`, `complete.html`)

**Daten & Speicher**
- Personas werden aus `data/personas.json` geladen.
- Vorab vorhandene persona-Rankings liegen in `data/persona_rankings/events_persona_XX.json`.
- Benutzer-Rankings werden in `data/evaluation.sqlite3` in den Tabellen `ranking_submissions` und `ranking_submission_items` gespeichert.

**Wichtige Routen**
- `/` – Einstieg; leitet zur nächsten offenen Persona weiter
- `/persona/<persona_id>` – Seite zur Präsentation einer Persona und ihrer Events
- `/persona/<persona_id>/complete` – POST-Endpoint zum Speichern einer Rangliste (JSON-Payload)
- `/complete` – Abschlussseite nachdem alle Personas bearbeitet wurden
- `/restart` – setzt die Session-Reihenfolge zurück

**Frontend / Nutzung**
- Öffne die Startseite, bearbeite die Rangliste für die dargestellte Persona und sende ab. Die App verwaltet die Persona-Reihenfolge in der Session.

**Entwicklung & Hinweise**
- Die `SECRET_KEY` ist in `app.py` für Entwicklungszwecke gesetzt; vor Produktion ändern.
- `data/` wird beim Start initialisiert, falls nötig.
- Tests oder CI sind nicht enthalten; für lokale Entwicklung ist ein virtuelles Environment ausreichend.

**Kontakt / Weiteres**
- Bei Fragen oder Änderungswünschen gern Bescheid geben.
