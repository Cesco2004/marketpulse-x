import sqlite3
import json
import os
from datetime import datetime

import config


def get_connection():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT UNIQUE,
            source TEXT,
            summary TEXT,
            keyword_score INTEGER DEFAULT 0,
            matched_keywords TEXT DEFAULT '[]',
            llm_rank INTEGER,
            stage TEXT DEFAULT 'fetched',
            manual_override TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            post_type TEXT,
            status TEXT DEFAULT 'pending_review',
            batch_id TEXT,
            source_article_ids TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            posted_at TIMESTAMP,
            x_tweet_id TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT NOT NULL,
            endpoint TEXT,
            tokens_input INTEGER DEFAULT 0,
            tokens_output INTEGER DEFAULT 0,
            cost_estimate REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedule_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            mode TEXT DEFAULT 'fixed',
            fixed_interval_hours INTEGER DEFAULT 24,
            fixed_interval_minutes INTEGER DEFAULT 0,
            random_tweets_per_day INTEGER DEFAULT 1,
            random_min_gap_hours INTEGER DEFAULT 3,
            random_min_gap_minutes INTEGER DEFAULT 0,
            random_max_gap_hours INTEGER DEFAULT 15,
            random_max_gap_minutes INTEGER DEFAULT 0,
            random_start_hour INTEGER DEFAULT 9,
            random_start_minute INTEGER DEFAULT 0,
            random_end_hour INTEGER DEFAULT 22,
            random_end_minute INTEGER DEFAULT 0,
            timezone TEXT DEFAULT 'Europe/Paris',
            is_active INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- Quality config (singleton) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quality_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            ai_detection_enabled INTEGER DEFAULT 1,
            ai_penalty_phrases TEXT DEFAULT '["delve","landscape","it''s worth noting","revolutionize","game-changer","paradigm shift","at the forefront","in the realm of","harness","leverage","navigate","unprecedented","groundbreaking","synergy","deep dive","robust","seamlessly","tapestry","embark","pivotal","multifaceted","notably","essentially","furthermore"]',
            ai_emdash_penalty INTEGER DEFAULT 15,
            ai_phrase_penalty INTEGER DEFAULT 10,
            readability_enabled INTEGER DEFAULT 1,
            readability_jargon_list TEXT DEFAULT '["decoherence","hamiltonian","eigenstate","annealing","qubit fidelity","hilbert space","topological","lagrangian","bosonic","fermionic"]',
            readability_jargon_penalty INTEGER DEFAULT 8,
            readability_max_grade_level INTEGER DEFAULT 10,
            emoji_enabled INTEGER DEFAULT 1,
            emoji_preferred TEXT DEFAULT '["🚨","🔥","⚡","💡","🚀","🧠","👀","📈","💥","✨","🔬","🌐","💰","🤖","🔒"]',
            emoji_leading_bonus INTEGER DEFAULT 50,
            weight_ai REAL DEFAULT 0.35,
            weight_readability REAL DEFAULT 0.35,
            weight_emoji REAL DEFAULT 0.30,
            min_quality_score REAL DEFAULT 50.0,
            auto_reject_below REAL DEFAULT 30.0,
            auto_approve_above REAL DEFAULT 70.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- RSS feeds (replaces hardcoded config.RSS_FEEDS) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rss_feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL UNIQUE,
            priority INTEGER DEFAULT 2,
            category TEXT DEFAULT 'industry_news',
            description TEXT DEFAULT '',
            website TEXT DEFAULT '',
            is_enabled INTEGER DEFAULT 1,
            topic_weight REAL DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- Topic categories ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS topic_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL,
            icon TEXT DEFAULT '',
            color TEXT DEFAULT '#9ca3af',
            is_enabled INTEGER DEFAULT 1,
            weight REAL DEFAULT 1.0,
            sort_order INTEGER DEFAULT 0
        )
    """)

    # --- Image config (singleton) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS image_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            images_enabled INTEGER DEFAULT 1,
            image_ratio REAL DEFAULT 0.66,
            min_image_score REAL DEFAULT 50.0,
            unsplash_api_key TEXT DEFAULT '',
            pexels_api_key TEXT DEFAULT '',
            prefer_article_images INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- Target accounts for engagement ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS target_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            user_id TEXT,
            display_name TEXT DEFAULT '',
            category TEXT DEFAULT 'general',
            reply_style TEXT DEFAULT 'mixed',
            is_enabled INTEGER DEFAULT 1,
            priority INTEGER DEFAULT 2,
            last_seen_tweet_id TEXT,
            last_polled_at TIMESTAMP,
            poll_errors INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- Engagement replies ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS engagement_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_account_id INTEGER NOT NULL,
            target_username TEXT NOT NULL,
            original_tweet_id TEXT NOT NULL UNIQUE,
            original_tweet_text TEXT NOT NULL,
            original_tweet_url TEXT,
            reply_content TEXT NOT NULL,
            reply_style TEXT,
            status TEXT DEFAULT 'approved',
            quality_score REAL,
            score_details TEXT DEFAULT '{}',
            x_reply_tweet_id TEXT,
            reply_after TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            posted_at TIMESTAMP,
            FOREIGN KEY (target_account_id) REFERENCES target_accounts(id)
        )
    """)

    # --- Engagement config (singleton) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS engagement_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_enabled INTEGER DEFAULT 0,
            poll_interval_minutes INTEGER DEFAULT 10,
            max_replies_per_day INTEGER DEFAULT 10,
            max_replies_per_account_per_day INTEGER DEFAULT 3,
            reply_delay_min_minutes INTEGER DEFAULT 2,
            reply_delay_max_minutes INTEGER DEFAULT 15,
            auto_reject_below REAL DEFAULT 35.0,
            max_reply_length INTEGER DEFAULT 280,
            reply_window_hours INTEGER DEFAULT 6,
            timezone TEXT DEFAULT 'Europe/Paris',
            active_start_hour INTEGER DEFAULT 8,
            active_end_hour INTEGER DEFAULT 23,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- Usage limits (singleton) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_limits (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            mistral_max_tokens_per_day INTEGER DEFAULT 500000,
            mistral_max_calls_per_day INTEGER DEFAULT 50,
            mistral_max_cost_per_day REAL DEFAULT 1.00,
            x_max_tweets_per_day INTEGER DEFAULT 15,
            x_max_replies_per_day INTEGER DEFAULT 10,
            warning_threshold_pct INTEGER DEFAULT 80,
            alert_email TEXT DEFAULT '',
            smtp_host TEXT DEFAULT 'smtp.gmail.com',
            smtp_port INTEGER DEFAULT 587,
            smtp_user TEXT DEFAULT '',
            smtp_password TEXT DEFAULT '',
            alerts_enabled INTEGER DEFAULT 0,
            daily_summary_enabled INTEGER DEFAULT 0,
            max_consecutive_errors INTEGER DEFAULT 5,
            current_consecutive_errors INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- Kill switch (singleton) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kill_switch (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_killed INTEGER DEFAULT 0,
            killed_at TIMESTAMP,
            killed_reason TEXT DEFAULT '',
            killed_by TEXT DEFAULT ''
        )
    """)

    # --- Alert log ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            message TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- Tweet metrics (engagement snapshots) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tweet_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tweet_id TEXT NOT NULL,
            post_id INTEGER,
            likes INTEGER DEFAULT 0,
            retweets INTEGER DEFAULT 0,
            replies INTEGER DEFAULT 0,
            quotes INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            bookmarks INTEGER DEFAULT 0,
            engagement_rate REAL DEFAULT 0,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tweet_metrics_tweet_id ON tweet_metrics(tweet_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tweet_metrics_collected_at ON tweet_metrics(collected_at)")

    # --- Account metrics (daily snapshots) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            followers INTEGER DEFAULT 0,
            following INTEGER DEFAULT 0,
            tweets_count INTEGER DEFAULT 0,
            listed_count INTEGER DEFAULT 0,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_account_metrics_collected_at ON account_metrics(collected_at)")

    # --- Analytics config (singleton) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_enabled INTEGER DEFAULT 0,
            collection_interval_hours INTEGER DEFAULT 12,
            lookback_days INTEGER DEFAULT 30,
            own_username TEXT DEFAULT ''
        )
    """)

    # --- Monthly budget (singleton) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monthly_budget (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            mistral_monthly_token_limit INTEGER DEFAULT 1000000,
            groq_monthly_token_limit INTEGER DEFAULT 1500000,
            auto_throttle_enabled INTEGER DEFAULT 1,
            throttle_start_pct INTEGER DEFAULT 70,
            throttle_medium_pct INTEGER DEFAULT 85,
            emergency_stop_pct INTEGER DEFAULT 95,
            budget_alert_threshold_pct INTEGER DEFAULT 75,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert default configs if empty
    cursor.execute("INSERT OR IGNORE INTO schedule_config (id) VALUES (1)")
    cursor.execute("INSERT OR IGNORE INTO quality_config (id) VALUES (1)")
    cursor.execute("INSERT OR IGNORE INTO image_config (id) VALUES (1)")
    cursor.execute("INSERT OR IGNORE INTO engagement_config (id) VALUES (1)")
    cursor.execute("INSERT OR IGNORE INTO usage_limits (id) VALUES (1)")
    cursor.execute("INSERT OR IGNORE INTO kill_switch (id) VALUES (1)")
    cursor.execute("INSERT OR IGNORE INTO analytics_config (id) VALUES (1)")
    cursor.execute("INSERT OR IGNORE INTO monthly_budget (id) VALUES (1)")

    # Seed topic categories
    default_categories = [
        ("academic_preprint", "Academic Pre-prints", "📚", "#818cf8", 1, 0.5, 0),
        ("academic_journal", "Peer-Reviewed Journals", "🎓", "#34d399", 1, 0.5, 1),
        ("industry_news", "Industry News", "📰", "#60a5fa", 1, 1.0, 2),
        ("industry_report", "Industry Reports", "📊", "#fbbf24", 1, 0.8, 3),
        ("tech_news", "Tech News", "💻", "#f472b6", 1, 1.0, 4),
        ("company_blog", "Company Blogs", "🏢", "#fb923c", 1, 1.0, 5),
        ("ai_ml", "AI & Machine Learning", "🤖", "#a78bfa", 1, 1.0, 6),
        ("semiconductors", "Semiconductors", "⚡", "#fbbf24", 1, 0.8, 7),
        ("robotics", "Robotics", "🦾", "#10b981", 1, 1.0, 8),
        ("space_tech", "Space Tech", "🚀", "#38bdf8", 1, 0.8, 9),
    ]
    for key, label, icon, color, enabled, weight, sort_order in default_categories:
        cursor.execute(
            "INSERT OR IGNORE INTO topic_categories (key, label, icon, color, is_enabled, weight, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, label, icon, color, enabled, weight, sort_order),
        )

    # Seed RSS feeds
    default_feeds = [
        # Existing feeds (deprioritized academic)
        ("ArXiv Quantum Physics", "https://rss.arxiv.org/rss/quant-ph", 1, "academic_preprint", "Pre-print server for quantum physics papers", "https://arxiv.org/list/quant-ph/recent", 1, 0.5),
        ("IEEE Spectrum Quantum", "https://spectrum.ieee.org/feeds/topic/computing.rss", 2, "industry_news", "Engineering and technology news magazine", "https://spectrum.ieee.org/topic/computing", 1, 0.8),
        ("Nature Quantum Information", "https://www.nature.com/natquantuminf.rss", 1, "academic_journal", "Peer-reviewed quantum information research", "https://www.nature.com/npjqi/", 1, 0.5),
        ("Quantum Computing Report", "https://quantumcomputingreport.com/feed/", 2, "industry_report", "Industry analysis and news aggregator", "https://quantumcomputingreport.com", 1, 0.8),
        # Quantum - accessible
        ("The Quantum Insider", "https://thequantuminsider.com/feed/", 1, "industry_news", "Quantum industry news and analysis", "https://thequantuminsider.com", 1, 1.0),
        ("TechCrunch Quantum", "https://techcrunch.com/tag/quantum-computing/feed/", 1, "tech_news", "Quantum computing coverage from TechCrunch", "https://techcrunch.com/tag/quantum-computing/", 1, 1.0),
        # Tech news
        ("Wired Science", "https://www.wired.com/feed/category/science/latest/rss", 2, "tech_news", "Science and technology news", "https://www.wired.com/category/science/", 1, 1.0),
        ("Ars Technica Science", "https://feeds.arstechnica.com/arstechnica/science", 2, "tech_news", "Science and tech reporting", "https://arstechnica.com/science/", 1, 1.0),
        # Company blogs
        ("Google AI Blog", "https://blog.google/technology/ai/rss/", 1, "company_blog", "Google AI announcements and research", "https://blog.google/technology/ai/", 1, 1.0),
        ("IBM Research Blog", "https://research.ibm.com/blog/rss", 1, "company_blog", "IBM research and quantum updates", "https://research.ibm.com/blog", 1, 1.0),
        ("Microsoft Quantum Blog", "https://cloudblogs.microsoft.com/quantum/feed/", 1, "company_blog", "Microsoft quantum computing updates", "https://cloudblogs.microsoft.com/quantum/", 1, 1.0),
        ("AWS Quantum Computing", "https://aws.amazon.com/blogs/quantum-computing/feed/", 2, "company_blog", "AWS quantum computing blog", "https://aws.amazon.com/blogs/quantum-computing/", 1, 1.0),
        # AI/ML
        ("MIT Technology Review", "https://www.technologyreview.com/feed/", 1, "ai_ml", "Emerging technology analysis", "https://www.technologyreview.com", 1, 1.0),
        ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", 2, "ai_ml", "AI news and analysis", "https://www.theverge.com/ai-artificial-intelligence", 1, 1.0),
        ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", 2, "ai_ml", "Enterprise AI news", "https://venturebeat.com/category/ai/", 1, 1.0),
        # Semiconductors
        ("Tom's Hardware", "https://www.tomshardware.com/feeds/all", 2, "semiconductors", "Hardware and chip news", "https://www.tomshardware.com", 1, 0.8),
        # Robotics
        ("The Robot Report", "https://www.therobotreport.com/feed/", 1, "robotics", "Robotics industry news", "https://www.therobotreport.com", 1, 1.0),
        ("TechCrunch Robotics", "https://techcrunch.com/tag/robotics/feed/", 2, "robotics", "Robotics coverage from TechCrunch", "https://techcrunch.com/tag/robotics/", 1, 1.0),
        # Space tech
        ("SpaceNews", "https://spacenews.com/feed/", 2, "space_tech", "Space industry news", "https://spacenews.com", 1, 0.8),
        ("Ars Technica Space", "https://feeds.arstechnica.com/arstechnica/space", 2, "space_tech", "Space science and tech", "https://arstechnica.com/space/", 1, 0.8),
    ]
    for name, url, priority, category, description, website, enabled, weight in default_feeds:
        cursor.execute(
            "INSERT OR IGNORE INTO rss_feeds (name, url, priority, category, description, website, is_enabled, topic_weight) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, url, priority, category, description, website, enabled, weight),
        )

    # Migrate existing tables if needed
    migrations = [
        ("articles", "keyword_score", "INTEGER DEFAULT 0"),
        ("articles", "matched_keywords", "TEXT DEFAULT '[]'"),
        ("articles", "llm_rank", "INTEGER"),
        ("articles", "stage", "TEXT DEFAULT 'fetched'"),
        ("articles", "manual_override", "TEXT"),
        ("posts", "source_article_ids", "TEXT DEFAULT '[]'"),
        ("posts", "scheduled_at", "TIMESTAMP"),
        ("posts", "quality_score", "REAL"),
        ("posts", "ai_score", "REAL"),
        ("posts", "readability_score", "REAL"),
        ("posts", "emoji_score", "REAL"),
        ("posts", "score_details", "TEXT DEFAULT '{}'"),
        ("posts", "image_url", "TEXT"),
        ("posts", "image_path", "TEXT"),
        ("posts", "image_source", "TEXT"),
        ("posts", "image_score", "REAL"),
        ("posts", "has_image", "INTEGER DEFAULT 0"),
        ("quality_config", "auto_approve_above", "REAL DEFAULT 70.0"),
        ("engagement_replies", "reject_reason", "TEXT"),
        ("engagement_config", "auto_approve_above", "REAL DEFAULT 60.0"),
    ]
    for table, column, col_type in migrations:
        if not _column_exists(cursor, table, column):
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    conn.commit()
    conn.close()


