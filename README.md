<div align="center">

<img src="assets/solvex-logo.png" alt="SolveX logo" width="520" />

# SolveX

### An AI-native workflow for mathematical modeling competitions

From problem statement to validated model, publication-ready figures, and a complete LaTeX paper.

[![Node](https://img.shields.io/badge/Node-%3E%3D22.19-339933?logo=node.js&logoColor=white)](https://nodejs.org/) [![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/) [![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

## Overview

SolveX 2.0 is a TypeScript monorepo built on the Pi coding-agent SDK (`@earendil-works/pi-coding-agent@1.5.0`). It runs a four-stage mathematical modeling pipeline on a parallel DAG with structured quality gates, and streams every step into a live WebUI — turning an unstructured problem statement into a reproducible, reviewable deliverable.

```text
P1 Modeling → P2 Implementation (N parallel) → Barrier → P2 Review (N parallel) → Barrier → P3 Figures → P4 LaTeX Paper
```

## What SolveX delivers

- **Modeling** — decomposes the problem, researches relevant methods, and writes a master plan.
- **Programming** — implements each model, runs experiments, and produces structured results.
- **Review & quality gates** — structured `handoff.json` verdicts, with `--strict` blocking critical issues before writing.
- **Visualization** — publication-quality figures with a traceable figure catalog.
- **Writing** — assembles a complete LaTeX paper from verified results.
- **WebUI 2.0** — model configuration center, streamed thinking view, stage DAG timeline, and a live usage bar.

Runs are resumable, intermediate artifacts stay human-reviewable, and credentials never appear in API responses.

## Quick start

### 1. Requirements

| Item | Requirement |
| --- | --- |
| Node | **>= 22.19** (`.nvmrc` = 22.20.0) |
| pnpm | 10.x |
| Model credentials | At least one provider API key / OAuth — or use `--fake` for a full offline demo |

### 2. Install

```bash
cd solvex-pi
pnpm install
npm run check        # typecheck + full test suite
```

### 3. Run a problem

CLI mode:

```bash
npx tsx apps/cli/src/index.ts run -p problem.md -d data/ --concurrency 3
```

Web mode:

```bash
npx tsx apps/cli/src/index.ts serve --port 8000
```

Then open <http://127.0.0.1:8000/>. The web server binds to localhost only.

No credentials yet? Append `--fake` to either command for a complete run with a synthetic agent and Pi events.

### 4. Other commands

```bash
npx tsx apps/cli/src/index.ts run --resume <session_id> --from-model 2
npx tsx apps/cli/src/index.ts run --skip-to-writing -r <session_id>
npx tsx apps/cli/src/index.ts validate <session_id>
npx tsx apps/cli/src/index.ts inspect <session_id>
```

## Architecture

```text
solvex-pi/
├── apps/
│   ├── cli/                 # CLI entry point + Web server
│   └── web/                 # WebUI 2.0 backend and static frontend
├── packages/
│   ├── core/                # Zero Pi dependency: prompts, flow state machine,
│   │                        # parallel DAG, contracts, gates, events
│   └── pi-runtime/          # Only place importing the Pi SDK: agent runner,
│                            # event bridge, model runtime, tool extensions
├── test/                    # prompts / flow / gates / pi / web / cli / regression
└── docs/                    # design spec, ADRs, regression and benchmark reports
```

`@solvex/core` owns the pipeline; `@solvex/pi-runtime` adapts the SDK behind an `AgentRunner` port. Prompts live in a single source of truth at `packages/core/src/prompts/*.md`.

## Output layout

Sessions are stored under `~/.solvex/sessions/{id}/`:

```text
01_modeling/     # Master plan and modeling decisions
02_programming/  # Source code, predictions, handoff verdicts
03_figures/      # Figures and figure catalog
04_paper/        # Complete LaTeX manuscript
```

## Configuration

- **Models & credentials** — `solvex-pi/packages/pi-runtime/models.json`; secrets use `$VAR` / `${VAR}` environment references, never plaintext.
- **Runtime defaults** — `~/.solvex/config.json` (`defaults`, `byPhase`, `scopedModels`, `concurrency`, `strict`, `persistThinking`), editable from the WebUI.

## Testing

```bash
npm run check                 # tsc + vitest (218 passed / 1 skipped)
npx vitest run
PI_TEST_MODEL=<provider/id> npx vitest run test/pi/integration.test.ts
```

The single skipped test needs a real model credential.

## Documentation

| Document | Contents |
| --- | --- |
| [`solvex-pi/README.md`](solvex-pi/README.md) | Full 2.0 reference (CLI flags, WebUI 2.0, configuration) |
| [`solvex-pi/SolveX-Pi-Migration.md`](solvex-pi/SolveX-Pi-Migration.md) | Migration design spec v1.1 |
| [`solvex-pi/SolveX-Pi-Migration-Plan.md`](solvex-pi/SolveX-Pi-Migration-Plan.md) | Nine-phase implementation plan |
| [`solvex-pi/docs/MIGRATION-STATUS.md`](solvex-pi/docs/MIGRATION-STATUS.md) | Implementation status and Go/No-Go checklist |
| [`solvex-pi/docs/regression-report.md`](solvex-pi/docs/regression-report.md) | Conclusions for the 23 historical pipeline issues |
| [`solvex-pi/docs/webui-2.0.md`](solvex-pi/docs/webui-2.0.md) | WebUI 2.0 guide |
| [`solvex-pi/docs/benchmark.md`](solvex-pi/docs/benchmark.md) | Performance and cost baseline |
| [`solvex-pi/docs/adr/`](solvex-pi/docs/adr/) | Architecture decision records |

## Contributing

Issues and pull requests are welcome. When contributing, please include a concise description of the change and, where relevant, a reproducible example or test. Run `npm run check` from `solvex-pi/` before opening a PR.

## License

SolveX is released under the [MIT License](LICENSE).
