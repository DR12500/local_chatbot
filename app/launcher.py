"""Model launcher: pick a local model, then open the chat with it.

    pythonw app/launcher.py        (or use the shortcut from scripts/create-shortcut.ps1)

Starts Ollama and the chat server if needed, can unload other models to free
VRAM, preloads the chosen model and opens the chat with it selected.
Standard library only (tkinter); talks only to 127.0.0.1.
"""
import http.client
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import quote

OLLAMA_PORT = 11434
UI_PORT = 8765
APP_DIR = Path(__file__).resolve().parent
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Short notes for known models. Speeds were measured on this PC (see README).
MODEL_INFO = {
    "qwen3:8b": ("Fastest. Thinks briefly before answering. Good for quick everyday questions.", "~95 tok/s"),
    "gemma3:12b": ("Answers directly, without a thinking step. Strong at writing and languages.", "~64 tok/s"),
    "qwen3:14b": ("Best reasoning and coding of the medium models. Thinks before answering.", "~57 tok/s"),
    "qwen3:4b": ("Small and very fast. Fine for simple tasks; makes more mistakes.", ""),
    "gemma3:4b": ("Small and very fast. Answers directly; makes more mistakes.", ""),
    "gpt-oss:20b": ("Large but fast (only part of it is active per token). Strong reasoning.", ""),
    "mistral-small3.2:24b": ("Largest that fits. Very good quality; needs a small context window.", ""),
}


# ---------------------------------------------------------------- local APIs
def request(port, method, path, body=None, timeout=5):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body=json.dumps(body) if body is not None else None,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        return json.loads(resp.read() or b"{}")
    finally:
        conn.close()


def is_up(port, path):
    try:
        request(port, "GET", path, timeout=2)
        return True
    except (OSError, ValueError):
        return False


