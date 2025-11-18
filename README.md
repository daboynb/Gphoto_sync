# Google Photos Sync

Automatically download all your photos from Google Photos using Docker Compose.

## Quick Start (Single Profile)

### 1. Authentication

```bash
git clone <this-repo>
cd Gphoto_sync
./doauth.sh  # Opens VNC at http://localhost:6080 - login with your Google account
```

### 2. Start Automatic Sync

Create `docker-compose.yml`:

```yaml
services:
  gphotos-sync:
    build:
      context: .
    container_name: gphotos-sync
    restart: unless-stopped
    privileged: true
    volumes:
      - ./profile1:/tmp/gphotos-cdp
      - ./photos1:/download
    environment:
      - PUID=1000              # Your user ID (run: id -u)
      - PGID=1000              # Your group ID (run: id -g)
      - CRON_SCHEDULE=0 2 * * *  # Daily at 2 AM
      - RUN_ON_STARTUP=true    # Sync immediately on startup
      - LOGLEVEL=info
      - TZ=Europe/Rome
      - WORKER_COUNT=6
```

Start sync:
```bash
docker compose up -d
docker compose logs -f  # Watch logs
```

---

## Multiple Google Accounts

### 1. Create Profiles

```bash
./doauth.sh  # Creates profile1 → login first account
./doauth.sh  # Creates profile2 → login second account
./doauth.sh  # Creates profile3 → login third account (optional)
```

### 2. Configure docker-compose.yml

```yaml
services:
  gphotos-sync-profile1:
    build:
      context: .
    container_name: gphotos-sync-profile1
    restart: unless-stopped
    privileged: true
    volumes:
      - ./profile1:/tmp/gphotos-cdp
      - ./photos1:/download
    environment:
      - PUID=1000
      - PGID=1000
      - CRON_SCHEDULE=0 2 * * *
      - RUN_ON_STARTUP=true
      - LOGLEVEL=info
      - TZ=Europe/Rome
      - WORKER_COUNT=6

  gphotos-sync-profile2:
    build:
      context: .
    container_name: gphotos-sync-profile2
    restart: unless-stopped
    privileged: true
    volumes:
      - ./profile2:/tmp/gphotos-cdp
      - ./photos2:/download
    environment:
      - PUID=1000
      - PGID=1000
      - CRON_SCHEDULE=0 3 * * *  # 3 AM (1 hour after profile1)
      - RUN_ON_STARTUP=true
      - LOGLEVEL=info
      - TZ=Europe/Rome
      - WORKER_COUNT=6
```

Start all:
```bash
docker compose up -d
```

Result: `profile1/` → `photos1/`, `profile2/` → `photos2/`

---

## Configuration Options

### Schedule Settings

- **CRON_SCHEDULE**: When to run the sync (default: `0 2 * * *` = daily at 2 AM)
  - `0 * * * *` = every hour
  - `0 */6 * * *` = every 6 hours
  - `0 0 * * 0` = every Sunday at midnight

### Download Specific Albums

To download only specific albums instead of your entire library:

1. Open the album in your browser
2. Copy the album ID from the URL: `https://photos.google.com/album/{ALBUM_ID}`
3. Set the environment variable:

```yaml
environment:
  - ALBUMS=album1_id,album2_id,album3_id
```

To sync both albums AND your entire library, add `ALL` to the list:
```yaml
  - ALBUMS=ALL,album1_id,album2_id
```

### Other Options

- **PUID/PGID**: User/group ID for file permissions (run `id -u` and `id -g` to find yours)
- **RUN_ON_STARTUP**: Set to `true` to sync immediately on container startup, then continue with cron (default: `false`)
- **LOGLEVEL**: `debug`, `info`, `warn`, or `error`
- **WORKER_COUNT**: Number of parallel downloads (default: 6)

---

## How It Works

1. **First Run**: Downloads all your photos to `./photos`
2. **Next Runs**: Only downloads new photos (skips existing ones)
3. **Deleted Photos**: If you delete a photo from Google Photos, it won't be deleted locally. Instead, it's added to a `.removed` file.
4. **File Structure**: Each photo gets its own folder (useful for Live Photos and edited versions)

---

## Tips & Tricks

### Fast Initial Sync (Legacy Mode)

If you have thousands of photos, the first sync can take a while. Use "legacy mode" to speed it up:

```yaml
environment:
  - GPHOTOS_CDP_ARGS=-legacy
```

**Note**: Legacy mode is slower for checking updates, so switch back to normal mode after the initial sync is complete.

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