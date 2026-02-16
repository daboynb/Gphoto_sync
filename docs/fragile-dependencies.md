# Fragile Dependencies on Google Photos Frontend

This document lists all places where the sync engine depends on Google Photos' internal frontend structure. These elements can change without notice and break the sync process.

## Risk Levels

- **Critical**: Sync completely fails if this changes
- **Medium**: A specific feature breaks, but sync can partially continue
- **Low**: Minor degradation, fallback exists

## Dependencies Table

| # | Dependency | Risk | File | What Could Break |
|---|-----------|------|------|-----------------|
| 1 | `a[href^="./photo/"]` CSS selector for finding photo links | Critical | `internal/sync/sync.go` | If Google changes the link structure for photo items, no photos are discovered |
| 2 | Shift+D keyboard shortcut triggers download | Critical | `internal/download/download.go:requestDownload()` | If Google removes or changes the shortcut, all downloads fail |
| 3 | `aria-label` attribute on photo elements containing date/orientation metadata | Critical | `internal/download/download.go:GetPhotoData()` | Date extraction fails, photos cannot be organized by date |
| 4 | `aria-label` format: `"Photo - Portrait - Nov 17, 2025, 11:08:35 PM"` (with ` - ` separators) | Critical | `internal/download/download.go:GetPhotoData()` | Date parsing fails if separator or field order changes |
| 5 | `data-p` attribute containing photo ID for element selection | Critical | `internal/download/download.go:GetPhotoData()` | Cannot locate metadata for a specific photo |
| 6 | `browser.EventDownloadWillBegin` / `EventDownloadProgress` CDP events | Low | `internal/download/download.go:StartDownloadListener()` | These are Chrome DevTools Protocol events, not Google-specific. Stable. |
| 7 | `c-wiz[data-media-key]` custom element for video processing detection | Medium | `internal/download/download.go:CheckForStillProcessing()` | "Still processing" videos won't be detected, causing download timeouts |
| 8 | `"Your video will be ready soon"` English text in page body | Medium | `internal/download/download.go:CheckForStillProcessing()` | Language-specific check fails for non-English users |
| 9 | URL path structure: `/photo/{imageId}` | Critical | `internal/download/download.go:DoWorkerBatchItem()`, `internal/navigation/` | Navigation to individual photos breaks |
| 10 | Right-arrow key navigates to next photo in viewer | Medium | `internal/download/download.go:DoWorkerBatchItem()` | Batch optimization fails, falls back to direct navigation (slower but functional) |
| 11 | Month names in various languages for date parsing | Medium | `internal/utils/date.go`, `months-config.json` | Date parsing fails for unconfigured languages |
| 12 | Google Photos URL base: `photos.google.com` | Critical | `internal/session/session.go` | Complete failure if Google changes the domain |
| 13 | Chrome user data directory structure (`Default/Preferences`) | Low | `src/sync.sh` | Language preference injection fails, but sync continues |
| 14 | `AF_initDataCallback` with `key: 'ds:5'` in page `<script>` tags | Medium | `internal/download/download.go` (original method) | Original download method fails, falls back to compressed (Shift+D) |
| 15 | Download URL pattern `=s0-d-I` suffix in `AF_initDataCallback` data | Medium | `internal/download/download.go` (original method) | Original download URL extraction fails, falls back to compressed |

## Mitigation Strategies

1. **Fallback chain**: The `original` download method falls back to `compressed` (Shift+D) if data extraction fails
2. **Multi-language support**: `months-config.json` supports multiple languages for date parsing
3. **Retry logic**: Most operations have retry loops with exponential backoff
4. **Screenshot on error**: Failed downloads capture screenshots for debugging

## Monitoring Recommendations

- Watch for increased error rates after Google Photos frontend updates
- Check logs for repeated "reloading page" messages (indicates metadata extraction difficulty)
- Monitor download success rate per method (`original` vs `compressed`)
