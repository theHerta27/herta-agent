"""Per-task tool identity for owned external resources; no handler API change."""

from contextvars import ContextVar

tool_call_id: ContextVar[str] = ContextVar("tool_call_id", default="direct")
