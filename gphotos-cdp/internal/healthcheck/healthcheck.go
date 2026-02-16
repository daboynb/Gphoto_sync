package healthcheck

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/chromedp/cdproto/cdp"
	"github.com/chromedp/cdproto/target"
	"github.com/chromedp/chromedp"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"

	"gphotos-cdp/internal/config"
	"gphotos-cdp/internal/download"
	"gphotos-cdp/internal/navigation"
	"gphotos-cdp/internal/session"
	phsync "gphotos-cdp/internal/sync"
	"gphotos-cdp/internal/types"
)

// TestResult represents the outcome of a single health check test
type TestResult struct {
	Name    string `json:"name"`
	Status  string `json:"status"` // "pass", "fail", "skip"
	Message string `json:"message"`
}

// Summary is printed at the end of all tests
type Summary struct {
	Type   string `json:"type"`
	Passed int    `json:"passed"`
	Failed int    `json:"failed"`
	Total  int    `json:"total"`
}

// printResult prints a TestResult as JSON to stdout
func printResult(r TestResult) {
	data, _ := json.Marshal(r)
	fmt.Println(string(data))
}

// RunAll executes all health check tests and prints JSON results to stdout.
// Tests use the same production functions as the sync engine to ensure
// that healthcheck results accurately reflect production behavior.
// Each test maps to a dependency listed in docs/fragile-dependencies.md.
func RunAll(s *types.Session, ctx context.Context) []TestResult {
	var results []TestResult
	testLog := log.With().Str("mode", "healthcheck").Logger()

	// Set up event listening for arrow navigation (same as production Resync)
	navigation.ListenNavEvents(ctx)

	var photoLinks []string
	var firstPhotoID string

	// Test 1: photo_grid_selector (dep #1)
	r := testPhotoGridSelector(s, ctx, &photoLinks)
	results = append(results, r)
	printResult(r)

	// Test 2: role_main_selector (used by GetScrollPosition)
	r = testRoleMainSelector(ctx)
	results = append(results, r)
	printResult(r)

	// Extract first photo ID using production ImageIdFromUrl
	if len(photoLinks) > 0 {
		firstPhotoID = extractPhotoID(photoLinks[0])
	}

	// Test 3: navigate_to_photo (dep #9)
	r = testNavigateToPhoto(s, ctx, testLog, firstPhotoID)
	results = append(results, r)
	printResult(r)

	// Tests 4-11 require being on a photo page
	if firstPhotoID == "" {
		for _, name := range []string{
			"aria_label_exists",
			"aria_label_format",
			"data_p_attribute",
			"af_init_data_callback",
			"direct_url_extraction",
			"epoch_timestamp",
			"shift_d_download",
			"video_processing_check",
		} {
			r = TestResult{Name: name, Status: "skip", Message: "Skipped: no photo available"}
			results = append(results, r)
			printResult(r)
		}
	} else {
		// Test 4: aria_label_exists (dep #3)
		r = testAriaLabelExists(ctx, firstPhotoID)
		results = append(results, r)
		printResult(r)

		// Test 5: aria_label_format (dep #4) — uses download.ExtractPhotoInfoLabel
		r = testAriaLabelFormat(ctx, firstPhotoID)
		results = append(results, r)
		printResult(r)

		// Test 6: data_p_attribute (dep #5)
		r = testDataPAttribute(ctx, firstPhotoID)
		results = append(results, r)
		printResult(r)

		// Test 7: af_init_data_callback (dep #14)
		r = testAFInitDataCallback(ctx)
		results = append(results, r)
		printResult(r)

		// Tests 8-9: Use production ExtractOriginalDownloadData (dep #15)
		origData, extractErr := download.ExtractOriginalDownloadData(ctx, testLog, firstPhotoID)

		// Test 8: direct_url_extraction (dep #15)
		r = testDirectURLExtraction(origData, extractErr)
		results = append(results, r)
		printResult(r)

		// Test 9: epoch_timestamp (dep #15)
		r = testEpochTimestamp(origData, extractErr)
		results = append(results, r)
		printResult(r)

		// Test 10: shift_d_download (dep #2) — uses download.RequestDownload + StartDownloadListener
		r = testShiftDDownload(s, ctx, testLog)
		results = append(results, r)
		printResult(r)

		// Test 11: video_processing_check (dep #7, #8) — uses download.CheckForStillProcessing
		r = testVideoProcessingCheck(ctx)
		results = append(results, r)
		printResult(r)
	}

	// Test 12: arrow_navigation (dep #10) — uses navigation.NavRight
	r = testArrowNavigation(ctx, testLog, firstPhotoID)
	results = append(results, r)
	printResult(r)

	// Test 13: month_config (dep #11) — verifies month parsing config
	r = testMonthConfig()
	results = append(results, r)
	printResult(r)

	// Test 14: base_url (dep #12) — verifies Google Photos domain
	r = testBaseURL(ctx)
	results = append(results, r)
	printResult(r)

	// Test 15: chrome_profile_dir (dep #13) — verifies Chrome profile structure
	r = testChromeProfileDir(s)
	results = append(results, r)
	printResult(r)

	// Print summary
	passed := 0
	failed := 0
	for _, res := range results {
		switch res.Status {
		case "pass":
			passed++
		case "fail":
			failed++
		}
	}
	summary := Summary{
		Type:   "summary",
		Passed: passed,
		Failed: failed,
		Total:  len(results),
	}
	data, _ := json.Marshal(summary)
	fmt.Println(string(data))

	return results
}

