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

// Session manages the Chrome session and download state
type Session struct {
	ParentContext    context.Context
	ChromeExecCancel context.CancelFunc
	DownloadDir      string
	DownloadDirTmp   string
	ProfileDir       string
	GlobalErrChan    chan error
	UserPath         string
	AlbumPath        string
	ExistingItems    sync.Map
	FoundItems       sync.Map
	DownloadedItems  sync.Map
	NewDownloadChan  chan NewDownload
	SkippedCount     uint64
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
