package sync

import (
	"context"
	"fmt"
	"math"
	"net/http"
	"path"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/chromedp/cdproto/cdp"
	"github.com/chromedp/cdproto/dom"
	cdpruntime "github.com/chromedp/cdproto/runtime"
	"github.com/chromedp/cdproto/target"
	"github.com/chromedp/chromedp"
	"github.com/chromedp/chromedp/kb"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"os"

	"gphotos-cdp/internal/download"
	"gphotos-cdp/internal/navigation"
	"gphotos-cdp/internal/session"
	"gphotos-cdp/internal/types"
	"gphotos-cdp/internal/utils"
)

// Resync the library/album of photos
// Use [...document.querySelectorAll('a[href^=".{relPath}photo/"]')] to find all visible photos
// Check that each one is already downloaded. Optionally check/update date from the element
// attr, e.g. aria-label="Photo - Landscape - Feb 12, 2025, 6:34:39 PM"
// Then do .pop().focus() on the last a element found to scroll to it and make more photos visible
// Then repeat until we get to the end
// If any photos are missing we can asynchronously create a new chromedp context, then in that
// context navigate to that photo and call downloadAndProcessItem
func Resync(s *types.Session, ctx context.Context, workersFlag int64, albumIdFlag string, runFlag string) error {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	navigation.ListenNavEvents(ctx)

	lastNode := &cdp.Node{}
	var nodes []*cdp.Node
	i := 0              // next node to process in nodes array
	n := 0              // number of nodes processed in all
	var newItemsCount int64 // number of photos downloaded
	retries := 0        // number of subsequent failed attempts to find new items to download
	sliderPos := 0.0
	estimatedRemaining := 1000
	photoNodeSelector := GetPhotoNodeSelector(s)

	log.Trace().Msgf("finding start node")
	opts := []chromedp.QueryOption{chromedp.ByQuery, chromedp.AtLeast(0)}

	if err := chromedp.Nodes(photoNodeSelector, &nodes, opts...).Do(ctx); err != nil {
		return fmt.Errorf("error finding photo nodes, %w", err)
	}
	if len(nodes) == 0 {
		log.Info().Msg("no photos to sync")
		return nil
	}

	jobChan := make(chan types.Job)
	resultChan := make(chan string, workersFlag)
	errChan := make(chan error, workersFlag)
	var runningWorkers int64
	atomic.StoreInt64(&runningWorkers, workersFlag)
	var workerDownloadChanByFrameId sync.Map
	for i := int64(0); i < workersFlag; i++ {
		workerDownloadChan := make(chan types.NewDownload, 1)
		workerDownloadChanByFrameId.Store(download.DownloadWorker(s, int(i+1), jobChan, resultChan, errChan, workerDownloadChan, runFlag), workerDownloadChan)
	}

	// job channel routing
	go func(ctx context.Context) {
		for {
			select {
			case <-ctx.Done():
				return
			case newDownload := <-s.NewDownloadChan:
				worker, exists := workerDownloadChanByFrameId.Load(newDownload.TargetId)
				if !exists {
					s.GlobalErrChan <- fmt.Errorf("worker with targetId %s not found for download of %s", newDownload.TargetId, newDownload.SuggestedFilename)
					return
				}
				go func() {
					worker.(chan types.NewDownload) <- newDownload
				}()
			case res := <-resultChan:
				if res != "" {
					if _, exists := s.DownloadedItems.Load(res); exists {
						log.Warn().Msgf("we've downloaded the same item twice, this shouldn't happen")
					} else {
						s.DownloadedItems.Store(res, struct{}{})
					}
				} else {
					atomic.AddUint64(&s.SkippedCount, 1)
				}
			case err := <-errChan:
				if err != nil {
					log.Trace().Msgf("received error from worker: %s", err.Error())
					s.GlobalErrChan <- err
				}
				if atomic.AddInt64(&runningWorkers, -1) == 0 {
					s.GlobalErrChan <- nil
					return
				}
			}
		}
	}(ctx)

	// progress logger
	go func(ctx context.Context) {
		lastSyncedCount := 0
		iterationsWithNoProgressCount := 0
		start := time.Now()
		for {
			done := false
			select {
			case <-time.After(60 * time.Second):
			case <-ctx.Done():
				done = true
			}
			downloadedCount := 0
			s.DownloadedItems.Range(func(key, value interface{}) bool {
				downloadedCount++
				return true
			})
			syncedCount := n
			progress := math.Min(float64(syncedCount)/float64(estimatedRemaining+syncedCount), 1)
			if !done {
				queueCount := atomic.LoadInt64(&newItemsCount) - int64(downloadedCount) - int64(atomic.LoadUint64(&s.SkippedCount))
				totalCount := syncedCount + estimatedRemaining
				denominator := syncedCount - int(queueCount/2)
				if denominator < 1 {
					denominator = 1
				}
				timeRemaining := time.Since(start) * time.Duration(estimatedRemaining) / time.Duration(denominator)
				log.Info().Msgf("so far: downloaded %d (%d in queue), progress: %.2f%% (%d/%d), estimated remaining: %d (%s)", downloadedCount, queueCount, progress*100, syncedCount, totalCount, estimatedRemaining, timeRemaining.Round(time.Second))
			} else {
				log.Info().Msgf("in total: synced %v items, downloaded %v, progress: %.2f%%", syncedCount, downloadedCount, progress*100)
				return
			}
			if syncedCount == lastSyncedCount {
				iterationsWithNoProgressCount++
				if iterationsWithNoProgressCount > 20 {
					panic("no new items processed for 20 minutes, stopping sync")
				}
			} else {
				iterationsWithNoProgressCount = 0
			}
			lastSyncedCount = syncedCount
		}
	}(ctx)

	for {
		if retries%5 == 0 {
			target.ActivateTarget(chromedp.FromContext(ctx).Target.TargetID).Do(ctx)
			if retries != 0 {
				log.Trace().Msgf("we seem to be stuck, manually scrolling might help")
				if err := navigation.DoActionWithTimeout(ctx, chromedp.KeyEvent(kb.ArrowDown), 1000*time.Millisecond); err != nil {
					log.Warn().Err(err).Msgf("error scrolling page down manually, %v", err)
				}
				time.Sleep(200 * time.Millisecond)
			}
		}

		if retries > 0 && retries%10 == 0 {
			// loading slow, let's give it some extra time
			time.Sleep(1 * time.Second)
		}

		// New new nodes found, does it look like we are done?
		if retries > 5000 || (retries > 100 && estimatedRemaining < 50) {
			break
		}

		if scrollErr := navigation.GetScrollPosition(ctx, &sliderPos, albumIdFlag); scrollErr != nil {
			// sometimes chromedp gets into a bad state here, so let's restart navigation and try again
			if err := navigation.NavigateWithAction(s, ctx, log.Logger, chromedp.Navigate(session.GphotosURL+s.UserPath+s.AlbumPath), "to start", 20000*time.Millisecond, 5); err != nil {
				return fmt.Errorf("error getting slider position, %w, followed by error when attempting to recover, %v", scrollErr, err)
			}
			chromedp.WaitReady("body", chromedp.ByQuery).Do(ctx)
			if err := navigation.SetScrollPosition(ctx, sliderPos, albumIdFlag); err != nil {
				session.CaptureScreenshot(ctx, path.Join(s.DownloadDir, "error"))
				return fmt.Errorf("error getting slider position, %w, followed by error when attempting to recover, %v", scrollErr, err)
			}
		}
		log.Trace().Msgf("slider position: %.2f%%", sliderPos*100)

		select {
		case err := <-s.GlobalErrChan:
			return err
		default:
		}

		if n < 5 || sliderPos < 0.001 {
			estimatedRemaining = 50
		} else {
			estimatedRemaining = int(math.Floor((1/sliderPos - 1) * float64(n+30)))
		}

		if n != 0 && i >= len(nodes) {
			if retries == 0 {
				// start by scrolling to the next batch by focusing the last processed node
				log.Trace().Msgf("scrolling to last processed node: %v", lastNode.NodeID)
				if err := navigation.DoActionWithTimeout(ctx, dom.Focus().WithNodeID(lastNode.NodeID), 1000*time.Millisecond); err != nil {
					log.Debug().Msgf("error scrolling to next batch of items: %v", err)
				}
			}

			if err := chromedp.Nodes(photoNodeSelector, &nodes, chromedp.ByQueryAll, chromedp.AtLeast(0)).Do(ctx); err != nil {
				return fmt.Errorf("error finding photo nodes, %w", err)
			}
			log.Trace().Msgf("found %d items, checking if any are new", len(nodes))

			// remove already processed nodes
			foundNodes := len(nodes)
			for i, node := range nodes {
				if node == lastNode {
					nodes = nodes[i+1:]
					break
				}
			}
			if len(nodes) == 0 {
				retries++
				continue
			}
			log.Trace().Msgf("%d nodes on page, processing %d that haven't been processed yet", foundNodes, len(nodes))
			if foundNodes == len(nodes) {
				log.Warn().Msg("only new nodes found, expected an overlap")
			}

			retries = 0
			i = 0
		}

		imageIds := []string{}

		for i < len(nodes) {
			lastNode = nodes[i]
			i++
			n++

			imageId, err := navigation.ImageIdFromUrl(lastNode.AttributeValue("href"))
			if err != nil {
				return fmt.Errorf("error getting item id from url, %w", err)
			}

			log := log.With().Str("itemId", imageId).Logger()

			shouldDownload, err := IsNewItem(s, log, imageId, false)
			if err != nil {
				return err
			} else if !shouldDownload {
				if len(imageIds) > 0 {
					break
				} else {
					continue
				}
			}

			imageIds = append(imageIds, imageId)
		}

		if len(imageIds) > 0 {
			log.Debug().Msgf("adding %d items to queue", len(imageIds))
			job := types.Job{ImageIds: imageIds}

			log.Trace().Msgf("queuing job with itemIds: %s", strings.Join(job.ImageIds, ", "))

			select {
			case err := <-s.GlobalErrChan:
				return err
			case jobChan <- job:
				log.Trace().Msgf("queued job with itemIds: %s", strings.Join(job.ImageIds, ", "))
			}
		}

		atomic.AddInt64(&newItemsCount, int64(len(imageIds)))
	}
	close(jobChan)

	for err := range s.GlobalErrChan {
		return err
	}
	return nil
}

