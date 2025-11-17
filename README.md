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