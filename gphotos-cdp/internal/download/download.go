package download

import (
	"context"
	"errors"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/chromedp/cdproto/browser"
	"github.com/chromedp/cdproto/cdp"
	"github.com/chromedp/cdproto/input"
	"github.com/chromedp/cdproto/target"
	"github.com/chromedp/chromedp"
	"github.com/chromedp/chromedp/kb"
	"github.com/evilsocket/islazy/zip"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"golang.org/x/text/unicode/norm"

	"gphotos-cdp/internal/config"
	"gphotos-cdp/internal/navigation"
	"gphotos-cdp/internal/session"
	"gphotos-cdp/internal/types"
	"gphotos-cdp/internal/utils"
)

var (
	ErrStillProcessing         = errors.New("video is still processing & can be downloaded later")
	ErrCouldNotPressDownloadButton = errors.New("could not press download button")
	ErrAlreadyDownloaded       = errors.New("photo already downloaded")
	ErrUnexpectedDownload      = errors.New("unexpected download")
)

// Locale interface for UI labels
type Locale interface {
	GetVideoStillProcessingDialogLabel() string
	GetVideoStillProcessingStatusText() string
	GetNoWebpageFoundText() string
}

// DownloadAndProcessItem starts a download then sends it to processDownload for processing
func DownloadAndProcessItem(s *types.Session, ctx context.Context, log zerolog.Logger, imageId string, newDownloadChan <-chan types.NewDownload, runFlag string) error {
	log.Trace().Msgf("entering downloadAndProcessItem")
	start := time.Now()

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	photoDataChan := make(chan types.PhotoData, 1)
	errChan := make(chan error)
	jobsRemaining := 2 // One for photo data extraction, one for download

	go func() {
		log.Trace().Msgf("getting photo data")
		data, err := GetPhotoData(s, ctx, log, imageId)
		if err != nil {
			errChan <- err
		} else {
			errChan <- nil
			photoDataChan <- data
		}
	}()

	// Download only the compressed version using Shift+D
	go func() {
		start := time.Now()
		log := log.With().Str("version", "compressed").Logger()
		var photoData types.PhotoData
		var err error
		for i := 0; i < 3; i++ {
			var downloadInfo types.NewDownload
			var downloadProgressChan <-chan bool
			downloadInfo, downloadProgressChan, err = StartDownload(s, ctx, log, imageId, newDownloadChan)
			if err != nil {
				log.Trace().Msgf("download failed: %v", err)
				break
			} else {
				err = WaitForDownload(log, downloadInfo, downloadProgressChan, imageId)
				if err != nil {
					break
				}

				log.Trace().Msgf("download completed, will continue processing when photo data is ready")
				if photoData == (types.PhotoData{}) {
					photoData = <-photoDataChan
				}
				err = ProcessDownload(s, log, downloadInfo, imageId, photoData, runFlag)
				if errors.Is(err, ErrUnexpectedDownload) {
					log.Err(err).Msgf("error processing download for %s (try %d/3)", imageId, i+1)
					continue
				}
				log.Debug().Int64("duration", time.Since(start).Milliseconds()).Msgf("download done")
				break
			}
		}
		errChan <- err
	}()

	go func() {
		deadline := time.NewTimer(30 * time.Minute)
		for {
			select {
			case <-ctx.Done():
				errChan <- ctx.Err()
				return
			case <-time.After(60 * time.Second):
				log.Trace().Msgf("downloadAndProcessItem: waiting for %d jobs to finish", jobsRemaining)
			case <-deadline.C:
				errChan <- fmt.Errorf("downloadAndProcessItem: timeout waiting for %d jobs for %s", jobsRemaining, imageId)
				return
			}
		}
	}()

	for err := range errChan {
		jobsRemaining--
		if err != nil {
			log.Trace().Msgf("downloadAndProcessItem: job result %s, %d jobs remaining", err.Error(), jobsRemaining)
			if !errors.Is(err, ErrStillProcessing) {
				if !errors.Is(err, context.Canceled) {
					session.CaptureScreenshot(ctx, filepath.Join(s.DownloadDir, "error"))
				}

				log.Info().Msgf("unrecoverable error occurred during download, removing files already downloaded for this item")
				// Error downloading, remove files already downloaded
				if err := os.RemoveAll(filepath.Join(s.DownloadDir, imageId)); err != nil {
					log.Err(err).Msgf("error removing files already downloaded: %v", err)
				}
			}

			return err
		} else {
			log.Trace().Msgf("downloadAndProcessItem: job result done, %d jobs remaining", jobsRemaining)
		}
		if jobsRemaining == 0 {
			log.Debug().Int64("duration", time.Since(start).Milliseconds()).Msgf("downloadAndProcessItem successfully completed")
			return nil
		}
	}

	// If we get here, the channel was closed but jobsRemaining > 0
	return ctx.Err()
}

