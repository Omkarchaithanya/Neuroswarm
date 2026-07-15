# ASCR Roadmap

## Now (shipped)

- Plugin proposers/verifiers + registries
- Draft model, self-spec/ngram/suffix, block/single/batched/quality verify
- Adaptive acceptance / thresholds / confidence fusion
- Escalation DAGs (linear, tool, memory)
- ARM adapters + Prometheus metrics
- DIPA wiring + ADR-0008 + tests

## Next

1. llama-server logits / speculative API → true token accept
2. Wire `cascade_profiles.yaml` quant floors through AQR connector into policy
3. Performix → PPO `RLPolicyAgent` closed loop
4. Same-engine SGLang speculative proposer behind HAL
5. EAGLE-3 ARM-quantized draft head plugin (replace stub)
6. SpecBench CI on Axion nightlies
7. Tree / hierarchical verify when logits available

## Research opportunities

- Parallel EAGLE on multi-socket Neoverse
- Energy/token via Performix joules into threshold agent
- Shared KV identity-safe draft/verify with future MTE
