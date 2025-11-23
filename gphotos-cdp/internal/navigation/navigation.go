package navigation

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"
	"github.com/chromedp/cdproto/network"
	"github.com/chromedp/cdproto/page"
	"github.com/chromedp/cdproto/target"
	"github.com/chromedp/chromedp"
	"github.com/chromedp/chromedp/kb"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"

	"gphotos-cdp/internal/session"
	"gphotos-cdp/internal/types"
)

const tick = 500 * time.Millisecond

var (
	ErrNavigateAborted = errors.New("navigate aborted")
	muTabActivity      sync.Mutex
	queuedTabLocks     int64
)

// FirstNav does either of:
// 1) if a specific photo URL was specified with *startFlag, it navigates to it
// 2) if the last session marked what was the most recent downloaded photo, it navigates to it
// 3) otherwise it jumps to the end of the timeline (i.e. the oldest photo)
func FirstNav(s *types.Session, ctx context.Context) error {
	log.Info().Msg("firstNav: navigating to Google Photos...")
	if s.UserPath+s.AlbumPath != "" {
		log.Info().Msgf("firstNav: navigating to album/user path: %s%s", s.UserPath, s.AlbumPath)
		if err := NavigateWithAction(s, ctx, log.Logger, chromedp.Navigate(session.GphotosURL+s.UserPath+s.AlbumPath), "to start", 20000*time.Millisecond, 5); err != nil {
			return err
		}
		chromedp.WaitReady("body", chromedp.ByQuery).Do(ctx)
	}

	log.Info().Msg("firstNav: setting first item...")
	// This is only used to ensure page is loaded
	if err := SetFirstItem(s, ctx); err != nil {
		log.Error().Msgf("firstNav: failed to set first item: %v", err)
		return err
	}
	log.Info().Msg("firstNav: first item set successfully")

	var location string
	if err := chromedp.Location(&location).Do(ctx); err != nil {
		return err
	}
	log.Debug().Msgf("location: %v", location)

	return nil
}

// SetFirstItem looks for the first item, and sets it as s.firstItem.
// We always run it first even for code paths that might not need s.firstItem,
// because we also run it for the side-effect of waiting for the first page load to
// be done, and to be ready to receive scroll key events.
func SetFirstItem(s *types.Session, ctx context.Context) error {
	// wait for page to be loaded, i.e. that we can make an element active by using
	// the right arrow key.
	var firstItem string
	attempts := 0
	maxAttempts := 60 // 60 attempts * 500ms = 30 seconds timeout

	log.Info().Msg("setFirstItem: waiting for page to load and find first photo...")
	for {
		attempts++
		if attempts > maxAttempts {
			session.CaptureScreenshot(ctx, filepath.Join(s.DownloadDir, "setFirstItem-timeout"))
			return errors.New("timeout waiting for first item to be found (page may not have loaded)")
		}

		log.Debug().Msgf("setFirstItem: attempt %d/%d to find first item", attempts, maxAttempts)
		attributes := make(map[string]string)
		if err := chromedp.Run(ctx,
			chromedp.KeyEvent(kb.ArrowRight),
			chromedp.Sleep(tick),
			chromedp.Attributes(`document.activeElement`, &attributes, chromedp.ByJSPath)); err != nil {
			log.Error().Msgf("setFirstItem: error getting attributes: %v", err)
			return err
		}

		log.Debug().Msgf("setFirstItem: found %d attributes on active element", len(attributes))
		if len(attributes) == 0 {
			time.Sleep(tick)
			continue
		}

		photoHref, ok := attributes["href"]
		if ok {
			log.Debug().Msgf("setFirstItem: checking href: %s", photoHref)
			res, err := ImageIdFromUrl(photoHref)
			if err == nil {
				firstItem = res
				log.Info().Msgf("setFirstItem: found first item: %s", firstItem)
				break
			}
			log.Debug().Msgf("setFirstItem: href is not a valid image URL: %v", err)
		} else {
			log.Debug().Msg("setFirstItem: active element has no href attribute")
		}
		time.Sleep(tick)
	}
	log.Info().Msgf("page loaded, most recent item in the feed is: %s", firstItem)
	return nil
}

