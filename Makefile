SHELL := /bin/bash

VM_HOST ?= neuroswarm-axion.us-central1-a.project-5bcdea88-8805-4908-991
VM_PROJECT_ROOT ?= ~/neuroswarm-arm
BENCH_OUT ?= C:/tmp/neuroswarm-run-all.json

.PHONY: setup-local package sync-vm bootstrap-vm smoke-vm bench-vm bench-spec bench-spec-live bench-tool-spec logs-vm stop-vm

setup-local:
	uv sync --all-groups

package:
	uv run python -m compileall neuroswarm_arm packages/okf/nexus_okf benchmarks
	uv run python benchmarks/run_all.py --out "$(BENCH_OUT)"

sync-vm:
	powershell -ExecutionPolicy Bypass -File scripts/sync-vm.ps1 -HostAlias "$(VM_HOST)"

bootstrap-vm:
	ssh "$(VM_HOST)" 'cd $(VM_PROJECT_ROOT) && bash scripts/bootstrap-vm.sh'

smoke-vm:
	ssh "$(VM_HOST)" 'cd $(VM_PROJECT_ROOT) && docker compose ps && curl -fsS http://127.0.0.1:8000/health && curl -fsS http://127.0.0.1:8000/ready'

bench-vm:
	ssh "$(VM_HOST)" 'cd $(VM_PROJECT_ROOT) && uv run python benchmarks/run_all.py --out benchmarks/results/run_all.json'

bench-spec:
	NSA_SPECDEC_BENCH=1 uv run python benchmarks/specdec_bench.py --out benchmarks/results/specdec_bench.json

bench-spec-live:
	NSA_SPECDEC_BENCH=1 uv run python benchmarks/specdec_bench.py --live --out benchmarks/results/specdec_bench_live.json

# Speculative tool calling A/B (inproc SpeculativeEngine; <5 min on Axion).
# matplotlib: pyproject dependency-group `bench` (NOT in requirements-gateway.txt).
bench-tool-spec:
	mkdir -p benchmarks/results docs/evidence/speculative_tool
	uv run python benchmarks/speculative_tool_bench.py --out benchmarks/results/speculative_tool_bench.json
	cp benchmarks/results/speculative_tool_bench.json docs/evidence/speculative_tool/
	cp benchmarks/results/speculative_tool_bench.csv docs/evidence/speculative_tool/
	uv run --group bench python scripts/render_speculative_tool_evidence.py \
		--in benchmarks/results/speculative_tool_bench.json \
		--out-dir docs/evidence/speculative_tool

logs-vm:
	ssh "$(VM_HOST)" 'cd $(VM_PROJECT_ROOT) && docker compose logs --tail=200'

stop-vm:
	@echo "Use the GCP Console or gcloud locally to stop the VM when you are done benchmarking."
