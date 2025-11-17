# Google Photos Sync

Automatically download all your photos from Google Photos.

## Quick Start

### 1. First Time Setup (Authentication)

Clone this repository and run the authentication script:

```bash
git clone <this-repo>
cd Gphoto_sync
./doauth.sh
```

This will:
- Open a VNC window at `http://localhost:6080`
- Let you login to your Google account
- Save your login session in the `./profile` folder

### 2. Test It Works

Run a test sync to make sure everything is working:

```bash
./testsync.sh
```

Your photos will be downloaded to the `./photos` folder.

### 3. Setup Automatic Sync (Optional)

Use Docker Compose to run syncs automatically on a schedule:

```yaml
services:
  gphotos-sync:
    build:
      context: .
    container_name: gphotos-sync
    restart: unless-stopped
    privileged: true
    volumes:
      - ./profile:/tmp/gphotos-cdp
      - ./photos:/download
    environment:
      - PUID=1000
      - PGID=1000
      - CRON_SCHEDULE=0 2 * * *  # Run every day at 2 AM
      - LOGLEVEL=info
      - TZ=Europe/Berlin
```

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

### Avoid Highlight Videos

Google Photos creates automatic highlight videos. These can cause sync issues because they're often undownloadable. If you experience freezes:

1. Delete highlight videos from your Google Photos account
2. Check the `.lastdone` file doesn't contain a highlight video URL

## Credits

This is a fork of those projects:
https://github.com/spraot/gphotos-sync
https://github.com/JakeWharton/docker-gphotos-sync
https://github.com/perkeep/gphotos-cdp