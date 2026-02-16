package session

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/chromedp/cdproto/browser"
	"github.com/chromedp/cdproto/cdp"
	"github.com/chromedp/chromedp"
	"github.com/chromedp/chromedp/kb"
	"github.com/rs/zerolog/log"

	"gphotos-cdp/internal/config"
	"gphotos-cdp/internal/types"
	"gphotos-cdp/internal/utils"
)

const (
	GphotosURL = "https://photos.google.com"
)

var (
	// Flags - questi sono riferimenti alle flag definite in main.go
	ProfileFlag  *string
	HeadlessFlag *bool
	AlbumIdFlag  *string
)

// NewSession creates a new Chrome session
func NewSession(downloadDirFlag, profileFlag, albumIdFlag *string) (*types.Session, error) {
	albumPath := ""
	userPath := ""
	if *albumIdFlag != "" {
		i := strings.LastIndex(*albumIdFlag, "/")
		if i != -1 {
			albumPath = "/" + *albumIdFlag
			*albumIdFlag = albumPath[i+1:]
		} else {
			albumPath = "/album/" + *albumIdFlag
		}
	}
	if strings.HasPrefix(albumPath, "/u/") {
		a := strings.Index(albumPath[3:], "/")
		if a == -1 {
			userPath = albumPath
			albumPath = ""
		} else {
			userPath = albumPath[:a+3]
			albumPath = albumPath[a+3:]
		}
	}
	log.Info().Msgf("syncing files at root dir %s%s%s", GphotosURL, userPath, albumPath)
	var dir string
	if *profileFlag != "" {
		dir = *profileFlag
		if err := os.MkdirAll(dir, 0700); err != nil {
			return nil, err
		}
	} else {
		var err error
		dir, err = os.MkdirTemp("", "gphotos-cdp")
		if err != nil {
			return nil, err
		}
	}
	downloadDir := *downloadDirFlag
	if downloadDir == "" {
		downloadDir = filepath.Join(os.Getenv("HOME"), "Downloads", "gphotos-cdp")
	}
	if err := os.MkdirAll(downloadDir, 0700); err != nil {
		return nil, err
	}

	downloadDirEntries, err := os.ReadDir(downloadDir)
	if err != nil {
		return nil, err
	}

	downloadDirTmp := filepath.Join(downloadDir, "tmp")
	if err := os.MkdirAll(downloadDirTmp, 0700); err != nil {
		return nil, err
	}

	// Initialize downloaded IDs manager
	downloadedIds, err := utils.NewDownloadedIdsManager(downloadDir)
	if err != nil {
		return nil, fmt.Errorf("failed to create downloaded IDs manager: %w", err)
	}

	s := &types.Session{
		ProfileDir:      dir,
		DownloadDir:     downloadDir,
		DownloadDirTmp:  downloadDirTmp,
		GlobalErrChan:   make(chan error, 1),
		UserPath:        userPath,
		AlbumPath:       albumPath,
		NewDownloadChan: make(chan types.NewDownload),
		DownloadedIds:   downloadedIds,
	}

	// Legacy: Load existing directories into ExistingItems (for CheckForRemovedFiles compatibility)
	for _, e := range downloadDirEntries {
		if e.IsDir() && e.Name() != "tmp" {
			s.ExistingItems.Store(e.Name(), struct{}{})
		}
	}

	log.Info().Msgf("Loaded %d previously downloaded items", downloadedIds.Count())

	return s, nil
}

