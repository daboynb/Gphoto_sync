# Passo 9: Portare Download Engine (download.py)

## Obiettivo

Portare `gphotos-cdp/internal/download/download.go` (731 righe) in Python. Gestisce il trigger del download via Shift+D, l'attesa del completamento, l'estrazione dei metadati, e il processing dei file scaricati.

## File da creare: `web-gui/sync_engine/download.py`

## Differenza fondamentale: Download in Playwright vs chromedp

### In Go (chromedp)

I download sono gestiti a basso livello tramite CDP events:
1. `browser.SetDownloadBehavior()` configura dove salvare i file
2. `chromedp.ListenBrowser()` ascolta `EventDownloadWillBegin` e `EventDownloadProgress`
3. Il download viene triggerato con `Shift+D` (keyboard shortcut)
4. I file vengono salvati con GUID come nome nella directory tmp
5. Dopo il completamento, vengono rinominati e spostati

### In Python (Playwright)

Playwright ha un'API di download di alto livello:
1. `page.on("download", handler)` cattura ogni download
2. `download.save_as(path)` salva il file
3. `download.suggested_filename` da' il nome originale
4. `download.path()` da' il path temporaneo

MA: il download viene comunque triggerato con `Shift+D` perche' Google Photos non ha un URL diretto per il download. Quindi il flusso e':
1. Registra handler `page.expect_download()`
2. Premi `Shift+D`
3. Attendi l'evento download
4. Salva il file con `download.save_as()`

## Funzioni da portare

### StartDownloadListener (download.go:500-544) → NON SERVE

In Playwright, non serve un listener globale. Usiamo `page.expect_download()` per ogni singolo download. Questa funzione viene eliminata.

### DownloadWorker (download.go:617-656) → Spostato in sync.py

I worker in Python saranno task asyncio. La logica del worker va nel passo 10 (sync.py).

### DownloadAndProcessItem (download.go:46-147)

Orchestrazione per un singolo item:
1. In parallelo: GetPhotoData() e StartDownload()
2. Attendi completamento di entrambi
3. ProcessDownload() per organizzare i file
4. Timeout 30 minuti

In Python con asyncio: `asyncio.gather(get_photo_data(...), start_download(...))`.

### StartDownload (download.go:152-196)

Logica:
1. Timeout 120 secondi
2. Loop:
   - Controlla se video "still processing"
   - Premi Shift+D
   - Se download non parte in 5 secondi, ricarica pagina
   - Se download parte, ritorna info
3. In Playwright: `async with page.expect_download(timeout=120000) as download_info`

### WaitForDownload (download.go:199-222) → Integrato in StartDownload

In Playwright, `download.save_as()` attende automaticamente il completamento.

### ProcessDownload (download.go:225-292)

Logica:
1. Crea directory output: `{download_dir}/{YYYY}/{MM}/`
2. Se il file e' un .zip, estrailo
3. Altrimenti, rinomina il file
4. Aggiorna date di modifica dei file
5. Esegui hook post-download (`-run` flag)
6. Segna l'ID come scaricato

### GetPhotoData (download.go:378-497)

Logica complessa:
1. Timeout 4 minuti
2. Loop fino a 10 tentativi:
   - Ogni 5 tentativi, ricarica la pagina
   - Attendi con backoff esponenziale
   - Esegui JS per estrarre aria-label dall'elemento `[data-p*="{imageId}"]`
   - L'aria-label ha formato: `"Photo - Portrait - Nov 17, 2025, 11:08:35 PM"`
   - Splitta per ` - ` e prendi l'ultima parte (data+ora)
   - Splitta per `, ` per separare data da ora
   - Se formato europeo (2 parti): `dateStr = parts[0]`, `timeStr = parts[1]`
   - Se formato inglese (3 parti): `dateStr = parts[0] + " " + parts[1]`, `timeStr = parts[2]`
3. Chiama parseDateWithConfig() per convertire in datetime

### HandleZip (download.go:296-312)

Logica: estrai zip, elimina zip, ritorna lista file estratti.
Python: `zipfile.extractall()`.

### CheckForStillProcessing (download.go:315-375)

Logica: controlla se Google Photos mostra "Video is still processing" via JS evaluation.

### DoWorkerBatchItem (download.go:671-730)

Logica per processare un singolo item in un batch:
1. Se e' consecutivo al precedente, prova freccia destra
2. Se non e' alla URL attesa, naviga direttamente
3. Chiama DownloadAndProcessItem

## Codice completo da scrivere