# --- Articles ---

def save_articles(articles):
    conn = get_connection()
    cursor = conn.cursor()
    saved = 0
    new_urls = []
    for article in articles:
        try:
            cursor.execute(
                """INSERT OR IGNORE INTO articles
                   (title, url, source, summary, keyword_score, matched_keywords, stage)
                   VALUES (?, ?, ?, ?, ?, ?, 'fetched')""",
                (
                    article["title"],
                    article["url"],
                    article["source"],
                    article["summary"],
                    article.get("keyword_score", 0),
                    json.dumps(article.get("matched_keywords", [])),
                ),
            )
            if cursor.rowcount > 0:
                saved += 1
                new_urls.append(article["url"])
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    return saved, new_urls


def update_article_score(article_url, score, matched_keywords, stage="prefiltered"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE articles SET keyword_score = ?, matched_keywords = ?, stage = ? WHERE url = ?",
        (score, json.dumps(matched_keywords), stage, article_url),
    )
    conn.commit()
    conn.close()


def update_article_rank(article_url, rank, stage="ranked"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE articles SET llm_rank = ?, stage = ? WHERE url = ?",
        (rank, stage, article_url),
    )
    conn.commit()
    conn.close()


def update_article_stage(article_url, stage):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE articles SET stage = ? WHERE url = ?", (stage, article_url))
    conn.commit()
    conn.close()


