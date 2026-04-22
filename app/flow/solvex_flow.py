import os
import shutil
import time
from typing import Union

from app.agent.base import BaseAgent
from app.flow.base import BaseFlow
from app.logger import logger
from app.schema import AgentState, Memory


WORKSPACE = "workspace"
DIR_MODELING = f"{WORKSPACE}/01_modeling"
DIR_PROGRAMMING = f"{WORKSPACE}/02_programming"
DIR_FIGURES = f"{WORKSPACE}/03_figures"
DIR_PAPER = f"{WORKSPACE}/04_paper"
DIR_DATA = f"{WORKSPACE}/data"


async def _emit(queue, event_type: str, message: str):
    """Print to stdout AND push to SSE queue if provided."""
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


class SolveXFlow(BaseFlow):
    """SolveX mathematical modeling workflow with file-based agent communication."""

    max_iterations: int = 5
    event_queue: object = None  # Optional asyncio.Queue for SSE streaming

    def __init__(
        self,
        agents: Union[BaseAgent, list, dict],
        max_iterations: int = 5,
        **data,
    ):
        data["max_iterations"] = max_iterations
        super().__init__(agents, **data)

    async def execute(self, input_text: str, data_dir: str = None) -> str:
        """Execute the full modeling workflow.

        Args:
            input_text: The problem description.
            data_dir: Optional path to a directory of data files (CSV, XLSX, etc.)
                      to copy into workspace/data/ for agents to access.
        """
        # Clean workspace before each run
        abs_workspace = os.path.join(os.getcwd(), WORKSPACE)
        for subdir_name in ["01_modeling", "02_programming", "03_figures", "04_paper", "data"]:
            subdir = os.path.join(abs_workspace, subdir_name)
            if os.path.exists(subdir):
                shutil.rmtree(subdir)

        # Resolve absolute paths once — str_replace_editor requires absolute paths
        cwd = os.getcwd()
        abs_modeling = os.path.join(cwd, DIR_MODELING)
        abs_programming = os.path.join(cwd, DIR_PROGRAMMING)
        abs_figures = os.path.join(cwd, DIR_FIGURES)
        abs_paper = os.path.join(cwd, DIR_PAPER)
        abs_data = os.path.join(cwd, DIR_DATA)

        # Ensure workspace directories exist
        for d in [abs_modeling, abs_programming, abs_figures, abs_paper]:
            os.makedirs(d, exist_ok=True)

        # Copy data files into workspace/data/ if provided
        data_info = ""
        if data_dir and os.path.exists(data_dir):
            os.makedirs(abs_data, exist_ok=True)
            if os.path.isdir(data_dir):
                for item in os.listdir(data_dir):
                    src = os.path.join(data_dir, item)
                    dst = os.path.join(abs_data, item)
                    if os.path.isfile(src):
                        shutil.copy2(src, dst)
                    elif os.path.isdir(src):
                        shutil.copytree(src, dst)
            else:
                # Single file
                shutil.copy2(data_dir, os.path.join(abs_data, os.path.basename(data_dir)))

            # Build data info string for prompts
            data_files = []
            for root, dirs, files in os.walk(abs_data):
                for f in files:
                    if not f.startswith(".") and "__pycache__" not in root:
                        rel = os.path.relpath(os.path.join(root, f), abs_data)
                        data_files.append(rel)
            if data_files:
                data_info = (
                    f"\nDATA FILES: Available at {abs_data}/\n"
                    f"Files: {', '.join(data_files)}\n"
                    f"Read these files first to understand the data structure before modeling.\n"
                )
                await _emit(self.event_queue, "info", f"Data files: {', '.join(data_files)}")

        modeling_agent = self.agents.get("modeling")
        programming_agent = self.agents.get("programming")

        if not modeling_agent or not programming_agent:
            raise ValueError("SolveXFlow requires 'modeling' and 'programming' agents")

        logger.info(f"=== SolveX Started ===")
        logger.info(f"Max iterations: {self.max_iterations}")
        await _emit(self.event_queue, "status", "SolveX: Mathematical Modeling System Started")
        await _emit(self.event_queue, "info", f"Max loop iterations: {self.max_iterations}")
        await _emit(self.event_queue, "info", f"Workspace: {WORKSPACE}/")
        start_time = time.time()

        satisfied = False

        # === Phase 1: Modeling ↔ Programming Loop ===
        await _emit(self.event_queue, "status", f"Phase 1: Modeling ↔ Programming Loop")
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"\n{'='*50}")
            logger.info(f"=== Iteration {iteration}/{self.max_iterations} ===")
            logger.info(f"{'='*50}\n")
            await _emit(self.event_queue, "info", f"\n  --- Iteration {iteration}/{self.max_iterations} ---")

            # --- Modeling Agent ---
            await _emit(self.event_queue, "step", f"[Iteration {iteration}] ModelingAgent: Analyzing problem & designing model...")
            logger.info(f"--- [ModelingAgent] Starting ---")
            if iteration == 1:
                modeling_prompt = (
                    f"PROBLEM:\n{input_text}\n\n"
                    f"{data_info}"
                    f"Analyze the problem, search for relevant methods if needed, "
                    f"and write your modeling plan to {abs_modeling}/plan.md"
                )
            else:
                modeling_prompt = (
                    f"PROBLEM:\n{input_text}\n\n"
                    f"{data_info}"
                    f"The previous plan is at {abs_modeling}/plan.md\n"
                    f"Programming feedback is at {abs_programming}/results_summary.md\n\n"
                    f"Read the feedback, revise the plan, and update {abs_modeling}/plan.md"
                )

            modeling_agent.state = AgentState.IDLE
            modeling_agent.current_step = 0
            modeling_agent.memory = Memory()
            await modeling_agent.run(modeling_prompt)
            logger.info(f"--- [ModelingAgent] Done ---\n")
            await _emit(self.event_queue, "done", f"ModelingAgent: Plan written to {DIR_MODELING}/plan.md")

            # --- Programming Agent ---
            await _emit(self.event_queue, "step", f"[Iteration {iteration}] ProgrammingAgent: Implementing solution...")
            logger.info(f"--- [ProgrammingAgent] Starting ---")
            programming_prompt = (
                f"PROBLEM:\n{input_text}\n\n"
                f"{data_info}"
                f"Modeling plan is at {abs_modeling}/plan.md\n"
                f"Read it, implement the solution, and save code to {abs_programming}/\n"
                f"Write results summary to {abs_programming}/results_summary.md"
            )

            programming_agent.state = AgentState.IDLE
            programming_agent.current_step = 0
            programming_agent.memory = Memory()
            prog_output = await programming_agent.run(programming_prompt)
            logger.info(f"--- [ProgrammingAgent] Done ---\n")
            await _emit(self.event_queue, "done", f"ProgrammingAgent: Code saved to {DIR_PROGRAMMING}/")

            # --- Check verification ---
            all_output = prog_output
            for msg in programming_agent.memory.messages:
                if msg.content:
                    all_output += "\n" + msg.content

            # Fallback: generate results_summary.md if ProgrammingAgent didn't create it
            summary_path = os.path.join(abs_programming, "results_summary.md")
            if not os.path.exists(summary_path):
                # Extract key output lines as summary
                summary_lines = ["# Results Summary (auto-generated)\n"]
                for msg in programming_agent.memory.messages:
                    if msg.content and msg.role == "tool":
                        content = msg.content[:2000]
                        summary_lines.append(f"\n## Tool Output\n```\n{content}\n```\n")
                    elif msg.content and msg.role == "assistant":
                        content = msg.content[:1000]
                        if content.strip():
                            summary_lines.append(f"\n{content}\n")
                with open(summary_path, "w") as f:
                    f.write("\n".join(summary_lines))
                logger.info(f"Auto-generated results_summary.md (agent didn't create it)")

            if "VERIFICATION_RESULT: SATISFIED" in all_output:
                satisfied = True
                logger.info(f"=== Iteration {iteration}: Verified! ===")
                await _emit(self.event_queue, "done", f"Verification PASSED after {iteration} iteration(s)")
                break
            else:
                logger.info(f"=== Iteration {iteration}: Needs revision ===")
                await _emit(self.event_queue, "warn", "Verification not passed, revising...")

        # === Phase 2: Final modeling plan ===
        await _emit(self.event_queue, "step", "ModelingAgent: Writing final consolidated plan...")
        logger.info(f"--- [ModelingAgent] Writing final plan ---")
        from app.prompt.modeling import FINAL_PLAN_PROMPT

        final_prompt = (
            f"PROBLEM:\n{input_text}\n\n"
            f"The loop has converged after {iteration} iteration(s).\n"
            f"Your plan is at {abs_modeling}/plan.md\n"
            f"Results summary is at {abs_programming}/results_summary.md\n\n"
            f"Read both files, then write a clean final plan to {abs_modeling}/final_plan.md"
        )

        modeling_agent.state = AgentState.IDLE
        modeling_agent.current_step = 0
        modeling_agent.memory = Memory()
        await modeling_agent.run(final_prompt)
        logger.info(f"--- [ModelingAgent] Final plan written ---\n")
        await _emit(self.event_queue, "done", f"Final plan saved to {DIR_MODELING}/final_plan.md")

        # === Build result summary ===
        if satisfied:
            result = f"Modeling-Programming loop completed ({iteration} iteration(s))\n"
        else:
            result = f"Max iterations ({self.max_iterations}) reached, using current best result\n"

        # === Phase 3a: Visualization ===
        await _emit(self.event_queue, "status", "Phase 2: Visualization")
        visualization_agent = self.agents.get("visualization")
        if visualization_agent:
            await _emit(self.event_queue, "step", "VisualizationAgent: Creating figures with matplotlib...")
            logger.info(f"\n--- [VisualizationAgent] Starting ---")
            viz_prompt = (
                f"PROBLEM:\n{input_text}\n\n"
                f"{data_info}"
                f"Modeling plan: {abs_modeling}/final_plan.md\n"
                f"Programming results: {abs_programming}/\n"
                f"Create publication-quality figures and save to {abs_figures}/\n"
                f"Write a figures catalog to {abs_figures}/figures_catalog.md"
            )
            visualization_agent.state = AgentState.IDLE
            visualization_agent.current_step = 0
            visualization_agent.memory = Memory()
            await visualization_agent.run(viz_prompt)
            logger.info(f"--- [VisualizationAgent] Done ---\n")
            await _emit(self.event_queue, "done", f"Figures saved to {DIR_FIGURES}/")

            # Fallback: auto-generate figures_catalog.md if agent didn't create it
            catalog_path = os.path.join(abs_figures, "figures_catalog.md")
            if not os.path.exists(catalog_path):
                figures = [
                    f for f in os.listdir(abs_figures)
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".svg", ".pdf"))
                ]
                if figures:
                    lines = ["# Figures Catalog\n"]
                    for i, fig in enumerate(figures, 1):
                        lines.append(f"## Figure {i}: {fig}\n")
                        lines.append(f"![{fig}](./{fig})\n")
                        lines.append(f"Description: Auto-cataloged figure.\n\n")
                    with open(catalog_path, "w") as f:
                        f.write("\n".join(lines))
                    logger.info(f"Auto-generated figures_catalog.md ({len(figures)} figures)")
        else:
            logger.warning("No visualization agent provided, skipping Phase 3a")

        # === Phase 3b: Writing ===
        await _emit(self.event_queue, "status", "Phase 3: Paper Writing")
        writing_agent = self.agents.get("writing")
        if writing_agent:
            await _emit(self.event_queue, "step", "WritingAgent: Composing LaTeX paper...")
            logger.info(f"\n--- [WritingAgent] Starting ---")

            # Pre-read key files to embed in prompt (avoids agent wasting steps reading)
            def _read_file(path: str) -> str:
                if os.path.exists(path):
                    with open(path, "r") as f:
                        return f.read()
                return f"[File not found: {path}]"

            final_plan_content = _read_file(os.path.join(abs_modeling, "final_plan.md"))
            figures_catalog_content = _read_file(os.path.join(abs_figures, "figures_catalog.md"))
            abs_paper_path = os.path.join(abs_paper, "main.tex")

            write_prompt = (
                f"PROBLEM:\n{input_text}\n\n"
                f"=== FINAL MODELING PLAN ===\n{final_plan_content}\n\n"
                f"=== FIGURES CATALOG ===\n{figures_catalog_content}\n\n"
                f"Write the complete LaTeX paper to {abs_paper_path}\n"
                f"Use \\includegraphics{{'../03_figures/filename.png'}} for each figure.\n"
                f"Write the ENTIRE paper in one str_replace_editor create call, then call terminate."
            )
            writing_agent.state = AgentState.IDLE
            writing_agent.current_step = 0
            writing_agent.memory = Memory()
            await writing_agent.run(write_prompt)
            logger.info(f"--- [WritingAgent] Done ---\n")

            # Fallback: if agent wrote to /tmp instead of workspace, move it
            if not os.path.exists(abs_paper_path) and os.path.exists("/tmp/main.tex"):
                os.makedirs(os.path.dirname(abs_paper_path), exist_ok=True)
                shutil.move("/tmp/main.tex", abs_paper_path)
                logger.info(f"Moved paper from /tmp to {abs_paper_path}")

            await _emit(self.event_queue, "done", f"Paper saved to {DIR_PAPER}/main.tex")
        else:
            logger.warning("No writing agent provided, skipping Phase 3b")

        # === Build result summary ===
        result += (
            f"\nFiles produced:\n"
            f"  Plan: {DIR_MODELING}/plan.md\n"
            f"  Final plan: {DIR_MODELING}/final_plan.md\n"
            f"  Code: {DIR_PROGRAMMING}/\n"
            f"  Results: {DIR_PROGRAMMING}/results_summary.md\n"
            f"  Figures: {DIR_FIGURES}/\n"
            f"  Paper: {DIR_PAPER}/main.tex\n"
        )

        logger.info(f"=== SolveX Completed ===")
        elapsed = time.time() - start_time
        await _emit(self.event_queue, "status", f"SolveX Completed in {elapsed:.1f}s")
        await _emit(self.event_queue, "info", "Output files:")
        await _emit(self.event_queue, "info", f"  {DIR_MODELING}/final_plan.md")
        await _emit(self.event_queue, "info", f"  {DIR_PROGRAMMING}/")
        await _emit(self.event_queue, "info", f"  {DIR_FIGURES}/")
        await _emit(self.event_queue, "info", f"  {DIR_PAPER}/main.tex")
        return result
