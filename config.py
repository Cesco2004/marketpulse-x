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

# --- Generation templates pool (replaces monolithic GENERATION_PROMPT) ---
# Each template generates 2-3 tweets with a distinct style.
# The pipeline randomly selects 2-3 templates per batch for variety.

_BANNED_WORDS_BLOCK = """
CRITICAL LENGTH RULE: Each tweet MUST be 150-280 characters. NOT shorter. Write full sentences, not fragments or bullet points. If your tweet is under 150 chars, add more context or detail.

BANNED words: delve, landscape, revolutionize, groundbreaking, unprecedented, paradigm, harness, leverage, navigate, robust, seamlessly, pivotal, multifaceted, notably, essentially, furthermore.
BANNED closers (if your last line matches any of these, DELETE it and end the tweet one line earlier):
- "The [noun] race is on" / "Are you ready?" / "This changes everything"
- "And it's only the beginning" / "Buckle up" / "The future of [X]"
- "Will [you/your company] adapt?" / "Let that sink in" / "Think about that"
- "That's huge" / "You're not ready" / "Mark my words"
- Any sentence so generic it could apply to any topic.
NEVER use em dashes (—). Use a period or new line instead.
NEVER mention Reddit upvotes, HackerNews scores, or comment counts. The audience doesn't care about other platforms.
English only. Max 1 hashtag (most tweets: zero). Plain English a 16-year-old can understand."""

