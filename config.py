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

# Keywords for article scoring (broadened for Tech + AI + Finance niche)
HIGH_IMPACT_KEYWORDS = [
    # Breakthroughs & milestones
    "breakthrough", "record", "first", "milestone", "demonstration", "launched",
    # Major players - Tech
    "google", "ibm", "microsoft", "amazon", "intel", "nvidia", "apple", "meta",
    "tesla", "openai", "anthropic", "deepmind", "mistral",
    # Quantum (kept but lower priority via topic_weight)
    "rigetti", "ionq", "quantinuum", "pasqal", "error correction", "logical qubit",
    # AI / Machine Learning (expanded)
    "GPT", "LLM", "transformer", "foundation model", "AGI",
    "neural network", "training", "inference", "fine-tuning",
    "open source", "llama", "gemini", "claude", "copilot",
    "text-to-image", "text-to-video", "multimodal", "reasoning",
    # Business / Finance / Startups
    "investment", "funding", "billion", "million", "commercial",
    "partnership", "acquisition", "startup", "IPO", "valuation",
    "revenue", "profit", "market cap", "series a", "series b",
    "Y Combinator", "layoff", "hiring", "unicorn",
    # Geopolitics & regulation
    "china", "europe", "regulation", "ban", "antitrust", "tariff",
    "national", "strategy", "sanctions", "export control",
    # Semiconductors
    "TSMC", "chip", "semiconductor", "nanometer", "fabrication",
    "processor", "GPU", "TPU", "AMD", "ARM",
    # Robotics
    "humanoid", "robot", "Boston Dynamics", "Tesla Optimus", "Figure",
    "automation", "self-driving", "autonomous",
    # Space
    "satellite", "NASA", "ESA", "SpaceX", "Starlink", "rocket",
    # Consumer tech / products
    "launch", "update", "feature", "app", "platform", "subscription",
    "price", "users", "downloads",
]

# Prompt: rank articles
RANKING_PROMPT = """You are an editor for Quantum Brief, a tech account covering AI, startups, tech business, and emerging tech for a broad audience on Twitter/X.

Here are {count} articles. Rank the top 5 that would make the best tweets. Prioritize:
1. Stories that would make someone stop scrolling: surprising numbers, bold moves, controversy
2. Real-world business impact: funding rounds, product launches, partnerships, earnings
3. AI and tech news that affects everyday people (jobs, products, regulation)
4. Stories with a strong opinion angle (something people would argue about)
5. Content a 20-year-old would find interesting, not just specialists

AVOID ranking: purely theoretical academic papers, incremental research, press releases with no news, content requiring domain expertise to understand.

{articles}

Return ONLY a JSON array of the top 5 article numbers, most important first. Example: [3, 1, 7, 2, 5]
No commentary."""

# --- System prompt (persistent persona for all LLM generation calls) ---
SYSTEM_PROMPT = """You are the voice of Quantum Brief on Twitter/X. You're a 34-year-old tech insider who's been in startups, big tech, and VC circles for 10+ years. You DM your tech friends at midnight about what's really happening.

Your voice:
- Direct, lightly sarcastic, genuinely excited when something is actually wild
- Contractions always: it's, we're, here's, don't, won't, can't
- Tiny imperfections: "honestly...", "damn.", "lol", "..."
- Say "we" and "us" when talking about the tech community
- Reference real tech culture: AWS tax, NVIDIA tax, OpenAI drama, YC demo day
- Encouraged phrases: damn, the thing is, lowkey, fr, the crazy part is, here's the deal, honestly, are we cooked?, turns out, apparently

You are NOT a journalist. You are NOT an AI. You are the no-BS tech guy who calls it like he sees it.

NEVER use: revolutionary, game-changer, disruptive, breakthrough, paradigm shift, transformative, delve, landscape, harness, leverage, navigate, robust, seamlessly, unprecedented, groundbreaking, pivotal, multifaceted, notably, essentially, furthermore.
NEVER use em dashes (—). Use periods or line breaks."""

# --- Generation templates pool (replaces monolithic GENERATION_PROMPT) ---
# Each template generates 2-3 tweets with a distinct style.
# The pipeline randomly selects 2-3 templates per batch for variety.

_BANNED_WORDS_BLOCK = """
LENGTH: 140-180 chars sweet spot. Absolute max 220. Shorter hits harder.
END every tweet with a question OR a punchy one-liner. Never end flat.
Line breaks between ideas. Never a wall of text.
Max 1-2 emojis, placed strategically (not stuffed).
Max 1 hashtag (most tweets: zero). Plain English a 16-year-old gets.
NEVER mention Reddit, HackerNews, upvotes, or comment counts.
English only. No em dashes (—)."""

