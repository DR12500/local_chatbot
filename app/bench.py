"""Measure real tokens/second for your installed models on this machine.

    python app/bench.py              # all installed local models
    python app/bench.py qwen3:8b     # specific models
"""
import http.client
import json
import sys

PROMPT = "Explain in about 200 words how a refrigerator works."


def call(method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", 11434, timeout=900)
    conn.request(method, path, body=json.dumps(body) if body else None,
                 headers={"Content-Type": "application/json"})
    data = json.loads(conn.getresponse().read())
    conn.close()
    return data


def main():
    models = sys.argv[1:] or [m["name"] for m in call("GET", "/api/tags")["models"]
                              if "cloud" not in m["name"]]
    print("%-28s %10s %12s %10s" % ("model", "load s", "prompt t/s", "gen t/s"))
    for model in models:
        req = {"model": model, "prompt": PROMPT, "stream": False, "think": False,
               "options": {"num_ctx": 8192, "num_predict": 300}}
        r = call("POST", "/api/generate", req)
        if "think" in str(r.get("error", "")):  # model has no thinking switch
            del req["think"]
            r = call("POST", "/api/generate", req)
        if "error" in r:
            print("%-28s error: %s" % (model, r["error"]))
            continue
        ns = 1e9
        pp = r.get("prompt_eval_count", 0) / max(r.get("prompt_eval_duration", 1), 1) * ns
        tg = r.get("eval_count", 0) / max(r.get("eval_duration", 1), 1) * ns
        print("%-28s %10.1f %12.0f %10.1f" % (model, r.get("load_duration", 0) / ns, pp, tg))
    print("\nRun 'ollama ps' while a model is loaded: PROCESSOR should say 100% GPU.")


if __name__ == "__main__":
    main()