```python
"""Photo download and processing engine.

Handles triggering downloads via Shift+D, waiting for completion,
extracting metadata, and organizing downloaded files.

Equivalent of Go download/download.go.
"""

import asyncio
import json
import logging
import math
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from unicodedata import normalize

from playwright.async_api import Page, Download

from . import config as cfg
from .date_parser import parse_date
from .file_utils import do_file_date_update, do_run, compare_mangled
from .models import GPHOTOS_URL, PhotoData, Session
from .navigation import navigate_to_photo, navigate_with_retry, image_id_from_url

logger = logging.getLogger(__name__)


class StillProcessingError(Exception):
    """Video is still processing and can't be downloaded."""
    pass


class UnexpectedDownloadError(Exception):
    """Downloaded file doesn't match expected item."""
    pass


async def download_and_process_item(
    session: Session,
    page: Page,
    image_id: str,
    run_flag: str = "",
) -> None:
    """Download a photo/video and process it.

    Runs metadata extraction and download in parallel, then
    organizes the files into the date-based directory structure.

    Equivalent of Go download.DownloadAndProcessItem().
    """
    logger.debug("[%s] entering download_and_process_item", image_id)
    start = asyncio.get_event_loop().time()

    for attempt in range(3):
        try:
            # Run metadata extraction and download in parallel
            photo_data_task = asyncio.create_task(
                get_photo_data(session, page, image_id)
            )
            download_task = asyncio.create_task(
                start_download(session, page, image_id)
            )

            # Wait for both with a 30-minute timeout
            (photo_data, (download_path, suggested_filename)) = await asyncio.wait_for(
                asyncio.gather(photo_data_task, download_task),
                timeout=30 * 60,
            )

            # Process the downloaded file
            await process_download(
                session, download_path, suggested_filename,
                image_id, photo_data, run_flag,
            )

            duration = (asyncio.get_event_loop().time() - start) * 1000
            logger.debug("[%s] download_and_process_item completed in %dms", image_id, duration)
            return

        except UnexpectedDownloadError as e:
            logger.warning("[%s] unexpected download (attempt %d/3): %s", image_id, attempt + 1, e)
            continue
        except StillProcessingError:
            logger.info("[%s] skipping - video still processing", image_id)
            raise
        except Exception as e:
            # Cleanup any partial downloads
            partial_dir = os.path.join(session.download_dir, image_id)
            if os.path.exists(partial_dir):
                logger.info("[%s] removing partial download files", image_id)
                shutil.rmtree(partial_dir, ignore_errors=True)
            raise


async def start_download(
    session: Session,
    page: Page,
    image_id: str,
) -> tuple[str, str]:
    """Trigger download via Shift+D and wait for completion.

    Returns (saved_file_path, suggested_filename).

    Equivalent of Go download.StartDownload() + WaitForDownload().
    """
    logger.debug("[%s] starting download", image_id)
    start = asyncio.get_event_loop().time()

    timeout = 120  # seconds
    refresh_interval = 5  # seconds before retrying
    last_request_time = 0

    deadline = asyncio.get_event_loop().time() + timeout

    while True:
        now = asyncio.get_event_loop().time()

        if now > deadline:
            raise RuntimeError(f"timeout waiting for download to start for {image_id}")

        # Check for "still processing" video
        await check_for_still_processing(page)

        # Try to trigger download with Shift+D
        try:
            async with page.expect_download(timeout=refresh_interval * 1000) as download_info:
                logger.debug("[%s] requesting download via Shift+D", image_id)
                await page.keyboard.press("Shift+D")
                await asyncio.sleep(0.05)

            download: Download = download_info.value

            # Skip downloads.html (Chrome's download page)
            if download.suggested_filename == "downloads.html":
                continue

            # Wait for download to complete and save
            save_path = os.path.join(
                session.download_dir_tmp,
                download.suggested_filename,
            )
            await download.save_as(save_path)

            duration = (asyncio.get_event_loop().time() - start) * 1000
            logger.debug("[%s] download completed in %dms", image_id, duration)
            return save_path, download.suggested_filename

        except Exception as e:
            if "Download timeout" in str(e) or "Timeout" in str(e):
                # Download didn't start, reload page and try again
                logger.debug("[%s] reloading page because download failed to start", image_id)
                try:
                    await navigate_to_photo(session, page, image_id)
                    await asyncio.sleep(0.1)
                except Exception as nav_err:
                    logger.error("[%s] navigation error: %s", image_id, nav_err)
                    await asyncio.sleep(1)
                continue
            raise


async def process_download(
    session: Session,
    download_path: str,
    suggested_filename: str,
    image_id: str,
    photo_data: PhotoData,
    run_flag: str = "",
) -> None:
    """Process a downloaded file: organize into date dirs, update metadata.

    Equivalent of Go download.ProcessDownload().
    """
    logger.debug("[%s] processing download", image_id)

    out_dir = _make_out_dir(session, photo_data.date)
    file_paths = []

    if suggested_filename.endswith(".zip"):
        # Extract zip file
        file_paths = _handle_zip(download_path, out_dir)
        # Verify expected file is in the zip
        found = any(
            compare_mangled(photo_data.filename, normalize("NFC", os.path.basename(f)))
            for f in file_paths
        )
        if not found:
            basenames = [os.path.basename(f) for f in file_paths]
            logger.debug(
                "[%s] accepting any file from zip, found: %s",
                image_id, ", ".join(basenames),
            )
    else:
        # Single file
        if suggested_filename not in ("download", ""):
            filename = normalize("NFC", suggested_filename)
        else:
            filename = photo_data.filename

        logger.debug("[%s] accepting downloaded filename: %s", image_id, filename)
        new_path = os.path.join(out_dir, filename)
        shutil.move(download_path, new_path)
        file_paths = [new_path]

    # Update file modification dates
    do_file_date_update(photo_data.date, file_paths)

    # Run post-download hook
    for f in file_paths:
        do_run(f, image_id, run_flag)

    # Log success
    basenames = [os.path.basename(f) for f in file_paths]
    logger.info(
        "[%s] downloaded file(s) %s with date %s",
        image_id, ", ".join(basenames), photo_data.date.strftime("%Y-%m-%d"),
    )

    # Mark as downloaded
    try:
        session.downloaded_ids.add(image_id)
    except Exception as e:
        logger.warning(
            "[%s] failed to save downloaded ID to file (download succeeded): %s",
            image_id, e,
        )


async def get_photo_data(
    session: Session,
    page: Page,
    image_id: str,
) -> PhotoData:
    """Extract date and filename from the photo's metadata.

    Reads the aria-label attribute from the photo info panel in the DOM.
    Retries up to 10 times with exponential backoff.

    Equivalent of Go download.GetPhotoData().
    """
    logger.debug("[%s] extracting photo data", image_id)
    start = asyncio.get_event_loop().time()

    for attempt in range(1, 11):
        # Every 5 attempts, reload the page to force metadata to load
        if attempt % 5 == 0 and attempt > 1:
            logger.debug("[%s] getPhotoData: reloading page (attempt %d)", image_id, attempt)
            try:
                await navigate_to_photo(session, page, image_id)
            except Exception as e:
                logger.error("[%s] getPhotoData: navigation error: %s", image_id, e)

        # Check for undownloadable video
        undownloadable = await page.evaluate(f"""
            [...document.querySelectorAll('c-wiz[data-media-key*="'+document.location.href.trim().split('/').pop()+'"]')]
                .filter(x => getComputedStyle(x).visibility != 'hidden')[0]
                ?.textContent.indexOf('Your video will be ready soon') >= 0
        """)
        if undownloadable:
            raise StillProcessingError("Video is still processing")

        # Exponential backoff sleep
        sleep_ms = min(2000, (1.5 ** (attempt - 1) - 1) * 50)
        await asyncio.sleep(sleep_ms / 1000)

        # Extract aria-label from photo info element
        photo_info_label = await page.evaluate(f"""
            [...document.querySelectorAll('[data-p*="{image_id}"] [aria-label]')]
                .map(el => el.getAttribute('aria-label'))
                .find(label => label && (label.startsWith('Foto - ') || label.startsWith('Video - ') ||
                                          label.startsWith('Photo - ') || label.startsWith('Video - '))) || ''
        """)

        if not photo_info_label:
            logger.debug("[%s] attempt %d: no photo info label found", image_id, attempt)
            # Wait outside of any "tab lock" so we don't block other operations
            await asyncio.sleep(attempt * 0.5)
            continue

        # Parse the label
        # Examples:
        # Italian: "Foto - Verticale - 13 nov 2025, 00:57:41"
        # English: "Photo - Portrait - Nov 17, 2025, 11:08:35 PM"
        parts = photo_info_label.split(" - ")
        if len(parts) < 3:
            logger.debug("[%s] attempt %d: unexpected label format: %s", image_id, attempt, photo_info_label)
            continue

        datetime_str = parts[-1]
        datetime_parts = datetime_str.split(", ")

        date_str = ""
        time_str = ""
        filename = image_id

        if len(datetime_parts) == 2:
            # European format: "13 nov 2025", "00:57:41"
            date_str = datetime_parts[0]
            time_str = datetime_parts[1]
        elif len(datetime_parts) == 3:
            # English format: "Nov 17", "2025", "11:08:35 PM"
            date_str = datetime_parts[0] + " " + datetime_parts[1]
            time_str = datetime_parts[2]
        else:
            logger.debug("[%s] attempt %d: unexpected datetime format: %s", image_id, attempt, datetime_str)
            continue

        if date_str and time_str:
            duration = (asyncio.get_event_loop().time() - start) * 1000
            logger.debug(
                "[%s] found photo data nodes in %dms (%d attempts)",
                image_id, duration, attempt,
            )

            # Parse the date using language config
            lang_cfg = cfg.months_config.get(cfg.page_language)
            if not lang_cfg:
                raise ValueError(
                    f"Language configuration not found for {cfg.page_language}"
                )

            dt = parse_date(date_str, time_str, "", lang_cfg.months, cfg.page_language)
            logger.debug("[%s] parsed date: %s, filename: %s", image_id, dt, filename)

            return PhotoData(date=dt, filename=normalize("NFC", filename))

    # All attempts exhausted
    raise RuntimeError(f"Failed to extract metadata after 10 attempts for {image_id}")


async def check_for_still_processing(page: Page) -> None:
    """Check if video is still being processed by Google.

    Equivalent of Go download.CheckForStillProcessing().
    """
    try:
        undownloadable = await asyncio.wait_for(
            page.evaluate("""
                (function() {
                    return [...document.querySelectorAll('c-wiz[data-media-key*="'+document.location.href.trim().split('/').pop()+'"]')]
                        .filter(x => getComputedStyle(x).visibility != 'hidden')[0]
                        ?.textContent.indexOf('Your video will be ready soon') >= 0;
                })()
            """),
            timeout=4,
        )
        if undownloadable:
            raise StillProcessingError("Video is still processing")
    except asyncio.TimeoutError:
        pass


def _make_out_dir(session: Session, date: datetime) -> str:
    """Create date-based output directory: {download_dir}/YYYY/MM/

    Equivalent of Go download.makeOutDir().
    """
    year = date.strftime("%Y")
    month = date.strftime("%m")
    out_dir = os.path.join(session.download_dir, year, month)
    os.makedirs(out_dir, mode=0o700, exist_ok=True)
    logger.debug("Created output directory for date %s: %s", date.strftime("%Y-%m"), out_dir)
    return out_dir


def _handle_zip(zip_path: str, out_folder: str) -> list[str]:
    """Extract a zip file and return list of extracted file paths.

    Equivalent of Go download.HandleZip().
    """
    logger.debug("unzipping %s to %s", zip_path, out_folder)
    extracted = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(out_folder)
        extracted = [os.path.join(out_folder, name) for name in zf.namelist()]

    os.remove(zip_path)
    logger.debug("done unzipping: %s", zip_path)
    return extracted
```

