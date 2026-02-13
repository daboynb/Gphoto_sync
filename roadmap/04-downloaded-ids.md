# Passo 4: Portare Downloaded IDs Manager (downloaded_ids.py)

## Obiettivo

Portare `gphotos-cdp/internal/utils/downloaded_ids.go` in Python. Gestisce il file `.downloaded_ids.txt` che traccia quali foto sono gia' state scaricate per evitare duplicati.

## File sorgente Go: `gphotos-cdp/internal/utils/downloaded_ids.go` (114 righe)

## File da creare: `web-gui/sync_engine/downloaded_ids.py`

## Logica da portare

### Struttura dati (Go)

```go
type DownloadedIdsManager struct {
    filePath string
    ids      map[string]struct{}
    mu       sync.RWMutex
}
```

In Python: siccome usiamo asyncio (single-thread), non serve RWMutex. Un semplice `set` + file append basta. Se in futuro si usano thread, aggiungere `threading.Lock`.

### NewDownloadedIdsManager (righe 21-37)

1. Calcola path: `{download_dir}/.downloaded_ids.txt`
2. Inizializza set vuoto
3. Carica IDs esistenti dal file (se esiste)
4. Se il file non esiste, non e' un errore

### load (righe 40-59)

1. Apri file in lettura
2. Leggi riga per riga
3. Aggiungi ogni riga non-vuota al set

### Has (righe 62-67)

Check se un ID e' nel set.

### Add (righe 70-94)

1. Se gia' presente, ritorna (no-op)
2. Aggiungi al set in memoria
3. Apri file in append mode
4. Scrivi `id + "\n"`

### GetAll (righe 97-106)

Ritorna lista di tutti gli ID.

### Count (righe 109-113)

Ritorna len del set.

## Codice completo da scrivere

```python
"""Manager for tracking downloaded photo IDs.

Maintains an in-memory set backed by a file (.downloaded_ids.txt) in the
download directory. Each line in the file is one photo ID.

Equivalent of Go utils.DownloadedIdsManager.
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

DOWNLOADED_IDS_FILE = ".downloaded_ids.txt"


class DownloadedIdsManager:
    """Thread-safe manager for downloaded image IDs.

    Keeps an in-memory set for fast lookups and appends to a file
    for persistence across restarts.
    """

    def __init__(self, download_dir: str):
        self._file_path = os.path.join(download_dir, DOWNLOADED_IDS_FILE)
        self._ids: set[str] = set()
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        """Load existing IDs from file."""
        if not os.path.exists(self._file_path):
            return

        try:
            with open(self._file_path, "r") as f:
                for line in f:
                    id_ = line.strip()
                    if id_:
                        self._ids.add(id_)
        except OSError as e:
            logger.warning("Error loading downloaded IDs from %s: %s", self._file_path, e)

    def has(self, id_: str) -> bool:
        """Check if an ID has been downloaded."""
        with self._lock:
            return id_ in self._ids

    def add(self, id_: str) -> None:
        """Mark an ID as downloaded and persist to file.

        No-op if already present.
        """
        with self._lock:
            if id_ in self._ids:
                return
            self._ids.add(id_)

        # Append to file (outside lock to minimize lock time)
        try:
            with open(self._file_path, "a") as f:
                f.write(id_ + "\n")
        except OSError as e:
            logger.warning("Error writing downloaded ID %s to file: %s", id_, e)

    def get_all(self) -> list[str]:
        """Return all downloaded IDs."""
        with self._lock:
            return list(self._ids)

    def count(self) -> int:
        """Return the number of downloaded IDs."""
        with self._lock:
            return len(self._ids)
```

## Formato file .downloaded_ids.txt

```
AF1QipN3abc123...
AF1QipN3def456...
AF1QipN3ghi789...
```

Un ID per riga. Gli ID sono stringhe alfanumeriche generate da Google Photos, tipicamente iniziano con `AF1QipN`.

## Verifica

```bash
cd web-gui && python -c "
import tempfile, os
from sync_engine.downloaded_ids import DownloadedIdsManager

# Test con directory vuota
tmpdir = tempfile.mkdtemp()
mgr = DownloadedIdsManager(tmpdir)
assert mgr.count() == 0
assert not mgr.has('test123')

# Test add
mgr.add('test123')
assert mgr.has('test123')
assert mgr.count() == 1

# Test idempotenza
mgr.add('test123')
assert mgr.count() == 1

# Test add multipli
mgr.add('test456')
assert mgr.count() == 2

# Test get_all
all_ids = mgr.get_all()
assert 'test123' in all_ids
assert 'test456' in all_ids

# Test persistenza (ricarica da file)
mgr2 = DownloadedIdsManager(tmpdir)
assert mgr2.count() == 2
assert mgr2.has('test123')
assert mgr2.has('test456')

# Cleanup
os.unlink(os.path.join(tmpdir, '.downloaded_ids.txt'))
os.rmdir(tmpdir)
print('All downloaded_ids tests passed!')
"
```
