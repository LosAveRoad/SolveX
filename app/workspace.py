"""SolveX workspace management — unified for CLI and Web."""

import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

# Fixed base directory for all sessions
BASE_DIR = Path.home() / ".solvex" / "sessions"

# Workspace subdirectory layout
DIR_PROBLEM = "00_problem"
DIR_MODELING = "01_modeling"
DIR_PROGRAMMING = "02_programming"
DIR_PAPER = "04_paper"
DIR_DATA = "data"

OUTPUT_DIRS = [DIR_MODELING, DIR_PROGRAMMING, DIR_PAPER]


def new_session_id() -> str:
    """Generate a short session ID like '0422-a3f1'."""
    now = datetime.now()
    uid = str(uuid.uuid4())[:4]
    return f"{now.month:02d}{now.day:02d}-{uid}"


def prepare_workspace(
    problem_text: str,
    data_dir: str = None,
    session_id: str = None,
) -> Path:
    """Create a session workspace and populate it.

    Layout:
        ~/.solvex/sessions/{session_id}/
        ├── 00_problem/problem.md   ← problem text
        ├── data/                   ← copied data files
        ├── 01_modeling/            ← master plan + reviews
        ├── 02_programming/         ← model_N/ subdirs with code + figures
        └── 04_paper/

    Args:
        problem_text: The problem description.
        data_dir: Optional path to data files to copy in.
        session_id: Optional session ID (auto-generated if not given).

    Returns:
        Absolute path to the session workspace root.
    """
    session_id = session_id or new_session_id()
    ws = BASE_DIR / session_id

    # Clean output dirs if workspace already exists (re-run)
    for d in OUTPUT_DIRS:
        p = ws / d
        if p.exists():
            shutil.rmtree(p)

    # Create all directories
    for d in [DIR_PROBLEM, DIR_DATA] + OUTPUT_DIRS:
        (ws / d).mkdir(parents=True, exist_ok=True)

    # Save problem text
    (ws / DIR_PROBLEM / "problem.md").write_text(problem_text)

    # Copy data files
    if data_dir and os.path.exists(data_dir):
        _copy_data(data_dir, ws / DIR_DATA)

    return ws


def zip_workspace(workspace: Path, output_path: str = None) -> str:
    """Compress workspace into a ZIP file.

    Args:
        workspace: Path to session workspace.
        output_path: Where to save the ZIP. Defaults to /tmp/solvex_{name}.zip

    Returns:
        Path to the created ZIP file.
    """
    import zipfile

    name = workspace.name
    output_path = output_path or f"/tmp/solvex_{name}.zip"

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in workspace.rglob("*"):
            if file_path.is_file() and "__pycache__" not in str(file_path):
                arcname = f"solvex_{name}/{file_path.relative_to(workspace)}"
                zf.write(str(file_path), arcname)

    return output_path


def list_sessions() -> list[dict]:
    """List all session workspaces."""
    if not BASE_DIR.exists():
        return []
    sessions = []
    for d in sorted(BASE_DIR.iterdir(), reverse=True):
        if d.is_dir():
            problem_file = d / DIR_PROBLEM / "problem.md"
            problem = ""
            if problem_file.exists():
                problem = problem_file.read_text()[:80]
            sessions.append({
                "id": d.name,
                "problem": problem,
                "created_at": d.stat().st_ctime,
            })
    return sessions


def _copy_data(src: str, dst: Path):
    """Copy data files (file or directory) into dst."""
    if os.path.isfile(src):
        shutil.copy2(src, dst / os.path.basename(src))
    elif os.path.isdir(src):
        for item in os.listdir(src):
            s = os.path.join(src, item)
            d = dst / item
            if os.path.isfile(s):
                shutil.copy2(s, d)
            elif os.path.isdir(s):
                shutil.copytree(s, d)
