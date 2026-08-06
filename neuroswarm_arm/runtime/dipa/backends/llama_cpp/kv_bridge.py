"""Zero-copy bridge between MAKS providers and llama.cpp KV cache via shared memory."""

from __future__ import annotations

import json
import os
import struct
from typing import Any

from neuroswarm_arm.runtime.kv.sharing.shm import SharedMemoryBackend


class MAKStoLlamaKVBridge:
    """
    Bridge for zero-copy KV cache transfer between MAKS and llama.cpp.

    Uses shared memory (SHM) instead of file I/O to avoid copy overhead.
    """

    METADATA_HEADER_SIZE = 4096  # 4KB reserved for JSON metadata

    def __init__(
        self,
        maks_manager: Any,  # MAKS KVManager or compatible
        slot_client: Any,   # SlotClient
    ) -> None:
        self._maks_manager = maks_manager
        self._slot_client = slot_client
        self._shm_backend = SharedMemoryBackend()

    async def share_session_kv(
        self,
        session_id: str,
        source_slot_id: int,
        target_backend: Any,  # LlamaCppBackend
    ) -> str:
        """
        Share MAKS session KV into a contiguous SHM segment for llama.cpp.

        Returns:
            shm_name: Name of the shared memory segment (e.g., "nsa_kv_{session_id}")
        """
        shm_name = f"nsa_kv_{session_id}"

        # 1. Get physical block payloads from MAKS for this session
        payloads = await self._maks_manager.read_payloads(session_id)

        # 2. Build offset map and calculate total size
        offset_map = {}
        total_data_size = 0
        block_index = 0

        for layer_idx, layer_data in enumerate(payloads):
            if isinstance(layer_data, dict):
                # K/V tensors per layer
                for tensor_name in ("k", "v"):
                    if tensor_name in layer_data:
                        tensor_bytes = layer_data[tensor_name]
                        offset_map[f"layer_{layer_idx}_{tensor_name}"] = {
                            "offset": self.METADATA_HEADER_SIZE + total_data_size,
                            "size": len(tensor_bytes),
                            "shape": layer_data.get(f"{tensor_name}_shape", []),
                            "dtype": layer_data.get(f"{tensor_name}_dtype", "float16"),
                            "layer": layer_idx,
                            "head": layer_data.get(f"{tensor_name}_head", 0),
                        }
                        total_data_size += len(tensor_bytes)
            elif isinstance(layer_data, bytes):
                # Raw bytes payload
                offset_map[f"block_{block_index}"] = {
                    "offset": self.METADATA_HEADER_SIZE + total_data_size,
                    "size": len(layer_data),
                    "shape": [],
                    "dtype": "float16",
                    "layer": block_index // 2,
                    "head": block_index % 2,
                }
                total_data_size += len(layer_data)
                block_index += 1

        total_size = self.METADATA_HEADER_SIZE + total_data_size

        # 3. Create SHM segment
        shm = self._shm_backend.create_named_region(shm_name, total_size)

        # 4. Write metadata header (JSON)
        metadata = {
            "session_id": session_id,
            "source_slot_id": source_slot_id,
            "block_table": offset_map,
            "total_data_size": total_data_size,
            "metadata_version": 1,
        }
        metadata_bytes = json.dumps(metadata).encode("utf-8")
        if len(metadata_bytes) > self.METADATA_HEADER_SIZE:
            raise ValueError(f"Metadata too large: {len(metadata_bytes)} > {self.METADATA_HEADER_SIZE}")
        shm.buf[:len(metadata_bytes)] = metadata_bytes

        # 5. Write contiguous KV tensor data
        data_offset = self.METADATA_HEADER_SIZE
        for layer_idx, layer_data in enumerate(payloads):
            if isinstance(layer_data, dict):
                for tensor_name in ("k", "v"):
                    if tensor_name in layer_data:
                        tensor_bytes = layer_data[tensor_name]
                        shm.buf[data_offset : data_offset + len(tensor_bytes)] = tensor_bytes
                        data_offset += len(tensor_bytes)
            elif isinstance(layer_data, bytes):
                shm.buf[data_offset : data_offset + len(layer_data)] = layer_data
                data_offset += len(layer_data)

        # 6. Import into llama.cpp backend via slot_client
        await target_backend.slot_client.kv_import_from_shm(
            source_slot_id, shm_name, offset_map
        )

        return shm_name

    async def import_session_kv(
        self,
        session_id: str,
        target_slot_id: int,
        shm_name: str,
    ) -> None:
        """
        Restore KV from existing SHM segment into llama.cpp slot.

        Reconstructs block table from SHM metadata header.
        """
        # Attach to existing SHM segment
        shm = self._shm_backend.attach_named_region(shm_name)

        # Read metadata header
        metadata_bytes = bytes(shm.buf[:self.METADATA_HEADER_SIZE])
        # Find actual JSON end (null-terminated or first valid JSON)
        metadata_str = metadata_bytes.decode("utf-8", errors="ignore").strip("\x00")
        metadata = json.loads(metadata_str)

        # Verify session_id matches
        if metadata.get("session_id") != session_id:
            raise ValueError(f"SHM session_id mismatch: {metadata.get('session_id')} != {session_id}")

        # Call slot_client restore from SHM
        await self._slot_client.restore_from_shm(target_slot_id, shm_name)

    def _serialize_offset_map(self, offset_map: dict[str, dict]) -> bytes:
        """Serialize offset map to compact binary format."""
        # Simple JSON for now; could use msgpack/cbor for efficiency
        return json.dumps(offset_map).encode("utf-8")

    def _deserialize_offset_map(self, data: bytes) -> dict[str, dict]:
        """Deserialize offset map from binary format."""
        return json.loads(data.decode("utf-8"))