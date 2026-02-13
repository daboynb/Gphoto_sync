# Passo 10: Portare Sync Orchestration (sync.py)

## Obiettivo

Portare `gphotos-cdp/internal/sync/sync.go` (382 righe) in Python. E' il cuore del sistema: il loop principale che scorre Google Photos, rileva nuove foto, e coordina i download worker.

## File da creare: `web-gui/sync_engine/sync.py`

## Logica principale: Resync (sync.go:38-291)

### Panoramica del loop

1. Trova tutti i nodi foto visibili nella pagina con CSS selector `a[href^="./photo/"]`
2. Per ogni nodo, estrai l'image ID dall'href
3. Controlla se l'ID e' gia' stato scaricato (via `.downloaded_ids.txt`)
4. Se e' nuovo, aggiungilo a un batch (Job)
5. Quando il batch e' pronto, mandalo ai worker
6. Dopo aver processato tutti i nodi visibili, scrolla per caricarne altri
7. Ripeti finche' non ci sono piu' nodi nuovi (retry fino a 5000)
8. Stima progresso tramite posizione dello scrollbar

### Dettagli critici dal Go

#### Creazione workers (sync.go:65-74)

```go
jobChan := make(chan types.Job)
resultChan := make(chan string, workersFlag)
errChan := make(chan error, workersFlag)
for i := 0; i < workersFlag; i++ {
    workerDownloadChan := make(chan types.NewDownload, 1)
    workerDownloadChanByFrameId.Store(
        download.DownloadWorker(s, i+1, jobChan, resultChan, errChan, workerDownloadChan, runFlag),
        workerDownloadChan,
    )
}
```

In Python: ogni worker e' un task asyncio con la sua pagina Playwright. I job vengono inviati tramite `asyncio.Queue`.

#### Nodo processing (sync.go:241-267)

```go
for i < len(nodes) {
    lastNode = nodes[i]
    i++; n++
    imageId = ImageIdFromUrl(lastNode.href)

    shouldDownload = IsNewItem(s, log, imageId, false)
    if !shouldDownload {
        if len(imageIds) > 0 { break }  // break batch on non-new item
        else { continue }
    }
    imageIds = append(imageIds, imageId)
}
```

NOTA IMPORTANTE: quando incontra un item gia' scaricato, se il batch corrente ha gia' items, lo invia. Questo crea batch di items **consecutivi** che i worker possono navigare con freccia destra.

#### Scrolling e retry (sync.go:158-239)

- Ogni 5 retry, prova scroll manuale (ArrowDown)
- Ogni 10 retry, aggiungi 1 secondo di pausa extra
- Stop dopo 5000 retry o 100 retry se pochi items stimati
- Scroll: focus sull'ultimo nodo processato con `dom.Focus().WithNodeID(lastNode.NodeID)`

In Playwright, non abbiamo NodeID. Alternativa: `element.scroll_into_view_if_needed()` o `page.evaluate()` per scroll.

#### Progress logger (sync.go:114-156)

Goroutine separata che logga ogni 60 secondi:
- Items scaricati, in coda
- Progresso percentuale
- Tempo stimato rimanente
- Panic se nessun progresso per 20 minuti

#### Job channel routing (sync.go:77-112)

In Go, i download CDP events vengono ruotati al worker corretto tramite `TargetId` (frame ID della tab del worker). In Playwright, ogni worker ha la sua pagina con il suo event handler, quindi il routing non serve.

### IsNewItem (sync.go:294-310)

```go
func IsNewItem(s, log, imageId, markFound) (bool, error) {
    if _, exists := s.FoundItems.Load(imageId); exists { return false }
    isNew := !s.DownloadedIds.Has(imageId)
    if markFound || !isNew { s.FoundItems.Store(imageId) }
    return isNew
}
```

### CheckForRemovedFiles (sync.go:313-366)

Dopo il sync, verifica se ci sono foto locali non trovate su Google Photos. Per ogni ID locale non trovato durante lo scan:
1. Fai fetch HTTP dello URL della foto
2. Se 404 → foto eliminata, aggiungi a `.removed`
3. Se 200 → foto ancora presente (forse nel cestino)

## Codice completo da scrivere

