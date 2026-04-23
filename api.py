"""SolveX Web API — FastAPI backend with SSE streaming."""

import asyncio
import json
import os
import shutil
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from app.agent.modeling import ModelingAgent
from app.agent.programming import ProgrammingAgent
from app.agent.writing import WritingAgent
from app.flow.flow_factory import FlowFactory, FlowType
from app.logger import logger
from app.workspace import prepare_workspace, zip_workspace, list_sessions

app = FastAPI(title="SolveX")

# Serve static files
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory session store
sessions: dict[str, dict] = {}


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/api/run")
async def start_run(
    text: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    """Start a new SolveX run. Returns session_id immediately."""
    if not text.strip():
        raise HTTPException(status_code=400, detail="Problem text is required")

    session_id = str(uuid.uuid4())[:8]
    queue = asyncio.Queue()

    # Save uploaded files to a temp dir, then prepare workspace
    data_dir = None
    if files:
        tmp = f"/tmp/solvex_upload_{session_id}"
        os.makedirs(tmp, exist_ok=True)
        for f in files:
            dest = os.path.join(tmp, f.filename)
            with open(dest, "wb") as out:
                out.write(await f.read())
        # If it's a zip, extract it
        if len(files) == 1 and files[0].filename.endswith(".zip"):
            with zipfile.ZipFile(dest, "r") as z:
                z.extractall(tmp)
            os.remove(dest)
            entries = os.listdir(tmp)
            if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])):
                data_dir = os.path.join(tmp, entries[0])
            else:
                data_dir = tmp
        else:
            data_dir = tmp

    # Prepare workspace — unified with CLI
    ws = prepare_workspace(text, data_dir=data_dir, session_id=session_id)

    sessions[session_id] = {
        "id": session_id,
        "problem": text,
        "status": "running",
        "queue": queue,
        "workspace": str(ws),
        "created_at": time.time(),
    }

    # Run in background
    asyncio.create_task(_run_flow(session_id, text, queue, str(ws)))

    return {"session_id": session_id}


@app.get("/api/stream/{session_id}")
async def stream_events(session_id: str):
    """SSE endpoint for streaming progress events."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    queue = sessions[session_id]["queue"]

    async def event_generator():
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield {"data": data}
                parsed = json.loads(data)
                if parsed.get("type") in ("complete", "error"):
                    break
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": ""}

    return EventSourceResponse(event_generator())


@app.get("/api/download/{session_id}")
async def download_zip(session_id: str):
    """Download workspace as ZIP."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    ws = Path(sessions[session_id]["workspace"])
    if not ws.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    zip_path = zip_workspace(ws)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"solvex_{session_id}.zip",
    )


@app.get("/api/sessions")
async def api_list_sessions():
    """List all sessions."""
    stored = {s["id"]: s for s in sessions.values()}
    result = []
    for s in list_sessions():
        status = stored[s["id"]]["status"] if s["id"] in stored else "unknown"
        result.append({
            "id": s["id"],
            "problem": s["problem"] + ("..." if len(s["problem"]) >= 80 else ""),
            "status": status,
            "created_at": s["created_at"],
        })
    return result


async def _run_flow(session_id: str, text: str, queue: asyncio.Queue, workspace: str):
    """Background task: run the full SolveX flow."""
    try:
        agents = {
            "modeling": ModelingAgent(),
            "programming": ProgrammingAgent(),
            "writing": WritingAgent(),
        }

        flow = FlowFactory.create_flow(
            flow_type=FlowType.SOLVEX,
            agents=agents,
            max_iterations=3,
        )
        flow.event_queue = queue

        result = await asyncio.wait_for(
            flow.execute(text, workspace=workspace),
            timeout=3600,
        )

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
