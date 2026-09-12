from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BrokerId = Literal["broker-alex", "broker-jordan"]
# A server-owned fixture name or the ID of an attachment uploaded to the same case.
EvidenceId = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9-]+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Changes(StrictModel):
    mailing_address: str | None = Field(default=None, min_length=1, max_length=500)
    email: str | None = Field(default=None, min_length=1, max_length=254)
    phone: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError("At least one permitted contact field is required")
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Contact fields cannot be cleared")
        return self


class Intake(StrictModel):
    broker_id: BrokerId
    original_request: str = Field(min_length=1, max_length=20000)
    policy_number: str | None = Field(default=None, min_length=1, max_length=80)
    # Optional so an inbox adapter can submit the same structure before changes are extracted.
    changes: Changes | None = None
    evidence_id: EvidenceId | None = None


class ProposalEdit(StrictModel):
    expected_version: int = Field(ge=1)
    changes: Changes


class Reply(StrictModel):
    expected_version: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=20000)
    policy_number: str | None = Field(default=None, min_length=1, max_length=80)
    evidence_id: EvidenceId | None = None


class VersionAction(StrictModel):
    version: int = Field(ge=1)


class Rejection(VersionAction):
    reason: str = Field(min_length=1, max_length=1000)