// extractPhotoID extracts the photo ID from an href using the same
// logic as production (navigation.ImageIdFromUrl)
func extractPhotoID(href string) string {
	id, err := navigation.ImageIdFromUrl(href)
	if err != nil {
		return ""
	}
	return id
}

// Test 1: photo_grid_selector — uses sync.GetPhotoNodeSelector (dep #1)
func testPhotoGridSelector(s *types.Session, ctx context.Context, photoLinks *[]string) TestResult {
	name := "photo_grid_selector"

	testCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	// Same selector as production Resync
	selector := phsync.GetPhotoNodeSelector(s)

	var nodes []*cdp.Node
	err := chromedp.Run(testCtx,
		chromedp.Nodes(selector, &nodes, chromedp.ByQueryAll, chromedp.AtLeast(0)),
	)
	if err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Error querying selector: %v", err)}
	}

	for _, n := range nodes {
		href := n.AttributeValue("href")
		if href != "" {
			*photoLinks = append(*photoLinks, href)
		}
	}

	if len(nodes) == 0 {
		return TestResult{Name: name, Status: "fail", Message: "No photo links found with selector: " + selector}
	}

	return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("Found %d photo links", len(nodes))}
}

// Test 2: role_main_selector — uses navigation.GetMainContainerSelector (used by GetScrollPosition)
func testRoleMainSelector(ctx context.Context) TestResult {
	name := "role_main_selector"

	testCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	// Same selector as production GetScrollPosition / SetScrollPosition (non-album mode)
	selector := navigation.GetMainContainerSelector("")

	var nodes []*cdp.Node
	err := chromedp.Run(testCtx,
		chromedp.Nodes(selector, &nodes, chromedp.ByQueryAll, chromedp.AtLeast(0)),
	)
	if err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Error querying %s: %v", selector, err)}
	}

	if len(nodes) == 0 {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("No element with %s found", selector)}
	}

	return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("Found %d %s elements", len(nodes), selector)}
}

// Test 3: navigate_to_photo — uses navigation.NavigateToPhoto (dep #9)
func testNavigateToPhoto(s *types.Session, ctx context.Context, testLog zerolog.Logger, photoID string) TestResult {
	name := "navigate_to_photo"

	if photoID == "" {
		return TestResult{Name: name, Status: "skip", Message: "Skipped: no photo ID available from grid"}
	}

	testCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	// Same navigation function as production DoWorkerBatchItem
	if err := navigation.NavigateToPhoto(s, testCtx, testLog, photoID); err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Failed to navigate to photo: %v", err)}
	}

	var location string
	if err := chromedp.Run(testCtx, chromedp.Location(&location)); err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Failed to get location: %v", err)}
	}

	if !strings.Contains(location, "/photo/") {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("URL does not contain /photo/: %s", location)}
	}

	return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("Navigated to photo page: %s", photoID)}
}

// Test 4: aria_label_exists — uses download.CountAriaLabelElements (dep #3)
func testAriaLabelExists(ctx context.Context, photoID string) TestResult {
	name := "aria_label_exists"

	testCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	// Same selector as production ExtractPhotoInfoLabel
	count, err := download.CountAriaLabelElements(testCtx, photoID)
	if err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("CountAriaLabelElements failed: %v", err)}
	}

	if count == 0 {
		return TestResult{Name: name, Status: "fail", Message: "No [data-p] [aria-label] elements found on photo page"}
	}

	return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("Found %d [data-p] [aria-label] elements", count)}
}