```python
"""Sync orchestration: photo detection, scrolling, and worker coordination.

Main loop that scrolls through Google Photos, detects new photos,
and dispatches download jobs to worker tasks.

Equivalent of Go sync/sync.go.
"""

import asyncio
import logging
import math
import os
import time as time_module
from typing import Optional

from playwright.async_api import Page, BrowserContext

from .download import download_and_process_item, StillProcessingError
from .models import GPHOTOS_URL, Job, Session
from .navigation import (
    get_photo_node_selector,
    get_photo_url,
    get_scroll_position,
    set_scroll_position,
    image_id_from_url,
    navigate_to_photo,
    navigate_with_retry,
    nav_right,
)

logger = logging.getLogger(__name__)


async def resync(
    session: Session,
    page: Page,
    workers_count: int,
    album_id: str = "",
    run_flag: str = "",
) -> None:
    """Main sync loop: detect photos, scroll, and download new ones.

    Equivalent of Go sync.Resync().
    """
    photo_selector = get_photo_node_selector(session)
    logger.debug("photo node selector: %s", photo_selector)

    # Find initial nodes
    nodes = await _get_photo_nodes(page, photo_selector)
    if not nodes:
        logger.info("no photos to sync")
        return

    # Setup worker pool
    job_queue: asyncio.Queue[Optional[Job]] = asyncio.Queue()
    result_queue: asyncio.Queue[str] = asyncio.Queue()
    error_event = asyncio.Event()
    worker_error: Optional[Exception] = None

    # Create worker pages (one per worker)
    worker_tasks = []
    for worker_id in range(1, workers_count + 1):
        task = asyncio.create_task(
            _download_worker(
                session, worker_id, job_queue, result_queue,
                error_event, run_flag,
            )
        )
        worker_tasks.append(task)

    # Start progress logger
    progress_task = asyncio.create_task(
        _progress_logger(session, result_queue, error_event)
    )

    # Main sync loop
    try:
        await _sync_loop(
            session, page, nodes, photo_selector,
            job_queue, result_queue, error_event,
            album_id,
        )
    finally:
        # Signal workers to stop
        for _ in worker_tasks:
            await job_queue.put(None)  # Sentinel value

        # Wait for workers to finish
        await asyncio.gather(*worker_tasks, return_exceptions=True)
        progress_task.cancel()

    # Log final stats
    logger.info(
        "in total: synced items, downloaded %d",
        len(session.downloaded_items),
    )


async def _sync_loop(
    session: Session,
    page: Page,
    initial_nodes: list[dict],
    photo_selector: str,
    job_queue: asyncio.Queue,
    result_queue: asyncio.Queue,
    error_event: asyncio.Event,
    album_id: str,
) -> None:
    """Core loop: scroll through photos and queue new ones for download.

    Process flow:
    1. Extract image IDs from visible photo nodes
    2. Check each against downloaded_ids
    3. Batch consecutive new items into Jobs
    4. Send Jobs to workers via queue
    5. Scroll to load more photos
    6. Repeat until no new items found
    """
    nodes = initial_nodes
    node_index = 0         # next node to process
    total_processed = 0    # total nodes processed
    new_items_count = 0    # items queued for download
    retries = 0            # consecutive failed attempts to find new items
    slider_pos = 0.0
    estimated_remaining = 1000
    last_processed_href = None

    while True:
        # Check for worker errors
        if error_event.is_set():
            raise RuntimeError("Worker encountered a fatal error")

        # Retry management (same logic as Go)
        if retries % 5 == 0 and retries > 0:
            logger.debug("stuck, manually scrolling down")
            await page.keyboard.press("ArrowDown")
            await asyncio.sleep(0.2)

        if retries > 0 and retries % 10 == 0:
            await asyncio.sleep(1)  # slow loading, extra wait

        # Check exit conditions
        if retries > 5000 or (retries > 100 and estimated_remaining <= 50):
            break

        # Get scroll position
        try:
            slider_pos = await get_scroll_position(page, album_id)
        except Exception as e:
            logger.warning("error getting scroll position: %s, recovering...", e)
            url = GPHOTOS_URL + session.user_path + session.album_path
            await navigate_with_retry(page, url, timeout_ms=20000, retries=5)
            await page.wait_for_load_state("domcontentloaded")
            await set_scroll_position(page, slider_pos, album_id)

        logger.debug("slider position: %.2f%%", slider_pos * 100)

        # Estimate remaining items
        if total_processed < 5 or slider_pos < 0.001:
            estimated_remaining = 50
        else:
            estimated_remaining = int(math.floor((1 / slider_pos - 1) * (total_processed + 30)))

        # Need to load more nodes?
        if total_processed > 0 and node_index >= len(nodes):
            if retries == 0 and last_processed_href:
                # Scroll to last processed node
                logger.debug("scrolling to last processed node")
                await page.evaluate(f"""
                    (() => {{
                        const el = document.querySelector('a[href="{last_processed_href}"]');
                        if (el) el.focus();
                    }})()
                """)

            # Re-query all nodes
            nodes = await _get_photo_nodes(page, photo_selector)
            logger.debug("found %d items, checking for new ones", len(nodes))

            # Skip already-processed nodes
            if last_processed_href:
                new_start = 0
                for idx, node in enumerate(nodes):
                    if node.get("href") == last_processed_href:
                        new_start = idx + 1
                        break
                nodes = nodes[new_start:]

            if not nodes:
                retries += 1
                continue

            logger.debug("processing %d nodes that haven't been processed", len(nodes))
            retries = 0
            node_index = 0

        # Process current batch of nodes
        image_ids = []
        while node_index < len(nodes):
            node = nodes[node_index]
            node_index += 1
            total_processed += 1
            last_processed_href = node.get("href", "")

            try:
                image_id = image_id_from_url(last_processed_href)
            except ValueError as e:
                logger.warning("error getting image id from URL: %s", e)
                continue

            should_download = _is_new_item(session, image_id)
            if not should_download:
                if image_ids:
                    break  # End current batch on non-new item
                continue
            image_ids.append(image_id)

        # Queue job if we found new items
        if image_ids:
            logger.debug("adding %d items to queue", len(image_ids))
            new_items_count += len(image_ids)
            await job_queue.put(Job(image_ids=image_ids))


async def _download_worker(
    session: Session,
    worker_id: int,
    job_queue: asyncio.Queue,
    result_queue: asyncio.Queue,
    error_event: asyncio.Event,
    run_flag: str,
) -> None:
    """Worker task that processes download jobs.

    Each worker creates its own browser page for independent navigation.

    Equivalent of Go download.DownloadWorker().
    """
    wlog = logging.getLogger(f"{__name__}.worker{worker_id}")
    wlog.info("worker %d starting", worker_id)

    # Create a new page for this worker
    page = await session.context.new_page()

    try:
        while True:
            job = await job_queue.get()
            if job is None:
                wlog.debug("worker %d received shutdown signal", worker_id)
                break

            wlog.debug("worker %d received batch of %d items", worker_id, len(job.image_ids))

            is_consecutive = False
            for i, image_id in enumerate(job.image_ids):
                try:
                    # Navigate to photo
                    expected_url = (
                        GPHOTOS_URL + session.user_path + session.album_path
                        + "/photo/" + image_id
                    )
                    current_url = page.url

                    if is_consecutive and current_url != expected_url and current_url.startswith(GPHOTOS_URL):
                        # Try right arrow for consecutive items
                        wlog.debug("[%s] navigating right", image_id)
                        await nav_right(page)
                        await asyncio.sleep(0.01)
                        if page.url != expected_url:
                            wlog.debug("[%s] right arrow didn't reach target, navigating directly", image_id)
                            await navigate_to_photo(session, page, image_id)
                    elif page.url != expected_url:
                        await navigate_to_photo(session, page, image_id)

                    is_consecutive = True
                    await asyncio.sleep(0.002)

                    # Download and process
                    await download_and_process_item(session, page, image_id, run_flag)

                    session.downloaded_items.add(image_id)
                    await result_queue.put(image_id)

                except StillProcessingError:
                    wlog.info("[%s] skipping generated highlight video", image_id)
                    is_consecutive = False
                    session.skipped_count += 1
                except Exception as e:
                    wlog.error("[%s] worker %d error: %s", image_id, worker_id, e)
                    error_event.set()
                    return

            wlog.debug("worker %d finished batch", worker_id)
    finally:
        await page.close()
        wlog.info("worker %d stopped", worker_id)


async def _progress_logger(
    session: Session,
    result_queue: asyncio.Queue,
    error_event: asyncio.Event,
) -> None:
    """Log sync progress every 60 seconds.

    Equivalent of Go's progress logger goroutine.
    """
    start = time_module.time()
    last_count = 0
    stale_iterations = 0

    while not error_event.is_set():
        await asyncio.sleep(60)

        downloaded = len(session.downloaded_items)
        elapsed = time_module.time() - start

        if downloaded == last_count:
            stale_iterations += 1
            if stale_iterations > 20:
                logger.error("no new items processed for 20 minutes, stopping")
                error_event.set()
                return
        else:
            stale_iterations = 0
        last_count = downloaded

        logger.info(
            "progress: downloaded %d items in %.0f seconds (skipped %d)",
            downloaded, elapsed, session.skipped_count,
        )


def _is_new_item(session: Session, image_id: str) -> bool:
    """Check if an item needs to be downloaded.

    Equivalent of Go sync.IsNewItem().
    """
    if image_id in session.found_items:
        return False

    is_new = not session.downloaded_ids.has(image_id)
    if not is_new:
        logger.debug("[%s] skipping, already downloaded", image_id)
        session.found_items.add(image_id)

    return is_new


async def check_for_removed_files(
    session: Session,
    page: Page,
    check_removed: bool = False,
) -> None:
    """Check for locally stored photos that were deleted from Google Photos.

    Equivalent of Go sync.CheckForRemovedFiles().
    """
    if not check_removed:
        return

    logger.info("checking for removed files")
    deleted = []

    for item_id in session.existing_items:
        if item_id != "tmp" and item_id not in session.found_items:
            deleted.append(item_id)

    if not deleted:
        return

    logger.info(
        "found %d local photos not found in sync, verifying on Google Photos",
        len(deleted),
    )

    confirmed_deleted = []
    for item_id in deleted:
        photo_url = get_photo_url(session, item_id)
        try:
            status = await page.evaluate(f"""
                new Promise((res) => fetch('{photo_url}').then(x => res(x.status)))
            """)
            if status == 404:
                logger.debug("[%s] confirmed deleted from Google Photos", item_id)
                confirmed_deleted.append(item_id)
            elif status == 200:
                logger.debug("[%s] still present on Google Photos (maybe in trash)", item_id)
            else:
                logger.warning("[%s] unexpected HTTP status: %d", item_id, status)
        except Exception as e:
            logger.warning("[%s] error checking: %s, stopping removed check", item_id, e)
            break

    if confirmed_deleted:
        removed_file = os.path.join(session.download_dir, ".removed")
        with open(removed_file, "w") as f:
            f.write("\n".join(confirmed_deleted))
        logger.info("saved %d removed photo IDs to .removed", len(confirmed_deleted))


async def _get_photo_nodes(page: Page, selector: str) -> list[dict]:
    """Query all photo link nodes and return their attributes.

    Returns list of dicts with 'href' key.
    """
    return await page.evaluate(f"""
        [...document.querySelectorAll('{selector}')].map(el => ({{
            href: el.getAttribute('href')
        }}))
    """)
```

