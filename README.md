# Google Photos Sync

Automatically download all your photos from Google Photos using Docker Compose with an intuitive Web GUI for managing multiple accounts.

## Quick Start (Web GUI)

### 1. Start Web GUI

```bash
git clone <this-repo>
cd Gphoto_sync
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
6. Configure sync settings:
   - **Cron Schedule**: When to sync (e.g., `0 3 * * *` = daily at 3 AM)
   - **Run on Startup**: Sync immediately when container starts
   - **Log Level**: Debug, Info, Warning, or Error
   - **Parallel Downloads**: Number of concurrent downloads (1-20, default: 6)
   - **Albums**: Leave empty for entire library, or specify album IDs
   - **Timezone**: Your timezone (e.g., Europe/Rome, America/New_York)
7. Click **"Create Docker Compose"**

Your profile will start automatically and begin syncing!

---

## Web GUI Features

**Access at http://localhost:8080**

### Profile Management
- ➕ **Create Profile**: Add new Google accounts with custom names
- 🔑 **Authenticate**: Login via VNC browser interface
- ⚙️ **Configure**: Set sync schedule, workers, albums, and more
- ▶️ **Start/Stop/Restart**: Control individual profile containers
- 🗑️ **Delete**: Remove profiles and their containers

### Monitoring
- 📊 **Real-time Status**: View running/stopped containers at a glance
- ⏰ **Next Sync Time**: Countdown to next scheduled sync
- 📜 **Live Logs**: Stream logs in real-time with auto-scroll
- 📥 **Download Logs**: Export logs for debugging

### Container Information
- Container ID and status
- Sync schedule (cron expression)
- Worker count and startup behavior
- Next run time and countdown

---

## Multiple Google Accounts

The Web GUI makes managing multiple accounts easy:

1. **Create multiple profiles** with different Google accounts
2. **Each profile syncs independently** with its own schedule
3. **Files are organized separately**: `photos1/`, `photos2/`, `photos3/`, etc.
4. **Manage everything from one dashboard**

Example setup:
- **Profile 1** "Personal" → syncs daily at 2 AM → 6 workers
- **Profile 2** "Work" → syncs every 6 hours → 3 workers
- **Profile 3** "Family" → syncs on startup + daily → entire library

---

## Configuration Options (Web GUI)

All settings can be configured through the Web GUI when creating or editing a profile:

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

Useful for testing or ensuring you have the latest photos after a restart.

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
**Which albums to sync**

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

## Advanced Configuration (Manual)

For advanced users who prefer editing docker-compose files directly, you can also configure profiles manually:

### Additional Environment Variables

```yaml
environment:
  - PUID=1000                          # User ID for file ownership
  - PGID=1000                          # Group ID for file ownership
  - RESTART_SCHEDULE=0 0 1 * *         # Delete .lastdone files (monthly restart)
  - HEALTHCHECK_HOST=https://hc-ping.com
  - HEALTHCHECK_ID=your-healthcheck-id
```

---

## How It Works

1. **Authentication**: Login to Google Photos via VNC browser (one-time per profile)
2. **Profile Storage**: Chrome session saved to `profile1/`, `profile2/`, etc.
3. **First Sync**: Downloads all photos to `photos1/`, `photos2/`, etc.
4. **Incremental Syncs**: Only downloads new photos (skips existing ones)
5. **Deleted Photos**: If deleted from Google Photos, won't be deleted locally (tracked in `.removed` file)
6. **File Organization**: Each photo gets its own folder (supports Live Photos and edited versions)
7. **Scheduled Syncs**: Runs automatically based on cron schedule
8. **EXIF Preservation**: File modification dates synced to photo's original date

### Directory Structure

```
Gphoto_sync/
├── profile1/              # Chrome session for account 1
├── profile2/              # Chrome session for account 2
├── photos1/               # Photos from account 1
│   ├── 2024-01-01/
│   │   └── IMG_1234/
│   │       ├── IMG_1234.jpg
│   │       └── IMG_1234.MOV (if Live Photo)
│   └── .lastdone          # Sync progress tracking
├── photos2/               # Photos from account 2
└── docker-compose.profile1.yml  # Profile 1 configuration
```

---

## Troubleshooting

### Profile not syncing at startup
- Make sure "Run on Startup" is enabled in profile configuration
- Check logs: Container logs will show "running initial sync on startup..."
- Edit the profile configuration to toggle the setting

### VNC authentication stuck
- Make sure to click "Start VNC Container" button first
- Wait 5-10 seconds for VNC to start
- If VNC is slow, refresh the VNC tab (http://localhost:6080)

### Container won't start after config change
- Configuration changes require container recreation
- The Web GUI automatically recreates containers when you edit configuration
- Alternatively, stop and start the profile manually

### Photos not appearing in photos directory
- Check container logs for errors
- Verify authentication is successful (check for "authentication successful!" in logs)
- Ensure PUID/PGID match your user (run `id -u` and `id -g`)

### Sync is slow
- Increase worker count (default: 6, try 10-15)
- Check network connection and Google Photos API rate limits

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