import os
from dotenv import load_dotenv

load_dotenv()

# Mistral API
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

# X / Twitter
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")

# Schedule
POST_HOUR = int(os.getenv("POST_HOUR", "14"))
POST_MINUTE = int(os.getenv("POST_MINUTE", "0"))

# Legacy RSS feeds (kept as fallback, DB is primary source now)
RSS_FEEDS = [
    {
        "name": "ArXiv Quantum Physics",
        "url": "https://rss.arxiv.org/rss/quant-ph",
        "priority": 1,
        "category": "academic_preprint",
        "description": "Pre-print server for quantum physics papers",
        "website": "https://arxiv.org/list/quant-ph/recent",
    },
    {
        "name": "IEEE Spectrum Quantum",
        "url": "https://spectrum.ieee.org/feeds/topic/computing.rss",
        "priority": 2,
        "category": "industry_news",
        "description": "Engineering and technology news magazine",
        "website": "https://spectrum.ieee.org/topic/computing",
    },
    {
        "name": "Nature Quantum Information",
        "url": "https://www.nature.com/natquantuminf.rss",
        "priority": 1,
        "category": "academic_journal",
        "description": "Peer-reviewed quantum information research",
        "website": "https://www.nature.com/npjqi/",
    },
    {
        "name": "Quantum Computing Report",
        "url": "https://quantumcomputingreport.com/feed/",
        "priority": 2,
        "category": "industry_report",
        "description": "Industry analysis and news aggregator",
        "website": "https://quantumcomputingreport.com",
    },
]

# Legacy categories (DB is primary source now)
SOURCE_CATEGORIES = {
    "academic_preprint": {"label": "Academic Pre-prints", "icon": "📚", "color": "#818cf8"},
    "academic_journal": {"label": "Peer-Reviewed Journals", "icon": "🎓", "color": "#34d399"},
    "industry_news": {"label": "Industry News", "icon": "📰", "color": "#60a5fa"},
    "industry_report": {"label": "Industry Reports", "icon": "📊", "color": "#fbbf24"},
    "tech_news": {"label": "Tech News", "icon": "💻", "color": "#f472b6"},
    "company_blog": {"label": "Company Blogs", "icon": "🏢", "color": "#fb923c"},
    "ai_ml": {"label": "AI & Machine Learning", "icon": "🤖", "color": "#a78bfa"},
    "semiconductors": {"label": "Semiconductors", "icon": "⚡", "color": "#fbbf24"},
    "robotics": {"label": "Robotics", "icon": "🦾", "color": "#10b981"},
    "space_tech": {"label": "Space Tech", "icon": "🚀", "color": "#38bdf8"},
}

# Keywords for article scoring
HIGH_IMPACT_KEYWORDS = [
    # Breakthroughs & milestones
    "breakthrough", "record", "first", "milestone", "demonstration",
    # Major players - Quantum
    "google", "ibm", "microsoft", "amazon", "intel", "nvidia",
    "rigetti", "ionq", "quantinuum", "pasqal", "alice&bob",
    # Key quantum topics
    "error correction", "fault-tolerant", "logical qubit", "supremacy", "advantage",
    "topological", "photonic", "trapped ion", "superconducting",
    # Impact / business
    "investment", "funding", "billion", "million", "commercial",
    "partnership", "acquisition", "startup", "IPO", "valuation",
    # Geopolitics
    "china", "us", "europe", "race", "national", "strategy",
    # AI / Machine Learning
    "GPT", "LLM", "transformer", "OpenAI", "Anthropic", "DeepMind",
    "neural network", "training", "inference", "foundation model",
    # Semiconductors
    "TSMC", "chip", "semiconductor", "nanometer", "fabrication",
    "processor", "GPU", "TPU",
    # Robotics
    "humanoid", "robot", "Boston Dynamics", "Tesla Optimus", "Figure",
    "automation", "actuator", "manipulation",
    # Space
    "satellite", "NASA", "ESA", "quantum sensing", "quantum communication", "SpaceX",
]

# Prompt: rank articles
RANKING_PROMPT = """You are an editor for Quantum Brief, a tech account covering quantum computing, AI, robotics and emerging tech for a broad audience.

Here are {count} articles. Rank the top 5 that would make the best tweets. Prioritize:
1. Real-world impact (funding, product launches, partnerships) over lab results
2. Stories with concrete numbers or milestones
3. Content a non-scientist would find exciting
4. Company news over academic papers

AVOID ranking: purely theoretical papers, incremental research results, content requiring PhD-level background to understand.

{articles}

Return ONLY a JSON array of the top 5 article numbers, most important first. Example: [3, 1, 7, 2, 5]
No commentary."""

