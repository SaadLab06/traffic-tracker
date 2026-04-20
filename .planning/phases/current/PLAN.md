# PLAN: Traffic Tracker Performance Diagnostic & Remediation

**Date:** 2026-04-20  
**Status:** REVISED — Architect must-fix items incorporated  
**Mode:** RALPLAN-DR (Deliberate)

---

## RALPLAN-DR Summary

### Principles (honored by every option chosen)

1. **Verify before optimize** — Phase 0 correctness gate blocks all performance work. No point making a broken system faster.
2. **Measure before optimize** — Every performance change must embed or be accompanied by its own timing instrumentation. No guessing.
3. **Fail loud, never silently** — Silent empty-list returns from Flippa/DotMarket are the current cardinal sin. Every failure must produce an actionable log.
4. **Batched HTTP over looped HTTP** — The dominant bottleneck (Stage 2 serial loop) exists because of unbatched design. Default to batch.
5. **Minimal blast radius** — Production is live. Each phase is independently deployable and rollback-safe.

### Decision Drivers (top 3)

| # | Driver | Weight |
|---|--------|--------|
| 1 | **Correctness first** — User explicitly asked "does it actually work?" | HIGH |
| 2 | **Observability ROI** — Adding structured logs is cheap, unblocks every other decision, zero regression risk | HIGH |
| 3 | **Minimize VPS infra risk** — System is deployed behind Traefik on shared n8n_net; changes must not break other services | MEDIUM |

### Viable Options — Phase 2 (Stage 2 bottleneck: 15-23 min for 500 URLs)

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A: Batch at scraper** | `/check-traffic` already accepts N URLs — swap serial `for` loop for `asyncio.gather` with module-level semaphore (5-10 concurrent); fix n8n to aggregate URLs before calling | Single n8n call; fine-grained concurrency control; retry per-URL; scraper owns rate limiting; NO API contract change needed | Must handle partial failures; n8n needs aggregation node before `n-traffic` |
| **B: Parallelize in n8n** | Split-In-Batches node with `batchSize=10`, parallel item execution | No scraper changes; quick n8n-only fix | n8n parallel execution is limited and flaky; no visibility into rate limits; harder to debug; n8n CE may not support true parallelism |
| **C: Semrush batch API** | Use Semrush's native batch/bulk endpoint if it exists | Fewest calls; best rate-limit compliance | Likely does not exist for the analytics endpoint used; would require API research; vendor lock-in deepens |

**Recommendation:** Option A dominates. The endpoint already accepts a URL list — the change is purely internal (serial loop to `asyncio.gather`). It gives us control over concurrency (critical for Semrush rate limits), clean error isolation, and structured logging. No breaking API change; n8n just needs to aggregate candidates before `n-traffic` (same pattern as `n-aggregate` for Stage 0.5). Option B is a fallback if scraper changes are blocked. Option C is speculative — invalidated unless Semrush docs confirm a batch endpoint exists (unlikely for domain analytics).

### Viable Options — Phase 3 (Flippa correctness if broken)

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A: Playwright for Flippa** | Use headless Playwright (already in requirements.txt) to render Flippa JS | Highest reliability; handles any JS-rendered content | Heavy runtime (~2-5s per fetch); increases container memory; Docker image grows ~200MB |
| **B: Flippa JSON API** | Reverse-engineer Flippa's internal XHR/JSON endpoint via DevTools | Lightest runtime; fastest fetch; no browser dependency | Fragile — Flippa can change endpoints without notice; requires manual discovery |
| **C: Accept gaps + alert** | Keep current scraper, add monitoring alert when catalog returns 0 listings | Zero code change; cheapest | Defeats the purpose — user wants correctness |

**Recommendation:** Attempt Option B (JSON API probe) **first** — it is a 15-minute investigation already scheduled as Phase 0 task 3, and could eliminate the need for a browser entirely. If the probe fails or the endpoint is unstable, proceed with Option A (Playwright) for reliability. The catalog fetch happens once per 6h (cache TTL), so Playwright's 2-5s overhead is negligible amortized. Option C is explicitly invalidated — user's primary ask is "does it work?"

### Pre-mortem (3 failure scenarios, 2 weeks post-deploy)

