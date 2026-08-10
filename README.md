<div align="center">

<img src="assets/solvex-logo.png" alt="SolveX logo" width="520" />

# SolveX

### An AI-native workflow for mathematical modeling competitions

From problem statement to validated model, publication-ready figures, and a complete LaTeX paper.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

[![FastAPI](https://img.shields.io/badge/FastAPI-%20web%20API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

## Overview

SolveX is a multi-agent mathematical modeling system designed for competition-style problems. It coordinates specialized agents through an iterative modeling and programming loop, turning an unstructured problem into a reproducible, reviewable deliverable.

```text
Problem → Modeling ↔ Programming → Visualization → LaTeX Paper → Output
```

## What SolveX delivers

- **Modeling** — decomposes the problem, researches relevant methods, and proposes an actionable solution plan.
- **Programming** — implements the model in Python, runs experiments, and checks results.
- **Visualization** — produces publication-quality figures with a traceable figure catalog.
- **Writing** — assembles a complete LaTeX paper from the verified work.
- **Iteration** — keeps modeling and implementation in a feedback loop instead of treating them as one-shot steps.

Additional capabilities include ArXiv and web research, long-session memory compaction, CSV/XLSX/ZIP data inputs, and a FastAPI interface with streaming progress and ZIP export.

## Quick start

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure your model provider

```bash
cp config/config.example.toml config/config.toml
```

Edit `config/config.toml` with your provider, model, and credentials.

### 3. Run a problem

CLI mode:

```bash
python run_flow.py --problem tests/competition/2025_C/problem.txt --data tests/competition/2025_C/data/
```

Web mode:

```bash
python api.py
```

Then open <http://localhost:8000>.

## Architecture

```text
app/
├── agent/       # Modeling, programming, visualization, and writing agents
├── flow/        # SolveX workflow orchestration
├── prompt/      # Agent system prompts
├── service/     # Memory and session services
├── tool/        # Execution, editing, and research tools
├── llm.py       # Provider-agnostic LLM abstraction
└── schema.py    # Shared data models
config/          # LLM and MCP configuration
static/          # Web interface assets
api.py           # FastAPI entry point
run_flow.py      # CLI entry point
```

## Output layout

Each run is organized for inspection and reuse:

```text
workspace/
├── 01_modeling/     # Plans and final modeling decisions
├── 02_programming/  # Source code, predictions, and results
├── 03_figures/      # Figures and figure catalog
└── 04_paper/        # Complete LaTeX manuscript
```

## Design principles

1. **Reproducibility first** — preserve plans, code, data products, and figures together.
2. **Verification before narration** — written conclusions should follow executable results.
3. **Modular agents** — each stage can be inspected, improved, or replaced independently.
4. **Human reviewable** — intermediate artifacts remain available for debugging and critique.

## Contributing

Issues and pull requests are welcome. When contributing, please include a concise description of the change and, where relevant, a reproducible example or test.

## License

SolveX is released under the [MIT License](LICENSE). The project is inspired by and builds on concepts from [OpenManus](https://github.com/FoundationAgents/OpenManus).

