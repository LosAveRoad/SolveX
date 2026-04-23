import asyncio
import json
import os
import sys
import tempfile
from typing import Dict

from app.tool.base import BaseTool

# Use the same Python interpreter that runs this process
PYTHON_BIN = sys.executable


class PythonExecute(BaseTool):
    """A tool for executing Python code with timeout and safety restrictions."""

    name: str = "python_execute"
    description: str = "Executes Python code string. Note: Only print outputs are visible, function return values are not captured. Use print statements to see results."
    parameters: dict = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The Python code to execute.",
            },
        },
        "required": ["code"],
    }

    async def execute(
        self,
        code: str,
        timeout: int = 120,
    ) -> Dict:
        """
        Executes the provided Python code in a subprocess with a timeout.

        Uses subprocess instead of multiprocessing to avoid pickle/spawn issues
        on macOS + Python 3.13.

        Args:
            code (str): The Python code to execute.
            timeout (int): Execution timeout in seconds (default: 120).

        Returns:
            Dict: Contains 'observation' with output and 'success' status.
        """
        # Write code to a temp file and run it as a subprocess
        fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="solvex_")
        with os.fdopen(fd, "w") as f:
            f.write(code)

        try:
            proc = await asyncio.create_subprocess_exec(
                PYTHON_BIN, tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                os.unlink(tmp_path)
                return {
                    "observation": f"Execution timeout after {timeout} seconds",
                    "success": False,
                }

            output = stdout.decode("utf-8", errors="replace") if stdout else ""

            if proc.returncode == 0:
                if not output.strip():
                    # Detect import-only code
                    stripped = code.strip()
                    all_lines = [
                        l.strip()
                        for l in stripped.split("\n")
                        if l.strip() and not l.strip().startswith("#")
                    ]
                    is_import_only = (
                        all(l.startswith(("import ", "from ")) for l in all_lines)
                        if all_lines
                        else False
                    )
                    if is_import_only:
                        output = (
                            "Imports loaded successfully. Now write actual computation code with print() "
                            "to see results. Do NOT repeat imports — just write the logic you need."
                        )
                    else:
                        output = "Code executed successfully (no print output). Use print() to see results."
                return {"observation": output, "success": True}
            else:
                return {"observation": output or f"Process exited with code {proc.returncode}", "success": False}

        except Exception as e:
            return {"observation": f"Execution failed: {str(e)}", "success": False}
        finally:
            os.unlink(tmp_path)