def set_article_override(article_id, override):
    """Set manual override: 'include', 'exclude', or None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE articles SET manual_override = ? WHERE id = ?", (override, article_id))
    conn.commit()
    conn.close()


def get_articles(stage_filter=None):
    conn = get_connection()
    cursor = conn.cursor()
    if stage_filter:
        cursor.execute(
            "SELECT * FROM articles WHERE stage = ? ORDER BY keyword_score DESC, fetched_at DESC",
            (stage_filter,),
        )
    else:
        cursor.execute("SELECT * FROM articles ORDER BY fetched_at DESC")
    articles = cursor.fetchall()
    conn.close()
    return articles


def get_recent_articles(limit=30):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM articles ORDER BY fetched_at DESC LIMIT ?", (limit,)
    )
    articles = cursor.fetchall()
    conn.close()
    return articles


def reset_article_stages():
    """Reset all article stages to 'fetched' before a new pipeline run."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE articles SET stage = 'fetched', llm_rank = NULL WHERE stage != 'fetched'")
    conn.commit()
    conn.close()


# --- Posts ---

def get_pending_posts():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM posts WHERE status = 'pending_review' ORDER BY created_at ASC"
    )
    posts = cursor.fetchall()
    conn.close()
    return posts


def get_approved_posts():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM posts WHERE status = 'approved' ORDER BY created_at ASC"
    )
    posts = cursor.fetchall()
    conn.close()
    return posts


def get_posted_posts():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM posts WHERE status = 'posted' ORDER BY posted_at DESC"
    )
    posts = cursor.fetchall()
    conn.close()
    return posts


