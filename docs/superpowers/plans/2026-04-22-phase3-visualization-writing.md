# Phase 3: Visualization Agent + Writing Agent

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add VisualizationAgent (Matplotlib figures) and WritingAgent (LaTeX paper) that run sequentially after the modeling-programming loop.

**Architecture:** Two new ToolCallAgent subclasses plugged into SolveXFlow. After the loop converges and the final plan is written, VisualizationAgent reads programming results and creates PNG figures via matplotlib (PythonExecute). WritingAgent then reads all workspace outputs and produces a complete LaTeX paper. Both agents use file-based communication through the existing workspace directory structure.

**Tech Stack:** Python, Matplotlib (via PythonExecute), LaTeX, ToolCallAgent/OpenManus framework, ChatGLM (glm-4.7)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/prompt/visualization.py` | Visualization prompts (SYSTEM_PROMPT, NEXT_STEP_PROMPT) |
| Create | `app/agent/visualization.py` | VisualizationAgent class |
| Create | `app/prompt/writing.py` | Writing prompts (SYSTEM_PROMPT, NEXT_STEP_PROMPT) |
| Create | `app/agent/writing.py` | WritingAgent class |
| Modify | `app/flow/solvex_flow.py` | Add Phase 3 steps after Phase 2 |
| Modify | `run_flow.py` | Register VisualizationAgent + WritingAgent |

---

### Task 1: Create Visualization Prompt

**Files:**
- Create: `app/prompt/visualization.py`

- [ ] **Step 1: Create the visualization prompt file**

```python
# app/prompt/visualization.py

SYSTEM_PROMPT = (
    "SETTING: You are an expert data visualization specialist for mathematical modeling. "
    "You create publication-quality figures that clearly communicate modeling results.\n\n"

    "AVAILABLE TOOLS:\n"
    "- python_execute: Run Python code. Use matplotlib to generate figures.\n"
    "- str_replace_editor: Create or edit files in the workspace directory.\n"
    "- terminate: Signal that you are done.\n\n"

    "WORKSPACE:\n"
    "- Read data from: workspace/02_programming/ (code, data files, results_summary.md)\n"
    "- Read model from: workspace/01_modeling/final_plan.md\n"
    "- Save figures to: workspace/03_figures/ (PNG format, 300 DPI)\n\n"

    "RESPONSE FORMAT:\n"
    "For every response:\n"
    "1. First, briefly state what you are going to do next and why\n"
    "2. Then make exactly ONE tool call and wait for the result\n"
    "3. After receiving the result, analyze it before making the next move\n\n"

    "WORKFLOW:\n"
    "1. ANALYZE: Read the final modeling plan (workspace/01_modeling/final_plan.md) and "
    "programming results (workspace/02_programming/results_summary.md or data files).\n"
    "2. SELECT: Choose appropriate visualization types based on the model:\n"
    "   - Optimization: feasible region plot, constraint lines, optimal point\n"
    "   - Regression: scatter plot, fitted curve, residuals\n"
    "   - Time series: trend lines, forecasts, confidence intervals\n"
    "   - Classification: decision boundaries, confusion matrix\n"
    "   - Network: graph visualization, flow diagrams\n"
    "   - General: bar charts, heatmaps, contour plots as appropriate\n"
    "3. IMPLEMENT: Write matplotlib Python code via python_execute. For each figure:\n"
    "   - Set figure size and DPI for publication quality (figsize=(8,6), dpi=300)\n"
    "   - Include clear titles, axis labels with units, and legends\n"
    "   - Use professional color schemes\n"
    "   - Save to workspace/03_figures/ using plt.savefig()\n"
    "   - Close figures after saving: plt.close()\n"
    "4. VERIFY: Re-read saved figures directory to confirm all files exist.\n"
    "5. CATALOG: Write a figures catalog to workspace/03_figures/figures_catalog.md listing "
    "each figure with its filename, description, and what it shows.\n\n"

    "CODING GUIDELINES:\n"
    "- Always import matplotlib and set backend: import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt\n"
    "- Always set plt.rcParams for English fonts: plt.rcParams['font.family'] = 'serif'\n"
    "- Save as PNG with dpi=300 and bbox_inches='tight'\n"
    "- Create each figure in a single python_execute call (create plot + save + close)\n"
    "- Use str_replace_editor to write the figures catalog file\n\n"

    "When all figures are created and the catalog is written, call `terminate`."
)

