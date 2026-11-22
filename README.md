# MarketPulse X: an LLM pipeline that turns cross-market data into published analysis

A transparent, AI-run X (Twitter) account that read five financial data sources, spotted
connections across markets, and published short data-backed analyses. Built and operated by **Francesco Rochet** in March 2026.

**Status: discontinued.** The system ran in production on a live X account and did its job
technically. It was stopped for business reasons: audience engagement stayed too low to justify
the cost of the X API.

---

## The problem

Market commentary usually looks at one asset class at a time. The interesting stories sit
*between* markets: a prediction-market odds shift that front-runs a move in Treasury yields, or a
crypto rally that diverges from equities. The question was whether an automated pipeline could:

- find those cross-market connections reliably;
- explain them in a format people read;
- do it at a quality level that needs little human review.

## What was built

```
Sources ──> Aggregator ──> Correlation engine ──> Generation ──> Scoring ──> Review ──> Publisher
```

| Stage | What it does |
|---|---|
| **Sources** | Polymarket (odds shifts and volume spikes, filtered to financial markets); CoinGecko (crypto movers, BTC/ETH dominance); Yahoo Finance (S&P 500, NASDAQ, VIX, Treasury curve, DXY, gold, oil); Fear & Greed index; economic calendar (FOMC, CPI, NFP) |
| **Aggregator** | Parallel fetch, deduplication, market snapshots stored for delta computation, alert detection on large moves (>8 % odds shift, >4 % crypto move, >2 % index move) |
| **Correlation engine** | Detects five cross-source patterns: risk-on / risk-off, divergence, policy-to-price, volatility gap, dominance rotation |
| **Generation** | LLM writes the post from ten weighted templates. Mistral is the primary model; Groq (Llama 3.3 70B) is the fallback, through a provider router |
| **Scoring** | Seven-component quality score: substance, tone, data accuracy, variety, readability, format, and an "anti-AI" score that penalises generic phrasing. Cross-source synthesis is rewarded. Posts above 68 are auto-approved, posts below 25 rejected, the rest go to human review |
| **Charts** | Matplotlib charts in six types, attached to posts |
| **Publisher and scheduler** | 4 to 8 posts a day plus instant alerts on big moves, through the X API |
| **Dashboard** | Flask and HTMX, seven pages: command centre, markets, review queue, pipeline history, analytics, engagement, settings (quality thresholds, API budget, safety) |
| **Guardrails** | Every post ends with "Not financial advice."; no buy or sell recommendations; API budget limits, alerts and a kill switch |

Deployed on an Oracle Cloud free-tier VM as a systemd service.

## What happened, and what I learned

- **Technically, it worked.** The pipeline fetched, correlated, generated, scored and published
  on its own, and the review queue kept a human in the loop for borderline posts.
- **Commercially, it did not.** Engagement stayed low. Generic market commentary is a crowded
  space, and an automated account has no personal voice to build an audience on.
- **Unit economics decided it.** The cost of the X API outweighed what the account brought in. The
  right call was to stop, not to keep optimising the pipeline.
- **The hard part was quality control, not generation.** Most of the iteration went into the
  scoring model, the freshness rules (stale data, expired markets) and the review workflow. Making
  an LLM write is easy; making its output reliably worth publishing is not.

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env          # Mistral, Groq, X API, CoinGecko keys, dashboard login
python main.py fetch          # fetch data and generate posts
python main.py review         # review pending posts
python main.py run            # autopilot daemon
python run_dashboard.py       # dashboard on port 5001
```

All market data sources are free tiers. Posting requires X API credentials.
