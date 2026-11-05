# Pi WebUI workspace implementation plan

Goal: Replace the handwritten SolveX screen with an application using the real
`@earendil-works/pi-web-ui@0.75.3` components and its document loader. No chat composer.
User flow: create/select a managed workspace, upload a problem document and data,
choose the main problem if needed, start modeling, inspect progress and artifacts.

Architecture: Keep Fastify, the server-side Pi runner, and four-stage pipeline.
Add persistent managed workspaces and reference their immutable uploads from runs.
Use official MessageList/ThinkingBlock/tool renderers through a typed event adapter;
use the upstream stylesheet and Lit for the small workspace application shell.
Pin the official published UI version independently of the backend coding SDK.

1. Workspace input API (test first): create/list/select, multipart uploads, main
   problem selection, start without text, run history, prevent overlapping starts.
   Text/Markdown decode on the server; PDF/DOCX use official browser extraction,
   with extracted text stored alongside originals. Reject empty/unsupported problem
   files, duplicate names and directory traversal. Keep legacy /api/run working.
2. Transcript adapter (test first): isolate parallel tasks, preserve all turns,
   authoritative final messages, pair calls/results, reconstruct streaming blocks,
   handle errors, usage and redacted thinking. Do not execute agents in the browser.
3. Frontend: Vite production bundle served by existing CLI serve; official CSS and
   message components. Workspace sidebar, file upload, progress/task selection,
   artifacts preview/download, model settings, cancellation, replay after reload.
4. Verify: full existing suite, typecheck, production build and browser fake-run
   through upload -> completion -> artifacts -> reload. Document usage and upstream.

Decisions: User's “继续” authorizes proceeding with the requested rebuild. A fresh
clone and feature branch isolate changes. Workspaces are managed server folders,
not browser filesystem handles; runs keep existing session IDs/API compatibility.
