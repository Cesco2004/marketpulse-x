import os
from dotenv import load_dotenv

load_dotenv()

# Mistral API
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

# Groq API (free tier fallback - Llama 3.3 70B, 6000 req/day)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# X / Twitter
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")

# Schedule
POST_HOUR = int(os.getenv("POST_HOUR", "14"))
POST_MINUTE = int(os.getenv("POST_MINUTE", "0"))

# CoinGecko API (optional, higher rate limits with key)
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")

# Legacy RSS feeds (deprecated - financial data comes from APIs now)
RSS_FEEDS = []

# Source categories (financial)
SOURCE_CATEGORIES = {
    "polymarket": {"label": "Polymarket Odds", "icon": "📊", "color": "#818cf8"},
    "crypto": {"label": "Crypto Markets", "icon": "₿", "color": "#f7931a"},
    "sp500": {"label": "S&P 500 / Indices", "icon": "📈", "color": "#00C853"},
    "macro": {"label": "Macro / Fed / Bonds", "icon": "🏛️", "color": "#60a5fa"},
    "cross_market": {"label": "Cross-Market", "icon": "⚡", "color": "#fbbf24"},
}

# Keywords for article scoring (financial markets focus)
HIGH_IMPACT_KEYWORDS = [
    # Crypto majors
    "bitcoin", "BTC", "ethereum", "ETH", "solana", "SOL", "XRP",
    "binance", "coinbase", "stablecoin", "USDT", "USDC",
    # Crypto events
    "halving", "ETF", "whale", "liquidation", "DeFi", "NFT",
    "mining", "staking", "airdrop",
    # Market terms
    "all-time high", "ATH", "correction", "rally", "crash",
    "volume", "market cap", "dominance", "breakout", "support", "resistance",
    # Indices & macro
    "S&P 500", "NASDAQ", "Dow Jones", "VIX", "treasury",
    "yield", "Fed", "FOMC", "rate cut", "rate hike", "CPI", "PPI",
    "inflation", "GDP", "jobs report", "unemployment", "PMI",
    # Polymarket / prediction markets
    "Polymarket", "prediction market", "odds", "probability",
    "election", "tariff", "regulation", "approval",
    # Geopolitics (market movers)
    "tariff", "sanctions", "trade war", "China", "EU",
    "regulation", "SEC", "CFTC", "ban",
    # Events
    "earnings", "IPO", "merger", "acquisition", "bankruptcy",
    "funding", "investment", "billion", "million",
]

# Disclaimer appended to every tweet
DISCLAIMER = "\n\nNot financial advice."

# Prompt: rank market data
RANKING_PROMPT = """You are a financial data editor for a market data Twitter bot.

Here are {count} data points from Polymarket, crypto markets, and stock indices. Rank the top 5 that would make the most informative tweets. Prioritize:
1. Biggest percentage moves (price or odds shifts)
2. Data points marked [ALERT] (significant movements)
3. Cross-market patterns (e.g., Fed decision affecting both stocks and crypto)
4. High volume or unusual activity
5. Data that provides immediate value to traders and market watchers

AVOID: Stale data with no significant movement, duplicate data about the same asset, data without specific numbers.

{articles}

Return ONLY a JSON array of the top 5 data point numbers, most significant first. Example: [3, 1, 7, 2, 5]
No commentary."""

# --- System prompt (persistent persona for all LLM generation calls) ---
SYSTEM_PROMPT = """You are the data engine behind a transparent AI Twitter bot that aggregates financial data from Polymarket, crypto markets, and stock indices into clear, accessible tweets.

Your voice:
- Professional, factual, and concise. You report data, not opinions.
- Accessible to non-experts: explain jargon when used, prefer plain English.
- Every tweet includes at least one specific number (price, percentage, volume).
- Use comparisons to add context: "up 12% in 24h, highest since March", "volume 3x the 30-day average".
- Neutral tone. Never bullish or bearish. Never "to the moon" or "crash incoming".
- You may note patterns ("This is the third consecutive day of decline") but never predict outcomes.
- Always factual. If data is delayed or uncertain, say so.

You are NOT a financial advisor. You are NOT predicting markets. You are a data aggregator that makes financial data accessible.

Formatting rules:
- Start each tweet with a text tag: BREAKING: / JUST IN: / MARKET UPDATE: / ALERT: / DATA: (pick the most appropriate).
- NO emojis. Ever. The tone is strictly professional.
- Include source attribution: "(via Polymarket)", "(CoinGecko data)", "(Yahoo Finance)"
- Do NOT include the disclaimer "Not financial advice." in your output. It will be appended automatically.
- Use line breaks between data point, context, and source.
- No em dashes. Use periods and line breaks.
- Max 1 hashtag per tweet. Use $TICKER cashtags where appropriate ($BTC, $ETH, $SPX).
- Numbers formatted clearly: $1.2B not $1,200,000,000. 12.4% not 0.124.
- Max 200 characters (a source link + disclaimer are appended automatically).

NEVER use emojis.
NEVER use: revolutionary, game-changer, to the moon, WAGMI, NGMI, rug pull (unless reporting one), HODL, diamond hands, paper hands, bullish, bearish, NFA (spell it out), DYOR (spell it out).
NEVER give buy/sell recommendations. NEVER say "you should" in financial context.
NEVER use em dashes (—)."""