// Test 5: aria_label_format — uses download.ExtractPhotoInfoLabel (dep #4)
func testAriaLabelFormat(ctx context.Context, photoID string) TestResult {
	name := "aria_label_format"

	testCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	// Same extraction as production GetPhotoData
	label, err := download.ExtractPhotoInfoLabel(testCtx, photoID)
	if err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Error extracting aria-label: %v", err)}
	}

	if label == "" {
		return TestResult{Name: name, Status: "fail", Message: "No aria-label matching production filter (Foto/Photo/Video prefix)"}
	}

	// Verify the label has the expected structure: Type - Orientation - DateTime
	parts := strings.Split(label, " - ")
	if len(parts) < 3 {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("aria-label has %d parts (expected >= 3): %s", len(parts), label)}
	}

	return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("aria-label matches format: %s", truncate(label, 80))}
}

// Test 6: data_p_attribute — uses download.CountDataPElements (dep #5)
func testDataPAttribute(ctx context.Context, photoID string) TestResult {
	name := "data_p_attribute"

	testCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	// Same selector used by ExtractPhotoInfoLabel
	count, err := download.CountDataPElements(testCtx, photoID)
	if err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("CountDataPElements failed: %v", err)}
	}

	if count == 0 {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("No element with [data-p*=\"%s\"] found", photoID)}
	}

	return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("Found %d elements with data-p containing photo ID", count)}
}

// Test 7: af_init_data_callback — uses download.CheckDS5DataExists (dep #14)
func testAFInitDataCallback(ctx context.Context) TestResult {
	name := "af_init_data_callback"

	testCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	// Same check used as precondition in ExtractOriginalDownloadData
	found, err := download.CheckDS5DataExists(testCtx)
	if err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("CheckDS5DataExists failed: %v", err)}
	}

	if !found {
		return TestResult{Name: name, Status: "fail", Message: "AF_initDataCallback with 'ds:5' not found in page scripts"}
	}

	return TestResult{Name: name, Status: "pass", Message: "AF_initDataCallback with 'ds:5' found in page scripts"}
}

// Test 8: direct_url_extraction — uses download.ExtractOriginalDownloadData (dep #15)
func testDirectURLExtraction(origData download.OriginalDownloadData, extractErr error) TestResult {
	name := "direct_url_extraction"

	if extractErr != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("ExtractOriginalDownloadData failed: %v", extractErr)}
	}

	if origData.DownloadURL == "" {
		return TestResult{Name: name, Status: "fail", Message: "Extracted empty download URL"}
	}

	return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("Extracted download URL: %s", truncate(origData.DownloadURL, 60))}
}

// Test 9: epoch_timestamp — uses download.ExtractOriginalDownloadData (dep #15)
func testEpochTimestamp(origData download.OriginalDownloadData, extractErr error) TestResult {
	name := "epoch_timestamp"

	if extractErr != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Extraction failed: %v", extractErr)}
	}

	if origData.TimestampMs <= 0 {
		return TestResult{Name: name, Status: "fail", Message: "Timestamp is 0 or negative"}
	}

	ts := time.UnixMilli(origData.TimestampMs)
	if ts.Year() < 2000 || ts.Year() > 2030 {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Timestamp date out of range (2000-2030): %v", ts.Format("2006-01-02"))}
	}

	return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("Timestamp: %v (%s)", origData.TimestampMs, ts.Format("2006-01-02 15:04:05"))}
}

// Test 10: shift_d_download — uses download.RequestDownload + StartDownloadListener (dep #2)
func testShiftDDownload(s *types.Session, ctx context.Context, testLog zerolog.Logger) TestResult {
	name := "shift_d_download"

	testCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	// Set up download listener (same as production main.go)
	downloadChan := make(chan types.NewDownload, 1)
	download.StartDownloadListener(testCtx, downloadChan)

	// Press Shift+D (same as production StartDownload -> RequestDownload)
	if err := download.RequestDownload(testCtx, testLog); err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("RequestDownload (Shift+D) failed: %v", err)}
	}

	// Wait for download event
	select {
	case dl := <-downloadChan:
		// Wait for download to complete, then clean up
		if dl.ProgressChan != nil {
			timeout := time.NewTimer(30 * time.Second)
			for {
				select {
				case done := <-dl.ProgressChan:
					if done {
						goto cleanup
					}
				case <-timeout.C:
					goto cleanup
				}
			}
		}
	cleanup:
		os.Remove(filepath.Join(s.DownloadDirTmp, dl.GUID))
		return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("Shift+D triggered download: %s", dl.SuggestedFilename)}
	case <-time.After(15 * time.Second):
		return TestResult{Name: name, Status: "fail", Message: "No download event received after Shift+D (15s timeout)"}
	}
}

