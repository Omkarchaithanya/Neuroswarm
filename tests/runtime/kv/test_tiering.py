"""Tiering policy unit tests."""

from __future__ import annotations

import time

from neuroswarm_arm.runtime.kv.interfaces.types import PhysicalBlockRecord, StorageTier
from neuroswarm_arm.runtime.kv.migration import TieringPolicy


def test_temperature_and_score() -> None:
    policy = TieringPolicy(hot_access_window_s=10, warm_access_window_s=100)
    now = time.time()
    hot = PhysicalBlockRecord(
        physical_id="h",
        content_hash="a",
        prefix_hash="",
        tier=StorageTier.L1_RAM,
        provider_key="h",
        last_access=now,
        access_count=5,
    )
    cold = PhysicalBlockRecord(
        physical_id="c",
        content_hash="b",
        prefix_hash="",
        tier=StorageTier.L1_RAM,
        provider_key="c",
        last_access=now - 1000,
        access_count=1,
    )
    assert policy.temperature(hot, now).value == "hot"
    assert policy.temperature(cold, now).value == "cold"
    assert policy.score(cold, now) > policy.score(hot, now)
    assert policy.next_colder(StorageTier.L1_RAM) == StorageTier.L2_COMPRESSED_RAM
    assert policy.next_hotter(StorageTier.L2_COMPRESSED_RAM) == StorageTier.L1_RAM
