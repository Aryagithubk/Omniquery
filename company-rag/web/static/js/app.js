// ─────────────────────────────────────────────────────
//  OmniQuery AI  —  app.js  (v10 GlobalLogic theme)
// ─────────────────────────────────────────────────────

const form         = document.getElementById('query-form');
const input        = document.getElementById('query-input');
const chatContainer = document.getElementById('chat-container');
const loader       = document.getElementById('loader');
const roleBadge    = document.getElementById('role-badge');
const logoutBtn    = document.getElementById('logout-btn');

// ── Auth Guard ──────────────────────────────────────
function initAuth() {
    const token = localStorage.getItem('token');
    const role  = localStorage.getItem('role');

    if (!token) {
        window.location.href = '/auth';
        return;
    }

    roleBadge.textContent = role ? role.toUpperCase() : 'USER';
    roleBadge.classList.remove('hidden');
    logoutBtn.classList.remove('hidden');
}

initAuth();

// ── Logout ──────────────────────────────────────────
logoutBtn.addEventListener('click', () => {
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    window.location.href = '/auth';
});

// ── Suggestion chips ────────────────────────────────
document.querySelectorAll('.suggestion-chip').forEach(chip => {
    chip.addEventListener('click', () => {
        input.value = chip.textContent.trim();
        form.dispatchEvent(new Event('submit'));
    });
});

// ── Submit handler ───────────────────────────────────
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = input.value.trim();
    if (!query) return;

    // Remove welcome message on first send
    const welcome = document.querySelector('.welcome-message');
    if (welcome) {
        welcome.style.transition = 'opacity 0.3s ease';
        welcome.style.opacity = '0';
        setTimeout(() => welcome.remove(), 300);
    }
    // Hide the right bot panel
    const botPanel = document.getElementById('bot-panel-right');
    if (botPanel) botPanel.classList.add('hidden-chat');
    // Mark container
    chatContainer.classList.add('has-messages');

    appendMessage(query, 'user');
    input.value = '';
    input.focus();

    const sendBtn = document.getElementById('send-btn');
    sendBtn.disabled = true;
    loader.style.display = 'flex';

    try {
        const token = localStorage.getItem('token');
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = 'Bearer ' + token;

        const res = await fetch('/api/v1/query', {
            method: 'POST',
            headers,
            body: JSON.stringify({ query })
        });

        if (res.status === 401) {
            localStorage.removeItem('token');
            localStorage.removeItem('role');
            window.location.href = '/auth';
            return;
        }

        const data = await res.json();
        appendMessage(
            data.answer,
            'bot',
            data.sources     || [],
            data.agents_used || [],
            data.confidence  || 0
        );
    } catch (err) {
        console.error('Query error:', err);
        appendMessage('⚠️ Unable to reach the OmniQuery server. Make sure it is running on port 8001.', 'bot');
    } finally {
        loader.style.display = 'none';
        sendBtn.disabled = false;
    }
});

