# Passo 15: Testing e Cleanup Finale

## Obiettivo

Aggiungere test per i moduli core, fare cleanup del codice Go rimosso, e verificare che tutto funzioni end-to-end.

## 15.1 Test unitari per moduli senza browser

Creare `web-gui/tests/` con test per i moduli che non richiedono browser:

### `web-gui/tests/__init__.py`

Vuoto.

### `web-gui/tests/test_date_parser.py`

```python
import pytest
from datetime import datetime
from sync_engine.date_parser import parse_date

EN_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
IT_MONTHS = ["gen","feb","mar","apr","mag","giu","lug","ago","set","ott","nov","dic"]

def test_english_date():
    dt = parse_date("Nov 17 2025", "11:08:35 PM", "", EN_MONTHS, "en")
    assert dt == datetime(2025, 11, 17, 23, 8)

def test_italian_date():
    dt = parse_date("13 nov 2025", "00:57:41", "", IT_MONTHS, "it")
    assert dt == datetime(2025, 11, 13, 0, 57)

def test_am_midnight():
    dt = parse_date("Jan 1 2025", "12:30:00 AM", "", EN_MONTHS, "en")
    assert dt.hour == 0

def test_pm_noon():
    dt = parse_date("Jan 1 2025", "12:30:00 PM", "", EN_MONTHS, "en")
    assert dt.hour == 12

def test_timezone():
    dt = parse_date("Jan 1 2025", "12:00:00", "GMT+2", EN_MONTHS, "en")
    assert dt.tzinfo is not None

def test_unknown_month_raises():
    with pytest.raises(ValueError, match="Could not find month"):
        parse_date("99 xyz 2025", "00:00:00", "", EN_MONTHS, "en")

def test_no_year_defaults_to_current():
    dt = parse_date("Nov 17", "12:00:00", "", EN_MONTHS, "en")
    assert dt.year == datetime.now().year
```

### `web-gui/tests/test_downloaded_ids.py`

```python
import os
import tempfile
import pytest
from sync_engine.downloaded_ids import DownloadedIdsManager

@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    import shutil
    shutil.rmtree(d)

def test_empty_start(tmp_dir):
    mgr = DownloadedIdsManager(tmp_dir)
    assert mgr.count() == 0
    assert not mgr.has("test")

def test_add_and_has(tmp_dir):
    mgr = DownloadedIdsManager(tmp_dir)
    mgr.add("id1")
    assert mgr.has("id1")
    assert mgr.count() == 1

def test_idempotent_add(tmp_dir):
    mgr = DownloadedIdsManager(tmp_dir)
    mgr.add("id1")
    mgr.add("id1")
    assert mgr.count() == 1

def test_persistence(tmp_dir):
    mgr1 = DownloadedIdsManager(tmp_dir)
    mgr1.add("id1")
    mgr1.add("id2")

    mgr2 = DownloadedIdsManager(tmp_dir)
    assert mgr2.count() == 2
    assert mgr2.has("id1")
    assert mgr2.has("id2")

def test_get_all(tmp_dir):
    mgr = DownloadedIdsManager(tmp_dir)
    mgr.add("a")
    mgr.add("b")
    mgr.add("c")
    all_ids = mgr.get_all()
    assert set(all_ids) == {"a", "b", "c"}
```

### `web-gui/tests/test_config.py`

```python
import json
import os
import tempfile
import pytest
from sync_engine.config import load_months_config, save_months_config, get_configured_languages, months_config
from sync_engine.models import MonthConfig

@pytest.fixture
def config_file():
    data = {
        "en": {
            "months": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
            "metadataFormat": "Photo - Nov 17, 2025",
            "dateFormat": "month day, year"
        }
    }
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, f)
    f.close()
    yield f.name
    os.unlink(f.name)

def test_load_missing_file():
    load_months_config("/nonexistent/path.json")
    assert months_config == {} or True  # Should not crash

def test_load_valid_file(config_file):
    load_months_config(config_file)
    assert "en" in months_config
    assert months_config["en"].months[0] == "Jan"

def test_save_and_reload(config_file):
    load_months_config(config_file)
    months_config["it"] = MonthConfig(
        months=["gen","feb","mar","apr","mag","giu","lug","ago","set","ott","nov","dic"],
        metadata_format="Foto - 13 nov 2025",
        date_format="day month year",
    )
    save_months_config(config_file)

    load_months_config(config_file)
    assert "it" in months_config
    assert months_config["it"].months[0] == "gen"

def test_get_configured_languages(config_file):
    load_months_config(config_file)
    langs = get_configured_languages()
    assert "en" in langs
```

