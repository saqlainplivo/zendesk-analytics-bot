// API Configuration
const API_URL = 'http://localhost:8000';

// DOM Elements
let queryInput, sendButton, messagesContainer, welcomeScreen, statusText;

// State
let isProcessing = false;
let ticketDetailsCache = {};

// Initialize
function init() {
    queryInput = document.getElementById('queryInput');
    sendButton = document.getElementById('sendButton');
    messagesContainer = document.getElementById('messagesContainer');
    welcomeScreen = document.getElementById('welcomeScreen');
    statusText = document.getElementById('statusText');

    if (!queryInput || !sendButton || !messagesContainer) {
        console.error('Required DOM elements not found');
        return;
    }

    // Event listeners
    sendButton.addEventListener('click', handleSend);
    queryInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleSend();
        }
    });

    // Example buttons
    document.querySelectorAll('.example-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            queryInput.value = btn.getAttribute('data-query');
            handleSend();
        });
    });

    // Check API status
    checkApiStatus();
    console.log('✓ App initialized');
}

// Check API status
async function checkApiStatus() {
    try {
        const response = await fetch(`${API_URL}/health`);
        statusText.textContent = response.ok ? 'Ready' : 'Offline';
    } catch (error) {
        statusText.textContent = 'Offline';
    }
}

// Handle send
async function handleSend() {
    const query = queryInput.value.trim();
    if (!query || isProcessing) return;

    // Hide welcome
    if (welcomeScreen) {
        welcomeScreen.classList.add('hidden');
    }

    // Clear input
    queryInput.value = '';
    queryInput.focus();

    // Add user message
    addUserMessage(query);

    // Show loading
    const loadingId = showLoading();

    // Disable input
    isProcessing = true;
    sendButton.disabled = true;

    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: query }),
        });

        if (!response.ok) throw new Error(`API error: ${response.status}`);

        const data = await response.json();
        removeLoading(loadingId);

        // Cache ticket details
        if (data.evidence_details) {
            data.evidence_details.forEach(ticket => {
                ticketDetailsCache[ticket.ticket_id] = ticket;
            });
        }

        addBotMessage(
            data.answer,
            data.query_type,
            data.evidence || [],
            data.reasoning || null
        );

    } catch (error) {
        console.error('Error:', error);
        removeLoading(loadingId);
        addErrorMessage('Sorry, something went wrong. Please try again.');
    } finally {
        isProcessing = false;
        sendButton.disabled = false;
        queryInput.focus();
    }
}

// Add user message
function addUserMessage(text) {
    const div = document.createElement('div');
    div.className = 'message user';
    div.innerHTML = `
        <div class="message-label">You</div>
        <div class="message-content">${escapeHtml(text)}</div>
    `;
    messagesContainer.appendChild(div);
    scrollToBottom();
}

// Add bot message
function addBotMessage(answer, queryType, evidence = [], reasoning = null) {
    const div = document.createElement('div');
    div.className = 'message bot';

    // Badge
    const icon = queryType === 'analytics' ? '📊' : '🔍';
    const label = queryType === 'analytics' ? 'SQL Analytics' : 'Semantic Search';

    // Reasoning section
    let reasoningHtml = '';
    if (reasoning) {
        reasoningHtml = `
            <div class="reasoning-section">
                <div class="reasoning-label">Reasoning</div>
                <div class="reasoning-text">${escapeHtml(reasoning)}</div>
            </div>
        `;
    }

    // Evidence with clickable refs
    let evidenceHtml = '';
    if (evidence && evidence.length > 0) {
        const refs = evidence.map((id, idx) =>
            `<span class="ticket-ref" onclick="showTicketPreview('${id}')" title="Click to preview">
                #${escapeHtml(id)}<sup>[${idx + 1}]</sup>
            </span>`
        ).join('');

        evidenceHtml = `
            <div class="evidence">
                <div class="evidence-label">Sources</div>
                <div class="evidence-items">${refs}</div>
            </div>
        `;
    }

    div.innerHTML = `
        <div class="message-label">
            <span class="agent-badge">
                <span>${icon}</span>
                <span>${label}</span>
            </span>
        </div>
        ${reasoningHtml}
        <div class="message-content">${renderMarkdown(answer)}</div>
        ${evidenceHtml}
    `;

    messagesContainer.appendChild(div);
    scrollToBottom();
}

