let currentLogStream = null;
let currentContainerId = null;

// Mini-terminal streams for each container
let miniLogStreams = {};
// Store log lines for each container (persists across refreshes)
let miniLogLines = {};

// Dark Mode Toggle
function toggleDarkMode() {
    const body = document.body;
    const isDark = body.classList.contains('dark-mode');

    if (isDark) {
        body.classList.remove('dark-mode');
        document.getElementById('theme-toggle').innerHTML = '<i class="fas fa-moon"></i>';
        localStorage.setItem('theme', 'light');
    } else {
        body.classList.add('dark-mode');
        document.getElementById('theme-toggle').innerHTML = '<i class="fas fa-sun"></i>';
        localStorage.setItem('theme', 'dark');
    }
}

// Load theme on startup
document.addEventListener('DOMContentLoaded', () => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        document.body.classList.remove('dark-mode');
        document.getElementById('theme-toggle').innerHTML = '<i class="fas fa-moon"></i>';
    } else {
        // Default to dark mode
        document.body.classList.add('dark-mode');
        document.getElementById('theme-toggle').innerHTML = '<i class="fas fa-sun"></i>';
        if (!savedTheme) {
            localStorage.setItem('theme', 'dark');
        }
    }
});

// Toast Notification System
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');

    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        warning: 'bg-yellow-500',
        info: 'bg-blue-500'
    };

    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    toast.className = `${colors[type]} text-white px-6 py-4 rounded-lg shadow-lg flex items-center gap-3 min-w-[300px] max-w-md animate-slide-in`;
    toast.innerHTML = `
        <i class="fas ${icons[type]} text-xl"></i>
        <span class="flex-1">${message}</span>
        <button onclick="this.parentElement.remove()" class="text-white hover:text-gray-200">
            <i class="fas fa-times"></i>
        </button>
    `;

    container.appendChild(toast);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// Custom Confirm Dialog
function showConfirm(title, message, onConfirm) {
    const modal = document.getElementById('confirm-modal');
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;

    const yesBtn = document.getElementById('confirm-yes');
    const noBtn = document.getElementById('confirm-no');

    // Remove old listeners
    const newYesBtn = yesBtn.cloneNode(true);
    const newNoBtn = noBtn.cloneNode(true);
    yesBtn.parentNode.replaceChild(newYesBtn, yesBtn);
    noBtn.parentNode.replaceChild(newNoBtn, noBtn);

    // Add new listeners
    newYesBtn.addEventListener('click', () => {
        modal.classList.add('hidden');
        onConfirm();
    });

    newNoBtn.addEventListener('click', () => {
        modal.classList.add('hidden');
    });

    modal.classList.remove('hidden');
}

