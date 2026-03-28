# Market Pulse Bot

## Project Overview

Transparent AI-powered Twitter bot that aggregates financial data from multiple sources, detects cross-market patterns, and generates analytical tweets that connect dots across markets:
1. **Polymarket** - Prediction market odds shifts, volume spikes (financially filtered)
2. **Crypto** - Top movers, BTC/ETH dominance, volume spikes (CoinGecko)
3. **S&P 500 / Macro** - US indices, VIX, Treasury yields, DXY, gold, oil (Yahoo Finance / yfinance)
4. **Sentiment** - Crypto Fear & Greed Index (alternative.me)
5. **Economic Calendar** - Upcoming FOMC, CPI, NFP dates for event context

## Architecture

```
Sources (Polymarket + CoinGecko + yfinance + Fear&Greed + Calendar)
  -> Aggregator (parallel fetch + dedup + alert detection)
  -> Correlation Engine (detect cross-source narratives: risk-on/off, divergences, policy-to-price)
  -> Pipeline (rank -> generate tweets via LLM -> score -> generate charts)
  -> Scheduler (4-8 tweets/day + instant alerts on big moves)
  -> Publisher (X/Twitter API via tweepy)
```

- **Dashboard**: Flask + HTMX at port 5001 (gunicorn, 1 worker, 4 threads)
- **Database**: SQLite at `data/quantum_brief.db`
- **LLM**: Mistral (primary), Groq/Llama 3.3 70B (fallback)
- **Charts**: matplotlib-generated images (dark theme, 1200x628px)
- **Deploy**: Oracle Cloud Free Tier VM, systemd service

## Key Files

| Component | Path |
|-----------|------|
| CLI orchestrator | `main.py` |
| Pipeline logic | `pipeline.py` |
| Config (prompts, templates, keywords) | `config.py` |
| DB schema & queries | `storage/database.py` |
| Polymarket fetcher | `sources/polymarket_fetcher.py` |
| Crypto fetcher | `sources/crypto_fetcher.py` |
| Macro fetcher | `sources/macro_fetcher.py` |
| Sentiment fetcher | `sources/sentiment_fetcher.py` |
| Economic calendar | `sources/calendar_fetcher.py` |
| Correlation engine | `sources/correlation_engine.py` |
| Source aggregator | `sources/aggregator.py` |
| LLM generation | `generator/mistral_generator.py` |
| Provider routing | `generator/provider_router.py` |
| Quality scoring | `scoring/quality_scorer.py` |
| Chart generation | `images/chart_generator.py` |
| Alert detection | `alerts/detector.py` |
| X/Twitter publishing | `publisher/x_publisher.py` |
| Scheduler | `scheduler/scheduler.py` |
| Dashboard app | `dashboard/app.py` |
| Dashboard routes | `dashboard/routes/` |

## Conventions

- Every tweet MUST end with "Not financial advice."
- Never include buy/sell recommendations in generated content
- System prompt and templates live in `config.py`
- All market data snapshots stored in `market_data` table for delta computation
- Alert thresholds: >8% odds shift (Polymarket), >4% price move (crypto), >2% index move (macro)
- Polymarket markets filtered by financial keywords (no sports/entertainment)
- Correlation engine detects 5 pattern types: risk-on/off, divergence, policy-to-price, volatility gap, dominance rotation
- 10 generation templates with weighted random selection; cross-source templates have highest weights
- Scoring rewards cross-source synthesis (+12 for 2 sources, +20 for 3+) and connection language (+8)
- Auto-approve threshold: 68 (quality score). Auto-reject below 25.
- Charts: dark theme, 6 types (line, bar, odds, pie, comparison, dual_overlay)
- Macro tickers: S&P 500, NASDAQ, DJI, VIX, 3M/5Y/10Y/30Y Treasury, DXY, Gold, Oil
- Free tier APIs only: Polymarket Gamma (no auth), CoinGecko (demo key), yfinance (no auth), alternative.me Fear&Greed (no auth)

## Commands

```bash
python main.py fetch      # Fetch financial data + generate tweets
python main.py review     # Review pending tweets
python main.py post       # Post next approved tweet
python main.py run        # Start autopilot daemon
python main.py status     # Show queue stats
python main.py alerts     # Show pending market alerts
python main.py kill       # Emergency stop all API calls
python main.py limits     # Show API usage limits
python run_dashboard.py   # Start dashboard locally
```

## Environment Variables

```
MISTRAL_API_KEY=          # Primary LLM
GROQ_API_KEY=             # Fallback LLM (free)
X_API_KEY=                # Twitter API
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
COINGECKO_API_KEY=        # Optional, for higher rate limits
DASHBOARD_USER=           # Dashboard login
DASHBOARD_PASSWORD=
FLASK_SECRET_KEY=
```

## Instructions pour Claude Code

- Mettre a jour ce fichier CLAUDE.md apres chaque changement architectural majeur
  (nouvelle dependance, refactoring significatif, nouvelle convention adoptee)
- Ne pas modifier la section "Instructions pour Claude Code"