GENERATION_TEMPLATES = {
    "news_wire": {
        "weight": 2.0,  # Most commonly selected
        "tweets_per_call": 3,
        "prompt": """You write breaking tech news tweets for Quantum Brief, a Twitter account covering AI, startups, and emerging tech.

Write like a wire journalist, not a marketer. No hype. Just the facts, fast.

RULES:
- Lead with the single most important fact. No filler intro.
- Second line: ONE specific detail that makes readers stop (a number, a name, a comparison).
- Optional third line: direct consequence for a SPECIFIC group (not "the world" — name who is affected).
- NO rhetorical questions at the end. If you can't think of a strong closer, just end after line 2.
- Start each tweet with one emoji from: {emoji_list}
- Short sentences only. Max 12 words per sentence.
- Include a specific number in every tweet: "$2.1B" not "billions".
- Use line breaks between ideas. Never a wall of text.
""" + _BANNED_WORDS_BLOCK + """

INPUT ARTICLES:
{articles}

OUTPUT: Generate exactly 3 tweets from the most interesting articles. Each tweet about a DIFFERENT article.
After each tweet, write IMAGE_HINT: [2-3 keywords for an ideal image].

TWEET 1: [tweet]
IMAGE_HINT: [keywords]
TWEET 2: [tweet]
IMAGE_HINT: [keywords]
TWEET 3: [tweet]
IMAGE_HINT: [keywords]""",
    },

    "insider": {
        "weight": 1.5,
        "tweets_per_call": 2,
        "prompt": """You're explaining tech news to a smart friend over coffee. You write for Quantum Brief on Twitter.

Your tone: casual, surprising, insightful. You make people feel smarter.

RULES:
- Start with a surprising fact stated plainly. No "Did you know" or "Fun fact" — just say the thing.
- Give exactly ONE piece of context that makes the fact click.
- End with the implication in one short sentence. Not a question. Not an exclamation.
- Sounds like: "Turns out..." or "Here's the thing about X..." or "So apparently..."
- Start each tweet with one emoji from: {emoji_list}
- Max 260 chars.
""" + _BANNED_WORDS_BLOCK + """

INPUT ARTICLES:
{articles}

OUTPUT: Generate exactly 2 tweets. Each about a DIFFERENT article.
After each tweet, write IMAGE_HINT: [2-3 keywords for an ideal image].

TWEET 1: [tweet]
IMAGE_HINT: [keywords]
TWEET 2: [tweet]
IMAGE_HINT: [keywords]""",
    },

    "data_point": {
        "weight": 1.0,
        "tweets_per_call": 2,
        "prompt": """You're a data analyst who found something wild in the numbers. You tweet for Quantum Brief.

RULES:
- Open with the number. Not "Did you know" — just the raw number.
- Second line: what it was before, or what the comparison is.
- Optional third line: what this means, in plain English.
- Max one emoji (a chart or money emoji). Can also start without emoji.
- Keep it under 220 chars. Shorter is better.
- Every tweet MUST contain at least one specific number ($X.XB, X%, X,XXX).
""" + _BANNED_WORDS_BLOCK + """

INPUT ARTICLES:
{articles}

OUTPUT: Generate exactly 2 tweets from articles that have strong numbers/data.
After each tweet, write IMAGE_HINT: [2-3 keywords for an ideal image].

TWEET 1: [tweet]
IMAGE_HINT: [keywords]
TWEET 2: [tweet]
IMAGE_HINT: [keywords]""",
    },

    "contrarian": {
        "weight": 1.0,
        "tweets_per_call": 2,
        "prompt": """You disagree with the consensus on a tech topic. You tweet for Quantum Brief — bold, specific, no hedging.

RULES:
- Line 1: State what everyone thinks or what just happened.
- Line 2: State why that's wrong OR why people are missing the real story. Cite ONE specific reason.
- No hedging ("I think", "in my opinion"). Just state it.
- Sounds like a podcast guest making a bold claim, not a motivational poster.
- Start with one emoji from: {emoji_list}
- Max 260 chars.
""" + _BANNED_WORDS_BLOCK + """

INPUT ARTICLES:
{articles}

OUTPUT: Generate exactly 2 contrarian takes on the articles.
After each tweet, write IMAGE_HINT: [2-3 keywords for an ideal image].

TWEET 1: [tweet]
IMAGE_HINT: [keywords]
TWEET 2: [tweet]
IMAGE_HINT: [keywords]""",
    },

    "question": {
        "weight": 1.0,
        "tweets_per_call": 1,
        "prompt": """You're starting a debate in a tech group chat. You tweet for Quantum Brief.

RULES:
- Ask ONE specific question. Not vague ("What's the future of AI?").
- Good: "If Nvidia drops 30% tomorrow, do you buy?" / "OpenAI or Anthropic — who ships faster?"
- Optionally add a mini-poll: "A) ... B) ..."
- Keep it under 200 chars. No hashtags. No more than one emoji (optional).
- The question should relate to the articles but feel like a spontaneous thought.
""" + _BANNED_WORDS_BLOCK + """

INPUT ARTICLES:
{articles}

OUTPUT: Generate exactly 1 engagement tweet.

TWEET 1: [tweet]""",
    },

    "thread": {
        "weight": 0.7,
        "tweets_per_call": 1,
        "is_thread": True,
        "prompt": """Write a 3-tweet thread for Quantum Brief covering AI, startups, and emerging tech on Twitter.

RULES:
- THREAD_TWEET 1 (the hook): A bold claim or surprising fact. Must work as a standalone tweet. End with "🧵" or "A thread:"
- THREAD_TWEET 2 (the evidence): The backstory or data. Include a specific number.
- THREAD_TWEET 3 (the takeaway): What it means going forward. End with a question OR a specific prediction.
- Each tweet under 260 chars.
- Start tweet 1 with one emoji from: {emoji_list}
- Use line breaks within tweets for readability.
""" + _BANNED_WORDS_BLOCK + """

INPUT ARTICLES:
{articles}

OUTPUT: Generate exactly 1 thread (3 tweets). Pick the most interesting article.
After the thread, write IMAGE_HINT: [2-3 keywords for an image for tweet 1].

THREAD_TWEET 1: [hook tweet]
THREAD_TWEET 2: [evidence tweet]
THREAD_TWEET 3: [takeaway tweet]
IMAGE_HINT: [keywords]""",
    },

    "poll": {
        "weight": 0.5,
        "tweets_per_call": 1,
        "is_poll": True,
        "prompt": """Write a Twitter poll for Quantum Brief, a tech account covering AI, startups, and emerging tech.

RULES:
- The question should be specific and related to the articles.
- 2-4 options (labeled OPTION_A through OPTION_D).
- The question + options should spark genuine debate, not have an obvious answer.
- Start with one emoji from: {emoji_list}
- Question text: max 200 chars.
- Each option: max 25 chars.
""" + _BANNED_WORDS_BLOCK + """

INPUT ARTICLES:
{articles}

OUTPUT: Generate exactly 1 poll.

POLL: [question text]
OPTION_A: [option]
OPTION_B: [option]
OPTION_C: [option]
OPTION_D: [option]""",
    },
}

# Legacy single prompt (kept for fallback if template system fails)
GENERATION_PROMPT = """You are the social media voice of Quantum Brief. You cover AI, startups, and emerging tech.

FORMATTING RULES:
- Every tweet uses LINE BREAKS to separate ideas. One idea per line. Never a wall of text.
- Start every tweet with one emoji from: {emoji_list}
- Sentences are SHORT. Max 10-12 words per sentence.
- Include a specific number in every tweet when possible. "$2.1B" not "billions".
- NEVER use em dashes. NEVER use: delve, landscape, revolutionize, groundbreaking, unprecedented, paradigm, harness, leverage, navigate, robust, seamlessly, pivotal, multifaceted
- Max 280 chars per tweet. English only. Max 1 hashtag at the very end.

INPUT:
{articles}

OUTPUT: Generate exactly 7 tweets, labeled TWEET 1 through TWEET 7. No extra commentary.
After each tweet, write IMAGE_HINT: [2-3 keywords for an ideal image]."""

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
