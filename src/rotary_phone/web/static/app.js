/**
 * Rotary Phone Admin - Main Application JavaScript
 */

// =============================================================================
// State Management
// =============================================================================

let currentPage = 'dashboard';
let allowlistData = { allowlist: [], allow_all: false };
let speedDialData = {};
let callLogState = {
    calls: [],
    currentPage: 0,
    pageSize: 20,
    hasMore: false,
    selectedCallId: null
};
let searchTimeout = null;
let ringSettings = { ring_duration: 2.0, ring_pause: 4.0 };
let audioGainSettings = { input_gain: 1.0, output_volume: 1.0 };
let ringTestTimeout = null;
let soundFiles = [];
let soundAssignments = {};
let currentlyPlaying = null;

// =============================================================================
// Navigation
// =============================================================================

function showPage(pageName) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    document.getElementById('page-' + pageName).classList.add('active');
    event.target.closest('.nav-item').classList.add('active');
    currentPage = pageName;

    if (pageName === 'calls') {
        callLogState.currentPage = 0;
        loadCallLog();
    } else if (pageName === 'settings') {
        loadAllowlist();
        loadSpeedDial();
        loadSoundFiles();
        loadSystemConfig();
    } else if (pageName === 'dashboard') {
        loadStatus();
        loadDashboardStats();
        loadRecentCalls();
    }
}

function toggleSection(name) {
    const section = document.getElementById('section-' + name);
    section.classList.toggle('open');
}

// =============================================================================
// Status
// =============================================================================

async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        const state = data.phone.state;

        // Update visual
        const visual = document.getElementById('phone-visual');
        visual.className = 'phone-visual state-' + state.toLowerCase();

        // Update text
        document.getElementById('status-state').textContent = formatState(state);
        document.getElementById('status-detail').textContent = getStateDescription(state);

        // Update number
        const numberEl = document.getElementById('status-number');
        if (data.phone.dialed_number) {
            numberEl.textContent = data.phone.dialed_number;
            numberEl.style.display = 'block';
        } else {
            numberEl.style.display = 'none';
        }

        // Update error
        const errorEl = document.getElementById('status-error');
        if (data.phone.error_message) {
            errorEl.textContent = data.phone.error_message;
            errorEl.style.display = 'block';
        } else {
            errorEl.style.display = 'none';
        }

        // Connection status
        document.getElementById('connection-dot').className = 'status-dot';
        document.getElementById('connection-text').textContent = 'Connected';
    } catch (error) {
        document.getElementById('connection-dot').className = 'status-dot offline';
        document.getElementById('connection-text').textContent = 'Offline';
    }
}

function formatState(state) {
    const states = {
        'idle': 'Idle',
        'off_hook_waiting': 'Off Hook',
        'dialing': 'Dialing',
        'validating': 'Validating',
        'calling': 'Calling',
        'ringing': 'Incoming Call',
        'connected': 'Connected',
        'error': 'Error'
    };
    return states[state.toLowerCase()] || state;
}

function getStateDescription(state) {
    const descriptions = {
        'idle': 'Phone is on hook, ready for calls',
        'off_hook_waiting': 'Waiting for digits to be dialed',
        'dialing': 'Entering phone number',
        'validating': 'Checking number',
        'calling': 'Attempting to connect',
        'ringing': 'Someone is calling',
        'connected': 'Call in progress',
        'error': 'An error occurred'
    };
    return descriptions[state.toLowerCase()] || '';
}

// =============================================================================
// Dashboard Stats
// =============================================================================

