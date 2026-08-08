from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, computed_field, field_validator


def rank_to_score(rank: int | None) -> float:
    """Convert a published specialty rank into a bounded ranking score."""
    if rank is None:
        return 0.0
    if rank < 1:
        raise ValueError('rank must be greater than zero')
    return float(max(0, 110 - (rank * 10)))


class SpecialtyRankingEvidence(BaseModel):
    """Traceable specialty-ranking evidence for a hospital."""

    model_config = ConfigDict(extra='forbid')

    hospital: StrictStr = Field(min_length=1, max_length=200)
    city: StrictStr = Field(min_length=1, max_length=100)
    specialty: StrictStr = Field(min_length=1, max_length=100)
    rank: Annotated[StrictInt, Field(gt=0)] | None = None
    year: StrictInt
    source: StrictStr
    verification_status: StrictStr = '待核验'

    @field_validator('hospital', 'city', 'specialty')
    @classmethod
    def normalize_identity_field(cls, value: str) -> str:
        normalized = ' '.join(value.split())
        if not normalized:
            raise ValueError('value must not be blank')
        return normalized

    @computed_field
    @property
    def score(self) -> float:
        return rank_to_score(self.rank)
