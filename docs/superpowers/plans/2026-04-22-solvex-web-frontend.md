# SolveX Web Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Perplexity-style web UI to SolveX with streaming progress, session history, and ZIP download of all outputs.

**Architecture:** FastAPI backend serves static files and exposes SSE endpoint for streaming agent progress. The flow's `_print_status/_print_step/_print_done` calls are redirected to an event queue that feeds the SSE stream. Frontend is vanilla HTML/CSS/JS — no build step, no framework. Workspace is cleaned before each run. Sessions are stored in-memory with unique IDs.

**Tech Stack:** FastAPI, sse-starlette, vanilla HTML/CSS/JS, Python zipfile for download

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `api.py` | FastAPI server: SSE streaming, ZIP download, workspace cleanup, session management |
| Create | `static/index.html` | Single-page UI layout (sidebar + main area) |
| Create | `static/style.css` | Perplexity-inspired dark theme styles |
| Create | `static/app.js` | Client logic: SSE consumption, session history, download trigger |
| Modify | `app/flow/solvex_flow.py` | Add optional event_queue parameter to redirect _print_* calls |

---

### Task 1: Add Event Queue Support to SolveXFlow

**Files:**
- Modify: `app/flow/solvex_flow.py`

The flow currently prints to stdout via `_print_status/_print_step/_print_done`. We need to also push events to an optional async queue so the API can stream them via SSE.

- [ ] **Step 1: Add event queue support to flow helper functions and execute()**

In `app/flow/solvex_flow.py`, modify the helper functions to accept an optional queue, and add `event_queue` parameter to the class and `execute()`:

```python
# Replace the three helper functions (lines 18-31) with:

# Progress event helpers — print to stdout AND push to optional SSE queue
async def _emit(queue, event_type: str, message: str):
    """Print to stdout and push to SSE queue if provided."""
    if event_type == "status":
        print(f"\033[1;36m{'='*50}\n  {message}\n{'='*50}\033[0m")
    elif event_type == "step":
        print(f"\033[1;33m>>> {message}\033[0m")
    elif event_type == "done":
        print(f"\033[1;32m✓ {message}\033[0m")
    elif event_type == "info":
        print(f"  {message}")
    elif event_type == "warn":
        print(f"  ⚠ {message}")

    if queue is not None:
        import json
        await queue.put(json.dumps({"type": event_type, "message": message}))
```

Then in the `SolveXFlow` class, add `event_queue` field and thread it through `execute()`:

```python
class SolveXFlow(BaseFlow):
    """SolveX mathematical modeling workflow with file-based agent communication."""

    max_iterations: int = 5
    event_queue: object = None  # Optional asyncio.Queue for SSE streaming
```

Replace every `_print_status(msg)` call with `await _emit(self.event_queue, "status", msg)`, every `_print_step(msg)` with `await _emit(self.event_queue, "step", msg)`, every `_print_done(msg)` with `await _emit(self.event_queue, "done", msg)`, and every bare `print(f"  ...")` with `await _emit(self.event_queue, "info", msg)`.

Add at the very start of `execute()`, before the workspace makedirs:

```python
        # Clean workspace before each run
        import shutil
        for subdir in [abs_modeling, abs_programming, abs_figures, abs_paper]:
            if os.path.exists(subdir):
                shutil.rmtree(subdir)
```

Add workspace cleanup import at top of file:
```python
import shutil
```

- [ ] **Step 2: Verify syntax**

Run: `cd /Users/akuya/Desktop/manus/SolveX && .venv/bin/python -c "from app.flow.solvex_flow import SolveXFlow; print('OK')"`
Expected: `OK`

---

### Task 2: Create FastAPI Backend

**Files:**
- Create: `api.py`

- [ ] **Step 1: Create the API server**