// ── Append message ───────────────────────────────────
function appendMessage(text, sender, sources = [], agentsUsed = [], confidence = 0) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message', sender);

    const avatar = document.createElement('div');
    avatar.classList.add('avatar');
    if (sender === 'user') {
        const role = localStorage.getItem('role') || 'U';
        avatar.textContent = role.charAt(0).toUpperCase();
    } else {
        avatar.textContent = '⚡';
    }

    const contentDiv = document.createElement('div');
    contentDiv.classList.add('message-content');

    const textDiv = document.createElement('div');
    textDiv.classList.add('text');
    textDiv.innerHTML = formatText(text);
    contentDiv.appendChild(textDiv);

    if (sender === 'bot') {
        // Agent badges + confidence
        if (agentsUsed.length > 0) {
            const agentsDiv = document.createElement('div');
            agentsDiv.classList.add('agents-used');
            agentsDiv.innerHTML = agentsUsed.map(agent => {
                const icon = getAgentIcon(agent);
                const cls  = getAgentClass(agent);
                return `<span class="agent-badge ${cls}">${icon} ${agent}</span>`;
            }).join('');

            if (confidence > 0) {
                const pct   = Math.round(confidence * 100);
                const level = confidence >= 0.7 ? 'high' : confidence >= 0.4 ? 'med' : 'low';
                agentsDiv.innerHTML += `<span class="confidence-badge confidence-${level}">${pct}% confidence</span>`;
            }
            contentDiv.appendChild(agentsDiv);
        }

        // Sources
        if (sources.length > 0) {
            const sourcesDiv = document.createElement('div');
            sourcesDiv.classList.add('sources');
            sourcesDiv.innerHTML = 'Sources: ' + sources.map(s => {
                const icon = getSourceIcon(s.source_type);
                const name = getSourceName(s);
                const cls  = getSourceClass(s.source_type);
                return `<span class="source-tag ${cls}">${icon} ${name}</span>`;
            }).join('');
            contentDiv.appendChild(sourcesDiv);
        }
    }

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(contentDiv);
    chatContainer.appendChild(msgDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// ── Agent helpers ─────────────────────────────────────
function getAgentIcon(agent) {
    const icons = { DocAgent: '📄', DBAgent: '🗃️', ConfluenceAgent: '📖', WebSearchAgent: '🌐', Fallback: 'ℹ️' };
    return icons[agent] || '🤖';
}

function getAgentClass(agent) {
    const classes = { DocAgent: 'agent-doc', DBAgent: 'agent-db', ConfluenceAgent: 'agent-confluence', WebSearchAgent: 'agent-web', Fallback: 'agent-fallback' };
    return classes[agent] || '';
}

function getSourceIcon(type) {
    const icons = { document: '📄', database: '🗃️', confluence: '📖', web: '🌐', general_knowledge: 'ℹ️' };
    return icons[type] || '📎';
}

function getSourceClass(type) {
    const classes = { document: 'source-doc', database: 'source-db', confluence: 'source-confluence', web: 'source-web', general_knowledge: 'source-general' };
    return classes[type] || '';
}

function getSourceName(source) {
    if (source.source_type === 'document') {
        const path = source.source_identifier || 'Unknown';
        return path.split('\\').pop().split('/').pop();
    }
    if (source.source_type === 'database') return source.excerpt || 'Database Query';
    if (source.source_type === 'web') {
        try { return new URL(source.source_identifier).hostname; } catch { return 'Web Source'; }
    }
    if (source.source_type === 'confluence') return 'Confluence Page';
    return source.source_identifier || 'Unknown';
}

// ── Text Formatting (Markdown → HTML) ────────────────
function formatText(text) {
    if (!text) return '';
    const lines      = text.split('\n');
    const result     = [];
    let tableLines   = [];
    let inTable      = false;

    for (let i = 0; i < lines.length; i++) {
        const line        = lines[i].trim();
        const isTableRow  = line.startsWith('|') && line.endsWith('|');
        const isSeparator = /^\|[\s\-:|]+\|$/.test(line);

        if (isTableRow || isSeparator) {
            if (!inTable) inTable = true;
            tableLines.push(line);
        } else {
            if (inTable) {
                result.push(renderMarkdownTable(tableLines));
                tableLines = [];
                inTable = false;
            }
            result.push(line === '' ? '<br>' : formatLine(line));
        }
    }

    if (inTable && tableLines.length > 0) result.push(renderMarkdownTable(tableLines));
    return result.join('\n');
}

function formatLine(line) {
    line = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // Markdown links
    line = line.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, linkText, url) => {
        if (url.indexOf('/static/reports/') !== -1 || url.match(/\.(pdf|csv|xlsx|doc|docx|zip)$/i)) {
            return `<a href="${url}" target="_blank" download class="pdf-download-btn">📥 ${linkText}</a>`;
        }
        return `<a href="${url}" target="_blank" class="inline-link">${linkText}</a>`;
    });

    // Raw URLs
    line = line.replace(
        /(?<!href="|">)(?:https?:\/\/[^\s<]+|\/static\/reports\/[\w\-]+\.pdf)/g,
        url => {
            if (url.indexOf('/static/reports/') !== -1) {
                return `<a href="${url}" target="_blank" download class="pdf-download-btn">📥 Download Report</a>`;
            }
            return `<a href="${url}" target="_blank" class="inline-link">${url}</a>`;
        }
    );

    // Bold, italic, code
    line = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    line = line.replace(/\*(.*?)\*/g,     '<em>$1</em>');
    line = line.replace(/`(.*?)`/g,       '<code>$1</code>');

    return line;
}

function renderMarkdownTable(lines) {
    if (lines.length < 2) return lines.join('<br>');

    const headerLine = lines[0];
    let dataStartIndex = 1;
    for (let s = 1; s < lines.length; s++) {
        if (/^\|[\s\-:|]+\|$/.test(lines[s])) { dataStartIndex = s + 1; break; }
    }

    const headerCells = headerLine.split('|').filter(c => c.trim() !== '');
    const rowCount    = lines.length - dataStartIndex;

    let html = '<div class="db-table-wrapper">';
    html += '<div class="db-table-header">';
    html += '<span class="db-table-icon">📊</span>';
    html += '<span class="db-table-title">Query Results</span>';
    html += `<span class="db-table-count">${rowCount} rows</span>`;
    html += '</div>';
    html += '<div class="db-table-scroll">';
    html += '<table class="db-result-table">';

    html += '<thead><tr>';
    headerCells.forEach(cell => { html += `<th>${cell.trim()}</th>`; });
    html += '</tr></thead><tbody>';

    for (let i = dataStartIndex; i < lines.length; i++) {
        const cells = lines[i].split('|').filter(c => c.trim() !== '');
        if (/^[\s\-:|]+$/.test(cells.join(''))) continue;
        html += '<tr>';
        cells.forEach(cell => {
            const value     = cell.trim();
            const isNumeric = /^[\d,]+(\.\d+)?$/.test(value);
            html += `<td${isNumeric ? ' class="numeric"' : ''}>${value}</td>`;
        });
        html += '</tr>';
    }
    html += '</tbody></table></div></div>';
    return html;
}