## Differenze rispetto al Go

| Aspetto | Go | Python |
|---|---|---|
| Download trigger | `Shift+D` via CDP input events | `Shift+D` via `page.keyboard.press()` |
| Download wait | CDP `EventDownloadProgress` channel | `page.expect_download()` + `download.save_as()` |
| Download listener globale | `StartDownloadListener()` | Non necessario (Playwright gestisce internamente) |
| Parallismo metadata+download | 2 goroutines + errChan | `asyncio.gather()` |
| Tab locking | `muTabActivity.Lock()` | Non necessario (single-thread asyncio) |
| File naming | GUID come nome temporaneo | `download.suggested_filename` disponibile subito |
| Timeout management | `time.NewTimer()` + select | `asyncio.wait_for()` |
| Worker goroutines | Spostati in sync.py (passo 10) | Task asyncio in sync.py |

## Verifica

Questo modulo richiede browser per test completi. Test parziale delle utility:

```bash
cd web-gui && python -c "
import tempfile, os, zipfile
from datetime import datetime
from sync_engine.download import _make_out_dir, _handle_zip
from sync_engine.models import Session

# Test _make_out_dir
tmpdir = tempfile.mkdtemp()
s = Session(download_dir=tmpdir, download_dir_tmp=tmpdir+'/tmp', profile_dir='')
out = _make_out_dir(s, datetime(2025, 11, 13))
assert out == os.path.join(tmpdir, '2025', '11')
assert os.path.isdir(out)

# Test _handle_zip
zip_path = os.path.join(tmpdir, 'test.zip')
with zipfile.ZipFile(zip_path, 'w') as zf:
    zf.writestr('photo1.jpg', 'data1')
    zf.writestr('photo2.jpg', 'data2')

extracted = _handle_zip(zip_path, out)
assert len(extracted) == 2
assert not os.path.exists(zip_path)  # zip should be deleted
for f in extracted:
    assert os.path.exists(f)

import shutil
shutil.rmtree(tmpdir)
print('Download utility tests passed!')
"
```