// IsNewItem checks if an item needs to be downloaded
func IsNewItem(s *types.Session, log zerolog.Logger, imageId string, markFound bool) (bool, error) {
	if _, exists := s.FoundItems.Load(imageId); exists {
		return false, nil
	}

	isNew := true
	hasFiles, err := utils.DirHasFiles(s.DownloadDir, imageId)
	if err != nil {
		return false, err
	} else if hasFiles {
		log.Trace().Msgf("skipping item, already downloaded")
		isNew = false
	}

	if markFound || !isNew {
		s.FoundItems.Store(imageId, struct{}{})
	}

	return isNew, nil
}

// CheckForRemovedFiles checks if there are folders in the download dir that were not seen in gphotos
func CheckForRemovedFiles(s *types.Session, ctx context.Context, removedFlag bool) error {
	if removedFlag {
		ctx, cancel := context.WithTimeout(ctx, 30*time.Minute)
		defer cancel()

		log.Info().Msg("checking for removed files")
		deleted := []string{}
		s.ExistingItems.Range(func(itemId, _ any) bool {
			if itemId != "tmp" {
				// Check if the folder name is in the map of photo IDs
				if _, exists := s.FoundItems.Load(itemId); !exists {
					deleted = append(deleted, itemId.(string))
				}
			}
			return true
		})
		if len(deleted) > 0 {
			log.Info().Msgf("folders found for %d local photos that were not found in this sync. Checking google photos to confirm they are not there", len(deleted))
		}
		i := 0
		for i < len(deleted) {
			imageId := deleted[i]
			photoUrl := GetPhotoUrl(s, imageId)
			var resp int
			if err := chromedp.Run(ctx,
				chromedp.Evaluate(`new Promise((res) => fetch('`+photoUrl+`').then(x => res(x.status)));`, &resp,
					func(p *cdpruntime.EvaluateParams) *cdpruntime.EvaluateParams {
						return p.WithAwaitPromise(true)
					}),
			); err != nil {
				log.Err(err).Msgf("error checking for removed file %s: %s, will not continue checking for removed files", imageId, err.Error())
				return nil
			}
			if resp == http.StatusOK {
				log.Debug().Msgf("photo %s was not in original sync, but is still present on google photos, it might be in the trash", imageId)
				// Remove element at index i (slices.Delete equivalent for Go 1.18)
				deleted = append(deleted[:i], deleted[i+1:]...)
				continue
			} else if resp == http.StatusNotFound {
				log.Trace().Msgf("photo %s not found on google photos, but is in local folder, it was probably deleted or removed from album", imageId)
			} else {
				return fmt.Errorf("unexpected response for %s: %v", imageId, resp)
			}
			i++
		}
		if len(deleted) > 0 {
			log.Info().Msgf("folders found for %d local photos that don't exist on google photos (in album if using -album), list saved to .removed", len(deleted))
			if err := os.WriteFile(path.Join(s.DownloadDir, ".removed"), []byte(strings.Join(deleted, "\n")), 0644); err != nil {
				return err
			}
		}
	}
	return nil
}

// GetPhotoUrl returns the URL for a photo
func GetPhotoUrl(s *types.Session, imageId string) string {
	return session.GphotosURL + s.UserPath + s.AlbumPath + "/photo/" + imageId
}

// GetPhotoNodeSelector returns the CSS selector for photo nodes
func GetPhotoNodeSelector(s *types.Session) string {
	return fmt.Sprintf(`a[href^=".%s/photo/"]`, s.AlbumPath)
}

// GetContentOfFirstVisibleNodeScript returns JavaScript to get content of first visible node
func GetContentOfFirstVisibleNodeScript(sel string, imageId string) string {
	return fmt.Sprintf(`[...document.querySelectorAll('[data-p*="%s"] %s')].filter(x => x.checkVisibility()).map(x => x.textContent)[0] || ''`, imageId, sel)
}