// Fetch and display containers
async function loadContainers() {
    try {
        const response = await fetch('/api/containers');
        const containers = await response.json();

        const containersList = document.getElementById('containers-list');

        // Close existing mini-log streams that are no longer needed
        const runningIds = containers.filter(c => c.status === 'running').map(c => c.id);
        Object.keys(miniLogStreams).forEach(id => {
            if (!runningIds.includes(id)) {
                miniLogStreams[id].close();
                delete miniLogStreams[id];
                delete miniLogLines[id]; // Also clear cached logs
            }
        });

        if (containers.length === 0) {
            containersList.innerHTML = `
                <div class="bg-white rounded-lg shadow-md p-8 text-center text-gray-500">
                    <i class="fas fa-box-open text-6xl mb-4"></i>
                    <p class="text-lg">No sync containers found</p>
                    <p class="text-sm mt-2">Start containers using: docker compose up -d</p>
                </div>
            `;
            return;
        }

        containersList.innerHTML = containers.map(container => {
            const statusColor = container.status === 'running' ? 'green' : 'red';
            const statusIcon = container.status === 'running' ? 'circle-check' : 'circle-xmark';

            // Sync status badge
            let syncBadge = '';
            if (container.sync_status === 'completed') {
                syncBadge = '<span class="px-2 py-1 rounded text-white bg-green-600"><i class="fas fa-check-circle"></i> Sync Completed</span>';
            } else if (container.sync_status === 'syncing') {
                syncBadge = '<span class="px-2 py-1 rounded text-white bg-blue-500"><i class="fas fa-sync fa-spin"></i> Syncing...</span>';
            } else if (container.sync_status === 'idle') {
                syncBadge = '<span class="px-2 py-1 rounded text-white bg-yellow-500"><i class="fas fa-clock"></i> Idle</span>';
            }

            // Mini terminal (only for running containers)
            const miniTerminal = container.status === 'running' ? `
                <div class="mt-4 bg-gray-900 rounded-lg overflow-hidden">
                    <div class="px-3 py-1 bg-gray-800 flex items-center gap-2">
                        <i class="fas fa-terminal text-green-400 text-xs"></i>
                        <span class="text-xs text-gray-400">Live Output</span>
                    </div>
                    <div id="mini-log-${container.id}" class="p-2 h-24 overflow-hidden font-mono text-xs text-green-400 whitespace-pre-wrap"></div>
                </div>
            ` : '';

            return `
                <div class="bg-white rounded-lg shadow-md p-6">
                    <div class="flex justify-between items-start mb-4">
                        <div class="flex-1">
                            <h3 class="text-xl font-bold text-gray-800 mb-1">
                                <i class="fas fa-user-circle text-blue-500"></i>
                                ${container.display_name || container.name}
                            </h3>
                            ${container.display_name && container.display_name !== container.profile ?
                                `<p class="text-sm text-gray-500">${container.name}</p>` : ''
                            }
                            <div class="flex items-center gap-2 text-sm">
                                <span class="px-2 py-1 rounded text-white bg-${statusColor}-500">
                                    <i class="fas fa-${statusIcon}"></i> ${container.status}
                                </span>
                                ${syncBadge}
                                <span class="text-gray-500">ID: ${container.id}</span>
                            </div>
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-4 mb-4 text-sm">
                        <div>
                            <i class="fas fa-clock text-gray-400"></i>
                            <strong>Next sync:</strong> ${container.next_run}
                            <div class="text-gray-600 ml-5">in ${container.time_until}</div>
                        </div>
                        <div>
                            <i class="fas fa-calendar-alt text-gray-400"></i>
                            <strong>Schedule:</strong> ${container.cron_schedule}
                        </div>
                        <div>
                            <i class="fas fa-rocket text-gray-400"></i>
                            <strong>Run on startup:</strong> ${container.run_on_startup}
                        </div>
                        <div>
                            <i class="fas fa-users text-gray-400"></i>
                            <strong>Workers:</strong> ${container.worker_count}
                        </div>
                    </div>

                    ${miniTerminal}

                    <div class="flex gap-2 flex-wrap mt-4">
                        ${container.status === 'running' ? `
                            <button onclick="viewLogs('${container.id}', '${container.name}')"
                                    class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm">
                                <i class="fas fa-expand"></i> Full Logs
                            </button>
                        ` : `
                            <button disabled
                                    class="px-4 py-2 bg-gray-400 text-white rounded cursor-not-allowed text-sm"
                                    title="Container must be running to view logs">
                                <i class="fas fa-file-lines"></i> View Logs
                            </button>
                        `}
                        ${container.vnc_enabled && container.vnc_port && container.status === 'running' ? `
                            <button onclick="openVNCViewer('${container.display_name || container.name}', ${container.vnc_port})"
                                    class="px-4 py-2 bg-teal-500 text-white rounded hover:bg-teal-600 text-sm">
                                <i class="fas fa-desktop"></i> View VNC
                            </button>
                        ` : ''}
                        ${container.status === 'running' ? `
                            <button onclick="stopContainer('${container.id}')"
                                    class="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 text-sm">
                                <i class="fas fa-stop"></i> Stop
                            </button>
                        ` : `
                            <button onclick="startContainer('${container.id}')"
                                    class="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 text-sm">
                                <i class="fas fa-play"></i> Start
                            </button>
                        `}
                        <button onclick="restartContainer('${container.id}')"
                                class="px-4 py-2 bg-yellow-500 text-white rounded hover:bg-yellow-600 text-sm">
                            <i class="fas fa-rotate"></i> Restart
                        </button>
                        ${container.profile !== 'default' ? `
                            <button onclick="reAuthProfile('${container.profile}', '${container.display_name || container.name}')"
                                    class="px-4 py-2 bg-purple-500 text-white rounded hover:bg-purple-600 text-sm">
                                <i class="fas fa-key"></i> Re-Auth
                            </button>
                            <button onclick="editProfileConfig('${container.profile}', '${container.display_name || container.name}')"
                                    class="px-4 py-2 bg-indigo-500 text-white rounded hover:bg-indigo-600 text-sm">
                                <i class="fas fa-cog"></i> Edit Config
                            </button>
                            <button onclick="deleteProfile('${container.profile}', '${container.display_name || container.name}')"
                                    class="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-800 text-sm">
                                <i class="fas fa-trash"></i> Delete
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');

        // Start mini-log streams for running containers
        containers.filter(c => c.status === 'running').forEach(container => {
            startMiniLogStream(container.id);
        });

    } catch (error) {
        console.error('Error loading containers:', error);
    }
}

// Fetch and display stats
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();

        document.getElementById('stat-total').textContent = stats.total;
        document.getElementById('stat-running').textContent = stats.running;
        document.getElementById('stat-stopped').textContent = stats.stopped;
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Prettify JSON logs
function prettifyLogLine(line) {
    // Check if line contains JSON
    const jsonMatch = line.match(/\{.*\}/);
    if (!jsonMatch) return line;

    try {
        const json = JSON.parse(jsonMatch[0]);

        // Extract timestamp prefix (before JSON)
        const prefix = line.substring(0, line.indexOf('{'));

        // Format: [timestamp] level: message
        let formatted = '';
        if (prefix.trim()) {
            formatted += `<span class="text-gray-500">${prefix}</span>`;
        }

        if (json.level) {
            const levelColors = {
                'error': 'text-red-500',
                'warn': 'text-yellow-500',
                'info': 'text-blue-400',
                'debug': 'text-gray-400',
                'trace': 'text-gray-600'
            };
            const color = levelColors[json.level] || 'text-green-400';
            formatted += `<span class="${color} font-bold">[${json.level.toUpperCase()}]</span> `;
        }

        if (json.message) {
            formatted += `<span class="text-green-400">${json.message}</span>`;
        }

        return formatted || line;
    } catch (e) {
        return line;
    }
}

// Mini-terminal log streaming
const MINI_LOG_MAX_LINES = 5;

function startMiniLogStream(containerId) {
    const miniLogEl = document.getElementById(`mini-log-${containerId}`);
    if (!miniLogEl) return;

    // Initialize log lines array if not exists
    if (!miniLogLines[containerId]) {
        miniLogLines[containerId] = [];
    }

    // If we already have cached logs, display them immediately
    if (miniLogLines[containerId].length > 0) {
        updateMiniLogDisplay(containerId);
    }

    // Don't create duplicate streams
    if (miniLogStreams[containerId]) {
        return;
    }

    // Load initial logs only if we don't have cached lines
    if (miniLogLines[containerId].length === 0) {
        fetch(`/api/container/${containerId}/logs`)
            .then(res => res.json())
            .then(data => {
                if (data.logs) {
                    const lines = data.logs.split('\n').filter(l => l.trim());
                    miniLogLines[containerId] = lines.slice(-MINI_LOG_MAX_LINES);
                    updateMiniLogDisplay(containerId);
                }
            })
            .catch(() => {});
    }

    // Start streaming
    const stream = new EventSource(`/api/container/${containerId}/logs/stream`);
    miniLogStreams[containerId] = stream;

    stream.onmessage = function(event) {
        const line = event.data;
        if (line.trim()) {
            miniLogLines[containerId].push(line);
            if (miniLogLines[containerId].length > MINI_LOG_MAX_LINES) {
                miniLogLines[containerId].shift();
            }
            updateMiniLogDisplay(containerId);
        }
    };

    stream.onerror = function() {
        // Silently handle errors, stream will be cleaned up on next loadContainers
    };
}

function updateMiniLogDisplay(containerId) {
    const miniLogEl = document.getElementById(`mini-log-${containerId}`);
    if (!miniLogEl || !miniLogLines[containerId]) return;

    miniLogEl.innerHTML = miniLogLines[containerId].map(line => prettifyLogLine(line)).join('\n');
    // Auto-scroll to bottom
    miniLogEl.scrollTop = miniLogEl.scrollHeight;
}

// View logs modal
async function viewLogs(containerId, containerName) {
    currentContainerId = containerId;
    document.getElementById('log-container-name').textContent = containerName;
    document.getElementById('log-modal').classList.remove('hidden');

    // Clear previous logs
    document.getElementById('log-content').innerHTML = '';

    // Ensure auto-scroll is checked
    document.getElementById('auto-scroll').checked = true;

    // Load initial logs
    try {
        const response = await fetch(`/api/container/${containerId}/logs`);
        const data = await response.json();

        if (data.logs) {
            const logContent = document.getElementById('log-content');
            const lines = data.logs.split('\n');
            logContent.innerHTML = lines.map(line => prettifyLogLine(line)).join('\n');

            // Scroll to bottom after a short delay to ensure content is rendered
            setTimeout(() => {
                scrollLogsToBottom();
            }, 100);
        }
    } catch (error) {
        console.error('Error loading logs:', error);
    }

    // Start streaming logs
    startLogStream(containerId);
}

// Start log streaming
function startLogStream(containerId) {
    if (currentLogStream) {
        currentLogStream.close();
    }

    currentLogStream = new EventSource(`/api/container/${containerId}/logs/stream`);

    currentLogStream.onmessage = function(event) {
        const logContent = document.getElementById('log-content');
        const newLine = prettifyLogLine(event.data);
        logContent.innerHTML += newLine + '\n';

        // Always scroll to bottom (auto-scroll is always on by default)
        if (document.getElementById('auto-scroll').checked) {
            // Use requestAnimationFrame for smooth scrolling
            requestAnimationFrame(() => {
                scrollLogsToBottom();
            });
        }
    };

    // Handle custom 'close' event from server
    currentLogStream.addEventListener('close', function(event) {
        console.log('Container stopped, closing log stream:', event.data);
        const logContent = document.getElementById('log-content');
        logContent.innerHTML += '\n[Container stopped - log stream closed]\n';

        // Scroll to show the final message
        scrollLogsToBottom();

        currentLogStream.close();
        currentLogStream = null;
    });

    // Handle custom 'error' event from server
    currentLogStream.addEventListener('error', function(event) {
        if (event.data) {
            console.error('Server error in log stream:', event.data);
            const logContent = document.getElementById('log-content');
            logContent.innerHTML += `\n[Error: ${event.data}]\n`;
        }
        if (currentLogStream) {
            currentLogStream.close();
            currentLogStream = null;
        }
    });

    currentLogStream.onerror = function(error) {
        // Silently handle stream closure when container stops
        // This is normal behavior, not an error
        if (currentLogStream) {
            const readyState = currentLogStream.readyState;

            // EventSource.CLOSED = 2, means stream ended normally
            if (readyState === EventSource.CLOSED || readyState === 2) {
                // Stream closed normally (container stopped), just clean up
                currentLogStream.close();
                currentLogStream = null;
            }
            // EventSource.CONNECTING = 0, means reconnecting after error
            else if (readyState === EventSource.CONNECTING || readyState === 0) {
                console.warn('Log stream reconnecting...');
            }
            // EventSource.OPEN = 1, unexpected error while open
            else {
                console.error('Unexpected log stream error:', error);
            }
        }
    };
}

// Close log modal
function closeLogModal() {
    document.getElementById('log-modal').classList.add('hidden');
    if (currentLogStream) {
        currentLogStream.close();
        currentLogStream = null;
    }
}

// Scroll logs to bottom
function scrollLogsToBottom() {
    const logContainer = document.getElementById('log-container');
    if (logContainer) {
        logContainer.scrollTop = logContainer.scrollHeight;
    }
}

// Download logs
function downloadLogs() {
    const logs = document.getElementById('log-content').textContent;
    const blob = new Blob([logs], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${currentContainerId}-logs-${new Date().toISOString()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
}

// Container actions
async function startContainer(containerId) {
    try {
        await fetch(`/api/container/${containerId}/start`, { method: 'POST' });
        setTimeout(() => {
            loadContainers();
            loadStats();
        }, 1000);
    } catch (error) {
        console.error('Error starting container:', error);
    }
}

async function stopContainer(containerId) {
    showConfirm(
        'Stop Container',
        'Are you sure you want to stop this container?',
        async () => {
            try {
                await fetch(`/api/container/${containerId}/stop`, { method: 'POST' });
                showToast('Container stopped successfully', 'success');
                setTimeout(() => {
                    loadContainers();
                    loadStats();
                }, 1000);
            } catch (error) {
                console.error('Error stopping container:', error);
                showToast('Error stopping container', 'error');
            }
        }
    );
}

async function restartContainer(containerId) {
    showConfirm(
        'Restart Container',
        'Are you sure you want to restart this container?',
        async () => {
            try {
                await fetch(`/api/container/${containerId}/restart`, { method: 'POST' });
                showToast('Container restarted successfully', 'success');
                setTimeout(() => {
                    loadContainers();
                    loadStats();
                }, 1000);
            } catch (error) {
                console.error('Error restarting container:', error);
                showToast('Error restarting container', 'error');
            }
        }
    );
}

// Load available profiles (not started)
async function loadAvailableProfiles() {
    try {
        const response = await fetch('/api/available-profiles');
        const profiles = await response.json();

        const profilesDiv = document.getElementById('available-profiles');

        if (profiles.length === 0) {
            profilesDiv.innerHTML = '';
            return;
        }

        // Check authentication status for each profile
        const profilesWithAuth = await Promise.all(profiles.map(async profile => {
            const authResponse = await fetch(`/api/check-auth/${profile.name}`);
            const authData = await authResponse.json();
            return { ...profile, authenticated: authData.authenticated };
        }));

        profilesDiv.innerHTML = `
            <div class="bg-white border-l-4 border-yellow-400 p-4 rounded shadow-md">
                <div class="flex items-start">
                    <div class="flex-shrink-0">
                        <i class="fas fa-pause-circle text-yellow-500 text-xl"></i>
                    </div>
                    <div class="ml-3 flex-1">
                        <h3 class="text-sm font-medium text-gray-800 mb-2">
                            Available Profiles (Not Running)
                        </h3>
                        <div class="space-y-2">
                            ${profilesWithAuth.map(profile => `
                                <div class="flex items-center justify-between bg-gray-100 p-3 rounded">
                                    <div>
                                        <span class="font-semibold text-gray-800">${profile.display_name || profile.name}</span>
                                        ${profile.display_name && profile.display_name.toLowerCase() !== profile.name.toLowerCase() ?
                                            `<span class="ml-2 text-xs text-gray-500">(${profile.name})</span>` : ''
                                        }
                                        ${!profile.has_compose && profile.authenticated ?
                                            '<span class="ml-2 text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded"><i class="fas fa-check"></i> Authenticated</span>' :
                                            !profile.has_compose ?
                                            '<span class="ml-2 text-xs bg-red-100 text-red-800 px-2 py-1 rounded">Not authenticated</span>' :
                                            '<span class="ml-2 text-xs bg-green-100 text-green-800 px-2 py-1 rounded">Ready to start</span>'
                                        }
                                    </div>
                                    <div class="flex gap-2">
                                        ${!profile.has_compose ? `
                                            ${profile.authenticated ? `
                                                <button onclick="openConfigModal('${profile.name}', '${profile.display_name || profile.name}')"
                                                        class="px-3 py-1 bg-blue-500 text-white text-sm rounded hover:bg-blue-600">
                                                    <i class="fas fa-cog"></i> Configure
                                                </button>
                                            ` : `
                                                <button onclick="startVNCAuth('${profile.name}', '${profile.display_name || profile.name}')"
                                                        class="px-3 py-1 bg-purple-500 text-white text-sm rounded hover:bg-purple-600">
                                                    <i class="fas fa-key"></i> Authenticate
                                                </button>
                                            `}
                                        ` : `
                                            <button onclick="startProfileFromGUI('${profile.name}')"
                                                    class="px-3 py-1 bg-green-500 text-white text-sm rounded hover:bg-green-600">
                                                <i class="fas fa-play"></i> Start
                                            </button>
                                        `}
                                        <button onclick="deleteProfileFiles('${profile.name}', '${profile.display_name || profile.name}')"
                                                class="px-3 py-1 bg-gray-700 text-white text-sm rounded hover:bg-gray-800">
                                            <i class="fas fa-trash"></i> Delete
                                        </button>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        `;
    } catch (error) {
        console.error('Error loading available profiles:', error);
    }
}

// Note: createCompose is replaced by openConfigModal + saveConfiguration

// Start profile directly from GUI
async function startProfileFromGUI(profileName) {
    try {
        const response = await fetch(`/api/start-profile/${profileName}`, { method: 'POST' });
        const data = await response.json();

        if (data.status === 'started') {
            // Reload everything to show the running container
            setTimeout(() => {
                loadContainers();
                loadStats();
                loadAvailableProfiles();
            }, 1000);
        } else {
            showToast('Error starting profile: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error starting profile:', error);
        showToast('Error starting profile', 'error');
    }
}

// Delete profile (container + compose file) - for running containers
async function deleteProfile(profileName, displayName) {
    showConfirm(
        `Delete Profile`,
        `This will:\n- Stop and remove the Docker container for "${displayName}"\n- Delete docker-compose.${profileName}.yml\n\nThis action cannot be undone!`,
        async () => {
            try {
                const response = await fetch(`/api/delete-profile/${profileName}`, { method: 'DELETE' });
                const data = await response.json();

                if (data.status === 'deleted' || data.status === 'partial') {
                    if (data.errors && data.errors.length > 0) {
                        showToast('Profile deleted with some errors', 'warning');
                    } else {
                        showToast('Profile deleted successfully', 'success');
                    }

                    // Reload everything
                    setTimeout(() => {
                        loadContainers();
                        loadStats();
                        loadAvailableProfiles();
                    }, 1000);
                } else {
                    showToast('Error deleting profile: ' + (data.error || 'Unknown error'), 'error');
                }
            } catch (error) {
                console.error('Error deleting profile:', error);
                showToast('Error deleting profile', 'error');
            }
        }
    );
}

// Delete profile files only (for available profiles not yet started)
async function deleteProfileFiles(profileName, displayName) {
    showConfirm(
        `Delete Profile`,
        `This will delete:\n- Profile directory (profiles/${profileName})\n- docker-compose.${profileName}.yml (if exists)\n- All authentication data for "${displayName}"\n\nThis action cannot be undone!`,
        async () => {
            try {
                const response = await fetch(`/api/delete-profile-files/${profileName}`, { method: 'DELETE' });
                const data = await response.json();

                if (data.status === 'deleted' || data.status === 'partial') {
                    if (data.errors && data.errors.length > 0) {
                        showToast('Profile files deleted with some errors', 'warning');
                    } else {
                        showToast('Profile files deleted successfully', 'success');
                    }

                    // Reload everything
                    setTimeout(() => {
                        loadContainers();
                        loadStats();
                        loadAvailableProfiles();
                    }, 1000);
                } else {
                    showToast('Error deleting profile files: ' + (data.error || 'Unknown error'), 'error');
                }
            } catch (error) {
                console.error('Error deleting profile files:', error);
                showToast('Error deleting profile files', 'error');
            }
        }
    );
}

// Open create profile modal
function openCreateProfileModal() {
    document.getElementById('create-profile-modal').classList.remove('hidden');
    document.getElementById('profile-name-input').value = '';
    document.getElementById('profile-name-input').focus();
}

// Close create profile modal
function closeCreateProfileModal() {
    document.getElementById('create-profile-modal').classList.add('hidden');
}

// Create new profile
async function createNewProfile() {
    const profileName = document.getElementById('profile-name-input').value.trim();

    if (!profileName) {
        showToast('Please enter a profile name', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/create-new-profile', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name: profileName })
        });

        const data = await response.json();

        if (data.status === 'created') {
            closeCreateProfileModal();
            showToast(`Profile "${data.profile_name}" created successfully!`, 'success');

            // Reload to show the new profile
            setTimeout(() => {
                loadContainers();
                loadStats();
                loadAvailableProfiles();
            }, 500);
        } else {
            showToast('Error creating profile: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error creating profile:', error);
        showToast('Error creating profile', 'error');
    }
}

// Profile Configuration
let currentConfigProfileNum = null;
let isEditMode = false;

// Toggle Advanced Options
function toggleAdvancedOptions() {
    const advancedDiv = document.getElementById('advanced-options');
    const icon = document.getElementById('advanced-toggle-icon');

    if (advancedDiv.classList.contains('hidden')) {
        advancedDiv.classList.remove('hidden');
        icon.classList.add('rotate-180');
    } else {
        advancedDiv.classList.add('hidden');
        icon.classList.remove('rotate-180');
    }
}

async function openConfigModal(profileName, displayName) {
    currentConfigProfileNum = profileName; // Store profile name instead of number
    isEditMode = false;
    document.getElementById('config-profile-name').textContent = displayName;

    // Update button text for create mode
    document.getElementById('config-save-text').textContent = 'Create Docker Compose';

    document.getElementById('config-modal').classList.remove('hidden');

    // Fetch defaults from backend
    let defaults = {};
    try {
        const resp = await fetch('/api/defaults');
        defaults = await resp.json();
    } catch (e) {
        console.warn('Failed to fetch defaults, using fallbacks', e);
    }

    // Set default values for new profile
    document.getElementById('config-enable-cron').checked = true;
    document.getElementById('config-cron').value = defaults.cron_schedule || '0 3 * * *';
    document.getElementById('config-run-on-startup').checked = defaults.run_on_startup !== undefined ? defaults.run_on_startup : true;
    document.getElementById('config-loglevel').value = defaults.loglevel || 'info';
    document.getElementById('config-workers').value = defaults.worker_count || 6;
    document.getElementById('config-download-method').value = defaults.download_method || 'compressed';
    document.getElementById('config-albums').value = '';
    document.getElementById('config-timezone').value = defaults.timezone || 'Europe/Rome';
    document.getElementById('config-photo-dir').value = '';

    // Advanced options defaults
    document.getElementById('config-puid').value = defaults.puid || 1000;
    document.getElementById('config-pgid').value = defaults.pgid || 1000;
    document.getElementById('config-restart-schedule').value = '';
    document.getElementById('config-healthcheck-url').value = '';
    document.getElementById('config-enable-vnc').checked = defaults.enable_vnc || false;

    // Show cron fields by default
    toggleCronSchedule();

    // Hide advanced options by default
    document.getElementById('advanced-options').classList.add('hidden');
    document.getElementById('advanced-toggle-icon').classList.remove('rotate-180');

    // Initialize albums list (empty for new profile)
    initializeAlbumsList('');
}

async function editProfileConfig(profileName, displayName) {
    currentConfigProfileNum = profileName; // Store profile name directly
    isEditMode = true;
    document.getElementById('config-profile-name').textContent = displayName;

    // Update button text for edit mode
    document.getElementById('config-save-text').textContent = 'Update Configuration';

    try {
        // Load current configuration and defaults in parallel
        const [configResponse, defaultsResponse] = await Promise.all([
            fetch(`/api/get-config/${profileName}`),
            fetch('/api/defaults')
        ]);
        const config = await configResponse.json();
        let defaults = {};
        try { defaults = await defaultsResponse.json(); } catch (e) {}

        if (config.error) {
            showToast('Error loading configuration: ' + config.error, 'error');
            return;
        }

        // Populate form with current values, falling back to server defaults
        const isCronDisabled = config.cron_schedule === 'disabled' || config.cron_schedule === 'no-cron';
        document.getElementById('config-enable-cron').checked = !isCronDisabled;
        document.getElementById('config-cron').value = isCronDisabled ? (defaults.cron_schedule || '0 3 * * *') : (config.cron_schedule || defaults.cron_schedule || '0 3 * * *');
        document.getElementById('config-run-on-startup').checked = config.run_on_startup;
        document.getElementById('config-loglevel').value = config.loglevel || defaults.loglevel || 'info';
        document.getElementById('config-workers').value = config.worker_count || defaults.worker_count || 6;
        document.getElementById('config-download-method').value = config.download_method || defaults.download_method || 'compressed';
        document.getElementById('config-timezone').value = config.timezone || defaults.timezone || 'Europe/Rome';
        document.getElementById('config-photo-dir').value = config.photo_dir || '';

        // Advanced options
        document.getElementById('config-puid').value = config.puid || defaults.puid || 1000;
        document.getElementById('config-pgid').value = config.pgid || defaults.pgid || 1000;
        document.getElementById('config-restart-schedule').value = config.restart_schedule || '';
        document.getElementById('config-healthcheck-url').value = config.healthcheck_url || '';
        document.getElementById('config-enable-vnc').checked = config.enable_vnc || false;

        // Toggle cron fields visibility
        toggleCronSchedule();

        // Hide advanced options by default
        document.getElementById('advanced-options').classList.add('hidden');
        document.getElementById('advanced-toggle-icon').classList.remove('rotate-180');

        // Initialize albums list with existing data
        initializeAlbumsList(config.albums || '');

        document.getElementById('config-modal').classList.remove('hidden');
    } catch (error) {
        console.error('Error loading config:', error);
        showToast('Error loading configuration', 'error');
    }
}

function closeConfigModal() {
    document.getElementById('config-modal').classList.add('hidden');
    currentConfigProfileNum = null;
}

function toggleCronSchedule() {
    const enableCron = document.getElementById('config-enable-cron').checked;
    const cronContainer = document.getElementById('cron-schedule-container');
    const startupContainer = document.getElementById('run-on-startup-container');

    if (enableCron) {
        cronContainer.style.display = 'block';
        startupContainer.style.display = 'block';
    } else {
        cronContainer.style.display = 'none';
        startupContainer.style.display = 'none';
    }
}

async function saveConfiguration() {
    const enableCron = document.getElementById('config-enable-cron').checked;

    // Get sync mode and albums
    const syncMode = document.querySelector('input[name="sync-mode"]:checked').value;
    let albums = '';
    if (syncMode === 'albums') {
        albums = document.getElementById('config-albums').value.trim();
    }

    // Basic configuration
    const config = {
        enable_cron: enableCron,
        cron_schedule: enableCron ? document.getElementById('config-cron').value.trim() : 'no-cron',
        run_on_startup: enableCron ? document.getElementById('config-run-on-startup').checked : false,
        loglevel: document.getElementById('config-loglevel').value,
        worker_count: parseInt(document.getElementById('config-workers').value),
        download_method: document.getElementById('config-download-method').value,
        albums: albums,
        timezone: document.getElementById('config-timezone').value.trim(),
        photo_dir: document.getElementById('config-photo-dir').value.trim(),

        // Advanced options
        puid: parseInt(document.getElementById('config-puid').value),
        pgid: parseInt(document.getElementById('config-pgid').value),
        restart_schedule: document.getElementById('config-restart-schedule').value.trim(),
        healthcheck_url: document.getElementById('config-healthcheck-url').value.trim(),
        enable_vnc: document.getElementById('config-enable-vnc').checked
    };

    try {
        const response = await fetch(`/api/create-compose/${currentConfigProfileNum}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(config)
        });

        const data = await response.json();

        if (data.status === 'created') {
            // Save profile name before closing modal
            const profileName = currentConfigProfileNum;

            closeConfigModal();

            if (isEditMode) {
                // In edit mode: recreate the container to apply changes
                showToast('Configuration updated! Recreating container...', 'info');

                // Recreate the container with new configuration
                (async () => {
                    try {
                        // Wait a bit before starting
                        await new Promise(resolve => setTimeout(resolve, 500));

                        // Use the recreate endpoint that stops+removes+starts with docker-compose
                        const recreateResp = await fetch(`/api/recreate-profile/${profileName}`, { method: 'POST' });
                        const recreateData = await recreateResp.json();

                        if (recreateData.status !== 'recreated') {
                            throw new Error(recreateData.error || 'Failed to recreate container');
                        }

                        showToast('Container recreated with new configuration!', 'success');

                        // Reload UI
                        setTimeout(() => {
                            loadContainers();
                            loadStats();
                            loadAvailableProfiles();
                        }, 1000);
                    } catch (error) {
                        console.error('Error recreating container:', error);
                        showToast('Configuration saved but failed to recreate container. Please stop and start manually.', 'warning');
                    }
                })();
            } else {
                // In create mode: automatically start the profile after creating compose file
                showToast('Docker Compose created successfully. Starting container...', 'success');
                setTimeout(() => startProfileFromGUI(profileName), 500);
            }
        } else {
            showToast('Error: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error saving configuration:', error);
        showToast('Error saving configuration', 'error');
    }
}

// VNC Authentication
let currentAuthProfileNum = null;
let currentAuthProfileName = null;
let isReAuthMode = false;

function startVNCAuth(profileName, displayName) {
    currentAuthProfileNum = profileName; // Store profile name instead of number
    currentAuthProfileName = displayName;
    isReAuthMode = false;
    document.getElementById('vnc-profile-name').textContent = displayName;
    document.getElementById('vnc-auth-modal').classList.remove('hidden');

    // Reset UI
    document.getElementById('vnc-status').classList.remove('hidden');
    document.getElementById('vnc-running').classList.add('hidden');
}

async function reAuthProfile(profileName, displayName) {
    // First, stop any existing VNC container to avoid profile confusion
    try {
        await fetch('/api/stop-auth', { method: 'POST' });
        // Wait a moment for the container to fully stop
        await new Promise(resolve => setTimeout(resolve, 1000));
    } catch (error) {
        // Ignore errors if no VNC is running
        console.log('No existing VNC to stop, continuing...');
    }

    currentAuthProfileNum = profileName;
    currentAuthProfileName = displayName;
    isReAuthMode = true;
    document.getElementById('vnc-profile-name').textContent = displayName;
    document.getElementById('vnc-auth-modal').classList.remove('hidden');

    // Reset UI
    document.getElementById('vnc-status').classList.remove('hidden');
    document.getElementById('vnc-running').classList.add('hidden');
}

function closeVNCModal() {
    document.getElementById('vnc-auth-modal').classList.add('hidden');
    currentAuthProfileNum = null;
    currentAuthProfileName = null;
}

async function startVNCContainer() {
    const startBtn = document.getElementById('start-vnc-btn');
    startBtn.disabled = true;
    startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting VNC...';

    try {
        // Use different endpoint based on whether it's re-auth or initial auth
        const endpoint = isReAuthMode
            ? `/api/reauth-profile/${currentAuthProfileNum}`
            : `/api/start-auth/${currentAuthProfileNum}`;

        const response = await fetch(endpoint, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.status === 'started') {
            // Show VNC running UI
            document.getElementById('vnc-status').classList.add('hidden');
            document.getElementById('vnc-running').classList.remove('hidden');

            // Set VNC link dynamically using current hostname
            const vncLink = document.getElementById('vnc-link');
            const currentHost = window.location.hostname;
            vncLink.href = `http://${currentHost}:6080`;

            const message = isReAuthMode
                ? 'VNC container started for re-authentication'
                : 'VNC container started successfully';
            showToast(message, 'success');
        } else {
            showToast('Error starting VNC: ' + (data.error || 'Unknown error'), 'error');
            startBtn.disabled = false;
            startBtn.innerHTML = '<i class="fas fa-play-circle"></i> Start VNC Container';
        }
    } catch (error) {
        console.error('Error starting VNC:', error);
        showToast('Error starting VNC container', 'error');
        startBtn.disabled = false;
        startBtn.innerHTML = '<i class="fas fa-play-circle"></i> Start VNC Container';
    }
}

async function stopVNCAndSave() {
    showConfirm(
        'Save Authentication',
        'Have you completed the Google authentication in VNC?\n\nClick Confirm to stop VNC and save the authentication.',
        async () => {
            // Find the "Stop VNC & Save" button and show spinner
            const vncRunningDiv = document.getElementById('vnc-running');
            const originalHTML = vncRunningDiv.innerHTML;

            vncRunningDiv.innerHTML = `
                <div class="bg-blue-50 border-l-4 border-blue-400 p-4">
                    <p class="text-blue-900 font-bold mb-2 flex items-center gap-2">
                        <i class="fas fa-spinner fa-spin"></i> Stopping VNC and saving authentication...
                    </p>
                    <p class="text-sm text-blue-800">
                        Please wait, this may take a few seconds.
                    </p>
                </div>
            `;

            try {
                const response = await fetch('/api/stop-auth', {
                    method: 'POST'
                });

                const data = await response.json();

                if (data.status === 'stopped') {
                    // Save profile info before closing VNC modal
                    const profileName = currentAuthProfileNum; // This is the profile name (e.g., "family")
                    const displayName = currentAuthProfileName; // This is the display name (e.g., "Family Photos")

                    if (isReAuthMode) {
                        // Re-auth mode: just close and show success
                        showToast('Re-authentication completed successfully!', 'success');
                        closeVNCModal();
                    } else {
                        // Initial auth mode: open configuration modal
                        showToast('Authentication saved successfully! Opening configuration...', 'success');
                        closeVNCModal();

                        // Open configuration modal after a short delay
                        setTimeout(() => {
                            openConfigModal(profileName, displayName);
                        }, 500);
                    }

                    // Reload profiles in background
                    setTimeout(() => {
                        loadContainers();
                        loadStats();
                        loadAvailableProfiles();
                    }, 1000);
                } else {
                    // Restore original HTML on error
                    vncRunningDiv.innerHTML = originalHTML;
                    showToast('Error stopping VNC: ' + (data.error || 'Unknown error'), 'error');
                }
            } catch (error) {
                // Restore original HTML on error
                vncRunningDiv.innerHTML = originalHTML;
                console.error('Error stopping VNC:', error);
                showToast('Error stopping VNC container', 'error');
            }
        }
    );
}

// VNC Viewer
let currentVNCUrl = '';

function openVNCViewer(profileName, port) {
    const currentHost = window.location.hostname;
    const protocol = window.location.protocol;
    currentVNCUrl = `${protocol}//${currentHost}:${port}/vnc.html?autoconnect=true&resize=scale`;

    document.getElementById('vnc-viewer-profile-name').textContent = profileName;
    document.getElementById('vnc-viewer-iframe').src = currentVNCUrl;
    document.getElementById('vnc-viewer-modal').classList.remove('hidden');
}

function closeVNCViewer() {
    document.getElementById('vnc-viewer-modal').classList.add('hidden');
    document.getElementById('vnc-viewer-iframe').src = '';
    currentVNCUrl = '';
}

function openVNCInteractive() {
    if (currentVNCUrl) {
        window.open(currentVNCUrl, '_blank');
    }
}

// Folder Picker
let currentFolderPath = '/';

async function openFolderPicker() {
    // Get current value or start from home
    const currentValue = document.getElementById('config-photo-dir').value.trim();
    currentFolderPath = currentValue || '/home';

    document.getElementById('folder-picker-modal').classList.remove('hidden');
    await loadFolderContents(currentFolderPath);
}

function closeFolderPicker() {
    document.getElementById('folder-picker-modal').classList.add('hidden');
}

async function loadFolderContents(path) {
    try {
        const response = await fetch('/api/browse-directories', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ path: path })
        });

        const data = await response.json();

        if (data.error) {
            showToast('Error: ' + data.error, 'error');
            return;
        }

        currentFolderPath = data.current_path;
        document.getElementById('folder-picker-path').value = data.current_path;

        const listDiv = document.getElementById('folder-picker-list');
        listDiv.innerHTML = '';

        // Add parent directory link if not at root
        if (data.parent_path) {
            const parentDiv = document.createElement('div');
            parentDiv.className = 'flex items-center gap-2 p-2 hover:bg-gray-100 rounded cursor-pointer';
            parentDiv.onclick = () => loadFolderContents(data.parent_path);
            parentDiv.innerHTML = `
                <i class="fas fa-level-up-alt text-gray-500"></i>
                <span class="font-medium text-gray-700">..</span>
                <span class="text-xs text-gray-500">(parent directory)</span>
            `;
            listDiv.appendChild(parentDiv);
        }

        // Add directories
        if (data.directories.length === 0) {
            listDiv.innerHTML += '<p class="text-gray-500 text-sm p-4 text-center">No subdirectories found</p>';
        } else {
            data.directories.forEach(dir => {
                const dirDiv = document.createElement('div');
                dirDiv.className = 'flex items-center gap-2 p-2 hover:bg-blue-50 rounded cursor-pointer';

                if (dir.unreadable) {
                    dirDiv.className += ' opacity-50';
                    dirDiv.innerHTML = `
                        <i class="fas fa-folder text-gray-400"></i>
                        <span class="flex-1 text-gray-500">${dir.name}</span>
                        <span class="text-xs text-red-500"><i class="fas fa-lock"></i> No permission</span>
                    `;
                } else {
                    dirDiv.onclick = () => loadFolderContents(dir.path);
                    dirDiv.innerHTML = `
                        <i class="fas fa-folder text-yellow-500"></i>
                        <span class="flex-1 text-gray-800">${dir.name}</span>
                        <i class="fas fa-chevron-right text-gray-400"></i>
                    `;
                }

                listDiv.appendChild(dirDiv);
            });
        }

        // Update info
        const infoText = data.directories.length === 1
            ? '1 directory'
            : `${data.directories.length} directories`;
        const filesText = data.files_count > 0 ? `, ${data.files_count} files` : '';
        document.getElementById('folder-picker-info').textContent = infoText + filesText;

    } catch (error) {
        console.error('Error loading folder contents:', error);
        showToast('Error loading directory contents', 'error');
    }
}

