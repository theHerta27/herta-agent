"""Safe expected errors; messages never include service bodies or credentials."""

from herta_agent.runtime.errors import AgentError


class RagError(AgentError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
