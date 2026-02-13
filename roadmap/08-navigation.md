# Passo 8: Portare Navigation (navigation.py)

## Obiettivo

Portare `gphotos-cdp/internal/navigation/navigation.go` (359 righe) in Python. Gestisce la navigazione nella pagina Google Photos: scrolling, navigazione tra foto, parsing URL, e serializzazione accesso tab.

## File da creare: `web-gui/sync_engine/navigation.py`

## Differenze chiave rispetto a Go

### Tab locking non necessario

In Go, multiple goroutines (workers) condividono lo stesso browser e devono serializzare l'accesso alla tab attiva con `muTabActivity` mutex. In Python con asyncio, tutto gira su un singolo event loop — le operazioni sono naturalmente serializzate. Il "tab lock" non serve.

Tuttavia, se si usano piu' pagine Playwright (una per worker), ogni worker ha la sua pagina indipendente e non c'e' conflitto.

### Navigation events non necessari

In Go, `ListenNavEvents` ascolta `EventNavigatedWithinDocument` per sapere quando una navigazione intra-pagina e' completata (navigazione tra foto usa URL fragments). In Playwright, possiamo usare `page.wait_for_url()` o `page.wait_for_load_state()`.

## Funzioni da portare

### FirstNav (navigation.go:38-63)

Logica:
1. Se album/user path specificato, naviga a `GPHOTOS_URL + userPath + albumPath`
2. Attendi body ready
3. Chiama `SetFirstItem()` per verificare che la pagina sia caricata
4. Logga location corrente

### SetFirstItem (navigation.go:69-117)

Logica:
1. Loop fino a 60 tentativi (30 secondi):
   - Premi freccia destra (ArrowRight)
   - Attendi 500ms
   - Leggi attributi dell'elemento attivo (`document.activeElement`)
   - Se ha `href` con pattern `/photo/{id}` → pagina caricata, prima foto trovata
2. Se timeout → errore con screenshot

### NavigateToPhoto (navigation.go:149-152)

Semplice: `page.goto(GPHOTOS_URL + userPath + albumPath + "/photo/" + imageId)`

### NavigateWithAction (navigation.go:155-192)

Navigazione con retry (fino a 5 tentativi), gestione errori HTTP, timeout.
In Playwright: `page.goto(url, timeout=timeout)` con try/except in loop.

### NavRight (navigation.go:195-200)

Premi freccia destra per passare alla foto successiva.

### GetScrollPosition (navigation.go:251-282)

Esegui JS per leggere posizione scroll:
```javascript
var main = [...document.querySelectorAll('{mainSel}')]
    .filter(x => x.querySelector('a[href*="/photo/"]') && getComputedStyle(x).visibility != 'hidden')[0];
return main ? (main.scrollTop+0.000001)/(main.scrollHeight-main.clientHeight+0.000001) : 0.0;
```

Selettore dipende da se e' un album o la libreria:
- Album: `c-wiz c-wiz c-wiz`
- Libreria: `[role="main"]`

### SetScrollPosition (navigation.go:230-248)

Esegui JS per impostare posizione scroll:
```javascript
var main = [...document.querySelectorAll('{mainSel}')].filter(...)[0];
main.scrollTo(0, main.scrollHeight * scrollTarget);
```

### ImageIdFromUrl (navigation.go:331-348)

Regex: estrai ID foto da URL tipo `./album/ABC/photo/XYZ123` o `./photo/XYZ123`

## Codice completo da scrivere