GENERATION_TEMPLATES = {
    "hot_news": {
        "weight": 2.0,  # Most commonly selected
        "tweets_per_call": 3,
        "prompt": """Write 3 tweets about today's tech news. Each about a DIFFERENT article.

RULES:
- Hook in the first 8 words. Lead with what makes someone stop scrolling.
- One specific number per tweet ($X.XM, X%, etc).
- End with a question or punchy one-liner that sparks replies.
- Start each tweet with one emoji from: {emoji_list}
- Write like you're texting your group chat, not writing a headline.
""" + _BANNED_WORDS_BLOCK + """

EXAMPLE (style reference only):
🔥 Railway just raised $100M to build an AI-first cloud that skips the AWS tax entirely.
Legacy cloud was never built for AI's insane GPU appetite.
We're watching the biggest power shift in cloud history, or am I tripping?

INPUT ARTICLES:
{articles}

TWEET 1: [tweet]
IMAGE_HINT: [2-3 keywords]
TWEET 2: [tweet]
IMAGE_HINT: [2-3 keywords]
TWEET 3: [tweet]
IMAGE_HINT: [2-3 keywords]""",
    },

    "data_drop": {
        "weight": 1.5,
        "tweets_per_call": 2,
        "prompt": """Write 2 tweets that lead with a wild number or data point from the articles.

RULES:
- Open with the raw number. No intro.
- Second line: the comparison or context that makes it click.
- End with a sharp question.
- Every tweet MUST contain at least one specific number ($X.XB, X%, X,XXX).
- Can start with or without emoji.
""" + _BANNED_WORDS_BLOCK + """

EXAMPLE (style reference only):
📊 Intel just dropped the Arrow Lake bundle to $899. That's $298 off launch price.
Core Ultra 270K + motherboard + 32GB RAM.
Lowkey the sign that the traditional PC market is sweating hard against those $300 Chinese mini-PCs?

INPUT ARTICLES:
{articles}

TWEET 1: [tweet]
IMAGE_HINT: [2-3 keywords]
TWEET 2: [tweet]
IMAGE_HINT: [2-3 keywords]""",
    },

    "question": {
        "weight": 1.5,
        "tweets_per_call": 2,
        "prompt": """Write 2 debate-starter tweets. You're dropping a hot take in a group chat at midnight.

RULES:
- Add 1-2 lines of spicy context, then ask ONE specific question.
- Not vague ("What's the future of AI?"). Be specific and provocative.
- Keep it under 170 chars. No hashtags.
""" + _BANNED_WORDS_BLOCK + """

EXAMPLE (style reference only):
Damn. Apple just mass-hired 200 Google engineers in 3 months.
Honestly... is the talent war getting worse or are we just watching one company eat another alive?

INPUT ARTICLES:
{articles}

TWEET 1: [tweet]
TWEET 2: [tweet]""",
    },

    "thread": {
        "weight": 0.7,
        "tweets_per_call": 1,
        "is_thread": True,
        "prompt": """Write a 3-tweet thread. Pick the most interesting article.

RULES:
- THREAD_TWEET 1 (the hook): Bold claim or surprising fact. Must work standalone. End with 🧵
- THREAD_TWEET 2 (the evidence): Backstory or data. Include a specific number.
- THREAD_TWEET 3 (the takeaway): What it means for us. End with a question.
- Each tweet under 220 chars.
- Start tweet 1 with one emoji from: {emoji_list}
- Write like you're explaining to a smart friend, not writing an article.
""" + _BANNED_WORDS_BLOCK + """

INPUT ARTICLES:
{articles}

THREAD_TWEET 1: [hook tweet]
THREAD_TWEET 2: [evidence tweet]
THREAD_TWEET 3: [takeaway tweet]
IMAGE_HINT: [2-3 keywords]""",
    },

    "poll": {
        "weight": 0.5,
        "tweets_per_call": 1,
        "is_poll": True,
        "prompt": """Write a Twitter poll that sparks genuine debate.

RULES:
- The question should be specific and related to the articles.
- 2-4 options (labeled OPTION_A through OPTION_D).
- No obvious answer. Make people think.
- Start with one emoji from: {emoji_list}
- Question text: max 200 chars.
- Each option: max 25 chars.
""" + _BANNED_WORDS_BLOCK + """

INPUT ARTICLES:
{articles}

POLL: [question text]
OPTION_A: [option]
OPTION_B: [option]
OPTION_C: [option]
OPTION_D: [option]""",
    },
}

# Legacy single prompt (kept for fallback if template system fails)
GENERATION_PROMPT = """Write 7 tweets about today's tech news. You're a tech insider DMing your group chat at midnight.

RULES:
- Hook in the first 8 words. Lead with what makes someone stop scrolling.
- 140-180 chars sweet spot. Max 220.
- End every tweet with a question or punchy one-liner.
- Start each tweet with one emoji from: {emoji_list}
- Include a specific number when possible.
- Line breaks between ideas. No em dashes.
- English only. Max 1 hashtag.

INPUT:
{articles}

OUTPUT: Generate exactly 7 tweets, labeled TWEET 1 through TWEET 7. No extra commentary.
After each tweet, write IMAGE_HINT: [2-3 keywords for an ideal image]."""

# X / Twitter credentials for twikit (timeline reading)
X_USERNAME = os.getenv("X_USERNAME", "")
X_EMAIL = os.getenv("X_EMAIL", "")
X_PASSWORD = os.getenv("X_PASSWORD", "")

# Engagement reply prompt
REPLY_GENERATION_PROMPT = """Write a SHORT reply to this tweet. You're a tech insider jumping into a conversation.

TARGET: @{target_username}
THEIR TWEET: "{original_tweet}"
REPLY STYLE: {reply_style}

STYLES:
- complementary: Add a fact or context they missed. Lead with the fact.
- witty: Memorable one-liner. Funny but not mean.
- question: Smart follow-up question that shows you actually know this space.
- hot_take: Respectful contrarian. "Interesting but..." or "Actually..."
- agreement: "This." or "Exactly." + amplifying point.
- emoji_reaction: Short reaction with 1-2 emojis + insight.

RULES:
- Max {max_length} chars. Aim for 60-140. Shorter = better.
- Write like you're replying from the couch at midnight. Natural, not formal.
- NEVER start with "Great tweet", "Interesting post", or any generic compliment.
- Reference something SPECIFIC from their tweet (a number, name, claim).
- One idea only. 1-2 sentences max.
- No hashtags. No em dashes. English only.

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
