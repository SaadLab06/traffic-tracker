# Acquisition Scraper Service

FastAPI service used by n8n to filter French ecom stores through a 4-stage acquisition funnel.

## Endpoints

- `POST /check-marketplaces` — Stage 0.5: DotMarket + Flippa cross-reference
- `POST /check-activity`     — Stage 1: blog freshness + Trustpilot velocity
- `POST /check-traffic`      — Stage 2: Semrush 6-month trend
- `GET  /health`             — container healthcheck

## Local development

```bash
python -m venv .venv
.venv/Scripts/activate           # or .venv/bin/activate on Linux
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
uvicorn app.main:app --reload --port 8000
pytest
```

## Deploy to Hostinger VPS

Assumes Traefik (network `web`) and n8n already running.

```bash
scp -r scraper-service/ user@vps:/srv/scraper-service/
ssh user@vps
cd /srv/scraper-service
cp .env.example .env     # then fill in SEMRUSH_API_KEY + SCRAPER_DOMAIN
docker compose up -d --build
docker compose logs -f scraper
curl -H "Host: scraper.yourdomain.com" https://scraper.yourdomain.com/health
```

### Traefik snippet

If Traefik is configured via a static file, no additions are needed — the compose labels register the router automatically. For the dynamic file config variant:

```yaml
http:
  routers:
    scraper:
      rule: "Host(`scraper.yourdomain.com`)"
      entryPoints: [websecure]
      tls:
        certResolver: le
      service: scraper@docker
```

## Re-run / tuning runbook

- **Clear marketplace cache**: `rm -r scraper-service/.cache/dotmarket scraper-service/.cache/flippa`
- **Clear Semrush cache**: `rm -r scraper-service/.cache/semrush`
- **Tune PELT penalty**: `pen=2` (currently calibrated for ruptures 1.0.6/1.1.9 — see comment above the `algo.predict` call) in `app/services/pattern_analyzer.py`. Raise to reduce false breaks, lower to detect gentler slowdowns. Run `pytest tests/test_pattern_analyzer_pelt.py` after any change.
- **Tune stage1 threshold**: `stage1_verdict` cutoff in `app/services/pattern_analyzer.py` (default 40). Raising narrows the funnel.

## Library wrapping contracts

| Module | Wraps | Test file |
|---|---|---|
| `blog_fetcher` | `feedparser` + `lxml` + `crawl4ai` | `test_blog_fetcher_*.py` |
| `pattern_analyzer` | `ruptures.Pelt(model="rbf")` | `test_pattern_analyzer_*.py` |
| `review_scraper` | `trustpilot-scraper` | `test_review_scraper.py` |
| `trend_analyzer` | `scipy.stats.linregress` | `test_trend_analyzer.py` |
| `semrush_client` | HTTP + `tenacity` + `TTLCache` | `test_semrush_client.py` |

Do **not** replace these libraries without updating both code and tests together.
