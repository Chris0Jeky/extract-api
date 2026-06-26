"""job_posting.v1 strict schema (UK job postings).

The salary cross-field checks are canonical validation-retry triggers: constraints the
providers' structured-output JSON-schema subset provably cannot enforce, so they live
here and run after parse. salary_max >= salary_min when both are present, and
salary_currency is required whenever a salary figure is present (a figure without a
currency is ambiguous).

Nullable fields are required-but-nullable (no default), mirroring invoice.v1: a provider
must emit the key as an explicit null when the value is genuinely absent, so omission
fails loudly and the generated JSON schema marks every field required (ADR 0002).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, model_validator

from schemas._common import STRICT_CONFIG, CurrencyCode


class RemotePolicy(StrEnum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"
    unspecified = "unspecified"


class SalaryPeriod(StrEnum):
    year = "year"
    month = "month"
    day = "day"
    hour = "hour"
    unspecified = "unspecified"


class EmploymentType(StrEnum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    temporary = "temporary"
    internship = "internship"
    unspecified = "unspecified"


class Seniority(StrEnum):
    intern = "intern"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    staff = "staff"
    principal = "principal"
    lead = "lead"
    manager = "manager"
    director = "director"
    unspecified = "unspecified"


class VisaSponsorship(StrEnum):
    offered = "offered"
    not_offered = "not_offered"
    unspecified = "unspecified"


class JobPostingV1(BaseModel):
    model_config = STRICT_CONFIG

    title: str
    company: str | None
    location: str | None
    remote_policy: RemotePolicy
    salary_min: int | None
    salary_max: int | None
    salary_currency: CurrencyCode | None
    salary_period: SalaryPeriod
    employment_type: EmploymentType
    seniority: Seniority
    visa_sponsorship: VisaSponsorship
    posted_date: date | None

    @model_validator(mode="after")
    def _check_salary(self) -> JobPostingV1:
        # A salary figure without a currency is ambiguous (issue #4): when either bound is
        # present, the currency must be too. salary_currency stays null only when the
        # posting discloses no figure (for example "competitive").
        has_salary = self.salary_min is not None or self.salary_max is not None
        if has_salary and self.salary_currency is None:
            raise ValueError("salary_currency is required when salary_min or salary_max is present")
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValueError("salary_max must be >= salary_min when both are present")
        return self
