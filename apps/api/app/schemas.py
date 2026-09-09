import base64
import binascii
from typing import Any, Literal

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


class FeedbackSubmission(BaseModel):
    category: Literal['bug', 'improvement', 'other']
    message: StrictStr = Field(min_length=10, max_length=2000)
    contact: str | None = Field(default=None, max_length=200)
    attachments: list['FeedbackAttachment'] = Field(default_factory=list, max_length=5)

    @field_validator('message')
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('message must not be blank')
        return value

    @field_validator('contact')
    @classmethod
    def normalize_contact(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ''
        return normalized or None


class FeedbackAttachment(BaseModel):
    filename: StrictStr = Field(min_length=1, max_length=120)
    content_type: Literal['image/jpeg', 'image/png', 'image/webp']
    data: StrictStr = Field(min_length=1, max_length=7_000_000)

    @field_validator('data')
    @classmethod
    def attachment_data_must_be_valid_and_small(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError('attachment data must be valid base64') from exc
        if len(decoded) > 5 * 1024 * 1024:
            raise ValueError('attachment exceeds 5 MB')
        return value


class FeedbackAdminSession(BaseModel):
    token: StrictStr = Field(min_length=1, max_length=512)


class FeedbackStatusUpdate(BaseModel):
    status: Literal['new', 'processed']


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
    location_level: Literal['province', 'city', 'district'] = 'district'
    scope: Literal['district', 'city', 'province', 'national'] = 'district'
    ai_consent: StrictBool
    confirmed_direction: str | None = Field(default=None, max_length=100)
    hospital_tiers: list[Literal['tertiary_a']] = Field(default_factory=lambda: ['tertiary_a'], min_length=1, max_length=1)
    ignore_geography: StrictBool = False

    @field_validator('query')
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('query must not be blank')
        return value


class MediaTaskRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    model: StrictStr = Field(min_length=1, max_length=160)
    prompt: StrictStr = Field(min_length=1, max_length=4000)
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator('model', 'prompt')
    @classmethod
    def media_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('media text must not be blank')
        return value
