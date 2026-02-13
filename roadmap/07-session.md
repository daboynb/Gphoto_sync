# Passo 7: Portare Session Management (session.py)

## Obiettivo

Portare `gphotos-cdp/internal/session/session.go` (600 righe) in Python usando Playwright. Questo e' il modulo piu' critico: gestisce avvio Chrome, autenticazione, rilevamento lingua, e auto-estrazione configurazione mesi.

## File da creare: `web-gui/sync_engine/session.py`

## Mappatura funzioni Go -> Python

| Go | Python | Note |
|---|---|---|
| `NewSession()` | `create_session()` | Crea directory, inizializza DownloadedIdsManager |
| `NewWindow()` | `launch_browser()` | Avvia Chrome con Playwright invece di chromedp |
| `Login()` | `login()` | Polling URL per rilevare auth completata |
| `Shutdown()` | `shutdown()` | Chiude browser |
| `CleanDownloadDir()` | `clean_download_dir()` | Pulisce tmp |
| `GetLocale()` | `get_locale()` | JS evaluation nel browser |
| `CheckLanguage()` | `check_language()` | Verifica supporto lingua + auto-extract |
| `AutoExtractLanguageConfig()` | `auto_extract_language_config()` | JS per estrarre nomi mesi |
| `CaptureScreenshot()` | `capture_screenshot()` | Screenshot debug |
| `SetContextData()/GetContextData()` | Non necessario | Playwright non ha context values |

## Differenze architetturali chiave

### chromedp vs Playwright

| chromedp (Go) | Playwright (Python) |
|---|---|
| `chromedp.NewExecAllocator()` | `playwright.chromium.launch_persistent_context()` |
| `chromedp.NewContext()` per tab | `context.new_page()` per tab |
| `chromedp.Run(ctx, actions...)` | `await page.evaluate(js)`, `await page.goto(url)`, etc. |
| `browser.SetDownloadBehavior()` | Context option `accept_downloads=True` |
| `chromedp.ListenBrowser()` per download events | `page.on("download", handler)` |
| Headless: flag Chrome | `headless=True` nel launch |
| User data dir: flag Chrome | `user_data_dir` param di `launch_persistent_context` |

### Autenticazione (Login)

Il flusso Go (session.go:223-343) fa polling dell'URL ogni 2 secondi per 2 minuti:

1. Naviga a `https://photos.google.com/login`
2. Loop:
   - Leggi URL corrente
   - Se inizia con `https://photos.google.com` → autenticato!
   - Se contiene `signinchooser` → click account selector
   - Se contiene `signin/challenge/dp` → attendi approvazione da altro device
   - Se contiene `signin/shadowdisambiguate` → click profilo (GPHOTOS_PROFILE_INDEX)
   - Se contiene `signin/confirmidentifier` → click Next
   - Se contiene `signin/rejected` → errore fatale
   - Se contiene `signin/speedbump/passkeyenrollment` → click "Not now"
   - Se GPHOTOS_EMAIL env → compila campo email
   - Se GPHOTOS_PASSWORD env → compila campo password
   - Se headless e non autenticato → errore fatale con screenshot
   - Se timeout 2 min → errore
3. Log "successfully authenticated"

### Chrome flags (NewWindow)

Go (session.go:126-141) aggiunge queste flags:
```
--disable-blink-features=AutomationControlled
--lang=en-US,en
--accept-lang=en-US,en
--window-size=1920,1080
--enable-logging
--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...
```

Playwright equivalente: passare come `args` a `launch_persistent_context()`.

### Download behavior (NewWindow)

Go (session.go:154-162):
```go
browser.SetDownloadBehavior(browser.SetDownloadBehaviorBehaviorAllowAndName).
    WithDownloadPath(s.DownloadDirTmp).
    WithEventsEnabled(true)
```

Playwright: `accept_downloads=True` + gestione evento `download`.

### Auto-extract language config (session.go:442-525)

1. Attendi 2 secondi
2. Trova primo `[aria-label]` che contiene ` - `
3. Rileva pattern data nel label:
   - `(\d{1,2})\.\s+(\w+)\.\s+(\d{4}),` → "day. month. year"
   - `(\w+)\s+(\d{1,2}),\s+(\d{4}),` → "month day, year"
   - `(\d{1,2})\s+(\w+)\s+(\d{4}),` → "day month year"
4. Genera mesi abbreviati via JS: `new Date(2024, i, 1).toLocaleDateString(lang, {month: 'short'})`
5. Ritorna MonthConfig

## Codice completo da scrivere