// NewWindow creates a new Chrome window with the appropriate settings
func NewWindow(s *types.Session, headlessFlag *bool) (context.Context, context.CancelFunc) {
	log.Info().Msgf("starting Chrome browser")

	// Remove stale Chrome lock files from the profile directory.
	// These are left behind when Chrome doesn't shut down cleanly
	// (e.g. container killed) and prevent Chrome from starting again.
	for _, lockFile := range []string{"SingletonLock", "SingletonSocket", "SingletonCookie"} {
		p := filepath.Join(s.ProfileDir, lockFile)
		if err := os.Remove(p); err == nil {
			log.Warn().Msgf("removed stale lock file: %s", lockFile)
		}
	}

	// Let's use as a base for allocator options (It implies Headless)
	opts := append(chromedp.DefaultExecAllocatorOptions[:],
		chromedp.UserDataDir(s.ProfileDir),
		chromedp.Flag("disable-blink-features", "AutomationControlled"),
		chromedp.Flag("lang", "en-US,en"),
		chromedp.Flag("accept-lang", "en-US,en"),
		chromedp.Flag("window-size", "1920,1080"),
		chromedp.Flag("enable-logging", true),
		chromedp.Flag("user-agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36"),
	)

	if !*headlessFlag {
		// undo the three opts in chromedp.Headless() which is included in DefaultExecAllocatorOptions
		opts = append(opts, chromedp.Flag("headless", false))
		opts = append(opts, chromedp.Flag("hide-scrollbars", false))
		opts = append(opts, chromedp.Flag("mute-audio", false))
	}

	ctx, cancel := chromedp.NewExecAllocator(context.Background(), opts...)
	s.ChromeExecCancel = cancel

	ctx, cancel = chromedp.NewContext(ctx,
		chromedp.WithLogf(cdpLog),
		chromedp.WithDebugf(cdpDebug),
		chromedp.WithErrorf(cdpError),
	)
	s.ParentContext = ctx
	ctx = SetContextData(ctx)

	if err := chromedp.Run(ctx,
		chromedp.ActionFunc(func(ctx context.Context) error {
			c := chromedp.FromContext(ctx)
			if err := browser.SetDownloadBehavior(browser.SetDownloadBehaviorBehaviorAllowAndName).WithDownloadPath(s.DownloadDirTmp).WithEventsEnabled(true).
				// use the Browser executor so that it does not pass "sessionId" to the command.
				Do(cdp.WithExecutor(ctx, c.Browser)); err != nil {
				return err
			}

			_, product, _, _, _, err := browser.GetVersion().Do(ctx)
			if err != nil {
				return err
			}
			log.Info().Msgf("Browser version: %s", product)
			return nil
		}),
	); err != nil {
		panic(err)
	}

	return ctx, cancel
}

// Shutdown closes the Chrome session
func Shutdown(s *types.Session) {
	s.ChromeExecCancel()
}

// cdpLog logs CDP messages
func cdpLog(format string, v ...any) {
	if !strings.Contains(format, "unhandled") && !strings.Contains(format, "event") {
		log.Debug().Msgf(format, v...)
	}
}

// cdpDebug logs CDP debug messages
func cdpDebug(format string, v ...any) {
	log.Trace().Msgf(format, v...)
}

// cdpError logs CDP error messages
func cdpError(format string, v ...any) {
	if !strings.Contains(format, "unhandled") && !strings.Contains(format, "event") {
		log.Error().Msgf(format, v...)
	}
}

// CleanDownloadDir removes all files (but not directories) from s.DownloadDirTmp
func CleanDownloadDir(s *types.Session) error {
	if s.DownloadDir == "" {
		return nil
	}
	entries, err := os.ReadDir(s.DownloadDirTmp)
	if err != nil {
		return err
	}
	for _, v := range entries {
		if v.IsDir() {
			continue
		}
		if err := os.Remove(filepath.Join(s.DownloadDirTmp, v.Name())); err != nil {
			return err
		}
	}
	return nil
}

