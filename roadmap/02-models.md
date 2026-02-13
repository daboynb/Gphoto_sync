# Passo 2: Definire i Modelli (models.py)

## Obiettivo

Portare le struct Go da `gphotos-cdp/internal/types/types.go` in dataclass Python.

## File da creare: `web-gui/sync_engine/models.py`

## Mappatura Go -> Python

### PhotoData (types.go:10-13)

Go:
```go
type PhotoData struct {
    Date     time.Time
    Filename string
}
```

Python:
```python
@dataclass
class PhotoData:
    date: datetime
    filename: str
```

### Job (types.go:16-18)

Go:
```go
type Job struct {
    ImageIds []string
}
```

Python:
```python
@dataclass
class Job:
    image_ids: list[str]
```

### NewDownload (types.go:21-26)

Go:
```go
type NewDownload struct {
    GUID              string
    SuggestedFilename string
    TargetId          string
    ProgressChan      chan bool
}
```

Python (usa asyncio.Event invece di chan):
```python
@dataclass
class NewDownload:
    guid: str
    suggested_filename: str
    target_id: str
    progress_event: asyncio.Event  # segnala completamento download
    completed: bool = False
```

### Session (types.go:37-52)

Go:
```go
type Session struct {
    ParentContext      context.Context
    ChromeExecCancel   context.CancelFunc
    DownloadDir        string
    DownloadDirTmp     string
    ProfileDir         string
    GlobalErrChan      chan error
    UserPath           string
    AlbumPath          string
    ExistingItems      sync.Map
    FoundItems         sync.Map
    DownloadedItems    sync.Map
    DownloadedIds      DownloadedIdsManager
    NewDownloadChan    chan NewDownload
    SkippedCount       uint64
}
```

Python (usa asyncio.Queue, set, e riferimenti Playwright):
```python
@dataclass
class Session:
    download_dir: str
    download_dir_tmp: str
    profile_dir: str
    user_path: str = ""
    album_path: str = ""

    # Playwright objects (set after browser launch)
    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None

    # State tracking
    found_items: set = field(default_factory=set)
    downloaded_items: set = field(default_factory=set)
    downloaded_ids: Optional[Any] = None  # DownloadedIdsManager
    skipped_count: int = 0

    # Download coordination
    new_download_queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    # Legacy (per CheckForRemovedFiles)
    existing_items: set = field(default_factory=set)
```

### MonthConfig

Go (config/config.go:15-19):
```go
type MonthConfig struct {
    Months         []string
    MetadataFormat string
    DateFormat     string
}
```

Python:
```python
@dataclass
class MonthConfig:
    months: list[str]
    metadata_format: str
    date_format: str
```

### GPhotosLocale (locales.go)

Go:
```go
type GPhotosLocale struct {
    VideoStillProcessingDialogLabel NodeLabelMatch
    VideoStillProcessingStatusText  string
    NoWebpageFoundText              string
}
```

Python:
```python
@dataclass
class GPhotosLocale:
    video_still_processing_label: str = "Video still is processing"
    video_still_processing_text: str = "Video is still processing &amp; can be downloaded later"
    no_webpage_found_text: str = "No webpage was found for the web address:"
```

## Codice completo da scrivere

```python
"""Data models for the sync engine."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any


@dataclass
class PhotoData:
    """Metadata about a photo extracted from Google Photos DOM."""
    date: datetime
    filename: str


@dataclass
class Job:
    """A batch of image IDs to download."""
    image_ids: list[str]


@dataclass
class NewDownload:
    """Represents a download event from Chrome CDP."""
    guid: str
    suggested_filename: str
    target_id: str
    progress_event: asyncio.Event = field(default_factory=asyncio.Event)
    completed: bool = False


@dataclass
class MonthConfig:
    """Language-specific month names and date format."""
    months: list[str]
    metadata_format: str
    date_format: str


@dataclass
class Session:
    """Manages Chrome session and download state."""
    download_dir: str
    download_dir_tmp: str
    profile_dir: str
    user_path: str = ""
    album_path: str = ""

    # Playwright objects (set after browser launch)
    browser: Optional[Any] = None
    context: Optional[Any] = None
    page: Optional[Any] = None

    # State tracking (thread-safe sets)
    found_items: set = field(default_factory=set)
    downloaded_items: set = field(default_factory=set)
    downloaded_ids: Optional[Any] = None  # DownloadedIdsManager instance
    skipped_count: int = 0

    # Download coordination
    new_download_queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    # Legacy (for CheckForRemovedFiles)
    existing_items: set = field(default_factory=set)


@dataclass
class GPhotosLocale:
    """UI labels for detecting Google Photos states (English only for now)."""
    video_still_processing_label: str = "Video still is processing"
    video_still_processing_text: str = "Video is still processing &amp; can be downloaded later"
    no_webpage_found_text: str = "No webpage was found for the web address:"


# Constants
GPHOTOS_URL = "https://photos.google.com"
```

## Differenze chiave Go vs Python

| Go | Python | Motivazione |
|---|---|---|
| `sync.Map` | `set` | In Python asyncio e' single-thread, non serve lock |
| `chan NewDownload` | `asyncio.Queue` | Equivalente async dei Go channels |
| `chan bool` (progress) | `asyncio.Event` | Segnala completamento una tantum |
| `context.Context` | Implicito in Playwright | Playwright gestisce il lifecycle internamente |
| `context.CancelFunc` | `browser.close()` | Chiusura diretta dell'oggetto |

## Verifica

```bash
cd web-gui && python -c "
from sync_engine.models import Session, Job, PhotoData, NewDownload, MonthConfig, GPHOTOS_URL
print('All models imported successfully')
print(f'GPHOTOS_URL = {GPHOTOS_URL}')
s = Session(download_dir='/tmp', download_dir_tmp='/tmp/tmp', profile_dir='/tmp/profile')
print(f'Session created: {s.download_dir}')
"
```
