# Passo 11: Creare CLI Entry Point (main.py)

## Obiettivo

Creare l'entry point Python che sostituisce sia `gphotos-cdp/main.go` che `src/sync.sh`. Deve accettare gli stessi flag del binario Go per essere compatibile con gli script esistenti.

## File da creare: `web-gui/sync_engine/main.py`

## Flusso di esecuzione (da main.go:54-173)

1. Parsing argomenti (equivalente dei flag Go)
2. Setup logging
3. Create session (directory, ID manager)
4. Launch browser (Chrome via Playwright)
5. Login / verifica autenticazione
6. Detect locale (lingua della pagina)
7. Load months config
8. Check language (auto-extract se necessario)
9. First navigation (verifica caricamento pagina)
10. Start sync (Resync loop + workers)
11. Check removed files (opzionale)
12. Shutdown

## Flag da supportare (mappatura da Go)

| Go flag | Python arg | Default | Descrizione |
|---|---|---|---|
| `-dldir` | `--dldir` | `$HOME/Downloads/gphotos-cdp` | Directory download |
| `-profile` | `--profile` | (temp dir) | Chrome profile directory |
| `-headless` | `--headless` | `False` | Modalita' headless |
| `-loglevel` | `--loglevel` | `info` | Livello log |
| `-workers` | `--workers` | `1` | Worker concorrenti (1-20) |
| `-album` | `--album` | `""` | Album ID da sincronizzare |
| `-removed` | `--removed` | `False` | Traccia file eliminati |
| `-run` | `--run` | `""` | Comando post-download |
| `-json` | `--json` | `False` | Output log JSON |

## Codice completo da scrivere

```python
#!/usr/bin/env python3
"""
Sync engine CLI entry point.

Downloads photos from Google Photos using Playwright/Chrome.
Replaces both the Go binary (gphotos-cdp) and shell orchestration (sync.sh).

Usage:
    python -m sync_engine.main --profile /tmp/profile --dldir /download --headless --workers 6

Equivalent of Go main.go + src/sync.sh combined.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time

from . import config
from .session import (
    create_session,
    launch_browser,
    login,
    get_locale,
    check_language,
    clean_download_dir,
    shutdown,
)
from .navigation import first_nav
from .sync import resync, check_for_removed_files

logger = logging.getLogger("sync_engine")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments (same flags as Go binary)."""
    parser = argparse.ArgumentParser(
        description="Google Photos sync engine using Chrome DevTools Protocol"
    )
    parser.add_argument(
        "--dldir", default="",
        help="Download directory (default: $HOME/Downloads/gphotos-cdp)"
    )
    parser.add_argument(
        "--profile", default="",
        help="Chrome profile directory for session persistence"
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run Chrome in headless mode (requires --profile with saved auth)"
    )
    parser.add_argument(
        "--loglevel", default="info",
        choices=["debug", "info", "warn", "warning", "error", "fatal"],
        help="Log level (default: info)"
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Number of concurrent download workers, 1-20 (default: 1)"
    )
    parser.add_argument(
        "--album", default="",
        help="Album ID to sync (syncs entire library if not specified)"
    )
    parser.add_argument(
        "--removed", action="store_true",
        help="Track photos deleted from Google Photos"
    )
    parser.add_argument(
        "--run", default="",
        help="Command to run on each downloaded file (receives dir_path and image_id as args)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output logs in JSON format"
    )
    return parser.parse_args()


def setup_logging(level_str: str, json_format: bool = False) -> None:
    """Configure logging to match Go's zerolog output."""
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "fatal": logging.CRITICAL,
    }
    level = level_map.get(level_str.lower(), logging.INFO)

    if json_format:
        # JSON format matching Go's zerolog output
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                return json.dumps({
                    "level": record.levelname.lower(),
                    "message": record.getMessage(),
                    "dt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(record.created)),
                })
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", datefmt="%H:%M:%S")
        )

    logging.root.handlers = [handler]
    logging.root.setLevel(level)

    # Suppress noisy Playwright logs
    logging.getLogger("playwright").setLevel(logging.WARNING)


async def main() -> int:
    """Main async entry point."""
    args = parse_args()
    setup_logging(args.loglevel, args.json)

    # Validate args
    if not args.profile and args.headless:
        logger.fatal("--headless only allowed if --profile is set")
        return 1

    workers = max(1, min(20, args.workers))

    # --- Session Setup ---
    logger.info("========================================")
    logger.info("SESSION SETUP")
    logger.info("========================================")

    session = await create_session(
        download_dir=args.dldir,
        profile_dir=args.profile,
        album_id=args.album,
    )
    logger.info("session dir: %s", session.profile_dir)

    clean_download_dir(session)

    # --- Launch Browser ---
    pw, context, page = await launch_browser(session, headless=args.headless)

    try:
        # --- Authentication ---
        logger.info("")
        logger.info("========================================")
        logger.info("AUTHENTICATION")
        logger.info("========================================")
        await login(session, page, headless=args.headless)

        # --- Language Detection ---
        logger.info("")
        logger.info("========================================")
        logger.info("LANGUAGE DETECTION")
        logger.info("========================================")
        locale = await get_locale(page)

        config.load_months_config()
        await check_language(page)

        # --- First Navigation ---
        logger.info("")
        logger.info("========================================")
        logger.info("FIRST NAVIGATION")
        logger.info("========================================")
        await first_nav(session, page)

        await check_language(page)
        logger.info("first navigation completed")

        # --- Sync ---
        logger.info("")
        logger.info("========================================")
        logger.info("STARTING SYNC")
        logger.info("========================================")
        await resync(session, page, workers, args.album, args.run)

        # --- Check Removed ---
        await check_for_removed_files(session, page, args.removed)

        logger.info("")
        logger.info("========================================")
        logger.info("SYNC COMPLETED")
        logger.info("========================================")
        return 0

    except Exception as e:
        logger.fatal("sync failed: %s", e, exc_info=True)
        return 1
    finally:
        await shutdown(session, pw)


def run():
    """Synchronous entry point for CLI."""
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    run()
```

