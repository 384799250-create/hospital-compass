from typing import Literal

from pydantic import BaseModel, Field, StrictBool, field_validator


class MatchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    city: str | None = None
    priority: Literal['overall', 'specialty', 'convenience'] = 'overall'

    @field_validator('query')
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('query must not be blank')
        return value


class AIMatchRequest(MatchRequest):
    ai_consent: StrictBool
