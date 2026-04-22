import argparse
import asyncio
import time

from app.agent.modeling import ModelingAgent
from app.agent.programming import ProgrammingAgent
from app.agent.visualization import VisualizationAgent
from app.agent.writing import WritingAgent
from app.flow.flow_factory import FlowFactory, FlowType
from app.logger import logger
from app.workspace import prepare_workspace


async def run_flow(problem: str, data_dir: str = None):
    print("\033[1;36m")
    print("╔══════════════════════════════════════╗")
    print("║        SolveX - Math Modeling        ║")
    print("║   Paper → Model → Code → Figures    ║")
    print("╚══════════════════════════════════════╝")
    print("\033[0m")

    # Prepare workspace — problem + data → ~/.solvex/sessions/{id}/
    ws = prepare_workspace(problem, data_dir=data_dir)
    print(f"\033[1;36m  Workspace: {ws}\033[0m")

    agents = {
        "modeling": ModelingAgent(),
        "programming": ProgrammingAgent(),
        "visualization": VisualizationAgent(),
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
                flow.execute(problem, workspace=str(ws)),
                timeout=3600,
            )
            elapsed_time = time.time() - start_time
            logger.info(f"Request processed in {elapsed_time:.2f} seconds")
            print(f"\n\033[1;32mTotal time: {elapsed_time:.1f}s\033[0m")
            print(f"\033[1;36mWorkspace: {ws}\033[0m")
            logger.info(result)
        except asyncio.TimeoutError:
            logger.error("Request processing timed out after 1 hour")
            print("\033[1;31mTimeout after 1 hour\033[0m")

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
    args = parser.parse_args()

    if args.problem:
        with open(args.problem, "r") as f:
            problem_text = f.read()
    else:
        problem_text = input("\033[1;33mEnter math modeling problem: \033[0m")

    if problem_text.strip().isspace() or not problem_text:
        print("Empty problem, exiting.")
    else:
        asyncio.run(run_flow(problem_text, data_dir=args.data))
