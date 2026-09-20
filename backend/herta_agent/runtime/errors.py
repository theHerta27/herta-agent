"""Expected errors that the CLI can display without exposing HTTP bodies or credentials."""


class AgentError(Exception):
    """Base class for expected runtime errors."""


class ToolExecutionError(AgentError):
    """Expected tool failure; callers must supply a safe, credential-free message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ContextError(AgentError):
    """Required system context could not be loaded or constructed."""


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
