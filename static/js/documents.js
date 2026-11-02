/**
 * Legal Document Analyzer — Documents Module
 * Handles file upload, document listing, deletion, and preview.
 */

// ── Load Documents ────────────────────────────────────────────────────
async function loadDocuments() {
    try {
        const data = await apiRequest('/api/documents');
        renderDocumentsList(data.documents || []);
        renderDocumentsSidebar(data.documents || []);
        renderDocFilterChips(data.documents || []);
        updateDocCountBadge(data.documents || []);
    } catch (e) {
        console.error('Failed to load documents:', e);
    }
}

// ── Render Documents in Sidebar (Left) ────────────────────────────────
function renderDocumentsSidebar(docs) {
    const container = document.getElementById('documents-sidebar-list');

    if (!docs.length) {
        container.innerHTML = '<div class="empty-state-small"><p>No documents uploaded</p></div>';
        return;
    }

    container.innerHTML = docs.map(doc => {
        const ext = getFileExtension(doc.name);
        return `
            <div class="doc-item" title="${escapeHtml(doc.name)}">
                <div class="doc-icon ${ext}">${ext}</div>
                <div class="doc-info">
                    <div class="doc-name">${escapeHtml(doc.name)}</div>
                    <div class="doc-meta">${doc.chunk_count} chunks · ${doc.page_count} pages</div>
                </div>
                <div class="doc-status ${doc.status}"></div>
            </div>
        `;
    }).join('');
}

// ── Render Documents in Right Panel ───────────────────────────────────
function renderDocumentsList(docs) {
    const container = document.getElementById('documents-panel-list');

    if (!docs.length) {
        container.innerHTML = '<div class="empty-state-small"><p>No documents uploaded yet</p></div>';
        return;
    }

    container.innerHTML = docs.map(doc => {
        const ext = getFileExtension(doc.name);
        const size = formatFileSize(doc.file_size || 0);
        const parsedDate = parseUtcTimestamp(doc.upload_date);
        const date = parsedDate ? parsedDate.toLocaleDateString() : '';
        const isReady = doc.status === 'ready';

        return `
            <div class="doc-item" data-doc-id="${escapeAttr(doc.id)}">
                <div class="doc-item-header">
                    <div class="doc-icon ${ext}">${ext}</div>
                    <div class="doc-info">
                        <div class="doc-name">${escapeHtml(doc.name)}</div>
                        <div class="doc-meta">${date}</div>
                    </div>
                    <div class="doc-status ${doc.status}" title="${escapeAttr(doc.status)}"></div>
                    ${isReady ? `
                    <button class="btn-icon btn-preview-doc"
                            data-action="preview"
                            data-doc-id="${escapeAttr(doc.id)}"
                            title="Preview document text">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="14" height="14">
                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                        </svg>
                    </button>
                    ` : ''}
                    <button class="btn-icon btn-delete-doc"
                            data-action="delete"
                            data-doc-id="${escapeAttr(doc.id)}"
                            data-doc-name="${escapeAttr(doc.name)}"
                            title="Delete document">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="14" height="14">
                            <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                </div>
                <div class="doc-item-details">
                    <span>📄 ${doc.page_count} pages</span>
                    <span>🧩 ${doc.chunk_count} chunks</span>
                    <span>💾 ${size}</span>
                </div>
            </div>
        `;
    }).join('');
}

// ── Render Document Filter Chips ──────────────────────────────────────
function renderDocFilterChips(docs) {
    const container = document.getElementById('doc-filter-chips');

    let chips = '<span class="filter-chip active" data-doc-id="all">All Documents</span>';

    docs.forEach(doc => {
        if (doc.status === 'ready') {
            const shortName = doc.name.length > 20 ? doc.name.substring(0, 18) + '…' : doc.name;
            chips += `<span class="filter-chip" data-doc-id="${escapeAttr(doc.id)}">${escapeHtml(shortName)}</span>`;
        }
    });

    container.innerHTML = chips;
}

// ── Toggle Document Filter ────────────────────────────────────────────
function toggleDocFilter(chip) {
    const docId = chip.dataset.docId;

    if (docId === 'all') {
        // Select "All Documents", deselect others
        document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        AppState.selectedDocIds = [];
    } else {
        // Deselect "All", toggle this chip
        document.querySelector('.filter-chip[data-doc-id="all"]').classList.remove('active');
        chip.classList.toggle('active');

        // Build selected list
        AppState.selectedDocIds = [];
        document.querySelectorAll('.filter-chip.active').forEach(c => {
            if (c.dataset.docId !== 'all') {
                AppState.selectedDocIds.push(c.dataset.docId);
            }
        });

        // If none selected, go back to all
        if (AppState.selectedDocIds.length === 0) {
            document.querySelector('.filter-chip[data-doc-id="all"]').classList.add('active');
        }
    }
}

