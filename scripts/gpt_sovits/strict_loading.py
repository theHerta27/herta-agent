"""Force weights-only checkpoint loading; the sole role config alias is inert."""
from __future__ import annotations
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
import torch

class SafeHParams:
    # No constructor, reduce/setstate/import side effects. BUILD restores plain attributes.
    pass

_ORIGINAL_LOAD = torch.load
LOAD_AUDIT = []

def _plain(value):
    if isinstance(value, SafeHParams):
        return {str(k): _plain(v) for k, v in vars(value).items()}
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_plain(v) for v in value)
    if isinstance(value, (torch.Tensor, str, bytes, int, float, bool, type(None))):
        return value
    raise TypeError(f"Unsupported deserialized value: {type(value).__name__}")

def strict_torch_load(source, *args, **kwargs):
    kwargs["weights_only"] = True
    with torch.serialization.safe_globals([(SafeHParams, "utils.HParams")]):
        result = _ORIGINAL_LOAD(source, *args, **kwargs)
    result = _plain(result)
    LOAD_AUDIT.append({"source": str(source) if isinstance(source, (str, Path)) else "in-memory", "weights_only": True})
    return result

def load_sovits_new(path):
    # Version 06 is upstream's documented v2ProPlus archive marker.
    data = Path(path).read_bytes()
    if data[:2] == b"06":
        data = b"PK" + data[2:]
    elif data[:2] != b"PK":
        raise ValueError("Only standard PyTorch archives and v2ProPlus 06 archives are accepted")
    return strict_torch_load(BytesIO(data), map_location="cpu")

def install():
    torch.load = strict_torch_load
