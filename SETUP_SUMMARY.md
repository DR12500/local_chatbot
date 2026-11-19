# Setup summary

I've built the setup in `local_chatbot/`, but I didn't install Ollama or download any models. That means installing software and downloading 15–60 GB, so it's one command for you to run (below). The chat app itself has only been tested against a fake Ollama, not a real model yet.

> **Update:** `scripts\setup.ps1` now installs Ollama and downloads the medium-tier models to `G:\ai-models\ollama-models` (the default `-ModelsDir`).

## How it works

Browser → `app/server.py` → Ollama → your RX 9070 XT. Each step only talks to your own computer.

- **[app/server.py](app/server.py)** is a small web server using only Python's standard library (no extra packages). It:
  - only accepts connections from this computer;
  - refuses to forward your chats to an Ollama running on another computer;
  - blocks Ollama's "cloud" models, which would run on Ollama's servers instead of your GPU;
  - never logs your prompts.
- **[app/static/](app/static/)** is the chat page. It shows answers as they're typed, keeps your chats only in your browser, and has settings for the system prompt, context size and temperature. It also shows live speed and how much of the context window you've used. A browser security rule stops the page from loading anything from the internet.
- **[scripts/](scripts/)** has `setup.ps1` (installs Ollama, keeps it reachable only from this PC, downloads models), `start.ps1`, and `pull-models.ps1` (model download by size level).
- **[app/bench.py](app/bench.py)** measures the real speed of each model on your machine.

The tests passed for: refusing a remote server, filtering cloud models, streaming, blocking access to files outside the app folder, the security rule, and the "Ollama is down" error. All four PowerShell scripts parse without errors.

## To get it running

```powershell
cd G:\projects\local_chatbot
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Tier medium
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

After that, run `ollama ps` while a model is loaded. It should say "100% GPU". If it doesn't, the README's troubleshooting section covers the AMD/Vulkan fallback.

## Steps
1. Install a program that runs models locally (Ollama).
2. Pick a model size that fits in your 16 GB of graphics memory, including room for the conversation.
3. Download a compressed (4-bit) version of the model. This is the only step that needs the internet.
4. Run the model server so only this PC can reach it.
5. Connect a chat page to it. The model has no memory of its own, so the page resends the whole conversation each turn.
6. Check privacy and tune the settings.
7. Optionally, later: let it answer questions about your own documents.

## Estimates for your PC (16 GB graphics card)

| Level | Example models | Graphics memory | Speed (estimated) | Quality |
|---|---|---|---|---|
| Small 3–4B | qwen3:4b | 3–5 GB | 120–160 tokens/s | Basic; often gets facts wrong |
| **Medium 8–14B** | qwen3:8b / 14b, gemma3:12b | 6–11 GB | 40–85 tokens/s | **A decent chatbot** |
| Large 20–24B | gpt-oss:20b, mistral-small3.2 | 14–16 GB | 25–120 tokens/s | Best that fits on your card |

**Tokens for a decent chatbot:**
- A 10-turn chat uses about 5–10k tokens, so 8k of context is enough for normal use. 16–32k is better for long chats or pasted documents.
- Context costs graphics memory: about 0.15 GB per 1k tokens on a medium model.
- German text needs about 1.3–1.5× more tokens than English.
- The only running cost is electricity, about €0.50 per million generated tokens.

The speed figures come from a formula based on memory bandwidth, and AMD cards on Windows may come in 10–30% lower. `python app\bench.py` gives your real numbers. [README.md](README.md) has the full reasoning and a privacy checklist, including an optional firewall rule that cuts Ollama off from the internet entirely.
