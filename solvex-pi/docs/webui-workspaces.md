# Workspace WebUI

SolveX uses the actual `@earendil-works/pi-web-ui@0.75.3` package. One problem is
one workspace: the user creates or selects a workspace, uploads a problem document
and its datasets, then starts modeling as many times as needed. Each start creates
an independent runtime. No chat message or prompt editor is needed.

## Run

From `solvex-pi/`, with Node >=22.19 and pnpm 10:

```bash
pnpm install
npm run build:web
npm run cli -- serve --port 8000
```

Open http://127.0.0.1:8000. Configure at least one model provider credential in
the WebUI model settings before starting a run. The CLI and the server always
use the real model runtime; no demonstration switch is exposed.

Rebuild after changing frontend source. A server without a frontend build
shows build instructions instead of silently serving the old UI. For frontend
development run the API server and `npm run dev:web` in separate terminals;
Vite proxies `/api` to port 8000.

## Workflow

1. Create/select a workspace in the sidebar. Upload a PDF, DOCX, Markdown or
   TXT problem and any data attachments, together or in successive uploads.
2. If multiple documents are present, use the file's radio button to select
   the main problem. Every run snapshots all current inputs at startup.
3. Select a stage/task to see its own Pi transcript. Inspect figures and text
   artifacts, download a ZIP, stop the **selected** run, or return to a saved
   run after reload. The run list shows each run's status and runtime summary.

Uploads retain their original bytes. PDF/DOCX text extraction uses Pi's
`loadAttachment` in the browser; its PDF worker is bundled locally. Scanned
PDFs with no extractable text require OCR before upload. Files are at most
50 MB each, at most 30 per upload. Existing names are never overwritten.
Archives and spreadsheets can be data attachments; they are not main problems.

## One problem, many runtimes

Managed workspaces live in `~/.solvex/workspaces/`; `--session-dir /path/sessions`
selects `/path/workspaces` as the corresponding workspace root. The workspace
selector lists these managed directories; it does not grant the browser
arbitrary access to local filesystem paths.

```
workspaces/{workspaceId}/
├── workspace.json        name, input manifest, selected main problem
├── inputs/               original uploaded bytes
└── runs/{runId}/         one directory per run
    ├── runtime.json      effective config snapshot + input manifest
    ├── events.jsonl      that run's event log (SSE replay source)
    ├── .solvex-meta.json status / created_at / workspaceId
    └── 00_problem/ data/ 01_modeling/ 02_programming/ 04_paper/
```

A run owns its directory, `EventBus`, `AbortController`, stage snapshot,
artifact tree and ZIP. Runs in the same workspace may execute **in parallel**;
starting, stopping, downloading or replaying one run never touches another.
Inputs are copied into the run at startup, so later uploads do not rewrite
previous runs. The workspace ID is recorded in run metadata. Interrupted runs
are marked failed on server restart, retaining their inputs and artifacts.

`runtime.json` is written once at startup. It contains the effective
`defaults` / `byPhase` / `scopedModels` / `concurrency` / `strict` /
`persistThinking`, the overrides that were applied, and the input manifest.
It never contains API keys, credentials or endpoint definitions. To start a
run with different settings without changing the global configuration:

```bash
curl -X POST http://127.0.0.1:8000/api/workspaces/$WS_ID/runs \
  -H 'content-type: application/json' \
  -d '{"runtime":{"concurrency":1,"strict":true,
       "defaults":{"provider":"openai","model":"gpt-5","thinkingLevel":"high"}}}'
```

Unknown override fields, invalid thinking levels and credential-like values
are dropped by `sanitizeOverrides()`. Global model settings are still edited
in the WebUI settings dialog; they only affect runs started afterwards.

### API

| Endpoint | Purpose |
| --- | --- |
| `POST /api/workspaces/:id/runs` | Start a new run; `POST /api/workspaces/:id/run` is a compatible alias |
| `GET /api/workspaces/:id/runs` | All runs of a problem, newest first, with runtime summaries |
| `GET /api/workspaces/:id/runs/:runId` | Run detail + full snapshot; other workspaces' runs return 404 |
| `GET /api/runs/:id` / `GET /api/runs/:id/runtime` | Look up a run / its snapshot by runId |
| `GET /api/sessions`, `POST /api/run` | Legacy flat layout, still writable for CLI-style runs |
| `GET/PUT /api/mcp`, `POST /api/mcp/refresh` | MCP server config, connection status and discovered tools |
| `GET /api/mcp/presets`, `POST /api/mcp/presets/:id` | Built-in search server presets and one-click enable |

### MCP search capability

With `~/.solvex/mcp.json` (or `--mcp-config`) the runtime connects to MCP servers
at startup, calls `tools/list`, and registers only the tools the server actually
returns. They appear in the P1 prompt's discovered tool list, in the session's
`tools` allowlist and in `customTools` — the same set of names, so an unavailable
server can never leave a ghost tool behind. Configure which roles see them and
which tools are exposed with `roles` / `tools`. Credentials in `env` / `headers`
must be `$VAR` references; plaintext keys are rejected. See
[ADR-0012](adr/0012-mcp-search-capability.md).

`GET /api/events/:id`, `/api/stages/:id`, `/api/artifacts/:id`,
`/api/download/:id`, `/api/stream/:id` and `/api/abort/:id` all take a runId
and are scoped to that single run. Legacy `~/.solvex/sessions/{id}` runs are
indexed read-only alongside the new layout; they are neither moved nor deleted.

## Upstream reuse

- Package and upstream source:
  [Pi WebUI v0.75.3](https://github.com/earendil-works/pi/tree/v0.75.3/packages/web-ui)
  (MIT, Mario Zechner).
- Directly imported: `MessageList`, `loadAttachment`, and Pi's `app.css`.
- `MessageList` renders the upstream `AssistantMessage`, `ThinkingBlock`,
  `ToolMessage`, Markdown and code components, including tool input/results.
- The small Lit workspace shell replaces Pi's chat composer. No CSS trick hides
  a live chat input, and no browser Agent executes tools or calls providers.
- `src/client/transcript.ts` maps existing SolveX SSE events into Pi message
  objects. Tasks are isolated, turns are retained, final messages override
  partials, and calls/results are paired by ID. Thinking omitted from disk
  logs is shown as a placeholder on replay.
- `src/client/runs.ts` holds the pure run-list view model (runtime labels,
  merge-on-poll, start/stop eligibility) so the multi-runtime UI is unit tested
  without a DOM.
- Pi's published UI version is pinned separately from the server coding SDK
  (`1.5.0`). The backend remains the existing four-stage SolveX flow.

Model settings use the existing server catalog and configuration APIs.
Default and per-phase model selection, thinking level, concurrency and strict
quality gates are available. Runtime API keys reach the same Pi runtime used
by the pipeline and are not persisted. Custom OpenAI-compatible endpoints
accept environment variable key references, then refresh the running catalog.

## Validation

```bash
npm run check
npm run build:web
```

Tests cover file-only runs, original PDF bytes + extracted text, workspace
persistence, main-document selection, duplicate/path rejection, parallel
independent runtimes (distinct directories, distinct configs, isolated abort),
runtime snapshots, run ownership across workspaces, legacy flat sessions,
interrupted-run recovery, transcript turns/task isolation/tool pairing,
credential and endpoint runtime wiring, image previews and inert HTML previews.
CLI tests resolve paths relative to the repository and support all Node
versions allowed by `engines.node`.