// ── Upload Documents ──────────────────────────────────────────────────
async function uploadFiles(files) {
    if (!files || files.length === 0) return;

    const uploadProgress = document.getElementById('upload-progress');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    const uploadContent = document.querySelector('.upload-content');

    uploadProgress.classList.remove('hidden');
    uploadContent.style.display = 'none';
    progressFill.style.width = '30%';
    progressText.textContent = `Processing ${files.length} file(s)...`;

    const formData = new FormData();
    for (const file of files) {
        formData.append('files', file);
    }

    try {
        progressFill.style.width = '60%';
        progressText.textContent = 'Extracting & embedding...';

        const result = await apiRequest('/api/documents/upload', {
            method: 'POST',
            body: formData,
        });

        progressFill.style.width = '100%';

        // Show results
        let successCount = 0;
        let errorCount = 0;

        result.results.forEach(r => {
            if (r.status === 'ready') {
                successCount++;
            } else {
                errorCount++;
                showToast(`Error: ${r.filename} — ${r.message}`, 'error', 6000);
            }
        });

        if (successCount > 0) {
            showToast(`${successCount} document(s) processed successfully`, 'success');
        }

        // Reload documents
        await loadDocuments();
        await updateStats();

    } catch (e) {
        showToast('Upload failed: ' + e.message, 'error');
    } finally {
        setTimeout(() => {
            uploadProgress.classList.add('hidden');
            uploadContent.style.display = '';
            progressFill.style.width = '0%';
        }, 1000);
    }
}

// ── Delete Document ───────────────────────────────────────────────────
async function deleteDocument(docId, docName) {
    const confirmed = await showConfirmModal(
        'Delete Document',
        `Delete "${docName}"? This will remove the document and all its indexed data. This cannot be undone.`
    );

    if (!confirmed) return;

    try {
        await apiRequest(`/api/documents/${docId}`, { method: 'DELETE' });
        await loadDocuments();
        await updateStats();
        showToast(`"${docName}" deleted`, 'success');
    } catch (e) {
        showToast('Failed to delete: ' + e.message, 'error');
    }
}

// ── Preview Document ──────────────────────────────────────────────────
async function previewDocument(docId) {
    const modal = document.getElementById('preview-modal');
    const title = document.getElementById('preview-title');
    const body = document.getElementById('preview-body');

    title.textContent = 'Loading...';
    body.innerHTML = '<p class="loading-text">Extracting document text...</p>';
    modal.classList.remove('hidden');

    try {
        const data = await apiRequest(`/api/documents/${docId}/preview`);
        title.textContent = data.name;
        body.innerHTML = `
            <div class="preview-meta">
                <span>📄 ${data.page_count} pages</span>
                <span>📝 ${formatFileSize(data.total_length)} text</span>
                ${data.truncated ? '<span class="preview-truncated">⚠ Showing first 3,000 characters</span>' : ''}
            </div>
            <pre class="preview-text">${escapeHtml(data.preview)}</pre>
        `;
    } catch (e) {
        body.innerHTML = `<p class="error-text">Failed to load preview: ${e.message}</p>`;
    }
}

function closePreviewModal() {
    document.getElementById('preview-modal').classList.add('hidden');
}

// ── Update Doc Count Badge ────────────────────────────────────────────
function updateDocCountBadge(docs) {
    const badge = document.getElementById('doc-count-badge');
    const readyDocs = docs.filter(d => d.status === 'ready');
    badge.textContent = readyDocs.length;
}

// ── File Helpers ──────────────────────────────────────────────────────
function getFileExtension(filename) {
    return (filename || '').split('.').pop().toLowerCase();
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
}

// ── Document Actions — Event Delegation ───────────────────────────────
function initDocumentActions() {
    const panelList = document.getElementById('documents-panel-list');
    if (panelList) {
        panelList.addEventListener('click', (e) => {
            const button = e.target.closest('[data-action]');
            if (!button) return;

            const docId = button.dataset.docId;
            if (button.dataset.action === 'preview') {
                previewDocument(docId);
            } else if (button.dataset.action === 'delete') {
                deleteDocument(docId, button.dataset.docName || '');
            }
        });
    }

    const filterChips = document.getElementById('doc-filter-chips');
    if (filterChips) {
        filterChips.addEventListener('click', (e) => {
            const chip = e.target.closest('.filter-chip');
            if (chip) toggleDocFilter(chip);
        });
    }
}

// ── Upload Zone — Drag & Drop + Click ─────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initDocumentActions();

    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');

    // Click to browse
    uploadZone.addEventListener('click', (e) => {
        if (e.target.closest('.upload-progress')) return;
        fileInput.click();
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            uploadFiles(fileInput.files);
            fileInput.value = '';
        }
    });

    // Drag & drop
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('drag-over');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('drag-over');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) {
            uploadFiles(e.dataTransfer.files);
        }
    });
});