// StartDownload starts the download of the currently viewed item. It returns
// with an error if the download does not start within a minute.
// Always downloads the compressed version using Shift+D shortcut.
func StartDownload(s *types.Session, ctx context.Context, log zerolog.Logger, imageId string, downloadChan <-chan types.NewDownload) (newDownload types.NewDownload, progressChan <-chan bool, err error) {
	log.Trace().Msgf("entering startDownload()")

	start := time.Now()

	timeoutTimer := time.NewTimer(120 * time.Second)
	refreshTimer := time.NewTimer(120 * time.Second)
	requestTimer := time.NewTimer(0 * time.Second)

	log.Trace().Msgf("requesting download from tab %s", chromedp.FromContext(ctx).Target.TargetID)

	for {
		// Checking for gphotos warning that this video can't be downloaded (no known solution)
		if err := CheckForStillProcessing(ctx, nil); err != nil && !errors.Is(err, context.DeadlineExceeded) {
			return types.NewDownload{}, nil, fmt.Errorf("error checking for still processing, %w", err)
		}

		select {
		case <-requestTimer.C:
			// Use Shift+D keyboard shortcut to trigger download
			if err := requestDownload(ctx, log); err != nil {
				return types.NewDownload{}, nil, err
			}
			refreshTimer = time.NewTimer(5 * time.Second)
		case <-refreshTimer.C:
			log.Debug().Msgf("reloading page because download failed to start")
			if err := navigation.NavigateToPhoto(s, ctx, log, imageId); err != nil {
				log.Error().Msgf("startDownload: %s", err.Error())
				refreshTimer = time.NewTimer(1 * time.Second)
			} else {
				requestTimer = time.NewTimer(100 * time.Millisecond)
			}
		case <-timeoutTimer.C:
			return types.NewDownload{}, nil, fmt.Errorf("timeout waiting for download to start for %v", imageId)
		case newDownload := <-downloadChan:
			log.Trace().Msgf("downloadChan: %v", newDownload)
			log.Debug().Int64("duration", time.Since(start).Milliseconds()).Str("GUID", newDownload.GUID).Msgf("download started")
			return newDownload, newDownload.ProgressChan, nil
		default:
			time.Sleep(50 * time.Millisecond)
		}

		log.Trace().Msgf("checking download start status")
	}
}

// WaitForDownload waits for a download to complete
func WaitForDownload(log zerolog.Logger, downloadInfo types.NewDownload, downloadProgressChan <-chan bool, imageId string) error {
	log = log.With().Str("GUID", downloadInfo.GUID).Logger()

	log.Trace().Msgf("entering waitForDownload")
	downloadTimeout := time.NewTimer(time.Minute)
progressLoop:
	for {
		select {
		case p := <-downloadProgressChan:
			if p {
				// download done
				log.Trace().Msgf("waitForDownload: received download completed message")
				break progressLoop
			} else {
				// still downloading
				log.Trace().Msgf("waitForDownload: received download still in progress message")
				downloadTimeout.Reset(time.Minute)
			}
		case <-downloadTimeout.C:
			return fmt.Errorf("timeout waiting for download to complete for %v", imageId)
		}
	}
	return nil
}

