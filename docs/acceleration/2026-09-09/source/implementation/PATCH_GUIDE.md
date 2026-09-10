# Implementation and patch guide

This is a path-level design guide, not a blind patch. Re-read current files and tests before editing.

## 1. Failed validation cost

### Current seam

The provider pipeline already accumulates billed attempt cost into its terminal extraction exception. The API reconciles the budget but returns only attempts/trail in the 422 body. The live harness therefore cannot count that spend.

### Change

- Add `cost_usd` to the terminal validation error `extra` only.
- Keep pre-request 422 cost-free and shape-stable unless an additive nullable field is intentionally universal.
- Validate cost is finite and nonnegative before returning/journalling.
- Extend `PredictionFailed` to carry `cost_usd: float | None`, `attempts`, `error_code` and `request_outcome`.
- Summary reports separate successful, failed-known and unknown spend.

### Tests

- two validation attempts return their summed cost;
- first-attempt invalid + second valid remains 200 with summed cost;
- pre-request validation has no billed cost;
- malformed/negative/NaN cost in a server response invalidates evidence rather than becoming zero.

## 2. Layered scoring

Introduce explicit records:

```python
class RequestOutcome(str, Enum):
    COMPLETED = "completed_response"
    INFRA_FAILURE = "infrastructure_failure"
    AMBIGUOUS_SENT = "ambiguous_sent_failure"
    CONTROL_SKIP = "control_plane_skip"

class ExtractionOutcome(str, Enum):
    ACCEPTED = "accepted"
    VALIDATION_FAILED = "validation_failed"
    PROVIDER_FAILED = "provider_failed"
    NO_PREDICTION = "no_prediction"

class FieldOutcome(str, Enum):
    VALUE_EXACT = "value_exact"
    VALUE_INCORRECT = "value_incorrect"
    VALUE_MISSING = "value_missing"
    NULL_CORRECT = "null_correct"
    HALLUCINATED = "hallucinated"
```

Do not call the semantic scorer when no canonical prediction exists. The strict-document summary handles the penalty.

## 3. Nested paths

For accepted predictions only, recursively flatten Pydantic-canonical dictionaries/lists into paths. Preserve current top-level field statistics, then add paths under a separate table. Index alignment is deterministic and transparent. Do not sort/re-match line items silently.

## 4. Run journal

Create a dedicated module, for example `harness/run_artifacts.py`:

- canonical JSON serializer;
- manifest validation;
- append + flush + `os.fsync`;
- safe journal replay;
- duplicate fixture detection;
- atomic summary/report replacement;
- resume identity check.

Avoid using the API idempotency SQLite database as the run store.

## 5. Provider/model consistency

At run start, record requested provider/model. For every 200 or structured error, check effective provider/model when available. A mismatch makes the run invalid. Never label a section from “the last successful response.”

For gateway routes, record both requested route and effective upstream provider/model.

## 6. Transport policy

Catch transport subclasses deliberately. Do not infer “request not sent” from a generic exception string. If the HTTP library cannot prove the stage, use ambiguous-sent classification.

Do not automatically retry read timeout/reset without an idempotency plan. A duplicate provider call can spend twice even if the local API’s successful-response idempotency key later converges.

## 7. Fixture rehearsal

Recommended approach:

- add a test-only `MappingClient` that receives a mapping from content SHA-256 to scripted provider result/exception;
- inject it through the existing client dependency seam;
- use `httpx.ASGITransport` against the FastAPI app, no network port;
- create a perfect map from REVIEWED expected values only inside test/rehearsal code;
- create explicit failure scripts for retry, terminal 422, provider error and timeout;
- assert production environment routing cannot activate this map.

## 8. Job schema tightening

Use validators that reject, not normalise:

```python
from typing import Annotated
from pydantic import AfterValidator, Field

def non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value

NonBlankString = Annotated[str, AfterValidator(non_blank)]
NonNegativeInt = Annotated[int, Field(ge=0)]
```

Apply to `title`, and nullable string fields only when present. Apply nonnegative values to job salary bounds. Do not apply nonnegative invoice amounts until credit-note semantics are decided.

## 9. Prompt versioning

Build prompts from:

- generic strict instruction;
- document-type policy block;
- schema JSON;
- delimited untrusted content.

Record `prompt_version` and SHA-256 over the exact system+template bytes. Include explicit v1 conventions such as salary absence/null behavior and invoice line-item amount precedence. Do not hide schema limitations with unsupported inference instructions.

## 10. API metadata

Prefer additive fields:

- `request_id` header and error field;
- `field_presence` alongside deprecated `field_confidence`;
- journal-only `tokens_in/out`, prompt/schema/build hashes if public response expansion is undesirable;
- `cost_source` and `cost_known` in evidence records.

Keep raw provider identifiers/details sanitised.

## 11. Deployment

- document one Uvicorn worker until #42;
- bind service to private interface/network behind gateway;
- remove fixed `container_name` if scaling becomes relevant;
- add read-only root filesystem where compatible, `cap_drop: [ALL]`, `no-new-privileges`, memory/CPU/PID limits and a writable `/data` volume;
- require Docker build/persistence smoke in branch protection;
- pin CI actions consistently;
- do not make readiness call providers.
