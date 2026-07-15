"""KVTransferManager — honest handoff modes (ADR-0006)."""

from __future__ import annotations

from collections.abc import Sequence

from neuroswarm_arm.runtime.dipa.interfaces.pd import DecodeHandle, IKVTransfer
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    FeatureStatus,
    KVTransferMode,
    PrefillResult,
)


class KVTransferManager(IKVTransfer):
    """
    Modes:
    - native_sglang: same-engine PD (bootstrap_room / router)
    - recompute: heterogeneous default (SGLang → llama.cpp)
    - unavailable: RDMA engines not present
    """

    def __init__(
        self,
        *,
        mooncake_status: FeatureStatus = FeatureStatus.UNAVAILABLE,
        nixl_status: FeatureStatus = FeatureStatus.UNAVAILABLE,
        default_mode: KVTransferMode = KVTransferMode.RECOMPUTE,
    ) -> None:
        self.mooncake_status = mooncake_status
        self.nixl_status = nixl_status
        self.default_mode = default_mode
        self._last_mode = default_mode

    def resolve_mode(
        self,
        *,
        prefill_backend: str,
        decode_backend: str,
        requested: KVTransferMode | None = None,
    ) -> KVTransferMode:
        pref = (prefill_backend or "").lower()
        dec = (decode_backend or "").lower()
        same_sglang = "sglang" in pref and "sglang" in dec
        if requested == KVTransferMode.NATIVE_SGLANG or (
            requested is None and same_sglang
        ):
            if (
                self.mooncake_status == FeatureStatus.AVAILABLE
                or self.nixl_status == FeatureStatus.AVAILABLE
                or same_sglang
            ):
                # Soft native: pass bootstrap metadata even without IB on single process.
                return KVTransferMode.NATIVE_SGLANG
            return KVTransferMode.UNAVAILABLE
        if requested == KVTransferMode.UNAVAILABLE:
            return KVTransferMode.UNAVAILABLE
        if pref and dec and pref != dec and "sglang" in pref and "llama" in dec:
            return KVTransferMode.RECOMPUTE
        return requested or self.default_mode

    async def handoff(
        self,
        prefill: PrefillResult | Sequence[PrefillResult],
        *,
        messages: list[dict[str, str]],
        decode_backend: str,
        session_id: str = "",
        quant: str = "",
    ) -> DecodeHandle:
        results = list(prefill) if isinstance(prefill, Sequence) else [prefill]
        last = results[-1] if results else PrefillResult()
        mode = last.transfer_mode or self.default_mode
        prefix_tokens = sum(r.prefix_tokens for r in results) or last.prefix_tokens
        hit = sum(r.prefix_hit_tokens for r in results) or last.prefix_hit_tokens
        if mode == KVTransferMode.RECOMPUTE:
            recompute = max(0, prefix_tokens - hit)
        elif mode == KVTransferMode.NATIVE_SGLANG:
            recompute = 0
        else:
            recompute = prefix_tokens
        self._last_mode = mode
        return DecodeHandle(
            messages=list(last.messages or messages),
            transfer_mode=mode,
            kv_handle=last.kv_handle,
            bootstrap_room=last.bootstrap_room,
            radix_node_id=last.radix_node_id,
            prefix_tokens=prefix_tokens,
            prefix_hit_tokens=hit,
            recompute_tokens=recompute,
            token_ids=list(last.token_ids),
            prefill_backend=last.backend,
            decode_backend=decode_backend,
            session_id=session_id,
            quant=quant,
            metadata={
                "chunk_count": float(len(results)),
                "mooncake": self.mooncake_status.value,
                "nixl": self.nixl_status.value,
            },
        )

    @property
    def last_mode(self) -> KVTransferMode:
        return self._last_mode
