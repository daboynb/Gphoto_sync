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
                                ${container.name}
                            </h3>
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

                    <div class="flex gap-2">
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

// Auto-refresh containers every 10 seconds
setInterval(() => {
    loadContainers();
    loadStats();
}, 10000);

// Initial load
loadContainers();
loadStats();
