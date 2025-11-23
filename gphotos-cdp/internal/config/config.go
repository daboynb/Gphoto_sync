package config

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/rs/zerolog/log"
)

// MonthConfig contains locale-specific month names and date formats
type MonthConfig struct {
	Months         []string `json:"months"`
	MetadataFormat string   `json:"metadataFormat"`
	DateFormat     string   `json:"dateFormat"`
}

// Config holds all month configurations for different languages
var MonthsConfig map[string]MonthConfig

// PageLanguage stores the detected language from Google Photos
var PageLanguage string

// GetConfiguredLanguages returns a comma-separated list of configured languages
func GetConfiguredLanguages() string {
	languages := make([]string, 0, len(MonthsConfig))
	for lang := range MonthsConfig {
		languages = append(languages, lang)
	}
	if len(languages) == 0 {
		return "none"
	}
	return strings.Join(languages, ", ")
}

// LoadMonthsConfig loads the months configuration from file
func LoadMonthsConfig() error {
	configPath := "/app/months-config.json"
	log.Debug().Msgf("Looking for months-config.json at: %s", configPath)

	data, err := os.ReadFile(configPath)
	if err != nil {
		log.Warn().Msgf("months-config.json not found at %s - will auto-extract languages on first use", configPath)
		MonthsConfig = make(map[string]MonthConfig)
		log.Debug().Msgf("Initialized empty monthsConfig map, len=%d", len(MonthsConfig))
		return nil
	}

	log.Debug().Msgf("Read %d bytes from months-config.json", len(data))

	MonthsConfig = make(map[string]MonthConfig)
	log.Debug().Msgf("Initialized monthsConfig map before unmarshal, len=%d", len(MonthsConfig))

	if err := json.Unmarshal(data, &MonthsConfig); err != nil {
		return fmt.Errorf("error parsing months-config.json: %w\n\nThe file exists but contains invalid JSON. Please check the format.", err)
	}

	log.Debug().Msgf("After unmarshal, monthsConfig len=%d", len(MonthsConfig))

	if len(MonthsConfig) == 0 {
		log.Warn().Msg("months-config.json is empty. Languages will be auto-extracted on first use.")
		return nil
	}

	languages := make([]string, 0, len(MonthsConfig))
	for lang := range MonthsConfig {
		languages = append(languages, lang)
	}
	log.Info().Msgf("Loaded month configurations for languages: %s", strings.Join(languages, ", "))

	return nil
}

// SaveMonthsConfig saves the months configuration to file with compact array formatting
func SaveMonthsConfig() error {
	configPath := "/app/months-config.json"

	var buf bytes.Buffer
	buf.WriteString("{\n")

	keys := make([]string, 0, len(MonthsConfig))
	for k := range MonthsConfig {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	for i, lang := range keys {
		config := MonthsConfig[lang]

		monthsJSON, err := json.Marshal(config.Months)
		if err != nil {
			return fmt.Errorf("error marshaling months array: %w", err)
		}

		buf.WriteString(fmt.Sprintf("  %q: {\n", lang))
		buf.WriteString(fmt.Sprintf("    \"months\": %s,\n", string(monthsJSON)))
		buf.WriteString(fmt.Sprintf("    \"metadataFormat\": %q,\n", config.MetadataFormat))
		buf.WriteString(fmt.Sprintf("    \"dateFormat\": %q\n", config.DateFormat))

		if i < len(keys)-1 {
			buf.WriteString("  },\n")
		} else {
			buf.WriteString("  }\n")
		}
	}
	buf.WriteString("}\n")

	if err := os.WriteFile(configPath, buf.Bytes(), 0644); err != nil {
		return fmt.Errorf("error writing months-config.json: %w", err)
	}

	log.Info().Msgf("Saved updated months-config.json to %s", configPath)
	return nil
}
