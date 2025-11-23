package main

import (
	"fmt"
)

type NodeLabelMatch struct {
	MatchType  string
	MatchValue string
}

type GPhotosLocale struct {
	VideoStillProcessingDialogLabel NodeLabelMatch
	VideoStillProcessingStatusText  string
	NoWebpageFoundText              string
}

var locales = map[string]GPhotosLocale{
	"en": {
		VideoStillProcessingDialogLabel: NodeLabelMatch{"startsWith", "Video still is processing"},
		VideoStillProcessingStatusText:  "Video is still processing &amp; can be downloaded later",
		NoWebpageFoundText:              "No webpage was found for the web address:",
	},
}

func initLocales() error {
	// English locale is hardcoded above, no need to load from file
	return nil
}

func getAriaLabelSelector(matcher NodeLabelMatch) string {
	eq := "="
	if matcher.MatchType == "equals" {
		eq = "="
	} else if matcher.MatchType == "startsWith" {
		eq = "^="
	} else if matcher.MatchType == "contains" {
		eq = "*="
	} else if matcher.MatchType == "endsWith" {
		eq = "$="
	}
	return fmt.Sprintf("[aria-label%s\"%s\"]", eq, matcher.MatchValue)
}
