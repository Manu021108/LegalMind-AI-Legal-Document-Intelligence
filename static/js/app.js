/**
 * Legal Document Analyzer — Main Application Module
 * Handles initialization, global state, health checks, notifications, and modals.
 */

const API_BASE = '';

// ── Global Application State ─────────────────────────────────────────
const AppState = {
    currentSessionId: null,
    currentMode: 'strict',
    selectedDocIds: [],          // empty = all documents
    systemHealth: null,
    llmProvider: 'checking...',
    embeddingProvider: 'checking...',
};

// ── API Helper ────────────────────────────────────────────────────────
function getApiAuthKey() {
    try {
        if (typeof localStorage !== "undefined") {
            return localStorage.getItem("apiAuthKey") || "";
        }
    } catch (e) {
        // Ignore localStorage access errors
    }
    return "";
}

function setApiAuthKey(key) {
    try {
        if (typeof localStorage !== "undefined") {
            if (key && key.trim()) {
                localStorage.setItem("apiAuthKey", key.trim());
            } else {
                localStorage.removeItem("apiAuthKey");
            }
        }
    } catch (e) {
        // Ignore localStorage access errors
    }
}

async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
    };

    // Don't set Content-Type for FormData
    if (options.body instanceof FormData) {
        delete config.headers["Content-Type"];
    }

    const apiKey = getApiAuthKey();
    if (apiKey) {
        config.headers["X-API-Key"] = apiKey;
    }

    const response = await fetch(url, config);

    if (response.status === 401) {
        throw new Error("Unauthorized. Please provide a valid API key (X-API-Key).");
    }

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

// ── HTML / Timestamp Helpers ──────────────────────────────────────────
function escapeAttr(text) {
    return String(text == null ? '' : text)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function parseUtcTimestamp(isoString) {
    if (!isoString) return null;
    // Accept both timezone-aware values and legacy naive UTC strings
    const hasTimezone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(isoString);
    return new Date(hasTimezone ? isoString : isoString + 'Z');
}

// ── Toast Notifications ───────────────────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ',
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-message">${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ── Confirm Modal ─────────────────────────────────────────────────────
function showConfirmModal(title, message) {
    return new Promise((resolve) => {
        const modal = document.getElementById('confirm-modal');
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-message').textContent = message;
        modal.classList.remove('hidden');

        const cleanup = () => {
            modal.classList.add('hidden');
            confirmBtn.removeEventListener('click', onConfirm);
            cancelBtn.removeEventListener('click', onCancel);
            backdrop.removeEventListener('click', onCancel);
        };

        const confirmBtn = document.getElementById('modal-confirm');
        const cancelBtn = document.getElementById('modal-cancel');
        const backdrop = modal.querySelector('.modal-backdrop');

        const onConfirm = () => { cleanup(); resolve(true); };
        const onCancel = () => { cleanup(); resolve(false); };

        confirmBtn.addEventListener('click', onConfirm);
        cancelBtn.addEventListener('click', onCancel);
        backdrop.addEventListener('click', onCancel);
    });
}

// ── Setup Alert Banner ────────────────────────────────────────────────
function showSetupBanner(issues) {
    const banner = document.getElementById('setup-banner');
    const list = document.getElementById('setup-issues');
    if (!banner || !list || issues.length === 0) {
        if (banner) banner.classList.add('hidden');
        return;
    }

    list.innerHTML = issues.map(issue => `<li>${issue}</li>`).join('');
    banner.classList.remove('hidden');
}

function dismissSetupBanner() {
    const banner = document.getElementById('setup-banner');
    if (banner) banner.classList.add('hidden');
}

// ── Health Check ──────────────────────────────────────────────────────
async function checkSystemHealth() {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const providerBadge = document.getElementById('provider-badge');

    try {
        const health = await apiRequest('/api/health');
        AppState.systemHealth = health;
        AppState.llmProvider = health.llm_provider || 'none';
        AppState.embeddingProvider = health.embedding_provider || 'none';

        statusDot.className = 'status-dot ' + health.status;
        statusText.textContent = health.status === 'healthy'
            ? 'All systems operational'
            : 'Some services need attention';

        const providerLabel = {
            groq: '⚡ Groq API',
            ollama: '🏠 Ollama Local',
            none: '❌ No LLM',
        };
        providerBadge.textContent = `LLM: ${providerLabel[health.llm_provider] || health.llm_provider}`;

        // Build setup issues for the banner
        const issues = [];
        const services = health.services;

        if (services.ollama_server.status !== 'up') {
            issues.push('🖥️ <strong>Ollama is not running.</strong> Embeddings require Ollama. Start it with: <code>ollama serve</code>');
        } else if (services.ollama_embedding.status !== 'ready') {
            issues.push('🔢 <strong>Embedding model not found.</strong> Pull the embedding model: <code>ollama pull nomic-embed-text</code>');
        }

        if (health.llm_provider === 'none') {
            issues.push('🤖 <strong>No LLM available.</strong> Add your Groq API key to <code>.env</code>, or pull an Ollama model: <code>ollama pull llama3.2</code>');
        }

        showSetupBanner(issues);

    } catch (e) {
        statusDot.className = 'status-dot down';
        statusText.textContent = 'Cannot reach server';
        providerBadge.textContent = 'LLM: Offline';
        showSetupBanner(['🔌 <strong>Cannot connect to the backend server.</strong> Make sure it is running: <code>python app.py</code>']);
    }
}

// ── UI Panel Toggles ──────────────────────────────────────────────────
function initPanelToggles() {
    // Right panel toggle
    const rightPanel = document.getElementById('sidebar-right');
    const toggleBtn = document.getElementById('btn-toggle-panel');
    const closeBtn = document.getElementById('btn-close-panel');

    toggleBtn.addEventListener('click', () => {
        rightPanel.classList.toggle('collapsed');
        rightPanel.classList.toggle('expanded');
    });

    closeBtn.addEventListener('click', () => {
        rightPanel.classList.add('collapsed');
        rightPanel.classList.remove('expanded');
    });

    // Left sidebar toggle (mobile)
    const leftSidebar = document.getElementById('sidebar-left');
    const sidebarToggle = document.getElementById('btn-toggle-sidebar');

    sidebarToggle.addEventListener('click', () => {
        leftSidebar.classList.toggle('open');
    });

    // Mode toggle
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            AppState.currentMode = btn.dataset.mode;
        });
    });

    // Setup banner dismiss
    const dismissBtn = document.getElementById('btn-dismiss-banner');
    if (dismissBtn) {
        dismissBtn.addEventListener('click', dismissSetupBanner);
    }
}

// ── Application Initialization ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Legal Document Analyzer — Initializing...');

    initPanelToggles();

    // Load initial data in parallel
    await Promise.all([
        checkSystemHealth(),
        loadSessions(),
        loadDocuments(),
    ]);

    // Periodic health check (reduced frequency to limit provider calls)
    setInterval(checkSystemHealth, 120000);

    console.log('Legal Document Analyzer — Ready');
});
