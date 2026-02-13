# Passo 13: Riscrivere Dockerfile Unificato

## Obiettivo

Riscrivere il Dockerfile principale per eliminare la build Go e usare Python + Playwright come sync engine. Il container deve includere: Python, Playwright con Chromium, exiftool, cron.

## File da modificare: `Dockerfile` (root del progetto)

## Dockerfile attuale (da sostituire)

```dockerfile
FROM golang:1.25-bookworm AS build          # <-- ELIMINARE
# ... build Go binary ...                    # <-- ELIMINARE

FROM debian:bookworm-slim
# ... installa Chrome, exiftool, cron ...
COPY --from=build /go/bin/gphotos-cdp /usr/bin/    # <-- ELIMINARE
COPY src ./app/
ENTRYPOINT ["/app/start.sh"]
```

## Nuovo Dockerfile

```dockerfile
FROM python:3.11-slim-bookworm

ARG BUILD_DATE="unknown"
ARG IMAGE_VERSION="dev"

ENV \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    CRON_SCHEDULE="0 0 * * *" \
    RESTART_SCHEDULE= \
    DEBIAN_FRONTEND=noninteractive \
    LOGLEVEL=INFO \
    HEALTHCHECK_HOST="https://hc-ping.com" \
    HEALTHCHECK_ID= \
    ALBUMS= \
    WORKER_COUNT=6 \
    RUN_ON_STARTUP=false \
    BUILD_DATE=${BUILD_DATE} \
    IMAGE_VERSION=${IMAGE_VERSION} \
    # Playwright env
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

# Install system dependencies
RUN apt-get update && apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        cron \
        exiftool \
        jq \
        wget \
        sudo \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY web-gui/sync_engine/requirements-sync.txt /tmp/requirements-sync.txt
RUN pip install --no-cache-dir -r /tmp/requirements-sync.txt && \
    rm /tmp/requirements-sync.txt

# Install Playwright and Chromium
RUN playwright install chromium --with-deps

# Copy sync engine
COPY web-gui/sync_engine /app/sync_engine/

# Copy months-config.json (initial language config)
COPY gphotos-cdp/months-config.json /app/months-config.json

# Copy shell scripts that are still needed
COPY src/start.sh /app/start.sh
COPY src/log.sh /app/log.sh
RUN chmod +x /app/start.sh /app/log.sh

# Make postdl.py executable as script
RUN chmod +x /app/sync_engine/postdl.py

USER root
ENTRYPOINT ["/app/start.sh"]
CMD [""]
```

## File aggiuntivo da creare: `web-gui/sync_engine/requirements-sync.txt`

```
playwright==1.49.0
```

Questo file contiene solo le dipendenze del sync engine (usato dal Dockerfile del sync container). Il `requirements.txt` della web-gui e' separato.

## Modifiche a `src/start.sh`

Il file `start.sh` e' ancora necessario per:
- Creazione utente non-root (`abc` con PUID/PGID)
- Setup permessi directory
- Rilevamento cambio config album
- Setup cron

MA deve essere aggiornato per invocare Python invece del binario Go:

### Riga da cambiare in start.sh (riga 82)

PRIMA:
```bash
sudo -E -u abc sh /app/sync.sh
```

DOPO:
```bash
sudo -E -u abc sh /app/sync.sh
```

(sync.sh viene aggiornato nel passo 14)

### Riga da cambiare nel cron setup (riga 110)

PRIMA:
```bash
CRON="$CRON\n$CRON_SCHEDULE /usr/bin/flock -n /app/sync.lock bash /app/sync.sh > $LOGFIFO 2>&1"
```

Resta invariata — sync.sh gestisce l'invocazione.

## Modifiche a `src/sync.sh`

### Linea comando gphotos-cdp da sostituire

