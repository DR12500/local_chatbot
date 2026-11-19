# Local Chatbot

A private ChatGPT-style chatbot that runs entirely on this PC. Prompts, answers and chat history never leave the machine.

```
Browser (127.0.0.1:8765) ──► app/server.py (127.0.0.1 only) ──► Ollama (127.0.0.1:11434) ──► GPU (RX 9070 XT)
   chats in localStorage       stdlib Python, no dependencies      runs the model weights
```

| Part | What it does | Why it's private |
|---|---|---|
| **Ollama** | Loads open-weight models (GGUF, 4-bit) and runs them on the GPU | Listens on `127.0.0.1` only; models are files on your disk |
| **app/server.py** | Serves the UI and forwards requests to Ollama | Binds to localhost, refuses non-local Ollama hosts, blocks Ollama *cloud* models |
| **app/static/** | Chat UI (streaming, history, settings, tokens/s display) | Strict CSP: the page can only talk to its own server. No CDNs, fonts or analytics |

## Quick start

```powershell
cd G:\projects\local_chatbot
# one-time: installs Ollama (winget), downloads the "medium" models (~23 GB)
# to G:\ai-models\ollama-models (change with -ModelsDir)
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Tier medium

# every time:
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

Then check that the model runs on the GPU:

```powershell
ollama ps            # PROCESSOR column should say "100% GPU"
python app\bench.py  # real tokens/s on your machine
```

## The steps, explained

1. **Install a local inference runtime.** Ollama wraps `llama.cpp`, which does the actual math on your GPU. On Windows it supports AMD Radeon cards (ROCm, plus a Vulkan backend in newer versions).
2. **Pick a model size that fits your VRAM.** The model weights *and* the conversation memory (KV cache) must fit in the GPU's 16 GB. Anything that spills into system RAM runs 5–20× slower. See the tiers below.
3. **Download quantized weights.** Models are stored in 4-bit ("Q4") form: about 0.6 GB per billion parameters, with only a small quality loss. This is the only step that needs the internet.
4. **Run the model server locally.** Ollama serves an HTTP API on `127.0.0.1:11434`. Nothing outside your PC can reach it.
5. **Put a chat UI in front of it.** The UI keeps the conversation and sends the *whole* history every turn, because the model itself is stateless. That's why the context window (in tokens) matters.
6. **Verify privacy** (see below), then **tune**: system prompt, context size, temperature, model choice.
7. *(Optional, later)* **Chat with your documents (RAG):** a local embedding model indexes your files, and relevant chunks are added to the prompt.

## Model tiers for this PC

Hardware: **RX 9070 XT, 16 GB VRAM, ~640 GB/s**, Ryzen 7 7800X3D, 32 GB RAM.

Generation speed is limited by memory bandwidth: every generated token reads all the active weights once. Rough rule: **tokens/s ≈ 0.6 × 640 GB/s ÷ model size in GB**. The figures below are estimates; AMD on Windows can come in 10–30% lower, so run `app\bench.py` to get your real numbers. People read at roughly 5–8 tokens/s, so anything above about 20 tokens/s feels instant.

| Tier | Models (`ollama pull …`) | Download | VRAM incl. 8k context | Est. speed | Quality |
|---|---|---|---|---|---|
| **Small** (3–4B) | `qwen3:4b`, `gemma3:4b` | 2.5–3.3 GB | 3–5 GB | 120–160 tok/s | Fine for rewriting, summaries, simple Q&A. Gets facts wrong often; weak at reasoning |
| **Medium** (8–14B) ⭐ | `qwen3:8b`, `gemma3:12b`, `qwen3:14b` | 5–9 GB | 6–11 GB | 40–85 tok/s | **The "decent chatbot" level.** Good writing, coding help, German/English, solid reasoning (qwen3 can "think"). About GPT-3.5 level or better |
| **Large** (20–24B) | `gpt-oss:20b`, `mistral-small3.2:24b` | 14–15 GB | 14–16 GB | gpt-oss: 80–120 tok/s (MoE), mistral: 25–35 tok/s | Best that fits in 16 GB. Clearly better reasoning and coding. Mistral only fits with about 4k context |
| **XL** (70B) | `llama3.3:70b` | 43 GB | Doesn't fit (spills to RAM) | 1–3 tok/s | Not practical here. Needs 48 GB+ of VRAM or a 64 GB+ unified-memory Mac |

**Recommendation:** start with `qwen3:14b` (all-round) and `gpt-oss:20b` (fast and smart). Use `qwen3:4b` when you want speed. `gpt-oss:20b` is a Mixture-of-Experts model: 21B parameters in total, but only about 3.6B active per token, so it is both larger *and* faster than the 14B models.

Model names are current as of 2025/26. Newer models of the same size appear regularly on <https://ollama.com/library>; pick by size, using the same VRAM math.

## How many tokens does a decent chatbot need?

A token is about ¾ of an English word. German needs about 1.3–1.5× more tokens for the same text.

| What | Tokens |
|---|---|
| System prompt | 50–300 |
| Your message | 20–300 |
| Answer | 200–800 (thinking models add 300–3000 hidden "reasoning" tokens, which are not kept in the history) |
| 10-turn conversation | about 5,000–10,000 in total |
| Pasting a 10-page document | about 6,000–8,000 |

**Context window (how much the bot "remembers"):**
- **4k**: short Q&A only. It forgets the start of the conversation fast.
- **8k**: the default here. Fine for normal chats.
- **16–32k**: long conversations and pasted documents. Costs extra VRAM.

**Context costs memory (the KV cache).** For an 8–14B model it's about **0.15 GB per 1,000 tokens**: 8k context ≈ 1.2 GB, 32k ≈ 5 GB. So `qwen3:14b` with 32k context (9.3 + 5 GB) still just fits. A 24B model with 32k does not. You can change the context size in the UI's settings, and the header shows how many context tokens a chat has used.

**Cost per token:** zero, apart from electricity. At about 400 W system draw and ~70 tok/s, 1 million generated tokens takes about 4 h ≈ 1.6 kWh ≈ **€0.50**. Typical personal use (20–50k tokens a day) costs cents per month.

## Impact on your PC

Ollama has three states. The model size mostly decides how much of the graphics card is taken up, and for how long.

| State | When | GPU | CPU / RAM | Power (approx.) |
|---|---|---|---|---|
| **Generating** | While an answer is being written | ~100% busy, fans spin up | 1 core busy; ~1–2 GB RAM | +250–300 W (card at full load) |
| **Loaded, idle** | Up to 5 min after the last message | 0% busy, but **the model stays in VRAM** | ~0% | +10–30 W (memory clocks stay up) |
| **Dormant** | Model unloaded, Ollama running in the tray | Nothing used | ~0% CPU, ~50 MB RAM | ≈ 0 W extra |

How each tier affects the PC:

| Tier | VRAM taken while loaded | 500-token answer takes | Gaming or other GPU work at the same time |
|---|---|---|---|
| Small (4B) | 3–5 GB | ~3–4 s | Fine. Most games still have 11+ GB left |
| Medium (8–14B) | 6–11 GB | ~6–12 s | Light games OK; heavy games will stutter or push the model onto the CPU |
| Large (20–24B) | 14–16 GB (whole card) | ~5–20 s | Not at the same time. Unload the model first |

Notes:
- **Peak power is about the same for every size.** The card runs flat out either way. Bigger models just run longer per answer, so they use more energy per answer.
- **Loading a model** from the NVMe SSD (G:) takes about 2–5 s. Reloads after that come from the Windows file cache and are faster.
- **Spilling over is what makes the PC sluggish.** If model plus context exceeds 16 GB, the rest runs on the CPU. All 8 cores go to 100%, the PC slows down, and generation drops to a few tokens/s. `ollama ps` shows this as e.g. "30%/70% CPU/GPU".
- **Freeing VRAM immediately** (e.g. before gaming): `ollama stop <model>`. Or make models unload right after each answer by setting the user env var `OLLAMA_KEEP_ALIVE=0`. The trade-off is a 2–5 s load at the start of every answer.
- **Fully off:** quit Ollama from the tray, and turn off its autostart under Windows Settings → Apps → Startup.
- **Disk:** models live in `G:\ai-models\ollama-models` until you run `ollama rm <model>`. The medium tier is about 23 GB. The Ollama program itself is in `%LOCALAPPDATA%\Programs\Ollama`.

## Can RAM or the SSD act as extra VRAM?

Technically yes, but every step down is a lot slower. Generating each token means reading all the active weights once, so speed is set by the slowest memory the model sits in:

| Memory | Speed (approx.) | Model fully in it → speed for a 9 GB model (qwen3:14b) |
|---|---|---|
| VRAM (RX 9070 XT) | ~640 GB/s | ~40–48 tok/s |
| System RAM (DDR5, 32 GB) | ~60 GB/s | ~4–6 tok/s |
| NVMe SSD (Lexar NM790) | ~7 GB/s at best, much less for random reads | ~0.3–0.7 tok/s |

- **RAM spill-over** happens automatically when a model doesn't fit. A *little* is OK: a few GB over makes it maybe 1.5–3× slower. MoE models (`gpt-oss`, `qwen3-coder:30b`) handle it best, because only the active experts are read for each token.
- **SSD as memory** (when a model is bigger than VRAM + RAM, it gets read from disk over and over) is technically possible but unusable, at under 1 tok/s. **Not recommended.**
- **SSD wear isn't the problem.** Loading a model only *reads* the file, and reads hardly wear an SSD (the NM790 2 TB is rated for ~1,500 TB of writes). Only the Windows pagefile writes, and that only happens if the PC runs out of RAM entirely. Speed is the real reason not to do it.

**Better ways to get more context in 16 GB:**
- **Quantize the KV cache:** set the user env vars `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0`, then restart Ollama. Context then takes about half the VRAM, with almost no quality loss (`q4_0` takes a quarter, with a noticeable loss).
- Use a smaller model, or an MoE model, for long-context work.

## Coding agents: a separate domain

Chat and coding agents are related but have different requirements. A coding agent (Claude Code, Cline, Aider, …) reads files, runs commands and edits code in a loop. That needs:

1. **Reliable tool calling:** the model has to produce correctly formatted tool calls dozens of times in a row. Small models break the format or loop.
2. **Long context:** agents fill the context with files, diffs and command output. 32k tokens is a minimum and 64–128k is comfortable. Locally, every 1k tokens costs VRAM (see above), so long context forces you onto smaller models.
3. **Fast prompt processing:** every agent step re-reads the whole context. At an estimated ~1,000–3,000 tokens/s prompt processing, a 30k-token context means roughly 10–30 s *per step* before any output appears.
4. **Long-horizon reasoning:** planning across many files and recovering from mistakes. This is where model size matters most.

| Tier | Coding *assistant* (chat, explain, write a function) | Coding *agent* (multi-step edits in a repo) |
|---|---|---|
| Small (1.5–4B) | Good for **tab autocomplete** (`qwen2.5-coder:1.5b` / `3b`); weak at chat | Not usable |
| Medium (8–14B) | Good: `qwen2.5-coder:14b`, `qwen3:14b`. Solid for single files and explanations | Unreliable. Simple one-file tasks sometimes work; loses track on bigger ones |
| Large (20–30B) | Very good: `qwen3-coder:30b` (MoE; ~19 GB, so it partly spills but stays usable), `devstral:24b` (made for agents), `gpt-oss:20b` | **Usable for simple agent tasks** (scaffolding, small fixes, tests). Context limited to ~16–32k on 16 GB |
| Frontier cloud models | Excellent | Far ahead on multi-file, long tasks. But your code leaves the machine |

**Realistic expectation on this PC:** a local model is a good private coding *assistant* and autocomplete. As an autonomous agent it handles small, well-defined tasks, well below frontier cloud models. A good private setup is VS Code + **Continue** (chat + autocomplete), or **Aider** / **Cline** pointed at `http://127.0.0.1:11434`. Turn off each tool's telemetry (e.g. Continue: `"allowAnonymousTelemetry": false`) so code stays local.

## Privacy checklist

- [x] UI server binds to `127.0.0.1` and only forwards to a loopback Ollama
- [x] Ollama cloud models (`*-cloud`), which would run on Ollama's servers, are hidden and refused
- [x] No external scripts, fonts or trackers in the UI (enforced by Content-Security-Policy)
- [x] Chats are stored only in your browser's `localStorage` (delete one with × in the sidebar)
- [ ] In the Ollama tray app settings: **"Expose Ollama to the network" OFF**; turn **Airplane mode ON** if your version has it
- [ ] Check that only localhost is listening: `netstat -ano | findstr 11434` should show `127.0.0.1:11434`, not `0.0.0.0`
- [ ] *(Paranoid mode)* After downloading models, block Ollama's internet access (admin PowerShell). Remove the rule before pulling new models:
  ```powershell
  New-NetFirewallRule -DisplayName "Block Ollama outbound" -Direction Outbound -Action Block -Program "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
  Remove-NetFirewallRule -DisplayName "Block Ollama outbound"
  ```

The only network traffic Ollama itself makes is model downloads and its update check. Your prompts are never sent.

## Troubleshooting

- **`ollama ps` shows CPU instead of GPU:** update the AMD Adrenalin driver and Ollama. On newer Ollama versions you can try the Vulkan backend: set the user env var `OLLAMA_VULKAN=1` and restart Ollama. Alternative runtime: LM Studio (also local, also uses llama.cpp).
- **Slow, or "100% GPU" not shown for big models:** the model plus context doesn't fit in 16 GB. Lower the context in Settings or use a smaller model.
- **UI says "Ollama not reachable":** run `scripts\start-ollama.ps1`, or start the Ollama app from the Start menu.