NEXT_STEP_PROMPT = (
    "TODAY'S TASK: Create publication-quality visualizations for the modeling results.\n"
    "1. Read the modeling plan and programming results\n"
    "2. Determine what visualizations are needed\n"
    "3. Create each figure using python_execute (matplotlib)\n"
    "4. Save all figures to workspace/03_figures/\n"
    "5. Write figures catalog to workspace/03_figures/figures_catalog.md\n\n"
    "When all figures and the catalog are saved, call `terminate`."
)
```

- [ ] **Step 2: Verify file syntax**

Run: `cd /Users/akuya/Desktop/manus/SolveX && /Users/akuya/Desktop/manus/SolveX/.venv/bin/python -c "from app.prompt.visualization import SYSTEM_PROMPT, NEXT_STEP_PROMPT; print('OK:', len(SYSTEM_PROMPT), 'chars')"`
Expected: `OK: <number> chars`

---

### Task 2: Create VisualizationAgent

**Files:**
- Create: `app/agent/visualization.py`

- [ ] **Step 1: Create the VisualizationAgent class**

Follow the exact same pattern as `ProgrammingAgent` (simple ToolCallAgent subclass, no MCP).

```python
# app/agent/visualization.py

from app.agent.toolcall import ToolCallAgent
from app.prompt.visualization import SYSTEM_PROMPT, NEXT_STEP_PROMPT
from app.tool import Terminate, ToolCollection
from app.tool.python_execute import PythonExecute
from app.tool.str_replace_editor import StrReplaceEditor


class VisualizationAgent(ToolCallAgent):
    """Data visualization expert that creates publication-quality figures."""

    name: str = "visualization"
    description: str = "Data visualization expert: creates figures and visual analysis from modeling results"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    max_steps: int = 15

    available_tools: ToolCollection = ToolCollection(
        PythonExecute(),
        StrReplaceEditor(),
        Terminate(),
    )
```

- [ ] **Step 2: Verify import works**

Run: `cd /Users/akuya/Desktop/manus/SolveX && /Users/akuya/Desktop/manus/SolveX/.venv/bin/python -c "from app.agent.visualization import VisualizationAgent; print('OK:', VisualizationAgent().name)"`
Expected: `OK: visualization`

---

### Task 3: Create Writing Prompt

**Files:**
- Create: `app/prompt/writing.py`

- [ ] **Step 1: Create the writing prompt file**

```python
# app/prompt/writing.py

SYSTEM_PROMPT = (
    "SETTING: You are an expert academic writer specializing in mathematical modeling papers. "
    "You synthesize results from modeling, programming, and visualization phases into a "
    "well-structured LaTeX paper.\n\n"

    "AVAILABLE TOOLS:\n"
    "- str_replace_editor: Create or edit LaTeX files in the workspace directory.\n"
    "- python_execute: Run Python to process data or generate tables if needed.\n"
    "- terminate: Signal that you are done.\n\n"

    "WORKSPACE:\n"
    "- Read modeling plan: workspace/01_modeling/final_plan.md\n"
    "- Read code & results: workspace/02_programming/ (solution files, data/, results_summary.md)\n"
    "- Read figures: workspace/03_figures/figures_catalog.md and PNG files\n"
    "- Write paper to: workspace/04_paper/\n\n"

    "RESPONSE FORMAT:\n"
    "For every response:\n"
    "1. First, briefly state what you are going to do next and why\n"
    "2. Then make exactly ONE tool call and wait for the result\n"
    "3. After receiving the result, analyze it before making the next move\n\n"

    "WORKFLOW:\n"
    "1. ANALYZE: Read all previous phase outputs:\n"
    "   - workspace/01_modeling/final_plan.md\n"
    "   - workspace/02_programming/ (read solution code and result data)\n"
    "   - workspace/03_figures/figures_catalog.md\n"
    "2. STRUCTURE: Plan the paper sections.\n"
    "3. WRITE: Compose the complete LaTeX paper to workspace/04_paper/main.tex using str_replace_editor.\n"
    "4. VERIFY: Re-read the file to confirm completeness.\n\n"

    "PAPER STRUCTURE (LaTeX):\n"
    "The paper MUST follow this structure:\n\n"

    "\\documentclass{article}\n"
    "\\usepackage{amsmath,amssymb,graphicx,booktabs,hyperref,geometry}\n"
    "\\geometry{margin=1in}\n\n"

    "Sections:\n"
    "1. \\title{...} and \\begin{abstract}...\\end{abstract}\n"
    "2. \\section{Introduction} — Problem background, motivation, objectives\n"
    "3. \\section{Mathematical Model} — Variables, objective function, constraints (from final_plan.md)\n"
    "4. \\section{Solution Method} — Algorithm, implementation details (from programming code)\n"
    "5. \\section{Results and Analysis} — Key findings, tables, figures with \\includegraphics\n"
    "6. \\section{Discussion} — Interpretation, sensitivity, limitations\n"
    "7. \\section{Conclusion} — Summary and future work\n"
    "8. \\section*{References} — Key references\n\n"

    "LATEX GUIDELINES:\n"
    "- Use \\includegraphics{../03_figures/filename.png} for figures (relative path from 04_paper/)\n"
    "- Use \\begin{figure}[h] with \\caption and \\label for each figure\n"
    "- Use \\begin{table} with \\begin{tabular} and \\toprule/\\midrule/\\bottomrule for data tables\n"
    "- Use align environment for mathematical equations: \\begin{align} ... \\end{align}\n"
    "- Include a \\begin{thebibliography} section with relevant references\n"
    "- Write the ENTIRE paper in a single main.tex file\n\n"

    "WRITING GUIDELINES:\n"
    "- Write in clear, academic English\n"
    "- Be precise with mathematical notation\n"
    "- Include numerical results in the Results section\n"
    "- Reference all figures (Figure \\ref{fig:...}) in the text\n"
    "- Keep the paper self-contained and readable\n\n"

    "When the complete paper is written to workspace/04_paper/main.tex, call `terminate`."
)