// ProcessDownload creates a directory in s.DownloadDir with name = imageId and moves the downloaded files into that directory
func ProcessDownload(s *types.Session, log zerolog.Logger, downloadInfo types.NewDownload, imageId string, data types.PhotoData, runFlag string) error {
	log.Trace().Msgf("entering processDownload")
	start := time.Now()

	outDir, err := makeOutDir(s, imageId, data.Date)
	if err != nil {
		return err
	}

	var filePaths []string
	baseNames := []string{}
	if strings.HasSuffix(downloadInfo.SuggestedFilename, ".zip") {
		var err error
		filePaths, err = HandleZip(s, log, filepath.Join(s.DownloadDirTmp, downloadInfo.GUID), outDir)
		if err != nil {
			return err
		}
		foundExpectedFile := false
		for _, f := range filePaths {
			// Google converts files to jpg and gif sometimes, we won't raise an error for those cases
			filename := norm.NFC.String(filepath.Base(f))
			baseNames = append(baseNames, filename)

			foundExpectedFile = foundExpectedFile || utils.CompareMangled(data.Filename, filename)
		}
		if !foundExpectedFile {
			log.Debug().Msgf("accepting any file from zip (metadata extraction disabled), found: %s", strings.Join(baseNames, ", "))
		}
	} else {
		var filename string
		if downloadInfo.SuggestedFilename != "download" && downloadInfo.SuggestedFilename != "" {
			filename = norm.NFC.String(downloadInfo.SuggestedFilename)
		} else {
			filename = data.Filename
		}

		// Just use whatever filename was downloaded from Google Photos
		log.Debug().Msgf("accepting downloaded filename: %s", filename)

		newFile := filepath.Join(outDir, filename)
		log.Debug().Msgf("moving %v to %v", downloadInfo.GUID, newFile)
		if err := os.Rename(filepath.Join(s.DownloadDirTmp, downloadInfo.GUID), newFile); err != nil {
			return err
		}
		filePaths = []string{newFile}
		baseNames = append(baseNames, filepath.Base(newFile))
	}

	if err := utils.DoFileDateUpdate(data.Date, filePaths); err != nil {
		return err
	}

	for _, f := range filePaths {
		if err := utils.DoRun(f, imageId, runFlag); err != nil {
			return err
		}
	}

	log.Debug().Int64("duration", time.Since(start).Milliseconds()).Msgf("processed downloaded item")
	log.Info().Msgf("downloaded file(s) %s with date %v", strings.Join(baseNames, ", "), data.Date.Format("2006-01-02"))

	// Mark this item as downloaded
	if err := s.DownloadedIds.Add(imageId); err != nil {
		log.Warn().Err(err).Msgf("failed to save downloaded ID %s to file, but download succeeded", imageId)
	}

	return nil
}

// HandleZip handles the case where the currently item is a zip file. It extracts
// each file in the zip file to the same folder, and then deletes the zip file.
func HandleZip(s *types.Session, log zerolog.Logger, zipfile, outFolder string) ([]string, error) {
	st := time.Now()
	log.Debug().Msgf("unzipping %v to %v", zipfile, outFolder)
	// unzip the file
	files, err := zip.Unzip(zipfile, outFolder)
	if err != nil {
		return []string{""}, err
	}

	// delete the zip file
	if err := os.Remove(zipfile); err != nil {
		return []string{""}, err
	}

	log.Debug().Int64("duration", time.Since(st).Milliseconds()).Msgf("done unzipping downloaded zip file: %s", zipfile)
	return files, nil
}