// Login navigates to https://photos.google.com/login and waits for the user to have
// authenticated (or for 2 minutes to have elapsed).
func Login(s *types.Session, ctx context.Context, headlessFlag *bool) error {
	log.Info().Msg("starting authentication...")
	return chromedp.Run(ctx,
		chromedp.Navigate("https://photos.google.com/login"),
		// when we're not authenticated, the URL is actually
		// https://www.google.com/photos/about/ , so we rely on that to detect when we have
		// authenticated.
		chromedp.ActionFunc(func(ctx context.Context) error {
			tick := 2 * time.Second
			timeout := time.Now().Add(2 * time.Minute)
			var location string
			log.Info().Msg("waiting for authentication to complete...")
			for {
				if err := chromedp.Location(&location).Do(ctx); err != nil {
					return err
				}
				log.Debug().Msgf("current URL: %s", location)
				if strings.HasPrefix(location, GphotosURL) {
					log.Info().Msg("authentication successful!")
					return nil
				}
				if strings.Contains(location, "signinchooser") {
					log.Info().Msg("detected account chooser, selecting account...")
					userIndex := 0
					if s.UserPath != "" {
						userIndex, _ = strconv.Atoi(s.UserPath[2:])
					}
					if err := chromedp.Evaluate(`document.querySelector('[data-authuser][data-item-index="`+strconv.Itoa(userIndex)+`"]')?.click()`, nil).Do(ctx); err != nil {
						return err
					}
					time.Sleep(tick)
					continue
				}
				if strings.Contains(location, "signin/challenge/dp") {
					log.Info().Msgf("waiting for user to approve login with other device")
					time.Sleep(tick)
					continue
				}
				if strings.Contains(location, "signin/shadowdisambiguate") {
					// Option to continue with workspace account or private. If we see this, we assume the user wants to
					// use the first account listed. We can improve this later
					profileindex := os.Getenv("GPHOTOS_PROFILE_INDEX")
					if strings.EqualFold(profileindex, "") {
						profileindex = "0"
					}
					if err := chromedp.Click(`div[data-profileindex="`+profileindex+`"]`, chromedp.ByQuery).Do(ctx); err != nil {
						return err
					}
					time.Sleep(tick)
					continue
				}
				if strings.Contains(location, "signin/confirmidentifier") {
					// Click Next button
					if err := chromedp.Click(`div#identifierNext button`, chromedp.ByQuery).Do(ctx); err != nil {
						return err
					}
					time.Sleep(tick)
					continue
				}
				if strings.Contains(location, "signin/rejected") {
					log.Error().Msg("Google rejected automated login")
					return errors.New("google rejected automated login")
				}
				if strings.Contains(location, "signin/speedbump/passkeyenrollment") {
					// skip passkey enrollment, press "Not now" button (hardcoded English text)
					if err := chromedp.Click(`//button//span[contains(text(), "Not now")]`, chromedp.BySearch).Do(ctx); err != nil {
						return err
					}
					time.Sleep(tick)
					continue
				}
				var nodes []*cdp.Node
				email := os.Getenv("GPHOTOS_EMAIL")
				if email != "" {
					email_node := "#identifierId:not([type=hidden])"
					log.Debug().Msgf("checking for email node: %s", email_node)
					if err := chromedp.Nodes(email_node, &nodes, chromedp.ByQuery, chromedp.AtLeast(0)).Do(ctx); err != nil {
						return err
					}
					if len(nodes) > 0 {
						log.Info().Msgf("logging in with user email: %s", email)
						if err := chromedp.SendKeys(email_node, email+kb.Enter).Do(ctx); err != nil {
							return err
						}
						time.Sleep(tick)
						continue
					}
				}
				password := os.Getenv("GPHOTOS_PASSWORD")
				if password != "" {
					password_node := "input[name=Passwd]"
					log.Debug().Msgf("checking for password node: %s", password_node)
					if err := chromedp.Nodes(password_node, &nodes, chromedp.ByQuery, chromedp.AtLeast(0)).Do(ctx); err != nil {
						return err
					}
					if len(nodes) > 0 {
						log.Info().Msgf("logging in with user password")
						if err := chromedp.SendKeys(password_node, password+kb.Enter).Do(ctx); err != nil {
							return err
						}
						time.Sleep(tick * time.Duration(3))
						continue
					}
				}
				if *headlessFlag {
					CaptureScreenshot(ctx, filepath.Join(s.DownloadDir, "error"))
					return errors.New("authentication not possible in -headless mode, see error.png (URL=" + location + ")")
				}
				if time.Now().After(timeout) {
					return errors.New("timeout waiting for authentication")
				}
				log.Debug().Msgf("not yet authenticated, at: %v", location)
				time.Sleep(tick)
			}
		}),
		chromedp.ActionFunc(func(ctx context.Context) error {
			log.Info().Msg("successfully authenticated")
			return nil
		}),
	)
}

// GetLocale detects the locale of the Google Photos page
func GetLocale(ctx context.Context) (string, error) {
	var locale string

	err := chromedp.Run(ctx,
		chromedp.EvaluateAsDevTools(`
				(function() {
					// Try to get locale from html lang attribute
					const htmlLang = document.documentElement.lang;
					if (htmlLang) return htmlLang;

					// Try to get locale from meta tags
					const metaLang = document.querySelector('meta[property="og:locale"]');
					if (metaLang) return metaLang.content;

					// Try to get locale from Google's internal data
					const scripts = document.getElementsByTagName('script');
					for (const script of scripts) {
						if (script.text && script.text.includes('"locale"')) {
							const match = script.text.match(/"locale":\s*"([^"]+)"/);
							if (match) return match[1];
						}
					}

					return "unknown";
				})()
			`, &locale),
	)

	if err != nil {
		return "", fmt.Errorf("failed to detect page language: %w - this is required for date parsing", err)
	}

	log.Info().Msgf("detected page locale: %s", locale)

	// Store page language for month parsing
	config.PageLanguage = locale

	return locale, nil
}

