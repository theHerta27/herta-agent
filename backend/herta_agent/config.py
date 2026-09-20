"""Validated configuration. No automatic .env loading or credential persistence."""

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class RunSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    max_steps: int = Field(default=8, strict=True, ge=1, le=100)
    request_timeout: float = Field(default=120.0, strict=True, gt=0, le=600)
    tool_timeout: float = Field(default=10.0, strict=True, gt=0, le=600)


class ProviderSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    base_url: str
    model: str = Field(min_length=1)
    api_key: SecretStr

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Base URL 必须是包含主机名的 http/https 地址")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Base URL 不能包含用户名、密码、query 或 fragment")
        if value.endswith("/chat/completions"):
            raise ValueError("填写 API 根地址（通常以 /v1 结尾），不要填写 /chat/completions")
        _ = parsed.port  # Reject invalid ports before starting any request.
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Model 不能为空")
        return value.strip()

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("API Key 不能为空；无鉴权本地服务可显式填写 local")
        if any(char in value.get_secret_value() for char in "\r\n"):
            raise ValueError("API Key 不能包含换行")
        return value
