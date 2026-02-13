# Passo 1: Creare Struttura Progetto e Dipendenze

## Obiettivo

Creare la struttura delle cartelle per il sync engine Python dentro `web-gui/sync_engine/` e aggiornare le dipendenze.

## Azioni

### 1.1 Creare la directory sync_engine con tutti i file vuoti

```bash
mkdir -p web-gui/sync_engine
```

Creare questi file (vuoti con solo docstring iniziale):

- `web-gui/sync_engine/__init__.py`
- `web-gui/sync_engine/main.py`
- `web-gui/sync_engine/models.py`
- `web-gui/sync_engine/config.py`
- `web-gui/sync_engine/session.py`
- `web-gui/sync_engine/navigation.py`
- `web-gui/sync_engine/download.py`
- `web-gui/sync_engine/sync.py`
- `web-gui/sync_engine/downloaded_ids.py`
- `web-gui/sync_engine/date_parser.py`
- `web-gui/sync_engine/file_utils.py`
- `web-gui/sync_engine/postdl.py`

### 1.2 Aggiornare web-gui/requirements.txt

Aggiungere a `web-gui/requirements.txt` (che attualmente contiene Flask, docker, croniter, python-dateutil, requests, urllib3, PyYAML):

```
playwright==1.49.0
```

NON rimuovere le dipendenze esistenti. Solo aggiungere.

### 1.3 Contenuto di __init__.py

```python
"""
Sync Engine - Python replacement for gphotos-cdp Go binary.

Uses Playwright to drive headless Chrome via CDP to download photos
from Google Photos.
"""

__version__ = "1.0.0"
```

## Verifica

- La cartella `web-gui/sync_engine/` esiste con tutti i file
- `web-gui/requirements.txt` contiene `playwright`
- `python -c "from sync_engine import __version__; print(__version__)"` funziona dalla cartella web-gui

## Note

- Playwright sara' installato nel Dockerfile con `playwright install chromium --with-deps`
- Per sviluppo locale: `pip install playwright && playwright install chromium`
