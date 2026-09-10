# Extraction hosting reference

Reference-only preparation, 2026-09-10. `manifest.json` is inert metadata. It changes no API, provider, database, credentials, hostname or deployment trigger. Existing workflows may still run after a future merge.

Keep the service local/private until a separately approved host is justified. A static demo does not execute Python/PyMuPDF extraction. Do not publish an unauthenticated paid-model endpoint or silently add this workload to Taskdeck's small instance.

EX1 specifies gateway authentication, per-caller limits, bounded PDF/text input and finite provider spend before external exposure. CORS and a per-run model cap are not substitutes for caller authentication and aggregate abuse control. EX2 proves fixture-mode restart/idempotency persistence on `/data`, strict validation and no paid-provider calls for invalid input. EX3 permits only a separately reviewed synthetic demonstration, not real documents or live keys.

Preserve key-plus-payload idempotency, conflict semantics and the existing retry/error contracts. Do not log document text, credential values or raw provider failures. Host/container compatibility is not a reason to change extraction semantics.

Follow `AGENTS.md` and the existing CLAUDE orientation and task queue. Syntax: `python -m json.tool .hosting/manifest.json`. Future implementation requires `make ci-quick` and the narrowest existing seam tests. Hosted, budget and restore acceptance need actual receipts; JSON validation does not establish them.

Record the previous image and compatible idempotency database before promotion. Do not delete the persistent volume to obtain a clean deployment. Purchases, live provider activation, public branding and domain changes are separate owner actions.