async function navigateToPath() {
    const path = document.getElementById('folder-picker-path').value.trim();
    if (path) {
        await loadFolderContents(path);
    }
}

function selectCurrentFolder() {
    document.getElementById('config-photo-dir').value = currentFolderPath;
    closeFolderPicker();
    showToast('Directory selected: ' + currentFolderPath, 'success');
}

// Handle Enter key in profile name input
document.addEventListener('DOMContentLoaded', function() {
    const input = document.getElementById('profile-name-input');
    if (input) {
        input.addEventListener('keypress', function(event) {
            if (event.key === 'Enter') {
                createNewProfile();
            }
        });
    }

    // Handle Enter key in folder picker path input
    const folderInput = document.getElementById('folder-picker-path');
    if (folderInput) {
        folderInput.addEventListener('keypress', function(event) {
            if (event.key === 'Enter') {
                navigateToPath();
            }
        });
    }
});

// Rebuild Docker image (global - compiles gphotos-cdp and rebuilds image)
let rebuildEventSource = null;
let rebuildLogBuffer = []; // Display buffer (limited)
let rebuildFullLog = [];   // Full log for download
const MAX_LOG_LINES = 100; // Keep only last 100 lines in display

async function rebuildDockerImage() {
    showConfirm(
        'Rebuild Docker Image',
        `This will:\n- Compile the latest gphotos-cdp code\n- Rebuild the Docker image from scratch\n- Restart ALL running containers with the new image\n\nThis process may take 2-3 minutes.\n\nContinue?`,
        async () => {
            // Open rebuild modal
            document.getElementById('rebuild-modal').classList.remove('hidden');
            document.getElementById('rebuild-log').textContent = '';
            document.getElementById('rebuild-close-btn').classList.add('hidden');
            document.getElementById('rebuild-download-btn').classList.add('hidden');
            document.getElementById('rebuild-log-truncated').classList.add('hidden');

            // Reset log buffers
            rebuildLogBuffer = [];
            rebuildFullLog = [];

            // Update status
            updateRebuildStatus('Building Docker image...', 'Please wait, this may take a few minutes', 'building');

            // Start streaming rebuild log
            rebuildEventSource = new EventSource('/api/rebuild-image/stream');

            rebuildEventSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    const logContent = document.getElementById('rebuild-log');

                    switch(data.type) {
                        case 'status':
                            updateRebuildStatus(data.message, 'In progress...', 'building');
                            break;

                        case 'log':
                            // Add to full log (unlimited)
                            rebuildFullLog.push(data.message);

                            // Add to display buffer and keep only last MAX_LOG_LINES
                            rebuildLogBuffer.push(data.message);
                            if (rebuildLogBuffer.length > MAX_LOG_LINES) {
                                rebuildLogBuffer.shift();
                                // Show truncation warning
                                document.getElementById('rebuild-log-truncated').classList.remove('hidden');
                            }

                            // Update display
                            logContent.textContent = rebuildLogBuffer.join('');

                            // Auto-scroll to bottom
                            if (document.getElementById('rebuild-auto-scroll').checked) {
                                const logContainer = document.getElementById('rebuild-log-container');
                                if (logContainer) {
                                    requestAnimationFrame(() => {
                                        logContainer.scrollTop = logContainer.scrollHeight;
                                    });
                                }
                            }
                            break;

                        case 'error':
                            updateRebuildStatus('Build Failed', data.message, 'error');
                            rebuildEventSource.close();
                            enableRebuildClose();
                            showToast('Build failed! Check the log for details.', 'error');
                            break;

                        case 'warning':
                            updateRebuildStatus('Completed with warnings', data.message, 'warning');
                            rebuildEventSource.close();
                            enableRebuildClose();
                            showToast(data.message, 'warning');
                            reloadContainersAfterRebuild();
                            break;

                        case 'complete':
                            updateRebuildStatus('Build Completed Successfully!',
                                `Successfully rebuilt image and restarted ${data.restarted_count} containers`,
                                'success');
                            rebuildEventSource.close();
                            enableRebuildClose();
                            showToast('Docker image rebuilt successfully!', 'success');
                            reloadContainersAfterRebuild();
                            break;
                    }
                } catch (e) {
                    console.error('Error parsing rebuild event:', e);
                }
            };

            rebuildEventSource.onerror = function(error) {
                console.error('Rebuild stream error:', error);
                updateRebuildStatus('Stream Error', 'Connection to rebuild stream lost', 'error');
                rebuildEventSource.close();
                enableRebuildClose();
                showToast('Error during rebuild. Check logs.', 'error');
            };
        }
    );
}

