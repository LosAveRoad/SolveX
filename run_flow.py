import argparse
import asyncio
import time
from pathlib import Path

from app.agent.modeling import ModelingAgent
from app.agent.programming import ProgrammingAgent
from app.agent.writing import WritingAgent
from app.flow.flow_factory import FlowFactory, FlowType
from app.logger import logger
from app.workspace import prepare_workspace


async def run_flow(
    problem: str,
    data_dir: str = None,
    resume_session: str = None,
    resume_from: int = 0,
    skip_to_writing: bool = False,
):
    print("\033[1;36m")
    print("╔══════════════════════════════════════╗")
    print("║        SolveX - Math Modeling        ║")
    print("║   Paper → Model → Code → Figures    ║")
    print("╚══════════════════════════════════════╝")
    print("\033[0m")

    if resume_session:
        # Resume existing session
        ws = Path.home() / ".solvex" / "sessions" / resume_session
        if not ws.exists():
            print(f"\033[1;31mSession not found: {ws}\033[0m")
            return
        print(f"\033[1;33m  Resuming session: {resume_session} from model {resume_from}\033[0m")
        print(f"\033[1;36m  Workspace: {ws}\033[0m")
    else:
        # Prepare workspace — problem + data → ~/.solvex/sessions/{id}/
        ws = prepare_workspace(problem, data_dir=data_dir)
        print(f"\033[1;36m  Workspace: {ws}\033[0m")

    agents = {
        "modeling": ModelingAgent(),
        "programming": ProgrammingAgent(),
        "writing": WritingAgent(),
    }
    try:
        flow = FlowFactory.create_flow(
            flow_type=FlowType.SOLVEX,
            agents=agents,
            max_iterations=3,
        )
        logger.warning("Processing your request...")

        try:
            start_time = time.time()
            result = await asyncio.wait_for(
                flow.execute(problem, workspace=str(ws), resume_from=resume_from, skip_to_writing=skip_to_writing),
                timeout=7200,  # 2 hours for resume
            )
            elapsed_time = time.time() - start_time
            logger.info(f"Request processed in {elapsed_time:.2f} seconds")
            print(f"\n\033[1;32mTotal time: {elapsed_time:.1f}s\033[0m")
            print(f"\033[1;36mWorkspace: {ws}\033[0m")
            logger.info(result)
        except asyncio.TimeoutError:
            logger.error("Request processing timed out")
            print("\033[1;31mTimeout\033[0m")

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user.")
        print("\033[1;33mCancelled.\033[0m")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\033[1;31mError: {str(e)}\033[0m")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SolveX Mathematical Modeling")
    parser.add_argument("--problem", "-p", type=str, help="Problem text file (.md or .txt)")
    parser.add_argument("--data", "-d", type=str, help="Data directory or file path")
    parser.add_argument("--resume", "-r", type=str, help="Resume session ID (e.g. 0423-b8a2)")
    parser.add_argument("--from-model", type=int, default=0, help="Model number to resume from (1-based)")
    parser.add_argument("--skip-to-writing", "-w", action="store_true", help="Skip to writing phase only")
    args = parser.parse_args()

    if args.resume:
        if args.skip_to_writing:
            # Skip directly to writing phase
            problem_file = Path.home() / ".solvex" / "sessions" / args.resume / "00_problem" / "problem.md"
            problem_text = problem_file.read_text() if problem_file.exists() else ""
            asyncio.run(run_flow(problem_text, resume_session=args.resume, skip_to_writing=True))
        else:
            resume_from = args.from_model
            if resume_from < 1:
                # Auto-detect: find first model without results_summary.md
                ws = Path.home() / ".solvex" / "sessions" / args.resume
                prog_dir = ws / "02_programming"
                if prog_dir.exists():
                    for i in range(1, 10):
                        model_dir = prog_dir / f"model_{i}"
                        summary = model_dir / "results_summary.md"
                        if not model_dir.exists() or not summary.exists():
                            resume_from = i
                            break
                        content = summary.read_text().strip()
                        if len(content) < 50:  # Nearly empty = incomplete
                            resume_from = i
                            break
                if resume_from < 1:
                    resume_from = 1
            # Read problem from existing session
            problem_file = Path.home() / ".solvex" / "sessions" / args.resume / "00_problem" / "problem.md"
            problem_text = problem_file.read_text() if problem_file.exists() else ""
            asyncio.run(run_flow(problem_text, resume_session=args.resume, resume_from=resume_from))
    elif args.problem:
        with open(args.problem, "r") as f:
            problem_text = f.read()
        asyncio.run(run_flow(problem_text, data_dir=args.data))
    else:
        problem_text = input("\033[1;33mEnter math modeling problem: \033[0m")
        if problem_text.strip().isspace() or not problem_text:
            print("Empty problem, exiting.")
        else:
            asyncio.run(run_flow(problem_text, data_dir=args.data))
