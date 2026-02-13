# Passo 5: Portare Date Parser (date_parser.py)

## Obiettivo

Portare `gphotos-cdp/internal/utils/date.go` in Python. Parsing multi-lingua delle date estratte dai metadati `aria-label` delle foto in Google Photos.

## File sorgente Go: `gphotos-cdp/internal/utils/date.go` (118 righe)

## File da creare: `web-gui/sync_engine/date_parser.py`

## Formati data supportati (da aria-label)

Google Photos usa formati diversi per lingua:

- **Inglese**: `"Photo - Portrait - Nov 17, 2025, 11:08:35 PM"` → dateStr=`"Nov 17 2025"`, timeStr=`"11:08:35 PM"`
- **Italiano**: `"Foto - Verticale - 13 nov 2025, 00:57:41"` → dateStr=`"13 nov 2025"`, timeStr=`"00:57:41"`
- **Tedesco**: `"Foto - Hochformat - 13. Nov. 2025, 14:32:41"` → dateStr=`"13. Nov. 2025"`, timeStr=`"14:32:41"`

Il parsing avviene in download.go:GetPhotoData (righe 439-457) che splitta l'aria-label in dateStr e timeStr, poi chiama parseDateWithConfig che a sua volta chiama utils.ParseDate.

## Logica di ParseDate (date.go:23-108)

Parametri: `dateStr, timeStr, tzStr string, months []string, pageLanguage string`

1. **Parsing anno**: regex `\d{4}`, estrai e rimuovi dalla stringa
2. **Parsing giorno**: regex `\d{1,2}`, estrai e rimuovi dalla stringa
3. **Parsing mese**: itera `months[]`, cerca match case-insensitive nella stringa restante. L'indice+1 = numero mese
4. **Parsing ora**: regex `(\d{1,2}):(\d\d)(?::\d\d)?.?([aApP][Mm])?$` su timeStr
   - Se PM e ora < 12: ora += 12
   - Se AM e ora == 12: ora = 0
5. **Parsing timezone**: regex `GMT([-+])?(\d{1,2})(?::(\d\d))?` su tzStr (opzionale, di solito vuoto)
6. Ritorna `time.Date(year, month, day, hour, minute, 0, 0, timezone)`

## Codice completo da scrivere

```python
"""Multi-language date parsing for Google Photos metadata.

Parses dates from aria-label attributes like:
  English: "Nov 17, 2025, 11:08:35 PM"
  Italian: "13 nov 2025, 00:57:41"
  German:  "13. Nov. 2025, 14:32:41"

Uses month names from months-config.json for language-aware parsing.

Equivalent of Go utils.ParseDate().
"""

import logging
import re
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Regex patterns (same as Go)
YEAR_RE = re.compile(r"\d{4}")
DAY_RE = re.compile(r"\d{1,2}")
TIME_RE = re.compile(r"(\d{1,2}):(\d\d)(?::\d\d)?\.?([aApP][mM])?$")
TZ_RE = re.compile(r"GMT([-+])?(\d{1,2})(?::(\d\d))?")


def parse_date(
    date_str: str,
    time_str: str,
    tz_str: str,
    months: list[str],
    page_language: str,
) -> datetime:
    """Parse a date string with time and optional timezone.

    Args:
        date_str: Date portion, e.g. "Nov 17 2025" or "13 nov 2025"
        time_str: Time portion, e.g. "11:08:35 PM" or "00:57:41"
        tz_str: Optional timezone, e.g. "GMT+1" or "" (defaults to local)
        months: List of 12 abbreviated month names for the page language
        page_language: Language code (for error messages)

    Returns:
        datetime object

    Raises:
        ValueError: If date cannot be parsed
    """
    if not months or not page_language:
        raise ValueError("months and page_language must be provided")

    # --- Parse year ---
    year_match = YEAR_RE.search(date_str)
    if year_match:
        year = int(year_match.group())
        date_str = date_str.replace(year_match.group(), "", 1)
    else:
        year = datetime.now().year

    logger.debug("parsed year: %d, remaining dateStr: %s", year, date_str)

    # --- Parse day ---
    day_match = DAY_RE.search(date_str)
    day = int(day_match.group()) if day_match else 1
    if day_match:
        date_str = date_str.replace(day_match.group(), "", 1)

    # --- Parse month ---
    month = 0
    for i, month_name in enumerate(months):
        if month_name.lower() in date_str.lower():
            month = i + 1
            logger.debug(
                "found month %s (index %d) in page language %s",
                month_name, month, page_language,
            )
            break

    if month == 0:
        raise ValueError(
            f'Could not find month in date string "{date_str}" for language "{page_language}"\n\n'
            f'Expected one of these month names: {", ".join(months)}\n\n'
            f"This might indicate:\n"
            f'1. The months-config.json for "{page_language}" is incorrect\n'
            f"2. Google Photos changed its date format\n"
            f"3. The date format is different than expected"
        )

    logger.debug("parsed month: %d, remaining dateStr: %s", month, date_str)

    # --- Parse time ---
    hour, minute = 0, 0
    if time_str:
        time_match = TIME_RE.search(time_str)
        if not time_match:
            raise ValueError(f"Could not find time in string: {time_str}")
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        ampm = time_match.group(3)
        if ampm and ampm.upper() == "PM" and hour < 12:
            hour += 12
        if ampm and ampm.upper() == "AM" and hour == 12:
            hour = 0

    # --- Parse timezone ---
    tz = None
    tz_str_stripped = tz_str.strip() if tz_str else ""
    if tz_str_stripped:
        tz_match = TZ_RE.search(tz_str_stripped)
        if tz_match:
            tz_hour = int(tz_match.group(2))
            tz_minute = int(tz_match.group(3) or "0")
            offset_seconds = tz_hour * 3600 + tz_minute * 60
            if tz_match.group(1) == "-":
                offset_seconds = -offset_seconds
            tz = timezone(timedelta(seconds=offset_seconds))
        else:
            raise ValueError(f"Could not parse timezone in string: {tz_str_stripped}")

    return datetime(year, month, day, hour, minute, tzinfo=tz)
```

## Verifica

```bash
cd web-gui && python -c "
from sync_engine.date_parser import parse_date

# Test formato inglese
en_months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
dt = parse_date('Nov 17 2025', '11:08:35 PM', '', en_months, 'en')
assert dt.year == 2025
assert dt.month == 11
assert dt.day == 17
assert dt.hour == 23  # PM
assert dt.minute == 8
print(f'English: {dt}')

# Test formato italiano
it_months = ['gen','feb','mar','apr','mag','giu','lug','ago','set','ott','nov','dic']
dt = parse_date('13 nov 2025', '00:57:41', '', it_months, 'it')
assert dt.year == 2025
assert dt.month == 11
assert dt.day == 13
assert dt.hour == 0
assert dt.minute == 57
print(f'Italian: {dt}')

# Test AM edge case (12 AM = 0)
dt = parse_date('Jan 1 2025', '12:30:00 AM', '', en_months, 'en')
assert dt.hour == 0

# Test PM edge case (12 PM = 12)
dt = parse_date('Jan 1 2025', '12:30:00 PM', '', en_months, 'en')
assert dt.hour == 12

# Test timezone
dt = parse_date('Jan 1 2025', '12:00:00', 'GMT+2', en_months, 'en')
assert dt.tzinfo is not None

# Test errore mese non trovato
try:
    parse_date('99 xyz 2025', '00:00:00', '', en_months, 'en')
    assert False, 'Should have raised ValueError'
except ValueError as e:
    assert 'Could not find month' in str(e)

print('All date_parser tests passed!')
"
```