```python
"""SolveX Web API — FastAPI backend with SSE streaming."""

import asyncio
import json
import os
import shutil
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from app.agent.modeling import ModelingAgent
from app.agent.programming import ProgrammingAgent
from app.agent.visualization import VisualizationAgent
from app.agent.writing import WritingAgent
from app.flow.flow_factory import FlowFactory, FlowType
from app.logger import logger

app = FastAPI(title="SolveX")

# Serve static files
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory session store
sessions: dict[str, dict] = {}

WORKSPACE = "workspace"


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/api/run")
async def start_run(problem: dict):
    """Start a new SolveX run. Returns session_id immediately."""
    text = problem.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Problem text is required")

    session_id = str(uuid.uuid4())[:8]
    queue = asyncio.Queue()

    sessions[session_id] = {
        "id": session_id,
        "problem": text,
        "status": "running",
        "queue": queue,
        "created_at": time.time(),
    }

    # Run in background
    asyncio.create_task(_run_flow(session_id, text, queue))

    return {"session_id": session_id}


@app.get("/api/stream/{session_id}")
async def stream_events(session_id: str):
    """SSE endpoint for streaming progress events."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    queue = session["queue"]

    async def event_generator():
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield {"data": data}
                # Check if this is the final event
                parsed = json.loads(data)
                if parsed.get("type") == "complete" or parsed.get("type") == "error":
                    break
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": ""}

    return EventSourceResponse(event_generator())


@app.get("/api/download/{session_id}")
async def download_zip(session_id: str):
    """Download all workspace outputs as a ZIP file."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    workspace_dir = Path(WORKSPACE)
    if not workspace_dir.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    zip_path = Path(f"/tmp/solvex_{session_id}.zip")
    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in workspace_dir.rglob("*"):
            if file_path.is_file() and "__pycache__" not in str(file_path):
                arcname = f"solvex_output/{file_path.relative_to(workspace_dir)}"
                zf.write(str(file_path), arcname)

    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename=f"solvex_{session_id}.zip",
    )


@app.get("/api/sessions")
async def list_sessions():
    """List all sessions."""
    return [
        {
            "id": s["id"],
            "problem": s["problem"][:80] + ("..." if len(s["problem"]) > 80 else ""),
            "status": s["status"],
            "created_at": s["created_at"],
        }
        for s in sessions.values()
    ]


async def _run_flow(session_id: str, text: str, queue: asyncio.Queue):
    """Background task: run the full SolveX flow."""
    try:
        agents = {
            "modeling": ModelingAgent(),
            "programming": ProgrammingAgent(),
            "visualization": VisualizationAgent(),
            "writing": WritingAgent(),
        }

        flow = FlowFactory.create_flow(
            flow_type=FlowType.SOLVEX,
            agents=agents,
            max_iterations=3,
        )
        # Inject the SSE queue into the flow
        flow.event_queue = queue

        result = await asyncio.wait_for(flow.execute(text), timeout=3600)

        sessions[session_id]["status"] = "completed"
        await queue.put(json.dumps({
            "type": "complete",
            "message": "SolveX pipeline completed",
            "result": result,
        }))

    except asyncio.TimeoutError:
        sessions[session_id]["status"] = "timeout"
        await queue.put(json.dumps({"type": "error", "message": "Timeout after 1 hour"}))
    except Exception as e:
        logger.error(f"Run error: {e}")
        sessions[session_id]["status"] = "error"
        await queue.put(json.dumps({"type": "error", "message": str(e)}))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 2: Verify server starts**

Run: `cd /Users/akuya/Desktop/manus/SolveX && .venv/bin/python -c "from api import app; print('FastAPI app OK')"`
Expected: `FastAPI app OK`

---

### Task 3: Create Frontend HTML

**Files:**
- Create: `static/index.html`

- [ ] **Step 1: Create the HTML file**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SolveX — Math Modeling</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="app">
        <!-- Sidebar -->
        <aside class="sidebar" id="sidebar">
            <div class="sidebar-header">
                <h2>SolveX</h2>
                <button class="btn-icon" id="toggleSidebar" title="Toggle sidebar">☰</button>
            </div>
            <button class="btn-new" id="newSession">+ New Problem</button>
            <div class="session-list" id="sessionList">
                <!-- sessions rendered here -->
            </div>
        </aside>

        <!-- Main content -->
        <main class="main">
            <!-- Input area -->
            <div class="input-area">
                <div class="input-wrapper">
                    <textarea id="problemInput" placeholder="Describe your mathematical modeling problem..." rows="3"></textarea>
                    <button class="btn-submit" id="submitBtn">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
                    </button>
                </div>
            </div>

            <!-- Progress area -->
            <div class="progress-area" id="progressArea">
                <div class="progress-messages" id="progressMessages"></div>
            </div>

            <!-- Results area -->
            <div class="results-area" id="resultsArea" style="display:none">
                <div class="results-header">
                    <h3>Results</h3>
                    <button class="btn-download" id="downloadBtn">
                        ⬇ Download ZIP
                    </button>
                </div>
                <div class="results-files" id="resultsFiles"></div>
            </div>
        </main>
    </div>

    <script src="/static/app.js"></script>
</body>
</html>
```

---

### Task 4: Create CSS Styles

**Files:**
- Create: `static/style.css`

- [ ] **Step 1: Create Perplexity-inspired dark theme**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --bg-primary: #191a1a;
    --bg-secondary: #202222;
    --bg-input: #2a2c2c;
    --bg-card: #242626;
    --text-primary: #e8e8e8;
    --text-secondary: #9a9a9a;
    --accent: #20b8cd;
    --accent-hover: #1da8bb;
    --green: #22c55e;
    --yellow: #eab308;
    --red: #ef4444;
    --border: #333535;
    --sidebar-width: 280px;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    height: 100vh;
    overflow: hidden;
}

.app {
    display: flex;
    height: 100vh;
}

/* Sidebar */
.sidebar {
    width: var(--sidebar-width);
    background: var(--bg-secondary);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    transition: width 0.2s;
    overflow: hidden;
}

.sidebar.collapsed {
    width: 0;
    border-right: none;
}