PRIMA (riga 17):
```bash
GPHOTOS_CDP_ARGS="-profile \"$PROFILE_DIR\" -headless -json -loglevel $LOGLEVEL -removed -workers $WORKER_COUNT $GPHOTOS_CDP_ARGS -run /app/postdl.sh"
```

DOPO:
```bash
GPHOTOS_CDP_ARGS="--profile \"$PROFILE_DIR\" --headless --json --loglevel $LOGLEVEL --removed --workers $WORKER_COUNT --run /app/sync_engine/postdl.py"
```

PRIMA (riga 72 e 75):
```bash
eval gphotos-cdp -dldir "$ALBUM_DL_DIR" $GPHOTOS_CDP_ARGS
eval gphotos-cdp -dldir "$ALBUM_DL_DIR" $GPHOTOS_CDP_ARGS -album "$ALBUM_ID"
```

DOPO:
```bash
eval python -m sync_engine --dldir "$ALBUM_DL_DIR" $GPHOTOS_CDP_ARGS
eval python -m sync_engine --dldir "$ALBUM_DL_DIR" $GPHOTOS_CDP_ARGS --album "$ALBUM_ID"
```

### Rimuovere la parte Chrome preferences (righe 27-32)

Le preferenze Chrome per forzare la lingua inglese erano necessarie per il binario Go. Con Playwright, passiamo la lingua come argomento nel launch. Questa sezione puo' essere rimossa o mantenuta per sicurezza.

## Struttura risultante nel container

```
/app/
├── start.sh                 # Entrypoint (init, cron, user creation)
├── log.sh                   # Logging utility bash
├── sync.sh                  # Orchestrator (album parsing, invoca Python)
├── months-config.json       # Config lingua iniziale
└── sync_engine/             # NUOVO: Python sync engine
    ├── __init__.py
    ├── __main__.py
    ├── main.py
    ├── config.py
    ├── models.py
    ├── session.py
    ├── navigation.py
    ├── download.py
    ├── sync.py
    ├── downloaded_ids.py
    ├── date_parser.py
    ├── file_utils.py
    └── postdl.py
```

## Note importanti

### Playwright vs Chrome standalone

Il Dockerfile attuale scarica Google Chrome come .deb. Con Playwright, usiamo `playwright install chromium --with-deps` che scarica Chromium + tutte le dipendenze automaticamente. Questo:
- E' piu' pulito (gestito da Playwright)
- Garantisce compatibilita' versione browser/driver
- Potrebbe essere leggermente diverso da Chrome (Chromium vs Chrome)

ATTENZIONE: Nella sezione README si dice che Chromium non funziona bene per auth Google Photos su ARM64. Su AMD64 dovrebbe funzionare, ma se ci sono problemi di auth, potrebbe essere necessario tornare a Chrome standalone e usare Playwright con `channel="chrome"`.

### Fallback: usare Chrome invece di Chromium

Se Chromium da problemi con Google auth, modificare il Dockerfile:

```dockerfile
# Invece di playwright install chromium, installa Chrome
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt install -y ./google-chrome-stable_current_amd64.deb && \
    rm google-chrome-stable_current_amd64.deb
```

E in session.py, usare:
```python
context = await pw.chromium.launch_persistent_context(
    channel="chrome",  # Usa Chrome installato nel sistema
    ...
)
```

## Verifica

```bash
# Build dell'immagine (dal root del progetto)
docker build -t gphotos-sync:latest .

# Verifica che Python e Playwright funzionino
docker run --rm gphotos-sync:latest python -c "
from playwright.sync_api import sync_playwright
print('Playwright imported successfully')
"

# Verifica che exiftool sia presente
docker run --rm gphotos-sync:latest exiftool -ver

# Verifica che il sync engine sia importabile
docker run --rm gphotos-sync:latest python -c "
import sys
sys.path.insert(0, '/app')
from sync_engine.models import GPHOTOS_URL
print(f'Sync engine loaded, GPHOTOS_URL={GPHOTOS_URL}')
"
```