# --- Generation templates pool ---
# Each template generates tweets with a distinct financial data style.
# The pipeline randomly selects 2-3 templates per batch for variety.

_FORMAT_RULES = """
LENGTH: 150-200 chars (a source link + disclaimer are appended automatically). Shorter is better.
Line breaks between data and context. Never a wall of text.
NO emojis. Start with a text tag: BREAKING: / JUST IN: / MARKET UPDATE: / ALERT: / DATA:
No hashtags unless directly relevant ($BTC is a cashtag, not a hashtag).
English only. No em dashes (—).
Do NOT include "Not financial advice" in your output."""

GENERATION_TEMPLATES = {
    "market_snapshot": {
        "weight": 2.5,
        "tweets_per_call": 3,
        "prompt": """Write 3 tweets summarizing today's key market movements. Each about a DIFFERENT market (Polymarket, crypto, stock indices).

RULES:
- Lead with the most significant number (price, odds change, volume).
- Second line: context (what changed, why it matters, comparison to recent history).
- Include source attribution: "(via Polymarket)", "(CoinGecko data)", "(Yahoo Finance)".
- Start each tweet with one of: JUST IN: / MARKET UPDATE: / DATA:
- Every tweet MUST contain at least one specific number.
""" + _FORMAT_RULES + """

INPUT DATA:
{articles}

TWEET 1: [tweet]
CHART_DATA: [chart type: line|bar|odds, asset name, timeframe]
TWEET 2: [tweet]
CHART_DATA: [chart type, asset name, timeframe]
TWEET 3: [tweet]
CHART_DATA: [chart type, asset name, timeframe]""",
    },

    "polymarket_mover": {
        "weight": 2.0,
        "tweets_per_call": 2,
        "prompt": """Write 2 tweets about the biggest movers on Polymarket prediction markets.

RULES:
- Lead with the odds change: "X market shifted from Y% to Z% in 24h"
- Add context: volume, what triggered the shift if apparent
- Include the market question
- Source: "(via Polymarket)"
- Neutral tone. Report the shift, do not predict the outcome.
""" + _FORMAT_RULES + """

INPUT DATA:
{articles}

TWEET 1: [tweet]
CHART_DATA: [odds, market name, 24h]
TWEET 2: [tweet]
CHART_DATA: [odds, market name, 24h]""",
    },

    "crypto_movers": {
        "weight": 2.0,
        "tweets_per_call": 2,
        "prompt": """Write 2 tweets about the biggest cryptocurrency movers in the last 24 hours.

RULES:
- Lead with the price change: "$BTC up/down X% to $XX,XXX"
- Include volume or market cap context
- Compare to recent history if data available: "lowest since [date]", "3rd consecutive day of gains"
- Use $TICKER cashtags for major coins
- Source: "(CoinGecko data)"
""" + _FORMAT_RULES + """

INPUT DATA:
{articles}

TWEET 1: [tweet]
CHART_DATA: [line, coin name, 7d]
TWEET 2: [tweet]
CHART_DATA: [line, coin name, 7d]""",
    },

    "dominance_shift": {
        "weight": 1.0,
        "tweets_per_call": 1,
        "prompt": """Write 1 tweet about crypto market dominance or macro market composition changes.

RULES:
- Focus on BTC dominance, ETH dominance, or total crypto market cap
- Include the specific percentage and direction of change
- Add context: what this level historically means
- Source: "(CoinGecko data)"
""" + _FORMAT_RULES + """

INPUT DATA:
{articles}

TWEET 1: [tweet]
CHART_DATA: [pie, dominance, 30d]""",
    },

    "alert_breaking": {
        "weight": 1.5,
        "tweets_per_call": 1,
        "is_alert": True,
        "prompt": """Write 1 tweet for a significant market movement alert.

RULES:
- Start with "BREAKING:" or "ALERT:"
- State the exact movement: what moved, by how much, in what timeframe
- One line of context maximum
- Keep under 200 chars (excluding auto-appended disclaimer). Speed matters for alerts.
""" + _FORMAT_RULES + """

INPUT DATA:
{articles}

TWEET 1: [tweet]
CHART_DATA: [line, asset name, 1h]""",
    },

    "weekly_recap": {
        "weight": 0.7,
        "tweets_per_call": 1,
        "is_thread": True,
        "prompt": """Write a 3-tweet thread recapping the week's key financial data movements.

RULES:
- THREAD_TWEET 1 (hook): The single biggest number of the week. Must work standalone. End with [thread]
- THREAD_TWEET 2 (markets): Polymarket + crypto summary with specific numbers.
- THREAD_TWEET 3 (macro): Stock market + macro summary. Include source attributions.
- Each tweet under 230 chars.
""" + _FORMAT_RULES + """

INPUT DATA:
{articles}

THREAD_TWEET 1: [hook]
THREAD_TWEET 2: [markets]
THREAD_TWEET 3: [macro]
CHART_DATA: [bar, weekly movers, 7d]""",
    },

    "poll_market": {
        "weight": 0.5,
        "tweets_per_call": 1,
        "is_poll": True,
        "prompt": """Write a Twitter poll about current market data.

RULES:
- Reference a SPECIFIC current data point from the input
- Options should be specific ranges or outcomes (not vague)
- Not a prediction question. Frame as "Which had the biggest move?" or knowledge-based.
- 2-4 options, max 25 chars each
- Question max 180 chars
""" + _FORMAT_RULES + """

INPUT DATA:
{articles}

POLL: [question]
OPTION_A: [option]
OPTION_B: [option]
OPTION_C: [option]
OPTION_D: [option]""",
    },

    "comparison": {
        "weight": 1.5,
        "tweets_per_call": 2,
        "prompt": """Write 2 tweets that compare two financial data points for perspective.

RULES:
- Structure: "X is now [value]. For comparison, Y is [value]."
- Cross-market comparisons are most interesting: Polymarket odds vs actual price, crypto volume vs stock volume
- Include specific numbers for both data points
- Source attribution for each data point
""" + _FORMAT_RULES + """

INPUT DATA:
{articles}

TWEET 1: [tweet]
CHART_DATA: [bar, comparison, current]
TWEET 2: [tweet]
CHART_DATA: [bar, comparison, current]""",
    },
}

