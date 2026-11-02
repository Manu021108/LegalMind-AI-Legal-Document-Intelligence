/**
 * Legal Document Analyzer — Chat Module
 * Handles message sending, rendering, typing indicators, and auto-scroll.
 */

// ── DOM References ────────────────────────────────────────────────────
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('btn-send');
const typingIndicator = document.getElementById('typing-indicator');
const welcomeScreen = document.getElementById('welcome-screen');

// ── Input Auto-Resize ─────────────────────────────────────────────────
chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + 'px';
    sendBtn.disabled = !chatInput.value.trim();
});

// ── Keyboard: Enter to send, Shift+Enter for newline ──────────────────
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (chatInput.value.trim()) {
            sendMessage();
        }
    }
});

// ── Send Button Click ─────────────────────────────────────────────────
sendBtn.addEventListener('click', () => {
    if (chatInput.value.trim()) {
        sendMessage();
    }
});

// ── Send Message ──────────────────────────────────────────────────────
async function sendMessage() {
    const question = chatInput.value.trim();
    if (!question) return;

    // Ensure we have a session
    if (!AppState.currentSessionId) {
        const session = await createNewSession('New Chat');
        if (!session) return;
    }

    // Hide welcome screen
    hideWelcomeScreen();

    // Display user message
    appendMessage('user', question);

    // Clear input
    chatInput.value = '';
    chatInput.style.height = 'auto';
    sendBtn.disabled = true;

    // Show typing indicator
    showTyping();

    try {
        const result = await apiRequest('/api/query', {
            method: 'POST',
            body: JSON.stringify({
                question: question,
                session_id: AppState.currentSessionId,
                doc_ids: AppState.selectedDocIds.length > 0 ? AppState.selectedDocIds : null,
                mode: AppState.currentMode,
            }),
        });

        hideTyping();

        // Display assistant response
        appendMessage('assistant', result.answer, result.sources || [], result.provider, result.model);

        // Update session title if it's the first message
        await loadSessions();

    } catch (e) {
        hideTyping();
        appendMessage('assistant', `⚠️ Error: ${e.message}. Please check your API configuration and try again.`);
        showToast('Query failed: ' + e.message, 'error');
    }
}

// ── Append Message to Chat ────────────────────────────────────────────
function appendMessage(role, content, sources = [], provider = '', model = '') {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const avatarLabel = role === 'user' ? 'You' : 'AI';

    let sourcesHtml = '';
    if (sources && sources.length > 0) {
        const sourceChips = sources.map(s => {
            const relevance = Math.round((s.relevance || 0) * 100);
            return `<span class="source-tag" title="Relevance: ${relevance}%">
                <span class="source-icon">📄</span>
                ${escapeHtml(s.doc_name)} · P${s.page_number}
            </span>`;
        }).join('');

        sourcesHtml = `<div class="message-sources">${sourceChips}</div>`;
    }

    let metaHtml = '';
    if (role === 'assistant' && provider && provider !== 'system') {
        const providerEmoji = provider === 'groq' ? '⚡' : '🏠';
        metaHtml = `<div class="message-meta">
            <span>${providerEmoji} ${provider} · ${model}</span>
        </div>`;
    }

    // Enhanced markdown rendering
    const renderedContent = renderMarkdown(content);

    messageDiv.innerHTML = `
        <div class="message-avatar">${avatarLabel}</div>
        <div class="message-body">
            <div class="message-content">${renderedContent}</div>
            ${sourcesHtml}
            ${metaHtml}
        </div>
    `;

    chatMessages.appendChild(messageDiv);
    scrollToBottom();
}

// ── Enhanced Markdown Renderer ────────────────────────────────────────
function renderMarkdown(text) {
    if (!text) return '';

    let html = escapeHtml(text);

    // Code blocks: ```language\ncode\n```
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
        const langLabel = lang ? `<span class="code-lang">${lang}</span>` : '';
        return `<div class="code-block">${langLabel}<pre><code>${code.trim()}</code></pre></div>`;
    });

    // Inline code: `code`
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold: **text**
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Italic: *text*
    html = html.replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');

    // Headings: ### text
    html = html.replace(/^### (.+)$/gm, '<h4 class="md-heading">$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3 class="md-heading">$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2 class="md-heading">$1</h2>');

    // Blockquotes: > text (used for legal citations)
    html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
    // Merge consecutive blockquotes
    html = html.replace(/<\/blockquote>\n<blockquote>/g, '\n');

    // Horizontal rule
    html = html.replace(/^---$/gm, '<hr class="md-hr">');

    // Bullet lists
    html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`);

    // Numbered lists
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

    // Tables: detect | header | header | pattern
    html = html.replace(/^(\|.+\|)\n(\|[\-\s|:]+\|)\n((?:\|.+\|\n?)+)/gm, (match, header, sep, body) => {
        const headers = header.split('|').filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`).join('');
        const rows = body.trim().split('\n').map(row => {
            const cells = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
            return `<tr>${cells}</tr>`;
        }).join('');
        return `<table class="md-table"><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table>`;
    });

    // Line breaks: double newline = paragraph, single = <br>
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');

    // Wrap in paragraph
    html = '<p>' + html + '</p>';

    // Clean empty paragraphs
    html = html.replace(/<p>\s*<\/p>/g, '');

    // Clean up paragraph wrapping around block elements
    html = html.replace(/<p>(<(?:div|ul|ol|h[1-6]|blockquote|hr|table|pre))/g, '$1');
    html = html.replace(/(<\/(?:div|ul|ol|h[1-6]|blockquote|hr|table|pre)>)<\/p>/g, '$1');

    return html;
}

// ── Typing Indicator ──────────────────────────────────────────────────
function showTyping() {
    typingIndicator.classList.remove('hidden');
    scrollToBottom();
}

function hideTyping() {
    typingIndicator.classList.add('hidden');
}

// ── Welcome Screen ────────────────────────────────────────────────────
function hideWelcomeScreen() {
    if (welcomeScreen) {
        welcomeScreen.style.display = 'none';
    }
}

function showWelcomeScreen() {
    if (welcomeScreen) {
        welcomeScreen.style.display = '';
    }
    document.getElementById('chat-title').textContent = 'Legal Document Analyzer';
    document.getElementById('chat-subtitle').textContent = 'Upload documents and start asking questions';
}

// ── Clear Chat ────────────────────────────────────────────────────────
function clearChatMessages() {
    // Remove all messages but keep welcome screen
    const messages = chatMessages.querySelectorAll('.message');
    messages.forEach(m => m.remove());
    hideWelcomeScreen();
}

// ── Auto-Scroll ───────────────────────────────────────────────────────
function scrollToBottom() {
    requestAnimationFrame(() => {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    });
}