| # | Scenario | Likelihood | Mitigation |
|---|----------|-----------|------------|
| 1 | **Semrush rate-limit ban** — Parallel Stage 2 calls (Option A) exceed Semrush's undocumented rate limit, IP gets throttled or banned | MEDIUM | Semaphore default = 5 concurrent; add exponential backoff on 429; add `rate_limit_hit` log field; make concurrency configurable via env var |
| 2 | **Observability log leak** — Structured logs include full URLs which may contain sensitive query params or client domains visible in log aggregator | LOW | Sanitize query params from logged URLs; ensure logs stay on VPS (no external log shipper without review); add `[REDACTED]` for query strings |
| 3 | **Phase 0 false green** — Smoke test uses a URL that happens to be listed today but delists tomorrow; team assumes correctness is fine when it silently breaks again | MEDIUM | Phase 5 integration tests run nightly with freshly-scraped "known listed" URLs; add a canary alert if catalog_size drops to 0 for either marketplace |

### Expanded Test Plan

| Layer | Scope | Details |
|-------|-------|---------|
| **Unit** | Batch handlers | Empty input returns []; 1 URL works; 200 URLs (max batch) works; partial failure (1 of N URLs times out) returns results for others + error for failed one |
| **Integration** | Real services | `@pytest.mark.integration` — hit real DotMarket, real Flippa, real Semrush (1 URL each); assert response shape; excluded from CI, run locally/nightly |
| **E2E** | n8n workflow | 10-URL fixture through full pipeline; measure wall clock; assert < 2 min for 10 URLs (implies < 12 min for 500) |
| **Observability** | Log verification | After Phase 1 deploy, run 10-URL request, parse JSON logs, assert fields: `catalog_fetch_ms`, `catalog_size`, `cache_hit`, `total_ms`, `request_id` |
| **Load** | 500-URL benchmark | Before/after comparison; target: 500 URLs < 8 min total (down from 22-30 min) |

---

## ADR (Architectural Decision Record)

**Decision:** Parallelize Stage 2 internally (Option A) with asyncio.gather + module-level semaphore; probe Flippa JSON API first (Option B), fall back to Playwright (Option A) if probe fails; add structured observability in parallel.

**Drivers:** Correctness-first mandate; need for rate-limit control at scraper layer via module-level singleton semaphore; `/check-traffic` already accepts a URL list (no API contract change).

**Alternatives considered:**
- n8n-side parallelism (Phase 2 Option B) — rejected: limited control, debugging difficulty, n8n CE parallel support uncertain.
- Semrush batch API (Phase 2 Option C) — invalidated: no evidence such endpoint exists for domain analytics.
- Flippa JSON API (Phase 3 Option B) — attempted first as 15-min probe; if stable, eliminates Playwright dependency entirely.
- Per-request semaphore — rejected: concurrent n8n runs (retry, overlap, manual test) would multiply effective concurrency past rate limit.

**Why chosen:** Phase 2 Option A requires zero API contract change — the endpoint already accepts N URLs, we only swap serial iteration for `asyncio.gather`. Module-level semaphore ensures global rate-limit compliance regardless of concurrent callers. n8n change is just an aggregation node (existing pattern). Flippa JSON probe is low-cost and may avoid Playwright entirely.

**Consequences:**
- Scraper container memory increases slightly if Playwright is needed for Flippa.
- `playwright>=1.47` added as explicit top-level dependency (not relying on transitive install from crawl4ai).
- Semrush concurrency must be tuned post-deploy based on rate-limit signals.
- n8n workflow gets an aggregation node before `n-traffic` (non-breaking; same pattern as `n-aggregate`).

**Follow-ups:**
- Monitor Semrush rate-limit logs for 1 week post-deploy; adjust semaphore if needed.
- Set up nightly integration test cron.
- Revisit Flippa approach if Playwright fetches start timing out (selector drift).
- If Flippa JSON API probe succeeds, remove Playwright from Phase 3 scope entirely.

---

## Actionable Plan

### Phase 0 — Verify Correctness (BLOCKING GATE)

**Objective:** Determine if the system actually returns correct results today.

**Tasks:**
1. Identify 2 URLs currently listed on Flippa and 2 on DotMarket (manual check or curl their catalog pages).
2. Hit deployed `/check-marketplaces` with 5 URLs (2 known Flippa, 2 known DotMarket, 1 unlisted control).
3. Capture raw HTML response from Flippa listings page via `curl` — inspect whether listing data is in static HTML or requires JS.
4. Record verdict: "correctness OK" or "correctness broken, root cause = [JS rendering | selector drift | redirect failure | other]".

