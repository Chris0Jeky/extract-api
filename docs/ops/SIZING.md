# Sizing extract-api

Measured, not guessed. Every number below comes from `scripts/load_test.py`, run by
`.github/workflows/loadtest.yml` on GitHub-hosted Linux (ubuntu-latest). The target is the
production image with a volume at `/data` and swap disabled, so an out-of-memory kill is real. The
service runs in fixture mode with a simulated provider latency. Each concurrency level sends 40
requests. The mix is the text invoice plus generated text PDFs of 1, 10, 50 and 999 pages (the
largest is 9.1 MB, about 4.2 million characters, just under the API's caps), each request with a
fresh `Idempotency-Key`. "Clients" is the number of requests the load test keeps open at once;
the server admits at most `EXTRACT_MAX_CONCURRENCY` of them. To refresh the numbers, re-run the
workflow from the Actions tab.

## Recommendation

**Render Starter (512 MB, 0.5 CPU) with `EXTRACT_MAX_CONCURRENCY=4`.** That is the image default
and the value `render.yaml` sets.

- Memory, not CPU, sets the cap. With anyio's default of 40, 512 MB was OOM-killed at 8 clients.
  With the cap at 4, peak memory stayed between 353 and 378 MiB from 4 up to 32 clients, with no
  errors.
- The cap admits requests before their bodies are read (`ExtractAdmission` in `api/main.py`), so
  a queued request costs a connection, not its payload. That is why memory stops growing beyond
  the cap.
- Capacity at that cap on 0.5 CPU: about 1.56 requests a second with a 2-second provider and 0.44
  with an 8-second one. That is 38,000 to 135,000 extractions a day, far beyond a portfolio API's
  load. Excess requests wait; they do not fail.
- Move up when queueing shows in the access logs for a sustained period: `duration_ms` (which
  includes the wait) well above the provider's own latency. On Render the next size is `1c-2g`
  (2 GB, 1 CPU; Render has no 1 GB size). On Railway, 1 GB. Use a cap of 16 on either: measured
  below at a 763 MiB peak on 1 GB.

## Admission-gated runs (the shipped design)

Run [37784951654](https://github.com/Chris0Jeky/extract-api/actions/runs/37784951654)
(2026-10-08, PR #139 head 7cabc39). All four legs: 0% errors, no OOM.

**512 MB, 0.5 CPU, cap 4.**

| Clients | 2 s provider: req/s | p50 ms | p95 ms | Peak MiB | 8 s provider: req/s | p95 ms | Peak MiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.43 | 2012 | 3454 | 212 | 0.12 | 10714 | 214 |
| 4 | 1.57 | 2087 | 3552 | 353 | 0.44 | 10837 | 313 |
| 8 | 1.56 | 4373 | 6118 | 354 | 0.44 | 21234 | 318 |
| 16 | 1.55 | 9319 | 11068 | 378 | 0.44 | 37478 | 336 |
| 32 | 1.57 | 12739 | 19859 | 378 | 0.44 | 72071 | 361 |

**1 GB, 1 CPU, cap 16.**

| Clients | 2 s provider: req/s | p50 ms | p95 ms | Peak MiB | 8 s provider: req/s | p95 ms | Peak MiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.44 | 2015 | 3344 | 213 | 0.12 | 9026 | 212 |
| 4 | 1.59 | 2048 | 3390 | 347 | 0.47 | 9026 | 311 |
| 8 | 2.74 | 2115 | 4037 | 517 | 0.93 | 9151 | 453 |
| 16 | 2.90 | 2666 | 8216 | 709 | 1.53 | 11141 | 720 |
| 32 | 2.89 | 5209 | 11202 | 763 | 1.53 | 19125 | 761 |

## How we got here

1. **No effective cap** (anyio's default of 40). Run
   [37779120364](https://github.com/Chris0Jeky/extract-api/actions/runs/37779120364). On 512 MB
   the container was OOM-killed at 8 clients (473 MiB, then dead) with a 2 s provider, and at 16
   clients with an 8 s provider. 1 GB survived 32 clients at 1002 MiB.
2. **Cap 4 on the threadpool.** Run
   [37782784598](https://github.com/Chris0Jeky/extract-api/actions/runs/37782784598). There was no
   OOM, but 512 MB still climbed from 338 MiB at 4 clients to 443 MiB at 32. Queued requests had
   already read their bodies before waiting for a thread, a flaw review caught.
3. **Cap 4 at admission, before the body is read** (the tables above). Memory levels off at the cap.

## What the numbers say

- The process sits at about 210 MiB with one request in flight. Each further in-flight request of
  this mix adds roughly 25 to 45 MiB: the base64 body, the decoded PDF and its extracted text are
  all held at once. The figure falls as concurrency rises, because the large PDF is one request in
  five.
- One CPU saturates near 3 requests a second with a 2-second provider, and 0.5 CPU near 1.6. PDF
  text extraction is CPU work. Past that point, extra concurrency only adds waiting.
- Headroom at the recommended caps: about 134 MiB on 512 MB (378 peak) and about 260 MiB on 1 GB
  (763 peak).

## Limits of this evidence

- Peaks come from the cgroup's `memory.peak`, which counts page cache, so they are upper bounds on
  the process's own memory.
- Fixture mode makes no network call, so the provider SDKs' clients and connection pools are not
  in these numbers. They load once per process; expect tens of MiB on top, which the headroom
  absorbs.
- The mix is deliberately PDF-heavy, with one near-cap document in five. Traffic made only of
  near-cap PDFs would use more per in-flight request, about 70 MiB at worst by these figures: 4
  in flight is then about 490 MiB, which fits 512 MB only narrowly, so lower the cap to 3 if that
  is the expected traffic. Mostly-text traffic uses far less.
- GitHub's runners are not Render's hardware. Treat the CPU figures as relative. The memory
  figures carry over, because they measure the process itself.
