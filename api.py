"""SolveX Web API — FastAPI backend with SSE streaming."""

import asyncio
import json
import os
import shutil
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
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
async def start_run(
    text: str = "",
    files: list[UploadFile] = File(default=[]),
):
    """Start a new SolveX run. Returns session_id immediately."""
    if not text.strip():
        raise HTTPException(status_code=400, detail="Problem text is required")

    session_id = str(uuid.uuid4())[:8]
    queue = asyncio.Queue()

    # Save uploaded data files to temp dir
    data_dir = None
    if files:
        data_dir = f"/tmp/solvex_data_{session_id}"
        os.makedirs(data_dir, exist_ok=True)
        for f in files:
            dest = os.path.join(data_dir, f.filename)
            with open(dest, "wb") as out:
                content = await f.read()
                out.write(content)
        # If it's a zip, extract it
        if len(files) == 1 and files[0].filename.endswith(".zip"):
            import zipfile as zf
            with zf.ZipFile(dest, "r") as z:
                z.extractall(data_dir)
            os.remove(dest)
            # If extraction created a single subdirectory, use that
            entries = os.listdir(data_dir)
            if len(entries) == 1 and os.path.isdir(os.path.join(data_dir, entries[0])):
                data_dir = os.path.join(data_dir, entries[0])

    sessions[session_id] = {
        "id": session_id,
        "problem": text,
        "status": "running",
        "queue": queue,
        "created_at": time.time(),
        "data_dir": data_dir,
    }

    # Run in background
    asyncio.create_task(_run_flow(session_id, text, queue, data_dir))

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


async def _run_flow(session_id: str, text: str, queue: asyncio.Queue, data_dir: str = None):
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
        flow.event_queue = queue

        result = await asyncio.wait_for(flow.execute(text, data_dir=data_dir), timeout=3600)

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
