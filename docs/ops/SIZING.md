# Sizing extract-api

Measured, not guessed: the numbers below come from `scripts/load_test.py` run by
`.github/workflows/loadtest.yml` on GitHub-hosted Linux (ubuntu-latest), against the production
image with a volume at `/data`, swap disabled (an OOM is a real kill), in fixture mode with a
simulated provider latency. Re-run the workflow from the Actions tab to refresh them.

## Recommendation

**Render Starter (512 MB, 0.5 CPU) with `EXTRACT_MAX_CONCURRENCY=4`.** This is the image default
and the value `render.yaml` sets.

- Memory, not CPU, sets the cap. At 4 in flight the container peaked at 351 MiB of 512 MiB. At 8
  in flight the uncapped container was OOM-killed.
- Capacity at that cap: about 1.3 requests a second with a 2-second provider, about 0.46 a second
  with an 8-second provider. That is 40,000 to 110,000 extractions a day, far above a portfolio
  API's load. Excess requests queue rather than fail.
- Move up when queueing shows in the access logs (`duration_ms` well above the provider's own
  latency) for a sustained period, not before. On Render the next size is `1c-2g` (2 GB, 1 CPU;
  Render has no 1 GB size), where a cap of 16 is measured below with room to spare. On Railway, 1
  GB with a cap of 16.

## Baseline: the old default (40) had no effective cap

Run [37779120364](https://github.com/Chris0Jeky/extract-api/actions/runs/37779120364)
(2026-10-08), PR #139 head before the cap changed. Each level sends 40 requests; the mix is the
text invoice plus generated text PDFs of 1, 10, 50 and 999 pages (the largest is 9.1 MB, about
4.2 million characters, just under the API's caps), each with a fresh `Idempotency-Key`.

**512 MB, 0.5 CPU, 2 s provider: OOM-killed at 8 in flight.**

| In flight | req/s | p50 ms | p95 ms | Errors | Peak MiB |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.39 | 2015 | 4718 | 0% | 219 |
| 2 | 0.73 | 2113 | 4707 | 0% | 257 |
| 4 | 1.31 | 2255 | 5045 | 0% | 351 |
| 8 | 2.32 | 2716 | 10050 | 22.5% | 473, then killed |

**512 MB, 0.5 CPU, 8 s provider: OOM-killed at 16 in flight** (peak 501 MiB at 8; every request
at 16 failed because the process was dead).

**1 GB, 1 CPU, 2 s provider: survived 32 in flight, peaking at 1002 MiB.**

| In flight | req/s | p50 ms | p95 ms | Errors | Peak MiB |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.44 | 2015 | 3312 | 0% | 216 |
| 4 | 1.59 | 2063 | 3359 | 0% | 349 |
| 8 | 2.77 | 2127 | 3877 | 0% | 502 |
| 16 | 2.97 | 2731 | 7932 | 0% | 708 |
| 32 | 2.91 | 4530 | 11210 | 0% | 1002 |

**1 GB, 1 CPU, 8 s provider:** 0.47 req/s at 4, 1.49 at 16, 2.03 at 32; peak 1003 MiB at 32.

## What the numbers say

- The process idles at about 200 MiB and each in-flight request of this mix adds 35 to 45 MiB:
  the base64 body, the decoded PDF and its extracted text are all held at once.
- One CPU saturates at about 3 requests a second with a 2-second provider: PDF text extraction is
  CPU work. Past that, more concurrency only adds queueing and memory.
- A cap of 4 on 512 MB leaves about 160 MiB of headroom; 16 on 1 GB leaves about 300 MiB.

## Limits of this evidence

- Fixture mode makes no network call, so the provider SDKs' clients and connection pools are not
  in these numbers. They load once per process; expect tens of MiB on top, which the headroom
  above absorbs.
- The mix is deliberately PDF-heavy and includes a near-cap document. Mostly-text traffic uses
  far less memory per request, so these caps are conservative.
- GitHub's runners are not Render's hardware. Treat CPU figures as relative; the memory figures
  carry over because they are the process's own usage.