def user_env(name):
    """Read a user env var from the registry, in case this process started before it was set."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def start_ollama():
    if is_up(OLLAMA_PORT, "/api/version"):
        return
    exe = shutil.which("ollama") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
    if not os.path.isfile(exe):
        raise RuntimeError("Ollama is not installed. Run scripts\\setup.ps1 first.")
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "127.0.0.1:%d" % OLLAMA_PORT
    models_dir = user_env("OLLAMA_MODELS")
    if models_dir:
        env["OLLAMA_MODELS"] = models_dir
    subprocess.Popen([exe, "serve"], env=env, creationflags=NO_WINDOW,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        time.sleep(0.5)
        if is_up(OLLAMA_PORT, "/api/version"):
            return
    raise RuntimeError("Ollama did not start within 15 s.")


def python_console_exe():
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        return str(exe.parent / "python.exe")
    return str(exe)


# ---------------------------------------------------------------- window
class Launcher:
    def __init__(self, root):
        self.root = root
        self.server = None  # chat server process started by this launcher
        self.models = []
        self.loaded = {}

        root.title("Local Chatbot – choose a model")
        root.geometry("680x400")
        root.minsize(560, 320)

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)

        cols = ("size", "speed", "status")
        self.tree = ttk.Treeview(frame, columns=cols, selectmode="browse", height=8)
        self.tree.heading("#0", text="Model")
        self.tree.heading("size", text="Size")
        self.tree.heading("speed", text="Speed")
        self.tree.heading("status", text="Status")
        self.tree.column("#0", width=200)
        self.tree.column("size", width=110, anchor="center")
        self.tree.column("speed", width=90, anchor="center")
        self.tree.column("status", width=200)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_info())
        self.tree.bind("<Double-1>", lambda e: self.open_chat())

        self.info = ttk.Label(frame, text="", wraplength=640, padding=(0, 8))
        self.info.pack(fill="x")

        self.unload_others = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="Unload other models first (frees graphics memory)",
                        variable=self.unload_others).pack(anchor="w")

        buttons = ttk.Frame(frame, padding=(0, 8, 0, 0))
        buttons.pack(fill="x")
        self.open_btn = ttk.Button(buttons, text="Open chat", command=self.open_chat)
        self.open_btn.pack(side="right")
        self.unload_one_btn = ttk.Button(buttons, text="Unload selected", command=self.unload_selected)
        self.unload_one_btn.pack(side="left")
        self.unload_btn = ttk.Button(buttons, text="Unload all models", command=self.unload_all)
        self.unload_btn.pack(side="left", padx=6)
        ttk.Button(buttons, text="Refresh", command=self.refresh).pack(side="left")
        self.closing = False

        self.status = ttk.Label(root, text="Starting…", relief="sunken", anchor="w", padding=(8, 2))
        self.status.pack(fill="x", side="bottom")

        root.bind("<Return>", lambda e: self.open_chat())
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.queue = queue.Queue()
        self.drain_queue()
        self.run_bg(self.startup)

    # -- threading helpers: network work off the UI thread, UI updates on it
    def run_bg(self, fn, *args):
        self.set_busy(True)

        def worker():
            try:
                fn(*args)
            except Exception as e:  # show any failure instead of dying silently
                self.ui(self.set_status, "Error: %s" % e)
            finally:
                self.ui(self.set_busy, False)
        threading.Thread(target=worker, daemon=True).start()

    def ui(self, fn, *args):
        # tkinter is not thread-safe: hand UI updates to the main thread via a queue.
        self.queue.put((fn, args))

    def drain_queue(self):
        while not self.queue.empty():
            fn, args = self.queue.get_nowait()
            try:
                fn(*args)
            except tk.TclError:
                return  # window is gone
        self.root.after(50, self.drain_queue)

    def set_status(self, text):
        self.status.config(text=text)

    def set_busy(self, busy):
        state = "disabled" if busy else "normal"
        for btn in (self.open_btn, self.unload_btn, self.unload_one_btn):
            btn.config(state=state)

    # -- data
    def startup(self):
        self.ui(self.set_status, "Starting Ollama…")
        start_ollama()
        self.fetch()

    def refresh(self):
        self.run_bg(self.fetch)

    def fetch(self):
        tags = request(OLLAMA_PORT, "GET", "/api/tags").get("models", [])
        ps = request(OLLAMA_PORT, "GET", "/api/ps").get("models", [])
        models = sorted((m for m in tags if "cloud" not in m["name"].lower()), key=lambda m: m.get("size", 0))
        loaded = {m["name"]: m.get("size_vram", 0) for m in ps}
        self.ui(self.populate, models, loaded)

    def populate(self, models, loaded):
        selected = self.selected()
        self.models, self.loaded = models, loaded
        self.tree.delete(*self.tree.get_children())
        for m in models:
            name = m["name"]
            params = (m.get("details") or {}).get("parameter_size", "")
            size = "%s · %.1f GB" % (params, m.get("size", 0) / 1e9)
            speed = MODEL_INFO.get(name, ("", ""))[1]
            status = "● loaded (%.1f GB VRAM)" % (loaded[name] / 1e9) if name in loaded else ""
            self.tree.insert("", "end", iid=name, text=name, values=(size, speed, status))
        if not models:
            self.set_status("No models installed. Run scripts\\pull-models.ps1")
            return
        pick = selected if selected in self.tree.get_children() else next(iter(loaded), models[0]["name"])
        if pick not in self.tree.get_children():
            pick = models[0]["name"]
        self.tree.selection_set(pick)
        self.tree.focus(pick)
        used = sum(loaded.values()) / 1e9
        self.set_status("%d models installed · %.1f GB of graphics memory in use by models" % (len(models), used))

    def selected(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def show_info(self):
        name = self.selected()
        if name:
            self.info.config(text=MODEL_INFO.get(name, ("Local model.", ""))[0])

    # -- actions
    def open_chat(self):
        name = self.selected()
        if name and str(self.open_btn["state"]) != "disabled":
            self.run_bg(self._open_chat, name, self.unload_others.get())

    def _open_chat(self, name, unload_others):
        if unload_others:
            for other in list(self.loaded):
                if other != name:
                    self.ui(self.set_status, "Unloading %s…" % other)
                    request(OLLAMA_PORT, "POST", "/api/generate", {"model": other, "keep_alive": 0}, timeout=30)
        self.ui(self.set_status, "Loading %s into graphics memory…" % name)
        # A request without a prompt just loads the model; keep it ready for 10 min.
        request(OLLAMA_PORT, "POST", "/api/generate", {"model": name, "keep_alive": "10m"}, timeout=180)
        self.ensure_chat_server()
        webbrowser.open("http://127.0.0.1:%d/?model=%s" % (UI_PORT, quote(name, safe="")))
        self.fetch()
        self.ui(self.set_status, "Chat opened with %s. Keep this window open while you chat." % name)

    def ensure_chat_server(self):
        if is_up(UI_PORT, "/api/health"):
            return
        self.ui(self.set_status, "Starting chat server…")
        self.server = subprocess.Popen(
            [python_console_exe(), str(APP_DIR / "server.py"), "--port", str(UI_PORT)],
            creationflags=NO_WINDOW, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(20):
            time.sleep(0.25)
            if is_up(UI_PORT, "/api/health"):
                return
        raise RuntimeError("Chat server did not start.")

    def unload_selected(self):
        name = self.selected()
        if not name:
            return
        if name not in self.loaded:
            self.set_status("%s is not loaded." % name)
            return
        self.run_bg(self._unload, [name])

    def unload_all(self):
        self.run_bg(self._unload, None)

    def _unload(self, names):
        """Unload the given models, or every loaded model if names is None."""
        if names is None:  # ask Ollama, so models loaded by other tabs/tools are included too
            names = [m["name"] for m in request(OLLAMA_PORT, "GET", "/api/ps").get("models", [])]
        for name in names:
            self.ui(self.set_status, "Unloading %s…" % name)
            request(OLLAMA_PORT, "POST", "/api/generate", {"model": name, "keep_alive": 0}, timeout=30)
        self.fetch()

    def on_close(self):
        """Closing frees the graphics card: unload all models and stop the chat server."""
        if self.closing:
            return
        if self.server and self.server.poll() is None:
            if not messagebox.askyesno(
                    "Close launcher",
                    "Closing unloads all models from graphics memory and stops the chat, "
                    "so open chat tabs stop working.\n\nClose anyway?"):
                return
        self.closing = True
        self.set_busy(True)
        self.set_status("Unloading all models…")

        def shutdown():
            try:
                self._unload(None)
            except (OSError, ValueError):
                pass  # Ollama not running: nothing is loaded
            if self.server and self.server.poll() is None:
                self.server.terminate()
            self.ui(self.root.destroy)
        threading.Thread(target=shutdown, daemon=True).start()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    Launcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