```python
"""Chrome session management using Playwright.

Handles browser launch, authentication, locale detection,
and language auto-extraction.

Equivalent of Go session/session.go.
"""

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .config import months_config, page_language, save_months_config
from .config import months_config as _mc, page_language as _pl
from .downloaded_ids import DownloadedIdsManager
from .models import GPHOTOS_URL, MonthConfig, Session

logger = logging.getLogger(__name__)


async def create_session(
    download_dir: str,
    profile_dir: str,
    album_id: str = "",
) -> Session:
    """Create a new sync session (directories, ID manager).

    Equivalent of Go session.NewSession().
    """
    # Parse album path
    album_path = ""
    user_path = ""
    if album_id:
        if "/" in album_id:
            # Full path provided
            album_path = "/" + album_id
            album_id = album_id.rsplit("/", 1)[-1]
        else:
            album_path = "/album/" + album_id

    if album_path.startswith("/u/"):
        slash_idx = album_path[3:].find("/")
        if slash_idx == -1:
            user_path = album_path
            album_path = ""
        else:
            user_path = album_path[: slash_idx + 3]
            album_path = album_path[slash_idx + 3:]

    logger.info("syncing files at root dir %s%s%s", GPHOTOS_URL, user_path, album_path)

    # Create directories
    os.makedirs(profile_dir, mode=0o700, exist_ok=True)
    if not download_dir:
        download_dir = os.path.join(os.environ.get("HOME", "/tmp"), "Downloads", "gphotos-cdp")
    os.makedirs(download_dir, mode=0o700, exist_ok=True)

    download_dir_tmp = os.path.join(download_dir, "tmp")
    os.makedirs(download_dir_tmp, mode=0o700, exist_ok=True)

    # Load existing directory entries (legacy, for CheckForRemovedFiles)
    existing_items = set()
    if os.path.isdir(download_dir):
        for entry in os.scandir(download_dir):
            if entry.is_dir() and entry.name != "tmp":
                existing_items.add(entry.name)

    # Initialize downloaded IDs manager
    downloaded_ids = DownloadedIdsManager(download_dir)
    logger.info("Loaded %d previously downloaded items", downloaded_ids.count())

    return Session(
        download_dir=download_dir,
        download_dir_tmp=download_dir_tmp,
        profile_dir=profile_dir,
        user_path=user_path,
        album_path=album_path,
        downloaded_ids=downloaded_ids,
        existing_items=existing_items,
    )


async def launch_browser(
    session: Session,
    headless: bool = True,
) -> tuple:
    """Launch Chrome with Playwright using persistent context.

    Returns (playwright_instance, browser_context, page).

    Equivalent of Go session.NewWindow().
    """
    logger.info("starting Chrome browser")

    pw = await async_playwright().start()

    # Chrome args matching Go's chromedp flags
    chrome_args = [
        "--disable-blink-features=AutomationControlled",
        "--lang=en-US,en",
        "--accept-lang=en-US,en",
        "--window-size=1920,1080",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]

    context = await pw.chromium.launch_persistent_context(
        user_data_dir=session.profile_dir,
        headless=headless,
        accept_downloads=True,
        downloads_path=session.download_dir_tmp,
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/111.0.0.0 Safari/537.36"
        ),
        args=chrome_args,
        chromium_sandbox=False,
    )

    # Get or create a page
    if context.pages:
        page = context.pages[0]
    else:
        page = await context.new_page()

    # Log browser version
    version = await page.evaluate("navigator.userAgent")
    logger.info("Browser user agent: %s", version)

    session.context = context
    session.page = page

    return pw, context, page


async def login(
    session: Session,
    page: Page,
    headless: bool = True,
    timeout_seconds: int = 120,
) -> None:
    """Navigate to Google Photos and wait for authentication.

    In headless mode, uses GPHOTOS_EMAIL/GPHOTOS_PASSWORD env vars
    or fails if not authenticated via saved cookies.

    Equivalent of Go session.Login().
    """
    logger.info("starting authentication...")
    await page.goto("https://photos.google.com/login", wait_until="domcontentloaded")

    tick = 2  # seconds between checks
    deadline = asyncio.get_event_loop().time() + timeout_seconds

    logger.info("waiting for authentication to complete...")

    while True:
        location = page.url
        logger.debug("current URL: %s", location)

        # Success: redirected to Google Photos
        if location.startswith(GPHOTOS_URL):
            logger.info("authentication successful!")
            return

        # Account chooser
        if "signinchooser" in location:
            logger.info("detected account chooser, selecting account...")
            user_index = 0
            if session.user_path:
                try:
                    user_index = int(session.user_path[2:])
                except ValueError:
                    pass
            await page.evaluate(
                f'document.querySelector(\'[data-authuser][data-item-index="{user_index}"]\')?.click()'
            )
            await asyncio.sleep(tick)
            continue

        # Device approval challenge
        if "signin/challenge/dp" in location:
            logger.info("waiting for user to approve login with other device")
            await asyncio.sleep(tick)
            continue

        # Workspace/private account selector
        if "signin/shadowdisambiguate" in location:
            profile_index = os.environ.get("GPHOTOS_PROFILE_INDEX", "0")
            await page.click(f'div[data-profileindex="{profile_index}"]')
            await asyncio.sleep(tick)
            continue

        # Confirm identifier
        if "signin/confirmidentifier" in location:
            await page.click("div#identifierNext button")
            await asyncio.sleep(tick)
            continue

        # Rejected
        if "signin/rejected" in location:
            logger.error("Google rejected automated login")
            raise RuntimeError("Google rejected automated login")

        # Passkey enrollment skip
        if "signin/speedbump/passkeyenrollment" in location:
            try:
                await page.click('//button//span[contains(text(), "Not now")]')
            except Exception:
                pass
            await asyncio.sleep(tick)
            continue

        # Auto-fill email
        email = os.environ.get("GPHOTOS_EMAIL", "")
        if email:
            email_el = await page.query_selector("#identifierId:not([type=hidden])")
            if email_el:
                logger.info("logging in with user email: %s", email)
                await email_el.fill(email)
                await page.keyboard.press("Enter")
                await asyncio.sleep(tick)
                continue

        # Auto-fill password
        password = os.environ.get("GPHOTOS_PASSWORD", "")
        if password:
            pwd_el = await page.query_selector("input[name=Passwd]")
            if pwd_el:
                logger.info("logging in with user password")
                await pwd_el.fill(password)
                await page.keyboard.press("Enter")
                await asyncio.sleep(tick * 3)
                continue

        # Headless mode failure
        if headless:
            await capture_screenshot(page, os.path.join(session.download_dir, "error"))
            raise RuntimeError(
                f"authentication not possible in headless mode, see error.png (URL={location})"
            )

        # Timeout
        if asyncio.get_event_loop().time() > deadline:
            raise RuntimeError("timeout waiting for authentication")

        logger.debug("not yet authenticated, at: %s", location)
        await asyncio.sleep(tick)

    logger.info("successfully authenticated")


async def get_locale(page: Page) -> str:
    """Detect the locale of the Google Photos page.

    Reads <html lang="..."> attribute.

    Equivalent of Go session.GetLocale().
    """
    import sync_engine.config as cfg

    locale = await page.evaluate("""
        (function() {
            const htmlLang = document.documentElement.lang;
            if (htmlLang) return htmlLang;

            const metaLang = document.querySelector('meta[property="og:locale"]');
            if (metaLang) return metaLang.content;

            const scripts = document.getElementsByTagName('script');
            for (const script of scripts) {
                if (script.text && script.text.includes('"locale"')) {
                    const match = script.text.match(/"locale":\\s*"([^"]+)"/);
                    if (match) return match[1];
                }
            }
            return "unknown";
        })()
    """)

    logger.info("detected page locale: %s", locale)
    cfg.page_language = locale
    return locale


async def check_language(page: Page) -> None:
    """Check if detected language is supported, auto-extract if needed.

    Equivalent of Go session.CheckLanguage().
    """
    import sync_engine.config as cfg

    html_lang = await page.evaluate('document.documentElement.lang || "unknown"')

    try:
        browser_langs = await page.evaluate(
            "(navigator.languages || [navigator.language]).join(',')"
        )
    except Exception:
        browser_langs = "unknown"

    if html_lang in ("unknown", ""):
        logger.fatal(
            "Could not detect page language (detected: %s) | Browser preferences: %s",
            html_lang, browser_langs,
        )
        raise RuntimeError(f"Could not detect page language: {html_lang}")

    if html_lang in cfg.months_config:
        logger.info(
            "Page language: %s (supported) | Browser preferences: %s",
            html_lang, browser_langs,
        )
        return

    # Language not in config - auto-extract
    logger.warning(
        "Page language: %s (NOT in months-config.json) | Browser preferences: %s",
        html_lang, browser_langs,
    )
    logger.info("Attempting to auto-extract language configuration for: %s", html_lang)

    month_cfg = await auto_extract_language_config(page, html_lang)
    cfg.months_config[html_lang] = month_cfg
    cfg.page_language = html_lang

    try:
        save_months_config()
    except Exception as e:
        logger.error("Failed to save months-config.json: %s (continuing with in-memory config)", e)

    logger.info("Successfully auto-configured language: %s", html_lang)


async def auto_extract_language_config(page: Page, lang: str) -> MonthConfig:
    """Extract language config from Google Photos page.

    Uses JavaScript to:
    1. Find an aria-label with date metadata
    2. Detect date format pattern
    3. Generate abbreviated month names

    Equivalent of Go session.AutoExtractLanguageConfig().
    """
    logger.info("Auto-extracting language configuration for: %s", lang)

    await asyncio.sleep(2)

    # Extract metadata label
    photo_info_label = await page.evaluate("""
        (function() {
            let labels = [...document.querySelectorAll('[aria-label]')]
                .map(e => e.getAttribute('aria-label'))
                .filter(l => l && l.includes(' - '));
            return labels.length > 0 ? labels[0] : '';
        })()
    """)

    if not photo_info_label:
        raise RuntimeError("Could not extract metadata format from page")

    logger.debug("Extracted metadata format: %s", photo_info_label)

    # Detect date format
    day_month_year_dot = re.compile(r"(\d{1,2})\.\s+(\w+)\.\s+(\d{4}),")
    month_day_year = re.compile(r"(\w+)\s+(\d{1,2}),\s+(\d{4}),")
    day_month_year = re.compile(r"(\d{1,2})\s+(\w+)\s+(\d{4}),")

    if day_month_year_dot.search(photo_info_label):
        date_format = "day. month. year"
    elif month_day_year.search(photo_info_label):
        date_format = "month day, year"
    elif day_month_year.search(photo_info_label):
        date_format = "day month year"
    else:
        raise RuntimeError(f"Unknown date format in metadata: {photo_info_label}")

    # Generate months using JavaScript
    import json
    months_json = await page.evaluate(f"""
        (function() {{
            const months = [];
            const pageLang = '{lang}';
            for (let i = 0; i < 12; i++) {{
                const date = new Date(2024, i, 1);
                months.push(date.toLocaleDateString(pageLang, {{ month: 'short' }}).replace(/\\./g, ''));
            }}
            return JSON.stringify(months);
        }})()
    """)

    months = json.loads(months_json)
    logger.info("Auto-extracted config for %s: months=%s, format=%s", lang, months, date_format)

    return MonthConfig(
        months=months,
        metadata_format=photo_info_label,
        date_format=date_format,
    )


def clean_download_dir(session: Session) -> None:
    """Remove all files (not directories) from the tmp download directory.

    Equivalent of Go session.CleanDownloadDir().
    """
    if not session.download_dir_tmp:
        return
    if not os.path.isdir(session.download_dir_tmp):
        return
    for entry in os.scandir(session.download_dir_tmp):
        if entry.is_file():
            os.remove(entry.path)


async def capture_screenshot(page: Page, file_path: str) -> None:
    """Save screenshot and HTML dump for debugging.

    Equivalent of Go session.CaptureScreenshot().
    """
    try:
        await page.screenshot(path=file_path + ".png")
        logger.debug("saved screenshot to %s.png", file_path)
    except Exception as e:
        logger.error("failed to capture screenshot: %s", e)

    try:
        html = await page.content()
        with open(file_path + ".html", "w") as f:
            f.write(html)
    except Exception as e:
        logger.error("failed to save HTML: %s", e)


async def shutdown(session: Session, pw=None) -> None:
    """Close browser and cleanup.

    Equivalent of Go session.Shutdown().
    """
    if session.context:
        await session.context.close()
    if pw:
        await pw.stop()
```