// CheckLanguage checks if the detected language is supported and auto-extracts configuration if needed
func CheckLanguage(ctx context.Context) {
	var htmlLang string
	var browserLangs string

	// Get page language
	err := chromedp.Run(ctx,
		chromedp.Evaluate(`document.documentElement.lang || "unknown"`, &htmlLang),
	)
	if err != nil {
		log.Debug().Err(err).Msg("failed to get page language")
		return
	}

	// Get browser language preferences
	err = chromedp.Run(ctx,
		chromedp.Evaluate(`(navigator.languages || [navigator.language]).join(',')`, &browserLangs),
	)
	if err != nil {
		browserLangs = "unknown"
	}

	// Check if page language is supported in months-config.json
	if htmlLang != "unknown" && htmlLang != "" {
		if _, exists := config.MonthsConfig[htmlLang]; exists {
			log.Info().Msgf("✓ Page language: %s (supported) | Browser preferences: %s", htmlLang, browserLangs)
		} else {
			// Language not in config - auto-extract it
			log.Warn().Msgf("✗ Page language: %s (NOT in months-config.json) | Browser preferences: %s", htmlLang, browserLangs)
			log.Warn().Msgf("Currently configured languages: %s", config.GetConfiguredLanguages())
			log.Info().Msgf("Attempting to auto-extract language configuration for: %s", htmlLang)

			// Auto-extract language configuration
			cfg, err := AutoExtractLanguageConfig(ctx, htmlLang)
			if err != nil {
				log.Fatal().Err(err).Msgf("Failed to auto-extract language configuration for %s", htmlLang)
			}

			// Add to MonthsConfig
			config.MonthsConfig[htmlLang] = *cfg
			config.PageLanguage = htmlLang

			// Save to file
			if err := config.SaveMonthsConfig(); err != nil {
				log.Error().Err(err).Msg("Failed to save months-config.json, but continuing with extracted config in memory")
			}

			log.Info().Msgf("✓ Successfully auto-configured language: %s", htmlLang)
		}
	} else {
		log.Fatal().Msgf("Could not detect page language (detected: %s) | Browser preferences: %s\nDate parsing will fail without a known page language.", htmlLang, browserLangs)
	}
}

// AutoExtractLanguageConfig extracts language configuration from Google Photos
// Following exact same logic as console-extract.js
func AutoExtractLanguageConfig(ctx context.Context, lang string) (*config.MonthConfig, error) {
	log.Info().Msgf("Auto-extracting language configuration for: %s", lang)

	// Extract metadata - same as console-extract.js lines 9-12
	var photoInfoLabel string
	err := chromedp.Run(ctx,
		chromedp.Sleep(2*time.Second),
		chromedp.Evaluate(`
			(function() {
				let labels = [...document.querySelectorAll('[aria-label]')]
					.map(e => e.getAttribute('aria-label'))
					.filter(l => l && l.includes(' - '));
				return labels.length > 0 ? labels[0] : '';
			})()
		`, &photoInfoLabel),
	)

	if err != nil || photoInfoLabel == "" {
		return nil, fmt.Errorf("could not extract metadata format: %w", err)
	}

	log.Debug().Msgf("Extracted metadata format: %s", photoInfoLabel)

	// Detect date format pattern - same as console-extract.js lines 34-41
	var dateFormat string

	// Import regexp package for pattern matching
	dayMonthYear := `(\d{1,2})\.\s+(\w+)\.\s+(\d{4}),`
	monthDayYear := `(\w+)\s+(\d{1,2}),\s+(\d{4}),`
	dayMonthYearNoComma := `(\d{1,2})\s+(\w+)\s+(\d{4}),`

	matched := false
	for _, pattern := range []string{dayMonthYear, monthDayYear, dayMonthYearNoComma} {
		if matchPattern(photoInfoLabel, pattern) {
			matched = true
			switch pattern {
			case dayMonthYear:
				dateFormat = "day. month. year"
			case monthDayYear:
				dateFormat = "month day, year"
			case dayMonthYearNoComma:
				dateFormat = "day month year"
			}
			break
		}
	}

	if !matched {
		return nil, fmt.Errorf("unknown date format in metadata: %s", photoInfoLabel)
	}

	// Generate months using page language - same as console-extract.js lines 44-48
	var monthsJSON string
	err = chromedp.Run(ctx,
		chromedp.Evaluate(`
			(function() {
				const months = [];
				const pageLang = '`+lang+`';
				for (let i = 0; i < 12; i++) {
					const date = new Date(2024, i, 1);
					months.push(date.toLocaleDateString(pageLang, { month: 'short' }).replace(/\./g, ''));
				}
				return JSON.stringify(months);
			})()
		`, &monthsJSON),
	)

	if err != nil {
		return nil, fmt.Errorf("could not generate months: %w", err)
	}

	var months []string
	if err := json.Unmarshal([]byte(monthsJSON), &months); err != nil {
		return nil, fmt.Errorf("could not parse months JSON: %w", err)
	}

	log.Info().Msgf("Auto-extracted config for %s: months=%v, format=%s", lang, months, dateFormat)

	return &config.MonthConfig{
		Months:         months,
		MetadataFormat: photoInfoLabel,
		DateFormat:     dateFormat,
	}, nil
}

