# GCP Axion Bootstrap Automation

## Summary
- Turn current Axion runbook into repeatable setup flow for Windows laptop + Ubuntu ARM VM.
- Keep app/runtime unchanged; focus on GCP provisioning, VM bootstrap, and docs.
- Treat `project ID` as source of truth; do not use display name like `My First Project` in CLI.

## Implementation Changes
- Update [docs/gcp-axion-setup.md](C:/Users/Tejas/neuroswarm-arm-gcp-axion/docs/gcp-axion-setup.md) to:
  - separate `gcloud auth login`, `gcloud config set project PROJECT_ID`, and API enablement into clear steps
  - explain `project name` vs `project ID`
  - add `gcloud projects list` as lookup path
  - keep firewall, VM create, SSH, model, compose, metrics, benchmark, stop/delete flow aligned with current repo
- Add [scripts/bootstrap-gcp.ps1](C:/Users/Tejas/neuroswarm-arm-gcp-axion/scripts/bootstrap-gcp.ps1) as Windows entrypoint:
  - parameters: `ProjectId`, `Zone`, `InstanceName`, `MachineType`, `FirewallRuleName`, `SourceRanges`
  - validate `ProjectId` has no spaces and set active config with exact ID
  - enable `compute.googleapis.com` and `artifactregistry.googleapis.com`
  - create firewall rule only if missing
  - create `neuroswarm-axion` C4A VM only if missing, then print next SSH/SCP step
  - use idempotent checks so reruns are safe
- Add [scripts/bootstrap-vm.sh](C:/Users/Tejas/neuroswarm-arm-gcp-axion/scripts/bootstrap-vm.sh) for VM-side setup:
  - verify ARM architecture and save evidence file
  - install `git`, `curl`, build tools, `clang`, `docker.io`, `docker-compose-plugin`
  - create `/models`, set ownership, and fail fast if expected GGUF files are missing
  - start stack with `docker compose up --build -d`
  - run health, routing, chat, and metrics smoke checks
- Update [README.md](C:/Users/Tejas/neuroswarm-arm-gcp-axion/README.md) with a short pointer to the new bootstrap scripts and the Axion guide.

## Test Plan
- Run script syntax checks:
  - `pwsh` parse check for `bootstrap-gcp.ps1`
  - `bash -n` for `bootstrap-vm.sh`
- Dry-run local provisioning path:
  - verify project ID validation rejects spaces
  - verify script prints exact `gcloud config set project <id>` usage
  - verify rerun behavior for already-enabled APIs, existing firewall rule, and existing VM
- End-to-end on real project:
  - `gcloud config get-value project` returns chosen project ID
  - `gcloud compute instances list` shows `neuroswarm-axion`
  - VM SSH works
  - `docker compose ps` shows gateway, tier1, tier2, tier3, prometheus up
  - `curl /health`, `curl /metrics`, `/tools/route`, and `/v1/chat/completions` respond
  - benchmark output files land in `benchmarks/results/`

## Assumptions
- Existing app code and Docker compose are already correct for Axion; no FastAPI or API-contract changes needed.
- User will supply the actual `PROJECT_ID` at runtime; script will not hardcode a display name.
- GGUF model files are manual inputs because license/size make auto-download out of scope.
- Artifact Registry API stays enabled because it is in the runbook and useful for future image work, even though current compose pulls from GHCR.

## Speculative Tool Routing (Layer 2)

Plane 3.5 tool-level speculation (see `02-ARCHITECTURE.md`, `04-IMPLEMENTATION-PLAN.md`). Canonical key: `ToolOutputCache.make_key` in `neuroswarm_arm/runtime/dipa/speculative/tool_cache.py`.

Prompt B4 checklist:

- [ ] **1.** Parallel `predictor.predict` + `cascade.generate` (`asyncio.Task`)
- [ ] **2.** High-conf preds (`>= NSA_TOOL_SPEC_THRESHOLD`) → cache hit via `make_key` **or** `executor.speculate`
- [ ] **3.** On actor `tool_call` → match key / await in-flight / else sync MCP; tag `speculative_hit`
- [ ] **4.** No tool call → cancel speculative tasks

After VM sync: `docker compose up --build gateway`, then `curl /v1/tools/cache` must be 200 before claiming live Layer-2 status in README.