function updateRebuildStatus(title, detail, status) {
    const statusDiv = document.getElementById('rebuild-status');
    const titleEl = document.getElementById('rebuild-status-text');
    const detailEl = document.getElementById('rebuild-status-detail');

    titleEl.textContent = title;
    detailEl.textContent = detail;

    // Update colors based on status
    statusDiv.className = 'p-4 border-b';
    const iconEl = statusDiv.querySelector('i');

    switch(status) {
        case 'building':
            statusDiv.classList.add('bg-blue-50');
            titleEl.className = 'font-semibold text-blue-900';
            detailEl.className = 'text-sm text-blue-700';
            iconEl.className = 'fas fa-spinner fa-spin text-blue-600 text-xl';
            break;
        case 'success':
            statusDiv.classList.add('bg-green-50');
            titleEl.className = 'font-semibold text-green-900';
            detailEl.className = 'text-sm text-green-700';
            iconEl.className = 'fas fa-check-circle text-green-600 text-xl';
            break;
        case 'error':
            statusDiv.classList.add('bg-red-50');
            titleEl.className = 'font-semibold text-red-900';
            detailEl.className = 'text-sm text-red-700';
            iconEl.className = 'fas fa-exclamation-circle text-red-600 text-xl';
            break;
        case 'warning':
            statusDiv.classList.add('bg-yellow-50');
            titleEl.className = 'font-semibold text-yellow-900';
            detailEl.className = 'text-sm text-yellow-700';
            iconEl.className = 'fas fa-exclamation-triangle text-yellow-600 text-xl';
            break;
    }
}