// Show loading
function showLoading() {
    const id = 'loading-' + Date.now();
    const div = document.createElement('div');
    div.id = id;
    div.className = 'message bot';
    div.innerHTML = `
        <div class="message-label">Assistant</div>
        <div class="loading">
            <span>Analyzing</span>
            <div class="loading-dots">
                <div class="loading-dot"></div>
                <div class="loading-dot"></div>
                <div class="loading-dot"></div>
            </div>
        </div>
    `;
    messagesContainer.appendChild(div);
    scrollToBottom();
    return id;
}

// Remove loading
function removeLoading(id) {
    document.getElementById(id)?.remove();
}

// Add error message
function addErrorMessage(text) {
    const div = document.createElement('div');
    div.className = 'message bot';
    div.innerHTML = `
        <div class="message-label">System</div>
        <div class="error-message">${escapeHtml(text)}</div>
    `;
    messagesContainer.appendChild(div);
    scrollToBottom();
}

// Show ticket preview
window.showTicketPreview = async function(ticketId) {
    let ticket = ticketDetailsCache[ticketId];

    // If not in cache, fetch it
    if (!ticket) {
        try {
            const response = await fetch(`${API_URL}/tickets/${ticketId}`);
            if (response.ok) {
                ticket = await response.json();
                ticketDetailsCache[ticketId] = ticket;
            }
        } catch (error) {
            console.error('Failed to fetch ticket:', error);
            return;
        }
    }

    if (!ticket) return;

    // Create modal
    const modal = document.createElement('div');
    modal.className = 'ticket-preview';
    modal.innerHTML = `
        <div class="preview-content">
            <div class="preview-header">
                <div>
                    <div class="preview-title">${escapeHtml(ticket.subject || 'No subject')}</div>
                    <div class="preview-id">Ticket #${escapeHtml(ticketId)}</div>
                </div>
                <button class="preview-close" onclick="this.closest('.ticket-preview').remove()">×</button>
            </div>
            <div class="preview-body">
                <div class="preview-meta">
                    <div class="preview-meta-item">
                        <div class="preview-field-label">Organization</div>
                        <div class="preview-field-value">${escapeHtml(ticket.organization_name || 'N/A')}</div>
                    </div>
                    <div class="preview-meta-item">
                        <div class="preview-field-label">Priority</div>
                        <div class="preview-field-value">${escapeHtml(ticket.priority || 'N/A')}</div>
                    </div>
                    <div class="preview-meta-item">
                        <div class="preview-field-label">Status</div>
                        <div class="preview-field-value">${escapeHtml(ticket.status || 'N/A')}</div>
                    </div>
                </div>
                ${ticket.description ? `
                    <div class="preview-field">
                        <div class="preview-field-label">Description</div>
                        <div class="preview-field-value">${escapeHtml(ticket.description)}</div>
                    </div>
                ` : ''}
                <div class="preview-field">
                    <div class="preview-field-label">Created</div>
                    <div class="preview-field-value">${formatDate(ticket.created_at)}</div>
                </div>
            </div>
        </div>
    `;

    // Close on background click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });

    document.body.appendChild(modal);
};

// Scroll to bottom
function scrollToBottom() {
    const chatArea = messagesContainer.parentElement;
    chatArea.scrollTop = chatArea.scrollHeight;
}

// Format date
function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Render basic markdown (bold, newlines) — escapes HTML first to prevent XSS
function renderMarkdown(text) {
    if (!text) return '';
    return escapeHtml(text)
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
}

// Initialize
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