// NavToEnd scrolls down to the end of the page, i.e. to the oldest items.
func NavToEnd(ctx context.Context) error {
	// try jumping to the end of the page. detect we are there and have stopped
	// moving when two consecutive screenshots are identical.
	var previousScr, scr []byte
	for {
		if err := chromedp.Run(ctx,
			chromedp.KeyEvent(kb.PageDown),
			chromedp.KeyEvent(kb.End),
			chromedp.Sleep(tick*time.Duration(5)),
			chromedp.CaptureScreenshot(&scr),
		); err != nil {
			return err
		}
		if previousScr == nil {
			previousScr = scr
			continue
		}
		if string(previousScr) == string(scr) {
			break
		}
		previousScr = scr
	}

	log.Debug().Msg("successfully jumped to the end")

	return nil
}

// NavigateToPhoto navigates to the photo page for the given image ID.
func NavigateToPhoto(s *types.Session, ctx context.Context, log zerolog.Logger, imageId string) error {
	photoUrl := session.GphotosURL + s.UserPath + s.AlbumPath + "/photo/" + imageId
	return NavigateWithAction(s, ctx, log, chromedp.Navigate(photoUrl), "to item "+imageId, 10000*time.Millisecond, 5)
}

// NavigateWithAction navigates using a chromedp action with retry logic
func NavigateWithAction(s *types.Session, ctx context.Context, log zerolog.Logger, action chromedp.Action, desc string, timeout time.Duration, retries int) error {
	log.Trace().Msgf("navigating %s", desc)
	var resp *network.Response
	var err error
	for i := 0; i < retries; i++ {
		func() {
			ctx, cancel := context.WithTimeout(ctx, timeout)
			defer cancel()
			target.ActivateTarget(chromedp.FromContext(ctx).Target.TargetID)
			resp, err = chromedp.RunResponse(ctx, action)
		}()
		if (err != nil && strings.Contains(err.Error(), "net::ERR_ABORTED")) ||
			(err != nil && errors.Is(err, context.DeadlineExceeded) && ctx.Err() == nil) ||
			(err == nil && (resp != nil && resp.Status == 504)) {
			err = fmt.Errorf("%w: %w", ErrNavigateAborted, err)
		}
		if errors.Is(err, ErrNavigateAborted) {
			// retry
			log.Warn().Msgf("error navigating %s: %s (response %v), will try again", desc, err.Error(), resp)
			time.Sleep(100 * time.Millisecond)
		} else {
			break
		}
	}
	if err != nil {
		return fmt.Errorf("error navigating %s: %w", desc, err)
	}
	if resp == nil {
		return nil
	} else if resp.Status == http.StatusOK {
		if err := chromedp.Run(ctx, chromedp.WaitReady("body", chromedp.ByQuery)); err != nil {
			return fmt.Errorf("error waiting for body: %w", err)
		}
	} else {
		return fmt.Errorf("unexpected response navigating %s: %v", desc, resp.Status)
	}
	return nil
}

// NavRight navigates to the next item to the right
func NavRight(log zerolog.Logger) func(ctx context.Context) error {
	return func(ctx context.Context) error {
		log.Debug().Msg("Navigating right")
		return navWithAction(ctx, chromedp.KeyEvent(kb.ArrowRight))
	}
}

// navWithAction performs a navigation action and waits for completion
func navWithAction(ctx context.Context, action chromedp.Action) error {
	cl := session.GetContextData(ctx)
	st := time.Now()
	cl.MuNavWaiting.Lock()
	cl.ListenEvents = true
	cl.MuNavWaiting.Unlock()
	action.Do(ctx)
	cl.MuNavWaiting.Lock()
	cl.NavWaiting = true
	cl.MuNavWaiting.Unlock()
	t := time.NewTimer(2 * time.Minute)
	select {
	case <-cl.NavDone:
		if !t.Stop() {
			<-t.C
		}
	case <-t.C:
		return errors.New("timeout waiting for navigation")
	}
	cl.MuNavWaiting.Lock()
	cl.NavWaiting = false
	cl.MuNavWaiting.Unlock()
	log.Debug().Int64("duration", time.Since(st).Milliseconds()).Msgf("navigation done")
	return nil
}

