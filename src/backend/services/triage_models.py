"""Pydantic models describing LLM responses for triage."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from models.messages_kernel import RiskTier, TreatmentRecommendation


class TriageLLMResponse(BaseModel):
    likelihood: int = Field(..., ge=1, le=5)
    impact: int = Field(..., ge=1, le=5)
    risk_score: int = Field(..., ge=1, le=25)
    risk_tier: RiskTier
    treatment: TreatmentRecommendation
    rationale: str = Field(..., min_length=1)
    residual_risk_rationale: str = Field(..., min_length=1)
    unacceptable_conditions: List[str] = Field(default_factory=list)
    compensating_controls: List[str] = Field(default_factory=list)
    waiver_justification: Optional[str] = None
    waiver_expiry_days: Optional[int] = Field(default=None, ge=1)
    risk_transfer_notes: Optional[str] = None

    @field_validator("risk_score")
    @classmethod
    def validate_risk_score(cls, value: int) -> int:
        if value < 1:
            raise ValueError("risk_score must be positive")
        return value

    @field_validator("unacceptable_conditions")
    @classmethod
    def validate_condition_ids(cls, values: List[str]) -> List[str]:
        for value in values:
            if not value:
                raise ValueError("Condition identifier cannot be empty")
        return values

    @field_validator("compensating_controls")
    @classmethod
    def normalize_controls(cls, values: List[str]) -> List[str]:
        return [item.strip() for item in values if isinstance(item, str) and item.strip()]


def triage_response_schema() -> dict:
    """Return JSON schema expected by the LLM response_format directive."""
    model_schema = TriageLLMResponse.model_json_schema()
    model_schema["title"] = "TriageLLMResponse"
    return model_schema