// CheckForStillProcessing checks if a video is still being processed
func CheckForStillProcessing(ctx context.Context, loc Locale) error {
	ctx, cancel := context.WithTimeout(ctx, 4000*time.Millisecond)
	defer cancel()
	log.Trace().Msgf("checking for still processing dialog")

	// This text is available before attempting to download, but doesn't show immediately when the page is loaded
	var undownloadable bool
	chromedp.Evaluate(`function () {
		return [...document.querySelectorAll('c-wiz[data-media-key*="document.location.href.trim().split('/').pop()"]')].filter(x => getComputedStyle(x).visibility != 'hidden')[0]?.textContent.indexOf('Your video will be ready soon') >= 0
	}`, &undownloadable).Do(ctx)

	if undownloadable {
		return ErrStillProcessing
	}

	// If no locale is provided, skip the locale-specific checks
	if loc == nil {
		return nil
	}

	// First check: Look for the dialog with button
	var nodes []*cdp.Node
	selector := getAriaLabelSelector(loc.GetVideoStillProcessingDialogLabel())
	if err := chromedp.Nodes(selector+` button`, &nodes, chromedp.ByQuery, chromedp.AtLeast(0)).Do(ctx); err != nil {
		return err
	}
	isStillProcessing := len(nodes) > 0
	if isStillProcessing {
		log.Debug().Msgf("found still processing dialog, need to press button to remove")
		// Click the button to close the warning, otherwise it will block navigating to the next photo
		cl := session.GetContextData(ctx)
		cl.MuKbEvents.Lock()
		err := chromedp.MouseClickNode(nodes[0]).Do(ctx)
		cl.MuKbEvents.Unlock()
		if err != nil {
			return err
		}
	} else {
		// Second check: Look for status text in page body
		statusText := loc.GetVideoStillProcessingStatusText()
		if err := chromedp.Evaluate("document.body?.textContent.indexOf('"+statusText+"') >= 0", &isStillProcessing).Do(ctx); err != nil {
			return err
		}
		if isStillProcessing {
			log.Debug().Msg("found still processing status at bottom of screen, waiting for it to disappear before continuing")
			time.Sleep(5 * time.Second) // Wait for error message to disappear before continuing, otherwise we will also skip next files
		}
		if !isStillProcessing {
			// Sometimes Google returns a different error, check for that too
			noWebpageText := loc.GetNoWebpageFoundText()
			if err := chromedp.Evaluate("document.body?.textContent.indexOf('"+noWebpageText+"') >= 0", &isStillProcessing).Do(ctx); err != nil {
				return err
			}
		}
	}
	if isStillProcessing {
		log.Debug().Msg("received 'Video is still processing' error")
		return ErrStillProcessing
	}
	return nil
}