def get_post_by_id(post_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
    post = cursor.fetchone()
    conn.close()
    return post


def set_post_scheduled_at(post_id, scheduled_at):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE posts SET scheduled_at = ? WHERE id = ?", (scheduled_at, post_id))
    conn.commit()
    conn.close()


def clear_all_scheduled_times():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE posts SET scheduled_at = NULL WHERE status = 'approved'")
    conn.commit()
    conn.close()


def update_post_status(post_id, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE posts SET status = ? WHERE id = ?", (status, post_id))
    conn.commit()
    conn.close()


def update_post_content(post_id, content):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE posts SET content = ? WHERE id = ?", (content, post_id))
    conn.commit()
    conn.close()


def mark_as_posted(post_id, tweet_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE posts SET status = 'posted', posted_at = ?, x_tweet_id = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), tweet_id, post_id),
    )
    conn.commit()
    conn.close()


def get_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, COUNT(*) as count FROM posts GROUP BY status")
    stats = {row["status"]: row["count"] for row in cursor.fetchall()}

    cursor.execute("SELECT COUNT(*) as count FROM articles")
    stats["total_articles"] = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM articles WHERE stage = 'prefiltered'")
    stats["prefiltered"] = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM articles WHERE stage = 'ranked'")
    stats["ranked"] = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM articles WHERE stage = 'selected'")
    stats["selected"] = cursor.fetchone()["count"]

    conn.close()
    return stats


# --- API Usage ---

def log_api_usage(service, endpoint, tokens_input=0, tokens_output=0, cost_estimate=0):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO api_usage (service, endpoint, tokens_input, tokens_output, cost_estimate)
           VALUES (?, ?, ?, ?, ?)""",
        (service, endpoint, tokens_input, tokens_output, cost_estimate),
    )
    conn.commit()
    conn.close()


def get_api_usage_summary():
    conn = get_connection()
    cursor = conn.cursor()

    def _query_service(service, daily=False):
        date_filter = "AND DATE(created_at) = DATE('now')" if daily else ""
        cursor.execute(f"""
            SELECT COUNT(*) as calls,
                   COALESCE(SUM(tokens_input), 0) as input_tokens,
                   COALESCE(SUM(tokens_output), 0) as output_tokens,
                   COALESCE(SUM(cost_estimate), 0) as total_cost
            FROM api_usage WHERE service = ? {date_filter}
        """, (service,))
        row = cursor.fetchone()
        return {
            "calls": row["calls"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "total_tokens": row["input_tokens"] + row["output_tokens"],
            "cost": row["total_cost"],
        }

    # All-time totals
    mistral = _query_service("mistral")
    groq = _query_service("groq")
    x = _query_service("x")

    # Today's usage
    mistral_today = _query_service("mistral", daily=True)
    groq_today = _query_service("groq", daily=True)
    x_today = _query_service("x", daily=True)

    # Recent usage log
    cursor.execute("""
        SELECT * FROM api_usage ORDER BY created_at DESC LIMIT 20
    """)
    recent = cursor.fetchall()

    conn.close()
    return {
        # All-time
        "mistral_calls": mistral["calls"],
        "mistral_tokens_input": mistral["input_tokens"],
        "mistral_tokens_output": mistral["output_tokens"],
        "mistral_tokens_total": mistral["total_tokens"],
        "mistral_cost": mistral["cost"],
        "groq_calls": groq["calls"],
        "groq_tokens_total": groq["total_tokens"],
        "groq_cost": groq["cost"],
        "x_posts": x["calls"],
        "x_cost": x["cost"],
        # Today
        "mistral_today_calls": mistral_today["calls"],
        "mistral_today_tokens": mistral_today["total_tokens"],
        "mistral_today_cost": mistral_today["cost"],
        "groq_today_calls": groq_today["calls"],
        "groq_today_tokens": groq_today["total_tokens"],
        "x_today_posts": x_today["calls"],
        "x_today_cost": x_today["cost"],
        "recent": recent,
    }


# --- Schedule Config ---

def get_schedule_config():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM schedule_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "mode": "fixed",
        "fixed_interval_hours": 24,
        "fixed_interval_minutes": 0,
        "random_tweets_per_day": 1,
        "random_min_gap_hours": 3,
        "random_min_gap_minutes": 0,
        "random_max_gap_hours": 15,
        "random_max_gap_minutes": 0,
        "random_start_hour": 9,
        "random_start_minute": 0,
        "random_end_hour": 22,
        "random_end_minute": 0,
        "timezone": "Europe/Paris",
        "is_active": 0,
    }


def update_schedule_config(**kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    allowed = [
        "mode", "fixed_interval_hours", "fixed_interval_minutes",
        "random_tweets_per_day",
        "random_min_gap_hours", "random_min_gap_minutes",
        "random_max_gap_hours", "random_max_gap_minutes",
        "random_start_hour", "random_start_minute",
        "random_end_hour", "random_end_minute",
        "timezone", "is_active",
    ]
    sets = []
    values = []
    for key, val in kwargs.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(val)
    if sets:
        sets.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE schedule_config SET {', '.join(sets)} WHERE id = 1"
        cursor.execute(query, values)
        conn.commit()
    conn.close()


# --- Quality Config ---

def get_quality_config():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM quality_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {}


def update_quality_config(**kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    allowed = [
        "ai_detection_enabled", "ai_penalty_phrases", "ai_emdash_penalty",
        "ai_phrase_penalty", "readability_enabled", "readability_jargon_list",
        "readability_jargon_penalty", "readability_max_grade_level",
        "emoji_enabled", "emoji_preferred", "emoji_leading_bonus",
        "weight_ai", "weight_readability", "weight_emoji",
        "min_quality_score", "auto_reject_below", "auto_approve_above",
    ]
    sets = []
    values = []
    for key, val in kwargs.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(val)
    if sets:
        sets.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE quality_config SET {', '.join(sets)} WHERE id = 1"
        cursor.execute(query, values)
        conn.commit()
    conn.close()


# --- RSS Feeds ---

def get_rss_feeds(enabled_only=False):
    conn = get_connection()
    cursor = conn.cursor()
    if enabled_only:
        cursor.execute("SELECT * FROM rss_feeds WHERE is_enabled = 1 ORDER BY category, priority, name")
    else:
        cursor.execute("SELECT * FROM rss_feeds ORDER BY category, priority, name")
    feeds = cursor.fetchall()
    conn.close()
    return [dict(f) for f in feeds]


def add_rss_feed(name, url, priority=2, category="industry_news", description="", website=""):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO rss_feeds (name, url, priority, category, description, website) VALUES (?, ?, ?, ?, ?, ?)",
            (name, url, priority, category, description, website),
        )
        conn.commit()
        feed_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        feed_id = None
    conn.close()
    return feed_id


def toggle_rss_feed(feed_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE rss_feeds SET is_enabled = CASE WHEN is_enabled = 1 THEN 0 ELSE 1 END WHERE id = ?", (feed_id,))
    conn.commit()
    conn.close()


def delete_rss_feed(feed_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM rss_feeds WHERE id = ?", (feed_id,))
    conn.commit()
    conn.close()


def update_rss_feed_weight(feed_id, weight):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE rss_feeds SET topic_weight = ? WHERE id = ?", (weight, feed_id))
    conn.commit()
    conn.close()


# --- Topic Categories ---

def get_topic_categories(enabled_only=False):
    conn = get_connection()
    cursor = conn.cursor()
    if enabled_only:
        cursor.execute("SELECT * FROM topic_categories WHERE is_enabled = 1 ORDER BY sort_order")
    else:
        cursor.execute("SELECT * FROM topic_categories ORDER BY sort_order")
    cats = cursor.fetchall()
    conn.close()
    return [dict(c) for c in cats]


def update_topic_category(cat_id, **kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    allowed = ["label", "icon", "color", "is_enabled", "weight", "sort_order"]
    sets = []
    values = []
    for key, val in kwargs.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(val)
    if sets:
        query = f"UPDATE topic_categories SET {', '.join(sets)} WHERE id = ?"
        values.append(cat_id)
        cursor.execute(query, values)
        conn.commit()
    conn.close()


# --- Posts with scores ---

def save_posts(posts, batch_id, source_article_ids=None):
    conn = get_connection()
    cursor = conn.cursor()
    ids_json = json.dumps(source_article_ids or [])
    for post in posts:
        cursor.execute(
            """INSERT INTO posts (content, post_type, status, batch_id, source_article_ids,
               quality_score, ai_score, readability_score, emoji_score, score_details,
               image_url, image_path, image_source, image_score, has_image)
               VALUES (?, ?, 'pending_review', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                post["content"], post["type"], batch_id, ids_json,
                post.get("quality_score"),
                post.get("ai_score"),
                post.get("readability_score"),
                post.get("emoji_score"),
                post.get("score_details", "{}"),
                post.get("image_url"),
                post.get("image_path"),
                post.get("image_source"),
                post.get("image_score"),
                post.get("has_image", 0),
            ),
        )
    conn.commit()
    conn.close()


