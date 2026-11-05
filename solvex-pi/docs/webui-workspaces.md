# Workspace WebUI

SolveX uses the actual `@earendil-works/pi-web-ui@0.75.3` package. The user
creates or selects a workspace, uploads a problem document and its datasets,
and clicks **开始建模**. No chat message or prompt editor is needed.

## Run

From `solvex-pi/`, with Node >=22.19 and pnpm 10:

```bash
pnpm install
npm run build:web
npm run cli -- serve --port 8000
```

Open http://127.0.0.1:8000. For an offline end-to-end demonstration:

```bash
npm run cli -- serve --fake --port 8000
```

Rebuild after changing frontend source. A server without a frontend build
shows build instructions instead of silently serving the old UI. For frontend
development run the API server and `npm run dev:web` in separate terminals;
Vite proxies `/api` to port 8000.

## Workflow

1. Create/select a workspace in the sidebar. Upload a PDF, DOCX, Markdown or
   TXT problem and any data attachments, together or in successive uploads.
2. If multiple documents are present, use the file's radio button to select
   the main problem. Start modeling; each run snapshots all current inputs.
3. Select a stage/task to see its own Pi transcript. Inspect figures and text
   artifacts, download a ZIP, stop a run, or return to a saved run after reload.

Uploads retain their original bytes. PDF/DOCX text extraction uses Pi's
`loadAttachment` in the browser; its PDF worker is bundled locally. Scanned
PDFs with no extractable text require OCR before upload. Files are at most
50 MB each, at most 30 per upload. Existing names are never overwritten.
Archives and spreadsheets can be data attachments; they are not main problems.

Managed workspaces live alongside the session root in `~/.solvex/workspaces/`.
`--session-dir /path/sessions` selects `/path/workspaces` as the corresponding
workspace root. The workspace selector lists these managed directories; it
does not grant the browser arbitrary access to local filesystem paths.
Each workspace stores inputs and its selected problem; sessions retain the
existing `00_problem`, `data`, `01_modeling`, `02_programming`, `04_paper` layout.
The workspace ID is recorded in session metadata. Interrupted runs are marked
failed on server restart, retaining their inputs and artifacts.

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
persistence, main-document selection, duplicate/path rejection, overlapping
starts, interrupted-run recovery, transcript turns/task isolation/tool pairing,
credential and endpoint runtime wiring, image previews and inert HTML previews.
CLI tests resolve paths relative to the repository and support all Node
versions allowed by `engines.node`.
