let currentLogStream = null;
let currentContainerId = null;

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
    if (confirm('Are you sure you want to stop this container?')) {
        try {
            await fetch(`/api/container/${containerId}/stop`, { method: 'POST' });
            setTimeout(() => {
                loadContainers();
                loadStats();
            }, 1000);
        } catch (error) {
            console.error('Error stopping container:', error);
        }
    }
}

async function restartContainer(containerId) {
    if (confirm('Are you sure you want to restart this container?')) {
        try {
            await fetch(`/api/container/${containerId}/restart`, { method: 'POST' });
            setTimeout(() => {
                loadContainers();
                loadStats();
            }, 1000);
        } catch (error) {
            console.error('Error restarting container:', error);
        }
    }
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
                                        <button onclick="startVNCAuth(${profile.number}, '${profile.display_name || profile.name}')"
                                                class="px-3 py-1 bg-purple-500 text-white text-sm rounded hover:bg-purple-600">
                                            <i class="fas fa-key"></i> Authenticate
                                        </button>
                                        ${!profile.has_compose ? `
                                            <button onclick="createCompose(${profile.number})"
                                                    class="px-3 py-1 bg-blue-500 text-white text-sm rounded hover:bg-blue-600">
                                                <i class="fas fa-file-circle-plus"></i> Create Docker Compose
                                            </button>
                                        ` : `
                                            <button onclick="startProfileFromGUI(${profile.number})"
                                                    class="px-3 py-1 bg-green-500 text-white text-sm rounded hover:bg-green-600">
                                                <i class="fas fa-play"></i> Start
                                            </button>
                                        `}
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

// Create docker-compose for a profile
async function createCompose(profileNum) {
    try {
        const response = await fetch(`/api/create-compose/${profileNum}`, { method: 'POST' });
        const data = await response.json();

        if (data.status === 'created') {
            // Automatically start the profile after creating compose file
            setTimeout(() => startProfileFromGUI(profileNum), 500);
        } else {
            alert('❌ Error: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error creating compose:', error);
        alert('❌ Error creating docker-compose file');
    }
}

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
            alert('❌ Error starting profile: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error starting profile:', error);
        alert('❌ Error starting profile');
    }
}

// Delete profile (container + compose file)
async function deleteProfile(profileName) {
    // Extract profile number from name (e.g., "profile1" -> "1")
    const profileNum = profileName.replace('profile', '');

    if (!confirm(`⚠️ Are you sure you want to DELETE profile ${profileNum}?\n\nThis will:\n- Stop and remove the Docker container\n- Delete docker-compose.profile${profileNum}.yml\n\nThis action cannot be undone!`)) {
        return;
    }

    try {
        const response = await fetch(`/api/delete-profile/${profileNum}`, { method: 'DELETE' });
        const data = await response.json();

        if (data.status === 'deleted' || data.status === 'partial') {
            let message = '✅ Profile deleted:\n\n';
            if (data.success) {
                message += data.success.join('\n');
            }
            if (data.errors && data.errors.length > 0) {
                message += '\n\n⚠️ Errors:\n' + data.errors.join('\n');
            }
            alert(message);

            // Reload everything
            setTimeout(() => {
                loadContainers();
                loadStats();
                loadAvailableProfiles();
            }, 1000);
        } else {
            alert('❌ Error deleting profile: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error deleting profile:', error);
        alert('❌ Error deleting profile');
    }
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
        alert('⚠️ Please enter a profile name');
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
            alert(`✅ Profile "${data.profile_name}" created successfully!\n\nProfile number: ${data.profile_num}\n\nNext step: Authenticate this profile using VNC by running:\nPROFILE_DIR=./profile${data.profile_num} ./doauth.sh`);

            // Reload to show the new profile
            setTimeout(() => {
                loadContainers();
                loadStats();
                loadAvailableProfiles();
            }, 500);
        } else {
            alert('❌ Error creating profile: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error creating profile:', error);
        alert('❌ Error creating profile');
    }
}

// VNC Authentication
let currentAuthProfileNum = null;

function startVNCAuth(profileNum, profileName) {
    currentAuthProfileNum = profileNum;
    document.getElementById('vnc-profile-name').textContent = profileName;
    document.getElementById('vnc-auth-modal').classList.remove('hidden');

    // Reset UI
    document.getElementById('vnc-status').classList.remove('hidden');
    document.getElementById('vnc-running').classList.add('hidden');
}

function closeVNCModal() {
    document.getElementById('vnc-auth-modal').classList.add('hidden');
    currentAuthProfileNum = null;
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
        } else {
            alert('❌ Error starting VNC: ' + (data.error || 'Unknown error'));
            startBtn.disabled = false;
            startBtn.innerHTML = '<i class="fas fa-play-circle"></i> Start VNC Container';
        }
    } catch (error) {
        console.error('Error starting VNC:', error);
        alert('❌ Error starting VNC container');
        startBtn.disabled = false;
        startBtn.innerHTML = '<i class="fas fa-play-circle"></i> Start VNC Container';
    }
}

async function stopVNCAndSave() {
    if (!confirm('⚠️ Have you completed the Google authentication in VNC?\n\nClick OK to stop VNC and save the authentication.')) {
        return;
    }

    try {
        const response = await fetch('/api/stop-auth', {
            method: 'POST'
        });

        const data = await response.json();

        if (data.status === 'stopped') {
            alert('✅ Authentication saved successfully!\n\nYou can now create a docker-compose and start the container.');
            closeVNCModal();

            // Reload profiles
            setTimeout(() => {
                loadContainers();
                loadStats();
                loadAvailableProfiles();
            }, 1000);
        } else {
            alert('❌ Error stopping VNC: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error stopping VNC:', error);
        alert('❌ Error stopping VNC container');
    }
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
