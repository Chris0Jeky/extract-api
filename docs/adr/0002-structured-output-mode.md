# ADR 0002: Structured-output mode per provider

- Status: ACCEPTED (2026-06-13).
- Deciders: Chris.
- Research: live provider docs + SDK READMEs, 2026-06-13.

## Context

Both providers now ship guaranteed-conformance structured outputs. The central
finding: structured outputs guarantee schema SHAPE, not SEMANTICS. Constrained
decoding makes the JSON match types and required-ness, but the providers'
JSON-schema subset does not support the keywords extract-api cares about
(`minimum`/`maximum`, `pattern`, `format`, string length, cross-field relations),
and conformance is not guaranteed on a refusal or token-limit truncation. So the
validation-retry loop is reframed, not removed: it owns the semantic,
normalization, cross-field, refusal, and degraded-backend cases.

## Decision

**OpenAI: native Structured Outputs via the SDK parse helper.**
`client.responses.parse(model=..., input=..., text_format=Model)` (primary), or
`client.chat.completions.parse(..., response_format=Model)` (equivalent
fallback): `json_schema` with `strict:true` under the hood. Chosen over strict
tool-calling (single fixed shape, no tool to choose) and over `json_object` (no
shape guarantee).

**Anthropic: `messages.parse()` with the Pydantic model.**
`client.messages.parse(model=..., messages=..., output_format=Model)`. Uses
`output_config.format` (json_schema, constrained decoding) on the wire AND
re-validates the full Pydantic model client-side. Fallback behind the seam:
strict tool use (`tool_choice` forced + `strict:true`).

**Both:** check the stop reason before trusting output; map refusal and
truncation to the taxonomy or a retry. Construct each client purely from
`LLM_BASE_URL` + `LLM_API_KEY` so the gateway migration is an env flip.

## Design consequences (already in the code)

1. **Optionals are null-unions** (`X | None`): the strict schema marks every
   field required, the value may be explicit `null`. Never omit a field.
2. **Constraints live in Pydantic, after parse:** `salary_max >= salary_min`,
   ISO dates, integer minor units, ISO-4217 currency. A failure here is what
   triggers retry attempt 2. The salary cross-field check is the canonical
   exemplar, kept as a worked test, because structured outputs provably cannot
   enforce it.
3. **Gateway-degradation path:** when `LLM_BASE_URL` points at a backend without
   strict json_schema, the client degrades to JSON mode and the same Pydantic
   validate-and-retry catches everything. The retry loop is what makes
   provider-agnostic routing safe.

## Consequences for the accuracy harness

Shape conformance being guaranteed means the two-provider table measures what
matters: semantic correctness, null-handling, and the hallucinated-field rate,
not JSON-formatting noise.
