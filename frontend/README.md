# Frontend

A single-file, dependency-free HTML/JS UI — deliberately minimal per the
brief ("do not spend excessive time on visual design"). It demonstrates:

- document upload + live status list
- RAG chat with grounded/ungrounded indicator and citation chips (filename,
  page, similarity score)
- an "Agentic AI" mode that shows the tool-call trace (which tool, what
  arguments, success/failure) alongside the final answer
- loading and error states for both upload and chat/agent requests

## Running it locally

```bash
# Terminal 1: the API
cd gcp-genai-platform
make dev            # serves FastAPI on http://localhost:8080

# Terminal 2: the frontend (any static file server works)
cd gcp-genai-platform/frontend
python3 -m http.server 3000
# open http://localhost:3000
```

`app/main.py`'s CORS config allows `http://localhost:3000` by default,
matching the command above. If you serve the frontend from a different
port, add it to `allow_origins` in `app/main.py`.

To point the UI at a different API URL (e.g. a deployed Cloud Run
service), set `window.API_BASE` before the script runs, e.g. by adding
`<script>window.API_BASE = "https://your-service.run.app";</script>`
above the main `<script>` tag.

## What this is not

This is not a production frontend — no build step, no framework, no
component library, no auth UI (there is no auth layer in the backend yet;
see `docs/SECURITY.md`). It exists to make the backend's capabilities
visible and demoable, not to be a polished product UI.
