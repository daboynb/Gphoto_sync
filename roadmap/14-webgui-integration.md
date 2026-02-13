# Passo 14: Aggiornare Web GUI per Nuovo Engine

## Obiettivo

Aggiornare i punti di contatto tra il Web GUI e il sync engine per riflettere il passaggio da Go a Python.

## File da modificare

### 1. `web-gui/routes/profiles.py` — Generazione docker-compose

Il compose generato per ogni profilo monta `gphotos-cdp/months-config.json`. Dopo il rewrite, months-config.json resta nella stessa posizione sul filesystem ma la sorgente cambia.

#### Riga 145: volume mount months-config.json

PRIMA:
```python
      - {workspace_path}/gphotos-cdp/months-config.json:/app/months-config.json
```

Questo resta INVARIATO perche':
- Il file `months-config.json` viene ancora generato dal sync engine
- Viene letto e scritto dallo stesso path `/app/months-config.json` nel container
- Il file iniziale viene copiato dal Dockerfile da `gphotos-cdp/months-config.json`

NOTA: Quando il progetto Go viene rimosso (passo 15), il file sorgente non esistera' piu'. Bisogna spostare `months-config.json` fuori da `gphotos-cdp/`:

**Spostare il file:**
```bash
cp gphotos-cdp/months-config.json months-config.json
```

**Aggiornare il Dockerfile (gia' fatto nel passo 13):**
```dockerfile
COPY months-config.json /app/months-config.json
```

**Aggiornare profiles.py riga 145:**
```python
      - {workspace_path}/months-config.json:/app/months-config.json
```

### 2. `web-gui/routes/rebuild.py` — Rebuild dell'immagine

Il rebuild process ricostruisce l'immagine Docker. Non dovrebbe servire nessun cambiamento perche':
- Il Dockerfile viene letto dalla root del progetto
- Il build context include tutto il necessario
- L'immagine risultante ha lo stesso nome `gphotos-sync:latest`

Verificare che `docker build --no-cache -t gphotos-sync:latest .` funzioni con il nuovo Dockerfile.

### 3. `docker-compose.yml` — Compose principale della web-gui

PRIMA:
```yaml
volumes:
  - .:/workspace
```

Resta INVARIATO. La web-gui monta la root del progetto come `/workspace`, che include sia i profili che il months-config.json.

### 4. Compose generati per profili — Template in profiles.py

PRIMA (compose generato):
```yaml
volumes:
  - {workspace}/profiles/{profile}:/tmp/gphotos-cdp
  - {workspace}/gphotos-cdp/months-config.json:/app/months-config.json
  - {download_dir}:/download
```

DOPO:
```yaml
volumes:
  - {workspace}/profiles/{profile}:/tmp/gphotos-cdp
  - {workspace}/months-config.json:/app/months-config.json
  - {download_dir}:/download
```

Solo il path di months-config.json cambia.

## Codice da modificare in `web-gui/routes/profiles.py`

### Funzione `create_compose()` — riga 137-155

Trovare la riga:
```python
      - {workspace_path}/gphotos-cdp/months-config.json:/app/months-config.json
```

Sostituire con:
```python
      - {workspace_path}/months-config.json:/app/months-config.json
```

## Spostamento di months-config.json

```bash
# Copiare il file dalla cartella Go alla root
cp gphotos-cdp/months-config.json ./months-config.json
```

NOTA: Non eliminare `gphotos-cdp/months-config.json` fino a quando il progetto Go non viene completamente rimosso.

## Test di regressione

Dopo queste modifiche, verificare che:

1. La web-gui si avvia correttamente:
```bash
docker compose up -d
# Aprire http://localhost:8080
```

2. Creare un profilo genera il compose corretto:
```bash
# Tramite UI, creare un profilo di test
# Verificare che docker-compose.{profile}.yml contenga il path corretto per months-config.json
cat /workspace/docker-compose.test-profile.yml | grep months-config
# Deve mostrare: - {path}/months-config.json:/app/months-config.json
```

3. Avviare un profilo funziona:
```bash
# Tramite UI, avviare il profilo
# Verificare nei log che il sync engine Python si avvia
docker logs gphotos-sync-test-profile 2>&1 | head -20
```

## Checklist modifiche

- [ ] Spostare `gphotos-cdp/months-config.json` → `./months-config.json` (root progetto)
- [ ] Aggiornare `web-gui/routes/profiles.py`: path volume months-config.json
- [ ] Aggiornare `Dockerfile`: COPY path months-config.json
- [ ] Aggiornare `src/sync.sh`: `gphotos-cdp` → `python -m sync_engine`
- [ ] Aggiornare `src/sync.sh`: flag syntax (`-flag` → `--flag`)
- [ ] Aggiornare `src/sync.sh`: `postdl.sh` → `postdl.py`
- [ ] Verificare che `docker build` funziona
- [ ] Verificare che la web-gui genera compose corretti
- [ ] Verificare che i container sync si avviano con il nuovo engine
