package utils

import (
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/rs/zerolog/log"
)

var (
	yearRegex     = regexp.MustCompile(`\d{4}`)
	dayRegex      = regexp.MustCompile(`\d{1,2}`)
	timeRegex     = regexp.MustCompile(`(\d{1,2}):(\d\d)(?::\d\d)?.?([aApP][Mm])?$`)
	timeZoneRegex = regexp.MustCompile(`GMT([-+])?(\d{1,2})(?::(\d\d))?`)
)

// ParseDate parses a date string with time and timezone
// If months and pageLanguage are nil/"", it will use the global config
func ParseDate(dateStr, timeStr, tzStr string, months []string, pageLanguage string) (time.Time, error) {
	// Import config if needed
	if months == nil || pageLanguage == "" {
		// This will be set by the caller from config package
		return time.Time{}, fmt.Errorf("months and pageLanguage must be provided")
	}
	var year, month, day, hour, minute int

	// Parse year
	yearStr := yearRegex.FindString(dateStr)
	if yearStr != "" {
		year, _ = strconv.Atoi(yearStr)
		dateStr = strings.Replace(dateStr, yearStr, "", 1)
	} else {
		year = time.Now().Year()
	}
	log.Trace().Msgf("parsed year: %d, dateStr: %s", year, dateStr)

	// Parse day
	dayStr := dayRegex.FindString(dateStr)
	if dayStr != "" {
		day, _ = strconv.Atoi(dayStr)
	}
	dateStr = strings.Replace(dateStr, dayStr, "", 1)

	// Parse month
	for i, v := range months {
		if strings.Contains(strings.ToLower(dateStr), strings.ToLower(v)) {
			month = i + 1
			log.Trace().Msgf("found month %s (index %d) in page language %s", v, month, pageLanguage)
			break
		}
	}

	if month == 0 {
		return time.Time{}, fmt.Errorf(`could not find month in date string "%s" for language "%s"

Expected one of these month names: %s

This might indicate:
1. The months-config.json for "%s" is incorrect
2. Google Photos changed its date format
3. The date format is different than expected

Please re-run console-extract.js and update months-config.json`, dateStr, pageLanguage, strings.Join(months, ", "), pageLanguage)
	}
	log.Trace().Msgf("parsed month: %d, dateStr: %s", month, dateStr)

	// Parse time
	if timeStr != "" {
		timeMatch := timeRegex.FindStringSubmatch(timeStr)
		if timeMatch == nil {
			return time.Time{}, fmt.Errorf("could not find time in string %s", timeStr)
		}
		hour, _ = strconv.Atoi(timeMatch[1])
		minute, _ = strconv.Atoi(timeMatch[2])
		if strings.EqualFold(timeMatch[3], "pm") && hour < 12 {
			hour += 12
		}
		if strings.EqualFold(timeMatch[3], "am") && hour == 12 {
			hour = 0
		}
	}

	// Parse timezone
	var timeZone *time.Location
	timeZoneStr := strings.Trim(tzStr, " ")
	if timeZoneStr != "" {
		timeZoneMatch := timeZoneRegex.FindStringSubmatch(timeZoneStr)
		if timeZoneMatch != nil {
			tzHour, _ := strconv.Atoi(timeZoneMatch[2])
			tzMinute, _ := strconv.Atoi(timeZoneMatch[3])
			offset := tzHour*60*60 + tzMinute*60
			if timeZoneMatch[1] == "-" {
				offset = -offset
			}
			timeZone = time.FixedZone("", offset)
		} else {
			return time.Time{}, fmt.Errorf("could not parse time zone in string %s", timeZoneStr)
		}
	} else {
		timeZone = time.Local
	}

	return time.Date(year, time.Month(month), day, hour, minute, 0, 0, timeZone), nil
}

// SetFileDate updates the modification time of a file
func SetFileDate(filepath string, date time.Time) error {
	log.Trace().Msgf("updating date of %v to %v", filepath, date)
	if err := os.Chtimes(filepath, date, date); err != nil {
		return fmt.Errorf("could not change the time of %v: %w", filepath, err)
	}
	return nil
}
