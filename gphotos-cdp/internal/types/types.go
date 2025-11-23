package types

import (
	"context"
	"sync"
	"time"
)

// PhotoData contains metadata about a photo
type PhotoData struct {
	Date     time.Time
	Filename string
}

// Job represents a batch of images to download
type Job struct {
	ImageIds []string
}

// NewDownload represents a download in progress
type NewDownload struct {
	GUID              string
	SuggestedFilename string
	TargetId          string
	ProgressChan      chan bool
}

// DownloadedIdsManager interface for managing downloaded image IDs
type DownloadedIdsManager interface {
	Has(id string) bool
	Add(id string) error
	GetAll() []string
	Count() int
}

// Session manages the Chrome session and download state
type Session struct {
	ParentContext      context.Context
	ChromeExecCancel   context.CancelFunc
	DownloadDir        string
	DownloadDirTmp     string
	ProfileDir         string
	GlobalErrChan      chan error
	UserPath           string
	AlbumPath          string
	ExistingItems      sync.Map // Deprecated: use DownloadedIds instead
	FoundItems         sync.Map
	DownloadedItems    sync.Map
	DownloadedIds      DownloadedIdsManager // New: tracks downloaded IDs in file
	NewDownloadChan    chan NewDownload
	SkippedCount       uint64
}

// ContextLocks manages locks for tab navigation
type ContextLocks struct {
	MuNavWaiting             sync.RWMutex
	MuKbEvents               sync.Mutex
	ListenEvents, NavWaiting bool
	NavDone                  chan bool
}

// ContextLocksPointer wraps a pointer to ContextLocks
type ContextLocksPointer struct {
	Ptr *ContextLocks
}
