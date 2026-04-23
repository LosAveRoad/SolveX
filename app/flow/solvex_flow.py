import os
import re
import time
from pathlib import Path
from typing import Union

from app.agent.base import BaseAgent
from app.flow.base import BaseFlow
from app.logger import logger
from app.prompt.modeling import REVIEW_PROMPT
from app.schema import AgentState, Memory
from app.workspace import DIR_DATA, DIR_MODELING, DIR_PAPER, DIR_PROGRAMMING


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


def _read_file(path) -> str:
    p = Path(path)
    return p.read_text() if p.exists() else f"[File not found: {path}]"


def _parse_models(master_plan: str) -> list[str]:
    """Extract model section headers from master plan."""
    matches = re.findall(r'## (Model \d+)', master_plan)
    if matches:
        return matches
    return ["Model 1"]


def _extract_model_section(master_plan: str, model_name: str) -> str:
    """Extract a single model's section from the master plan."""
    pattern = rf'(## {re.escape(model_name)}:.*?)(?=\n## (?:Model \d+|Integration)|\Z)'
    match = re.search(pattern, master_plan, re.DOTALL)
    if match:
        return match.group(1).strip()
    return master_plan


def _validate_model_output(model_name: str, model_dir: Path) -> list[str]:
    """Check basic output quality. Returns list of issues found."""
    issues = []

    # Check results_summary exists and is meaningful
    summary = model_dir / "results_summary.md"
    if not summary.exists():
        issues.append("No results_summary.md file")
    elif summary.stat().st_size < 100:
        issues.append("results_summary.md is nearly empty")
    else:
        text = summary.read_text()
        if "<think/>" in text:
            issues.append("results_summary.md contains raw think tags (auto-generated?)")
        if "auto-generated" in text.lower() and "⚠" not in text:
            issues.append("results_summary appears auto-generated without validation")

    # Check code files exist
    py_files = list(model_dir.glob("*.py"))
    if not py_files:
        issues.append("No Python code files generated")

    # Check CSV data for common issues
    for csv_file in model_dir.glob("*.csv"):
        try:
            import pandas as pd
            df = pd.read_csv(csv_file)
            for col in df.select_dtypes(include="number").columns:
                if col.lower() == "probability":
                    if df[col].sum() > 50 and len(df) > 10:
                        issues.append(
                            f"{csv_file.name}: Probability sum = {df[col].sum():.0f} "
                            f"(historical: ~5-6 first medals per Olympics)"
                        )
                    if (df[col] > 0.95).sum() > len(df) * 0.3:
                        issues.append(
                            f"{csv_file.name}: {(df[col] > 0.95).sum()}/{len(df)} "
                            f"probabilities > 0.95 (likely uncalibrated)"
                        )
        except Exception:
            pass  # CSV reading is best-effort

    # Check figures
    fig_dir = model_dir / "figures"
    if fig_dir.exists():
        figs = list(fig_dir.glob("*.png"))
        if not figs:
            issues.append("No figures generated")
    else:
        issues.append("No figures/ directory")

    return issues


