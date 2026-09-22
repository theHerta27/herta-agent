from pydantic import BaseModel, ConfigDict, Field


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    text: str = Field(min_length=1, max_length=10000, pattern=r"\S")