```python
"""Page navigation and scrolling for Google Photos.

Handles page loading, photo navigation, scroll position tracking,
and URL parsing.

Equivalent of Go navigation/navigation.go.
"""

import asyncio
import logging
import os
import re
from urllib.parse import urlparse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .models import GPHOTOS_URL, Session

logger = logging.getLogger(__name__)

TICK = 0.5  # seconds, same as Go's 500ms


async def first_nav(session: Session, page: Page) -> None:
    """Navigate to Google Photos and verify page is loaded.

    If an album or user path is set, navigates to that specific path.
    Then waits for the first photo to be visible.

    Equivalent of Go navigation.FirstNav().
    """
    logger.info("firstNav: navigating to Google Photos...")

    if session.user_path or session.album_path:
        url = GPHOTOS_URL + session.user_path + session.album_path
        logger.info("firstNav: navigating to album/user path: %s%s", session.user_path, session.album_path)
        await navigate_with_retry(page, url, timeout_ms=20000, retries=5)
        await page.wait_for_load_state("domcontentloaded")

    logger.info("firstNav: setting first item...")
    await set_first_item(session, page)
    logger.info("firstNav: first item set successfully")

    location = page.url
    logger.debug("location: %s", location)


async def set_first_item(session: Session, page: Page) -> None:
    """Wait for page to load by detecting the first photo element.

    Presses right arrow key until an element with a photo href becomes active.
    This confirms the page is loaded and ready for scrolling.

    Equivalent of Go navigation.SetFirstItem().
    """
    max_attempts = 60  # 60 * 500ms = 30 seconds
    logger.info("setFirstItem: waiting for page to load and find first photo...")

    for attempt in range(1, max_attempts + 1):
        logger.debug("setFirstItem: attempt %d/%d to find first item", attempt, max_attempts)

        await page.keyboard.press("ArrowRight")
        await asyncio.sleep(TICK)

        # Get attributes of the currently active element
        result = await page.evaluate("""
            (() => {
                const el = document.activeElement;
                if (!el) return null;
                const attrs = {};
                for (const attr of el.attributes) {
                    attrs[attr.name] = attr.value;
                }
                return attrs;
            })()
        """)

        if not result:
            await asyncio.sleep(TICK)
            continue

        href = result.get("href", "")
        if href:
            logger.debug("setFirstItem: checking href: %s", href)
            try:
                image_id = image_id_from_url(href)
                logger.info("setFirstItem: found first item: %s", image_id)
                logger.info("page loaded, most recent item in the feed is: %s", image_id)
                return
            except ValueError:
                logger.debug("setFirstItem: href is not a valid image URL")

        await asyncio.sleep(TICK)

    # Timeout
    await capture_screenshot_safe(page, os.path.join(session.download_dir, "setFirstItem-timeout"))
    raise RuntimeError("timeout waiting for first item to be found (page may not have loaded)")


async def navigate_to_photo(session: Session, page: Page, image_id: str) -> None:
    """Navigate to a specific photo page.

    Equivalent of Go navigation.NavigateToPhoto().
    """
    photo_url = GPHOTOS_URL + session.user_path + session.album_path + "/photo/" + image_id
    await navigate_with_retry(page, photo_url, timeout_ms=10000, retries=5)


async def navigate_with_retry(
    page: Page,
    url: str,
    timeout_ms: int = 10000,
    retries: int = 5,
) -> None:
    """Navigate to URL with retry logic.

    Equivalent of Go navigation.NavigateWithAction().
    """
    last_error = None
    for i in range(retries):
        try:
            response = await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            if response and response.status == 200:
                await page.wait_for_load_state("domcontentloaded")
                return
            elif response and response.status == 504:
                last_error = RuntimeError(f"HTTP 504 navigating to {url}")
                logger.warning("error navigating to %s: HTTP 504, will try again", url)
                await asyncio.sleep(0.1)
                continue
            elif response is None:
                # No response usually means in-page navigation
                return
            else:
                raise RuntimeError(f"Unexpected HTTP {response.status} navigating to {url}")
        except PlaywrightTimeout:
            last_error = RuntimeError(f"Timeout navigating to {url}")
            logger.warning("timeout navigating to %s, will try again (%d/%d)", url, i + 1, retries)
            await asyncio.sleep(0.1)
        except Exception as e:
            if "net::ERR_ABORTED" in str(e):
                last_error = e
                logger.warning("navigation aborted for %s, will try again", url)
                await asyncio.sleep(0.1)
                continue
            raise

    if last_error:
        raise last_error


async def nav_right(page: Page) -> None:
    """Navigate to the next photo by pressing right arrow.

    Equivalent of Go navigation.NavRight().
    """
    logger.debug("Navigating right")
    await page.keyboard.press("ArrowRight")
    # Small delay to let the page update
    await asyncio.sleep(0.05)


async def get_scroll_position(page: Page, album_id: str = "") -> float:
    """Get current scroll position as a fraction (0.0 to 1.0).

    Equivalent of Go navigation.GetScrollPosition().
    """
    main_sel = "c-wiz c-wiz c-wiz" if len(album_id) > 1 else '[role="main"]'

    for attempt in range(3):
        try:
            pos = await page.evaluate(f"""
                (function() {{
                    var main = [...document.querySelectorAll('{main_sel}')]
                        .filter(x => x.querySelector('a[href*="/photo/"]') && getComputedStyle(x).visibility != 'hidden')[0];
                    return main ? (main.scrollTop+0.000001)/(main.scrollHeight-main.clientHeight+0.000001) : 0.0;
                }})()
            """)
            return float(pos)
        except Exception as e:
            logger.warning("error getting scroll position (attempt %d): %s", attempt + 1, e)
            await asyncio.sleep(0.5)

    raise RuntimeError("Failed to get scroll position after 3 attempts")


async def set_scroll_position(page: Page, pos: float, album_id: str = "") -> None:
    """Set scroll position on the main scrollable element.

    Equivalent of Go navigation.SetScrollPosition().
    """
    main_sel = "c-wiz c-wiz c-wiz" if len(album_id) > 1 else '[role="main"]'

    await page.evaluate(f"""
        (function() {{
            var main = [...document.querySelectorAll('{main_sel}')]
                .filter(x => x.querySelector('a[href*="/photo/"]') && getComputedStyle(x).visibility != 'hidden')[0];
            const scrollTarget = {pos};
            main.scrollTo(0, main.scrollHeight * scrollTarget);
        }})();
    """)


def image_id_from_url(url: str) -> str:
    """Extract the image ID from a Google Photos URL.

    URL patterns:
    - ./photo/IMAGE_ID
    - ./album/ALBUM_ID/photo/IMAGE_ID
    - https://photos.google.com/.../photo/IMAGE_ID

    Equivalent of Go navigation.ImageIdFromUrl().

    Raises:
        ValueError: If no /photo/{id} pattern found
    """
    parsed = urlparse(url)
    path = parsed.path if parsed.path else url
    parts = [p for p in path.strip("/").split("/") if p]

    for i in range(len(parts) - 1):
        if parts[i] == "photo":
            return parts[i + 1]

    raise ValueError(f"Could not find /photo/{{imageId}} pattern in URL: {url}")


def get_photo_node_selector(session: Session) -> str:
    """Return CSS selector for photo link nodes.

    Equivalent of Go sync.GetPhotoNodeSelector().
    """
    return f'a[href^=".{session.album_path}/photo/"]'


def get_photo_url(session: Session, image_id: str) -> str:
    """Return full URL for a photo.

    Equivalent of Go sync.GetPhotoUrl().
    """
    return GPHOTOS_URL + session.user_path + session.album_path + "/photo/" + image_id


async def capture_screenshot_safe(page: Page, path: str) -> None:
    """Capture screenshot without raising on failure."""
    try:
        await page.screenshot(path=path + ".png")
    except Exception:
        pass


async def do_action_with_timeout(page: Page, coro, timeout_seconds: float):
    """Execute an async action with timeout.

    Equivalent of Go navigation.DoActionWithTimeout().
    """
    try:
        await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.debug("action timed out after %.1f seconds", timeout_seconds)
```

## Verifica

```bash
cd web-gui && python -c "
from sync_engine.navigation import image_id_from_url, get_photo_node_selector
from sync_engine.models import Session

# Test image_id_from_url
assert image_id_from_url('./photo/ABC123') == 'ABC123'
assert image_id_from_url('./album/XYZ/photo/ABC123') == 'ABC123'
assert image_id_from_url('https://photos.google.com/photo/ABC123') == 'ABC123'
assert image_id_from_url('/u/0/album/XYZ/photo/ABC123') == 'ABC123'

# Test errore
try:
    image_id_from_url('/no/photo/here')
    # Actually this should work because 'photo' is not in the parts
except ValueError:
    pass

try:
    image_id_from_url('/just/a/path/')
    assert False
except ValueError:
    pass

# Test photo node selector
s = Session(download_dir='', download_dir_tmp='', profile_dir='', album_path='/album/XYZ')
assert get_photo_node_selector(s) == 'a[href^=\"./album/XYZ/photo/\"]'

s2 = Session(download_dir='', download_dir_tmp='', profile_dir='')
assert get_photo_node_selector(s2) == 'a[href^=\"./photo/\"]'

print('All navigation tests passed!')
"
```