async function loadDashboardStats() {
    try {
        const response = await fetch('/api/calls/stats?days=7');
        if (!response.ok) return;

        const data = await response.json();
        const stats = data.stats;

        document.getElementById('dash-stat-total').textContent = stats.total_calls || 0;
        document.getElementById('dash-stat-completed').textContent = stats.by_status?.completed || 0;
        document.getElementById('dash-stat-missed').textContent = stats.by_status?.missed || 0;
        document.getElementById('dash-stat-failed').textContent = stats.by_status?.failed || 0;
        document.getElementById('dash-stat-duration').textContent = formatDuration(stats.avg_duration_seconds || 0);
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// =============================================================================
// Recent Calls (Dashboard)
// =============================================================================

async function loadRecentCalls() {
    const tbody = document.getElementById('recent-calls-body');
    try {
        const response = await fetch('/api/calls?limit=5');
        if (!response.ok) {
            tbody.innerHTML = '<tr><td colspan="5" class="table-empty">Unable to load calls</td></tr>';
            return;
        }

        const data = await response.json();
        renderCallTable(tbody, data.calls, true);
    } catch (error) {
        tbody.innerHTML = '<tr><td colspan="5" class="table-empty">Unable to load calls</td></tr>';
    }
}

// =============================================================================
// Call Log
// =============================================================================

function debounceSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => loadCallLog(), 300);
}

async function loadCallLog() {
    const tbody = document.getElementById('call-log-body');
    const search = document.getElementById('call-search').value;
    const direction = document.getElementById('call-direction').value;
    const status = document.getElementById('call-status').value;
    const offset = callLogState.currentPage * callLogState.pageSize;

    let url = `/api/calls?limit=${callLogState.pageSize}&offset=${offset}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    if (direction) url += `&direction=${encodeURIComponent(direction)}`;
    if (status) url += `&status=${encodeURIComponent(status)}`;

    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load calls');

        const data = await response.json();
        callLogState.calls = data.calls;
        callLogState.hasMore = data.pagination.has_more;

        renderCallTable(tbody, data.calls, false);
        updatePagination();
    } catch (error) {
        tbody.innerHTML = `<tr><td colspan="5" class="table-empty" style="color: var(--red);">Error: ${error.message}</td></tr>`;
    }
}

function renderCallTable(tbody, calls, isRecent) {
    if (calls.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="table-empty">No calls found</td></tr>';
        return;
    }

    tbody.innerHTML = '';
    calls.forEach(call => {
        const tr = document.createElement('tr');
        tr.onclick = () => showCallDetails(call.id);
        tr.style.cursor = 'pointer';

        const dirClass = call.direction === 'inbound' ? 'direction-in' : 'direction-out';
        const dirIcon = call.direction === 'inbound' ? '&#8595;' : '&#8593;';
        const number = call.direction === 'inbound'
            ? (call.caller_id || 'Unknown')
            : (call.destination || call.dialed_number || 'Unknown');

        tr.innerHTML = `
            <td>${isRecent ? formatTimeAgo(call.timestamp) : formatDateTime(call.timestamp)}</td>
            <td><span class="direction ${dirClass}"><span class="direction-icon">${dirIcon}</span> ${call.direction}</span></td>
            <td class="phone-number">${escapeHtml(number)}</td>
            <td>${formatDuration(call.duration_seconds)}</td>
            <td><span class="badge badge-${call.status}">${call.status}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

function updatePagination() {
    document.getElementById('prev-page').disabled = callLogState.currentPage === 0;
    document.getElementById('next-page').disabled = !callLogState.hasMore;
    document.getElementById('page-info').textContent = `Page ${callLogState.currentPage + 1}`;
}

function prevPage() {
    if (callLogState.currentPage > 0) {
        callLogState.currentPage--;
        loadCallLog();
    }
}

function nextPage() {
    if (callLogState.hasMore) {
        callLogState.currentPage++;
        loadCallLog();
    }
}

async function showCallDetails(callId) {
    callLogState.selectedCallId = callId;
    try {
        const response = await fetch(`/api/calls/${callId}`);
        if (!response.ok) throw new Error('Call not found');

        const data = await response.json();
        const call = data.call;

        document.getElementById('call-modal-content').innerHTML = `
            <div class="detail-row">
                <span class="detail-label">Direction</span>
                <span class="detail-value">${call.direction}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Status</span>
                <span class="detail-value"><span class="badge badge-${call.status}">${call.status}</span></span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Started</span>
                <span class="detail-value">${formatDateTime(call.timestamp)}</span>
            </div>
            ${call.caller_id ? `<div class="detail-row"><span class="detail-label">Caller ID</span><span class="detail-value phone-number">${escapeHtml(call.caller_id)}</span></div>` : ''}
            ${call.dialed_number ? `<div class="detail-row"><span class="detail-label">Dialed</span><span class="detail-value phone-number">${escapeHtml(call.dialed_number)}</span></div>` : ''}
            ${call.destination ? `<div class="detail-row"><span class="detail-label">Destination</span><span class="detail-value phone-number">${escapeHtml(call.destination)}</span></div>` : ''}
            ${call.speed_dial_code ? `<div class="detail-row"><span class="detail-label">Speed Dial</span><span class="detail-value">${escapeHtml(call.speed_dial_code)}</span></div>` : ''}
            <div class="detail-row">
                <span class="detail-label">Duration</span>
                <span class="detail-value">${formatDuration(call.duration_seconds)}</span>
            </div>
            ${call.error_message ? `<div class="detail-row"><span class="detail-label">Error</span><span class="detail-value" style="color: var(--red);">${escapeHtml(call.error_message)}</span></div>` : ''}
        `;

        document.getElementById('call-modal').classList.add('active');
    } catch (error) {
        showMessage('calls-message', 'error', error.message);
    }
}

function closeCallModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('call-modal').classList.remove('active');
    callLogState.selectedCallId = null;
}

