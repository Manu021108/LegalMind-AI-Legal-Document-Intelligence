/**
 * Legal Document Analyzer — Sessions Module
 * Handles session CRUD, sidebar rendering, and chat export.
 */

// ── Load Sessions ─────────────────────────────────────────────────────
async function loadSessions() {
    try {
        const data = await apiRequest('/api/sessions');
        renderSessions(data.sessions || []);
        updateStats();
    } catch (e) {
        console.error('Failed to load sessions:', e);
    }
}

// ── Render Sessions List ──────────────────────────────────────────────
function renderSessions(sessions) {
    const container = document.getElementById('sessions-list');

    if (!sessions.length) {
        container.innerHTML = '<div class="empty-state-small"><p>No conversations yet</p></div>';
        return;
    }

    container.innerHTML = sessions.map(session => {
        const isActive = session.id === AppState.currentSessionId;
        const preview = session.last_message
            ? truncate(session.last_message, 45)
            : 'No messages yet';
        const timeAgo = formatTimeAgo(session.updated_at);

        return `
            <div class="session-item ${isActive ? 'active' : ''}"
                 data-session-id="${escapeAttr(session.id)}">
                <div class="session-icon">💬</div>
                <div class="session-info">
                    <div class="session-title">${escapeHtml(session.title)}</div>
                    <div class="session-preview">${escapeHtml(preview)}</div>
                </div>
                <button class="btn-icon btn-delete-session"
                        data-action="delete"
                        data-session-id="${escapeAttr(session.id)}"
                        title="Delete session">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="14" height="14">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                </button>
            </div>
        `;
    }).join('');
}

// ── Create New Session ────────────────────────────────────────────────
async function createNewSession(title = 'New Chat') {
    try {
        const session = await apiRequest('/api/sessions', {
            method: 'POST',
            body: JSON.stringify({ title }),
        });

        AppState.currentSessionId = session.id;
        await loadSessions();
        clearChatMessages();
        updateChatHeader(session.title);
        updateExportButton();
        showToast('New conversation started', 'success');
        return session;
    } catch (e) {
        showToast('Failed to create session: ' + e.message, 'error');
    }
}

// ── Switch Session ────────────────────────────────────────────────────
async function switchSession(sessionId) {
    try {
        AppState.currentSessionId = sessionId;

        // Load session messages
        const data = await apiRequest(`/api/sessions/${sessionId}`);

        clearChatMessages();
        updateChatHeader(data.title);
        updateExportButton();

        // Render existing messages
        if (data.messages && data.messages.length > 0) {
            data.messages.forEach(msg => {
                appendMessage(msg.role, msg.content, msg.sources || []);
            });
        }

        // Update sidebar active state
        document.querySelectorAll('.session-item').forEach(item => {
            item.classList.toggle('active', item.dataset.sessionId === sessionId);
        });

    } catch (e) {
        showToast('Failed to load session: ' + e.message, 'error');
    }
}

// ── Delete Session ────────────────────────────────────────────────────
async function deleteSession(sessionId) {
    const confirmed = await showConfirmModal(
        'Delete Conversation',
        'This will permanently delete this conversation and all its messages. This cannot be undone.'
    );

    if (!confirmed) return;

    try {
        await apiRequest(`/api/sessions/${sessionId}`, { method: 'DELETE' });

        if (AppState.currentSessionId === sessionId) {
            AppState.currentSessionId = null;
            clearChatMessages();
            showWelcomeScreen();
            updateExportButton();
        }

        await loadSessions();
        showToast('Conversation deleted', 'success');
    } catch (e) {
        showToast('Failed to delete session: ' + e.message, 'error');
    }
}

// ── Export Chat as Markdown ───────────────────────────────────────────
async function exportChat() {
    if (!AppState.currentSessionId) return;

    try {
        const headers = {};
        const apiKey = getApiAuthKey();
        if (apiKey) headers['X-API-Key'] = apiKey;

        const response = await fetch(`/api/sessions/${AppState.currentSessionId}/export`, { headers });
        if (response.status === 401) throw new Error('Unauthorized — a valid API key is required');
        if (!response.ok) throw new Error('Export failed');

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);

        // Extract filename from Content-Disposition header
        const disposition = response.headers.get('Content-Disposition');
        let filename = 'chat_export.md';
        if (disposition && disposition.includes('filename=')) {
            filename = disposition.split('filename="')[1]?.replace('"', '') || filename;
        }

        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);

        showToast('Chat exported successfully', 'success');
    } catch (e) {
        showToast('Failed to export chat: ' + e.message, 'error');
    }
}

// ── Update Export Button Visibility ───────────────────────────────────
function updateExportButton() {
    const btn = document.getElementById('btn-export-chat');
    if (btn) {
        btn.style.display = AppState.currentSessionId ? '' : 'none';
    }
}

// ── Update Chat Header ───────────────────────────────────────────────
function updateChatHeader(title) {
    document.getElementById('chat-title').textContent = title || 'LegalMind';
    document.getElementById('chat-subtitle').textContent = 'Ask questions about your documents';
}

// ── Helper: Truncate Text ─────────────────────────────────────────────
function truncate(text, maxLen) {
    if (!text) return '';
    return text.length > maxLen ? text.substring(0, maxLen) + '...' : text;
}

// ── Helper: Escape HTML ───────────────────────────────────────────────
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

// ── Helper: Format Time Ago ───────────────────────────────────────────
function formatTimeAgo(isoString) {
    if (!isoString) return '';
    const now = new Date();
    const date = parseUtcTimestamp(isoString);
    if (!date || Number.isNaN(date.getTime())) return '';
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

// ── Update Stats ──────────────────────────────────────────────────────
async function updateStats() {
    try {
        const [sessionsData, statsData] = await Promise.all([
            apiRequest('/api/sessions'),
            apiRequest('/api/documents/stats').catch(() => ({})),
        ]);
        document.getElementById('stat-sessions').textContent = sessionsData.sessions?.length || 0;
        document.getElementById('stat-docs').textContent = statsData.total_files || 0;
        document.getElementById('stat-chunks').textContent = statsData.total_chunks || 0;
    } catch (e) {
        // Silently fail
    }
}

// ── Init: New Session + Export Buttons ─────────────────────────────────
function initSessionActions() {
    const sessionsList = document.getElementById('sessions-list');
    if (sessionsList) {
        sessionsList.addEventListener('click', (e) => {
            const deleteBtn = e.target.closest('[data-action="delete"]');
            if (deleteBtn) {
                e.stopPropagation();
                deleteSession(deleteBtn.dataset.sessionId);
                return;
            }

            const sessionItem = e.target.closest('.session-item');
            if (sessionItem) {
                switchSession(sessionItem.dataset.sessionId);
            }
        });
    }

    const newBtn = document.getElementById('btn-new-session');
    if (newBtn) newBtn.addEventListener('click', () => createNewSession());

    const exportBtn = document.getElementById('btn-export-chat');
    if (exportBtn) exportBtn.addEventListener('click', () => exportChat());
}

document.addEventListener('DOMContentLoaded', initSessionActions);