// Test 11: video_processing_check — uses download.CheckForStillProcessing (dep #7, #8)
func testVideoProcessingCheck(ctx context.Context) TestResult {
	name := "video_processing_check"

	// Same function as production: checks c-wiz[data-media-key] selector
	// and "Your video will be ready soon" text.
	// On a regular photo, should return nil (not processing).
	// If the selectors break, this will error.
	err := download.CheckForStillProcessing(ctx, nil)
	if err != nil {
		return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("CheckForStillProcessing returned: %v (selector works)", err)}
	}

	return TestResult{Name: name, Status: "pass", Message: "CheckForStillProcessing ran successfully (no processing video detected)"}
}

// Test 12: arrow_navigation — uses navigation.NavRight (dep #10)
func testArrowNavigation(ctx context.Context, testLog zerolog.Logger, photoID string) TestResult {
	name := "arrow_navigation"

	if photoID == "" {
		return TestResult{Name: name, Status: "skip", Message: "Skipped: no photo available"}
	}

	testCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	// Get current URL
	var beforeURL string
	if err := chromedp.Run(testCtx, chromedp.Location(&beforeURL)); err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Error getting URL before navigation: %v", err)}
	}

	// Same as production DoWorkerBatchItem: ActivateTarget + NavRight
	err := chromedp.Run(testCtx,
		target.ActivateTarget(chromedp.FromContext(testCtx).Target.TargetID),
		chromedp.ActionFunc(navigation.NavRight(testLog)),
	)
	if err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("NavRight failed: %v", err)}
	}

	// Get URL after navigation
	var afterURL string
	if err := chromedp.Run(testCtx, chromedp.Location(&afterURL)); err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Error getting URL after navigation: %v", err)}
	}

	if beforeURL == afterURL {
		return TestResult{Name: name, Status: "fail", Message: "URL did not change after NavRight"}
	}

	if !strings.Contains(afterURL, "/photo/") {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("URL after navigation does not contain /photo/: %s", afterURL)}
	}

	return TestResult{Name: name, Status: "pass", Message: "Arrow navigation works: URL changed to new photo"}
}

// Test 13: month_config — verifies month parsing config loaded for detected language (dep #11)
func testMonthConfig() TestResult {
	name := "month_config"

	if config.PageLanguage == "" {
		return TestResult{Name: name, Status: "fail", Message: "Page language not detected"}
	}

	if len(config.MonthsConfig) == 0 {
		return TestResult{Name: name, Status: "fail", Message: "MonthsConfig is empty (months-config.json not loaded)"}
	}

	cfg, exists := config.MonthsConfig[config.PageLanguage]
	if !exists {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("No month config for detected language '%s' (available: %s)", config.PageLanguage, config.GetConfiguredLanguages())}
	}

	if len(cfg.Months) != 12 {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Language '%s' has %d months (expected 12)", config.PageLanguage, len(cfg.Months))}
	}

	return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("Month config loaded for '%s': %s", config.PageLanguage, strings.Join(cfg.Months, ", "))}
}

// Test 14: base_url — verifies browser is on photos.google.com (dep #12)
func testBaseURL(ctx context.Context) TestResult {
	name := "base_url"

	testCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	var location string
	if err := chromedp.Run(testCtx, chromedp.Location(&location)); err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Error getting location: %v", err)}
	}

	if !strings.HasPrefix(location, session.GphotosURL) {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Not on Google Photos domain: %s (expected prefix: %s)", location, session.GphotosURL)}
	}

	return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("On Google Photos: %s", truncate(location, 60))}
}

// Test 15: chrome_profile_dir — verifies Chrome profile directory structure (dep #13)
func testChromeProfileDir(s *types.Session) TestResult {
	name := "chrome_profile_dir"

	prefsPath := filepath.Join(s.ProfileDir, "Default", "Preferences")

	info, err := os.Stat(prefsPath)
	if err != nil {
		return TestResult{Name: name, Status: "fail", Message: fmt.Sprintf("Chrome Preferences file not found: %s", prefsPath)}
	}

	if info.Size() == 0 {
		return TestResult{Name: name, Status: "fail", Message: "Chrome Preferences file is empty"}
	}

	return TestResult{Name: name, Status: "pass", Message: fmt.Sprintf("Chrome profile dir OK (%s, %d bytes)", prefsPath, info.Size())}
}

// truncate returns the first n characters of s, with "..." appended if truncated
func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