async function deleteCall() {
    if (!callLogState.selectedCallId) return;
    if (!confirm('Delete this call record?')) return;

    try {
        const response = await fetch(`/api/calls/${callLogState.selectedCallId}`, { method: 'DELETE' });
        if (!response.ok) throw new Error('Failed to delete');

        closeCallModal();
        showMessage('calls-message', 'success', 'Call deleted');
        loadCallLog();
        loadDashboardStats();
    } catch (error) {
        showMessage('calls-message', 'error', error.message);
    }
}

// =============================================================================
// Allowlist
// =============================================================================

async function loadAllowlist() {
    try {
        const response = await fetch('/api/allowlist');
        allowlistData = await response.json();
        document.getElementById('allow-all-toggle').checked = allowlistData.allow_all;
        updateAllowlistUI();
    } catch (error) {
        showMessage('settings-message', 'error', 'Failed to load allowlist');
    }
}

function updateAllowlistUI() {
    const container = document.getElementById('allowlist-entries-container');
    const entriesDiv = document.getElementById('allowlist-entries');
    const toggle = document.getElementById('allow-all-toggle');

    container.style.display = toggle.checked ? 'none' : 'block';
    if (toggle.checked) return;

    const entries = allowlistData.allowlist.filter(e => e !== '*');
    if (entries.length === 0) {
        entriesDiv.innerHTML = '<p style="color: var(--text-secondary); font-size: 14px;">No numbers added. Click "Add Number" to start.</p>';
        return;
    }

    entriesDiv.innerHTML = '';
    entries.forEach((entry, i) => {
        const div = document.createElement('div');
        div.className = 'list-item';
        div.innerHTML = `
            <input type="tel" class="list-item-input" value="${escapeHtml(entry)}"
                   onchange="updateAllowlistEntry(${i}, this.value)" placeholder="+12065551234">
            <button class="btn btn-danger btn-icon" onclick="removeAllowlistEntry(${i})">&#10005;</button>
        `;
        entriesDiv.appendChild(div);
    });
}

function toggleAllowAll() {
    const toggle = document.getElementById('allow-all-toggle');
    allowlistData.allow_all = toggle.checked;
    if (toggle.checked) {
        allowlistData._savedEntries = allowlistData.allowlist.filter(e => e !== '*');
        allowlistData.allowlist = ['*'];
    } else {
        allowlistData.allowlist = allowlistData._savedEntries || [];
    }
    updateAllowlistUI();
}