### `web-gui/tests/test_navigation.py`

```python
import pytest
from sync_engine.navigation import image_id_from_url, get_photo_node_selector
from sync_engine.models import Session

def test_image_id_basic():
    assert image_id_from_url("./photo/ABC123") == "ABC123"

def test_image_id_album():
    assert image_id_from_url("./album/XYZ/photo/ABC123") == "ABC123"

def test_image_id_full_url():
    assert image_id_from_url("https://photos.google.com/photo/ABC123") == "ABC123"

def test_image_id_invalid():
    with pytest.raises(ValueError):
        image_id_from_url("/no/photo/pattern")

def test_photo_selector_album():
    s = Session(download_dir="", download_dir_tmp="", profile_dir="", album_path="/album/XYZ")
    assert get_photo_node_selector(s) == 'a[href^="./album/XYZ/photo/"]'

def test_photo_selector_library():
    s = Session(download_dir="", download_dir_tmp="", profile_dir="")
    assert get_photo_node_selector(s) == 'a[href^="./photo/"]'
```

### `web-gui/tests/test_file_utils.py`

```python
import os
import tempfile
from datetime import datetime
from sync_engine.file_utils import set_file_date, compare_mangled, dir_has_files

def test_set_file_date():
    f = tempfile.NamedTemporaryFile(delete=False)
    f.write(b"test")
    f.close()
    target = datetime(2025, 6, 15, 12, 0)
    set_file_date(f.name, target)
    assert abs(os.stat(f.name).st_mtime - target.timestamp()) < 1
    os.unlink(f.name)

def test_compare_mangled_exact():
    assert compare_mangled("photo.jpg", "photo.jpg")

def test_compare_mangled_underscore():
    assert compare_mangled("my photo.jpg", "my_photo.jpg")

def test_compare_mangled_different():
    assert not compare_mangled("totally_different.jpg", "photo.jpg")

def test_dir_has_files():
    d = tempfile.mkdtemp()
    assert not dir_has_files(d, "nonexistent")
    sub = os.path.join(d, "testid")
    os.makedirs(sub)
    assert not dir_has_files(d, "testid")
    with open(os.path.join(sub, "file.jpg"), "w") as f:
        f.write("data")
    assert dir_has_files(d, "testid")
    import shutil
    shutil.rmtree(d)
```

## 15.2 Come eseguire i test

```bash
# Dalla root del progetto
cd web-gui

# Installare dipendenze test
pip install pytest

# Eseguire tutti i test
python -m pytest tests/ -v

# Eseguire un singolo test
python -m pytest tests/test_date_parser.py -v

# Con coverage (opzionale)
pip install pytest-cov
python -m pytest tests/ --cov=sync_engine --cov-report=term-missing
```

## 15.3 Cleanup: rimuovere codice Go

ATTENZIONE: Fare questo solo DOPO aver verificato che il sync engine Python funziona end-to-end.

```bash
# Rimuovere il progetto Go
rm -rf gphotos-cdp/

# Spostare months-config.json se non gia' fatto
# (dovrebbe essere gia' stato fatto nel passo 14)

# Rimuovere shell scripts obsoleti
rm src/postdl.sh     # Sostituito da sync_engine/postdl.py
# MANTENERE: src/start.sh (ancora usato come entrypoint)
# MANTENERE: src/sync.sh (ancora usato per orchestrazione album)
# MANTENERE: src/log.sh (usato da start.sh e sync.sh)
```

## 15.4 Aggiornare .gitignore

Aggiungere:
```
__pycache__/
*.pyc
.pytest_cache/
```

## 15.5 Aggiornare CLAUDE.md

Aggiornare il file CLAUDE.md per riflettere la nuova architettura:
- Rimuovere sezione Go Sync Engine
- Aggiungere sezione Python Sync Engine
- Aggiornare i comandi build
- Aggiornare il diagramma architetturale

## 15.6 Test end-to-end

Checklist manuale:

1. [ ] `docker build -t gphotos-sync:latest .` completa senza errori
2. [ ] `docker compose up -d` avvia la web-gui
3. [ ] http://localhost:8080 mostra la dashboard
4. [ ] Creare un profilo funziona
5. [ ] Autenticazione via VNC funziona
6. [ ] Avviare un sync container funziona
7. [ ] I log del container mostrano output del sync engine Python
8. [ ] Le foto vengono scaricate nella directory corretta
9. [ ] I metadati EXIF vengono aggiornati
10. [ ] Il cron schedule funziona
11. [ ] Stop/restart del container funziona
12. [ ] Rebuild dell'immagine funziona
