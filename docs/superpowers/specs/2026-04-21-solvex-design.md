# SolveX Design Document

## Overview

SolveX is a Multi-Agent mathematical modeling system based on OpenManus. It automates the full pipeline: paper search → modeling → programming → visualization → paper writing.

## Architecture Decision

**Approach**: Minimal-invasive modification of OpenManus (Plan A)
- Keep: BaseAgent hierarchy, Tool framework, LLM abstraction, Memory, MCP, Config
- Remove: SWEAgent, Sandbox/Daytona, ComputerUse, A2A protocol, DataAnalysis
- Add: 4 specialized agents, loop-capable flow, math-specific tools

## Agent Design

### Phase 1: Modeling Agent + Programming Agent

| Agent | Role | Tools | Output |
|-------|------|-------|--------|
| ModelingAgent | Analyze problem, select approach, define model | PythonExecute, AskHuman | Structured modeling plan (model choice, variables, objective, constraints) |
| ProgrammingAgent | Implement model in Python, execute, verify | PythonExecute, StrReplaceEditor, AskHuman | Working code + results + satisfaction flag |

### Phase 2+: Additional Agents

| Agent | Role | Tools |
|-------|------|-------|
| PaperSearchAgent | Search ArXiv/journals for relevant papers | ArxivSearch (MCP), later BrowserUseTool |
| VisualizationAgent | Generate charts with Matplotlib | PythonExecute, ChartGenerator |
| WritingAgent | Write LaTeX paper | LaTeXWriter, StrReplaceEditor |

## Flow Design

### Loop Mechanism

```
PlanningFlow (restructured)
  ├─ Step 1: PaperSearchAgent (Phase 2)
  ├─ Step 2: Loop {
  │     ModelingAgent → ProgrammingAgent
  │     → verify result
  │     → satisfied? break : continue
  │   }
  ├─ Step 3: VisualizationAgent (Phase 3)
  └─ Step 4: WritingAgent (Phase 3)
```

**Loop exit conditions**:
1. ProgrammingAgent marks output as `SATISFIED` (execution success + results reasonable)
2. Max iterations reached (configurable, default 5) → use current best result

### Implementation in PlanningFlow

Add `StepType.LOOP` to planning steps. Flow layer controls the loop:
- Calls ModelingAgent with previous feedback (if any)
- Passes modeling plan to ProgrammingAgent
- Checks ProgrammingAgent output for satisfaction flag
- Loops or exits accordingly

## Tech Stack

| Component | Choice |
|-----------|--------|
| Language | Python (from OpenManus) |
| LLM | Config-based per-agent (OpenManus LLM abstraction) |
| Visualization | Matplotlib |
| Paper output | LaTeX (.tex) via Jinja2 templates |
| Paper search | MCP + ArXiv API (Phase 2), Browser-use (Phase 4) |
| RAG | For modeling agent (Phase 5) |

## Test Set

Two layers:
- `tests/simple/`: Basic problems (linear programming, regression) for flow validation
- `tests/competition/`: Real competition problems for end-to-end testing

## Development Phases

### Phase 1 (Current)
1. Copy OpenManus to SolveX
2. Create ModelingAgent + ProgrammingAgent with prompts
3. Restructure PlanningFlow with loop support
4. Test with simple problems, iterate on prompts

### Phase 2
- PaperSearchAgent via MCP + ArXiv
- Integration into flow

### Phase 3
- VisualizationAgent (Matplotlib)
- WritingAgent (LaTeX)
- End-to-end testing

### Phase 4
- Browser-use for journal paper search

### Phase 5
- RAG for mainstream model lookup

## Project Structure

```
SolveX/
├── app/
│   ├── agent/
│   │   ├── base.py              # Keep
│   │   ├── toolcall.py          # Keep
│   │   ├── paper_search.py      # New (Phase 2)
│   │   ├── modeling.py          # New
│   │   ├── programming.py       # New
│   │   ├── visualization.py     # New (Phase 3)
│   │   └── writing.py           # New (Phase 3)
│   ├── tool/
│   │   ├── base.py              # Keep
│   │   ├── python_execute.py    # Keep
│   │   ├── str_replace_editor.py# Keep
│   │   ├── ask_human.py         # Keep
│   │   ├── terminate.py         # Keep
│   │   ├── planning.py          # Keep
│   │   ├── arxiv_search.py      # New (Phase 2)
│   │   ├── latex_writer.py      # New (Phase 3)
│   │   └── chart_generator.py   # New (Phase 3)
│   ├── flow/
│   │   ├── base.py              # Keep
│   │   └── planning.py          # Restructure: add LoopStep
│   ├── mcp/                     # Keep
│   ├── llm/                     # Keep
│   ├── config/                  # Keep
│   ├── prompt/                  # Rewrite: math modeling prompts
│   └── utils/                   # Keep
├── config/
│   └── config.toml              # Modified: SolveX config
├── tests/
│   ├── simple/                  # Simple test problems
│   └── competition/             # Competition problems
├── workspace/                   # Runtime working directory
└── run_flow.py                  # Main entry point
```