def update_post_scores(post_id, quality_score, ai_score, readability_score, emoji_score, score_details="{}"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE posts SET quality_score = ?, ai_score = ?, readability_score = ?, emoji_score = ?, score_details = ? WHERE id = ?",
        (quality_score, ai_score, readability_score, emoji_score, score_details, post_id),
    )
    conn.commit()
    conn.close()


def update_post_image(post_id, image_url, image_path, image_source, image_score, has_image=1):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE posts SET image_url = ?, image_path = ?, image_source = ?, image_score = ?, has_image = ? WHERE id = ?",
        (image_url, image_path, image_source, image_score, has_image, post_id),
    )
    conn.commit()
    conn.close()


def clear_post_image(post_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE posts SET image_url = NULL, image_path = NULL, image_source = NULL, image_score = NULL, has_image = 0 WHERE id = ?",
        (post_id,),
    )
    conn.commit()
    conn.close()


# --- Image Config ---

def get_image_config():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM image_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"images_enabled": 1, "image_ratio": 0.66, "min_image_score": 50.0}


def update_image_config(**kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    allowed = [
        "images_enabled", "image_ratio", "min_image_score",
        "unsplash_api_key", "pexels_api_key", "prefer_article_images",
    ]
    sets = []
    values = []
    for key, val in kwargs.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(val)
    if sets:
        sets.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE image_config SET {', '.join(sets)} WHERE id = 1"
        cursor.execute(query, values)
        conn.commit()
    conn.close()


# --- Target Accounts (Engagement) ---

def get_target_accounts(enabled_only=False):
    conn = get_connection()
    cursor = conn.cursor()
    if enabled_only:
        cursor.execute("SELECT * FROM target_accounts WHERE is_enabled = 1 ORDER BY priority, username")
    else:
        cursor.execute("SELECT * FROM target_accounts ORDER BY priority, username")
    accounts = cursor.fetchall()
    conn.close()
    return [dict(a) for a in accounts]


def add_target_account(username, category="general", reply_style="mixed", priority=2):
    username = username.lstrip("@").strip()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO target_accounts (username, category, reply_style, priority) VALUES (?, ?, ?, ?)",
            (username, category, reply_style, priority),
        )
        conn.commit()
        account_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        account_id = None
    conn.close()
    return account_id