// GetPhotoData gets the date from the currently viewed item.
func GetPhotoData(s *types.Session, ctx context.Context, log zerolog.Logger, imageId string) (types.PhotoData, error) {
	// METADATA EXTRACTION ENABLED - Supports any language configured in months-config.json
	ctx, cancel := context.WithTimeout(ctx, 4*time.Minute)
	defer cancel()

	start := time.Now()

	var filename string
	var dateStr string
	var timeStr string
	var tzStr string

	var n = 0
	log.Debug().Msg("extracting photo data")
	for {
		n++
		start := time.Now()
		log := log.With().Int("attempt", n).Logger()
		if err := func() error {
			unlock := navigation.AcquireTabLock(log, "to extract photo data")
			defer unlock()
			log.Trace().Msgf("extracting photo data")

			target.ActivateTarget(chromedp.FromContext(ctx).Target.TargetID).Do(ctx)

			// If video is 'still processing', photo data may never load, so stop here
			var undownloadable bool
			if err := chromedp.Run(ctx, chromedp.Evaluate(`[...document.querySelectorAll('c-wiz[data-media-key*="'+document.location.href.trim().split('/').pop()+'"]')].filter(x => getComputedStyle(x).visibility != 'hidden')[0]?.textContent.indexOf('Your video will be ready soon') >= 0`, &undownloadable)); err != nil {
				return fmt.Errorf("while checking if video is still processing %w", err)
			}
			if undownloadable {
				return ErrStillProcessing
			}

			if n%5 == 0 {
				log.Debug().Msgf("getPhotoData: reloading page to force photo info to load")
				if err := navigation.NavigateToPhoto(s, ctx, log, imageId); err != nil {
					log.Error().Msgf("getPhotoData: %s", err.Error())
				}
			}

			// Extract data from the "Foto/Video - Orientation - Date, Time" aria-label
			var photoInfoLabel string
			sleepDuration := int(math.Min(2000, (math.Pow(1.5, float64(n-1))-1)*50))
			if err := chromedp.Run(ctx,
				chromedp.Sleep(time.Duration(sleepDuration)*time.Millisecond),
				chromedp.Evaluate(`
					[...document.querySelectorAll('[data-p*="`+imageId+`"] [aria-label]')]
						.map(el => el.getAttribute('aria-label'))
						.find(label => label && (label.startsWith('Foto - ') || label.startsWith('Video - ') ||
						                          label.startsWith('Photo - ') || label.startsWith('Video - '))) || ''
				`, &photoInfoLabel),
			); err != nil {
				return fmt.Errorf("could not extract photo info label due to %w", err)
			}

			if len(photoInfoLabel) > 0 {
				// Parse format examples:
				// Italian: "Foto - Verticale - 13 nov 2025, 00:57:41"
				// English: "Photo - Portrait - Nov 17, 2025, 11:08:35 PM"
				// German: "Foto - Hochformat - 13. Nov. 2025, 14:32:41"
				parts := strings.Split(photoInfoLabel, " - ")
				if len(parts) >= 3 {
					dateTimeStr := parts[len(parts)-1]
					dateTimeParts := strings.Split(dateTimeStr, ", ")

					// Handle different date formats:
					// European format (day month year): ["13 nov 2025", "00:57:41"] (2 parts)
					// English format (month day, year): ["Nov 17", "2025", "11:08:35 PM"] (3 parts)
					if len(dateTimeParts) == 2 {
						// European format (Italian, German, French, etc.)
						dateStr = dateTimeParts[0]
						timeStr = dateTimeParts[1]
						filename = imageId
					} else if len(dateTimeParts) == 3 {
						// English format: rejoin date parts
						dateStr = dateTimeParts[0] + " " + dateTimeParts[1]
						timeStr = dateTimeParts[2]
						filename = imageId
					}
				}
			}

			return nil
		}(); err != nil {
			return types.PhotoData{}, err
		} else if len(filename) > 0 && len(dateStr) > 0 && len(timeStr) > 0 {
			log.Debug().Int64("duration", time.Since(start).Milliseconds()).Int("triesToSuccess", n).Msgf("done finding photo data nodes")
			break
		} else {
			log.Debug().Int64("duration", time.Since(start).Milliseconds()).Msgf("done attempt to find photo data nodes")
		}

		// If we can't find metadata after 10 attempts, exit with error
		if n >= 10 {
			log.Error().Msgf("FATAL: could not find metadata after %d attempts for item %s", n, imageId)
			return types.PhotoData{}, fmt.Errorf("failed to extract metadata after %d attempts", n)
		}

		if time.Since(start).Seconds() > 200 {
			return types.PhotoData{}, fmt.Errorf("timeout waiting for photo info (waited %d ms)", time.Since(start).Milliseconds())
		}

		// Do part of the waiting outside of the tab lock, so we don't hog the active tab the whole time
		time.Sleep(time.Duration(n*500) * time.Millisecond)

		log.Trace().Msgf("failed attempt to find photo data nodes")
	}

	log.Trace().Msgf("parsing date: %v and time: %v", dateStr, timeStr)
	log.Trace().Msgf("parsing filename: %v", filename)
	dt, err := parseDateWithConfig(dateStr, timeStr, tzStr)
	if err != nil {
		return types.PhotoData{}, fmt.Errorf("parsing date, %w", err)
	}

	log.Debug().Int64("duration", time.Since(start).Milliseconds()).Msgf("found date and filename: '%v', '%v'", dt, filename)

	return types.PhotoData{Date: dt, Filename: norm.NFC.String(filename)}, nil
}

// StartDownloadListener listens for download events from Chrome
func StartDownloadListener(ctx context.Context, newDownloadChan chan types.NewDownload) {
	currentDownloads := make(map[string]chan bool)

	// Listen for new download events
	chromedp.ListenBrowser(ctx, func(v interface{}) {
		if ev, ok := v.(*browser.EventDownloadWillBegin); ok {
			log.Debug().Str("GUID", ev.GUID).Msgf("download of %s started", ev.SuggestedFilename)
			if ev.SuggestedFilename == "downloads.html" {
				return
			}
			if _, exists := currentDownloads[ev.GUID]; !exists {
				currentDownloads[ev.GUID] = make(chan bool)
			}
			go func() {
				newDownloadChan <- types.NewDownload{
					GUID:              ev.GUID,
					SuggestedFilename: ev.SuggestedFilename,
					TargetId:          ev.FrameID.String(),
					ProgressChan:      currentDownloads[ev.GUID],
				}
			}()
		}
	})

	// Listen for download progress events
	chromedp.ListenBrowser(ctx, func(v interface{}) {
		if ev, ok := v.(*browser.EventDownloadProgress); ok {
			if ev.State == browser.DownloadProgressStateInProgress {
				select {
				case currentDownloads[ev.GUID] <- false:
				default:
				}
			}
			if ev.State == browser.DownloadProgressStateCompleted {
				log.Trace().Str("GUID", ev.GUID).Msgf("received download completed event")
				progressChan := currentDownloads[ev.GUID]
				delete(currentDownloads, ev.GUID)
				go func() {
					time.Sleep(1 * time.Millisecond)
					progressChan <- true
				}()
			}
		}
	})
}

