# Passo 6: Portare File e String Utils (file_utils.py)

## Obiettivo

Portare `gphotos-cdp/internal/utils/file.go` e `gphotos-cdp/internal/utils/string.go` in Python.

## File sorgente Go

- `gphotos-cdp/internal/utils/file.go` (60 righe)
- `gphotos-cdp/internal/utils/string.go` (67 righe)

## File da creare: `web-gui/sync_engine/file_utils.py`

## Funzioni da portare

### DoFileDateUpdate (file.go:14-21)

Logica: per ogni file nella lista, aggiorna il modification time.

Python: `os.utime(path, (date.timestamp(), date.timestamp()))`

### DoRun (file.go:24-36)

Logica: esegue un comando esterno su un file scaricato.
- `cmd = exec.Command(runCmd, dirPath, imageId)`
- In Python: `subprocess.run([run_cmd, dir_path, image_id])`

NOTA: nel nuovo design, `-run` chiamera' `postdl.py` invece di `postdl.sh`. Pero' manteniamo DoRun generico per compatibilita'.

### DirHasFiles (file.go:39-59)

Logica: controlla se una directory contiene file non-vuoti.

### CompareMangled (string.go:17-66)

Logica: confronta due nomi file dove uno potrebbe essere stato "mangled" da Google Photos (underscores, encoding URL, estensioni diverse).

Questa funzione e' usata in ProcessDownload per verificare che il file scaricato corrisponda al filename atteso. E' una comparazione fuzzy.

## Codice completo da scrivere

```python
"""File operations and string utilities.

Equivalent of Go utils/file.go and utils/string.go.
"""

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

logger = logging.getLogger(__name__)


def set_file_date(filepath: str, date: datetime) -> None:
    """Update the modification time of a file.

    Equivalent of Go utils.SetFileDate().
    """
    logger.debug("updating date of %s to %s", filepath, date)
    ts = date.timestamp()
    os.utime(filepath, (ts, ts))


def do_file_date_update(date: datetime, file_paths: list[str]) -> None:
    """Update the modification time of multiple files.

    Equivalent of Go utils.DoFileDateUpdate().
    """
    for path in file_paths:
        set_file_date(path, date)


def do_run(file_path: str, image_id: str, run_cmd: str) -> None:
    """Execute a command on a downloaded file.

    The command receives the directory path as arg1 and the image ID as arg2.

    Equivalent of Go utils.DoRun().
    """
    if not run_cmd:
        return

    dir_path = os.path.dirname(file_path)
    logger.info('running %r on %s', run_cmd, dir_path)
    result = subprocess.run(
        [run_cmd, dir_path, image_id],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Run command {run_cmd} {dir_path} {image_id} failed: "
            f"exit code {result.returncode}, stderr: {result.stderr}"
        )


def dir_has_files(download_dir: str, image_id: str) -> bool:
    """Check if a directory contains any non-empty files.

    Equivalent of Go utils.DirHasFiles().
    """
    target_dir = os.path.join(download_dir, image_id)
    if not os.path.isdir(target_dir):
        return False

    for entry in os.scandir(target_dir):
        if entry.is_file() and entry.stat().st_size > 0:
            return True
    return False


def compare_mangled(s1: str, s2: str) -> bool:
    """Compare two filenames where one may have been mangled by Google Photos.

    Google Photos sometimes:
    - Replaces characters with underscores
    - URL-encodes filenames
    - Changes file extensions (jpg, gif)

    Returns True if the filenames are likely the same file.
    Some false positives are acceptable.

    Equivalent of Go utils.CompareMangled().
    """
    def _compare(a: str, b: str) -> bool:
        # Find extension start positions
        ext_a = a.rfind(".")
        if ext_a == -1:
            ext_a = len(a)
        else:
            ext_a += 1  # include the dot

        ext_b = b.rfind(".")
        if ext_b == -1:
            ext_b = len(b)
        else:
            ext_b += 1

        # Skip leading dots in a
        i_a = 0
        while i_a < len(a) and a[i_a] == "." and (i_a >= len(b) or b[i_a] != "."):
            i_a += 1

        # Compare character by character
        for i_b in range(ext_b):
            if i_a >= len(a):
                return i_b == ext_b - 1 and b[i_b] == "."
            if a[i_a] != b[i_b] and b[i_b] != "_":
                return False
            i_a += 1

        return i_a >= ext_a

    if _compare(s1, s2):
        return True

    # Try URL-decoded version of s1
    decoded = unquote(s1)
    if decoded != s1:
        return _compare(decoded, s2)

    return False
```

## Verifica

```bash
cd web-gui && python -c "
import tempfile, os
from datetime import datetime
from sync_engine.file_utils import (
    set_file_date, do_file_date_update, dir_has_files, compare_mangled
)

# Test set_file_date
tmpfile = tempfile.NamedTemporaryFile(delete=False)
tmpfile.write(b'test')
tmpfile.close()
target_date = datetime(2025, 6, 15, 12, 0)
set_file_date(tmpfile.name, target_date)
stat = os.stat(tmpfile.name)
assert abs(stat.st_mtime - target_date.timestamp()) < 1
os.unlink(tmpfile.name)

# Test dir_has_files
tmpdir = tempfile.mkdtemp()
assert not dir_has_files(tmpdir, 'nonexistent')
subdir = os.path.join(tmpdir, 'testid')
os.makedirs(subdir)
assert not dir_has_files(tmpdir, 'testid')  # empty dir
with open(os.path.join(subdir, 'photo.jpg'), 'w') as f:
    f.write('data')
assert dir_has_files(tmpdir, 'testid')  # has file

# Test compare_mangled
assert compare_mangled('photo.jpg', 'photo.jpg')
assert compare_mangled('photo.jpg', 'photo.gif')  # different extension
assert compare_mangled('my photo.jpg', 'my_photo.jpg')  # underscore replacement
assert not compare_mangled('totally_different.jpg', 'photo.jpg')

# Cleanup
import shutil
shutil.rmtree(tmpdir)

print('All file_utils tests passed!')
"
```
