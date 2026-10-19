import os, httpx

env = {}
with open(r"D:\Adhikaar\backend\.llm_env", encoding="utf-8") as f:
    for line in f:
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v

base = env["ADHIKAAR_LLM_BASE_URL"].rstrip("/")
key = env["ADHIKAAR_LLM_API_KEY"]
model = env["ADHIKAAR_LLM_MODEL"]
url = base + "/chat/completions"
try:
    r = httpx.post(url,
                   headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                   json={"model": model, "temperature": 0, "max_tokens": 50,
                         "messages": [{"role": "user", "content": "Reply with exactly: CONNECTION_OK"}]},
                   timeout=60.0)
    print("HTTP", r.status_code)
    if r.status_code == 200:
        j = r.json()
        print("reply:", j["choices"][0]["message"]["content"][:120])
    else:
        print("body (first 400):", r.text[:400])
except Exception as e:
    print("ERROR", type(e).__name__, str(e)[:200])