function enableRebuildClose() {
    document.getElementById('rebuild-close-btn').classList.remove('hidden');
    document.getElementById('rebuild-download-btn').classList.remove('hidden');
}

function closeRebuildModal() {
    if (rebuildEventSource) {
        rebuildEventSource.close();
        rebuildEventSource = null;
    }
    document.getElementById('rebuild-modal').classList.add('hidden');
}

function downloadRebuildLog() {
    // Use full log for download, not just the displayed buffer
    const logs = rebuildFullLog.join('');
    const blob = new Blob([logs], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `rebuild-log-${new Date().toISOString()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
}

function reloadContainersAfterRebuild() {
    setTimeout(() => {
        loadContainers();
        loadStats();
        loadAvailableProfiles();
    }, 2000);
}

// ==========================================
// Health Check Functions
// ==========================================

let healthCheckEventSource = null;

async function openHealthCheckModal() {
    document.getElementById('healthcheck-modal').classList.remove('hidden');

    // Reset UI
    document.getElementById('healthcheck-tests').innerHTML = '';
    document.getElementById('healthcheck-log').textContent = '';
    document.getElementById('healthcheck-log-container').classList.add('hidden');
    document.getElementById('healthcheck-status').classList.add('hidden');
    document.getElementById('healthcheck-summary').classList.add('hidden');
    document.getElementById('healthcheck-setup').classList.remove('hidden');
    document.getElementById('healthcheck-run-btn').disabled = false;
    document.getElementById('healthcheck-run-btn').innerHTML = '<i class="fas fa-play"></i> Run Health Check';

    // Load profiles
    try {
        const response = await fetch('/api/healthcheck/profiles');
        const profiles = await response.json();
        const select = document.getElementById('healthcheck-profile');

        if (profiles.length === 0) {
            select.innerHTML = '<option value="">No authenticated profiles found</option>';
            document.getElementById('healthcheck-run-btn').disabled = true;
        } else {
            select.innerHTML = profiles.map(p =>
                `<option value="${p.name}">${p.display_name}</option>`
            ).join('');
        }
    } catch (error) {
        console.error('Error loading healthcheck profiles:', error);
        showToast('Error loading profiles', 'error');
    }
}

function closeHealthCheckModal() {
    document.getElementById('healthcheck-modal').classList.add('hidden');
    if (healthCheckEventSource) {
        healthCheckEventSource.close();
        healthCheckEventSource = null;
    }
}

function runHealthCheck() {
    const profileName = document.getElementById('healthcheck-profile').value;
    if (!profileName) {
        showToast('Please select a profile', 'warning');
        return;
    }

    // Update UI
    document.getElementById('healthcheck-run-btn').disabled = true;
    document.getElementById('healthcheck-run-btn').innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running...';
    document.getElementById('healthcheck-tests').innerHTML = '';
    document.getElementById('healthcheck-log').textContent = '';
    document.getElementById('healthcheck-log-container').classList.remove('hidden');
    document.getElementById('healthcheck-status').classList.remove('hidden');
    document.getElementById('healthcheck-summary').classList.add('hidden');
    updateHealthCheckStatus('Starting health check...', '', 'running');

    // Start SSE
    healthCheckEventSource = new EventSource(`/api/healthcheck/${profileName}/stream`);

    // POST triggers the stream; EventSource connects via GET implicit in the browser
    // Actually, EventSource only supports GET. We need to use fetch for POST + SSE.
    healthCheckEventSource.close();
    healthCheckEventSource = null;

    // Use fetch with ReadableStream for POST SSE
    startHealthCheckStream(profileName);
}

async function startHealthCheckStream(profileName) {
    try {
        const response = await fetch(`/api/healthcheck/${profileName}/stream`, {
            method: 'POST',
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Process complete SSE messages
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.substring(6));
                        handleHealthCheckEvent(data);
                    } catch (e) {
                        // Ignore parse errors
                    }
                }
            }
        }

        // Process remaining buffer
        if (buffer.startsWith('data: ')) {
            try {
                const data = JSON.parse(buffer.substring(6));
                handleHealthCheckEvent(data);
            } catch (e) {}
        }
    } catch (error) {
        console.error('Health check stream error:', error);
        updateHealthCheckStatus('Connection Error', 'Failed to connect to health check stream', 'error');
        document.getElementById('healthcheck-run-btn').disabled = false;
        document.getElementById('healthcheck-run-btn').innerHTML = '<i class="fas fa-play"></i> Run Health Check';
    }
}

function handleHealthCheckEvent(data) {
    switch (data.type) {
        case 'status':
            updateHealthCheckStatus(data.message, '', 'running');
            break;

        case 'test_result':
            addHealthCheckTestResult(data.data);
            break;

        case 'summary':
            showHealthCheckSummary(data.data);
            break;

        case 'log':
            appendHealthCheckLog(data.message);
            break;

        case 'complete':
            updateHealthCheckStatus(data.message, '', data.message.includes('successfully') ? 'success' : 'warning');
            document.getElementById('healthcheck-run-btn').disabled = false;
            document.getElementById('healthcheck-run-btn').innerHTML = '<i class="fas fa-play"></i> Run Again';
            break;

        case 'error':
            updateHealthCheckStatus('Error', data.message, 'error');
            document.getElementById('healthcheck-run-btn').disabled = false;
            document.getElementById('healthcheck-run-btn').innerHTML = '<i class="fas fa-play"></i> Run Again';
            break;
    }
}

function updateHealthCheckStatus(title, detail, status) {
    const statusDiv = document.getElementById('healthcheck-status');
    const titleEl = document.getElementById('healthcheck-status-text');
    const detailEl = document.getElementById('healthcheck-status-detail');
    const iconEl = document.getElementById('healthcheck-status-icon');

    statusDiv.classList.remove('hidden');
    titleEl.textContent = title;
    detailEl.textContent = detail;

    statusDiv.className = 'p-4 border-b';
    switch (status) {
        case 'running':
            statusDiv.classList.add('bg-blue-50');
            titleEl.className = 'font-semibold text-blue-900';
            detailEl.className = 'text-sm text-blue-700';
            iconEl.className = 'fas fa-spinner fa-spin text-blue-600 text-xl';
            break;
        case 'success':
            statusDiv.classList.add('bg-green-50');
            titleEl.className = 'font-semibold text-green-900';
            detailEl.className = 'text-sm text-green-700';
            iconEl.className = 'fas fa-check-circle text-green-600 text-xl';
            break;
        case 'error':
            statusDiv.classList.add('bg-red-50');
            titleEl.className = 'font-semibold text-red-900';
            detailEl.className = 'text-sm text-red-700';
            iconEl.className = 'fas fa-exclamation-circle text-red-600 text-xl';
            break;
        case 'warning':
            statusDiv.classList.add('bg-yellow-50');
            titleEl.className = 'font-semibold text-yellow-900';
            detailEl.className = 'text-sm text-yellow-700';
            iconEl.className = 'fas fa-exclamation-triangle text-yellow-600 text-xl';
            break;
    }
}

function addHealthCheckTestResult(test) {
    const container = document.getElementById('healthcheck-tests');

    const statusIcons = {
        'pass': '<i class="fas fa-check-circle text-green-500"></i>',
        'fail': '<i class="fas fa-times-circle text-red-500"></i>',
        'skip': '<i class="fas fa-minus-circle text-gray-400"></i>',
    };

    const statusColors = {
        'pass': 'bg-green-50 border-green-200',
        'fail': 'bg-red-50 border-red-200',
        'skip': 'bg-gray-50 border-gray-200',
    };

    const div = document.createElement('div');
    div.className = `flex items-start gap-3 p-3 rounded-lg border ${statusColors[test.status] || 'bg-gray-50 border-gray-200'}`;
    div.innerHTML = `
        <div class="mt-0.5">${statusIcons[test.status] || ''}</div>
        <div class="flex-1 min-w-0">
            <div class="font-medium text-gray-800 text-sm">${test.name}</div>
            <div class="text-xs text-gray-600 mt-1 break-words">${test.message}</div>
        </div>
        <span class="text-xs font-medium px-2 py-1 rounded ${
            test.status === 'pass' ? 'bg-green-100 text-green-700' :
            test.status === 'fail' ? 'bg-red-100 text-red-700' :
            'bg-gray-100 text-gray-600'
        }">${test.status.toUpperCase()}</span>
    `;

    container.appendChild(div);

    // Update running count
    const passCount = container.querySelectorAll('.text-green-500').length;
    const failCount = container.querySelectorAll('.text-red-500').length;
    const total = container.children.length;
    updateHealthCheckStatus(`Running tests... (${total})`, `${passCount} passed, ${failCount} failed`, 'running');
}

function showHealthCheckSummary(summary) {
    const summaryDiv = document.getElementById('healthcheck-summary');
    summaryDiv.classList.remove('hidden');

    document.getElementById('healthcheck-passed').textContent = summary.passed;
    document.getElementById('healthcheck-failed').textContent = summary.failed;
    document.getElementById('healthcheck-total').textContent = summary.total;

    const badge = document.getElementById('healthcheck-summary-badge');
    if (summary.failed === 0) {
        badge.innerHTML = '<span class="px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm font-medium"><i class="fas fa-check"></i> All Passed</span>';
    } else {
        badge.innerHTML = `<span class="px-3 py-1 bg-red-100 text-red-700 rounded-full text-sm font-medium"><i class="fas fa-exclamation-triangle"></i> ${summary.failed} Failed</span>`;
    }
}

function appendHealthCheckLog(message) {
    const logEl = document.getElementById('healthcheck-log');
    logEl.textContent += message + '\n';

    // Auto-scroll
    const logContainer = document.getElementById('healthcheck-log-container');
    logContainer.scrollTop = logContainer.scrollHeight;
}

function toggleHealthCheckLog() {
    const logContainer = document.getElementById('healthcheck-log-container');
    const icon = document.getElementById('healthcheck-log-toggle-icon');

    if (logContainer.classList.contains('max-h-48')) {
        logContainer.classList.remove('max-h-48');
        logContainer.classList.add('max-h-96');
        icon.classList.remove('fa-chevron-down');
        icon.classList.add('fa-chevron-up');
    } else {
        logContainer.classList.remove('max-h-96');
        logContainer.classList.add('max-h-48');
        icon.classList.remove('fa-chevron-up');
        icon.classList.add('fa-chevron-down');
    }
}

// Auto-refresh containers every 10 seconds
setInterval(() => {
    loadContainers();
    loadStats();
    loadAvailableProfiles();
}, 10000);

// Initial load
loadContainers();
loadStats();
loadAvailableProfiles();

// ==========================================
// Album Management Functions
// ==========================================

// Store albums as array of {name, id} objects
let configAlbumsList = [];

// Toggle sync mode (all library vs specific albums)
function toggleSyncMode() {
    const syncMode = document.querySelector('input[name="sync-mode"]:checked').value;
    const albumsContainer = document.getElementById('albums-list-container');

    if (syncMode === 'albums') {
        albumsContainer.classList.remove('hidden');
    } else {
        albumsContainer.classList.add('hidden');
    }
}

// Open add album modal
function openAddAlbumModal() {
    document.getElementById('add-album-modal').classList.remove('hidden');
    document.getElementById('album-link-input').value = '';
    document.getElementById('album-id-display').value = '';
    document.getElementById('album-name-input').value = '';
    document.getElementById('album-id-container').classList.add('hidden');
    document.getElementById('album-name-container').classList.add('hidden');
    document.getElementById('add-album-btn').disabled = true;
    document.getElementById('album-link-input').focus();
}

// Close add album modal
function closeAddAlbumModal() {
    document.getElementById('add-album-modal').classList.add('hidden');
}

// Extract album ID from Google Photos URL
function extractAlbumIdFromUrl(url) {
    // Google Photos album URL patterns:
    // https://photos.google.com/album/ALBUM_ID
    // https://photos.google.com/share/ALBUM_ID
    // https://photos.google.com/u/0/album/ALBUM_ID

    const patterns = [
        /photos\.google\.com\/(?:u\/\d+\/)?album\/([A-Za-z0-9_-]+)/,
        /photos\.google\.com\/(?:u\/\d+\/)?share\/([A-Za-z0-9_-]+)/
    ];

    for (const pattern of patterns) {
        const match = url.match(pattern);
        if (match && match[1]) {
            return match[1];
        }
    }

    return null;
}

// Handle album link input change
function onAlbumLinkInput() {
    const linkInput = document.getElementById('album-link-input');
    const idDisplay = document.getElementById('album-id-display');
    const idContainer = document.getElementById('album-id-container');
    const nameContainer = document.getElementById('album-name-container');
    const addBtn = document.getElementById('add-album-btn');

    const url = linkInput.value.trim();
    const albumId = extractAlbumIdFromUrl(url);

    if (albumId) {
        idDisplay.value = albumId;
        idContainer.classList.remove('hidden');
        nameContainer.classList.remove('hidden');

        // Enable add button only if name is also filled
        updateAddAlbumButtonState();
    } else {
        idContainer.classList.add('hidden');
        nameContainer.classList.add('hidden');
        addBtn.disabled = true;
    }
}

// Update add album button state
function updateAddAlbumButtonState() {
    const albumId = document.getElementById('album-id-display').value.trim();
    const albumName = document.getElementById('album-name-input').value.trim();
    const addBtn = document.getElementById('add-album-btn');

    addBtn.disabled = !(albumId && albumName);
}

// Add event listener for album name input
document.addEventListener('DOMContentLoaded', function() {
    const nameInput = document.getElementById('album-name-input');
    if (nameInput) {
        nameInput.addEventListener('input', updateAddAlbumButtonState);
        nameInput.addEventListener('keypress', function(event) {
            if (event.key === 'Enter' && !document.getElementById('add-album-btn').disabled) {
                addAlbumToList();
            }
        });
    }
});

// Add album to the list
function addAlbumToList() {
    const albumId = document.getElementById('album-id-display').value.trim();
    const albumName = document.getElementById('album-name-input').value.trim();

    if (!albumId || !albumName) {
        showToast('Please enter both album link and name', 'warning');
        return;
    }

    // Check for duplicate ID
    if (configAlbumsList.some(a => a.id === albumId)) {
        showToast('This album is already in the list', 'warning');
        return;
    }

    // Sanitize album name for filesystem
    const sanitizedName = sanitizeAlbumName(albumName);

    // Add to list
    configAlbumsList.push({
        name: sanitizedName,
        id: albumId
    });

    // Update UI
    renderAlbumsList();
    updateConfigAlbumsInput();
    closeAddAlbumModal();
    showToast(`Album "${sanitizedName}" added`, 'success');
}

// Sanitize album name for filesystem use
function sanitizeAlbumName(name) {
    // Replace invalid characters with underscore
    // Keep letters, numbers, spaces, hyphens, underscores
    return name
        .replace(/[<>:"/\\|?*]/g, '_')  // Remove invalid chars
        .replace(/\s+/g, ' ')           // Normalize spaces
        .trim()
        .substring(0, 100);             // Limit length
}

// Remove album from list
function removeAlbumFromList(index) {
    const album = configAlbumsList[index];
    configAlbumsList.splice(index, 1);
    renderAlbumsList();
    updateConfigAlbumsInput();
    showToast(`Album "${album.name}" removed`, 'info');
}

// Render albums list in the config modal
function renderAlbumsList() {
    const listContainer = document.getElementById('albums-list');

    if (configAlbumsList.length === 0) {
        listContainer.innerHTML = `
            <div class="text-center text-gray-500 py-4">
                <i class="fas fa-folder-open text-2xl mb-2"></i>
                <p class="text-sm">No albums added yet</p>
            </div>
        `;
        return;
    }

    listContainer.innerHTML = configAlbumsList.map((album, index) => `
        <div class="flex items-center gap-2 p-2 bg-gray-50 rounded border border-gray-200">
            <i class="fas fa-images text-blue-500"></i>
            <div class="flex-1 min-w-0">
                <div class="font-medium text-gray-800 truncate">${album.name}</div>
                <div class="text-xs text-gray-500 font-mono truncate">${album.id}</div>
            </div>
            <button onclick="removeAlbumFromList(${index})"
                    class="p-1 text-red-500 hover:text-red-700 hover:bg-red-50 rounded">
                <i class="fas fa-trash-alt"></i>
            </button>
        </div>
    `).join('');
}

// Update hidden input with albums data
// Format: name|id,name|id (pipe separates name from id, comma separates albums)
function updateConfigAlbumsInput() {
    const input = document.getElementById('config-albums');
    if (configAlbumsList.length === 0) {
        input.value = '';
    } else {
        input.value = configAlbumsList.map(a => `${a.name}|${a.id}`).join(',');
    }
}

// Parse albums string back to array
// Format: name|id,name|id OR legacy format: id1,id2,id3
function parseAlbumsString(albumsStr) {
    if (!albumsStr || albumsStr.trim() === '' || albumsStr.toUpperCase() === 'ALL') {
        return [];
    }

    const albums = [];
    const parts = albumsStr.split(',');

    for (const part of parts) {
        const trimmed = part.trim();
        if (!trimmed) continue;

        if (trimmed.includes('|')) {
            // New format: name|id
            const [name, id] = trimmed.split('|');
            if (name && id) {
                albums.push({ name: name.trim(), id: id.trim() });
            }
        } else {
            // Legacy format: just id - use id as name
            albums.push({ name: trimmed, id: trimmed });
        }
    }

    return albums;
}

// Initialize albums list when opening config modal
function initializeAlbumsList(albumsStr) {
    configAlbumsList = parseAlbumsString(albumsStr);
    renderAlbumsList();
    updateConfigAlbumsInput();

    // Set sync mode based on whether there are albums
    const syncModeAll = document.querySelector('input[name="sync-mode"][value="all"]');
    const syncModeAlbums = document.querySelector('input[name="sync-mode"][value="albums"]');

    if (configAlbumsList.length > 0) {
        syncModeAlbums.checked = true;
        document.getElementById('albums-list-container').classList.remove('hidden');
    } else {
        syncModeAll.checked = true;
        document.getElementById('albums-list-container').classList.add('hidden');
    }
}