def update_target_account(account_id, **kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    allowed = ["username", "user_id", "display_name", "category", "reply_style",
               "is_enabled", "priority", "last_seen_tweet_id", "last_polled_at", "poll_errors"]
    sets = []
    values = []
    for key, val in kwargs.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(val)
    if sets:
        query = f"UPDATE target_accounts SET {', '.join(sets)} WHERE id = ?"
        values.append(account_id)
        cursor.execute(query, values)
        conn.commit()
    conn.close()


def delete_target_account(account_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM target_accounts WHERE id = ?", (account_id,))
    conn.commit()
    conn.close()


def update_target_last_seen(account_id, tweet_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE target_accounts SET last_seen_tweet_id = ?, last_polled_at = ? WHERE id = ?",
        (tweet_id, datetime.utcnow().isoformat(), account_id),
    )
    conn.commit()
    conn.close()


def increment_target_errors(account_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE target_accounts SET poll_errors = poll_errors + 1 WHERE id = ?",
        (account_id,),
    )
    # Auto-disable after 20 consecutive errors (was 5 — too aggressive)
    cursor.execute(
        "UPDATE target_accounts SET is_enabled = 0 WHERE id = ? AND poll_errors >= 20",
        (account_id,),
    )
    conn.commit()
    conn.close()


def reset_target_errors(account_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE target_accounts SET poll_errors = 0 WHERE id = ?", (account_id,))
    conn.commit()
    conn.close()


# --- Engagement Replies ---

def save_engagement_reply(target_account_id, target_username, original_tweet_id,
                          original_tweet_text, original_tweet_url, reply_content,
                          reply_style, quality_score=None, score_details="{}",
                          reply_after=None, status="approved", reject_reason=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO engagement_replies
               (target_account_id, target_username, original_tweet_id, original_tweet_text,
                original_tweet_url, reply_content, reply_style, status, quality_score,
                score_details, reply_after, reject_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (target_account_id, target_username, original_tweet_id, original_tweet_text,
             original_tweet_url, reply_content, reply_style, status, quality_score,
             score_details, reply_after, reject_reason),
        )
        conn.commit()
        reply_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        reply_id = None
    conn.close()
    return reply_id


def get_ready_engagement_replies():
    """Get approved replies whose delay has passed (ready to post)."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute(
        """SELECT * FROM engagement_replies
           WHERE status = 'approved' AND (reply_after IS NULL OR reply_after <= ?)
           ORDER BY created_at ASC""",
        (now,),
    )
    replies = cursor.fetchall()
    conn.close()
    return [dict(r) for r in replies]


def get_pending_engagement_replies():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM engagement_replies WHERE status IN ('approved', 'pending_review') ORDER BY created_at ASC"
    )
    replies = cursor.fetchall()
    conn.close()
    return [dict(r) for r in replies]


def update_engagement_reply_status(reply_id, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE engagement_replies SET status = ? WHERE id = ?", (status, reply_id))
    conn.commit()
    conn.close()


def mark_engagement_reply_posted(reply_id, x_reply_tweet_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE engagement_replies SET status = 'posted', posted_at = ?, x_reply_tweet_id = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), x_reply_tweet_id, reply_id),
    )
    conn.commit()
    conn.close()


def get_engagement_replies_today():
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT COUNT(*) as count FROM engagement_replies WHERE status = 'posted' AND DATE(posted_at) = ?",
        (today,),
    )
    count = cursor.fetchone()["count"]
    conn.close()
    return count


def get_engagement_replies_today_for_account(account_id):
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    cursor.execute(
        """SELECT COUNT(*) as count FROM engagement_replies
           WHERE target_account_id = ? AND status = 'posted' AND DATE(posted_at) = ?""",
        (account_id, today),
    )
    count = cursor.fetchone()["count"]
    conn.close()
    return count


def tweet_already_replied(original_tweet_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as count FROM engagement_replies WHERE original_tweet_id = ?",
        (original_tweet_id,),
    )
    exists = cursor.fetchone()["count"] > 0
    conn.close()
    return exists


def get_engagement_history(limit=50):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM engagement_replies ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    replies = cursor.fetchall()
    conn.close()
    return [dict(r) for r in replies]


def get_recent_reply_contents(limit=50):
    """Get recent reply texts for duplicate detection."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT reply_content FROM engagement_replies WHERE status IN ('approved', 'posted') ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    contents = [row["reply_content"] for row in cursor.fetchall()]
    conn.close()
    return contents


# --- Engagement Config ---

def get_engagement_config():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM engagement_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "is_enabled": 0,
        "poll_interval_minutes": 10,
        "max_replies_per_day": 10,
        "max_replies_per_account_per_day": 3,
        "reply_delay_min_minutes": 2,
        "reply_delay_max_minutes": 15,
        "auto_reject_below": 35.0,
        "max_reply_length": 280,
        "reply_window_hours": 6,
        "timezone": "Europe/Paris",
        "active_start_hour": 8,
        "active_end_hour": 23,
    }


def update_engagement_config(**kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    allowed = [
        "is_enabled", "poll_interval_minutes", "max_replies_per_day",
        "max_replies_per_account_per_day", "reply_delay_min_minutes",
        "reply_delay_max_minutes", "auto_reject_below", "max_reply_length",
        "reply_window_hours", "timezone", "active_start_hour", "active_end_hour",
    ]
    sets = []
    values = []
    for key, val in kwargs.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(val)
    if sets:
        sets.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE engagement_config SET {', '.join(sets)} WHERE id = 1"
        cursor.execute(query, values)
        conn.commit()
    conn.close()


# --- Usage Limits ---

def get_usage_limits():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usage_limits WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "mistral_max_tokens_per_day": 500000,
        "mistral_max_calls_per_day": 50,
        "mistral_max_cost_per_day": 1.00,
        "x_max_tweets_per_day": 15,
        "x_max_replies_per_day": 10,
        "warning_threshold_pct": 80,
        "alert_email": "",
        "alerts_enabled": 0,
        "max_consecutive_errors": 5,
        "current_consecutive_errors": 0,
    }


def update_usage_limits(**kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    allowed = [
        "mistral_max_tokens_per_day", "mistral_max_calls_per_day",
        "mistral_max_cost_per_day", "x_max_tweets_per_day", "x_max_replies_per_day",
        "warning_threshold_pct", "alert_email", "smtp_host", "smtp_port",
        "smtp_user", "smtp_password", "alerts_enabled", "daily_summary_enabled",
        "max_consecutive_errors",
    ]
    sets = []
    values = []
    for key, val in kwargs.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(val)
    if sets:
        sets.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE usage_limits SET {', '.join(sets)} WHERE id = 1"
        cursor.execute(query, values)
        conn.commit()
    conn.close()


def get_daily_usage(service=None):
    """Get today's API usage, optionally filtered by service."""
    conn = get_connection()
    cursor = conn.cursor()
    if service:
        cursor.execute("""
            SELECT COUNT(*) as calls,
                   COALESCE(SUM(tokens_input + tokens_output), 0) as total_tokens,
                   COALESCE(SUM(cost_estimate), 0) as total_cost
            FROM api_usage WHERE service = ? AND DATE(created_at) = DATE('now')
        """, (service,))
    else:
        cursor.execute("""
            SELECT service, COUNT(*) as calls,
                   COALESCE(SUM(tokens_input + tokens_output), 0) as total_tokens,
                   COALESCE(SUM(cost_estimate), 0) as total_cost
            FROM api_usage WHERE DATE(created_at) = DATE('now')
            GROUP BY service
        """)
        rows = cursor.fetchall()
        conn.close()
        return {row["service"]: dict(row) for row in rows}
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {"calls": 0, "total_tokens": 0, "total_cost": 0}


def get_daily_tweet_count():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) as count FROM api_usage
        WHERE service = 'x' AND endpoint = 'create_tweet' AND DATE(created_at) = DATE('now')
    """)
    count = cursor.fetchone()["count"]
    conn.close()
    return count


def get_daily_reply_count():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) as count FROM api_usage
        WHERE service = 'x' AND endpoint = 'create_reply' AND DATE(created_at) = DATE('now')
    """)
    count = cursor.fetchone()["count"]
    conn.close()
    return count


# --- Monthly Usage ---

def get_monthly_usage(service, year=None, month=None):
    """Get current month's API usage for a service."""
    now = datetime.utcnow()
    y = str(year or now.year)
    m = f"{(month or now.month):02d}"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) as calls,
               COALESCE(SUM(tokens_input + tokens_output), 0) as total_tokens,
               COALESCE(SUM(tokens_input), 0) as total_input,
               COALESCE(SUM(tokens_output), 0) as total_output,
               COALESCE(SUM(cost_estimate), 0) as total_cost
        FROM api_usage
        WHERE service = ?
          AND strftime('%Y', created_at) = ?
          AND strftime('%m', created_at) = ?
    """, (service, y, m))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {"calls": 0, "total_tokens": 0, "total_input": 0, "total_output": 0, "total_cost": 0}


def get_monthly_usage_by_day(service, year=None, month=None):
    """Get day-by-day usage breakdown for the current month."""
    now = datetime.utcnow()
    y = str(year or now.year)
    m = f"{(month or now.month):02d}"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DATE(created_at) as date,
               COUNT(*) as calls,
               COALESCE(SUM(tokens_input + tokens_output), 0) as total_tokens,
               COALESCE(SUM(cost_estimate), 0) as total_cost
        FROM api_usage
        WHERE service = ?
          AND strftime('%Y', created_at) = ?
          AND strftime('%m', created_at) = ?
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    """, (service, y, m))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monthly_usage_by_endpoint(service, year=None, month=None):
    """Get token usage breakdown by endpoint for the current month."""
    now = datetime.utcnow()
    y = str(year or now.year)
    m = f"{(month or now.month):02d}"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT endpoint,
               COUNT(*) as calls,
               COALESCE(SUM(tokens_input + tokens_output), 0) as total_tokens,
               COALESCE(SUM(cost_estimate), 0) as total_cost
        FROM api_usage
        WHERE service = ?
          AND strftime('%Y', created_at) = ?
          AND strftime('%m', created_at) = ?
        GROUP BY endpoint
        ORDER BY total_tokens DESC
    """, (service, y, m))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Monthly Budget ---

def get_monthly_budget():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monthly_budget WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "mistral_monthly_token_limit": 1000000,
        "groq_monthly_token_limit": 1500000,
        "auto_throttle_enabled": 1,
        "throttle_start_pct": 70,
        "throttle_medium_pct": 85,
        "emergency_stop_pct": 95,
        "budget_alert_threshold_pct": 75,
    }


def update_monthly_budget(**kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    allowed = [
        "mistral_monthly_token_limit", "groq_monthly_token_limit",
        "auto_throttle_enabled", "throttle_start_pct", "throttle_medium_pct",
        "emergency_stop_pct", "budget_alert_threshold_pct",
    ]
    sets = []
    values = []
    for key, val in kwargs.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(val)
    if sets:
        sets.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE monthly_budget SET {', '.join(sets)} WHERE id = 1"
        cursor.execute(query, values)
        conn.commit()
    conn.close()


# --- Kill Switch ---

def get_kill_switch():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM kill_switch WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"is_killed": 0, "killed_at": None, "killed_reason": "", "killed_by": ""}


def set_kill_switch(killed, reason="", killed_by=""):
    conn = get_connection()
    cursor = conn.cursor()
    if killed:
        cursor.execute(
            "UPDATE kill_switch SET is_killed = 1, killed_at = ?, killed_reason = ?, killed_by = ? WHERE id = 1",
            (datetime.utcnow().isoformat(), reason, killed_by),
        )
    else:
        cursor.execute(
            "UPDATE kill_switch SET is_killed = 0, killed_at = NULL, killed_reason = '', killed_by = '' WHERE id = 1"
        )
    conn.commit()
    conn.close()


def is_bot_killed():
    ks = get_kill_switch()
    return bool(ks.get("is_killed"))


# --- Alert Log ---

def log_alert(alert_type, message):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO alert_log (alert_type, message) VALUES (?, ?)",
        (alert_type, message),
    )
    conn.commit()
    conn.close()


def was_alert_sent_today(alert_type):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as count FROM alert_log WHERE alert_type = ? AND DATE(sent_at) = DATE('now')",
        (alert_type,),
    )
    count = cursor.fetchone()["count"]
    conn.close()
    return count > 0


def get_recent_alerts(limit=20):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alert_log ORDER BY sent_at DESC LIMIT ?", (limit,))
    alerts = cursor.fetchall()
    conn.close()
    return [dict(a) for a in alerts]


# --- Consecutive Error Tracking ---

def increment_consecutive_errors():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE usage_limits SET current_consecutive_errors = current_consecutive_errors + 1 WHERE id = 1"
    )
    conn.commit()
    cursor.execute("SELECT current_consecutive_errors, max_consecutive_errors FROM usage_limits WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row)


def reset_consecutive_errors():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE usage_limits SET current_consecutive_errors = 0 WHERE id = 1")
    conn.commit()
    conn.close()


# --- Analytics Config ---

def get_analytics_config():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analytics_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "is_enabled": 0,
        "collection_interval_hours": 12,
        "lookback_days": 30,
        "own_username": "",
    }


def update_analytics_config(**kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    allowed = ["is_enabled", "collection_interval_hours", "lookback_days", "own_username"]
    sets = []
    values = []
    for key, val in kwargs.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(val)
    if sets:
        query = f"UPDATE analytics_config SET {', '.join(sets)} WHERE id = 1"
        cursor.execute(query, values)
        conn.commit()
    conn.close()


# --- Tweet & Account Metrics (write) ---

def save_tweet_metrics(tweet_id, post_id, likes, retweets, replies, quotes, views, bookmarks=0):
    engagement_rate = 0.0
    if views and views > 0:
        engagement_rate = (likes + retweets + replies + quotes) / views * 100
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO tweet_metrics
           (tweet_id, post_id, likes, retweets, replies, quotes, views, bookmarks, engagement_rate)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (tweet_id, post_id, likes, retweets, replies, quotes, views, bookmarks, engagement_rate),
    )
    conn.commit()
    conn.close()


def save_account_metrics(followers, following, tweets_count=0, listed_count=0):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO account_metrics (followers, following, tweets_count, listed_count)
           VALUES (?, ?, ?, ?)""",
        (followers, following, tweets_count, listed_count),
    )
    conn.commit()
    conn.close()


