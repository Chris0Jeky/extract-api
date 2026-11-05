# Packaged Python security evidence

Issue [#194](https://github.com/Chris0Jeky/extract-api/issues/194) tracks two residual
CPython findings in the pinned image. `scripts/probe_runtime_security.py` exercises
the relevant behavior in the interpreter that runs it, using synthetic inputs in
memory. It opens no network connections and changes no runtime files.

The image workflow runs the probe against the same image reference used by its
runtime smoke check. On main, this is the pushed immutable digest. The container
runs without networking, with a read-only filesystem, as UID/GID 10001, and with
the probe script mounted read-only. The script is not added to the runtime image.

## What is checked

| Finding | Probe | Upstream reference |
| --- | --- | --- |
| CVE-2025-15367 | POP3 USER/PASS command formatting rejects C0 control characters and DEL before sending any bytes. Valid commands are controls. A capture object replaces the transport. | [CPython fix](https://github.com/python/cpython/commit/b234a2b67539f787e191d2ef19a7cbdce32874e7) |
| CVE-2026-103995 | HTTP response framing ignores invalid Content-Length values and rejects invalid chunk sizes. Valid framing, chunk extensions and optional whitespace around Content-Length are controls. Inputs use byte buffers. | [Grammar fix](https://github.com/python/cpython/commit/2eb2af805c156ca52b316bb4ced5e0ab3971d0ae), [whitespace follow-up](https://github.com/python/cpython/commit/9f52b443c002cccfb54bda0706a9276b6b4a109d) |

The chunk probes supply enough body bytes for the permissive parser to succeed.
For example, `1_f` includes 31 bytes. A shorter body would make an affected parser
raise the same incomplete-read exception as a rejecting parser and hide the finding.

## Reading the evidence

Each image job uploads `runtime-security-<commit>-<job>` containing
`runtime-security.json`. Its summary records the image reference, local image ID,
interpreter version, each result and the SHA-256 of the actual installed module
source. The full JSON includes all individual cases and upstream fix links.

| Result | Meaning |
| --- | --- |
| `affected_behavior_observed` | At least one malformed-input case reproduced the tracked behavior, with valid controls passing. |
| `affected_behavior_not_observed` | All tested malformed inputs were handled as expected, and the controls passed. This is limited to these cases. |
| `inconclusive` | A control failed, a probe raised an unexpected exception, or the case set was incomplete. Investigate the evidence rather than treating this as a clean result. |

A completed probe returns 0 even if affected behavior is observed: this is a
reporting step for known findings. An inconclusive or unreadable-runtime probe
returns 2 and fails the job. The existing Grype policy remains authoritative for
the scan gate (`critical`, `only-fixed`, `fail-build`). The probe adds no exclusions
and does not assert that application exploitability has been demonstrated.

For a local interpreter:

```sh
uv run python scripts/probe_runtime_security.py > runtime-security.json
```

This command describes that interpreter, not the Docker image. The optional
`--image-ref` and `--image-id` arguments are provenance supplied by the invoking
workflow; the script does not independently authenticate those values.

When a supported runtime update becomes available, compare its case results and
module hashes, then run the application, SDK, persistence and load checks and
review the new Grype SARIF before closing #194. A clean probe alone is insufficient
to conclude that every affected path has been remediated.