// SetScrollPosition sets the scroll position of the main element
func SetScrollPosition(ctx context.Context, pos float64, albumIdFlag string) error {
	var mainSel string
	if len(albumIdFlag) > 1 {
		mainSel = `c-wiz c-wiz c-wiz`
	} else {
		mainSel = `[role="main"]`
	}

	if err := chromedp.Evaluate(fmt.Sprintf(`
		(function() {
			var main = [...document.querySelectorAll('%s')].filter(x => x.querySelector('a[href*="/photo/"]') && getComputedStyle(x).visibility != 'hidden')[0];
			const scrollTarget = %f;
			main.scrollTo(0, main.scrollHeight*scrollTarget);
		})();
	`, mainSel, pos), nil).Do(ctx); err != nil {
		return err
	}
	return nil
}

// GetScrollPosition gets the current scroll position
func GetScrollPosition(ctx context.Context, sliderPos *float64, albumIdFlag string) error {
	var mainSel string
	if len(albumIdFlag) > 1 {
		mainSel = `c-wiz c-wiz c-wiz`
	} else {
		mainSel = `[role="main"]`
	}

	var err error
	for i := 0; i < 3; i++ {
		func() {
			ctx, cancel := context.WithTimeout(ctx, 4000*time.Millisecond)
			defer cancel()
			if err != nil {
				unlock := AcquireTabLock(log.Logger, "getScrollPosition")
				defer unlock()
				target.ActivateTarget(chromedp.FromContext(ctx).Target.TargetID).Do(ctx)
			}
			err = chromedp.Run(ctx, chromedp.Evaluate(fmt.Sprintf(`
				(function() {
					var main = [...document.querySelectorAll('%s')].filter(x => x.querySelector('a[href*="/photo/"]') && getComputedStyle(x).visibility != 'hidden')[0];
					return main ? (main.scrollTop+0.000001)/(main.scrollHeight-main.clientHeight+0.000001) : 0.0;
				})()`, mainSel), &sliderPos))
		}()
		if err == nil {
			break
		}
		log.Warn().Err(err).Msgf("error getting scroll position")
	}

	return err
}

// ListenNavEvents listens for navigation events
func ListenNavEvents(ctx context.Context) {
	cl := session.GetContextData(ctx)
	chromedp.ListenTarget(ctx, func(ev interface{}) {
		cl.MuNavWaiting.RLock()
		listen := cl.ListenEvents
		cl.MuNavWaiting.RUnlock()
		if !listen {
			return
		}
		switch ev.(type) {
		case *page.EventNavigatedWithinDocument:
			go func() {
				for {
					cl.MuNavWaiting.RLock()
					waiting := cl.NavWaiting
					cl.MuNavWaiting.RUnlock()
					if waiting {
						cl.NavDone <- true
						break
					}
					time.Sleep(10 * time.Millisecond)
				}
			}()
		}
	})
}

// AcquireTabLock acquires the tab activity lock
func AcquireTabLock(log zerolog.Logger, forWhat string) func() {
	if forWhat != "" {
		forWhat = fmt.Sprintf(" %s", forWhat)
	}
	log.Trace().Msgf("acquiring tab lock%s", forWhat)
	start := time.Now()
	atomic.AddInt64(&queuedTabLocks, 1)
	muTabActivity.Lock()
	atomic.AddInt64(&queuedTabLocks, -1)
	dur := time.Since(start)
	log.Debug().Int64("duration", dur.Milliseconds()).Msgf("acquired tab lock%s", forWhat)
	if dur > 10000*time.Millisecond {
		log.Warn().Int64("duration", dur.Milliseconds()).Msgf("acquiring tab lock%s took %d ms (%d in queue), consider reducing worker count", forWhat, dur.Milliseconds(), atomic.LoadInt64(&queuedTabLocks))
	}
	return muTabActivity.Unlock
}

// ImageIdFromUrl extracts the image ID from a Google Photos URL
func ImageIdFromUrl(location string) (string, error) {
	// Parse the URL
	u, err := url.Parse(location)
	if err != nil {
		return "", fmt.Errorf("invalid URL %v: %w", location, err)
	}

	// Split the path into segments
	parts := strings.Split(strings.Trim(u.Path, "/"), "/")

	// Look for "photo" segment and ensure there's a following segment
	for i := 0; i < len(parts)-1; i++ {
		if parts[i] == "photo" {
			return parts[i+1], nil
		}
	}
	return "", fmt.Errorf("could not find /photo/{imageId} pattern in URL: %v", location)
}

// DoActionWithTimeout executes an action with a timeout
func DoActionWithTimeout(ctx context.Context, action chromedp.Action, timeout time.Duration) error {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	if err := action.Do(ctx); err != nil {
		return err
	}
	return nil
}