.sidebar-header {
    padding: 16px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
}

.sidebar-header h2 {
    font-size: 18px;
    color: var(--accent);
    font-weight: 700;
    letter-spacing: 1px;
}

.btn-icon {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 20px;
    padding: 4px 8px;
    border-radius: 6px;
}
.btn-icon:hover { background: var(--bg-input); color: var(--text-primary); }

.btn-new {
    margin: 12px 16px;
    padding: 10px;
    background: transparent;
    border: 1px dashed var(--border);
    color: var(--text-secondary);
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    transition: all 0.15s;
}
.btn-new:hover { border-color: var(--accent); color: var(--accent); }

.session-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
}

.session-item {
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    margin-bottom: 4px;
    transition: background 0.1s;
}
.session-item:hover { background: var(--bg-input); }
.session-item.active { background: var(--bg-input); }
.session-item .problem-preview {
    font-size: 13px;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.session-item .session-meta {
    font-size: 11px;
    color: var(--text-secondary);
    margin-top: 4px;
    display: flex;
    gap: 8px;
}
.status-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 4px;
    vertical-align: middle;
}
.status-dot.running { background: var(--yellow); }
.status-dot.completed { background: var(--green); }
.status-dot.error { background: var(--red); }

/* Main */
.main {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

/* Input */
.input-area {
    padding: 24px 32px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
}

.input-wrapper {
    display: flex;
    gap: 12px;
    align-items: flex-end;
    max-width: 800px;
    margin: 0 auto;
}

textarea {
    flex: 1;
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 18px;
    color: var(--text-primary);
    font-size: 15px;
    font-family: inherit;
    resize: none;
    outline: none;
    transition: border-color 0.15s;
}
textarea:focus { border-color: var(--accent); }
textarea::placeholder { color: var(--text-secondary); }

.btn-submit {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    border: none;
    background: var(--accent);
    color: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: background 0.15s;
}
.btn-submit:hover { background: var(--accent-hover); }
.btn-submit:disabled { opacity: 0.5; cursor: not-allowed; }

/* Progress */
.progress-area {
    flex: 1;
    overflow-y: auto;
    padding: 24px 32px;
}

.progress-messages {
    max-width: 800px;
    margin: 0 auto;
}

.progress-msg {
    padding: 6px 0;
    font-size: 14px;
    line-height: 1.6;
    animation: fadeIn 0.2s;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
}

.msg-status {
    color: var(--accent);
    font-weight: 600;
    font-size: 15px;
    padding: 8px 0 4px;
}
.msg-step { color: var(--yellow); }
.msg-done { color: var(--green); }
.msg-info { color: var(--text-secondary); font-size: 13px; }
.msg-error { color: var(--red); }
.msg-complete { color: var(--green); font-weight: 600; font-size: 15px; padding: 12px 0; }

/* Results */
.results-area {
    border-top: 1px solid var(--border);
    padding: 16px 32px;
    flex-shrink: 0;
}

.results-header {
    max-width: 800px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.results-header h3 { font-size: 16px; }

.btn-download {
    padding: 8px 16px;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    transition: background 0.15s;
}
.btn-download:hover { background: var(--accent-hover); }

.results-files {
    max-width: 800px;
    margin: 0 auto;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 8px;
}

.file-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    font-size: 13px;
}
.file-card .file-label {
    color: var(--text-secondary);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.file-card .file-name {
    color: var(--accent);
    margin-top: 4px;
    word-break: break-all;
}
```

---

### Task 5: Create Frontend JavaScript

**Files:**
- Create: `static/app.js`

- [ ] **Step 1: Create client-side logic**

```javascript
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
$('toggleSidebar').addEventListener('click', () => {
    $('sidebar').classList.toggle('collapsed');
});
$('newSession').addEventListener('click', () => {
    $('problemInput').value = '';
    $('problemInput').focus();
    clearProgress();
});

// Download
$('downloadBtn').addEventListener('click', () => {
    if (currentSessionId) {
        window.open(`${API}/api/download/${currentSessionId}`, '_blank');
    }
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

// Load sessions on page load
loadSessions();
```

---

### Task 6: Integration Test

**Files:**
- No new files

- [ ] **Step 1: Start the server**

Run: `cd /Users/akuya/Desktop/manus/SolveX && .venv/bin/python api.py`
Expected: `Uvicorn running on http://0.0.0.0:8000`

- [ ] **Step 2: Open browser**

Open `http://localhost:8000` in browser. Verify:
- Dark Perplexity-like UI renders
- Input area accepts text
- Sidebar shows empty state

- [ ] **Step 3: Submit a test problem**

Type a problem and submit. Verify:
- SSE events stream into progress area
- Status/step/done messages appear with colors
- After completion, results area shows file cards
- Download ZIP button works
- Session appears in sidebar

- [ ] **Step 4: Verify workspace cleanup**

Submit a second problem. Check that workspace was cleaned before the new run (old files should not persist).