# Legacy single prompt (fallback)
GENERATION_PROMPT = """Write 5 tweets about today's market data. You're a factual financial data aggregator.

RULES:
- Lead with the most significant number.
- 180-240 chars. Do NOT include "Not financial advice" (added automatically).
- Include source attribution.
- Start each with one of: JUST IN: / MARKET UPDATE: / DATA: / BREAKING:
- Neutral, professional tone. No opinions or predictions. No emojis.

INPUT:
{articles}

OUTPUT: Generate exactly 5 tweets, labeled TWEET 1 through TWEET 5. No extra commentary.
After each tweet, write CHART_DATA: [chart type, asset, timeframe]."""

# X / Twitter credentials for twikit (timeline reading)
X_USERNAME = os.getenv("X_USERNAME", "")
X_EMAIL = os.getenv("X_EMAIL", "")
X_PASSWORD = os.getenv("X_PASSWORD", "")

# Engagement reply prompt (disabled for financial bot - liability risk)
REPLY_GENERATION_PROMPT = """Write a SHORT reply to this tweet. You're a financial data bot providing factual context.

TARGET: @{target_username}
THEIR TWEET: "{original_tweet}"
REPLY STYLE: {reply_style}

RULES:
- Max {max_length} chars. Aim for 60-140. Shorter = better.
- ONLY provide factual data or context. NEVER give financial advice.
- Reference a specific number or data point.
- End with "Not financial advice." if discussing any financial topic.
- No hashtags. No em dashes. English only.

Generate exactly 3 options:
REPLY 1: [reply]
REPLY 2: [reply]
REPLY 3: [reply]"""

# Image storage (charts generated by matplotlib)
IMAGE_DIR = os.path.join(os.path.dirname(__file__), "data", "images")

# Database
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "quantum_brief.db"))