// Helper function to match patterns (simple implementation)
func matchPattern(text, pattern string) bool {
	// This is a simplified check - in production you'd use regexp
	// For now, we check if certain patterns are present
	if pattern == `(\d{1,2})\.\s+(\w+)\.\s+(\d{4}),` {
		return strings.Contains(text, ". ") && strings.Contains(text, ", ")
	}
	if pattern == `(\w+)\s+(\d{1,2}),\s+(\d{4}),` {
		// English format: "Nov 17, 2025,"
		return !strings.Contains(text, ". ") && strings.Contains(text, ", ")
	}
	if pattern == `(\d{1,2})\s+(\w+)\s+(\d{4}),` {
		// Format without dots: "13 nov 2025,"
		return !strings.Contains(text, ". ") && !strings.Contains(text, ", ")
	}
	return false
}

// CaptureScreenshot saves a screenshot and HTML dump for debugging
func CaptureScreenshot(ctx context.Context, filePath string) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	var buf []byte

	log.Trace().Msgf("saving screenshot to %v", filePath+".png")
	if err := chromedp.Run(ctx, chromedp.CaptureScreenshot(&buf)); err != nil {
		log.Err(err).Msgf("failed to capture screenshot: %v", err)
	} else if err := os.WriteFile(filePath+".png", buf, os.FileMode(0666)); err != nil {
		log.Err(err).Msgf("failed to write screenshot: %v", err)
	}

	// Dump the HTML to a file
	var html string
	if err := chromedp.Run(ctx, chromedp.OuterHTML("html", &html, chromedp.ByQuery)); err != nil {
		log.Err(err).Msgf("failed to get HTML: %v", err)
	} else if err := os.WriteFile(filePath+".html", []byte(html), 0640); err != nil {
		log.Err(err).Msgf("failed to write HTML: %v", err)
	}
}

// setContextData creates context with navigation locks
// SetContextData creates context with navigation locks (exported for use by other packages)
func SetContextData(ctx context.Context) context.Context {
	return context.WithValue(ctx, contextLocksKey, &types.ContextLocks{
		NavDone: make(chan bool, 1),
	})
}

// GetContextData retrieves context locks from context (exported for use by other packages)
func GetContextData(ctx context.Context) *types.ContextLocks {
	return ctx.Value(contextLocksKey).(*types.ContextLocks)
}

// contextKey is a custom type for context keys to avoid collisions
type contextKey struct {
	name string
}

// Define the key for context locks
var contextLocksKey = &contextKey{name: "contextLocks"}

// SetFlags sets the package-level flag references
func SetFlags(profileFlag *string, headlessFlag *bool, albumIdFlag *string) {
	ProfileFlag = profileFlag
	HeadlessFlag = headlessFlag
	AlbumIdFlag = albumIdFlag
}

// InitFlags initializes flags (to be called from main)
func InitFlags() {
	flag.Parse()
}