def get_posted_tweets_with_ids(days=30):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, x_tweet_id, content, post_type, posted_at
           FROM posts
           WHERE status = 'posted' AND x_tweet_id IS NOT NULL
             AND posted_at >= datetime('now', ?)
           ORDER BY posted_at DESC""",
        (f"-{days} days",),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Tweet & Account Metrics (read/aggregation) ---

_LATEST_METRICS_SUBQUERY = """
    (SELECT tweet_id, MAX(collected_at) AS max_ca
     FROM tweet_metrics GROUP BY tweet_id) latest
"""


def get_latest_tweet_metrics():
    """Return the most recent metrics snapshot for each tweet, joined with post data."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT tm.tweet_id, tm.likes, tm.retweets, tm.replies, tm.quotes,
               tm.views, tm.bookmarks, tm.engagement_rate, tm.collected_at,
               p.id AS post_id, p.content, p.post_type, p.posted_at,
               p.quality_score, p.has_image
        FROM tweet_metrics tm
        INNER JOIN {_LATEST_METRICS_SUBQUERY}
            ON tm.tweet_id = latest.tweet_id AND tm.collected_at = latest.max_ca
        LEFT JOIN posts p ON tm.post_id = p.id
        ORDER BY p.posted_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_engagement_by_post_type():
    """Return average engagement metrics grouped by post_type."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT p.post_type,
               AVG(tm.likes) AS avg_likes,
               AVG(tm.retweets) AS avg_retweets,
               AVG(tm.replies) AS avg_replies,
               AVG(tm.views) AS avg_views,
               AVG(tm.engagement_rate) AS avg_engagement_rate,
               COUNT(DISTINCT tm.tweet_id) AS tweet_count
        FROM tweet_metrics tm
        INNER JOIN {_LATEST_METRICS_SUBQUERY}
            ON tm.tweet_id = latest.tweet_id AND tm.collected_at = latest.max_ca
        JOIN posts p ON tm.post_id = p.id
        WHERE p.post_type IS NOT NULL
        GROUP BY p.post_type
        ORDER BY avg_engagement_rate DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_engagement_heatmap_data():
    """Return average engagement by hour of day and day of week."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT CAST(strftime('%w', p.posted_at) AS INTEGER) AS day_of_week,
               CAST(strftime('%H', p.posted_at) AS INTEGER) AS hour,
               AVG(tm.engagement_rate) AS avg_engagement,
               COUNT(*) AS count
        FROM tweet_metrics tm
        INNER JOIN {_LATEST_METRICS_SUBQUERY}
            ON tm.tweet_id = latest.tweet_id AND tm.collected_at = latest.max_ca
        JOIN posts p ON tm.post_id = p.id
        WHERE p.posted_at IS NOT NULL
        GROUP BY day_of_week, hour
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_follower_history(days=30):
    """Return account metrics history for the given period."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT followers, following, tweets_count, listed_count, collected_at
           FROM account_metrics
           WHERE collected_at >= datetime('now', ?)
           ORDER BY collected_at ASC""",
        (f"-{days} days",),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_engagement_over_time(days=30):
    """Return daily aggregated engagement trends."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT DATE(collected_at) AS date,
                  AVG(likes) AS avg_likes,
                  AVG(retweets) AS avg_retweets,
                  AVG(replies) AS avg_replies,
                  AVG(engagement_rate) AS avg_engagement_rate,
                  SUM(views) AS total_views
           FROM tweet_metrics
           WHERE collected_at >= datetime('now', ?)
           GROUP BY DATE(collected_at)
           ORDER BY date ASC""",
        (f"-{days} days",),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_top_tweets(limit=5, metric="likes"):
    """Return top N tweets by a chosen metric (latest snapshot)."""
    allowed_metrics = {"likes", "retweets", "replies", "views", "engagement_rate"}
    if metric not in allowed_metrics:
        metric = "likes"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT tm.tweet_id, tm.likes, tm.retweets, tm.replies, tm.quotes,
               tm.views, tm.engagement_rate,
               p.content, p.post_type, p.posted_at
        FROM tweet_metrics tm
        INNER JOIN {_LATEST_METRICS_SUBQUERY}
            ON tm.tweet_id = latest.tweet_id AND tm.collected_at = latest.max_ca
        LEFT JOIN posts p ON tm.post_id = p.id
        ORDER BY tm.{metric} DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_flop_tweets(limit=5):
    """Return lowest engagement_rate tweets with views > 100."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT tm.tweet_id, tm.likes, tm.retweets, tm.replies, tm.quotes,
               tm.views, tm.engagement_rate,
               p.content, p.post_type, p.posted_at
        FROM tweet_metrics tm
        INNER JOIN {_LATEST_METRICS_SUBQUERY}
            ON tm.tweet_id = latest.tweet_id AND tm.collected_at = latest.max_ca
        LEFT JOIN posts p ON tm.post_id = p.id
        WHERE tm.views > 100
        ORDER BY tm.engagement_rate ASC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_quality_vs_engagement():
    """Return quality_score vs engagement_rate for correlation analysis."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT p.quality_score, tm.engagement_rate, tm.likes, tm.views, p.post_type
        FROM tweet_metrics tm
        INNER JOIN {_LATEST_METRICS_SUBQUERY}
            ON tm.tweet_id = latest.tweet_id AND tm.collected_at = latest.max_ca
        JOIN posts p ON tm.post_id = p.id
        WHERE p.quality_score IS NOT NULL
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_analytics_summary():
    """Return aggregated KPI card data."""
    conn = get_connection()
    cursor = conn.cursor()

    # Total tracked tweets and averages
    cursor.execute(f"""
        SELECT COUNT(DISTINCT tm.tweet_id) AS total_tweets,
               AVG(tm.engagement_rate) AS avg_engagement_rate,
               SUM(tm.views) AS total_views,
               AVG(tm.likes) AS avg_likes,
               AVG(tm.retweets) AS avg_retweets
        FROM tweet_metrics tm
        INNER JOIN {_LATEST_METRICS_SUBQUERY}
            ON tm.tweet_id = latest.tweet_id AND tm.collected_at = latest.max_ca
    """)
    metrics_row = cursor.fetchone()
    summary = dict(metrics_row) if metrics_row else {
        "total_tweets": 0, "avg_engagement_rate": 0, "total_views": 0,
        "avg_likes": 0, "avg_retweets": 0,
    }

    # Latest follower count
    cursor.execute("SELECT followers, following FROM account_metrics ORDER BY collected_at DESC LIMIT 1")
    latest = cursor.fetchone()
    summary["followers"] = latest["followers"] if latest else 0
    summary["following"] = latest["following"] if latest else 0

    # Follower growth (7 days)
    cursor.execute("SELECT followers FROM account_metrics WHERE collected_at >= datetime('now', '-7 days') ORDER BY collected_at ASC LIMIT 1")
    week_ago = cursor.fetchone()
    if week_ago and latest:
        summary["follower_growth_7d"] = latest["followers"] - week_ago["followers"]
    else:
        summary["follower_growth_7d"] = 0

    conn.close()
    return summary
