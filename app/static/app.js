// Local chatbot UI. Talks only to the local server (enforced by CSP).
// Chats are stored in this browser's localStorage, on this machine only.
"use strict";

const $ = (id) => document.getElementById(id);
const STORE_KEY = "local-chatbot-v1";
const DEFAULT_SYSTEM = "You are a helpful, concise assistant. If you are unsure about a fact, say so.";

let state = load();
let controller = null; // AbortController for the running generation

function load() {
  try {
    const s = JSON.parse(localStorage.getItem(STORE_KEY));
    if (s && Array.isArray(s.chats)) return s;
  } catch (_) { /* ignore */ }
  return { chats: [], activeId: null, settings: { system: DEFAULT_SYSTEM, numCtx: 8192, temperature: 0.7, model: "" } };
}
function save() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (_) { /* storage full/blocked */ }
}
const activeChat = () => state.chats.find((c) => c.id === state.activeId);

// ---------- tiny, safe markdown (escape first, then format) ----------
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function renderMarkdown(text) {
  const parts = text.split(/```/);
  return parts.map((part, i) => {
    if (i % 2 === 1) { // code block; first line may be a language tag
      const body = part.replace(/^[\w+-]*\n/, "");
      return "<pre><code>" + escapeHtml(body) + "</code></pre>";
    }
    return escapeHtml(part)
      .split(/\n{2,}/)
      .filter((p) => p.trim())
      .map((p) => "<p>" + p
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\n/g, "<br>") + "</p>")
      .join("");
  }).join("");
}

// ---------- rendering ----------
function renderChatList() {
  const list = $("chat-list");
  list.innerHTML = "";
  for (const chat of state.chats) {
    const li = document.createElement("li");
    li.className = chat.id === state.activeId ? "active" : "";
    const title = document.createElement("span");
    title.textContent = chat.title || "New chat";
    const del = document.createElement("button");
    del.textContent = "×";
    del.title = "Delete chat";
    del.onclick = (e) => {
      e.stopPropagation();
      state.chats = state.chats.filter((c) => c.id !== chat.id);
      if (state.activeId === chat.id) state.activeId = state.chats[0] ? state.chats[0].id : null;
      save(); renderAll();
    };
    li.append(title, del);
    li.onclick = () => { state.activeId = chat.id; save(); renderAll(); };
    list.appendChild(li);
  }
}

function messageEl(msg) {
  const div = document.createElement("div");
  div.className = "msg " + msg.role;
  fillMessage(div, msg);
  return div;
}
function fillMessage(div, msg) {
  let html = "";
  if (msg.thinking) html += '<details class="thinking"><summary>Thinking…</summary>' + escapeHtml(msg.thinking) + "</details>";
  html += msg.role === "user" ? "<p>" + escapeHtml(msg.content).replace(/\n/g, "<br>") + "</p>" : renderMarkdown(msg.content || "");
  div.innerHTML = html;
}

function renderMessages() {
  const box = $("messages");
  box.innerHTML = "";
  const chat = activeChat();
  if (!chat || !chat.messages.length) {
    box.innerHTML = '<div class="msg muted">Everything runs on this computer. Pick a model and start typing.</div>';
    return;
  }
  chat.messages.forEach((m) => box.appendChild(messageEl(m)));
  box.scrollTop = box.scrollHeight;
}

function renderAll() { renderChatList(); renderMessages(); }

// ---------- models / health ----------
async function loadModels() {
  const sel = $("model");
  try {
    const res = await fetch("/api/models");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    sel.innerHTML = "";
    if (!data.models.length) {
      sel.innerHTML = "<option>No models: run scripts/pull-models.ps1</option>";
      return;
    }
    for (const m of data.models) {
      const o = document.createElement("option");
      o.value = m.name;
      o.textContent = `${m.name}  (${m.params || "?"}, ${m.size_gb} GB)`;
      sel.appendChild(o);
    }
    // A model chosen in the launcher (?model=...) wins over the last-used one.
    const params = new URLSearchParams(location.search);
    const wanted = params.get("model");
    if (wanted && data.models.some((m) => m.name === wanted)) state.settings.model = wanted;
    if (params.has("model")) history.replaceState(null, "", "/");
    if (data.models.some((m) => m.name === state.settings.model)) sel.value = state.settings.model;
    state.settings.model = sel.value;
    $("status").textContent = "● Ollama connected (local)";
  } catch (e) {
    sel.innerHTML = "<option>Ollama not reachable</option>";
    $("status").textContent = "○ " + e.message;
  }
}

// ---------- chatting ----------
async function send(text) {
  let chat = activeChat();
  if (!chat) {
    chat = { id: String(Date.now()), title: "", messages: [] };
    state.chats.unshift(chat);
    state.activeId = chat.id;
  }
  if (!chat.title) chat.title = text.slice(0, 40);
  chat.messages.push({ role: "user", content: text });
  const reply = { role: "assistant", content: "", thinking: "" };
  chat.messages.push(reply);
  save(); renderAll();

  const box = $("messages");
  const replyDiv = box.lastElementChild;
  const history = chat.messages.slice(0, -1).map(({ role, content }) => ({ role, content }));
  const messages = [{ role: "system", content: state.settings.system }, ...history];

  controller = new AbortController();
  setBusy(true);
  $("stats").textContent = "loading model…";
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        model: state.settings.model,
        messages,
        options: { num_ctx: Number(state.settings.numCtx), temperature: Number(state.settings.temperature) },
      }),
    });
    if (!res.ok) throw new Error((await res.json()).error || res.statusText);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const chunk = JSON.parse(line);
        if (chunk.error) throw new Error(chunk.error);
        if (chunk.message) {
          reply.content += chunk.message.content || "";
          reply.thinking += chunk.message.thinking || "";
        }
        if (chunk.done) showStats(chunk);
      }
      fillMessage(replyDiv, reply);
      box.scrollTop = box.scrollHeight;
    }
  } catch (e) {
    if (e.name !== "AbortError") {
      replyDiv.classList.add("error");
      reply.content += (reply.content ? "\n\n" : "") + "Error: " + e.message;
      fillMessage(replyDiv, reply);
    }
    $("stats").textContent = "";
  } finally {
    if (!reply.thinking) delete reply.thinking;
    controller = null;
    setBusy(false);
    save();
  }
}

function showStats(c) {
  // Ollama reports durations in nanoseconds.
  const tps = c.eval_count && c.eval_duration ? (c.eval_count / (c.eval_duration / 1e9)).toFixed(1) : "?";
  const ctx = (c.prompt_eval_count || 0) + (c.eval_count || 0);
  $("stats").textContent = `${tps} tokens/s · ${c.eval_count || 0} generated · ${ctx} / ${state.settings.numCtx} context tokens used`;
}

function setBusy(busy) {
  $("send").textContent = busy ? "Stop" : "Send";
  $("send").classList.toggle("primary", !busy);
}

// ---------- wiring ----------
$("composer").onsubmit = (e) => {
  e.preventDefault();
  if (controller) { controller.abort(); return; }
  const text = $("input").value.trim();
  if (!text) return;
  $("input").value = "";
  send(text);
};
$("input").onkeydown = (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("composer").requestSubmit(); }
};
$("new-chat").onclick = () => { state.activeId = null; save(); renderAll(); $("input").focus(); };
$("model").onchange = (e) => { state.settings.model = e.target.value; save(); };
$("system-prompt").value = state.settings.system;
$("system-prompt").onchange = (e) => { state.settings.system = e.target.value; save(); };
$("num-ctx").value = String(state.settings.numCtx);
$("num-ctx").onchange = (e) => { state.settings.numCtx = Number(e.target.value); save(); };
$("temperature").value = state.settings.temperature;
$("temp-val").textContent = state.settings.temperature;
$("temperature").oninput = (e) => {
  state.settings.temperature = Number(e.target.value);
  $("temp-val").textContent = e.target.value;
  save();
};

renderAll();
loadModels();
