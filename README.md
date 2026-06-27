# Evaluation App

Eine kleine Flask-Anwendung zum Durchführen von Persona-basierten Event-Rankings.

Kurz: Die App zeigt nacheinander Personas an, lässt Benutzer 10 Events pro Persona in eine Rangfolge bringen und speichert die Submissions in einer Datenbank.

**Schnellstart (lokal)**

1. Repository klonen und Verzeichnis wechseln:

```bash
git clone <repo-url>
cd evaluation-app
```

2. Virtuelle Umgebung erstellen und aktivieren

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Windows (CMD):

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Abhängigkeiten installieren:

```bash
pip install -r requirements.txt
```

4. Beispiel `.env` (optional)

Lege eine Datei `.env` im Projektordner an oder setze die Umgebungsvariablen direkt. Minimale Variablen:

```
SECRET_KEY=change-me
PORT=8080
DATABASE_URL=mysql+pymysql://USER:PASSWORT@HOST:3306/DATENBANK
```

5. Anwendung starten:

```bash
python app.py
```

Standardmäßig hört die App auf `0.0.0.0:8080`. Mit `PORT` in der `.env` oder als Umgebungsvariable lässt sich der Port überschreiben.

**Projektstruktur (Kurzüberblick)**
- `app.py` – Haupt-Flask-Anwendung und Routen
- `requirements.txt` – Python-Abhängigkeiten
- `data/` – JSON-Dateien und Exporte (`personas.json`, `persona_rankings/`)
- `static/` – CSS/JS-Dateien
- `templates/` – Jinja2-Templates (`start.html`, `index.html`, `complete.html`)

**Wichtige Hinweise**
- Personas: `data/personas.json` enthält die Persona-Definitionen.
- Submissions: Jede abgeschickte Rangliste wird in der Datenbank gespeichert; Felder enthalten u. a. `participant_label`, `session_uuid`, `persona_id` und die geordnete Eventliste.
- Datenbank: Die App erwartet eine relationale DB (MySQL-kompatibel) über `DATABASE_URL`.
- Sicherheit: Setze `SECRET_KEY` in Produktion auf ein starkes, zufälliges Geheimnis.

**Deployment**

Docker (Build & Run):

```bash
docker build -t evaluation-app:latest .
docker run --rm -p 8080:8080 \
	-e SECRET_KEY=change-me \
	-e DATABASE_URL=mysql+pymysql://USER:PASSWORT@HOST:3306/DATENBANK \
	evaluation-app:latest
```

Gunicorn (Beispiel für Produktion):

```bash
gunicorn app:app --bind 0.0.0.0:${PORT:-8080}
```

Für Plattformen wie Wasmer/Wasix oder Container-Runtimes gilt: `DATABASE_URL` ist die zentrale Konfigurationsvariable.

**Routen (Auswahl)**
- `/` – Start/Weiterleitung
- `/start` – Teilnehmername setzen
- `/persona/<persona_id>` – Persona + Events anzeigen
- `/persona/<persona_id>/complete` – POST: Rangliste speichern
- `/complete` – Abschlussseite
