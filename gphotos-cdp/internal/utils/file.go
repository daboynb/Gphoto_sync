package utils

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/rs/zerolog/log"
)

// DoFileDateUpdate updates the modification time of multiple files
func DoFileDateUpdate(date time.Time, filePaths []string) error {
	for _, v := range filePaths {
		if err := SetFileDate(v, date); err != nil {
			return err
		}
	}
	return nil
}

// DoRun executes a command on a downloaded file
func DoRun(filePath, imageId string, runCmd string) error {
	if runCmd == "" {
		return nil
	}

	dirPath := filepath.Dir(filePath)
	log.Info().Msgf("running %q on %v", runCmd, dirPath)
	cmd := exec.Command(runCmd, dirPath, imageId)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("Run command %v %v %v failed: %v", runCmd, dirPath, imageId, err)
	}
	return nil
}

// DirHasFiles checks if a directory contains any non-empty files
func DirHasFiles(downloadDir, imageId string) (bool, error) {
	entries, err := os.ReadDir(filepath.Join(downloadDir, imageId))
	if os.IsNotExist(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	for _, v := range entries {
		if !v.IsDir() {
			f, err := os.Stat(filepath.Join(downloadDir, imageId, v.Name()))
			if err != nil {
				return false, err
			}
			if f.Size() > 0 {
				return true, nil
			}
		}
	}
	return false, nil
}