# Prompt: generate posts
GENERATION_PROMPT = """You are the social media voice of Quantum Brief. You cover quantum computing, AI, robotics and emerging tech.

Study these real high-engagement tweet examples and copy their EXACT style:

EXAMPLE A (Kalshi-style breaking):
🚨 BREAKING: Odds of a recession this year hit a record high of 36%

EXAMPLE B (news + consequence):
⚡ Google just mass-produced a 1,000-qubit chip.

That's 10x what IBM has.

The quantum race just changed overnight.

EXAMPLE C (stat bomb):
🔥 IQM just raised $300M.

Finnish quantum startup → global expansion.

First stop: US and Asia.

EXAMPLE D (fun fact):
🧠 Fun fact: A single quantum computer could break every encryption on Earth.

That's why NIST just released new "quantum-proof" standards.

Your bank will need to upgrade. Soon.

EXAMPLE E (engagement):
👀 Quantum computing or AI.

Which one changes the world more in the next 10 years?

FORMATTING RULES (CRITICAL — follow exactly):
- Every tweet uses LINE BREAKS to separate ideas. One idea per line. Never a wall of text.
- Start every tweet with one emoji from: {emoji_list}
- Sentences are SHORT. Max 10-12 words per sentence.
- Use action verbs: "surges", "plummets", "doubles", "hits record high", "just announced"
- Include a specific number in every tweet when possible. "$2.1B" not "billions".
- Structure: Line 1 = the fact. Line 2 = blank line. Line 3 = the consequence or context. Line 4 = blank line. Line 5 = the hook/kicker.
- NEVER use em dashes (—). Period or new line instead.
- NEVER use: delve, landscape, revolutionize, groundbreaking, unprecedented, paradigm, harness, leverage, navigate, robust, seamlessly, pivotal, multifaceted, notably, essentially, furthermore
- Plain English. A 16-year-old must understand every word.
- Max 1 hashtag per tweet, at the very end. Most tweets should have ZERO hashtags.
- Max 280 chars per tweet.
- English only.

INPUT:
{articles}

OUTPUT: Generate exactly 7 tweets.

TWEET 1 (Breaking news): The biggest story. "BREAKING:" format. Fact + consequence + kicker.
TWEET 2 (News): Second story. Same structure with line breaks.
TWEET 3 (Explainer): Make a complex concept dead simple. "Here's why X matters:" or "Most people don't realize:"
TWEET 4 (Stat bomb): One wild number. Give context on why it's wild.
TWEET 5 (Hot take): Bold opinion. Contrarian. Make people want to reply.
TWEET 6 (Fun fact): "Fun fact:" or "TIL:" — something surprising.
TWEET 7 (Engagement): A question. Two options or open-ended. Keep it under 200 chars.

Format: Return ONLY the 7 tweets, labeled TWEET 1 through TWEET 7. No extra commentary."""

# X / Twitter credentials for twikit (timeline reading)
X_USERNAME = os.getenv("X_USERNAME", "")
X_EMAIL = os.getenv("X_EMAIL", "")
X_PASSWORD = os.getenv("X_PASSWORD", "")

# Engagement reply prompt
REPLY_GENERATION_PROMPT = """You are the voice of Quantum Brief, a popular tech account covering quantum computing, AI, robotics and emerging tech. Write a SHORT reply to this tweet.

TARGET: @{target_username}
THEIR TWEET: "{original_tweet}"
REPLY STYLE: {reply_style}

STYLES:
- complementary: Add a fact, stat, or context they missed. Lead with the fact.
- witty: Memorable one-liner. Funny but not mean.
- question: Smart follow-up question showing expertise.
- hot_take: Respectful contrarian take. "Interesting but..." or "Actually..."
- agreement: "This." or "Exactly." + amplifying point.
- emoji_reaction: Short reaction with 1-2 emojis + insight.

RULES:
- Max {max_length} chars. Aim for 60-140 chars. Shorter = better.
- Sound human and natural, like a real person commenting.
- NEVER start with "Great tweet", "Interesting post", or any generic compliment.
- NEVER use hashtags.
- BANNED words: delve, landscape, revolutionize, groundbreaking, unprecedented, paradigm, harness, leverage, navigate, seamlessly, robust
- NO em dashes.
- Reference something SPECIFIC from their tweet (a number, name, claim).
- One idea only. 1-2 sentences max.
- English only.
- Be conversational, not formal.

Generate exactly 3 options:
REPLY 1: [reply]
REPLY 2: [reply]
REPLY 3: [reply]"""

# Image APIs (optional, for stock photo fallback)
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# Image storage
IMAGE_DIR = os.path.join(os.path.dirname(__file__), "data", "images")

# Database
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "quantum_brief.db"))