**Acceptance criteria:**
- Written verdict document with evidence (HTTP status codes, response bodies, curl output).
- If broken: root cause identified with specific line numbers in scraper code.
- Decision: proceed to Phase 1 (if OK) or Phase 1 + Phase 3 in parallel (if broken).

**Estimated time:** 30 min

---

### Phase 1 — Add Observability (for `/check-marketplaces` and `/check-activity`)

**Objective:** Instrument non-traffic scraper endpoints so we measure, not guess. (Phase 2 self-embeds timing for `/check-traffic`.)

**Depends on:** Phase 0 (correctness gate). Runs in **parallel** with Phase 2.

**Tasks:**
1. Add timing wrapper to `/check-marketplaces`: log `catalog_fetch_ms` (per marketplace), `catalog_size`, `cache_hit`, `match_loop_ms`, `total_ms`, `input_url_count`.
2. Add timing wrapper to `/check-activity`: log `total_ms`, `input_url_count`.
3. Add `request_id` (UUID) header propagation — n8n sends `X-Request-ID`, scraper logs it on every line (applies to ALL endpoints including `/check-traffic`).
4. Add alert log (WARNING level) when any catalog returns 0 listings.

**Acceptance criteria:**
- Run 10-URL request against `/check-marketplaces` and `/check-activity`; parse JSON logs; all fields present.
- Zero-listing catalog triggers a WARNING log line.
- No behavioral change to existing responses.

**Estimated time:** 2-3 hours

---

### Phase 2 — Fix Stage 2 Bottleneck (Batch Traffic Checks)

**Objective:** Reduce 500-URL Stage 2 from 15-23 min to under 5 min.

**Depends on:** Phase 0 (correctness gate). Does NOT depend on Phase 1 — Phase 2 self-embeds timing logs (`per_url_ms`, `total_ms`) for its own endpoint.

**Tasks:**
1. Create a **module-level `asyncio.Semaphore`** singleton in `app/services/semrush_client.py` (or new `app/services/_rate_limit.py`), instantiated once at import time, shared across all concurrent requests. Concurrency N is configurable via `SEMRUSH_CONCURRENCY` env var (default: 5).
2. Replace the serial `for url in req.urls` loop in `/check-traffic` with `asyncio.gather` gated by the module-level semaphore. The endpoint already accepts a `urls` list — no API contract change required.
3. Return per-URL results including individual success/failure status (partial failure isolation) and `duration_ms` per result.
4. In n8n workflow: add an aggregation node before `n-traffic` (same pattern as `n-aggregate` for Stage 0.5) so that all filtered Stage 1 candidates are sent in a single POST rather than 1-URL-at-a-time. Update `n-traffic` jsonBody to pass the full URL list + enrichment map. Remove the `n-flatten` workaround comment ("always 1 URL here").
5. Add structured log fields: `semaphore_concurrency`, `total_ms`, `success_count`, `failure_count`, `per_url_ms` (list).

**Acceptance criteria:**
- 500 URLs complete in < 5 min (at concurrency=5, ~2.5s/call = 500/5 * 2.5 = 4.2 min).
- Single URL failure does not fail the batch.
- Logs show `semaphore_concurrency`, `total_ms`, `success_count`, `failure_count`.
- Unit test asserts the same semaphore object is used across two simulated concurrent requests (verifies module-level singleton).

**Estimated time:** 4-6 hours

---

### Phase 3 — Fix Flippa Correctness (if Phase 0 confirms broken AND Phase 0 task 3 JSON API probe fails)

**Objective:** Make Flippa catalog fetch return actual listings.

**Tasks:**
1. Add `playwright>=1.47` (pin exact version used) as an **explicit** top-level dependency in `requirements.txt`. Do not rely on crawl4ai's transitive install — if crawl4ai is removed/swapped, Playwright must remain available independently. The existing Dockerfile `RUN playwright install chromium` line stays.
2. Replace `httpx` fetch in `flippa_scraper.py` with Playwright headless browser fetch.
3. Wait for JS render (networkidle or specific selector), then extract listing data.
4. Keep 6h cache TTL — Playwright only fires on cache miss.
5. Parallelize DotMarket + Flippa fetches with `asyncio.gather` (fixes serial 76s worst-case to ~38s).
6. Add `catalog_source: "playwright"` to structured logs for Flippa fetches.

