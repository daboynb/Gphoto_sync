# Passo 12: Portare Post-Download EXIF (postdl.py)

## Obiettivo

Portare `src/postdl.sh` (33 righe) in Python. Aggiorna i metadati EXIF dei file scaricati con la data corretta usando `exiftool`.

## File sorgente: `src/postdl.sh`

## File da creare: `web-gui/sync_engine/postdl.py`

## Logica di postdl.sh

1. Riceve path del file come argomento `$1`
2. Skippa file `.avi` (exiftool non li supporta)
3. Esegue exiftool per aggiornare `DateTimeOriginal` dal `FileModifyDate`:
   ```bash
   exiftool "-datetimeoriginal<FileModifyDate" -P -overwrite_original_in_place \
     -if 'not $DateTimeOriginal or ($datetimeoriginal gt ${filemodifydate;ShiftTime("1 0")}) or ($filemodifydate gt ${datetimeoriginal;ShiftTime("1 0")})' \
     "$1"
   ```
4. Exit code 2 = nessuna modifica necessaria (ok)
5. Ignora errori "too large" o "invalid atom size"

## Codice completo da scrivere

```python
#!/usr/bin/env python3
"""Post-download EXIF date update.

Updates the EXIF DateTimeOriginal of downloaded files to match
the file modification date (which was set from Google Photos metadata).

Requires exiftool to be installed.

Equivalent of src/postdl.sh.

Usage:
    python postdl.py <file_path> [image_id]
"""

import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

# File extensions that exiftool can't handle
SKIP_EXTENSIONS = {".avi"}


def update_exif_date(file_path: str) -> None:
    """Update EXIF DateTimeOriginal from file modification date.

    Uses exiftool with the same logic as the original postdl.sh:
    - Only updates if no EXIF date exists, or dates differ by more than 1 hour
    - Skips .avi files
    - Ignores "too large" and "invalid atom size" errors
    """
    if not os.path.isfile(file_path):
        logger.warning("file not found: %s", file_path)
        return

    # Skip unsupported extensions
    _, ext = os.path.splitext(file_path)
    if ext.lower() in SKIP_EXTENSIONS:
        logger.debug("skipping EXIF update for %s (unsupported format)", os.path.basename(file_path))
        return

    # Run exiftool with same args as postdl.sh
    result = subprocess.run(
        [
            "exiftool",
            "-datetimeoriginal<FileModifyDate",
            "-P",
            "-overwrite_original_in_place",
            "-if",
            'not $DateTimeOriginal or '
            '($datetimeoriginal gt ${filemodifydate;ShiftTime("1 0")}) or '
            '($filemodifydate gt ${datetimeoriginal;ShiftTime("1 0")})',
            file_path,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 2:
        # Exit code 2 = no changes needed (file already has correct date)
        logger.debug("file already has correct EXIF date: %s", os.path.basename(file_path))
    elif result.returncode != 0:
        stderr = result.stderr.strip()
        # Ignore known non-critical errors
        if "too large" in stderr or "invalid atom size" in stderr:
            logger.debug(
                "skipping EXIF update for %s (unsupported format)",
                os.path.basename(file_path),
            )
        else:
            for line in stderr.splitlines():
                logger.error("exiftool: %s", line)
    else:
        logger.info(
            "updated EXIF date for %s to match Google Photos date",
            os.path.basename(file_path),
        )


def main():
    """CLI entry point for postdl.py (called by --run flag)."""
    if len(sys.argv) < 2:
        print("Usage: postdl.py <file_path> [image_id]", file=sys.stderr)
        sys.exit(1)

    # Setup basic logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-5s %(message)s',
        datefmt='%H:%M:%S',
    )

    file_path = sys.argv[1]

    # postdl.sh receives dir_path as $1, so process all files in directory
    if os.path.isdir(file_path):
        for entry in os.scandir(file_path):
            if entry.is_file():
                update_exif_date(entry.path)
    else:
        update_exif_date(file_path)


if __name__ == "__main__":
    main()
```

## Differenze rispetto allo script bash

| Bash (postdl.sh) | Python (postdl.py) |
|---|---|
| Riceve dir_path da DoRun | Riceve dir_path, processa tutti i file dentro |
| Usa exiftool direttamente | Usa exiftool via subprocess |
| Exit code 2 = ok | Exit code 2 = ok (stesso comportamento) |
| source /app/log.sh per logging | Python logging standard |

## Note

- `exiftool` deve essere installato nel container (gia' presente nel Dockerfile attuale)
- Il file va reso eseguibile nel container: `chmod +x /app/postdl.py`
- Oppure invocato come `python /app/postdl.py` dal flag `--run`

## Verifica

```bash
cd web-gui && python -c "
from sync_engine.postdl import update_exif_date, SKIP_EXTENSIONS

# Test skip extensions
assert '.avi' in SKIP_EXTENSIONS

# Test con file inesistente (non deve crashare)
update_exif_date('/nonexistent/file.jpg')

print('Postdl module tests passed!')
"
```