function addAllowlistEntry() {
    const entries = allowlistData.allowlist.filter(e => e !== '*');
    entries.push('');
    allowlistData.allowlist = entries;
    updateAllowlistUI();
    setTimeout(() => {
        const inputs = document.querySelectorAll('#allowlist-entries input');
        if (inputs.length) inputs[inputs.length - 1].focus();
    }, 50);
}

function updateAllowlistEntry(index, value) {
    const entries = allowlistData.allowlist.filter(e => e !== '*');
    entries[index] = value;
    allowlistData.allowlist = entries;
}

function removeAllowlistEntry(index) {
    const entries = allowlistData.allowlist.filter(e => e !== '*');
    entries.splice(index, 1);
    allowlistData.allowlist = entries;
    updateAllowlistUI();
}

async function saveAllowlist() {
    const toSave = allowlistData.allow_all ? ['*'] :
        allowlistData.allowlist.filter(e => e && e !== '*').map(e => e.trim()).filter(e => e);

    try {
        const response = await fetch('/api/allowlist', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ allowlist: toSave })
        });
        const result = await response.json();
        if (response.ok) {
            showMessage('settings-message', 'success', 'Allowlist saved');
            loadAllowlist();
        } else {
            showMessage('settings-message', 'error', result.detail || 'Failed to save');
        }
    } catch (error) {
        showMessage('settings-message', 'error', error.message);
    }
}

// =============================================================================
// Speed Dial
// =============================================================================

async function loadSpeedDial() {
    try {
        const response = await fetch('/api/speed-dial');
        const data = await response.json();
        speedDialData = data.speed_dial || {};
        updateSpeedDialUI();
    } catch (error) {
        console.error('Failed to load speed dial:', error);
        showMessage('settings-message', 'error', 'Failed to load speed dial');
    }
}

function updateSpeedDialUI() {
    const container = document.getElementById('speed-dial-entries');
    const entries = Object.entries(speedDialData);

    if (entries.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); font-size: 14px;">No speed dials configured. Click "Add Speed Dial" to create one.</p>';
        return;
    }

    container.innerHTML = '';
    entries.forEach(([code, number]) => {
        const div = document.createElement('div');
        div.className = 'list-item';
        div.innerHTML = `
            <input type="text" style="width: 60px; text-align: center;" value="${escapeHtml(code)}"
                   onchange="updateSpeedDialCode('${escapeHtml(code)}', this.value)" placeholder="1">
            <span style="color: var(--text-muted);">&#8594;</span>
            <input type="tel" class="list-item-input" value="${escapeHtml(number)}"
                   onchange="updateSpeedDialNumber('${escapeHtml(code)}', this.value)" placeholder="+12065551234">
            <button class="btn btn-danger btn-icon" onclick="removeSpeedDial('${escapeHtml(code)}')">&#10005;</button>
        `;
        container.appendChild(div);
    });
}

function addSpeedDialEntry() {
    const code = String(Object.keys(speedDialData).length + 1);
    speedDialData[code] = '';
    updateSpeedDialUI();
}

function updateSpeedDialCode(oldCode, newCode) {
    if (newCode && newCode !== oldCode) {
        speedDialData[newCode] = speedDialData[oldCode];
        delete speedDialData[oldCode];
        updateSpeedDialUI();
    }
}

function updateSpeedDialNumber(code, number) {
    speedDialData[code] = number;
}

function removeSpeedDial(code) {
    delete speedDialData[code];
    updateSpeedDialUI();
}

async function saveSpeedDial() {
    // Filter out empty entries
    const cleaned = {};
    Object.entries(speedDialData).forEach(([k, v]) => {
        if (k && v) cleaned[k] = v;
    });

    try {
        const response = await fetch('/api/speed-dial', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ speed_dial: cleaned })
        });
        const result = await response.json();
        if (response.ok) {
            showMessage('settings-message', 'success', 'Speed dial saved successfully');
            loadSpeedDial();
        } else {
            showMessage('settings-message', 'error', result.detail || 'Failed to save speed dial');
        }
    } catch (error) {
        showMessage('settings-message', 'error', error.message);
    }
}

