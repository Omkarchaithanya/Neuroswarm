# RCIS Prediction

## Pre-execution

`DefaultCostPredictor.predict(RequestContext)` returns:

- expected latency / cost / memory / CPU / energy
- expected prompt / completion / reasoning tokens
- expected KV growth
- confidence (history-aware)

Priors come from historical `RuntimeCostReport` when available; otherwise `NSA_RCIS_DEFAULT_*`.

## Post-execution errors

`PredictionErrorReport` includes absolute and relative errors for cost, latency, memory, energy, CPU, tokens, KV, plus `planner_accuracy`.

## Storage

Predictions persisted alongside reports for offline analysis and AROP ASI.
