# local_chatbot

Private, fully local chatbot: Ollama (model runtime) + a zero-dependency Python web UI. See README.md for setup, model tiers and token estimates.

## Hard rules (privacy is the point of this project)
- Nothing may send prompts or chats off the machine. No external CDNs, fonts, analytics or API calls in the UI; keep the CSP in `app/server.py` strict.
- Servers bind to `127.0.0.1` only. `server.py` must keep refusing non-loopback Ollama hosts and Ollama cloud models.
- Never log prompt or response contents.

## Layout
- `app/server.py`: stdlib HTTP server (Python 3.8+): static files + `/api/models`, `/api/chat` (NDJSON streaming proxy), `/api/health`
- `app/static/`: vanilla JS/CSS UI; chats live in browser localStorage
- `app/bench.py`: tokens/s benchmark against local Ollama
- `scripts/`: PowerShell 5.1 scripts: `setup.ps1` (install + pull), `start.ps1`, `start-ollama.ps1`, `pull-models.ps1` (model tiers)

## Commands
- Run: `powershell -ExecutionPolicy Bypass -File scripts\start.ps1`
- Check: `python -m py_compile app/server.py app/bench.py`; with Ollama running: `python app/bench.py`
- No third-party Python packages. Keep it that way unless the user agrees.