// =============================================================================
// Ring Settings
// =============================================================================

async function loadRingSettings() {
    try {
        const response = await fetch('/api/ring-settings');
        const data = await response.json();
        ringSettings = data;
        document.getElementById('ring-duration').value = data.ring_duration || 2.0;
        document.getElementById('ring-pause').value = data.ring_pause || 4.0;
    } catch (error) {
        console.error('Failed to load ring settings:', error);
    }
}

async function saveRingSettings() {
    const ringDuration = parseFloat(document.getElementById('ring-duration').value);
    const ringPause = parseFloat(document.getElementById('ring-pause').value);

    if (isNaN(ringDuration) || ringDuration <= 0 || ringDuration > 30) {
        showMessage('settings-message', 'error', 'Ring duration must be between 0.5 and 30 seconds');
        return;
    }
    if (isNaN(ringPause) || ringPause <= 0 || ringPause > 60) {
        showMessage('settings-message', 'error', 'Ring pause must be between 0.5 and 60 seconds');
        return;
    }

    try {
        const response = await fetch('/api/ring-settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ring_duration: ringDuration,
                ring_pause: ringPause
            })
        });
        const result = await response.json();
        if (response.ok) {
            ringSettings = { ring_duration: ringDuration, ring_pause: ringPause };
            showMessage('settings-message', 'success', 'Ring settings saved');
        } else {
            showMessage('settings-message', 'error', result.detail || 'Failed to save ring settings');
        }
    } catch (error) {
        showMessage('settings-message', 'error', error.message);
    }
}

function testRing() {
    const player = document.getElementById('sound-player');
    const ringSound = document.getElementById('assign-ring_sound')?.value;

    if (!ringSound) {
        showMessage('settings-message', 'error', 'No ring sound assigned. Select a ring sound first.');
        return;
    }

    const ringDuration = parseFloat(document.getElementById('ring-duration').value) || 2.0;
    const ringPause = parseFloat(document.getElementById('ring-pause').value) || 4.0;

    // Stop any current playback
    if (ringTestTimeout) {
        clearTimeout(ringTestTimeout);
        ringTestTimeout = null;
    }
    player.pause();
    player.currentTime = 0;

    // Extract filename from path
    const filename = ringSound.split('/').pop();

    // Play the ring sound
    player.src = `/api/sounds/${encodeURIComponent(filename)}`;
    player.play();

    // Stop after ring_duration
    ringTestTimeout = setTimeout(() => {
        player.pause();
        player.currentTime = 0;
        showMessage('settings-message', 'success',
            `Ring test complete (${ringDuration}s on, ${ringPause}s pause)`);
    }, ringDuration * 1000);
}

// =============================================================================
// Audio Gain Settings
// =============================================================================

async function loadAudioGain() {
    try {
        const response = await fetch('/api/audio-gain');
        const data = await response.json();
        audioGainSettings = data;
        document.getElementById('input-gain').value = data.input_gain || 1.0;
        document.getElementById('input-gain-slider').value = data.input_gain || 1.0;
        document.getElementById('output-volume').value = data.output_volume || 1.0;
        document.getElementById('output-volume-slider').value = data.output_volume || 1.0;
    } catch (error) {
        console.error('Failed to load audio gain settings:', error);
    }
}

async function saveAudioGain() {
    const inputGain = parseFloat(document.getElementById('input-gain').value);
    const outputVolume = parseFloat(document.getElementById('output-volume').value);

    if (isNaN(inputGain) || inputGain < 0 || inputGain > 2) {
        showMessage('settings-message', 'error', 'Microphone gain must be between 0.0 and 2.0');
        return;
    }
    if (isNaN(outputVolume) || outputVolume < 0 || outputVolume > 2) {
        showMessage('settings-message', 'error', 'Speaker volume must be between 0.0 and 2.0');
        return;
    }

    try {
        const response = await fetch('/api/audio-gain', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input_gain: inputGain,
                output_volume: outputVolume
            })
        });
        const result = await response.json();
        if (response.ok) {
            audioGainSettings = { input_gain: inputGain, output_volume: outputVolume };
            showMessage('settings-message', 'success', 'Audio levels saved');
        } else {
            showMessage('settings-message', 'error', result.detail || 'Failed to save audio levels');
        }
    } catch (error) {
        showMessage('settings-message', 'error', error.message);
    }
}

