# Passo 3: Portare Gestione Config (config.py)

## Obiettivo

Portare `gphotos-cdp/internal/config/config.go` in Python. Gestisce il file `months-config.json` che contiene i nomi dei mesi per ogni lingua supportata.

## File sorgente Go: `gphotos-cdp/internal/config/config.go` (118 righe)

## File da creare: `web-gui/sync_engine/config.py`

## Logica da portare

### Variabili globali (config.go:22-25)

Go:
```go
var MonthsConfig map[string]MonthConfig
var PageLanguage string
```

Python: usare variabili a livello di modulo (come fa il Go con le var globali):
```python
months_config: dict[str, MonthConfig] = {}
page_language: str = ""
```

### LoadMonthsConfig (config.go:40-75)

Logica:
1. Path fisso: `/app/months-config.json`
2. Se il file non esiste, inizializza mappa vuota e ritorna (no errore)
3. Se esiste, leggi JSON e deserializza in `map[string]MonthConfig`
4. Se JSON invalido, errore fatale
5. Se mappa vuota, warning
6. Logga le lingue caricate

### SaveMonthsConfig (config.go:78-117)

Logica:
1. Path fisso: `/app/months-config.json`
2. Serializza con chiavi ordinate alfabeticamente
3. Formato custom: array months su una riga, il resto indentato
4. Scrivi su file

NOTA: Il formato custom di Go (mesi su una riga) puo' essere semplificato in Python usando `json.dumps` con `indent=2`. Non serve replicare il formato esatto, l'importante e' che sia JSON valido leggibile.

### GetConfiguredLanguages (config.go:28-37)

Logica: ritorna stringa comma-separated delle chiavi della mappa.

## Codice completo da scrivere

```python
"""Months configuration management for language-aware date parsing.

Reads/writes /app/months-config.json which maps language codes to month names.
This file is shared across all sync profiles via Docker volume mount.
"""

import json
import logging
import os
from typing import Optional

from .models import MonthConfig

logger = logging.getLogger(__name__)

# Global state (module-level, like Go's package-level vars)
months_config: dict[str, MonthConfig] = {}
page_language: str = ""

# Default config path (inside container). Can be overridden for testing.
CONFIG_PATH = os.environ.get("MONTHS_CONFIG_PATH", "/app/months-config.json")


def load_months_config(config_path: Optional[str] = None) -> None:
    """Load months configuration from JSON file.

    If file doesn't exist, initializes empty config (languages will be
    auto-extracted on first use).

    Equivalent of Go config.LoadMonthsConfig()
    """
    global months_config
    path = config_path or CONFIG_PATH

    logger.debug("Looking for months-config.json at: %s", path)

    if not os.path.exists(path):
        logger.warning(
            "months-config.json not found at %s - will auto-extract languages on first use",
            path
        )
        months_config = {}
        return

    try:
        with open(path, "r") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Error parsing months-config.json: {e}\n\n"
            "The file exists but contains invalid JSON. Please check the format."
        ) from e

    months_config = {}
    for lang, data in raw.items():
        months_config[lang] = MonthConfig(
            months=data.get("months", []),
            metadata_format=data.get("metadataFormat", ""),
            date_format=data.get("dateFormat", ""),
        )

    if not months_config:
        logger.warning("months-config.json is empty. Languages will be auto-extracted on first use.")
        return

    languages = ", ".join(sorted(months_config.keys()))
    logger.info("Loaded month configurations for languages: %s", languages)


def save_months_config(config_path: Optional[str] = None) -> None:
    """Save months configuration to JSON file.

    Writes sorted by language key with readable formatting.

    Equivalent of Go config.SaveMonthsConfig()
    """
    path = config_path or CONFIG_PATH

    # Build dict sorted by language key
    out = {}
    for lang in sorted(months_config.keys()):
        cfg = months_config[lang]
        out[lang] = {
            "months": cfg.months,
            "metadataFormat": cfg.metadata_format,
            "dateFormat": cfg.date_format,
        }

    with open(path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")

    logger.info("Saved updated months-config.json to %s", path)


def get_configured_languages() -> str:
    """Return comma-separated list of configured languages.

    Equivalent of Go config.GetConfiguredLanguages()
    """
    if not months_config:
        return "none"
    return ", ".join(sorted(months_config.keys()))
```

## Formato JSON di riferimento (months-config.json)

```json
{
  "en": {
    "months": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
    "metadataFormat": "Photo - Portrait - Nov 17, 2025, 11:08:38 PM",
    "dateFormat": "month day, year"
  },
  "it": {
    "months": ["gen","feb","mar","apr","mag","giu","lug","ago","set","ott","nov","dic"],
    "metadataFormat": "Foto - Verticale - 21 nov 2025, 17:56:20",
    "dateFormat": "day month year"
  }
}
```

## Verifica

```bash
cd web-gui && python -c "
from sync_engine.config import load_months_config, save_months_config, get_configured_languages, months_config
from sync_engine.models import MonthConfig

# Test con file inesistente (non deve crashare)
load_months_config('/tmp/nonexistent.json')
assert months_config == {}
assert get_configured_languages() == 'none'

# Test con file valido
import json, tempfile, os
test_data = {
    'en': {'months': ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
           'metadataFormat': 'Photo - Nov 17, 2025', 'dateFormat': 'month day, year'}
}
tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
json.dump(test_data, tmp)
tmp.close()

load_months_config(tmp.name)
assert 'en' in months_config
assert months_config['en'].months[0] == 'Jan'
assert get_configured_languages() == 'en'

# Test save
save_months_config(tmp.name)
with open(tmp.name) as f:
    saved = json.load(f)
assert saved['en']['months'][0] == 'Jan'

os.unlink(tmp.name)
print('All config tests passed!')
"
```
