# SolveX

Multi-Agent mathematical modeling system based on [OpenManus](https://github.com/mannaandpoem/OpenManus).

## Overview

SolveX automates the full mathematical modeling pipeline for competition-style problems:

```
Problem → [Modeling ↔ Programming Loop] → Visualization → LaTeX Paper → Output
```

**Agents:**
- **ModelingAgent** — Analyzes problems, searches literature (ArXiv, web), designs innovative models
- **ProgrammingAgent** — Implements models in Python, verifies results
- **VisualizationAgent** — Creates publication-quality figures with matplotlib
- **WritingAgent** — Composes complete LaTeX papers

**Key features:**
- Iterative modeling-programming loop with automatic verification
- Literature search via ArXiv + web MCP tools
- Memory compaction for long sessions
- Data file support (CSV, XLSX, ZIP)
- FastAPI web UI with SSE streaming + ZIP download
- 20-minute end-to-end pipeline for competition problems

## Quick Start

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure LLM (edit config/config.toml)
cp config/config.example.toml config/config.toml

# CLI mode
python run_flow.py --problem tests/competition/2025_C/problem.txt --data tests/competition/2025_C/data/

# Web mode
python api.py  # open http://localhost:8000
```

## Architecture

```
app/
├── agent/           # Agent implementations (modeling, programming, visualization, writing)
├── flow/            # Workflow orchestration (SolveXFlow)
├── prompt/          # System prompts for each agent
├── service/         # Memory compaction service
├── tool/            # Tools (python_execute, str_replace_editor, MCP, etc.)
├── llm.py           # LLM abstraction (supports DeepSeek, OpenAI, Bedrock, Azure, Ollama)
└── schema.py        # Data models
config/
├── config.toml      # LLM configuration
└── mcp.json         # MCP tool servers
static/              # Web frontend (HTML/CSS/JS)
api.py               # FastAPI server
run_flow.py          # CLI runner
```

## Workspace Output

Each run produces:
```
workspace/
├── 01_modeling/     # plan.md, final_plan.md
├── 02_programming/  # solution.py, predictions, results
├── 03_figures/      # PNG figures, figures_catalog.md
└── 04_paper/        # main.tex (complete LaTeX paper)
```

## License

MIT License — Based on [OpenManus](https://github.com/mannaandpoem/OpenManus).