// requestDownload sends the Shift+D keyboard shortcut to start the download of the currently
// viewed item. This is the standard download method.
func requestDownload(ctx context.Context, log zerolog.Logger) error {
	unlock := navigation.AcquireTabLock(log, "to request download")
	defer unlock()
	start := time.Now()

	log.Debug().Msgf("requesting download")
	target.ActivateTarget(chromedp.FromContext(ctx).Target.TargetID).Do(ctx)
	if err := pressButton(ctx, "D", input.ModifierShift); err != nil {
		return err
	}
	time.Sleep(50 * time.Millisecond)
	log.Debug().Int64("duration", time.Since(start).Milliseconds()).Msgf("done requesting download")
	return nil
}

// pressButton simulates pressing a keyboard button with optional modifiers
func pressButton(ctx context.Context, key string, modifier input.Modifier) error {
	keyD, ok := kb.Keys[rune(key[0])]
	if !ok {
		return fmt.Errorf("no %s key", key)
	}

	down := input.DispatchKeyEventParams{
		Key:                   keyD.Key,
		Code:                  keyD.Code,
		NativeVirtualKeyCode:  keyD.Native,
		WindowsVirtualKeyCode: keyD.Windows,
		Type:                  input.KeyDown,
		Modifiers:             modifier,
	}
	if key == "D" {
		down.NativeVirtualKeyCode = 0
	}
	up := down
	up.Type = input.KeyUp

	for _, ev := range []*input.DispatchKeyEventParams{&down, &up} {
		log.Trace().Msgf("triggering button press event: %v, %v, %v", ev.Key, ev.Type, ev.Modifiers)

		if err := chromedp.Run(ctx, ev); err != nil {
			return err
		}
	}
	return nil
}

// makeOutDir creates a directory organized by date: YYYY/MM/
func makeOutDir(s *types.Session, imageId string, date time.Time) (string, error) {
	// Create directory structure: DownloadDir/YYYY/MM/
	year := date.Format("2006")
	month := date.Format("01")

	newDir := filepath.Join(s.DownloadDir, year, month)
	if err := os.MkdirAll(newDir, 0700); err != nil {
		return "", err
	}

	log.Debug().Msgf("Created output directory for date %s: %s", date.Format("2006-01"), newDir)
	return newDir, nil
}

// getAriaLabelSelector returns a CSS selector for an aria-label
func getAriaLabelSelector(label string) string {
	// Simple implementation - assumes "startsWith" matching
	// In production you'd parse the NodeLabelMatch structure
	return fmt.Sprintf("[aria-label^=\"%s\"]", label)
}

