/*
Copyright 2019 The Perkeep Authors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

// The gphotos-cdp program uses the Chrome DevTools Protocol to drive a Chrome session
// that downloads your photos stored in Google Photos.
package main

import (
	"context"
	"flag"
	"os"
	"path/filepath"
	"time"

	"github.com/chromedp/chromedp"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"

	"gphotos-cdp/internal/config"
	"gphotos-cdp/internal/download"
	"gphotos-cdp/internal/navigation"
	"gphotos-cdp/internal/session"
	"gphotos-cdp/internal/sync"
)

var (
	// Flags used by Web UI (via sync.sh)
	downloadDirFlag = flag.String("dldir", "", "where to write the downloads. defaults to $HOME/Downloads/gphotos-cdp.")
	profileFlag     = flag.String("profile", "", "profile directory for Chrome session")
	runFlag         = flag.String("run", "", "the program to run on each downloaded item, right after it is dowloaded. It is also the responsibility of that program to remove the downloaded item, if desired.")
	headlessFlag    = flag.Bool("headless", false, "Start chrome browser in headless mode (must use -profile and have already authenticated).")
	jsonLogFlag     = flag.Bool("json", false, "output logs in JSON format")
	logLevelFlag    = flag.String("loglevel", "", "log level: debug, info, warn, error, fatal, panic")
	removedFlag     = flag.Bool("removed", false, "save list of files found locally that appear to be deleted from Google Photos")
	workersFlag     = flag.Int64("workers", 1, "number of concurrent downloads allowed")
	albumIdFlag     = flag.String("album", "", "ID of album to download, has no effect if lastdone file is found or if -start contains full URL")
)

var loc GPhotosLocale

func main() {
	zerolog.TimestampFieldName = "dt"
	zerolog.TimeFieldFormat = "2006-01-02T15:04:05.999Z07:00"
	flag.Parse()

	level, err := zerolog.ParseLevel(*logLevelFlag)
	if err != nil {
		log.Fatal().Err(err).Msgf("-loglevel argument not valid")
	}
	zerolog.SetGlobalLevel(level)
	if !*jsonLogFlag {
		log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stdout, TimeFormat: "15:04:05"})
	}
	if *profileFlag == "" && *headlessFlag {
		log.Fatal().Msg("-headless only allowed if -profile dir is set")
	}

	// Set XDG_CONFIG_HOME and XDG_CACHE_HOME to a temp dir to solve issue in newer versions of Chromium
	if os.Getenv("XDG_CONFIG_HOME") == "" {
		if err := os.Setenv("XDG_CONFIG_HOME", filepath.Join(os.TempDir(), ".chromium")); err != nil {
			log.Fatal().Msgf("err %v", err)
		}
	}
	if os.Getenv("XDG_CACHE_HOME") == "" {
		if err := os.Setenv("XDG_CACHE_HOME", filepath.Join(os.TempDir(), ".chromium")); err != nil {
			log.Fatal().Msgf("err %v", err)
		}
	}

	s, err := session.NewSession(downloadDirFlag, profileFlag, albumIdFlag)
	if err != nil {
		log.Fatal().Msgf("failed to create session: %v", err)
	}
	defer session.Shutdown(s)

	log.Info().Msgf("session dir: %v", s.ProfileDir)

	if err := session.CleanDownloadDir(s); err != nil {
		log.Fatal().Msgf("failed to clean download directory %v: %v", s.DownloadDir, err)
	}

	ctx, cancel := session.NewWindow(s, headlessFlag)
	defer cancel()

	startupCtx, startupCancel := context.WithTimeout(ctx, 10*time.Minute)
	defer startupCancel()

	log.Info().Msg("========================================")
	log.Info().Msg("AUTHENTICATION")
	log.Info().Msg("========================================")
	if err := session.Login(s, startupCtx, headlessFlag); err != nil {
		log.Fatal().Msgf("login failed: %v", err)
	}

	log.Info().Msg("")
	log.Info().Msg("========================================")
	log.Info().Msg("LANGUAGE DETECTION")
	log.Info().Msg("========================================")
	locale, err := session.GetLocale(startupCtx)
	if err != nil {
		log.Fatal().Msgf("failed to get locale: %v", err)
	}

	// Load months configuration BEFORE checking language
	if err := config.LoadMonthsConfig(); err != nil {
		log.Fatal().Msgf("failed to load months config: %v", err)
	}

	session.CheckLanguage(startupCtx)

	initLocales()
	_loc, exists := locales[locale]
	if !exists {
		log.Warn().Msgf("your Google account locale %s not found in locales.yaml (used for UI labels, not date parsing)", locale)
		log.Warn().Msg("Using default English locale for UI labels. This should not affect month parsing.")
		loc = locales["en"]
	} else {
		log.Info().Msgf("using locale %s for UI labels", locale)
		loc = _loc
	}

	log.Info().Msg("")
	log.Info().Msg("========================================")
	log.Info().Msg("FIRST NAVIGATION")
	log.Info().Msg("========================================")
	if err := chromedp.Run(startupCtx,
		chromedp.ActionFunc(func(ctx context.Context) error {
			return navigation.FirstNav(s, ctx)
		}),
	); err != nil {
		log.Fatal().Msgf("failed to run first nav: %v", err)
	}

	session.CheckLanguage(startupCtx)
	log.Info().Msg("first navigation completed")
	startupCancel()

	// Setup download listener on main context
	download.StartDownloadListener(ctx, s.NewDownloadChan)

	log.Info().Msg("")
	log.Info().Msg("========================================")
	log.Info().Msg("STARTING SYNC")
	log.Info().Msg("========================================")
	if err := chromedp.Run(ctx,
		chromedp.ActionFunc(func(ctx context.Context) error {
			return sync.Resync(s, ctx, *workersFlag, *albumIdFlag, *runFlag)
		}),
		chromedp.ActionFunc(func(ctx context.Context) error {
			return sync.CheckForRemovedFiles(s, ctx, *removedFlag)
		}),
	); err != nil {
		log.Fatal().Msgf("failure during sync: %v", err)
	}

	log.Info().Msg("")
	log.Info().Msg("========================================")
	log.Info().Msg("SYNC COMPLETED")
	log.Info().Msg("========================================")
}