## Note importanti

### Playwright persistent context vs chromedp

chromedp usa `UserDataDir` per persistere i cookie. Playwright ha `launch_persistent_context()` che fa esattamente la stessa cosa. I cookie Chrome vengono salvati in `{profile_dir}/Default/Cookies` come prima.

### Download handling

In Go, i download sono gestiti via CDP events (`EventDownloadWillBegin`, `EventDownloadProgress`). In Playwright, usiamo `page.on("download", handler)` che e' molto piu' semplice. I file vengono salvati con `download.save_as(path)`. Questo cambio impatta il passo 09 (download.py).

### Thread safety

In Go servono mutex perche' goroutines sono parallele. In Python con asyncio tutto gira su un singolo thread, quindi non servono lock per le strutture dati condivise (set, dict).

## Verifica

Questo modulo richiede Playwright installato. Test di base senza browser:

```bash
cd web-gui && python -c "
import asyncio
from sync_engine.session import create_session, clean_download_dir
from sync_engine.models import GPHOTOS_URL

async def test():
    import tempfile
    tmpdir = tempfile.mkdtemp()
    s = await create_session(
        download_dir=tmpdir + '/dl',
        profile_dir=tmpdir + '/profile',
    )
    assert s.download_dir == tmpdir + '/dl'
    assert s.profile_dir == tmpdir + '/profile'
    assert s.downloaded_ids is not None
    assert s.album_path == ''

    # Test album path parsing
    s2 = await create_session(
        download_dir=tmpdir + '/dl2',
        profile_dir=tmpdir + '/profile2',
        album_id='ABC123',
    )
    assert s2.album_path == '/album/ABC123'

    clean_download_dir(s)

    import shutil
    shutil.rmtree(tmpdir)
    print('Session creation tests passed!')

asyncio.run(test())
"
```
