from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator


class MatchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    city: str | None = Field(default=None, max_length=40)
    priority: Literal['overall', 'specialty', 'convenience'] = 'overall'

    @field_validator('query')
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('query must not be blank')
        return value


class AIMatchRequest(MatchRequest):
    ai_consent: StrictBool


class Location(BaseModel):
    model_config = ConfigDict(extra='forbid')

    province: StrictStr = Field(min_length=1, max_length=40)
    city: StrictStr = Field(min_length=1, max_length=40)
    district: StrictStr = Field(min_length=1, max_length=40)

    @field_validator('province', 'city', 'district')
    @classmethod
    def location_fields_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('location fields must not be blank')
        return value


class RealtimeSearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    query: StrictStr = Field(min_length=1, max_length=500)
    location: Location
    scope: Literal['district', 'city', 'province', 'national'] = 'district'
    ai_consent: StrictBool

    @field_validator('query')
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('query must not be blank')
        return value
