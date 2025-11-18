let currentLogStream = null;
let currentContainerId = null;

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

                    <div class="flex gap-2 flex-wrap">
                        <button onclick="viewLogs('${container.id}', '${container.name}')"
                                class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm">
                            <i class="fas fa-file-lines"></i> View Logs
                        </button>
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
                            <button onclick="editProfileConfig('${container.profile}', '${container.display_name || container.name}')"
                                    class="px-4 py-2 bg-indigo-500 text-white rounded hover:bg-indigo-600 text-sm">
                                <i class="fas fa-cog"></i> Edit Config
                            </button>
                            <button onclick="deleteProfile('${container.profile}')"
                                    class="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-800 text-sm">
                                <i class="fas fa-trash"></i> Delete
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');

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

// View logs modal
async function viewLogs(containerId, containerName) {
    currentContainerId = containerId;
    document.getElementById('log-container-name').textContent = containerName;
    document.getElementById('log-modal').classList.remove('hidden');

    // Load initial logs
    try {
        const response = await fetch(`/api/container/${containerId}/logs`);
        const data = await response.json();

        if (data.logs) {
            document.getElementById('log-content').textContent = data.logs;
            scrollLogsToBottom();
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
        logContent.textContent += event.data;

        if (document.getElementById('auto-scroll').checked) {
            scrollLogsToBottom();
        }
    };

    currentLogStream.onerror = function(error) {
        console.error('Log stream error:', error);
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
    const logContent = document.getElementById('log-content');
    logContent.scrollTop = logContent.scrollHeight;
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

        profilesDiv.innerHTML = `
            <div class="bg-yellow-50 border-l-4 border-yellow-400 p-4 rounded">
                <div class="flex items-start">
                    <div class="flex-shrink-0">
                        <i class="fas fa-exclamation-triangle text-yellow-400 text-xl"></i>
                    </div>
                    <div class="ml-3 flex-1">
                        <h3 class="text-sm font-medium text-yellow-800 mb-2">
                            Available Profiles (Not Running)
                        </h3>
                        <div class="space-y-2">
                            ${profiles.map(profile => `
                                <div class="flex items-center justify-between bg-white p-3 rounded">
                                    <div>
                                        <span class="font-semibold">${profile.display_name || profile.name}</span>
                                        ${profile.display_name && profile.display_name !== profile.name ?
                                            `<span class="ml-2 text-xs text-gray-500">(${profile.name})</span>` : ''
                                        }
                                        ${!profile.has_compose ?
                                            '<span class="ml-2 text-xs bg-red-100 text-red-800 px-2 py-1 rounded">No docker-compose.yml</span>' :
                                            '<span class="ml-2 text-xs bg-green-100 text-green-800 px-2 py-1 rounded">Ready to start</span>'
                                        }
                                    </div>
                                    <div class="flex gap-2">
                                        ${!profile.has_compose ? `
                                            <button onclick="startVNCAuth(${profile.number}, '${profile.display_name || profile.name}')"
                                                    class="px-3 py-1 bg-purple-500 text-white text-sm rounded hover:bg-purple-600">
                                                <i class="fas fa-key"></i> Authenticate
                                            </button>
                                        ` : `
                                            <button onclick="startProfileFromGUI(${profile.number})"
                                                    class="px-3 py-1 bg-green-500 text-white text-sm rounded hover:bg-green-600">
                                                <i class="fas fa-play"></i> Start
                                            </button>
                                        `}
                                        <button onclick="deleteProfileFiles(${profile.number}, '${profile.display_name || profile.name}')"
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
async function startProfileFromGUI(profileNum) {
    try {
        const response = await fetch(`/api/start-profile/${profileNum}`, { method: 'POST' });
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
async function deleteProfile(profileName) {
    // Extract profile number from name (e.g., "profile1" -> "1")
    const profileNum = profileName.replace('profile', '');

    showConfirm(
        `Delete Profile ${profileNum}`,
        `This will:\n- Stop and remove the Docker container\n- Delete docker-compose.profile${profileNum}.yml\n\nThis action cannot be undone!`,
        async () => {
            try {
                const response = await fetch(`/api/delete-profile/${profileNum}`, { method: 'DELETE' });
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
async function deleteProfileFiles(profileNum, profileName) {
    showConfirm(
        `Delete Profile ${profileNum}`,
        `This will delete:\n- Profile directory (profile${profileNum})\n- docker-compose.profile${profileNum}.yml (if exists)\n- All authentication data\n\nThis action cannot be undone!`,
        async () => {
            try {
                const response = await fetch(`/api/delete-profile-files/${profileNum}`, { method: 'DELETE' });
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

function openConfigModal(profileNum, profileName) {
    currentConfigProfileNum = profileNum;
    isEditMode = false;
    document.getElementById('config-profile-name').textContent = profileName;

    // Update button text for create mode
    document.getElementById('config-save-text').textContent = 'Create Docker Compose';

    document.getElementById('config-modal').classList.remove('hidden');

    // Set default values for new profile
    document.getElementById('config-cron').value = `0 ${2 + profileNum} * * *`;
    document.getElementById('config-run-on-startup').checked = true;
    document.getElementById('config-loglevel').value = 'info';
    document.getElementById('config-workers').value = 6;
    document.getElementById('config-albums').value = '';
    document.getElementById('config-timezone').value = 'Europe/Rome';

    // Advanced options defaults
    document.getElementById('config-puid').value = 1000;
    document.getElementById('config-pgid').value = 1000;
    document.getElementById('config-legacy-mode').checked = false;
    document.getElementById('config-restart-schedule').value = '';
    document.getElementById('config-healthcheck-url').value = '';

    // Hide advanced options by default
    document.getElementById('advanced-options').classList.add('hidden');
    document.getElementById('advanced-toggle-icon').classList.remove('rotate-180');
}

async function editProfileConfig(profileName, displayName) {
    // Extract profile number from profile name (e.g., "profile1" -> 1)
    const profileNum = parseInt(profileName.replace('profile', ''));

    currentConfigProfileNum = profileNum;
    isEditMode = true;
    document.getElementById('config-profile-name').textContent = displayName;

    // Update button text for edit mode
    document.getElementById('config-save-text').textContent = 'Update Configuration';

    try {
        // Load current configuration
        const response = await fetch(`/api/get-config/${profileNum}`);
        const config = await response.json();

        if (config.error) {
            showToast('Error loading configuration: ' + config.error, 'error');
            return;
        }

        // Populate form with current values
        document.getElementById('config-cron').value = config.cron_schedule || `0 ${2 + profileNum} * * *`;
        document.getElementById('config-run-on-startup').checked = config.run_on_startup;
        document.getElementById('config-loglevel').value = config.loglevel || 'info';
        document.getElementById('config-workers').value = config.worker_count || 6;
        document.getElementById('config-albums').value = config.albums || '';
        document.getElementById('config-timezone').value = config.timezone || 'Europe/Rome';

        // Advanced options
        document.getElementById('config-puid').value = config.puid || 1000;
        document.getElementById('config-pgid').value = config.pgid || 1000;
        document.getElementById('config-legacy-mode').checked = (config.gphotos_cdp_args || '').includes('-legacy');
        document.getElementById('config-restart-schedule').value = config.restart_schedule || '';
        document.getElementById('config-healthcheck-url').value = config.healthcheck_url || '';

        // Hide advanced options by default
        document.getElementById('advanced-options').classList.add('hidden');
        document.getElementById('advanced-toggle-icon').classList.remove('rotate-180');

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

async function saveConfiguration() {
    // Basic configuration
    const config = {
        cron_schedule: document.getElementById('config-cron').value.trim(),
        run_on_startup: document.getElementById('config-run-on-startup').checked,
        loglevel: document.getElementById('config-loglevel').value,
        worker_count: parseInt(document.getElementById('config-workers').value),
        albums: document.getElementById('config-albums').value.trim(),
        timezone: document.getElementById('config-timezone').value.trim(),

        // Advanced options
        puid: parseInt(document.getElementById('config-puid').value),
        pgid: parseInt(document.getElementById('config-pgid').value),
        legacy_mode: document.getElementById('config-legacy-mode').checked,
        restart_schedule: document.getElementById('config-restart-schedule').value.trim(),
        healthcheck_url: document.getElementById('config-healthcheck-url').value.trim()
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
            // Save profile number before closing modal
            const profileNum = currentConfigProfileNum;

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
                        const recreateResp = await fetch(`/api/recreate-profile/${profileNum}`, { method: 'POST' });
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
                setTimeout(() => startProfileFromGUI(profileNum), 500);
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

function startVNCAuth(profileNum, profileName) {
    currentAuthProfileNum = profileNum;
    currentAuthProfileName = profileName;
    document.getElementById('vnc-profile-name').textContent = profileName;
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
        const response = await fetch(`/api/start-auth/${currentAuthProfileNum}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.status === 'started') {
            // Show VNC running UI
            document.getElementById('vnc-status').classList.add('hidden');
            document.getElementById('vnc-running').classList.remove('hidden');
            showToast('VNC container started successfully', 'success');
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
                    showToast('Authentication saved successfully! Opening configuration...', 'success');

                    // Save profile info before closing VNC modal
                    const profileNum = currentAuthProfileNum;
                    const profileName = currentAuthProfileName;

                    closeVNCModal();

                    // Open configuration modal after a short delay
                    setTimeout(() => {
                        openConfigModal(profileNum, profileName);
                    }, 500);

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
});

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