## Differenze architetturali rispetto al Go

| Go | Python | Motivazione |
|---|---|---|
| `chan Job` (jobChan) | `asyncio.Queue[Job]` | Equivalente async |
| `chan string` (resultChan) | `asyncio.Queue[str]` | Equivalente async |
| `chan error` (errChan) | `asyncio.Event` (error_event) | Segnala errore fatale |
| N goroutines | N asyncio tasks | Un task per worker |
| `sync.Map` per download routing | Non necessario | Ogni worker ha la sua pagina |
| `dom.Focus().WithNodeID()` | `el.focus()` via JS evaluate | Playwright non ha NodeID |
| `chromedp.Nodes()` per query | `page.evaluate()` con querySelectorAll | Ritorna attributi come dict |
| `atomic.AddInt64` per contatori | Accesso diretto (single thread) | asyncio e' single-threaded |
| `target.ActivateTarget()` | Non necessario | Ogni worker ha pagina propria |

## Verifica

Test parziale senza browser:

```bash
cd web-gui && python -c "
from sync_engine.sync import _is_new_item
from sync_engine.models import Session
from sync_engine.downloaded_ids import DownloadedIdsManager
import tempfile

tmpdir = tempfile.mkdtemp()
mgr = DownloadedIdsManager(tmpdir)
mgr.add('existing_id')

s = Session(
    download_dir=tmpdir,
    download_dir_tmp=tmpdir+'/tmp',
    profile_dir='',
    downloaded_ids=mgr,
)

# New item
assert _is_new_item(s, 'new_id') == True

# Already downloaded
assert _is_new_item(s, 'existing_id') == False

# Already found in this session
s.found_items.add('found_id')
assert _is_new_item(s, 'found_id') == False

import shutil
shutil.rmtree(tmpdir)
print('Sync utility tests passed!')
"
```