NEXT_STEP_PROMPT = (
    "TODAY'S TASK: Write a complete LaTeX academic paper.\n"
    "1. Read all workspace outputs (model plan, code results, figures catalog)\n"
    "2. Write the complete paper to workspace/04_paper/main.tex\n"
    "3. Include all figures, tables, and mathematical notation\n\n"
    "When the paper is saved, call `terminate`."
)
```

- [ ] **Step 2: Verify file syntax**

Run: `cd /Users/akuya/Desktop/manus/SolveX && /Users/akuya/Desktop/manus/SolveX/.venv/bin/python -c "from app.prompt.writing import SYSTEM_PROMPT, NEXT_STEP_PROMPT; print('OK:', len(SYSTEM_PROMPT), 'chars')"`
Expected: `OK: <number> chars`

---

### Task 4: Create WritingAgent

**Files:**
- Create: `app/agent/writing.py`

- [ ] **Step 1: Create the WritingAgent class**

Same pattern as ProgrammingAgent. Max steps = 20 (writing a multi-section paper needs more steps).

```python
# app/agent/writing.py

from app.agent.toolcall import ToolCallAgent
from app.prompt.writing import SYSTEM_PROMPT, NEXT_STEP_PROMPT
from app.tool import Terminate, ToolCollection
from app.tool.python_execute import PythonExecute
from app.tool.str_replace_editor import StrReplaceEditor


class WritingAgent(ToolCallAgent):
    """Academic writing expert that composes LaTeX papers from modeling results."""

    name: str = "writing"
    description: str = "Academic writing expert: composes LaTeX papers from modeling and visualization results"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    max_steps: int = 20

    available_tools: ToolCollection = ToolCollection(
        PythonExecute(),
        StrReplaceEditor(),
        Terminate(),
    )
```

- [ ] **Step 2: Verify import works**

Run: `cd /Users/akuya/Desktop/manus/SolveX && /Users/akuya/Desktop/manus/SolveX/.venv/bin/python -c "from app.agent.writing import WritingAgent; print('OK:', WritingAgent().name)"`
Expected: `OK: writing`

---

### Task 5: Extend SolveXFlow with Phase 3

**Files:**
- Modify: `app/flow/solvex_flow.py`

- [ ] **Step 1: Add Phase 3 (Visualization + Writing) after Phase 2**

Add the following code AFTER the `# === Build result summary ===` section at line ~102, and modify the result string to include Phase 3 outputs. The Phase 3 code goes BEFORE the final `return result` line.

Insert this block before `logger.info(f"=== SolveX Completed ===")`:

