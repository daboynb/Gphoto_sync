# Google Photos Sync

**This is a beta, expect some bugs!**

**It supports only EN/ITA accounts right now!**

Automatically download all your photos from Google Photos using Docker Compose with an intuitive Web GUI for managing multiple accounts.

## Quick Start (Web GUI)

### 1. Start Web GUI

```bash
git clone <this-repo>
cd Gphoto_sync
docker build -t gphotos-sync:latest .
docker compose up -d
```

### 2. Open Web Interface

Open **http://localhost:8080** in your browser

### 3. Create and Configure Profile

1. Click **"Create New Profile"**
2. Enter a name (e.g., "Family Photos", "Work Account")
3. Click **"Authenticate"** → VNC opens at http://localhost:6080
4. In VNC, double-click `open-chrome.sh` and login to Google Photos
5. Return to Web GUI and click **"Stop VNC & Save"**
6. Configure sync settings
7. Click **"Create Docker Compose"**

Your profile will start automatically and begin syncing!

---

## How It Works

This tool uses **Chrome DevTools Protocol (CDP)** instead of Google Photos API:

1. **Manual Authentication**: Login once via VNC browser, Chrome saves session cookies
2. **Automated Browsing**: Chrome DevTools Protocol controls headless Chrome with saved credentials
3. **DOM Scraping**: Uses `document.querySelectorAll()` to find photos, reads `aria-label` for metadata
4. **Keyboard Shortcuts**: Triggers downloads via `Shift+D` shortcut (faster than menu clicking)
5. **Download Interception**: CDP monitors `browser.EventDownloadProgress` for original quality files

---

## Configuration Options (Web GUI)

### Cron Schedule
**When to run automatic syncs**

Common patterns:
- `0 3 * * *` - Daily at 3 AM (default)
- `0 */6 * * *` - Every 6 hours
- `0 0 * * 0` - Every Sunday at midnight
- `*/30 * * * *` - Every 30 minutes

Format: `minute hour day month weekday`

### Run on Startup
**Sync immediately when container starts**

- ✅ **Enabled**: Runs sync on container startup, then follows cron schedule
- ❌ **Disabled**: Only syncs according to cron schedule

### Log Level
**Amount of detail in logs**

- `error` - Only critical errors
- `warn` - Errors and warnings
- `info` - Normal operation logs (recommended)
- `debug` - Detailed debugging information

### Parallel Downloads (Workers)
**Number of concurrent downloads**

- Range: 1-20 workers
- Default: 6 workers
- More workers = faster sync, but higher CPU/memory usage
- Recommended: 4-8 for most systems

### Albums
**Which albums to sync** (This need to be tested)

Options:
1. **Empty or "ALL"** - Sync entire library
2. **Specific albums** - `album_id_1,album_id_2,album_id_3`
3. **Library + albums** - `ALL,album_id_1,album_id_2`

To find album IDs:
1. Open album in Google Photos
2. Copy ID from URL: `https://photos.google.com/album/{ALBUM_ID}`

### Timezone
**Timezone for cron schedule**

Examples:
- `Europe/Rome`
- `America/New_York`
- `Asia/Tokyo`
- `UTC`

Ensures syncs run at the correct local time.

---

## System Requirements

### Supported Architectures

**⚠️ AMD64 ONLY**

### Why ARM64 is Not Supported

This project requires **Google Chrome** for automated Google Photos authentication. ARM64 systems cannot run this project because:

#### Technical Limitations

**Google Chrome is unavailable for ARM64**

- Only Chromium (open-source version) is available for Linux on ARM64/aarch64 architecture.
- Google does not provide official Chrome builds for ARM-based Linux systems.

**Chromium lacks Google OAuth API keys by default**

- Chromium builds do not include Google API keys, so some Google services (like OAuth sign-in, Sync, Safe Browsing) may not work.
- OAuth authentication is restricted in default Chromium builds, but it can work if you manually add your own API keys.

**Google blocks automated Chromium logins**

- Google's security policies can detect and block headless or automated Chromium sessions.
- Even with valid saved credentials, Google may require manual password re-entry.
- Session cookies can be invalidated more aggressively in Chromium.
- Continuous password prompts prevent automated sync.

#### What This Means

After some test I got :
- ✅ Manual login in VNC works using multiarch docker image (one-time authentication)
- ❌ Automated headless sync fails (requires password every time)
- ❌ Session persistence doesn't work (cookies invalidated)
- ❌ Cannot run unattended syncs (defeats the purpose of automation)
---

## Credits & License

This project is a derivative work based on the following open-source projects:

### Based On

**[spraot/gphotos-sync](https://github.com/spraot/gphotos-sync)**
- Primary inspiration and base architecture
- No explicit license found in repository

**[JakeWharton/docker-gphotos-sync](https://github.com/JakeWharton/docker-gphotos-sync)**
- Docker containerization approach
- Licensed under MIT License
- Copyright © 2020 Jake Wharton

**[perkeep/gphotos-cdp](https://github.com/perkeep/gphotos-cdp)**
- Core sync engine using Chrome DevTools Protocol
- Licensed under Apache License 2.0
- Copyright © 2019 The Perkeep Authors

### License

This project incorporates code from projects under different licenses:

- **Apache License 2.0** components from `perkeep/gphotos-cdp`
- **MIT License** components from `JakeWharton/docker-gphotos-sync`

As required by both licenses, all original copyright notices and license texts are preserved in their respective files.

**This derivative work is provided "AS IS" without warranty of any kind.**

---