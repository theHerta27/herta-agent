"""Chat Completions HTTP adapter with separate complete and streaming protocols."""

from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from herta_agent.config import ProviderSettings
from herta_agent.llm.streaming import parse_stream
from herta_agent.runtime.errors import (
    ModelTimeoutError,
    ProviderError,
    ProviderProtocolError,
)
from herta_agent.runtime.messages import Message, ModelReply, ToolCall


class _WireFunction(BaseModel):
    name: str
    arguments: str


class _WireToolCall(BaseModel):
    id: str
    type: Literal["function"]
    function: _WireFunction


class _WireMessage(BaseModel):
    role: Literal["assistant"]
    content: str | None = None
    tool_calls: list[_WireToolCall] | None = None
    function_call: dict[str, object] | None = None


class _Choice(BaseModel):
    message: _WireMessage
    finish_reason: str


class _Completion(BaseModel):
    choices: list[_Choice] = Field(min_length=1, max_length=1)


class OpenAICompatibleProvider:
    def __init__(self, settings: ProviderSettings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client  # Owned and closed by the caller, shared across turns.

    async def stream(self, messages: tuple[Message, ...], *, tools: tuple[dict, ...] = ()):
        body = {
            "model": self.settings.model,
            "messages": [m.to_wire() for m in messages],
            "stream": True,
        }
        if tools:
            body["tools"] = list(tools)
        try:
            async with self.client.stream(
                "POST",
                f"{self.settings.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.api_key.get_secret_value()}"},
                json=body,
                follow_redirects=False,
            ) as response:
                if response.status_code in {401, 403}:
                    raise ProviderError("模型服务拒绝鉴权，请检查 API Key 和访问权限。")
                if not response.is_success:
                    raise ProviderError(
                        f"模型服务返回 HTTP {response.status_code}，本次没有自动重试。"
                    )
                async for event in parse_stream(response.aiter_bytes()):
                    yield event
        except httpx.TimeoutException:
            raise ModelTimeoutError("模型连接或读取超时。") from None
        except httpx.RequestError:
            raise ProviderError("无法连接模型服务，请检查地址、网络或代理配置。") from None

    async def complete(
        self, messages: tuple[Message, ...], *, tools: tuple[dict, ...] = ()
    ) -> ModelReply:
        body = {
            "model": self.settings.model,
            "messages": [message.to_wire() for message in messages],
            "stream": False,
        }
        if tools:
            body["tools"] = list(tools)
        try:
            response = await self.client.post(
                f"{self.settings.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.api_key.get_secret_value()}"},
                json=body,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise ModelTimeoutError("模型连接或读取超时。") from None
        except httpx.RequestError:
            raise ProviderError("无法连接模型服务，请检查地址、网络或代理配置。") from None

        if response.status_code in {401, 403}:
            raise ProviderError("模型服务拒绝鉴权，请检查 API Key 和访问权限。")
        if not response.is_success:
            # Never forward a vendor body/URL which might contain credentials or user input.
            raise ProviderError(f"模型服务返回 HTTP {response.status_code}，本次没有自动重试。")
        return self._parse_reply(response)

    @staticmethod
    def _parse_reply(response: httpx.Response) -> ModelReply:
        try:
            completion = _Completion.model_validate(response.json())
        except ValueError:
            raise ProviderProtocolError("模型响应不是受支持的 Chat Completions JSON。") from None

        choice = completion.choices[0]
        if choice.message.function_call is not None or choice.finish_reason == "function_call":
            raise ProviderProtocolError("不支持旧 function_call 协议，请使用 tool_calls。")
        if choice.finish_reason not in {"stop", "tool_calls"}:
            raise ProviderProtocolError("模型未正常结束回复，可能被截断或过滤；未保存为完整回答。")
        if choice.finish_reason == "tool_calls" and not choice.message.tool_calls:
            raise ProviderProtocolError("模型声明工具调用但没有提供调用内容。")
        try:
            return ModelReply(
                message=Message(
                    role="assistant",
                    content=choice.message.content,
                    tool_calls=tuple(
                        ToolCall(
                            id=call.id, name=call.function.name, arguments=call.function.arguments
                        )
                        for call in choice.message.tool_calls or ()
                    ),
                )
            )
        except ValidationError:
            raise ProviderProtocolError("模型没有返回有效的文本或工具调用。") from None
