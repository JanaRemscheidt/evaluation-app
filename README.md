# Evaluation App

Eine kleine Flask-Anwendung zum Durchführen von Persona-basierten Event-Rankings.

**Kurzbeschreibung**
- Zeigt nacheinander Personas an und präsentiert zu jeder Persona 10 Events.
- Speichert die abgeschickten Ranglisten in der externen Wasmer-MySQL-Datenbank.

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

Die App läuft standardmäßig auf `http://0.0.0.0:8080` und benötigt `DATABASE_URL` für die externe Wasmer-MySQL-Datenbank. `HOST`, `PORT` und `SECRET_KEY` bleiben optional.

**Deployment (Wasmer / Wasix)**

Das Projekt ist bereits mit einer Wasmer-Konfiguration vorbereitet. Die zentrale Flask-App wird als `app:app` exportiert, und Wasmer kann sie direkt starten.

Die vorhandene Datei `wasmer.toml` enthält bereits die nötigen Start-Befehle.

Wenn du die Werte manuell setzen willst, verwende:

- Install-Command: `pip install -r requirements.txt`
- Start-Command: `gunicorn app:app --bind 0.0.0.0:${PORT:-8080}`

Für Wasmer musst du `DATABASE_URL` auf eine MySQL-Verbindung setzen, zum Beispiel `mysql+pymysql://USER:PASSWORT@HOST:3306/DATENBANK`. Ein lokaler Fallback ist nicht mehr vorgesehen.

Wichtig: das WSGI-Target muss auf `app:app` zeigen, da die Flask-Instanz in `app.py` als `app` definiert ist.

**Deployment mit Docker**

Für Container-Deployments ist die App bereits vorbereitet. Sie liest die Konfiguration über Umgebungsvariablen und nutzt ausschließlich die externe Datenbank über `DATABASE_URL`.

Build:

```bash
docker build -t evaluation-app:latest .
```

Run:

```bash
docker run --rm -p 8080:8080 \
	-e SECRET_KEY=change-me \
	-e DATABASE_URL=mysql+pymysql://USER:PASSWORT@HOST:3306/DATENBANK \
	evaluation-app:latest
```

Compose:

```bash
docker compose up --build
```

Für ein echtes Deployment ist die robuste Variante eine externe Datenbank. Dann setzt du nur `DATABASE_URL` auf den Ziel-String der Plattform oder des DB-Providers und lässt den Container unverändert.

Ein typischer Registry-Flow sieht so aus:

```bash
docker build -t <registry>/<image>:<tag> .
docker push <registry>/<image>:<tag>
```

Auf der Zielplattform startest du denselben Image-Tag mit den Env-Variablen `SECRET_KEY`, `PORT` und `DATABASE_URL`.

**Projektstruktur (Kurzüberblick)**
- `app.py` – Haupt-Flask-Anwendung und Routen
- `requirements.txt` – Python-Abhängigkeiten
- `data/` – enthaltene JSON-Dateien und Persona-Ranking-Exports (`personas.json`, `persona_rankings/`)
- `static/` – CSS/JS Dateien
- `templates/` – Jinja2-Templates (`index.html`, `complete.html`)

**Daten & Speicher**
- Personas werden aus `data/personas.json` geladen.
- Vorab vorhandene persona-Rankings liegen in `data/persona_rankings/events_persona_XX.json`.
- Benutzer-Rankings werden über SQLAlchemy direkt in der externen Wasmer-MySQL-Datenbank gespeichert.
- Für Docker-Deployments ist `DATABASE_URL` ebenfalls der zentrale Hebel; ein lokales Volume wird nicht mehr verwendet.

**Wichtige Routen**
- `/` – Einstieg; leitet zur nächsten offenen Persona weiter
- `/persona/<persona_id>` – Seite zur Präsentation einer Persona und ihrer Events
- `/persona/<persona_id>/complete` – POST-Endpoint zum Speichern einer Rangliste (JSON-Payload)
- `/complete` – Abschlussseite nachdem alle Personas bearbeitet wurden
- `/restart` – setzt die Session-Reihenfolge zurück

**Frontend / Nutzung**
- Öffne die Startseite, bearbeite die Rangliste für die dargestellte Persona und sende ab. Die App verwaltet die Persona-Reihenfolge in der Session.

**Entwicklung & Hinweise**
- Die `SECRET_KEY` sollte in Produktion über die Umgebungsvariable `SECRET_KEY` gesetzt werden.
- `data/` wird beim Start initialisiert, falls nötig.
- Tests oder CI sind nicht enthalten; für lokale Entwicklung ist ein virtuelles Environment ausreichend.

**Kontakt / Weiteres**
- Bei Fragen oder Änderungswünschen gern Bescheid geben.
