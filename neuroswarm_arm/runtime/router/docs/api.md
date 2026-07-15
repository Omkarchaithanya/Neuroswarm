# API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/tools/register` | Register tool + index |
| POST | `/tools/update` | Update tool |
| DELETE | `/tools/remove?tool_id=` | Remove tool |
| POST | `/tools/search` | Search without prompt block |
| POST | `/tools/route` | Full route + prompt_block |
| POST | `/tools/reload` | Reload OKF roots |
| GET | `/tools` | List tools |
| GET | `/tools/{id}` | Get tool |
| GET | `/router/metrics` | Router gauges |
| GET | `/router/health` | Health + ARM features |
| POST | `/router/benchmark` | Run accuracy/latency suite |
| POST | `/router/snapshot` | Persist registry+index |
| POST | `/router/restore` | Restore snapshot |

Python surface: `register_tool`, `remove_tool`, `update_tool`, `search`, `route`, `batch_route`, `reload`, `snapshot`, `restore`, `health`, `metrics`, `benchmark`.
