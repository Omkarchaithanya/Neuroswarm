# AROP plugin guide

## Add an ObservationProvider

1. Subclass `neuroswarm_arm.evolution.interfaces.observation.ObservationProvider`.
2. Implement `collect`, `snapshot`, `metrics`, `health`.
3. Register in `build_arop` via `aggregator.add(provider)` or extend `factory.py`.

## Add a ReflectionStrategy

1. Subclass `ReflectionStrategy`.
2. Implement `analyze`, `reflect`, `propose` — **never mutate runtime**.
3. Select with `NSA_AROP_REFLECTION=your_name` (wire in `factory._build_reflection`).

## Add a DeploymentAdapter

1. Subclass `deployment.adapters.DeploymentAdapter`.
2. Declare `KEYS` / `supported_keys`.
3. Map parameters onto your layer target (prefer dry-run safe setattr).
4. Pass into `build_arop(... layer_target=...)` / `DeploymentEngine.add_adapter`.

## Offline RL arm

1. Push episodes into `ExperienceStore`.
2. `OfflineContextualBandit.fit(...)` then `propose(state)`.
3. Deltas enter the same Optimization → Experiment → Safety path.
