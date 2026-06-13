"""job_posting.v1 strict schema (UK job postings).

The salary_max >= salary_min cross-field check is the canonical validation-retry
trigger: it is a constraint the providers' structured-output JSON-schema subset
provably cannot enforce, so it lives here and runs after parse.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, model_validator

from schemas._common import STRICT_CONFIG, CurrencyCode


class RemotePolicy(str, Enum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"
    unspecified = "unspecified"


class SalaryPeriod(str, Enum):
    year = "year"
    month = "month"
    day = "day"
    hour = "hour"
    unspecified = "unspecified"


class EmploymentType(str, Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    temporary = "temporary"
    internship = "internship"
    unspecified = "unspecified"


class Seniority(str, Enum):
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


class VisaSponsorship(str, Enum):
    offered = "offered"
    not_offered = "not_offered"
    unspecified = "unspecified"


class JobPostingV1(BaseModel):
    model_config = STRICT_CONFIG

    title: str
    company: str | None = None
    location: str | None = None
    remote_policy: RemotePolicy
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: CurrencyCode | None = None
    salary_period: SalaryPeriod
    employment_type: EmploymentType
    seniority: Seniority
    visa_sponsorship: VisaSponsorship
    posted_date: date | None = None

    @model_validator(mode="after")
    def _check_salary_range(self) -> JobPostingV1:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValueError("salary_max must be >= salary_min when both are present")
        return self
