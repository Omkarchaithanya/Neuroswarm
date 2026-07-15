# Troubleshooting

| Symptom | Check |
|---------|-------|
| Low accuracy | Encoder downloaded? OKF descriptions rich? threshold too high? |
| Slow first route | Cold BGE load; warm with `/tools/reload` + dummy route |
| `turbovec` missing | Falls back to exact numpy; install `turbovec` wheel for ARM |
| Redis cache unused | `NSA_ROUTER_CACHE=redis` and Redis reachable |
| Schemas not in LLM | Confirm DIPA `tool_prompt_block` / HAOE baggage wiring |
| Snapshot restore fail | Ensure full directory (`registry.json` + `index/`) present |
