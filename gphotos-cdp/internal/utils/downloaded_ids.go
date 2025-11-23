package utils

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

const downloadedIdsFile = ".downloaded_ids.txt"

// DownloadedIdsManager manages the list of downloaded image IDs
type DownloadedIdsManager struct {
	filePath string
	ids      map[string]struct{}
	mu       sync.RWMutex
}

// NewDownloadedIdsManager creates a new manager for downloaded IDs
func NewDownloadedIdsManager(downloadDir string) (*DownloadedIdsManager, error) {
	filePath := filepath.Join(downloadDir, downloadedIdsFile)
	manager := &DownloadedIdsManager{
		filePath: filePath,
		ids:      make(map[string]struct{}),
	}

	// Load existing IDs from file
	if err := manager.load(); err != nil {
		// If file doesn't exist, that's ok - start with empty list
		if !os.IsNotExist(err) {
			return nil, fmt.Errorf("error loading downloaded IDs: %w", err)
		}
	}

	return manager, nil
}

// load reads the downloaded IDs from file
func (m *DownloadedIdsManager) load() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	file, err := os.Open(m.filePath)
	if err != nil {
		return err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		id := scanner.Text()
		if id != "" {
			m.ids[id] = struct{}{}
		}
	}

	return scanner.Err()
}

// Has checks if an ID has been downloaded
func (m *DownloadedIdsManager) Has(id string) bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	_, exists := m.ids[id]
	return exists
}

// Add marks an ID as downloaded and saves to file
func (m *DownloadedIdsManager) Add(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Check if already exists
	if _, exists := m.ids[id]; exists {
		return nil
	}

	// Add to memory
	m.ids[id] = struct{}{}

	// Append to file
	file, err := os.OpenFile(m.filePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return fmt.Errorf("error opening downloaded IDs file: %w", err)
	}
	defer file.Close()

	if _, err := file.WriteString(id + "\n"); err != nil {
		return fmt.Errorf("error writing to downloaded IDs file: %w", err)
	}

	return nil
}

// GetAll returns all downloaded IDs
func (m *DownloadedIdsManager) GetAll() []string {
	m.mu.RLock()
	defer m.mu.RUnlock()

	ids := make([]string, 0, len(m.ids))
	for id := range m.ids {
		ids = append(ids, id)
	}
	return ids
}

// Count returns the number of downloaded IDs
func (m *DownloadedIdsManager) Count() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.ids)
}