**Acceptance criteria:**
- `/check-marketplaces` with a known-listed Flippa URL returns `FOR_SALE`.
- Catalog size > 0 after Playwright fetch (logged).
- Cache hit path unchanged (still ~0ms).
- Docker image builds successfully with Playwright browsers installed.

**Estimated time:** 3-4 hours

---

### Phase 4 — Batch Google Sheets Writes

**Objective:** Reduce sheet write time from ~7.5 min to ~30s.

**Tasks:**
1. In n8n workflow, replace per-row Google Sheets write with `spreadsheets.values.batchUpdate` (single API call for all rows).
2. Structure output data as a 2D array matching sheet columns.
3. Handle partial failures (if batch update fails, log which rows failed).

**Acceptance criteria:**
- 500 rows written in < 60s (single API call).
- Data integrity: spot-check 10 random rows match expected values.
- Error handling: if batch fails, error is logged with row context.

**Estimated time:** 2-3 hours

---

### Phase 5 — Integration Test Suite

**Objective:** Catch silent failures before they reach production.

**Tasks:**
1. Create `tests/integration/` directory with `conftest.py` (marks, env var gating).
2. `test_flippa_live.py` — fetch real Flippa catalog, assert > 0 listings.
3. `test_dotmarket_live.py` — fetch real DotMarket catalog, assert > 0 listings.
4. `test_semrush_live.py` — fetch traffic for 1 known domain, assert response shape.
5. `test_e2e_pipeline.py` — 10-URL fixture through full n8n workflow, assert completion < 2 min.
6. Mark all with `@pytest.mark.integration`, excluded from default `pytest` run.

**Acceptance criteria:**
- `pytest -m integration` passes when run against live services.
- CI default run (`pytest`) skips integration tests.
- README documents how to run integration tests locally.

**Estimated time:** 3-4 hours

---

## Success Criteria (verifiable)

| # | Criterion | Verification method |
|---|-----------|-------------------|
| 1 | Stage 0.5 returns at least one `FOR_SALE` verdict for a known-listed URL | Phase 0 smoke test |
| 2 | End-to-end 500-URL run completes in under 8 minutes (down from 22-30) | Phase 2 + 4 load test |
| 3 | Each scraper endpoint logs `duration_ms`, `cache_hit`, `request_id` in structured JSON | Phase 1 log parse |
| 4 | Zero-listing catalog triggers WARNING log | Phase 1 alert test |
| 5 | Single URL failure in batch does not fail entire batch | Phase 2 unit test |
| 6 | Integration test suite passes with `-m integration` against real services | Phase 5 CI run |
| 7 | Google Sheets 500-row write completes in < 60s | Phase 4 timing measurement |

---

## Execution Order & Dependencies

```
Phase 0 (GATE) ──┬──> Phase 1 (observability for /check-marketplaces, /check-activity)
                 │          │
                 ├──> Phase 2 (Stage 2 batch — self-embeds timing for /check-traffic)
                 │          │
                 │          └──> Phase 4 (Sheets batch)
                 │
                 └──> Phase 3 (only if Phase 0 finds Flippa broken AND JSON API probe fails)
                                    │
                                    └──> Phase 5 (integration tests, after all fixes land)
```

Phase 0 blocks everything. Phase 1 and Phase 2 can run **in parallel** after Phase 0 — Phase 1 covers `/check-marketplaces` and `/check-activity` observability; Phase 2 self-embeds its own timing logs for `/check-traffic`. Phase 3 is conditional. Phase 5 is last (tests the final state).

---

## Total Estimated Effort

| Phase | Hours | Risk |
|-------|-------|------|
| 0 | 0.5 | LOW |
| 1 | 2-3 | LOW |
| 2 | 4-6 | MEDIUM |
| 3 | 3-4 | MEDIUM |
| 4 | 2-3 | LOW |
| 5 | 3-4 | LOW |
| **Total** | **15-21h** | — |

**Expected outcome:** 500-URL pipeline drops from 22-30 min to under 8 min, with correctness verified and observable.
