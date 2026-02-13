# Roadmap: Rewrite Go Sync Engine in Python

## Obiettivo

Eliminare il codice Go (`gphotos-cdp/`) e gli shell scripts intermediari (`src/sync.sh`, `src/start.sh`), riscrivendo il sync engine interamente in Python con Playwright. Il risultato finale e' una codebase omogenea Python che include sia il web GUI che il sync engine.

## Architettura Target

```
web-gui/
├── app.py                          # Flask (invariato)
├── routes/                         # API routes (invariato)
├── sync_engine/                    # NUOVO: sostituto di gphotos-cdp/ + src/
│   ├── __init__.py
│   ├── main.py                     # Entry point CLI (sostituto di main.go)
│   ├── config.py                   # Months config I/O (sostituto di config/config.go)
│   ├── models.py                   # Dataclass: Session, Job, PhotoData, etc.
│   ├── session.py                  # Chrome setup + auth (sostituto di session/session.go)
│   ├── navigation.py               # Scrolling, photo nav (sostituto di navigation/navigation.go)
│   ├── download.py                 # Download + process (sostituto di download/download.go)
│   ├── sync.py                     # Resync loop + workers (sostituto di sync/sync.go)
│   ├── downloaded_ids.py           # ID tracking (sostituto di utils/downloaded_ids.go)
│   ├── date_parser.py              # Date parsing (sostituto di utils/date.go)
│   ├── file_utils.py               # File ops (sostituto di utils/file.go + string.go)
│   └── postdl.py                   # Post-download EXIF (sostituto di src/postdl.sh)
├── Dockerfile                      # Aggiornato: aggiunge Chrome + exiftool
├── requirements.txt                # Aggiunto: playwright
└── ...
```

## Cosa viene eliminato

- `gphotos-cdp/` (intero progetto Go)
- `src/sync.sh` (orchestrazione shell)
- `src/start.sh` (init container - sostituito da Python entrypoint)
- `src/postdl.sh` (EXIF update - sostituito da postdl.py)
- `src/log.sh` (logging bash - non piu' necessario)
- Build stage Go nel Dockerfile principale

## Ordine di esecuzione dei passi

I file sono numerati nell'ordine in cui devono essere eseguiti:

1. `01-project-structure.md` - Creare struttura cartelle e dipendenze
2. `02-models.md` - Definire i dataclass Python (equivalenti dei Go types)
3. `03-config.md` - Portare gestione months-config.json
4. `04-downloaded-ids.md` - Portare il manager degli ID scaricati
5. `05-date-parser.md` - Portare il parsing delle date multi-lingua
6. `06-file-utils.md` - Portare le utility file e string
7. `07-session.md` - Portare la gestione sessione Chrome con Playwright
8. `08-navigation.md` - Portare la navigazione pagina e scrolling
9. `09-download.md` - Portare il download engine (Shift+D, wait, process)
10. `10-sync.md` - Portare il loop Resync con worker pool
11. `11-main-entrypoint.md` - Creare CLI entry point Python
12. `12-postdl.md` - Portare post-download EXIF in Python
13. `13-dockerfile.md` - Riscrivere Dockerfile unificato
14. `14-webgui-integration.md` - Aggiornare Web GUI per usare nuovo engine
15. `15-testing.md` - Aggiungere test per i moduli core

## Dipendenze Python da aggiungere

```
playwright==1.49.0        # Sostituto di chromedp
```

## Note importanti

- Ogni passo e' autocontenuto e puo' essere verificato indipendentemente
- I passi 2-6 sono utility pure senza dipendenze esterne (testabili subito)
- I passi 7-10 dipendono da Playwright e richiedono Chrome installato
- Il passo 13 (Dockerfile) e' critico: deve installare Chrome + Playwright + exiftool
- Il passo 14 tocca file esistenti del web-gui, fare attenzione a non rompere nulla