```python
        # === Phase 3a: Visualization ===
        visualization_agent = self.agents.get("visualization")
        if visualization_agent:
            logger.info(f"\n--- [VisualizationAgent] Starting ---")
            viz_prompt = (
                f"PROBLEM:\n{input_text}\n\n"
                f"Modeling plan: {DIR_MODELING}/final_plan.md\n"
                f"Programming results: {DIR_PROGRAMMING}/\n"
                f"Create publication-quality figures and save to {DIR_FIGURES}/\n"
                f"Write a figures catalog to {DIR_FIGURES}/figures_catalog.md"
            )
            visualization_agent.state = AgentState.IDLE
            visualization_agent.current_step = 0
            visualization_agent.memory = Memory()
            await visualization_agent.run(viz_prompt)
            logger.info(f"--- [VisualizationAgent] Done ---\n")
        else:
            logger.warning("No visualization agent provided, skipping Phase 3a")

        # === Phase 3b: Writing ===
        writing_agent = self.agents.get("writing")
        if writing_agent:
            logger.info(f"\n--- [WritingAgent] Starting ---")
            write_prompt = (
                f"PROBLEM:\n{input_text}\n\n"
                f"Modeling plan: {DIR_MODELING}/final_plan.md\n"
                f"Programming results: {DIR_PROGRAMMING}/\n"
                f"Figures: {DIR_FIGURES}/ (see figures_catalog.md)\n\n"
                f"Write a complete LaTeX paper to {DIR_PAPER}/main.tex\n"
                f"Include all figures and results."
            )
            writing_agent.state = AgentState.IDLE
            writing_agent.current_step = 0
            writing_agent.memory = Memory()
            await writing_agent.run(write_prompt)
            logger.info(f"--- [WritingAgent] Done ---\n")
        else:
            logger.warning("No writing agent provided, skipping Phase 3b")
```

Also update the result string to include new directories:

```python
        result += (
            f"\nFiles produced:\n"
            f"  Plan: {DIR_MODELING}/plan.md\n"
            f"  Final plan: {DIR_MODELING}/final_plan.md\n"
            f"  Code: {DIR_PROGRAMMING}/\n"
            f"  Results: {DIR_PROGRAMMING}/results_summary.md\n"
            f"  Figures: {DIR_FIGURES}/\n"
            f"  Paper: {DIR_PAPER}/main.tex\n"
        )
```

- [ ] **Step 2: Verify syntax**

Run: `cd /Users/akuya/Desktop/manus/SolveX && /Users/akuya/Desktop/manus/SolveX/.venv/bin/python -c "from app.flow.solvex_flow import SolveXFlow; print('OK')"`
Expected: `OK`

---

### Task 6: Register New Agents in run_flow.py

**Files:**
- Modify: `run_flow.py`

- [ ] **Step 1: Add imports and register agents**

Add imports for the two new agents and add them to the agents dict:

```python
import asyncio
import time

from app.agent.modeling import ModelingAgent
from app.agent.programming import ProgrammingAgent
from app.agent.visualization import VisualizationAgent
from app.agent.writing import WritingAgent
from app.flow.flow_factory import FlowFactory, FlowType
from app.logger import logger


async def run_flow():
    agents = {
        "modeling": ModelingAgent(),
        "programming": ProgrammingAgent(),
        "visualization": VisualizationAgent(),
        "writing": WritingAgent(),
    }
```

The rest of the function stays the same.

- [ ] **Step 2: Verify imports**

Run: `cd /Users/akuya/Desktop/manus/SolveX && /Users/akuya/Desktop/manus/SolveX/.venv/bin/python -c "from app.agent.visualization import VisualizationAgent; from app.agent.writing import WritingAgent; print('OK')"`
Expected: `OK`

---

### Task 7: End-to-End Test

**Files:**
- Test with existing test problem

- [ ] **Step 1: Run the full pipeline with the linear programming test problem**

Run:
```bash
cd /Users/akuya/Desktop/manus/SolveX && echo "A factory produces two products A and B. Product A requires 2 kg of material X and 1 kg of material Y, with a profit of 300 yuan per unit. Product B requires 1 kg of material X and 2 kg of material Y, with a profit of 400 yuan per unit. The factory has 100 kg of material X and 120 kg of material Y. How should the factory arrange production to maximize total profit?" | /Users/akuya/Desktop/manus/SolveX/.venv/bin/python run_flow.py
```
Timeout: 600 seconds (10 minutes, the full pipeline is slow due to LLM calls)

- [ ] **Step 2: Verify outputs**

Run:
```bash
ls -la workspace/03_figures/
ls -la workspace/04_paper/
```

Expected:
- `workspace/03_figures/` contains at least one `.png` file and `figures_catalog.md`
- `workspace/04_paper/main.tex` exists and contains a complete LaTeX document with `\documentclass`, `\begin{document}`, `\includegraphics`, and `\end{document}`

- [ ] **Step 3: Spot-check LaTeX content**

Run: `head -50 workspace/04_paper/main.tex`

Expected: Valid LaTeX document structure with title, abstract, and section headings.
