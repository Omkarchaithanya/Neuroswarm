#!/usr/bin/env python3
import json
import os
import urllib.request

os.chdir(os.environ.get("NSA_ROOT", "."))

print("N_PROBS", os.getenv("NSA_LLAMA_N_PROBS"))
from neuroswarm_arm.runtime.dipa.routing.speculation_router import SpeculationRouter
from neuroswarm_arm.runtime.dipa.interfaces.types import ExecutionPlan

p = ExecutionPlan(use_cascade=True)
SpeculationRouter({}).apply(p)
print("spec_empty_cfg", p.speculation, p.metadata.get("speculation"))

p2 = ExecutionPlan(use_cascade=True)
SpeculationRouter({"speculation": {"enabled": False}}).apply(p2)
print("spec_disabled_cfg", p2.speculation, p2.metadata.get("speculation"))

# One chat then dump key metrics
body = json.dumps(
    {
        "model": "default",
        "messages": [{"role": "user", "content": "Reply with three words."}],
        "max_tokens": 24,
        "temperature": 0,
    }
).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/v1/chat/completions",
    data=body,
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=120) as resp:
    chat = json.loads(resp.read().decode())
print("chat_metrics", chat.get("metrics"))
with urllib.request.urlopen("http://127.0.0.1:8000/metrics", timeout=30) as resp:
    text = resp.read().decode()
for line in text.splitlines():
    if "ascr_speculation_gain" in line or "ascr_quality_cascade" in line or "ascr_text_agreement" in line:
        if line.startswith("#"):
            continue
        print(line)