class SolveXFlow(BaseFlow):
    """SolveX multi-model mathematical modeling workflow."""

    max_iterations: int = 3
    event_queue: object = None

    def __init__(self, agents, max_iterations: int = 3, **data):
        data["max_iterations"] = max_iterations
        super().__init__(agents, **data)

    async def execute(
        self,
        input_text: str,
        workspace: str = None,
        resume_from: int = 0,
        skip_to_writing: bool = False,
    ) -> str:
        ws = Path(workspace) if workspace else Path.cwd() / "workspace"
        ws = ws.resolve()

        abs_modeling = ws / DIR_MODELING
        abs_programming = ws / DIR_PROGRAMMING
        abs_paper = ws / DIR_PAPER
        abs_data = ws / DIR_DATA

        for d in [abs_modeling, abs_programming, abs_paper]:
            d.mkdir(parents=True, exist_ok=True)

        # Build data info string
        data_info = ""
        if abs_data.exists():
            data_files = [
                os.path.relpath(os.path.join(root, f), abs_data)
                for root, dirs, files in os.walk(abs_data)
                for f in files
                if not f.startswith(".") and "__pycache__" not in root
            ]
            if data_files:
                data_info = (
                    f"\nDATA FILES: Available at {abs_data}/\n"
                    f"Files: {', '.join(data_files)}\n"
                    f"Read these files first to understand the data structure before modeling.\n"
                )
                await _emit(self.event_queue, "info", f"Data files: {', '.join(data_files)}")

        modeling_agent = self.agents.get("modeling")
        programming_agent = self.agents.get("programming")
        writing_agent = self.agents.get("writing")

        if not modeling_agent or not programming_agent:
            raise ValueError("SolveXFlow requires 'modeling' and 'programming' agents")

        logger.info(f"=== SolveX Multi-Model Started ===")
        logger.info(f"Max iterations per model: {self.max_iterations}")
        logger.info(f"Workspace: {ws}")
        await _emit(self.event_queue, "status", "SolveX: Multi-Model Pipeline Started")
        await _emit(self.event_queue, "info", f"Workspace: {ws}")
        start_time = time.time()

        # ===================================================================
        # Phase 1: Master Plan (skip if resuming or skip_to_writing)
        # ===================================================================
        master_plan_path = abs_modeling / "master_plan.md"

        if resume_from > 0 or skip_to_writing:
            if not master_plan_path.exists():
                raise FileNotFoundError(f"Cannot resume: master plan not found at {master_plan_path}")
            await _emit(self.event_queue, "done", f"Using existing Master Plan")
        else:
            await _emit(self.event_queue, "status", "Phase 1: Creating Master Plan")
            await _emit(self.event_queue, "step", "ModelingAgent: Creating multi-model Master Plan...")

            modeling_prompt = (
                f"PROBLEM:\n{input_text}\n\n"
                f"{data_info}"
                f"Analyze the problem, search for relevant methods, and write a multi-model "
                f"Master Plan to {master_plan_path}\n"
                f"Decide how many specialized models are needed. Each model gets its own "
                f"'## Model N: Name' section with full math formulation and solution strategy."
            )

            modeling_agent.state = AgentState.IDLE
            modeling_agent.current_step = 0
            modeling_agent.memory = Memory()
            await modeling_agent.run(modeling_prompt)

            if not master_plan_path.exists():
                await _emit(self.event_queue, "warn", "Master Plan not saved, retrying...")
                modeling_agent.state = AgentState.IDLE
                modeling_agent.current_step = 0
                modeling_agent.memory = Memory()
                retry_prompt = (
                    f"URGENT: Write a multi-model Master Plan NOW to {master_plan_path}\n\n"
                    f"PROBLEM:\n{input_text}\n\n"
                    f"{data_info}"
                    f"Write the plan immediately with '## Model N:' sections."
                )
                await modeling_agent.run(retry_prompt)

            if not master_plan_path.exists():
                raise FileNotFoundError(f"ModelingAgent failed to create {master_plan_path} after 2 attempts")

            await _emit(self.event_queue, "done", f"Master Plan saved to {DIR_MODELING}/master_plan.md")

        # Parse models
        master_plan_content = _read_file(master_plan_path)
        models = _parse_models(master_plan_content)
        if not models:
            models = ["Model 1"]

        await _emit(self.event_queue, "info", f"Master Plan contains {len(models)} model(s): {', '.join(models)}")

        # ===================================================================
        # Phase 2: Implement + Review (skip if skip_to_writing)
        # ===================================================================
        if skip_to_writing:
            await _emit(self.event_queue, "status", "SKIPPING Phase 2: Going directly to Writing")
        else:
            await _emit(self.event_queue, "status", f"Phase 2: Implementing {len(models)} Model(s)")

            for i, model_name in enumerate(models, 1):
                if resume_from > 0 and i < resume_from:
                    continue

                model_dir_name = model_name.lower().replace(" ", "_")
                abs_model_dir = abs_programming / model_dir_name
                abs_model_dir.mkdir(parents=True, exist_ok=True)
                (abs_model_dir / "figures").mkdir(exist_ok=True)

                await _emit(self.event_queue, "step", f"[{i}/{len(models)}] {model_name}: Implementing...")
                model_plan_section = _extract_model_section(master_plan_content, model_name)

                # --- Programming Agent ---
                programming_prompt = (
                    f"PROBLEM:\n{input_text}\n\n"
                    f"{data_info}"
                    f"=== YOUR TASK: Implement {model_name} ===\n\n"
                    f"MODEL PLAN:\n{model_plan_section}\n\n"
                    f"Save ALL outputs to:\n"
                    f"  - Code files: {abs_model_dir}/\n"
                    f"  - Figures: {abs_model_dir}/figures/\n"
                    f"  - Results summary: {abs_model_dir}/results_summary.md\n"
                )

                satisfied = False
                for attempt in range(2):
                    programming_agent.state = AgentState.IDLE
                    programming_agent.current_step = 0
                    programming_agent.memory = Memory()
                    prog_output = await programming_agent.run(programming_prompt)
                    await _emit(self.event_queue, "done", f"{model_name}: Code saved")

                    summary_path = abs_model_dir / "results_summary.md"
                    if not summary_path.exists():
                        auto_lines = [
                            f"# {model_name} Results Summary (auto-generated)\n\n",
                            "## Status\n⚠ Agent did not write results_summary.md\n\n",
                        ]
                        # Extract last tool output as "results"
                        for msg in reversed(programming_agent.memory.messages):
                            if msg.content and msg.role == "tool":
                                content = msg.content
                                # Strip think tags
                                if "<think/>" in content:
                                    content = content.split("<think/>", 1)[-1]
                                # Try to extract observation field
                                if "'observation':" in content:
                                    obs_match = re.search(r"'observation':\s*['\"](.+?)['\"]", content, re.DOTALL)
                                    if obs_match:
                                        auto_lines.append("## Key Output\n```\n" + obs_match.group(1)[:3000] + "\n```\n")
                                break
                        auto_lines.append("\n## Sanity Checks\n⚠ NOT PERFORMED — agent did not validate\n")
                        auto_lines.append("\n## Figures\n⚠ None generated\n")
                        summary_path.write_text("".join(auto_lines))

                    all_output = prog_output or ""
                    for msg in programming_agent.memory.messages:
                        if msg.content:
                            all_output += "\n" + msg.content

                    if "VERIFICATION_RESULT: SATISFIED" in all_output:
                        satisfied = True
                        break

                    if attempt == 0 and "VERIFICATION_RESULT: NEEDS_REVISION" in all_output:
                        prev_summary = _read_file(summary_path)
                        programming_prompt = (
                            f"PROBLEM:\n{input_text}\n\n"
                            f"{data_info}"
                            f"=== Re-implement {model_name} (REVISION) ===\n\n"
                            f"MODEL PLAN:\n{model_plan_section}\n\n"
                            f"PREVIOUS RESULTS:\n{prev_summary}\n\n"
                            f"Fix and save to {abs_model_dir}/\n"
                        )
                    else:
                        break

                # Validate output quality
                validation = _validate_model_output(model_name, abs_model_dir)
                if validation:
                    await _emit(self.event_queue, "warn", f"{model_name} validation issues: {'; '.join(validation)}")
                else:
                    await _emit(self.event_queue, "done", f"{model_name}: Output validation passed")

                # --- Modeling Agent reviews ---
                await _emit(self.event_queue, "step", f"[{i}/{len(models)}] {model_name}: Reviewing...")
                results_content = _read_file(summary_path)
                review_path = abs_modeling / f"{model_dir_name}_review.md"

                review_prompt = REVIEW_PROMPT.format(
                    model_name=model_name,
                    problem=input_text,
                    model_plan=model_plan_section,
                    results=results_content,
                    review_path=review_path,
                )

                # Protect master plan from accidental overwrite during review
                master_plan_snapshot = master_plan_path.read_text() if master_plan_path.exists() else None

                modeling_agent.state = AgentState.IDLE
                modeling_agent.current_step = 0
                modeling_agent.memory = Memory()
                await modeling_agent.run(review_prompt)

                # Restore master plan if overwritten
                if master_plan_snapshot and master_plan_path.exists():
                    current_plan = master_plan_path.read_text()
                    if current_plan != master_plan_snapshot:
                        master_plan_path.write_text(master_plan_snapshot)
                        logger.warning(f"Restored master_plan.md after {model_name} review (was modified)")

                # Check review — trigger fix if needed
                review_content = _read_file(review_path)
                if "VERIFICATION_RESULT: NEEDS_REVISION" in review_content:
                    fix_section = review_content
                    if "## Fix Instructions:" in review_content:
                        fix_section = review_content[review_content.index("## Fix Instructions:"):]
                    elif "## Issues Found:" in review_content:
                        fix_section = review_content[review_content.index("## Issues Found:"):]

                    fix_prompt = (
                        f"PROBLEM:\n{input_text}\n\n"
                        f"{data_info}"
                        f"=== Fix {model_name} (TARGETED REVISION) ===\n\n"
                        f"PREVIOUS CODE LOCATION: {abs_model_dir}/\n\n"
                        f"=== FIX INSTRUCTIONS ===\n{fix_section}\n\n"
                        f"Fix ONLY the issues above. Save to {abs_model_dir}/\n"
                    )
                    programming_agent.state = AgentState.IDLE
                    programming_agent.current_step = 0
                    programming_agent.memory = Memory()
                    await programming_agent.run(fix_prompt)
                    await _emit(self.event_queue, "done", f"{model_name}: Revision applied")

                await _emit(self.event_queue, "done", f"{model_name}: Review complete")

        # ===================================================================
        # Phase 3: Aggregate results
        # ===================================================================
        await _emit(self.event_queue, "status", "Phase 3: Aggregating Results")

        all_summary_path = abs_programming / "all_results_summary.md"
        summary_lines = ["# All Models Results Summary\n\n"]
        summary_lines.append(f"Total models implemented: {len(models)}\n\n")

        for model_name in models:
            model_dir_name = model_name.lower().replace(" ", "_")
            summary_lines.append(f"## {model_name}\n\n")
            summary_lines.append(_read_file(abs_programming / model_dir_name / "results_summary.md"))
            summary_lines.append("\n\n---\n\n")

            fig_dir = abs_programming / model_dir_name / "figures"
            if fig_dir.exists():
                figures = [f for f in os.listdir(fig_dir) if f.lower().endswith((".png", ".jpg", ".jpeg", ".svg", ".pdf"))]
                if figures:
                    summary_lines.append(f"### Figures\n")
                    for fig in figures:
                        summary_lines.append(f"- {model_dir_name}/figures/{fig}\n")
                    summary_lines.append("\n")

        all_summary_path.write_text("".join(summary_lines))
        await _emit(self.event_queue, "done", f"Aggregated results saved")

        # ===================================================================
        # Phase 4: Writing
        # ===================================================================
        await _emit(self.event_queue, "status", "Phase 4: Paper Writing")
        if writing_agent:
            await _emit(self.event_queue, "step", "WritingAgent: Composing LaTeX paper...")

            master_plan_content = _read_file(master_plan_path)
            all_results_content = _read_file(all_summary_path)

            figure_info_parts = []
            for model_name in models:
                model_dir_name = model_name.lower().replace(" ", "_")
                fig_dir = abs_programming / model_dir_name / "figures"
                if fig_dir.exists():
                    figures = [f for f in os.listdir(fig_dir) if f.lower().endswith((".png", ".jpg", ".jpeg", ".svg", ".pdf"))]
                    if figures:
                        figure_info_parts.append(f"{model_name} figures (use ../02_programming/{model_dir_name}/figures/):")
                        for fig in figures:
                            figure_info_parts.append(f"  - {fig}")

            figure_info = "\n".join(figure_info_parts) if figure_info_parts else "No figures generated."

            abs_paper_path = abs_paper / "main.tex"

            write_prompt = (
                f"PROBLEM:\n{input_text}\n\n"
                f"=== MASTER PLAN ===\n{master_plan_content}\n\n"
                f"=== ALL RESULTS (USE THESE EXACT NUMBERS — DO NOT FABRICATE) ===\n{all_results_content}\n\n"
                f"=== AVAILABLE FIGURES (INSERT ALL OF THEM) ===\n{figure_info}\n\n"
                f"Write the complete LaTeX paper to {abs_paper_path}\n"
                f"Target: 20-30 pages. Use multiple str_replace_editor calls if needed.\n"
                f"First call: create the file with preamble + abstract + introduction + first model section.\n"
                f"Then: use str_replace to append remaining sections.\n\n"
                f"FIGURE PATHS: Use relative path from 04_paper/:\n"
                f"  \\includegraphics[width=0.8\\textwidth]{{../02_programming/model_N/figures/figure_name.png}}\n"
                f"  IMPORTANT: NO single quotes inside the path. Just plain path.\n\n"
                f"CRITICAL:\n"
                f"- Use ONLY the numbers from ALL RESULTS above. Do NOT invent predictions or parameters.\n"
                f"- If a result says PARTIALLY SATISFIED or has issues, report that honestly.\n"
                f"- Insert EVERY figure listed in AVAILABLE FIGURES — do not skip any.\n"
                f"- Each model section should have: formulation, implementation, actual results, figures.\n\n"
                f"WRITE ORDER: Write the body sections FIRST, then write the abstract LAST.\n"
                f"The abstract must match the conclusions. Do NOT write the abstract first.\n"
            )

            writing_agent.state = AgentState.IDLE
            writing_agent.current_step = 0
            writing_agent.memory = Memory()
            await writing_agent.run(write_prompt)

            if not abs_paper_path.exists() and os.path.exists("/tmp/main.tex"):
                import shutil
                shutil.move("/tmp/main.tex", str(abs_paper_path))

            await _emit(self.event_queue, "done", f"Paper saved to {DIR_PAPER}/main.tex")

        # ===================================================================
        # Summary
        # ===================================================================
        result = f"Pipeline completed: {len(models)} model(s)\n"
        for model_name in models:
            model_dir_name = model_name.lower().replace(" ", "_")
            result += f"  {model_name}: {DIR_PROGRAMMING}/{model_dir_name}/\n"
        result += f"  Paper: {DIR_PAPER}/main.tex\n"

        elapsed = time.time() - start_time
        await _emit(self.event_queue, "status", f"SolveX Completed in {elapsed:.1f}s")
        return result