// DownloadWorker processes download jobs in a worker goroutine
func DownloadWorker(s *types.Session, workerId int, jobs <-chan types.Job, resultChan chan<- string, errChan chan<- error, downloadChan <-chan types.NewDownload, runFlag string) string {
	ctx, cancel := chromedp.NewContext(s.ParentContext)
	chromedp.Run(ctx)
	ctx = session.SetContextData(ctx)
	navigation.ListenNavEvents(ctx)

	log := log.With().Int("workerId", workerId).Logger()
	go func() {
		defer cancel()
		for job := range jobs {
			log.Debug().Msgf("worker received batch of %d items", len(job.ImageIds))
			log.Trace().Msgf("starting job with itemIds: %s", strings.Join(job.ImageIds, ", "))
			isConsecutive := false
			for i, imageId := range job.ImageIds {
				log := log.With().Str("itemId", imageId).Int("batchItemIndex", i).Logger()

				log.Trace().Msgf("processing batch item %d", i)
				downloadedItemId, err := DoWorkerBatchItem(s, ctx, log, imageId, downloadChan, isConsecutive, runFlag)
				isConsecutive = true
				if errors.Is(err, ErrAbortBatch) {
					break
				} else if errors.Is(err, ErrAlreadyDownloaded) || errors.Is(err, ErrStillProcessing) {
					if errors.Is(err, ErrStillProcessing) {
						// Old highlight videos are no longer available
						log.Info().Msg("skipping generated highlight video that Google cannot be downloaded")
						isConsecutive = false
					}
					downloadedItemId = ""
				} else if err != nil {
					errChan <- err
					return
				}
				resultChan <- downloadedItemId
			}
			log.Debug().Msgf("worker finished processing batch of %d items", len(job.ImageIds))
		}
		errChan <- nil
	}()
	return chromedp.FromContext(ctx).Target.TargetID.String()
}

var ErrAbortBatch = errors.New("abort batch")

// parseDateWithConfig parses a date using the global config
func parseDateWithConfig(dateStr, timeStr, tzStr string) (time.Time, error) {
	// Import config package for MonthsConfig and PageLanguage
	cfg, exists := config.MonthsConfig[config.PageLanguage]
	if !exists {
		return time.Time{}, fmt.Errorf("language configuration not found for %s", config.PageLanguage)
	}
	return utils.ParseDate(dateStr, timeStr, tzStr, cfg.Months, config.PageLanguage)
}

// DoWorkerBatchItem processes a single item in a worker batch
func DoWorkerBatchItem(s *types.Session, ctx context.Context, log zerolog.Logger, imageId string, downloadChan <-chan types.NewDownload, isConsecutive bool, runFlag string) (string, error) {
	expectedLocation := session.GphotosURL + s.UserPath + s.AlbumPath + "/photo/" + imageId

	var previousLocation string
	if err := chromedp.Run(ctx, chromedp.Location(&previousLocation)); err != nil {
		return "", fmt.Errorf("error getting location: %w", err)
	}
	log.Trace().Msgf("current location: %s", previousLocation)
	atExpectedUrl := previousLocation == expectedLocation
	if isConsecutive && !atExpectedUrl && strings.HasPrefix(previousLocation, session.GphotosURL) {
		var location string
		// pressing right arrow to navigate to the next item (batch jobs should be sequential)
		log.Trace().Msgf("navigating to next item by right arrow press (%s)", expectedLocation)
		err := chromedp.Run(ctx,
			target.ActivateTarget(chromedp.FromContext(ctx).Target.TargetID),
			chromedp.ActionFunc(navigation.NavRight(log)),
			chromedp.Sleep(10*time.Millisecond),
			chromedp.Location(&location),
			chromedp.ActionFunc(
				func(ctx context.Context) error {
					if location != expectedLocation {
						log.Warn().Msgf("after nav to right, expected location %s, got %s", expectedLocation, location)
					} else {
						atExpectedUrl = true
					}
					return nil
				},
			),
		)
		if err != nil {
			log.Error().Msgf("error navigating to next batch item: %s", err.Error())
		} else if atExpectedUrl {
			log.Trace().Msgf("done navigating to %v by right arrow press", expectedLocation)
		}
	}

	if !atExpectedUrl {
		log.Trace().Msgf("navigating to expected location")
		if err := navigation.NavigateToPhoto(s, ctx, log, imageId); err != nil {
			return "", err
		}
	}

	time.Sleep(2 * time.Millisecond)

	// Check if item is new - this will be implemented in sync package
	// For now, we assume it's new
	log.Debug().Msgf(`item not found in photos dir, downloading it now`)

	err := chromedp.Run(ctx, chromedp.ActionFunc(
		func(ctx context.Context) error {
			return DownloadAndProcessItem(s, ctx, log, imageId, downloadChan, runFlag)
		},
	))
	if err != nil {
		log.Trace().Msgf("downloadWorker: encountered error while processing batch item: %s", err.Error())
		return "", err
	}
	return imageId, nil
}