// =============================================================================
// Sounds
// =============================================================================

async function loadSoundFiles() {
    await loadRingSettings();
    await loadAudioGain();
    const container = document.getElementById('sound-list');
    try {
        const response = await fetch('/api/sounds');
        const data = await response.json();
        soundFiles = data.files || [];

        if (soundFiles.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); font-size: 14px;">No sound files found.</p>';
        } else {
            container.innerHTML = '';
            soundFiles.forEach(file => {
                const div = document.createElement('div');
                div.className = 'sound-item';
                div.id = `sound-${file.name.replace(/\./g, '-')}`;
                div.innerHTML = `
                    <div class="sound-icon">&#127925;</div>
                    <div class="sound-info">
                        <div class="sound-name">${escapeHtml(file.name)}</div>
                        <div class="sound-size">${formatBytes(file.size)}</div>
                    </div>
                    <div class="sound-actions">
                        <button class="btn-play" onclick="playSound('${escapeHtml(file.name)}')" title="Play">&#9654;</button>
                        <button class="btn-delete" onclick="deleteSound('${escapeHtml(file.name)}')" title="Delete">&#128465;</button>
                    </div>
                `;
                container.appendChild(div);
            });
        }

        // Update dropdowns and load assignments
        updateSoundDropdowns();
        await loadSoundAssignments();
    } catch (error) {
        container.innerHTML = `<p style="color: var(--red);">Error: ${error.message}</p>`;
    }
}

function updateSoundDropdowns() {
    const keys = ['ring_sound', 'dial_tone', 'busy_tone', 'error_tone'];
    keys.forEach(key => {
        const select = document.getElementById(`assign-${key}`);
        if (!select) return;
        const currentValue = select.value;
        select.innerHTML = '<option value="">-- None --</option>';
        soundFiles.forEach(file => {
            const option = document.createElement('option');
            option.value = `sounds/${file.name}`;
            option.textContent = file.name;
            select.appendChild(option);
        });
        select.value = currentValue;
    });
}

async function loadSoundAssignments() {
    try {
        const response = await fetch('/api/sound-assignments');
        const data = await response.json();
        soundAssignments = data.assignments || {};

        // Set dropdown values
        Object.entries(soundAssignments).forEach(([key, value]) => {
            const select = document.getElementById(`assign-${key}`);
            if (select) select.value = value || '';
        });
    } catch (error) {
        console.error('Failed to load sound assignments:', error);
    }
}

async function saveSoundAssignments() {
    const assignments = {
        ring_sound: document.getElementById('assign-ring_sound')?.value || '',
        dial_tone: document.getElementById('assign-dial_tone')?.value || '',
        busy_tone: document.getElementById('assign-busy_tone')?.value || '',
        error_tone: document.getElementById('assign-error_tone')?.value || ''
    };

    try {
        const response = await fetch('/api/sound-assignments', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ assignments })
        });
        const result = await response.json();
        if (response.ok) {
            showMessage('settings-message', 'success', 'Sound assignments saved');
        } else {
            showMessage('settings-message', 'error', result.detail || 'Failed to save assignments');
        }
    } catch (error) {
        showMessage('settings-message', 'error', error.message);
    }
}

