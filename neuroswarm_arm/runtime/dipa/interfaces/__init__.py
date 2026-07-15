"""DIPA interface package — dependency-inversion contracts."""

from __future__ import annotations

from .backend import InferenceBackend
from .cascade import ICascadeEngine
from .engine import IInferenceEngine
from .kv_cache import IKVCacheConnector
from .lifecycle import ILifecycle, LifecyclePhase
from .model import IModelRouter
from .pd import (
    DecodeHandle,
    IChunkPlanner,
    IDecodeRuntime,
    IKVTransfer,
    IPrefixCache,
    IPrefillRuntime,
    PromptChunk,
)
from .quantizer import IQuantConnector
from .reasoning import IReasoningHook, NullReasoningHook
from .runtime import IRuntime
from .streamer import IStreamer
from .types import (
    BackendCapabilities,
    BackendDescriptor,
    CorrelationIds,
    DecodeRequest,
    DeviceClass,
    ExecutionPhase,
    ExecutionPlan,
    FeatureStatus,
    GenerateRequest,
    GenerateResult,
    HealthState,
    HealthStatus,
    InferenceRequest,
    InferenceResponse,
    KVTransferMode,
    ModelCandidate,
    PDMode,
    PoolKind,
    PrefillRequest,
    PrefillResult,
    QuantLevel,
    RouteScore,
    TokenChunk,
    WorkloadClass,
)
from .warm import IWarmConnector

__all__ = [
    "InferenceBackend",
    "ICascadeEngine",
    "IInferenceEngine",
    "IKVCacheConnector",
    "ILifecycle",
    "LifecyclePhase",
    "IModelRouter",
    "IPrefillRuntime",
    "IDecodeRuntime",
    "IKVTransfer",
    "IPrefixCache",
    "IChunkPlanner",
    "DecodeHandle",
    "PromptChunk",
    "IQuantConnector",
    "IReasoningHook",
    "IRuntime",
    "IStreamer",
    "IWarmConnector",
    "NullReasoningHook",
    "BackendCapabilities",
    "BackendDescriptor",
    "CorrelationIds",
    "DecodeRequest",
    "DeviceClass",
    "ExecutionPhase",
    "ExecutionPlan",
    "FeatureStatus",
    "GenerateRequest",
    "GenerateResult",
    "HealthState",
    "HealthStatus",
    "InferenceRequest",
    "InferenceResponse",
    "KVTransferMode",
    "ModelCandidate",
    "PDMode",
    "PoolKind",
    "PrefillRequest",
    "PrefillResult",
    "QuantLevel",
    "RouteScore",
    "TokenChunk",
    "WorkloadClass",
]
