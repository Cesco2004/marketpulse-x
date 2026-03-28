from flask import Blueprint, render_template
from storage.database import get_approved_posts, get_posted_posts, get_post_by_id, update_post_status, mark_as_posted
from pipeline import publish_post

bp = Blueprint("pipeline_page", __name__)


@bp.route("/pipeline")
def pipeline_page():
    queue_posts = get_approved_posts()
    published_posts = get_posted_posts()
    return render_template("pipeline.html",
                           queue_posts=queue_posts,
                           published_posts=published_posts)


# --- HTMX tab content ---

@bp.route("/api/pipeline/queue")
def queue_tab():
    posts = get_approved_posts()
    if not posts:
        return '<div style="color:var(--text-secondary);padding:2rem;text-align:center">Queue is empty. <a href="/review">Review pending posts</a> to add them.</div>'

    html_parts = []
    for i, post in enumerate(posts, 1):
        clen = len(post["content"])
        chars_class = "chars-ok" if clen <= 260 else ("chars-warn" if clen <= 280 else "chars-over")
        score_html = ""
        if post["quality_score"] is not None:
            s = int(round(post["quality_score"]))
            sc = "score-good" if s >= 70 else ("score-warn" if s >= 50 else "score-bad")
            score_html = f'<span class="score-badge {sc}" style="width:28px;height:28px;font-size:0.65rem">{s}</span>'
        img_badge = '<span class="badge" style="background:rgba(99,102,241,0.12);color:var(--qb-accent-soft);font-size:0.65rem">IMG</span>' if post.get("has_image") else ""

        html_parts.append(f'''
        <div class="post-card" id="queue-card-{post["id"]}">
            <div class="post-meta" style="margin-bottom:0.4rem">
                <strong>#{i}</strong>
                <span class="badge badge-{post["post_type"]}">{post["post_type"]}</span>
                <span class="{chars_class}">{clen} chars</span>
                {img_badge} {score_html}
            </div>
            <div class="post-content">{post["content"]}</div>
            <div class="post-actions">
                <button hx-post="/api/posts/{post["id"]}/post-now"
                        hx-target="#queue-card-{post["id"]}" hx-swap="outerHTML"
                        hx-confirm="Post this tweet now?">Post Now</button>
                <button class="outline secondary"
                        hx-post="/api/posts/{post["id"]}/unqueue"
                        hx-target="#queue-card-{post["id"]}" hx-swap="outerHTML">Remove</button>
            </div>
        </div>
        ''')
    return "".join(html_parts)


@bp.route("/api/pipeline/published")
def published_tab():
    posts = get_posted_posts()
    if not posts:
        return '<div style="color:var(--text-secondary);padding:2rem;text-align:center">No posts published yet.</div>'

    html_parts = []
    for post in posts:
        x_link = ""
        if post.get("x_tweet_id"):
            x_link = f'<a href="https://x.com/QEdgeIntel/status/{post["x_tweet_id"]}" target="_blank" style="font-size:0.78rem">View on X</a>'

        html_parts.append(f'''
        <div class="post-card">
            <div class="post-content">{post["content"]}</div>
            <div class="post-meta">
                <span class="badge badge-{post["post_type"]}">{post["post_type"]}</span>
                <span style="font-size:0.78rem">{len(post["content"])} chars</span>
                <span style="color:var(--qb-gray);font-size:0.78rem">{post.get("posted_at", "unknown")}</span>
                {x_link}
            </div>
        </div>
        ''')
    return "".join(html_parts)