function playSound(filename) {
    const player = document.getElementById('sound-player');
    const allPlayBtns = document.querySelectorAll('.btn-play');

    // Stop if same file is playing
    if (currentlyPlaying === filename) {
        player.pause();
        player.currentTime = 0;
        currentlyPlaying = null;
        allPlayBtns.forEach(btn => btn.classList.remove('playing'));
        return;
    }

    // Reset all buttons
    allPlayBtns.forEach(btn => btn.classList.remove('playing'));

    // Play new file
    player.src = `/api/sounds/${encodeURIComponent(filename)}`;
    player.play();
    currentlyPlaying = filename;

    // Find and highlight the play button
    const itemId = `sound-${filename.replace(/\./g, '-')}`;
    const item = document.getElementById(itemId);
    if (item) {
        const btn = item.querySelector('.btn-play');
        if (btn) btn.classList.add('playing');
    }

    player.onended = () => {
        currentlyPlaying = null;
        allPlayBtns.forEach(btn => btn.classList.remove('playing'));
    };
}

async function deleteSound(filename) {
    if (!confirm(`Delete "${filename}"? This cannot be undone.`)) return;

    try {
        const response = await fetch(`/api/sounds/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        const result = await response.json();
        if (response.ok) {
            let message = `Deleted ${filename}`;
            if (result.was_assigned_to && result.was_assigned_to.length > 0) {
                message += ` (was assigned to: ${result.was_assigned_to.join(', ')})`;
            }
            showMessage('settings-message', 'success', message);
            loadSoundFiles();
        } else {
            showMessage('settings-message', 'error', result.detail || 'Failed to delete');
        }
    } catch (error) {
        showMessage('settings-message', 'error', error.message);
    }
}

async function uploadSound() {
    const fileInput = document.getElementById('sound-file');
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/sounds/upload', { method: 'POST', body: formData });
        const result = await response.json();
        if (response.ok) {
            showMessage('settings-message', 'success', `Uploaded ${file.name}`);
            fileInput.value = '';
            loadSoundFiles();
        } else {
            showMessage('settings-message', 'error', result.detail || 'Upload failed');
        }
    } catch (error) {
        showMessage('settings-message', 'error', error.message);
    }
}

// =============================================================================
// System Config
// =============================================================================

async function loadSystemConfig() {
    const container = document.getElementById('system-config');
    try {
        const response = await fetch('/api/config');
        const config = await response.json();

        // Render the full config as a formatted YAML-like display
        container.innerHTML = renderConfigSection(config, '');
    } catch (error) {
        container.innerHTML = `<p style="color: var(--red);">Failed to load configuration</p>`;
    }
}

function renderConfigSection(obj, prefix) {
    let html = '';
    for (const [key, value] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;
        if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
            // Nested object - render section header
            html += `<div class="config-section-header">${escapeHtml(key)}</div>`;
            html += renderConfigSection(value, fullKey);
        } else {
            // Leaf value
            let displayValue;
            if (Array.isArray(value)) {
                displayValue = value.length === 0 ? '(empty)' : value.join(', ');
            } else if (value === null || value === undefined || value === '') {
                displayValue = '(not set)';
            } else {
                displayValue = String(value);
            }
            html += `
                <div class="config-item">
                    <span class="config-key">${escapeHtml(key)}</span>
                    <span class="config-value">${escapeHtml(displayValue)}</span>
                </div>
            `;
        }
    }
    return html;
}

// =============================================================================
// Utilities
// =============================================================================

function showMessage(elementId, type, message) {
    const el = document.getElementById(elementId);
    el.innerHTML = `<div class="message message-${type}">${message}</div>`;
    setTimeout(() => el.innerHTML = '', 5000);
}

function formatDateTime(iso) {
    if (!iso) return '-';
    return new Date(iso).toLocaleString();
}

function formatTimeAgo(iso) {
    if (!iso) return '-';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return new Date(iso).toLocaleDateString();
}

function formatDuration(seconds) {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 10) / 10 + ' ' + sizes[i];
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =============================================================================
// Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    loadStatus();
    loadDashboardStats();
    loadRecentCalls();

    // Auto-refresh status when on dashboard
    setInterval(() => {
        if (currentPage === 'dashboard') {
            loadStatus();
        }
    }, 2000);
});