## Aggiungere anche `__main__.py`

Creare `web-gui/sync_engine/__main__.py` per permettere `python -m sync_engine`:

```python
"""Allow running sync engine as: python -m sync_engine"""
from .main import run
run()
```

## Come viene invocato

### Prima (Go + shell scripts):

```bash
# sync.sh (riga 72-76)
gphotos-cdp -dldir "$ALBUM_DL_DIR" -profile "$PROFILE_DIR" \
  -headless -json -loglevel $LOGLEVEL -removed -workers $WORKER_COUNT \
  -album "$ALBUM_ID" -run /app/postdl.sh
```

### Dopo (Python):

```bash
python -m sync_engine --dldir "$ALBUM_DL_DIR" --profile "$PROFILE_DIR" \
  --headless --json --loglevel $LOGLEVEL --removed --workers $WORKER_COUNT \
  --album "$ALBUM_ID" --run /app/postdl.py
```

NOTA: la sintassi degli argomenti cambia da `-flag value` (Go) a `--flag value` (Python argparse). Questo richiede un aggiornamento di sync.sh nel passo 14.

## Verifica

```bash
cd web-gui && python -c "
from sync_engine.main import parse_args, setup_logging
import sys

# Test argument parsing (mock sys.argv)
sys.argv = ['test', '--profile', '/tmp/test', '--headless', '--workers', '6', '--loglevel', 'debug']
args = parse_args()
assert args.profile == '/tmp/test'
assert args.headless == True
assert args.workers == 6
assert args.loglevel == 'debug'

# Test logging setup
setup_logging('info', json_format=False)
setup_logging('debug', json_format=True)

print('Main entrypoint tests passed!')
"
```
