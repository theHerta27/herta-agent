"""Expected errors that the CLI can display without exposing HTTP bodies or credentials."""


class AgentError(Exception):
    """Base class for expected runtime errors."""


class ProviderError(AgentError):
    """A model request failed."""


class ProviderProtocolError(ProviderError):
    """The service returned a response outside the supported protocol."""


class ModelTimeoutError(ProviderError):
    """The model request exceeded its deadline."""


class SessionBusyError(AgentError):
    """Another run is already using this in-memory session."""


class StepLimitExceeded(AgentError):
    """No model request may start after the run budget is exhausted."""


class ToolCallLimitExceeded(AgentError):
    """The model returned more calls than the per-response budget permits."""
