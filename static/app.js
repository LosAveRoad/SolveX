const API = '';
let currentSessionId = null;
let eventSource = null;
const $ = id => document.getElementById(id);

// Submit
$('submitBtn').addEventListener('click', startRun);
$('problemInput').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startRun(); }
});

// Sidebar
$('toggleSidebar').addEventListener('click', () => $('sidebar').classList.toggle('collapsed'));
$('newSession').addEventListener('click', () => {
    $('problemInput').value = '';
    $('problemInput').focus();
    clearProgress();
});

// Download
$('downloadBtn').addEventListener('click', () => {
    if (currentSessionId) window.open(`${API}/api/download/${currentSessionId}`, '_blank');
});

async function startRun() {
    const text = $('problemInput').value.trim();
    if (!text) return;

    $('submitBtn').disabled = true;
    clearProgress();

    try {
        const resp = await fetch(`${API}/api/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text }),
        });
        const data = await resp.json();
        currentSessionId = data.session_id;
        addProgress('status', `SolveX Started — Session ${currentSessionId}`);
        connectSSE(data.session_id);
        loadSessions();
    } catch (err) {
        addProgress('error', `Failed to start: ${err.message}`);
        $('submitBtn').disabled = false;
    }
}

function connectSSE(sessionId) {
    if (eventSource) eventSource.close();
    eventSource = new EventSource(`${API}/api/stream/${sessionId}`);

    eventSource.onmessage = (e) => {
        const event = JSON.parse(e.data);
        addProgress(event.type, event.message);
        if (event.type === 'complete') {
            $('submitBtn').disabled = false;
            eventSource.close();
            showResults(event.result);
            loadSessions();
        }
        if (event.type === 'error') {
            $('submitBtn').disabled = false;
            eventSource.close();
            loadSessions();
        }
    };

    eventSource.onerror = () => {
        eventSource.close();
        $('submitBtn').disabled = false;
    };
}

function addProgress(type, message) {
    const div = document.createElement('div');
    div.className = `progress-msg msg-${type}`;
    div.textContent = message;
    $('progressMessages').appendChild(div);
    $('progressArea').scrollTop = $('progressArea').scrollHeight;
}

function clearProgress() {
    $('progressMessages').innerHTML = '';
    $('resultsArea').style.display = 'none';
}

function showResults(resultText) {
    $('resultsArea').style.display = 'block';
    const files = [
        { label: 'Modeling Plan', name: '01_modeling/plan.md' },
        { label: 'Final Plan', name: '01_modeling/final_plan.md' },
        { label: 'Code', name: '02_programming/solution.py' },
        { label: 'Figures', name: '03_figures/*.png' },
        { label: 'Paper', name: '04_paper/main.tex' },
    ];
    $('resultsFiles').innerHTML = files.map(f => `
        <div class="file-card">
            <div class="file-label">${f.label}</div>
            <div class="file-name">${f.name}</div>
        </div>
    `).join('');
}

async function loadSessions() {
    try {
        const resp = await fetch(`${API}/api/sessions`);
        const sessions = await resp.json();
        $('sessionList').innerHTML = sessions.reverse().map(s => `
            <div class="session-item ${s.id === currentSessionId ? 'active' : ''}">
                <div class="problem-preview">${s.problem}</div>
                <div class="session-meta">
                    <span><span class="status-dot ${s.status}"></span>${s.status}</span>
                    <span>${new Date(s.created_at * 1000).toLocaleTimeString()}</span>
                </div>
            </div>
        `).join('');
    } catch {}
}

loadSessions();
